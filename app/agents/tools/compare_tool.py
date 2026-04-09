"""Compare tool — cross-year comparison using year-filtered retrieval.

Routes comparison queries by:
  1. Detecting which years are being compared
  2. Retrieving relevant chunks per year (via source filename filtering)
  3. Merging context from both years
  4. LLM generates a comparative analysis
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from app.core.embeddings import get_embedding_service
from app.core.vector_store import get_vector_store
from app.core.keyword_search import get_keyword_search
from app.core.llm_client import get_llm_client
from app.agents.prompts import CONFIDENCE_LABELS

logger = logging.getLogger(__name__)

# Map review years to filename patterns.
# KAR-2025 covers FY2024, KAR-2026 covers FY2025 data.
YEAR_SOURCE_MAP: dict[str, list[str]] = {
    "2024": ["KAR-2025"],  # KAR-2025 reports FY2024 data
    "2025": ["KAR-2026"],  # KAR-2026 reports FY2025 data
}

COMPARE_SYSTEM_PROMPT = """You are an AI analyst assistant for Khazanah Nasional Berhad. Your role is to compare data across different years from Khazanah's Annual Review documents.

RULES:
1. ONLY compare based on the provided context. Do not use outside knowledge.
2. Cite sources using numbered references like [1], [2], etc.
3. Present comparisons clearly — use tables for numeric comparisons when helpful.
4. State both the absolute values AND the change (increase/decrease, percentage change) where possible.
5. If data for one year is missing from the context, explicitly state that rather than guessing.
6. Be specific about which year each figure comes from.
7. If the context doesn't support a meaningful comparison, say so."""

COMPARE_USER_PROMPT = """Based on the following context from Khazanah's Annual Review documents covering different years, answer the comparison question.

CONTEXT FROM YEAR-SEPARATED RETRIEVAL:
{context}

QUESTION: {question}

Provide a clear comparative analysis. Use tables where numeric data allows side-by-side comparison. Cite sources with [1], [2], etc."""


@dataclass
class CompareResponse:
    """Response from the compare tool."""

    answer: str
    sources: list[dict[str, Any]] = field(default_factory=list)
    confidence: str = "high"
    confidence_label: str = ""
    years_detected: list[str] = field(default_factory=list)
    cached: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "answer": self.answer,
            "sources": self.sources,
            "confidence": self.confidence,
            "confidence_label": self.confidence_label,
            "years_detected": self.years_detected,
            "cached": self.cached,
        }


class CompareTool:
    """Cross-year comparison using year-filtered retrieval."""

    REFUSE_THRESHOLD = 0.30

    def __init__(self):
        self.embedding_service = get_embedding_service()
        self.vector_store = get_vector_store()
        self.keyword_search = get_keyword_search()
        self.llm_client = get_llm_client()

        if not self.keyword_search.is_ready:
            try:
                self.keyword_search.build_from_vector_store(self.vector_store)
            except Exception as e:
                logger.warning(f"Failed to build keyword index: {e}")

    async def compare(self, query: str, model: str | None = None) -> CompareResponse:
        """Execute a cross-year comparison query.

        Args:
            query: Natural language comparison question.
            model: Optional model override.

        Returns:
            CompareResponse with comparative analysis.
        """
        # Step 1: Detect years in the query
        years = self._detect_years(query)
        logger.info(f"Compare — detected years: {years} for query: {query[:80]}")

        if len(years) < 2:
            # If fewer than 2 years detected, retrieve broadly and let LLM compare
            years = sorted(YEAR_SOURCE_MAP.keys())

        # Step 2: Retrieve chunks per year
        query_embedding = self.embedding_service.embed_query(query)
        all_chunks: list[dict[str, Any]] = []
        source_counter = 0

        for year in years:
            year_chunks = self._retrieve_for_year(query, query_embedding, year)
            for chunk in year_chunks:
                source_counter += 1
                chunk["source_num"] = source_counter
                chunk["year_label"] = year
            all_chunks.extend(year_chunks)

        if not all_chunks:
            return CompareResponse(
                answer="I couldn't find relevant information for a cross-year comparison in the Annual Review documents.",
                confidence="none",
                confidence_label=CONFIDENCE_LABELS["none"],
                years_detected=years,
            )

        # Step 3: Check confidence
        avg_score = sum(c["score"] for c in all_chunks) / len(all_chunks)
        if avg_score < self.REFUSE_THRESHOLD:
            return CompareResponse(
                answer="I couldn't find enough relevant information to make a meaningful comparison across years.",
                confidence="none",
                confidence_label=CONFIDENCE_LABELS["none"],
                years_detected=years,
                sources=self._build_sources(all_chunks),
            )

        # Step 4: Build year-labeled context
        context = self._build_compare_context(all_chunks)

        # Step 5: LLM generates comparative analysis
        prompt = COMPARE_USER_PROMPT.format(context=context, question=query)
        answer = await self.llm_client.generate(
            prompt=prompt,
            system_prompt=COMPARE_SYSTEM_PROMPT,
            temperature=0.1,
            model_override=model,
        )

        confidence = "high" if avg_score >= 0.50 else ("medium" if avg_score >= 0.40 else "low")

        return CompareResponse(
            answer=answer,
            sources=self._build_sources(all_chunks),
            confidence=confidence,
            confidence_label=CONFIDENCE_LABELS[confidence],
            years_detected=years,
        )

    def _detect_years(self, query: str) -> list[str]:
        """Extract years mentioned in the query."""
        # Match 4-digit years in 2019-2030 range
        matches = re.findall(r"\b(20[12]\d)\b", query)
        years = sorted(set(matches))
        # Filter to years we have data for
        known_years = set(YEAR_SOURCE_MAP.keys())
        return [y for y in years if y in known_years] or years

    def _retrieve_for_year(
        self, query: str, query_embedding: list[float], year: str, top_k: int = 4
    ) -> list[dict[str, Any]]:
        """Retrieve relevant chunks for a specific year using source filtering."""
        source_patterns = YEAR_SOURCE_MAP.get(year, [])

        # Try vector search with source filter
        chunks = []
        if source_patterns:
            for pattern in source_patterns:
                results = self.vector_store.query(
                    query_embedding,
                    top_k=top_k,
                    where={"source": {"$contains": pattern}} if hasattr(self.vector_store, '_chroma_where') else None,
                )
                # ChromaDB doesn't support $contains on non-array fields easily,
                # so we filter post-query
                results_unfiltered = self.vector_store.query(query_embedding, top_k=top_k * 3)
                for r in results_unfiltered:
                    if any(p in r.metadata.get("source", "") for p in source_patterns):
                        chunks.append({
                            "id": r.id,
                            "text": r.text,
                            "source": r.metadata.get("source", ""),
                            "page": r.metadata.get("page", 0),
                            "section": r.metadata.get("section", ""),
                            "content_type": r.metadata.get("content_type", "text"),
                            "score": r.score,
                        })
        else:
            # No source mapping — retrieve all and filter by year mention in text
            results = self.vector_store.query(query_embedding, top_k=top_k * 3)
            for r in results:
                if year in r.text or year in r.metadata.get("source", ""):
                    chunks.append({
                        "id": r.id,
                        "text": r.text,
                        "source": r.metadata.get("source", ""),
                        "page": r.metadata.get("page", 0),
                        "section": r.metadata.get("section", ""),
                        "content_type": r.metadata.get("content_type", "text"),
                        "score": r.score,
                    })

        # Deduplicate by ID and take top_k
        seen = set()
        unique = []
        for c in sorted(chunks, key=lambda x: x["score"], reverse=True):
            if c["id"] not in seen:
                seen.add(c["id"])
                unique.append(c)
            if len(unique) >= top_k:
                break

        return unique

    def _build_compare_context(self, chunks: list[dict[str, Any]]) -> str:
        """Build a year-labeled context string for the comparison prompt."""
        parts = []
        for chunk in chunks:
            year_label = chunk.get("year_label", "?")
            source = chunk.get("source", "Unknown")
            page = chunk.get("page", "?")
            content_type = chunk.get("content_type", "text")
            text = chunk.get("text", "")
            num = chunk.get("source_num", "?")

            header = f"[Source {num} — Year {year_label}: {source}, Page {page}, Type: {content_type}]"
            parts.append(f"{header}\n{text}")

        return "\n\n---\n\n".join(parts)

    def _build_sources(self, chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert chunks to source reference dicts."""
        return [
            {
                "source": c.get("source", ""),
                "page": c.get("page", 0),
                "section": c.get("section", ""),
                "content_type": c.get("content_type", "text"),
                "relevance_score": round(c.get("score", 0), 3),
                "text_snippet": c.get("text", "")[:200],
            }
            for c in chunks
        ]


# ── Singleton ─────────────────────────────────────────────────────

_compare_tool: CompareTool | None = None


def get_compare_tool() -> CompareTool:
    """Return singleton compare tool."""
    global _compare_tool
    if _compare_tool is None:
        _compare_tool = CompareTool()
    return _compare_tool
