"""Embedding service — supports both local (sentence-transformers) and Google API embeddings.

Swappable: set EMBEDDING_PROVIDER in .env to 'local' or 'google'.
  - local:  uses sentence-transformers (default: all-MiniLM-L6-v2, 384-dim)
  - google: uses Google text-embedding-004 (768-dim, free tier: 1500 RPM)

The service is lazy-loaded and cached as a singleton.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

import numpy as np

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


class BaseEmbeddingService(ABC):
    """Abstract base for embedding providers."""

    def __init__(self, model_name: str):
        self.model_name = model_name

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Return the embedding dimension."""

    @abstractmethod
    def embed_texts(self, texts: list[str], batch_size: int = 64, show_progress: bool = False) -> list[list[float]]:
        """Generate embeddings for a list of texts."""

    def embed_query(self, query: str) -> list[float]:
        """Generate embedding for a single query string."""
        return self.embed_texts([query])[0]

    def similarity(self, embedding1: list[float], embedding2: list[float]) -> float:
        """Compute cosine similarity between two embeddings."""
        a = np.array(embedding1)
        b = np.array(embedding2)
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


class LocalEmbeddingService(BaseEmbeddingService):
    """Local embedding generation using sentence-transformers."""

    def __init__(self, model_name: str):
        super().__init__(model_name)
        self._model = None

    @property
    def model(self):
        """Lazy-load the model on first access."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            logger.info(f"Loading local embedding model: {self.model_name}")
            self._model = SentenceTransformer(self.model_name)
            logger.info(f"Embedding model loaded. Dimension: {self._model.get_sentence_embedding_dimension()}")
        return self._model

    @property
    def dimension(self) -> int:
        return self.model.get_sentence_embedding_dimension()

    def embed_texts(self, texts: list[str], batch_size: int = 64, show_progress: bool = False) -> list[list[float]]:
        if not texts:
            return []
        embeddings = self.model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=show_progress,
            normalize_embeddings=True,
        )
        return embeddings.tolist()


class GoogleEmbeddingService(BaseEmbeddingService):
    """Google gemini-embedding-001 via the Generative AI API."""

    # Free tier: 100 requests per minute → space calls ~0.7s apart
    _MIN_REQUEST_INTERVAL = 0.7

    def __init__(self, model_name: str, api_key: str, output_dimensionality: int = 3072):
        super().__init__(model_name)
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        self._genai = genai
        self._output_dimensionality = output_dimensionality
        self._last_request_time = 0.0
        logger.info(f"Google embedding service initialized: {self.model_name} ({self._output_dimensionality}-dim)")

    @property
    def dimension(self) -> int:
        return self._output_dimensionality

    def _rate_limit(self) -> None:
        """Ensure minimum interval between API requests."""
        import time as _time
        now = _time.time()
        elapsed = now - self._last_request_time
        if elapsed < self._MIN_REQUEST_INTERVAL:
            _time.sleep(self._MIN_REQUEST_INTERVAL - elapsed)
        self._last_request_time = _time.time()

    def _call_embed(self, content, task_type: str) -> dict:
        """Call embed_content with rate limiting and retry on 429."""
        import time as _time
        for attempt in range(3):
            try:
                self._rate_limit()
                return self._genai.embed_content(
                    model=f"models/{self.model_name}",
                    content=content,
                    task_type=task_type,
                    output_dimensionality=self._output_dimensionality,
                )
            except Exception as e:
                if "429" in str(e) and attempt < 2:
                    wait = 40 * (attempt + 1)
                    logger.warning(f"Rate limited, waiting {wait}s (attempt {attempt + 1}/3)")
                    _time.sleep(wait)
                    self._last_request_time = _time.time()
                else:
                    raise

    def embed_texts(self, texts: list[str], batch_size: int = 64, show_progress: bool = False) -> list[list[float]]:
        if not texts:
            return []

        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            result = self._call_embed(batch, "RETRIEVAL_DOCUMENT")
            all_embeddings.extend(result["embedding"])

            if show_progress:
                logger.info(f"Embedded batch {i // batch_size + 1}/{(len(texts) - 1) // batch_size + 1}")

        return all_embeddings

    def embed_query(self, query: str) -> list[float]:
        """Use RETRIEVAL_QUERY task type for queries (asymmetric search)."""
        result = self._call_embed(query, "RETRIEVAL_QUERY")
        return result["embedding"]


# Type alias for backward compatibility
EmbeddingService = BaseEmbeddingService

_embedding_service: BaseEmbeddingService | None = None


def get_embedding_service(settings: Settings | None = None) -> BaseEmbeddingService:
    """Return a singleton embedding service based on EMBEDDING_PROVIDER config."""
    global _embedding_service
    if _embedding_service is None:
        settings = settings or get_settings()
        if settings.embedding_provider == "google":
            _embedding_service = GoogleEmbeddingService(
                model_name=settings.embedding_model,
                api_key=settings.gemini_api_key,
            )
        else:
            _embedding_service = LocalEmbeddingService(model_name=settings.embedding_model)
    return _embedding_service
