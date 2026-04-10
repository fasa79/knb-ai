"""Agent Supervisor — LangGraph-based intent router.

Routes user queries to the right tool based on intent classification.
New tools can be registered without changing the routing logic.

Flow:
  User query → Supervisor classifies intent → Routes to tool → Returns result
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.llm_client import get_llm_client
from app.core.cache import get_semantic_cache
from app.agents.prompts import SUPERVISOR_SYSTEM_PROMPT
from app.agents.tools.search_tool import SearchTool, SearchResponse
from app.agents.tools.extraction_tool import get_extraction_tool
from app.agents.tools.compare_tool import get_compare_tool

logger = logging.getLogger(__name__)


class AgentSupervisor:
    """Agentic query router — classifies intent and delegates to the right tool.

    Supported intents:
    - search: RAG-based Q&A over the Annual Review
    - extract: Structured data extraction (portfolio, financials)
    - compare: Cross-year comparison queries
    - off_topic: Queries unrelated to Khazanah
    """

    def __init__(self):
        self.llm_client = get_llm_client()
        self.cache = get_semantic_cache()
        self.search_tool = SearchTool()
        self.extraction_tool = get_extraction_tool()
        self.compare_tool = get_compare_tool()

    async def process_query(self, query: str, use_cache: bool = True, model: str | None = None, chat_history: list[dict[str, str]] | None = None) -> dict[str, Any]:
        """Process a user query end-to-end.

        Args:
            query: Natural language question.
            use_cache: Whether to check/store in semantic cache.
            model: Optional model override (e.g. 'gemini-2.5-flash').
            chat_history: Previous conversation messages for follow-up context.

        Returns:
            Dict with answer, sources, confidence, intent, cached status.
        """
        # Rewrite follow-up queries using chat history
        resolved_query = await self._resolve_followup(query, chat_history, model) if chat_history else query
        if resolved_query != query:
            logger.info(f"Follow-up resolved: '{query[:60]}' → '{resolved_query[:80]}'")

        # Check cache first (using the resolved query)
        if use_cache:
            cached = self.cache.get(resolved_query)
            if cached is not None:
                cached["cached"] = True
                return cached

        # Classify intent
        intent = await self._classify_intent(resolved_query, model=model)
        logger.info(f"Intent: {intent} | Query: {resolved_query[:80]}")

        # Route to the right tool (chat_history flows into generation prompts)
        if intent == "off_topic":
            result = {
                "answer": "This question doesn't appear to be related to Khazanah's Annual Review. "
                          "I can help you with questions about Khazanah's financial performance, "
                          "investment portfolio, ESG initiatives, and other topics covered in the Annual Review.",
                "sources": [],
                "confidence": "none",
                "confidence_label": "Question is outside the scope of the Annual Review",
                "intent": "off_topic",
                "cached": False,
            }
        elif intent == "extract":
            # Detect extraction type from the query
            ext_type = self._detect_extraction_type(resolved_query)
            ext_result = await self.extraction_tool.extract(
                extraction_type=ext_type,
                query=resolved_query,
                model=model,
            )
            # Build a chat-friendly response from structured data
            result = await self._format_extraction_response(ext_result, resolved_query, model, chat_history)
            result["intent"] = "extract"
            result["extraction_data"] = ext_result.get("data")
        elif intent == "compare":
            response = await self.compare_tool.compare(resolved_query, model=model, chat_history=chat_history)
            result = response.to_dict()
            result["intent"] = "compare"
        else:
            response = await self.search_tool.search(resolved_query, model=model, chat_history=chat_history)
            result = response.to_dict()
            result["intent"] = "search"

        # Store in cache
        if use_cache and result.get("confidence") != "none":
            self.cache.put(resolved_query, result)

        return result

    def _detect_extraction_type(self, query: str) -> str:
        """Detect the extraction type from the query text."""
        q = query.lower()

        # Check for portfolio-related keywords
        if any(kw in q for kw in ["portfolio", "companies", "investee", "holdings", "ownership", "stakes"]):
            return "portfolio"

        # Check for investment performance keywords
        if any(kw in q for kw in ["twrr", "asset class", "performance by", "rolling return", "yearly return"]):
            return "investment_performance"

        # Check for financial metrics keywords
        if any(kw in q for kw in ["financial metric", "total asset", "rav", "net worth", "nwa", "dividend"]):
            return "financials"

        # Check for highlights keywords
        if any(kw in q for kw in ["highlight", "initiative", "achievement", "esg", "sustainability", "milestone"]):
            return "highlights"

        # Default to custom for ambiguous extraction requests
        return "custom"

    async def _format_extraction_response(
        self, ext_result: dict, query: str, model: str | None = None, chat_history: list[dict[str, str]] | None = None
    ) -> dict:
        """Convert structured extraction data into a chat-friendly response."""
        from app.agents.prompts import build_chat_history_block

        data = ext_result.get("data")
        if not data:
            error_detail = ext_result.get("error", "")
            error_msg = (
                "I couldn't extract structured data for this request."
            )
            if error_detail:
                error_msg += f"\n\n**Reason:** {error_detail}"
            error_msg += (
                "\n\nTry rephrasing, or ask about portfolio companies, financial metrics, "
                "investment performance, or key highlights. "
                "You can also use the dedicated **/extract** page for more reliable extraction."
            )
            return {
                "answer": error_msg,
                "sources": [],
                "confidence": "none",
                "confidence_label": "Extraction produced no results",
                "cached": False,
            }

        # Summarize the extracted data using LLM
        import json
        data_str = json.dumps(data, indent=2, default=str)

        # Build source reference list for citation
        sources = ext_result.get("sources", [])
        unique_sources = []
        seen = set()
        for s in sources:
            key = (s.get("source", ""), s.get("page", 0))
            if key not in seen:
                seen.add(key)
                unique_sources.append(s)
        source_refs = "\n".join(
            f"[{i+1}] {s.get('source', 'Unknown')} p.{s.get('page', 0)}"
            for i, s in enumerate(unique_sources[:6])
        )

        chat_history_block = build_chat_history_block(chat_history)

        prompt = (
            f"The user asked: \"{query}\"\n\n"
            f"{chat_history_block}"
            f"Here is the structured data extracted from Khazanah's Annual Review:\n"
            f"```json\n{data_str}\n```\n\n"
            f"Sources:\n{source_refs}\n\n"
            f"Present this data clearly to the user in a readable format. "
            f"Use bullet points for lists and tables where appropriate. "
            f"Reference specific values from the data. Be concise. "
            f"Cite sources using numbered references like [1], [2], etc. matching the Source numbers above. "
            f"Place citations at the end of the relevant sentence or data point."
        )

        try:
            answer = await self.llm_client.generate(
                prompt=prompt,
                system_prompt="You are a helpful financial data assistant. Present extracted data clearly and accurately. Always cite sources using [1], [2] etc.",
                temperature=0.1,
                model_override=model,
            )
        except Exception as e:
            logger.error(f"Failed to format extraction: {e}")
            answer = f"Extracted data:\n```json\n{data_str}\n```"

        return {
            "answer": answer,
            "sources": [
                {
                    "source": s.get("source", ""),
                    "page": s.get("page", 0),
                    "section": "",
                    "content_type": s.get("content_type", "text"),
                    "relevance_score": 0.0,
                    "text_snippet": "",
                }
                for s in unique_sources[:6]
            ],
            "confidence": "high",
            "confidence_label": "Structured extraction from Annual Review",
            "cached": False,
        }

    async def _resolve_followup(self, query: str, chat_history: list[dict[str, str]] | None, model: str | None = None) -> str:
        """Rewrite a follow-up query into a standalone question using chat history.

        Returns the resolved query string. If the query is already self-contained,
        returns it as-is. Chat history is separately passed to generation prompts
        for continuity — this method only handles query rewriting for better retrieval.
        """
        if not chat_history:
            return query

        # Use last 6 messages max (3 exchanges) to keep prompt small
        recent = chat_history[-6:]
        history_str = "\n".join(
            f"{'User' if m.get('role') == 'user' else 'Assistant'}: {m.get('content', '')[:300]}"
            for m in recent
        )

        prompt = (
            f"Chat history:\n{history_str}\n\n"
            f"Latest user message: {query}\n\n"
            f"If the latest message is a follow-up that references the conversation (e.g. uses pronouns "
            f"like 'it', 'that', 'those', 'they', or says 'elaborate', 'more details', 'what about', "
            f"or asks for translation/reformatting like 'in malay', 'summarize'), "
            f"rewrite it as a standalone question that makes sense without the chat history.\n"
            f"If the message is already self-contained, return it exactly as-is.\n\n"
            f"Return ONLY the rewritten question, nothing else."
        )

        try:
            rewritten = await self.llm_client.generate(
                prompt=prompt,
                system_prompt="You rewrite follow-up questions into standalone questions. Return ONLY the question.",
                temperature=0.0,
                model_override=model,
            )
            rewritten = rewritten.strip().strip('"\'')
            # Sanity check: if LLM returned junk or empty, fall back to original
            if len(rewritten) < 5 or len(rewritten) > 2000:
                return query
            return rewritten
        except Exception as e:
            logger.warning(f"Follow-up resolution failed: {e}, using original query")
            return query

    async def _classify_intent(self, query: str, model: str | None = None) -> str:
        """Classify query intent using LLM with keyword shortcut."""
        # Keyword-based shortcut for obvious extraction requests
        q = query.lower().strip()
        extract_patterns = [
            "list all", "extract all", "show all", "enumerate all",
            "give me all", "list every", "extract every",
            "list the", "extract the",
        ]
        if any(q.startswith(p) or f" {p} " in f" {q} " for p in extract_patterns):
            logger.info(f"Keyword shortcut → extract for: {q[:60]}")
            return "extract"

        try:
            intent = await self.llm_client.generate(
                prompt=query,
                system_prompt=SUPERVISOR_SYSTEM_PROMPT,
                temperature=0.0,
                model_override=model,
            )
            intent = intent.strip().lower().strip('"\'')

            # Validate
            valid_intents = {"search", "extract", "compare", "off_topic"}
            if intent not in valid_intents:
                # Default to search for ambiguous classification
                logger.warning(f"Unknown intent '{intent}', defaulting to 'search'")
                return "search"

            return intent
        except Exception as e:
            logger.error(f"Intent classification failed: {e}, defaulting to 'search'")
            return "search"


_supervisor: AgentSupervisor | None = None


def get_supervisor() -> AgentSupervisor:
    """Return singleton agent supervisor."""
    global _supervisor
    if _supervisor is None:
        _supervisor = AgentSupervisor()
    return _supervisor
