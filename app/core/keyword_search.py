"""BM25 keyword search — complements vector search for exact term matching.

Vector search is great for semantic similarity ("financial performance" ↔ "returns"),
but misses exact terms like "TWRR", "RM156b", specific company names.
BM25 catches those via token-level matching.

This index is rebuilt from the vector store contents on startup/ingestion.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)


@dataclass
class BM25Result:
    """A single BM25 search result."""

    id: str
    text: str
    metadata: dict[str, Any]
    score: float


class KeywordSearchService:
    """BM25-based keyword search over document chunks."""

    def __init__(self):
        self._index: BM25Okapi | None = None
        self._documents: list[dict[str, Any]] = []

    @property
    def is_ready(self) -> bool:
        return self._index is not None and len(self._documents) > 0

    def build_index(self, ids: list[str], texts: list[str], metadatas: list[dict[str, Any]]) -> None:
        """Build the BM25 index from document chunks."""
        self._documents = [
            {"id": id_, "text": text, "metadata": meta}
            for id_, text, meta in zip(ids, texts, metadatas)
        ]

        # Tokenize all documents
        tokenized = [self._tokenize(text) for text in texts]
        self._index = BM25Okapi(tokenized)

        logger.info(f"BM25 index built: {len(self._documents)} documents")

    def build_from_vector_store(self, vector_store) -> None:
        """Build index from an existing ChromaDB collection."""
        collection = vector_store.collection
        result = collection.get(include=["documents", "metadatas"])

        if not result["ids"]:
            logger.warning("Vector store is empty, cannot build BM25 index")
            return

        self.build_index(
            ids=result["ids"],
            texts=result["documents"],
            metadatas=result["metadatas"],
        )

    def search(self, query: str, top_k: int = 10) -> list[BM25Result]:
        """Search for documents matching the query terms."""
        if not self.is_ready:
            return []

        tokenized_query = self._tokenize(query)
        scores = self._index.get_scores(tokenized_query)

        # Get top-k indices by score
        ranked_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]

        results = []
        for idx in ranked_indices:
            if scores[idx] > 0:  # Only return docs with some match
                doc = self._documents[idx]
                results.append(BM25Result(
                    id=doc["id"],
                    text=doc["text"],
                    metadata=doc["metadata"],
                    score=float(scores[idx]),
                ))

        return results

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Tokenize text for BM25 — lowercase, split on non-alphanumeric."""
        text = text.lower()
        tokens = re.findall(r"\b[a-z0-9]+(?:\.[0-9]+)?[a-z0-9]*\b", text)
        # Keep financial terms intact
        return [t for t in tokens if len(t) > 1]


_keyword_service: KeywordSearchService | None = None


def get_keyword_search() -> KeywordSearchService:
    """Return singleton keyword search service."""
    global _keyword_service
    if _keyword_service is None:
        _keyword_service = KeywordSearchService()
    return _keyword_service
