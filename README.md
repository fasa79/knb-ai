# Khazanah Annual Review AI

An AI-powered tool that lets you **ask questions about Khazanah's Annual Review in plain English** and get accurate answers with source citations. Think of it as a smart assistant that has read the entire annual report and can instantly find the information you need.

---

## What This Tool Does

Instead of manually searching through a 20+ page annual report PDF, you can:

- **Ask questions** like *"What was Khazanah's total assets in 2025?"* and get an answer with the exact page reference
- **View structured data** — portfolio companies, financial metrics, and key highlights extracted automatically
- **Upload new reports** — drop in a new PDF and the system processes it automatically

---

## How It Works (Architecture)

```
┌──────────────┐     ┌──────────────┐     ┌───────────────────┐
│  You (User)  │────▶│   Frontend   │────▶│   FastAPI Backend  │
│              │◀────│  (Next.js)   │◀────│                    │
└──────────────┘     └──────────────┘     └────────┬──────────┘
                                                   │
                                          ┌────────▼──────────┐
                                          │  Agent Supervisor  │
                                          │  (decides what to  │
                                          │   do with your     │
                                          │   question)        │
                                          └──┬─────┬──────┬───┘
                                             │     │      │
                                    Search  Extract  Compare
                                    Tool    Tool     Tool
                                             │
                                    ┌────────▼──────────┐
                                    │  Vector Database   │
                                    │  (ChromaDB —       │
                                    │   searchable       │
                                    │   knowledge base)  │
                                    └───────────────────┘
```

**In simple terms:**

1. You upload a PDF annual report
2. The system reads and understands every page — text, tables, charts
3. It breaks the document into smart, meaningful pieces and stores them in a searchable knowledge base
4. When you ask a question, the AI finds the most relevant pieces and uses them to generate an accurate answer
5. Every answer comes with page numbers so you can verify it yourself

---

## Section 1: Data Ingestion & Pipeline

### How We Process PDFs

The system uses a **3-layer hybrid chunking strategy** — meaning it adapts to different types of content instead of using a one-size-fits-all approach:

#### Layer 1 — Content-Type Detection
Each section of the PDF is automatically classified as:
| Type | How It's Handled | Why |
|------|-----------------|-----|
| **Tables** | Kept whole, never split | Splitting a financial table destroys its meaning |
| **Bullet lists** | Grouped as a single unit | A list of initiatives only makes sense as a whole |
| **Financial figures** | Kept with surrounding context | "RM21.1b" alone is meaningless — it needs "total assets" next to it |
| **Narrative text** | Smart splitting (see Layer 2) | Long paragraphs need to be split at natural topic boundaries |

#### Layer 2 — Embedding-Based Semantic Splitting
For narrative text, instead of splitting at fixed character counts (which can break mid-sentence), we:
1. Break text into sentences
2. Use AI to measure how **similar** consecutive sentences are to each other
3. Where the topic changes (similarity drops), that's where we split

This is **data-driven** — it works regardless of how the PDF is formatted.

#### Layer 3 — Context Enrichment
Before storing each piece, we tag it with where it came from:
```
[Source: KAR-2026_Press-Release | Page 2 | Section: Financial Performance | Type: financial]
Khazanah recorded a TWRR of 8.4%...
```
This makes searches much more accurate because the AI knows the context, not just the isolated words.

### Technology Choices

| Component | Choice | Why |
|-----------|--------|-----|
| **PDF Parsing** | PyMuPDF + pdfplumber | PyMuPDF is fast for text extraction; pdfplumber is best for detecting tables in complex layouts |
| **Embeddings** | Google `gemini-embedding-001` (3072-dim) | Google's latest embedding model with full 3072-dimension vectors. Uses asymmetric task types (`RETRIEVAL_DOCUMENT` for indexing, `RETRIEVAL_QUERY` for search) for better retrieval. Free tier: 100 requests/min. Local fallback (`all-MiniLM-L6-v2`, 384-dim) available via config |
| **Vector Database** | ChromaDB | Simple local storage, no external services needed. Uses `upsert` for idempotent writes — safe for both append and re-index operations |
| **Chunk sizing** | ~600 tokens with 100-token overlap | Large enough to carry meaning, small enough for precise retrieval. Overlap ensures we don't lose context at boundaries |

### Pipeline Performance
Processing 4 Khazanah PDFs (61 pages total):
- **115 high-quality chunks** created
- **~68 seconds** total processing time (includes rate-limited Google embedding API calls at 0.7s intervals; retry with backoff on 429 errors)
- Automatic deduplication and noise filtering (headers, footers, page numbers removed)

---

## Setup Instructions

### Prerequisites
- [Docker Desktop](https://docs.docker.com/get-docker/) (recommended)
- A Google Gemini API key ([get one free here](https://aistudio.google.com/apikey))

### One-Command Setup (Docker)

```bash
# Clone and run the setup script — it prompts for your API key, then builds and starts everything
git clone <repo-url>
cd knb-ai

# macOS / Linux
bash setup.sh

# Windows (PowerShell)
.\setup.ps1
```

The script will:
1. Check Docker is installed and running
2. Prompt for your Gemini API key (or reuse existing `.env`)
3. Generate `.env` from the template
4. Build and start both services via `docker compose`
5. Print URLs when ready

```
Frontend:  http://localhost:3000
API Docs:  http://localhost:8000/docs
```

### Manual Setup (without Docker)

<details>
<summary>Click to expand</summary>

Requires Python 3.12+ and Node.js 20+.

```bash
# 1. Clone the repository
git clone <repo-url>
cd knb-ai

# 2. Set up environment
cp .env.example .env
# Edit .env and add your GEMINI_API_KEY

# 3. Install Python dependencies
python -m venv venv
# Windows:
.\venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate
pip install -r app/requirements.txt

# 4. Install frontend dependencies
cd frontend && npm install && cd ..

# 5. Start the backend
uvicorn app.main:app --reload --port 8000

# 6. Start the frontend (new terminal)
cd frontend && npm run dev

# 7. Open http://localhost:3000
# Upload PDFs → Click "Run Ingestion" → Start asking questions
```

</details>
```

---

## Section 2: RAG-Powered Query Engine

### How Questions Get Answered

When you type a question in the chat, here's what happens behind the scenes:

```
Your Question
     │
     ▼
┌────────────────────┐
│  Agent Supervisor   │ ← Classifies your intent (search / extract / compare / off-topic)
│  + Semantic Cache   │ ← Checks if a similar question was recently answered
└────────┬───────────┘
         │
         ▼
┌────────────────────┐
│  Hybrid Search      │ ← Finds the most relevant information from the report
│  (Vector + BM25)    │
└────────┬───────────┘
         │
         ▼
┌────────────────────┐
│  LLM Generation     │ ← Writes a natural-language answer using only the found context
│  (Gemini Flash)     │
└────────┬───────────┘
         │
         ▼
  Answer + Sources + Confidence Score
```

### Hybrid Search: Why Two Retrieval Methods?

| Method | What It Does | Good At | Bad At |
|--------|-------------|---------|--------|
| **Vector search** (semantic) | Finds chunks by *meaning* similarity | Paraphrased questions, synonyms | Exact numbers and acronyms |
| **BM25** (keyword) | Finds chunks by *word overlap* | Exact terms like "TWRR", "RM21.1b" | Understanding rephrased questions |

Using both gives better results than either alone. We merge them using **Reciprocal Rank Fusion (RRF)** with a **keyword boost**:

- Each method ranks its results independently
- RRF combines the ranks (not the raw scores) with equal 50/50 weighting
- **Keyword boost**: if your question contains specific terms (acronyms like "TWRR", "RAV", or exact figures) and BM25 finds chunks matching those terms, those chunks get an extra boost in the final ranking — even if vector search missed them entirely
- The top 6 most relevant chunks are passed to the LLM

This was a deliberate improvement. In early testing, asking *"What was Khazanah's TWRR?"* failed because the TWRR data lived in a table that embedded poorly (cosine score 0.25). BM25 ranked it #1, but vector search couldn't find it at all. With the keyword boost, the TWRR chunks now rank #1 and #2 after fusion.

**Why not add a reranker?** With only 115 chunks, a reranker adds latency and API cost for minimal improvement. RRF fusion already produces high-quality results. If the corpus grows to 1000+ chunks, adding a cross-encoder reranker would be worthwhile.

### Intent Classification

The Agent Supervisor examines each question and classifies it before routing:

| Intent | What It Means | Example |
|--------|-------------|---------|
| **search** | General Q&A about the report | "What was the TWRR?" |
| **extract** | Structured data extraction | "List all portfolio companies" |
| **compare** | Cross-year comparison | "How did assets change from 2024 to 2025?" |
| **off_topic** | Not related to the annual review | "What's the weather today?" |

This classification uses a single lightweight LLM call with zero-shot prompting.

### Confidence Scoring

Every answer gets a confidence level based on how relevant the retrieved chunks are:

| Level | Avg Similarity | What It Means |
|-------|---------------|---------------|
| **High** | ≥ 0.50 | Strong evidence found, answer is reliable |
| **Medium** | 0.40 – 0.50 | Partial evidence, answer may be incomplete |
| **Low** | 0.30 – 0.40 | Weak evidence, answer flagged with warning |
| **None** | < 0.30 | No relevant info found, question refused |

This prevents hallucination — the system refuses to guess when it doesn't find relevant information.

### Semantic Cache

Repeated or similar questions are answered instantly from cache:

- Uses cosine similarity (threshold: 0.95) to match semantically equivalent questions
- LRU eviction keeps cache at 100 entries max
- Cache hits skip both retrieval and LLM calls, reducing latency and API costs

### Prompt Engineering

The RAG prompt is designed with strict rules:
1. **Only cite from provided context** — never make up information
2. **Use numbered references** — citations appear as `[1]`, `[2]` in the answer text, matching the source numbers. This keeps the answer clean and readable (inspired by how Google Gemini displays citations)
3. **Admit uncertainty** — if the context doesn't fully answer, say so
4. **Structured format** — answers use paragraphs, bullet points, and tables as appropriate

### Technology Choices

| Component | Choice | Why |
|-----------|--------|-----|
| **Semantic search** | ChromaDB cosine similarity | Already stores our embeddings; no extra service needed |
| **Keyword search** | rank-bm25 (BM25Okapi) | Industry-standard keyword ranking, runs locally, no setup |
| **Fusion** | Reciprocal Rank Fusion (α=0.5) + keyword boost | Equal weighting ensures keyword matches aren't buried; boost surfaces exact-term hits |
| **LLM** | Google Gemini (swappable models) | Free tier, multiple models available. Default: Gemini 3.1 Flash Lite (500 requests/day) |
| **Rate limiting** | Exponential backoff retry (5s → 10s) | Handles free tier quota limits gracefully. Internal langchain retries disabled to avoid double-retry |
| **Caching** | In-memory semantic cache | Zero-cost, instant responses for repeated queries |

### Frontend Chat UI

The chat interface at `/chat` provides:
- **Model selector** in the header — switch between Gemini models (3.1 Flash Lite at 500 rpd, 2.5 Flash, 2.5 Flash Lite, 3 Flash) with rate limits shown
- **Suggested questions** to get started
- **Inline citation badges** — `[1]`, `[2]` in the answer text are rendered as clickable blue superscript badges that highlight the corresponding source
- **Compact source chips** below each answer showing document name, page number, and content type — click to expand the source snippet in a popover
- **Confidence badges** (green/yellow/orange/red) on every answer
- **Markdown rendering** with bold text, bullet lists, and paragraph breaks
- **Cache indicator** showing when an answer came from cache
- **Navigation** between Documents (upload/ingest) and Chat pages

---

## Known Limitations

- **Image-heavy PDFs**: Presentation decks with mostly visual content (charts as images) will have limited text extraction. We extract what text exists but can't yet read charts as images.
- **Embedding rate limits**: Google embedding free tier allows 100 requests/minute. The system rate-limits at 0.7s intervals and retries on 429 errors with exponential backoff (40s → 80s). Ingestion of 4 PDFs takes ~68s instead of ~25s due to this pacing. If switching to local embeddings (`all-MiniLM-L6-v2`), ingestion drops to ~25s with no rate limits.
- **Free tier LLM limits**: Gemini free tier has daily rate limits per model. The default model (Gemini 3.1 Flash Lite) allows 500 requests/day. Each query uses 2 LLM calls (intent classification + answer generation). Switch models from the chat UI dropdown if one runs out.
- **Tables embed poorly**: Financial tables still score lower in vector similarity than narrative text, though `gemini-embedding-001` handles them significantly better than the previous local model (avg score improved from 0.25–0.35 to 0.55–0.65). The keyword boost in RRF fusion further mitigates this. A potential next step: use the LLM to generate a natural-language summary of each table at ingestion time (e.g. *"This table shows TWRR by asset class from 2019–2024"*) and embed that summary alongside the raw table.

---

---

## Section 3: Structured Data Extraction

### What It Does

Beyond Q&A, the system can **extract structured data** from the Annual Review into clean, typed JSON objects. This is different from the chat — instead of generating a free-text answer, it fills in a predefined schema using only the report's actual content.

### Pre-Defined Extraction Types

| Type | What It Extracts | Example Output |
|------|-----------------|----------------|
| **Portfolio Companies** | Company name, sector, ownership %, asset class, description | `{"name": "EDOTCO", "sector": "Digital Infrastructure", "ownership_pct": 31.7}` |
| **Financial Metrics** | Metric name, value, year, unit, source context | `{"metric_name": "Profit from operations", "value": "5.6", "year": "2025", "unit": "RM billion"}` |
| **Investment Performance** | Asset class, portfolio weight, TWRR, yearly returns | `{"asset_class": "Public Markets: Malaysia", "portfolio_weight_pct": 57.5, "twrr_latest": "6.5%"}` |
| **Key Highlights** | Category, title, description, value, year | `{"category": "ESG", "title": "Community Investment", "value": "RM3.4 billion"}` |
| **Custom** | User-defined — any extraction request | User types what they want and the LLM figures out the structure |
| **All** | Runs all four pre-defined types at once | Combined JSON with all sections |

### How It Works

```
  User selects extraction type (or types "List all portfolio companies" in chat)
      │
      ▼
  ┌─────────────────────────┐
  │  Targeted Retrieval      │  ← Multiple search queries per type for broad coverage
  │  (3-4 queries × 10 each) │     e.g. "portfolio companies" + "investee" + "ownership"
  └──────────┬──────────────┘
             │
             ▼  Top 15 unique chunks (deduplicated, ranked)
  ┌─────────────────────────┐
  │  LLM Structured Output   │  ← Gemini with_structured_output(PydanticSchema)
  │  (constrained JSON)      │     Forces output to match the schema exactly
  └──────────┬──────────────┘
             │
             ▼  If structured output returns None (model can't parse)
  ┌─────────────────────────┐
  │  Fallback: Plain JSON    │  ← Free-form generation + Pydantic model_validate()
  │  (parse + validate)      │     Schema is included in prompt as reference
  └──────────┬──────────────┘
             │
             ▼
  Validated structured data (Pydantic models → JSON)
```

**Two-stage extraction approach:**
1. **Primary**: LangChain's `with_structured_output()` forces the LLM to generate JSON matching the Pydantic schema directly. This is the most reliable method.
2. **Fallback**: If the structured output returns None (can happen with complex contexts on smaller models), the system falls back to plain text generation with the schema embedded in the prompt, then validates with `model_validate()`.

### Two Access Paths

1. **Dedicated `/extract` page**: Click a type → get a sortable table instantly. Export to JSON. Ideal for browsing all extracted data.
2. **Via chat**: Type "List all portfolio companies" → agent routes to `extract` intent → returns structured data as a formatted table inline in the chat conversation.

Both use the same underlying extraction tool, ensuring consistent results.

### Schema Design

Each schema uses **Pydantic models** with typed fields and descriptions:

```python
class PortfolioCompany(BaseModel):
    name: str                          # "Tenaga Nasional Berhad"
    sector: str | None                 # "Power"
    ownership_pct: float | None        # 21.6
    asset_class: str | None            # "Public Markets: Malaysia"
    description: str | None            # Brief role from the report

class FinancialMetric(BaseModel):
    metric_name: str                   # "Realisable Asset Value (RAV)"
    value: str                         # "RM156 billion"
    year: str | None                   # "2025"
    unit: str | None                   # "RM billion"
    source_context: str | None         # Where this appears
```

**Why nullable fields?** Not every company has an ownership percentage listed, and not every metric has a clear year. Setting these to `None` (instead of guessing) ensures the extraction is honest about what the report actually says.

### Technology Choices

| Component | Choice | Why |
|-----------|--------|-----|
| **Schema framework** | Pydantic v2 | Type validation, JSON schema generation, model_validate() for fallback parsing |
| **Structured output** | LangChain `with_structured_output()` | Forces LLM to conform to schema. Falls back to prompt-based extraction when it returns None |
| **Retrieval** | Multi-query targeted retrieval | Each extraction type uses 3-4 specialised search queries for broad coverage (vs single query for Q&A) |
| **Chunk limit** | Top 15 per extraction | More chunks than Q&A (6) since extraction needs broader coverage of the document |

---

## Section 4: API Design & Deployment

### API Endpoints

All endpoints live under the `/api` prefix. Interactive docs are available at `/docs` (Swagger UI) and `/redoc` (ReDoc).

| Method | Endpoint | Tag | Description |
|--------|----------|-----|-------------|
| `GET` | `/api/health` | System | Health check — returns PDF count and filenames |
| `GET` | `/api/models` | System | List available LLM models with rate limits |
| `POST` | `/api/upload` | Documents | Upload a PDF (100 MB max, extension allowlist) |
| `GET` | `/api/documents` | Documents | List all uploaded PDFs with file sizes |
| `POST` | `/api/ingest` | Ingestion | Run full pipeline: parse → chunk → embed → store |
| `GET` | `/api/ingest/status` | Ingestion | Current vector store stats (chunk count, config) |
| `POST` | `/api/query` | Query | Natural-language Q&A with citations and confidence |
| `POST` | `/api/extract` | Extraction | Structured data extraction into typed JSON |

### API Design Decisions

**Typed response models:** Every endpoint declares a Pydantic `response_model`, so the OpenAPI spec has full JSON schemas. Frontend devs and API consumers see exact field types, required/optional markers, and examples in the docs.

**Input validation:** `QueryRequest.question` is constrained to 1–2000 characters. `ExtractionType` is an `Enum`, so invalid types get a 422 before hitting application code. Upload enforces a `.pdf` extension allowlist and 100 MB size cap. Filenames are sanitised to prevent path traversal.

**Error responses:** All error-returning endpoints declare `responses={400: ..., 500: ...}` with an `ErrorResponse` model (`{"error": str, "detail": str | None}`). A global exception handler catches unhandled errors and returns consistent JSON instead of HTML stack traces.

**CORS:** Allows `localhost:3000` and `127.0.0.1:3000` only — tightened to just the frontend origin rather than `*`.

### Docker Compose

The project ships with a `docker-compose.yml` for one-command deployment:

```bash
cp .env.example .env
# Edit .env with your GEMINI_API_KEY
docker compose up --build
# Backend: http://localhost:8000 (Swagger: /docs)
# Frontend: http://localhost:3000
```

**Services:**
| Service | Base Image | Dockerfile | Ports | Notes |
|---------|-----------|------------|-------|-------|
| `backend` | `python:3.12-slim` | `app/Dockerfile` | 8000 | FastAPI + ChromaDB, health check on `/api/health` |
| `frontend` | `node:22-alpine` | `frontend/Dockerfile` | 3000 | Next.js production build, depends on backend health |

**Volumes:** ChromaDB data is persisted in a named Docker volume (`chroma_data`). Uploaded PDFs are bind-mounted from `./app/data` so they survive container restarts.

### Frontend Pages

| Page | Route | Purpose |
|------|-------|---------|
| **Documents** | `/` | Upload PDFs, trigger ingestion, view processing status |
| **Chat** | `/chat` | Natural-language Q&A with model selector, citations, confidence badges |
| **Extract** | `/extract` | Structured extraction with type selector, sortable tables, JSON export |

---

*More sections will be added as modules are completed.*