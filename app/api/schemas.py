"""Pydantic response models for the API.

Typed response schemas enable auto-generated OpenAPI docs and consistent responses.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ── Health ────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str = Field(example="healthy")
    pdf_count: int = Field(description="Number of PDFs in the data directory")
    pdfs: list[str] = Field(description="List of PDF filenames")


# ── Documents ─────────────────────────────────────────────────────

class DocumentInfo(BaseModel):
    filename: str
    size_kb: float


class DocumentListResponse(BaseModel):
    documents: list[DocumentInfo]


class UploadResponse(BaseModel):
    filename: str
    size_kb: float
    message: str


# ── Ingestion ─────────────────────────────────────────────────────

class IngestDocumentDetail(BaseModel):
    filename: str
    pages: int
    chunks: int
    tables: int
    images: int
    duration_s: float = Field(alias="duration_s")
    status: str
    error: str | None = None


class IngestResponse(BaseModel):
    documents_processed: int
    total_chunks_stored: int
    total_duration_seconds: float
    details: list[IngestDocumentDetail]


class FileIngestStatus(BaseModel):
    filename: str
    chunks: int
    ingested: bool


class IngestStatusResponse(BaseModel):
    chunks_stored: int
    data_dir: str
    pdf_files: list[str]
    chunk_size: int
    chunk_overlap: int
    file_status: list[FileIngestStatus] = []


# ── Query ─────────────────────────────────────────────────────────

class SourceReference(BaseModel):
    source: str
    page: int
    section: str = ""
    content_type: str = "text"
    relevance_score: float = 0.0
    text_snippet: str = ""


class QueryResponse(BaseModel):
    answer: str
    sources: list[SourceReference]
    confidence: str
    confidence_label: str
    avg_score: float = 0.0
    intent: str
    cached: bool = False
    extraction_data: Any | None = Field(default=None, description="Structured extraction data (when intent=extract)")


# ── Extraction ────────────────────────────────────────────────────

class ExtractionType(str, Enum):
    portfolio = "portfolio"
    financials = "financials"
    investment_performance = "investment_performance"
    highlights = "highlights"
    custom = "custom"
    all = "all"


class ExtractionSource(BaseModel):
    source: str
    page: int
    content_type: str = "text"


class ExtractResponse(BaseModel):
    extraction_type: str
    data: Any | None = None
    chunks_used: int | None = None
    sources: list[ExtractionSource] | None = None
    error: str | None = None
    errors: list[str] | None = None
    fallback: bool | None = None


# ── Models ────────────────────────────────────────────────────────

class ModelInfo(BaseModel):
    id: str
    name: str
    rpm: int
    rpd: int
    provider: str


class ModelsResponse(BaseModel):
    models: list[ModelInfo]
    default: str


# ── Error ─────────────────────────────────────────────────────────

class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None
