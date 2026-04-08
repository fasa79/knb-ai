"""Vector store service — ChromaDB wrapper with CRUD operations.

Provides a clean interface for storing, querying, and managing document embeddings.
Swappable: to use FAISS/Pinecone, implement the same interface.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """A single search result from the vector store."""

    id: str
    text: str
    metadata: dict[str, Any]
    score: float  # similarity score (higher = more similar)


class VectorStoreService:
    """ChromaDB-backed vector store for document chunks."""

    def __init__(self, persist_dir: str, collection_name: str):
        self.persist_dir = persist_dir
        self.collection_name = collection_name
        self._client: chromadb.ClientAPI | None = None
        self._collection: chromadb.Collection | None = None

    @property
    def client(self) -> chromadb.ClientAPI:
        """Lazy-initialize ChromaDB persistent client."""
        if self._client is None:
            self._client = chromadb.PersistentClient(
                path=self.persist_dir,
                settings=ChromaSettings(anonymized_telemetry=False),
            )
            logger.info(f"ChromaDB client initialized at: {self.persist_dir}")
        return self._client

    @property
    def collection(self) -> chromadb.Collection:
        """Get or create the document collection."""
        if self._collection is None:
            self._collection = self.client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            logger.info(f"Collection '{self.collection_name}' ready. Count: {self._collection.count()}")
        return self._collection

    def add_documents(
        self,
        ids: list[str],
        texts: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict[str, Any]] | None = None,
    ) -> None:
        """Add (or update) documents with their embeddings to the store."""
        self.collection.upsert(
            ids=ids,
            documents=texts,
            embeddings=embeddings,
            metadatas=metadatas or [{}] * len(ids),
        )
        logger.info(f"Upserted {len(ids)} documents. Total: {self.collection.count()}")

    def query(
        self,
        query_embedding: list[float],
        top_k: int = 6,
        where: dict[str, Any] | None = None,
        where_document: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Query the vector store and return ranked results."""
        kwargs: dict[str, Any] = {
            "query_embeddings": [query_embedding],
            "n_results": top_k,
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where
        if where_document:
            kwargs["where_document"] = where_document

        results = self.collection.query(**kwargs)

        search_results = []
        if results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                # ChromaDB returns distances; convert to similarity (cosine: sim = 1 - dist)
                distance = results["distances"][0][i] if results["distances"] else 0.0
                similarity = 1.0 - distance

                search_results.append(
                    SearchResult(
                        id=doc_id,
                        text=results["documents"][0][i],
                        metadata=results["metadatas"][0][i] if results["metadatas"] else {},
                        score=similarity,
                    )
                )

        return search_results

    def count(self) -> int:
        """Return the number of documents in the collection."""
        return self.collection.count()

    def clear(self) -> None:
        """Delete all documents from the collection."""
        self.client.delete_collection(self.collection_name)
        self._collection = None
        logger.info(f"Collection '{self.collection_name}' cleared.")

    def collection_exists(self) -> bool:
        """Check if the collection has any documents."""
        try:
            return self.collection.count() > 0
        except Exception:
            return False


_vector_store: VectorStoreService | None = None


def get_vector_store(settings: Settings | None = None) -> VectorStoreService:
    """Return a singleton vector store service."""
    global _vector_store
    if _vector_store is None:
        settings = settings or get_settings()
        _vector_store = VectorStoreService(
            persist_dir=settings.chroma_persist_dir,
            collection_name=settings.chroma_collection_name,
        )
    return _vector_store
