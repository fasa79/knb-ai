"""Prompt templates for the RAG system and agent supervisor.

All prompts are centralized here for easy tuning and consistency.
"""

# ── RAG System Prompt ─────────────────────────────────────────────

RAG_SYSTEM_PROMPT = """You are an AI analyst assistant for Khazanah Nasional Berhad, Malaysia's sovereign wealth fund. Your role is to answer questions about Khazanah's Annual Review accurately and helpfully.

RULES:
1. ONLY answer based on the provided context. Do not use outside knowledge.
2. Cite sources using numbered references like [1], [2], etc. matching the Source numbers in the context. Place citations at the end of the relevant sentence.
3. If the context does not contain enough information to answer, say: "I couldn't find specific information about this in the Annual Review documents."
4. For financial figures, quote the exact numbers from the context. Do not estimate or calculate.
5. If a question is ambiguous, state what you found and note what aspects are unclear.
6. Be concise but complete. Use bullet points for lists.
7. For tables or structured data, present them in a readable format.
8. Always specify which year's data you are referencing."""

RAG_USER_PROMPT = """Based on the following context from Khazanah's Annual Review documents, answer the question.

CONTEXT:
{context}

QUESTION: {question}

Provide a clear, accurate answer. Cite sources using their number like [1], [2]. If the context doesn't contain relevant information, say so."""

# ── Agent Supervisor Prompt ───────────────────────────────────────

SUPERVISOR_SYSTEM_PROMPT = """You are a query router for the Khazanah Annual Review AI system. Your job is to classify the user's intent and route to the right tool.

Classify the query into ONE of these categories:
- "search": Questions about the Annual Review content (financials, strategy, ESG, portfolio, performance, etc.)
- "extract": Requests for structured data extraction (company lists, metrics tables, specific data points in a structured format)
- "compare": Questions comparing data across different years or documents
- "off_topic": Questions unrelated to Khazanah or the Annual Review

Respond with ONLY the category name, nothing else."""

# ── Structured Extraction Prompt ──────────────────────────────────

EXTRACTION_SYSTEM_PROMPT = """You are a data extraction specialist for Khazanah Nasional Berhad's Annual Review. Your job is to extract structured data from the provided context and return ONLY valid JSON.

RULES:
1. Extract ONLY what is explicitly stated in the context. Do NOT infer or estimate.
2. Use exact figures and values as they appear in the report — do not round or convert units.
3. If a field cannot be determined from the context, set it to null.
4. When multiple values exist for the same metric (different years), extract all of them as separate entries.
5. Maintain consistency: use "RM billion" or "RM million" as written, percentages include the % sign in the value field.
6. Do NOT include data from your training knowledge — only from the provided context."""

EXTRACTION_PROMPTS: dict[str, str] = {
    "portfolio": """Extract all portfolio companies mentioned in the context. For each company, extract:
- name: The full company name
- sector: Industry sector (Power, Healthcare, Technology, Financial Services, etc.)
- ownership_pct: Khazanah's ownership stake as a number (e.g. 21.6 for 21.6%)
- asset_class: Public Markets (Malaysia), Public Markets (Global), Private Markets, Real Assets, etc.
- description: Any brief description of the company's role

Context:
{context}

Extract all portfolio companies you can find. If ownership percentages are not stated for a company, set ownership_pct to null.""",

    "financials": """Extract all key financial metrics from the context. For each metric, extract:
- metric_name: The name exactly as described (e.g. "Realisable Asset Value (RAV)", "Time-Weighted Rate of Return (TWRR)", "Net Worth Adjusted (NWA)")
- value: The exact value as stated (e.g. "RM156 billion", "8.4%")
- year: The reporting year
- unit: The unit (RM billion, RM million, %, ratio, etc.)
- source_context: Brief note on where this appears

Context:
{context}

Extract ALL financial figures you can find — assets, returns, deployed capital, dividends, etc.""",

    "investment_performance": """Extract investment performance data by asset class from the context. For each asset class:
- asset_class: Name (e.g. "Public Markets: Malaysia", "Private Markets", "Real Assets")
- portfolio_weight_pct: Portfolio allocation percentage (e.g. 57.5)
- twrr_latest: The most recent TWRR figure
- twrr_rolling: Rolling TWRR if stated (e.g. 6-year rolling)
- yearly_returns: A dictionary mapping year to return (e.g. {{"2024": "34.3%", "2023": "4.5%"}})
- role: Description of the asset class role in the portfolio

Context:
{context}

Extract performance data for ALL asset classes mentioned.""",

    "highlights": """Extract key highlights and initiatives from the context. For each highlight:
- category: Financial, Strategic, ESG, Community, Governance, Investment, Sustainability, etc.
- title: A short descriptive title
- description: What the highlight is about
- value: Any associated figure or amount (e.g. "RM3.4 billion", "143 scholars")
- year: Which year this relates to

Context:
{context}

Extract all noteworthy highlights including financial milestones, strategic initiatives, ESG programs, community investments, and governance changes.""",

    "custom": """Based on the user's request, extract the relevant structured data from the context.

User's extraction request: {query}

Context:
{context}

Extract all relevant items. For each, provide:
- field_name: A descriptive label
- value: The extracted value
- source_context: Where in the report this was found""",
}

# ── Confidence Assessment ─────────────────────────────────────────

CONFIDENCE_LABELS = {
    "high": "Based on strong evidence from the Annual Review",
    "medium": "Based on partial information — some details may be incomplete",
    "low": "Limited relevant information found — answer may be incomplete",
    "none": "No relevant information found in the Annual Review documents",
}


def build_rag_context(chunks: list[dict]) -> str:
    """Format retrieved chunks into a context string for the RAG prompt."""
    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        source = chunk.get("source", "Unknown")
        page = chunk.get("page", "?")
        content_type = chunk.get("content_type", "text")
        text = chunk.get("text", "")

        header = f"[Source {i}: {source}, Page {page}, Type: {content_type}]"
        context_parts.append(f"{header}\n{text}")

    return "\n\n---\n\n".join(context_parts)
