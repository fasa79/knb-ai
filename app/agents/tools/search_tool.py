"""Search tool — hybrid retrieval (vector + BM25) with RAG generation.

This is the core RAG tool that the agent supervisor routes search queries to.

Flow:
  1. Vector search (semantic) → top-10
  2. BM25 keyword search → top-10
  3. Reciprocal Rank Fusion → merge → top-6 unique
  4. Confidence check (avg similarity score)
  5. Build context from chunks
  6. LLM generates answer with citations
  7. Return answer + sources + confidence
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.config import get_settings
from app.core.embeddings import get_embedding_service
from app.core.vector_store import get_vector_store, SearchResult
from app.core.keyword_search import get_keyword_search, BM25Result
from app.core.llm_client import get_llm_client
from app.agents.prompts import (
    RAG_SYSTEM_PROMPT,
    RAG_USER_PROMPT,
    CONFIDENCE_LABELS,
    build_rag_context,
    build_chat_history_block,
)

logger = logging.getLogger(__name__)


@dataclass
class SourceReference:
    """A source citation for an answer."""

    source: str
    page: int
    section: str
    content_type: str
    relevance_score: float
    text_snippet: str


@dataclass
class SearchResponse:
    """Response from the search tool."""

    answer: str
    sources: list[SourceReference] = field(default_factory=list)
    confidence: str = "high"
    confidence_label: str = ""
    avg_score: float = 0.0
    cached: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "answer": self.answer,
            "sources": [
                {
                    "source": s.source,
                    "page": s.page,
                    "section": s.section,
                    "content_type": s.content_type,
                    "relevance_score": round(s.relevance_score, 3),
                    "text_snippet": s.text_snippet[:200],
                }
                for s in self.sources
            ],
            "confidence": self.confidence,
            "confidence_label": self.confidence_label,
            "avg_score": round(self.avg_score, 3),
            "cached": self.cached,
        }


class SearchTool:
    """Hybrid search + RAG generation tool."""

    # Confidence thresholds
    REFUSE_THRESHOLD = 0.30
    LOW_THRESHOLD = 0.40
    MEDIUM_THRESHOLD = 0.50

    def __init__(self):
        settings = get_settings()
        self.top_k = settings.rag_top_k
        self.similarity_threshold = settings.rag_similarity_threshold
        self.context_token_budget = settings.context_token_budget
        self.embedding_service = get_embedding_service()
        self.vector_store = get_vector_store()
        self.keyword_search = get_keyword_search()
        self.llm_client = get_llm_client()

        # Build BM25 index if not ready
        if not self.keyword_search.is_ready:
            self._build_keyword_index()

    def _build_keyword_index(self) -> None:
        """Build BM25 index from vector store contents."""
        try:
            self.keyword_search.build_from_vector_store(self.vector_store)
        except Exception as e:
            logger.warning(f"Failed to build keyword index: {e}")

    async def search(self, query: str, model: str | None = None, chat_history: list[dict[str, str]] | None = None) -> SearchResponse:
        """Execute hybrid search + RAG generation.

        Args:
            query: Natural language question.
            model: Optional model override.
            chat_history: Previous conversation messages for follow-up context.

        Returns:
            SearchResponse with answer, sources, and confidence.
        """
        # Stage 1 & 2: Dual retrieval
        vector_results = self._vector_search(query)
        keyword_results = self._keyword_search(query)

        # Stage 3: Reciprocal Rank Fusion
        fused = self._reciprocal_rank_fusion(vector_results, keyword_results, query=query)

        # Take top-k
        top_results = fused[: self.top_k]

        if not top_results:
            return SearchResponse(
                answer="I couldn't find any relevant information in the Annual Review documents for your question.",
                confidence="none",
                confidence_label=CONFIDENCE_LABELS["none"],
            )

        # Stage 4: Confidence check
        avg_score = sum(r["score"] for r in top_results) / len(top_results)
        confidence = self._assess_confidence(avg_score)

        if confidence == "none":
            return SearchResponse(
                answer="I couldn't find specific information about this in the Annual Review documents. "
                       "The available documents may not cover this topic, or the question may need to be rephrased.",
                confidence="none",
                confidence_label=CONFIDENCE_LABELS["none"],
                avg_score=avg_score,
                sources=self._build_sources(top_results),
            )

        # Stage 5: Build context (with token budget)
        context = build_rag_context(top_results, token_budget=self.context_token_budget)

        # Stage 6: LLM generation
        chat_history_block = build_chat_history_block(chat_history)
        prompt = RAG_USER_PROMPT.format(context=context, question=query, chat_history_block=chat_history_block)
        answer = await self.llm_client.generate(
            prompt=prompt,
            system_prompt=RAG_SYSTEM_PROMPT,
            temperature=0.1,
            model_override=model,
        )

        # Add confidence warning for low-confidence answers
        if confidence == "low":
            answer += "\n\n⚠️ *Note: Limited relevant information was found. This answer may be incomplete.*"

        return SearchResponse(
            answer=answer,
            sources=self._build_sources(top_results),
            confidence=confidence,
            confidence_label=CONFIDENCE_LABELS[confidence],
            avg_score=avg_score,
        )

    def _vector_search(self, query: str, top_k: int = 10) -> list[SearchResult]:
        """Stage 1: Semantic vector search."""
        query_embedding = self.embedding_service.embed_query(query)
        return self.vector_store.query(query_embedding, top_k=top_k)

    def _keyword_search(self, query: str, top_k: int = 10) -> list[BM25Result]:
        """Stage 2: BM25 keyword search."""
        if not self.keyword_search.is_ready:
            return []
        return self.keyword_search.search(query, top_k=top_k)

    def _reciprocal_rank_fusion(
        self,
        vector_results: list[SearchResult],
        keyword_results: list[BM25Result],
        query: str = "",
        alpha: float = 0.5,
        k: int = 60,
    ) -> list[dict[str, Any]]:
        """Stage 3: Merge vector + keyword results using RRF with keyword boost.

        RRF score = alpha * 1/(k + vector_rank) + (1-alpha) * 1/(k + keyword_rank)

        Keyword boost: if a BM25 top-3 result contains exact query terms that
        are rare/specific (not common words), boost its RRF score. This ensures
        that exact acronym/term matches (e.g. "TWRR", "RAV") surface even when
        vector search misses them entirely.
        """
        # Detect specific terms in query (uppercase acronyms, numbers with %)
        import re
        query_tokens = set(query.split())
        specific_terms = {t for t in query_tokens if t.isupper() and len(t) >= 2}
        specific_terms |= {t for t in query_tokens if re.match(r"\d+\.?\d*%?$", t)}

        # Build lookup by chunk ID
        candidates: dict[str, dict[str, Any]] = {}

        # Add vector results
        for rank, result in enumerate(vector_results):
            candidates[result.id] = {
                "id": result.id,
                "text": result.text,
                "source": result.metadata.get("source", ""),
                "page": result.metadata.get("page", 0),
                "section": result.metadata.get("section", ""),
                "content_type": result.metadata.get("content_type", "text"),
                "vector_rank": rank,
                "keyword_rank": None,
                "vector_score": result.score,
            }

        # Add keyword results
        for rank, result in enumerate(keyword_results):
            if result.id in candidates:
                candidates[result.id]["keyword_rank"] = rank
            else:
                candidates[result.id] = {
                    "id": result.id,
                    "text": result.text,
                    "source": result.metadata.get("source", ""),
                    "page": result.metadata.get("page", 0),
                    "section": result.metadata.get("section", ""),
                    "content_type": result.metadata.get("content_type", "text"),
                    "vector_rank": None,
                    "keyword_rank": rank,
                    "vector_score": 0.0,
                }

        # Compute RRF scores
        for doc in candidates.values():
            v_score = alpha * (1.0 / (k + doc["vector_rank"])) if doc["vector_rank"] is not None else 0.0
            k_score = (1.0 - alpha) * (1.0 / (k + doc["keyword_rank"])) if doc["keyword_rank"] is not None else 0.0
            doc["rrf_score"] = v_score + k_score

            # Keyword boost: if chunk contains specific query terms and ranked
            # top-3 in BM25, boost its RRF score significantly
            if specific_terms and doc["keyword_rank"] is not None and doc["keyword_rank"] < 3:
                chunk_text = doc["text"].upper()
                matched = sum(1 for t in specific_terms if t.upper() in chunk_text)
                if matched:
                    boost = 0.005 * matched * (3 - doc["keyword_rank"])
                    doc["rrf_score"] += boost
                    logger.debug(f"Keyword boost +{boost:.4f} for chunk {doc['id'][:20]} (matched {matched} terms)")

            # Confidence score: use vector score if available, otherwise
            # derive from keyword rank (top BM25 hits are reliable)
            if doc.get("vector_score", 0) > 0:
                doc["score"] = doc["vector_score"]
            elif doc["keyword_rank"] is not None and doc["keyword_rank"] < 5:
                # High BM25 rank = reliable match even without vector score
                doc["score"] = max(0.50, 0.60 - doc["keyword_rank"] * 0.03)
            else:
                doc["score"] = doc["rrf_score"] * 50

        # Sort by RRF score
        ranked = sorted(candidates.values(), key=lambda x: x["rrf_score"], reverse=True)
        return ranked

    def _assess_confidence(self, avg_score: float) -> str:
        """Assess confidence based on average retrieval score."""
        if avg_score < self.REFUSE_THRESHOLD:
            return "none"
        elif avg_score < self.LOW_THRESHOLD:
            return "low"
        elif avg_score < self.MEDIUM_THRESHOLD:
            return "medium"
        return "high"

    def _build_sources(self, results: list[dict[str, Any]]) -> list[SourceReference]:
        """Build source references from search results."""
        sources = []
        for r in results:
            raw_text = r.get("text", "")
            # Strip the context enrichment prefix for display
            if raw_text.startswith("["):
                newline_idx = raw_text.find("\n")
                if newline_idx > 0:
                    raw_text = raw_text[newline_idx + 1:]

            sources.append(SourceReference(
                source=r.get("source", "Unknown"),
                page=r.get("page", 0),
                section=r.get("section", ""),
                content_type=r.get("content_type", "text"),
                relevance_score=r.get("vector_score", r.get("score", 0.0)),
                text_snippet=raw_text[:300],
            ))
        return sources
