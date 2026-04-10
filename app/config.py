"""Centralized configuration — single source of truth for all settings."""

from __future__ import annotations

import os
from pathlib import Path
from functools import lru_cache

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment / .env file."""

    # ── LLM Provider ──────────────────────────────────────────────
    llm_provider: str = Field(default="google_gemini", description="LLM provider: google_gemini | groq | ollama")
    gemini_api_key: str = Field(default="", description="Google Gemini API key")
    gemini_model: str = Field(default="gemini-3-flash-preview", description="Gemini model name")
    groq_api_key: str = Field(default="", description="Groq API key")
    groq_model: str = Field(default="llama-3.3-70b-versatile", description="Groq model name")
    ollama_base_url: str = Field(default="http://localhost:11434", description="Ollama base URL")
    ollama_model: str = Field(default="llama3.2", description="Ollama model name")

    # ── Embeddings ────────────────────────────────────────────────
    embedding_provider: str = Field(default="google", description="Embedding provider: google | local")
    embedding_model: str = Field(default="gemini-embedding-2-preview", description="Embedding model name")

    # ── Vector DB ─────────────────────────────────────────────────
    chroma_persist_dir: str = Field(default="./chroma_db", description="ChromaDB persistence directory")
    chroma_collection_name: str = Field(default="khazanah_annual_review", description="ChromaDB collection name")

    # ── Ingestion ─────────────────────────────────────────────────
    chunk_size: int = Field(default=600, description="Target chunk size in tokens")
    chunk_overlap: int = Field(default=100, description="Overlap between chunks in tokens")
    data_dir: str = Field(default="app/data", description="Directory containing source PDFs")
    extracted_dir: str = Field(default="app/data/extracted", description="Directory for extracted JSON")

    # ── RAG ────────────────────────────────────────────────────────
    rag_top_k: int = Field(default=6, description="Number of chunks to retrieve")
    rag_similarity_threshold: float = Field(default=0.3, description="Minimum similarity score")

    # ── API ────────────────────────────────────────────────────────
    api_host: str = Field(default="0.0.0.0", description="API host")
    api_port: int = Field(default=8000, description="API port")

    # ── Cache ──────────────────────────────────────────────────────
    cache_enabled: bool = Field(default=True, description="Enable query caching")
    cache_max_size: int = Field(default=100, description="Max cache entries")
    cache_similarity_threshold: float = Field(default=0.95, description="Semantic cache match threshold")

    @property
    def data_path(self) -> Path:
        return Path(self.data_dir)

    @property
    def extracted_path(self) -> Path:
        return Path(self.extracted_dir)

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


@lru_cache()
def get_settings() -> Settings:
    """Return cached singleton settings instance."""
    return Settings()
