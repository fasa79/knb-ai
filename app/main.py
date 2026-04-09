"""FastAPI application entry point."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.ingestion.pipeline import IngestionPipeline
from app.core.vector_store import get_vector_store
from app.agents.supervisor import get_supervisor
from app.core.llm_client import AVAILABLE_MODELS
from app.api.schemas import (
    HealthResponse,
    DocumentListResponse,
    UploadResponse,
    IngestResponse,
    IngestStatusResponse,
    QueryResponse,
    ExtractResponse,
    ExtractionType,
    ModelsResponse,
    ErrorResponse,
)
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

settings = get_settings()

app = FastAPI(
    title="Khazanah Annual Review AI",
    description=(
        "AI-powered tool for querying and extracting insights from Khazanah's Annual Review. "
        "Supports natural-language Q&A, structured data extraction, and document management."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://knb-ai.fadhs.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Global Error Handler ──────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Return consistent JSON for unhandled errors."""
    logger.error(f"Unhandled error on {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)},
    )


# ── Health ────────────────────────────────────────────────────────

@app.get(
    "/api/health",
    response_model=HealthResponse,
    tags=["System"],
    summary="Health check",
)
async def health_check():
    """Check if the API is running and list available PDFs."""
    data_dir = Path(settings.data_dir)
    pdf_files = list(data_dir.glob("*.pdf")) if data_dir.exists() else []
    return {
        "status": "healthy",
        "pdf_count": len(pdf_files),
        "pdfs": [f.name for f in pdf_files],
    }


ALLOWED_EXTENSIONS = {".pdf"}
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB


@app.post(
    "/api/upload",
    response_model=UploadResponse,
    tags=["Documents"],
    summary="Upload a PDF",
    responses={400: {"model": ErrorResponse}},
)
async def upload_pdf(file: UploadFile = File(...)):
    """Upload a PDF file to the data directory for later ingestion."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Only PDF files are allowed. Got: {ext}")

    # Sanitize filename — keep only alphanumeric, hyphens, underscores, dots
    safe_name = "".join(c if c.isalnum() or c in "-_." else "_" for c in file.filename)
    if not safe_name.lower().endswith(".pdf"):
        safe_name += ".pdf"

    data_dir = Path(settings.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    dest = data_dir / safe_name

    # Read and validate size
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail=f"File too large. Max: {MAX_FILE_SIZE // (1024*1024)}MB")

    dest.write_bytes(content)
    logger.info(f"Uploaded: {safe_name} ({len(content) / 1024:.1f} KB)")

    return {
        "filename": safe_name,
        "size_kb": round(len(content) / 1024, 1),
        "message": f"Successfully uploaded {safe_name}",
    }


@app.get(
    "/api/documents",
    response_model=DocumentListResponse,
    tags=["Documents"],
    summary="List uploaded documents",
)
async def list_documents():
    """List all uploaded PDF documents with their file sizes."""
    data_dir = Path(settings.data_dir)
    if not data_dir.exists():
        return {"documents": []}

    docs = []
    for f in sorted(data_dir.glob("*.pdf")):
        docs.append({
            "filename": f.name,
            "size_kb": round(f.stat().st_size / 1024, 1),
        })
    return {"documents": docs}


@app.delete(
    "/api/documents/{filename}",
    tags=["Documents"],
    summary="Delete a document",
    responses={404: {"model": ErrorResponse}},
)
async def delete_document(filename: str):
    """Delete a PDF document from the data directory."""
    import re
    if not re.match(r'^[\w\-. ()]+\.pdf$', filename, re.IGNORECASE):
        raise HTTPException(status_code=400, detail="Invalid filename")
    file_path = Path(settings.data_dir) / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {filename}")
    file_path.unlink()
    return {"deleted": filename}


# ── Ingestion Pipeline ────────────────────────────────────────────


@app.post(
    "/api/ingest",
    response_model=IngestResponse,
    tags=["Ingestion"],
    summary="Run ingestion pipeline",
    responses={500: {"model": ErrorResponse}},
)
async def ingest_documents(clear_existing: bool = True, use_vision: bool = False):
    """Run the full ingestion pipeline: parse → chunk → embed → store.

    - **clear_existing=true**: Wipe vector store and re-index all PDFs (default).
    - **clear_existing=false**: Append new chunks (upsert) alongside existing ones.
    - **use_vision=true**: Use Gemini Vision to analyze chart/graph images (slower, uses more API quota).
    """
    try:
        pipeline = IngestionPipeline(use_vision=use_vision)
        result = pipeline.run(clear_existing=clear_existing)
        return result.summary
    except Exception as e:
        logger.error(f"Ingestion failed: {e}")
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")


@app.get(
    "/api/ingest/status",
    response_model=IngestStatusResponse,
    tags=["Ingestion"],
    summary="Get ingestion status",
)
async def ingestion_status():
    """Get current vector store status: chunk count, data directory, and config."""
    try:
        pipeline = IngestionPipeline()
        return pipeline.get_status()
    except Exception as e:
        return {"chunks_stored": 0, "error": str(e)}


# ── Query (RAG) ───────────────────────────────────────────────────


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000, description="Natural language question about the Annual Review")
    use_cache: bool = Field(default=True, description="Check semantic cache for similar recent queries")
    model: str | None = Field(default=None, description="LLM model override (e.g. 'gemini-2.5-flash')")


@app.post(
    "/api/query",
    response_model=QueryResponse,
    tags=["Query"],
    summary="Ask a question",
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def query_documents(request: QueryRequest):
    """Ask a natural-language question about the Annual Review.

    The agent supervisor classifies intent (search / extract / compare / off_topic)
    and routes to the appropriate tool. Returns an answer with source citations
    and a confidence score.
    """
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    try:
        supervisor = get_supervisor()
        result = await supervisor.process_query(
            query=request.question.strip(),
            use_cache=request.use_cache,
            model=request.model,
        )
        return result
    except Exception as e:
        logger.error(f"Query failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")


@app.get(
    "/api/models",
    response_model=ModelsResponse,
    tags=["System"],
    summary="List available LLM models",
)
async def list_models():
    """List available LLM models with their rate limits."""
    return {"models": AVAILABLE_MODELS, "default": settings.gemini_model}


# ── Extraction ────────────────────────────────────────────────────


class ExtractRequest(BaseModel):
    extraction_type: ExtractionType = Field(default=ExtractionType.all, description="Type of data to extract")
    query: str | None = Field(default=None, description="Required for 'custom' type. Optional extra context for others.")
    model: str | None = Field(default=None, description="LLM model override")


@app.post(
    "/api/extract",
    response_model=ExtractResponse,
    tags=["Extraction"],
    summary="Extract structured data",
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def extract_data(request: ExtractRequest):
    """Extract structured data from the Annual Review into typed JSON.

    **Types:**
    - `portfolio` — Company names, sectors, ownership stakes
    - `financials` — Key financial metrics (RAV, TWRR, assets)
    - `investment_performance` — Returns by asset class with yearly TWRR
    - `highlights` — Strategic initiatives, ESG, milestones
    - `custom` — Free-form extraction (requires `query` field)
    - `all` — Run all pre-defined types at once
    """
    if request.extraction_type == ExtractionType.custom and not request.query:
        raise HTTPException(status_code=400, detail="'query' is required for custom extraction")

    try:
        from app.agents.tools.extraction_tool import get_extraction_tool
        tool = get_extraction_tool()
        result = await tool.extract(
            extraction_type=request.extraction_type.value,
            query=request.query,
            model=request.model,
        )
        return result
    except Exception as e:
        logger.error(f"Extraction failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Extraction failed: {str(e)}")
