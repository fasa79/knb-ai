"""Ingestion pipeline — orchestrates the full flow: parse → chunk → embed → store.

This is the main entry point for processing PDFs into searchable vector embeddings.
Handles any PDF dynamically — not hardcoded to a specific document structure.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings
from app.core.pdf_parser import PDFParser, ParsedDocument
from app.core.embeddings import get_embedding_service
from app.core.vector_store import get_vector_store
from app.ingestion.chunker import HybridChunker, Chunk

logger = logging.getLogger(__name__)


@dataclass
class IngestionResult:
    """Summary of an ingestion run."""

    filename: str
    total_pages: int
    total_chunks: int
    total_tables: int
    total_images: int
    duration_seconds: float
    status: str = "success"
    error: str | None = None


@dataclass
class PipelineResult:
    """Summary of the full pipeline run across all documents."""

    documents: list[IngestionResult]
    total_chunks_stored: int
    total_duration_seconds: float

    @property
    def summary(self) -> dict:
        return {
            "documents_processed": len(self.documents),
            "total_chunks_stored": self.total_chunks_stored,
            "total_duration_seconds": round(self.total_duration_seconds, 2),
            "details": [
                {
                    "filename": d.filename,
                    "pages": d.total_pages,
                    "chunks": d.total_chunks,
                    "tables": d.total_tables,
                    "images": d.total_images,
                    "duration_s": round(d.duration_seconds, 2),
                    "status": d.status,
                    "error": d.error,
                }
                for d in self.documents
            ],
        }


class IngestionPipeline:
    """End-to-end pipeline: PDF → parse → chunk → embed → vector store."""

    def __init__(
        self,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
        extract_images: bool = True,
        use_vision: bool = False,
        vision_model: str | None = None,
    ):
        settings = get_settings()
        self.chunk_size = chunk_size or settings.chunk_size
        self.chunk_overlap = chunk_overlap or settings.chunk_overlap
        self.data_dir = settings.data_path
        self.use_vision = use_vision
        self.vision_model = vision_model

        self.parser = PDFParser(extract_images=extract_images)
        self.embedding_service = get_embedding_service()
        self.vector_store = get_vector_store()
        self.chunker = HybridChunker(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            embedding_service=self.embedding_service,
        )

    def run(self, clear_existing: bool = False) -> PipelineResult:
        """Run the full ingestion pipeline on all PDFs in the data directory.

        Args:
            clear_existing: If True, wipe the vector store before ingesting.

        Returns:
            PipelineResult with details on each document processed.
        """
        start_time = time.time()

        if clear_existing:
            logger.info("Clearing existing vector store...")
            try:
                self.vector_store.clear()
            except Exception as e:
                logger.warning(f"Could not clear vector store: {e}")

        # Find all PDFs
        pdf_files = sorted(self.data_dir.glob("*.pdf"))
        if not pdf_files:
            logger.warning(f"No PDF files found in {self.data_dir}")
            return PipelineResult(documents=[], total_chunks_stored=0, total_duration_seconds=0)

        logger.info(f"Found {len(pdf_files)} PDF files in {self.data_dir}")

        results: list[IngestionResult] = []
        total_chunks = 0

        for pdf_path in pdf_files:
            result = self._process_single_pdf(pdf_path)
            results.append(result)
            if result.status == "success":
                total_chunks += result.total_chunks

        total_duration = time.time() - start_time
        logger.info(
            f"Pipeline complete: {len(results)} documents, "
            f"{total_chunks} chunks stored in {total_duration:.1f}s"
        )

        return PipelineResult(
            documents=results,
            total_chunks_stored=total_chunks,
            total_duration_seconds=total_duration,
        )

    def ingest_single(self, pdf_path: str | Path, clear_existing: bool = False) -> IngestionResult:
        """Ingest a single PDF file."""
        if clear_existing:
            try:
                self.vector_store.clear()
            except Exception:
                pass
        return self._process_single_pdf(Path(pdf_path))

    def _process_single_pdf(self, pdf_path: Path) -> IngestionResult:
        """Process a single PDF through the full pipeline."""
        start_time = time.time()
        logger.info(f"Processing: {pdf_path.name}")

        try:
            # Step 1: Parse PDF
            logger.info(f"  [1/4] Parsing {pdf_path.name}...")
            document = self.parser.parse(pdf_path)
            total_tables = sum(len(p.tables) for p in document.pages)
            total_images = sum(len(p.images) for p in document.pages)
            logger.info(
                f"  Parsed: {document.total_pages} pages, "
                f"{total_tables} tables, {total_images} images"
            )

            # Step 2: Chunk
            logger.info(f"  [2/4] Chunking {pdf_path.name}...")
            chunks = self.chunker.chunk_document(document)
            logger.info(f"  Created {len(chunks)} chunks")

            # Step 2b: Vision — describe chart/graph images and add as chunks
            if self.use_vision and total_images > 0:
                logger.info(f"  [2b] Analyzing {total_images} images with vision model...")
                vision_chunks = self._process_images_with_vision(document, model_override=self.vision_model)
                if vision_chunks:
                    chunks.extend(vision_chunks)
                    logger.info(f"  Added {len(vision_chunks)} image description chunks (total: {len(chunks)})")

            if not chunks:
                logger.warning(f"  No chunks produced for {pdf_path.name}")
                return IngestionResult(
                    filename=pdf_path.name,
                    total_pages=document.total_pages,
                    total_chunks=0,
                    total_tables=total_tables,
                    total_images=total_images,
                    duration_seconds=time.time() - start_time,
                    status="warning",
                    error="No chunks produced",
                )

            # Step 3: Generate embeddings
            logger.info(f"  [3/4] Generating embeddings for {len(chunks)} chunks...")
            texts = [c.text for c in chunks]
            embeddings = self.embedding_service.embed_texts(texts, show_progress=True)
            logger.info(f"  Generated {len(embeddings)} embeddings (dim={len(embeddings[0])})")

            # Step 4: Store in vector database
            logger.info(f"  [4/4] Storing in vector database...")
            ids = [c.id for c in chunks]
            metadatas = [c.metadata for c in chunks]
            self.vector_store.add_documents(
                ids=ids,
                texts=texts,
                embeddings=embeddings,
                metadatas=metadatas,
            )

            duration = time.time() - start_time
            logger.info(f"  Done: {pdf_path.name} in {duration:.1f}s")

            return IngestionResult(
                filename=pdf_path.name,
                total_pages=document.total_pages,
                total_chunks=len(chunks),
                total_tables=total_tables,
                total_images=total_images,
                duration_seconds=duration,
            )

        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"  Failed: {pdf_path.name} — {e}")
            return IngestionResult(
                filename=pdf_path.name,
                total_pages=0,
                total_chunks=0,
                total_tables=0,
                total_images=0,
                duration_seconds=duration,
                status="error",
                error=str(e),
            )

    def get_status(self) -> dict:
        """Return current vector store status with per-file chunk counts."""
        count = self.vector_store.count()
        pdf_files = [f.name for f in sorted(self.data_dir.glob("*.pdf"))]
        chunks_by_source = self.vector_store.count_by_source()

        file_status = []
        for filename in pdf_files:
            chunks = chunks_by_source.get(filename, 0)
            file_status.append({
                "filename": filename,
                "chunks": chunks,
                "ingested": chunks > 0,
            })

        return {
            "chunks_stored": count,
            "data_dir": str(self.data_dir),
            "pdf_files": pdf_files,
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
            "file_status": file_status,
        }

    def _process_images_with_vision(
        self,
        document: ParsedDocument,
        min_size_kb: int = 30,
        max_size_kb: int = 1000,
        model_override: str | None = None,
    ) -> list[Chunk]:
        """Use vision model to describe images and create searchable chunks.

        Filters images by size to skip tiny icons/logos (< min_size_kb)
        and full-page backgrounds (> max_size_kb).
        """
        from app.core.vision_parser import describe_images_batch

        # Collect significant images — skip tiny icons and huge backgrounds
        images = []
        skipped = 0
        for page in document.pages:
            for img_bytes in page.images:
                size_kb = len(img_bytes) // 1024
                if min_size_kb <= size_kb <= max_size_kb:
                    images.append((img_bytes, page.page_number, document.filename))
                else:
                    skipped += 1

        if skipped:
            logger.info(f"  Filtered {skipped} images by size, {len(images)} candidates remain")

        if not images:
            return []

        # Run vision analysis (async → sync bridge via thread to avoid loop conflicts)
        import concurrent.futures
        def _run_vision():
            return asyncio.run(describe_images_batch(images, model_override=model_override))

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            descriptions = pool.submit(_run_vision).result()

        # Convert descriptions to Chunk objects
        chunks = []
        for i, desc in enumerate(descriptions):
            chunk_id = f"{document.filename}_img_p{desc['page']}_{i}"
            text = f"[Image/Chart from page {desc['page']}]\n{desc['description']}"
            chunks.append(
                Chunk(
                    id=chunk_id,
                    text=text,
                    metadata={
                        "source": document.filename,
                        "page": desc["page"],
                        "section": "",
                        "content_type": "image_description",
                    },
                )
            )

        return chunks
