# Khazanah Annual Review AI

An AI-powered tool that lets you **ask questions about Khazanah's Annual Review in plain English** and get accurate answers with source citations. Think of it as a smart assistant that has read the entire annual report and can instantly find the information you need.

> **Video Walkthrough:** [Watch the 3–5 min demo on Loom](https://www.loom.com/share/b362dc701ceb4e2bb32063a7748c78c1)
>
> **Live Demo:** [knb-ai.fadhs.com](https://knb-ai.fadhs.com)

---

## What This Tool Does

Instead of manually searching through a 20+ page annual report PDF, you can:

- **Ask questions** like *"What was Khazanah's total assets in 2025?"* and get an answer with the exact page reference
- **View structured data** — portfolio companies, financial metrics, and key highlights extracted automatically
- **Upload new reports** — drop in a new PDF and the system processes it automatically

The tool has three main pages:

| Page | What You Do There |
|------|------------------|
| **Documents** (`/`) | Upload PDFs and process them into the knowledge base |
| **Chat** (`/chat`) | Ask questions in natural language, get cited answers |
| **Extract** (`/extract`) | Pull structured data (company lists, financials, metrics) into tables you can export |

---

## How It Works

```
┌──────────────┐     ┌──────────────┐     ┌───────────────────┐
│  You (User)  │────▶│   Frontend   │────▶│   Backend API      │
│              │◀────│  (Next.js)   │◀────│   (FastAPI)        │
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
                                    │  (searchable       │
                                    │   knowledge base)  │
                                    └───────────────────┘
```

**In simple terms:**

1. You upload a PDF annual report
2. The system reads every page — text, tables, charts — and breaks it into meaningful pieces
3. Those pieces are stored in a searchable knowledge base
4. When you ask a question, the AI finds the most relevant pieces and writes an accurate answer
5. Every answer comes with page numbers so you can verify it yourself

---

## Setup Instructions

### Prerequisites
- [Docker Desktop](https://docs.docker.com/get-docker/)
- A Google Gemini API key ([get one free here](https://aistudio.google.com/apikey))

### Option 1: One-Command Setup (Recommended)

```bash
git clone <repo-url>
cd knb-ai

# macOS / Linux
bash setup.sh

# Windows (PowerShell)
.\setup.ps1
```

The script will:
1. Check that Docker is installed and running
2. Ask for your Gemini API key
3. Build and start both services
4. Print the URLs when ready

```
Frontend:  http://localhost:3000
API Docs:  http://localhost:8000/docs
```

Then: open http://localhost:3000 → Upload PDFs → Click "Run Ingestion" → Go to Chat.

### Option 2: Docker Compose (manual .env)

<details>
<summary>Click to expand</summary>

```bash
git clone <repo-url>
cd knb-ai
cp .env.example .env
# Edit .env — set GEMINI_API_KEY=your-key-here

docker compose up --build
# Frontend: http://localhost:3000
# API Docs: http://localhost:8000/docs
```

</details>

### Option 3: Run Locally (no Docker)

<details>
<summary>Click to expand — requires Python 3.12+ and Node.js 20+</summary>

```bash
git clone <repo-url>
cd knb-ai

# Environment
cp .env.example .env
# Edit .env — set GEMINI_API_KEY=your-key-here

# Backend
python -m venv venv
# Windows: .\venv\Scripts\activate
# macOS/Linux: source venv/bin/activate
pip install -r app/requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend (new terminal)
cd frontend && npm install && npm run dev
```

Open http://localhost:3000 → Upload PDFs → Click "Run Ingestion" → Go to Chat.

</details>

---

## How We Built It

### Document Processing

The system doesn't just split PDFs at fixed intervals. It adapts to the content:

- **Tables** (like financial data) are kept whole — splitting a table destroys its meaning
- **Bullet lists** and grouped items are kept together
- **Long narratives** are split at natural topic boundaries using AI similarity detection
- Every piece is tagged with its source file, page number, and section — so citations are always accurate

We process Khazanah Annual Review PDFs into **searchable chunks** in about 60 seconds.

### Question Answering

When you ask a question, the system uses **two search methods** working together:

- **Meaning-based search** finds content by understanding what you mean (good for paraphrased questions)
- **Keyword search** finds content by exact word matching (good for acronyms like "TWRR" and specific figures like "RM21.1b")

Both sets of results are merged so you get the best of both. In early testing, questions about TWRR failed because the data was in a table that meaning-based search couldn't find — adding keyword search fixed this.

Every answer includes a **confidence score**. If the system can't find relevant information, it says so instead of guessing. This prevents the tool from confidently making things up.

An **intelligent router** reads each question and decides what to do: search for an answer, extract structured data, compare across years, or politely refuse off-topic questions.

Repeated questions are answered instantly from a **cache** — no extra AI calls needed.

### Structured Data Extraction

Beyond Q&A, the system can pull structured data into clean tables:

| Type | What It Extracts |
|------|-----------------|
| **Portfolio Companies** | Company name, sector, ownership stake |
| **Financial Metrics** | Key figures like total assets, TWRR, dividends |
| **Investment Performance** | Returns by asset class with yearly breakdown |
| **Key Highlights** | Strategic initiatives, ESG programs, milestones |
| **Custom** | Anything you ask for — the AI figures out the structure |

You can access this from the dedicated Extract page (click a type, get a table, export to JSON) or directly in chat by asking something like *"List all portfolio companies."*

We tested extraction across 11 different query types and verified every result against the actual PDF content — **zero hallucinated values** were found.

### API & Deployment

The backend exposes a REST API with interactive documentation at `/docs`. Every endpoint has typed request/response models, input validation, and consistent error handling.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check — returns status and available PDFs |
| `/api/upload` | POST | Upload a PDF to the data directory |
| `/api/documents` | GET | List uploaded documents with file sizes |
| `/api/documents/{filename}` | DELETE | Remove a document from the data directory |
| `/api/ingest` | POST | Run ingestion pipeline (parse → chunk → embed → store) |
| `/api/ingest/status` | GET | Current vector store status and per-file chunk counts |
| `/api/query` | POST | Ask a natural-language question (routed by agent supervisor) |
| `/api/extract` | POST | Extract structured data into typed JSON |
| `/api/models` | GET | List available LLM models and rate limits |

Full OpenAPI spec: [knb-ai-api.fadhs.com/docs](https://knb-ai-api.fadhs.com/docs) or http://localhost:8000/docs

The project ships as a Docker Compose setup with two containers (backend + frontend) that start with one command.

---

## Design Decisions & Trade-offs

| Decision | What We Chose | Why | With More Time |
|----------|--------------|-----|----------------|
| **Embedding model** | Google `gemini-embedding-001` (3072-dim) | Best free embedding model available; full dimensions preserve information for future use cases | Use a dedicated embedding service like Cohere or OpenAI for higher throughput |
| **Vector database** | ChromaDB (local) | Zero setup, runs anywhere, good enough for <1000 chunks | Switch to Qdrant or Pinecone for production scalability and filtering |
| **LLM** | Google Gemini (free tier, swappable models) | Multiple models available, generous free quota (500 req/day on lite). Model can be switched from the UI | Use a paid tier or self-hosted model for consistent latency and no rate limits |
| **Search strategy** | Hybrid (vector + keyword + fusion) | Vector alone missed table data; keyword alone missed paraphrased questions. Combining both solved both problems | Add a cross-encoder reranker once the corpus grows past ~1000 chunks |
| **Chunking** | Content-aware (tables kept whole, narrative split by topic) | Naive fixed-size splitting broke tables and mixed unrelated content together | Add LLM-generated table summaries at ingestion time for even better table retrieval |
| **Structured extraction** | LLM constrained output with fallback | Primary method forces exact schema compliance; fallback catches cases where the model struggles | Fine-tune a smaller model specifically for extraction to reduce fallback rate |
| **Caching** | In-memory semantic cache | Zero cost, instant for repeated queries | Use Redis for persistence across restarts and shared across instances |
| **Frontend** | Next.js with Tailwind | Fast to build, good developer experience, easy to deploy | Add real-time streaming responses, dark mode, and PDF viewer integration |

---

## Known Limitations

- **Charts as images**: Presentation decks with charts stored as images can be analyzed using an opt-in vision model (`use_vision=True` during ingestion). The system sends all extracted images to Gemini Vision for text descriptions that get embedded alongside the source text. A basic size filter skips tiny icons (<30KB) and full-page backgrounds (>1MB). This is rate-limited and adds processing time, so it's off by default.
- **Embedding rate limits**: Google's free tier allows 100 requests/minute. Ingestion takes ~68s due to pacing (vs ~25s with local embeddings). The system handles this automatically with rate limiting and retry.
- **Daily LLM quota**: The default model allows 500 requests/day. Each question uses 2 calls (classification + answer). You can switch models from the chat dropdown if one runs out.
- **Tables in vector search**: Financial tables score lower in meaning-based search than narrative text. The keyword search and fusion boost mitigate this, but it's not fully solved.
- **Custom extraction fallback**: On complex queries, the AI sometimes can't produce structured output directly and falls back to a two-step approach (generate then validate). This works but is slightly less reliable — in testing, 7 of 11 custom queries needed fallback.

---

## Stretch Goals Completed

Beyond the core requirements, we implemented:

- **Semantic caching** — repeated or similar questions answered instantly from cache
- **Hallucination guardrails** — confidence scoring, refusal when no evidence is found, off-topic detection
- **Agentic routing** — the system automatically decides whether to search, extract, or compare based on the question
- **One-command Docker deployment** — setup scripts that prompt for API key and handle everything
- **Multi-year comparison** — ask questions like *"How did total assets change from 2024 to 2025?"* and the system retrieves data from both years, labels sources by year, and generates a structured comparison table. Automatically detects years in queries, maps them to the correct source documents (KAR-2025 covers FY2024, KAR-2026 covers FY2025), and uses a dedicated comparison prompt.
- **Multi-modal chart analysis** — opt-in vision pipeline (`use_vision=True`) sends extracted images to Gemini Vision for text descriptions. A basic size filter skips tiny icons (<30KB) and full-page backgrounds (>1MB). Descriptions are embedded as searchable chunks alongside the source text.
- **RAGAS evaluation pipeline** — automated quality scoring on 15 ground-truth questions:

  | Metric | Score | What It Measures |
  |--------|-------|-----------------|
  | Context Precision | **1.00** | Are the top-ranked chunks actually relevant? |
  | Context Recall | **1.00** | Were all relevant chunks retrieved? |
  | Faithfulness | **0.74** | Is the answer grounded in the retrieved context? |
  | Answer Relevancy | **0.62** | Does the answer directly address the question? |

  Perfect retrieval scores confirm the hybrid search pipeline works well. Faithfulness and relevancy are impacted by free-tier rate limits causing some RAGAS judge calls to time out — with a paid API, these would be higher. Run it yourself: `python -m app.evaluation.run_eval`

---

## Design Questions

### 1. If this tool were deployed internally at Khazanah for daily use by analysts, what would you change?

Having worked on production RAG systems — where I enhanced a RAG application with hybrid search to reach 95% retrieval accuracy across APAC affiliates — I know the gap between a working prototype and a reliable internal tool is mostly about infrastructure and trust.

**Infrastructure changes:**
- **Swap ChromaDB for a managed vector database** (Qdrant Cloud or Pinecone). ChromaDB is file-based and locks during writes — if one analyst is querying while another triggers ingestion, they'll block each other. A managed DB handles concurrent access natively and supports metadata filtering (e.g. filter by report year or document type).
- **Move off free-tier LLM** to a paid API or self-hosted model via vLLM. The current 500 requests/day limit would be exhausted by 20 analysts before lunch. In my current role, we use Portkey as a centralized LLM gateway to manage API keys, route across providers, and guarantee consistent latency for user-facing tools — a similar pattern would work here.
- **Add a task queue** (Celery + Redis or Airflow) for ingestion. Right now, ingestion blocks the API process. I've built ETL pipelines with Apache Airflow in previous roles — the same pattern applies here: ingestion should run asynchronously so the API stays responsive.
- **Put the API behind an API gateway** with SSO/OAuth authentication, per-user rate limiting, and audit logging. In my experience, every internal tool in a regulated enterprise requires SSO integration — it's a non-negotiable for production deployment.

**Data & quality:**
- Add document versioning — track which version of each report was ingested, who uploaded it, when. This matters when analysts need to know if they're querying the latest data.
- Implement a feedback loop — let analysts flag wrong answers. I've seen this work well in practice: even a simple thumbs-up/down button generates signal you can use to re-tune prompts and identify weak spots in the knowledge base.

**Observability:**
- Add structured logging and request tracing (OpenTelemetry) with a Grafana dashboard. You need to know which queries fail, which take too long, and which documents get the most questions. Having set up CI/CD and monitoring pipelines in previous roles, I can say that observability is what separates a tool people trust from one they abandon.

---

### 2. A user reports that the tool confidently returned an incorrect answer and shared it in a presentation. How would you prevent this?

This is a real risk I've thought about — in my current role, the extraction pipelines I built are used for competitive intelligence, so accuracy is non-negotiable.

**First: investigate the root cause.**
Check the specific query: what chunks were retrieved, what confidence score was assigned, and what the LLM generated. The failure usually falls into one of three buckets:
- **Bad parsing** — the PDF chunk was garbled or incomplete (e.g. a table that didn't parse correctly)
- **Bad retrieval** — the relevant chunk existed but wasn't surfaced (search failed)
- **Bad generation** — the LLM hallucinated despite having correct context

Each failure type has a different fix. You can't solve a parsing problem by tweaking prompts.

**What's already in place:**
The current system has confidence scoring — it refuses to answer when evidence is weak. Every answer shows source page numbers so analysts can verify. But clearly, the thresholds may need tightening based on this incident.

**What I would add:**
- **Automated fact-checking** — after generating an answer, run a second LLM call that checks: *"Is this answer actually supported by the provided context?"* If the verification disagrees, flag the answer as "unverified" rather than showing high confidence. This is a lightweight cross-check that catches most hallucinations.
- **Visible disclaimer** — every answer should carry a note: *"AI-generated — verify against source before external use."* It sets the right expectation. Tools that are used for presentations need guardrails that are visible, not just technical.
- **RAGAS evaluation pipeline** — run regular automated evaluations against a curated question-answer set to catch regressions. Track faithfulness (does the answer match the context?) and relevancy (did we retrieve the right chunks?) over time. This is the same principle as regression testing in CI/CD — you want to know when a pipeline change makes things worse before users notice.
- **Audit trail** — log every question, answer, sources used, and confidence score. When something goes wrong, you need to trace exactly what happened. This also enables post-incident analysis and helps identify patterns.

---

### 3. You need to push an update to the RAG pipeline, but the tool is actively being used by 20 analysts. How do you roll out the change safely?

In previous roles, I managed deployments on Kubernetes with CI/CD pipelines on GitLab — rolling updates to production services without downtime was a regular part of the job. The same principles apply here.

**Step 1: Shadow test before touching production.**
Run the updated pipeline against a test set of known queries — the same questions analysts commonly ask. Compare the new answers against the current answers side by side. If quality drops on any query, investigate before proceeding. This is cheap and catches most regressions.

**Step 2: Blue-green deployment.**
Deploy the updated pipeline as a separate instance ("green") alongside the current one ("blue"). With Docker and Kubernetes, this is straightforward — I'd spin up a green deployment behind the same load balancer.
- Route a small percentage of traffic (10%, or just 2-3 volunteer analysts) to green.
- Monitor error rates, confidence scores, and response times on green vs. blue.
- If green performs equally or better after a day, gradually shift all traffic.
- If green shows problems, roll back instantly by routing everything back to blue. Zero downtime.

**Step 3: Handle vector store changes carefully.**
If the update changes embeddings or chunking (not just prompts), the risk is higher — you can't serve old and new embeddings from the same index. In this case:
- Build the new index in parallel (a new ChromaDB collection alongside the old one).
- Switch the API to read from the new collection only after shadow testing confirms quality.
- Keep the old collection for a rollback window (e.g. 7 days).

**Step 4: Communicate.**
Notify analysts before the change: *"We're improving the search pipeline this week. You may notice slightly different answers. Please flag anything that looks off."* This is underrated — it turns 20 analysts into 20 testers, and it builds trust because you're being transparent rather than making silent changes.

What I would **not** do: push directly to production during business hours without a rollback plan. Analysts lose trust fast if the tool goes down or starts giving worse answers after an update.

---

## Project Structure

```
knb-ai/
├── app/                        # Backend (Python/FastAPI)
│   ├── main.py                 # API entry point
│   ├── config.py               # Central configuration
│   ├── Dockerfile              # Backend container
│   ├── requirements.txt        # Python dependencies
│   ├── api/                    # Response models & schemas
│   ├── agents/                 # Intent router + tools
│   │   ├── supervisor.py       # Agent supervisor (routes questions)
│   │   └── tools/              # Search, extraction, comparison tools
│   │       ├── search_tool.py  # Hybrid search (vector + keyword + RRF)
│   │       ├── extraction_tool.py  # Structured data extraction
│   │       └── compare_tool.py     # Multi-year comparison
│   ├── core/                   # Shared services
│   │   ├── llm_client.py       # LLM provider abstraction
│   │   ├── embeddings.py       # Embedding service (Google/local)
│   │   ├── vector_store.py     # ChromaDB wrapper
│   │   ├── keyword_search.py   # BM25 keyword search
│   │   ├── pdf_parser.py       # PDF parsing (text, tables, images)
│   │   ├── vision_parser.py    # Gemini Vision for chart analysis
│   │   └── cache.py            # Semantic query cache
│   ├── ingestion/              # PDF processing pipeline
│   ├── extraction/             # Pydantic schemas for structured output
│   └── evaluation/             # RAGAS evaluation pipeline
│       ├── run_eval.py         # Evaluation runner
│       ├── dataset.py          # Ground-truth Q&A pairs
│       └── results/            # Saved evaluation results
├── frontend/                   # Frontend (Next.js)
│   ├── Dockerfile              # Frontend container
│   └── src/app/
│       ├── page.tsx            # Document upload & ingestion
│       ├── chat/page.tsx       # Q&A chat interface
│       └── extract/page.tsx    # Structured data extraction
├── docker-compose.yml          # One-command deployment
├── setup.ps1                   # Windows setup script
├── setup.sh                    # macOS/Linux setup script
├── .env.example                # Environment template
└── README.md
```