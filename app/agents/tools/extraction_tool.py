"""Extraction tool — LLM-powered structured data extraction from retrieved chunks.

Uses the same hybrid retrieval as the search tool, but routes the context
through structured output (Pydantic schema) instead of free-form generation.

Supports:
  - Pre-defined types: portfolio, financials, investment_performance, highlights
  - Custom free-form extraction from user queries
  - "all" mode: runs all pre-defined types in sequence
"""

from __future__ import annotations

import logging
from typing import Any

from app.config import get_settings
from app.core.embeddings import get_embedding_service
from app.core.vector_store import get_vector_store
from app.core.keyword_search import get_keyword_search
from app.core.llm_client import get_llm_client
from app.agents.prompts import (
    EXTRACTION_SYSTEM_PROMPT,
    EXTRACTION_PROMPTS,
    build_rag_context,
)
from app.extraction.schemas import (
    EXTRACTION_SCHEMAS,
    PortfolioExtraction,
    FinancialExtraction,
    InvestmentExtraction,
    HighlightsExtraction,
    CustomExtraction,
    FullExtraction,
)

logger = logging.getLogger(__name__)

# Targeted search queries per extraction type — ensures we retrieve the right chunks
EXTRACTION_QUERIES: dict[str, list[str]] = {
    "portfolio": [
        "portfolio companies investment holdings ownership stake",
        "Khazanah investee companies sectors",
        "public markets private markets real assets portfolio allocation",
    ],
    "financials": [
        "total assets realisable asset value RAV financial performance",
        "TWRR time weighted rate of return net worth adjusted",
        "dividend profit loss income revenue financial highlights",
        "deployed capital investment returns financial year",
    ],
    "investment_performance": [
        "TWRR by asset class portfolio weight performance returns",
        "public markets private markets real assets rolling TWRR yearly returns",
        "investment performance asset class allocation 6-year rolling",
    ],
    "highlights": [
        "key highlights achievements milestones initiatives",
        "ESG sustainability community development scholars",
        "strategic investments new initiatives governance",
        "Yayasan Hasanah Dana Impak deployed capital social impact",
    ],
}


class ExtractionTool:
    """LLM-powered structured data extractor using hybrid retrieval."""

    def __init__(self):
        self.settings = get_settings()
        self.embedding_service = get_embedding_service()
        self.vector_store = get_vector_store()
        self.keyword_search = get_keyword_search()
        self.llm_client = get_llm_client()

    async def extract(
        self,
        extraction_type: str,
        query: str | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        """Run structured extraction for a given type.

        Args:
            extraction_type: One of 'portfolio', 'financials', 'investment_performance',
                           'highlights', 'custom', or 'all'.
            query: Required for 'custom' type. Optional for others (used as extra search context).
            model: Optional LLM model override.

        Returns:
            Dict with extraction_type, data (structured), and metadata.
        """
        if extraction_type == "all":
            return await self._extract_all(model=model)

        if extraction_type == "custom" and not query:
            return {
                "extraction_type": "custom",
                "data": None,
                "error": "A query is required for custom extraction.",
            }

        return await self._extract_single(extraction_type, query=query, model=model)

    async def _extract_all(self, model: str | None = None) -> dict[str, Any]:
        """Run all pre-defined extraction types and combine results."""
        results = {}
        errors = []

        for ext_type in ["portfolio", "financials", "investment_performance", "highlights"]:
            try:
                result = await self._extract_single(ext_type, model=model)
                if result.get("data"):
                    results[ext_type] = result["data"]
            except Exception as e:
                logger.error(f"Extraction failed for {ext_type}: {e}")
                errors.append(f"{ext_type}: {str(e)}")

        full = FullExtraction(
            portfolio=results.get("portfolio"),
            financials=results.get("financials"),
            investment_performance=results.get("investment_performance"),
            highlights=results.get("highlights"),
        )

        return {
            "extraction_type": "all",
            "data": full.model_dump(exclude_none=True),
            "errors": errors if errors else None,
        }

    async def _extract_single(
        self,
        extraction_type: str,
        query: str | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        """Extract a single type of structured data."""
        # Step 1: Retrieve relevant chunks using targeted queries
        chunks = await self._retrieve_chunks(extraction_type, extra_query=query)

        if not chunks:
            return {
                "extraction_type": extraction_type,
                "data": None,
                "error": "No relevant chunks found for extraction.",
            }

        # Step 2: Build context from chunks
        context = build_rag_context(chunks)

        # Step 3: Build extraction prompt
        prompt_template = EXTRACTION_PROMPTS.get(extraction_type, EXTRACTION_PROMPTS["custom"])
        if extraction_type == "custom":
            prompt = prompt_template.format(context=context, query=query or "")
        else:
            prompt = prompt_template.format(context=context)

        # Step 4: LLM structured extraction
        schema = EXTRACTION_SCHEMAS[extraction_type]

        try:
            result = await self.llm_client.generate_structured(
                prompt=prompt,
                schema=schema,
                system_prompt=EXTRACTION_SYSTEM_PROMPT,
                temperature=0.0,
            )

            # with_structured_output can return None if parsing fails
            if result is None:
                logger.warning(f"Structured extraction returned None for {extraction_type}, trying fallback")
                return await self._fallback_extraction(extraction_type, prompt, schema, chunks, model)

            # result is a Pydantic model instance
            data = result.model_dump() if hasattr(result, "model_dump") else result

            return {
                "extraction_type": extraction_type,
                "data": data,
                "chunks_used": len(chunks),
                "sources": [
                    {
                        "source": c.get("source", "Unknown"),
                        "page": c.get("page", 0),
                        "content_type": c.get("content_type", "text"),
                    }
                    for c in chunks
                ],
            }

        except Exception as e:
            logger.error(f"Structured extraction failed for {extraction_type}: {e}")
            # Fallback: try plain generation and parse manually
            return await self._fallback_extraction(extraction_type, prompt, schema, chunks, model)

    async def _fallback_extraction(
        self,
        extraction_type: str,
        prompt: str,
        schema: type,
        chunks: list[dict],
        model: str | None = None,
    ) -> dict[str, Any]:
        """Fallback: use plain LLM generation with JSON parsing when structured output fails."""
        try:
            fallback_prompt = (
                f"{prompt}\n\n"
                f"Return your answer as a valid JSON object matching this schema:\n"
                f"{schema.model_json_schema()}\n"
                f"Return ONLY the JSON, no explanation."
            )

            logger.info(f"Running fallback extraction for {extraction_type}")
            raw = await self.llm_client.generate(
                prompt=fallback_prompt,
                system_prompt=EXTRACTION_SYSTEM_PROMPT,
                temperature=0.0,
                model_override=model,
            )
            logger.info(f"Fallback raw response length: {len(raw)} chars")

            # Try to parse the JSON
            import json
            # Strip markdown code fences if present
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()
            if cleaned.startswith("json"):
                cleaned = cleaned[4:].strip()

            parsed = json.loads(cleaned)
            data = schema.model_validate(parsed)

            return {
                "extraction_type": extraction_type,
                "data": data.model_dump(),
                "chunks_used": len(chunks),
                "fallback": True,
                "sources": [
                    {
                        "source": c.get("source", "Unknown"),
                        "page": c.get("page", 0),
                        "content_type": c.get("content_type", "text"),
                    }
                    for c in chunks
                ],
            }
        except Exception as e2:
            logger.error(f"Fallback extraction also failed: {e2}")
            return {
                "extraction_type": extraction_type,
                "data": None,
                "error": f"Extraction failed: {str(e2)}",
            }

    async def _retrieve_chunks(
        self,
        extraction_type: str,
        extra_query: str | None = None,
        top_k: int = 10,
    ) -> list[dict]:
        """Retrieve chunks using targeted queries for the extraction type.

        Uses multiple queries per type to get broad coverage, then deduplicates.
        """
        queries = EXTRACTION_QUERIES.get(extraction_type, [])
        if extra_query:
            queries = [extra_query] + queries

        if not queries:
            queries = [extra_query or "Khazanah Annual Review key information"]

        seen_ids: set[str] = set()
        all_chunks: list[dict] = []

        for q in queries:
            # Vector search
            query_embedding = self.embedding_service.embed_query(q)
            results = self.vector_store.query(
                query_embedding=query_embedding,
                top_k=top_k,
            )

            for r in results:
                if r.id not in seen_ids:
                    seen_ids.add(r.id)
                    all_chunks.append({
                        "id": r.id,
                        "text": r.text,
                        "source": r.metadata.get("source", "Unknown"),
                        "page": r.metadata.get("page", 0),
                        "section": r.metadata.get("section", ""),
                        "content_type": r.metadata.get("content_type", "text"),
                        "score": r.score,
                    })

        # Sort by relevance score descending, take top chunks
        all_chunks.sort(key=lambda c: c["score"], reverse=True)
        # Use more chunks for extraction than for Q&A (need broader coverage)
        max_chunks = min(len(all_chunks), 15)

        logger.info(
            f"Extraction retrieval for '{extraction_type}': "
            f"{len(all_chunks)} unique chunks from {len(queries)} queries, using top {max_chunks}"
        )

        return all_chunks[:max_chunks]


_extraction_tool: ExtractionTool | None = None


def get_extraction_tool() -> ExtractionTool:
    """Return singleton extraction tool."""
    global _extraction_tool
    if _extraction_tool is None:
        _extraction_tool = ExtractionTool()
    return _extraction_tool
