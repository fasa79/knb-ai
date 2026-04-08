"""Semantic query cache — avoids redundant LLM calls for similar questions.

Uses embedding similarity to detect near-duplicate queries.
"What's the TWRR?" and "What was Khazanah's TWRR?" will hit the same cache entry.

Zero API cost for cached responses. LRU eviction when cache is full.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from app.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """A cached query-response pair."""

    query: str
    query_embedding: list[float]
    response: dict[str, Any]
    timestamp: float = field(default_factory=time.time)


class SemanticCache:
    """Embedding-based cache: similar questions return cached answers."""

    def __init__(
        self,
        max_size: int = 100,
        similarity_threshold: float = 0.95,
        embedding_service=None,
    ):
        self.max_size = max_size
        self.similarity_threshold = similarity_threshold
        self._embedding_service = embedding_service
        self._entries: list[CacheEntry] = []

    @property
    def embedding_service(self):
        if self._embedding_service is None:
            from app.core.embeddings import get_embedding_service
            self._embedding_service = get_embedding_service()
        return self._embedding_service

    def get(self, query: str) -> dict[str, Any] | None:
        """Check cache for a similar query. Returns cached response or None."""
        if not self._entries:
            return None

        query_emb = self.embedding_service.embed_query(query)

        best_score = 0.0
        best_entry: CacheEntry | None = None

        for entry in self._entries:
            score = self._cosine_similarity(query_emb, entry.query_embedding)
            if score > best_score:
                best_score = score
                best_entry = entry

        if best_score >= self.similarity_threshold and best_entry is not None:
            logger.info(f"Cache HIT (score={best_score:.3f}): '{query[:50]}...'")
            return best_entry.response

        return None

    def put(self, query: str, response: dict[str, Any]) -> None:
        """Store a query-response pair in the cache."""
        query_emb = self.embedding_service.embed_query(query)

        self._entries.append(CacheEntry(
            query=query,
            query_embedding=query_emb,
            response=response,
        ))

        # LRU eviction
        if len(self._entries) > self.max_size:
            self._entries.pop(0)

        logger.info(f"Cache STORE: '{query[:50]}...' (size={len(self._entries)})")

    def clear(self) -> None:
        """Clear all cached entries."""
        self._entries.clear()
        logger.info("Cache cleared")

    @property
    def size(self) -> int:
        return len(self._entries)

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        a_arr = np.array(a)
        b_arr = np.array(b)
        return float(np.dot(a_arr, b_arr) / (np.linalg.norm(a_arr) * np.linalg.norm(b_arr) + 1e-9))


_cache: SemanticCache | None = None


def get_semantic_cache() -> SemanticCache:
    """Return singleton semantic cache."""
    global _cache
    if _cache is None:
        settings = get_settings()
        _cache = SemanticCache(
            max_size=settings.cache_max_size,
            similarity_threshold=settings.cache_similarity_threshold,
        )
    return _cache
