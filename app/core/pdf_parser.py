"""PDF parsing service — extracts text, tables, and images from PDF documents.

Uses PyMuPDF (fitz) for text/layout/image extraction and pdfplumber for table detection.
Handles complex annual report layouts: multi-column, tables, charts, footnotes.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF
import pdfplumber
from PIL import Image

logger = logging.getLogger(__name__)


@dataclass
class TableData:
    """Extracted table with metadata."""

    headers: list[str]
    rows: list[list[str]]
    page_number: int
    bbox: tuple[float, float, float, float] | None = None

    def to_markdown(self) -> str:
        """Convert table to markdown format for embedding."""
        if not self.headers and not self.rows:
            return ""

        lines = []
        if self.headers:
            lines.append("| " + " | ".join(self.headers) + " |")
            lines.append("| " + " | ".join(["---"] * len(self.headers)) + " |")

        for row in self.rows:
            # Pad row to match header length
            padded = row + [""] * (len(self.headers) - len(row)) if self.headers else row
            lines.append("| " + " | ".join(str(c) for c in padded) + " |")

        return "\n".join(lines)


@dataclass
class PageContent:
    """Extracted content from a single PDF page."""

    page_number: int  # 1-indexed
    text: str
    tables: list[TableData] = field(default_factory=list)
    images: list[bytes] = field(default_factory=list)  # Raw image bytes (PNG)
    image_descriptions: list[str] = field(default_factory=list)


@dataclass
class ParsedDocument:
    """Full parsed PDF document."""

    filename: str
    total_pages: int
    pages: list[PageContent]
    metadata: dict[str, Any] = field(default_factory=dict)


class PDFParser:
    """Multi-strategy PDF parser combining PyMuPDF and pdfplumber."""

    def __init__(self, extract_images: bool = True, min_image_size: int = 100):
        """
        Args:
            extract_images: Whether to extract images (for multi-modal analysis).
            min_image_size: Minimum image dimension (px) to extract (skip tiny icons).
        """
        self.extract_images = extract_images
        self.min_image_size = min_image_size

    def parse(self, pdf_path: str | Path) -> ParsedDocument:
        """Parse a PDF file and extract all content."""
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        logger.info(f"Parsing PDF: {pdf_path.name}")

        pages: list[PageContent] = []

        # Use PyMuPDF for text and images
        fitz_doc = fitz.open(str(pdf_path))
        total_pages = len(fitz_doc)

        # Use pdfplumber for tables
        plumber_pdf = pdfplumber.open(str(pdf_path))

        for page_idx in range(total_pages):
            page_num = page_idx + 1

            # Extract text via PyMuPDF (better layout preservation)
            fitz_page = fitz_doc[page_idx]
            text = self._extract_text(fitz_page)

            # Extract tables via pdfplumber (better table detection)
            tables = self._extract_tables(plumber_pdf.pages[page_idx], page_num) if page_idx < len(plumber_pdf.pages) else []

            # Extract images via PyMuPDF
            images = self._extract_images(fitz_page) if self.extract_images else []

            pages.append(
                PageContent(
                    page_number=page_num,
                    text=text,
                    tables=tables,
                    images=images,
                )
            )

        fitz_doc.close()
        plumber_pdf.close()

        logger.info(
            f"Parsed {pdf_path.name}: {total_pages} pages, "
            f"{sum(len(p.tables) for p in pages)} tables, "
            f"{sum(len(p.images) for p in pages)} images"
        )

        return ParsedDocument(
            filename=pdf_path.name,
            total_pages=total_pages,
            pages=pages,
            metadata={"source": str(pdf_path)},
        )

    def _extract_text(self, page: fitz.Page) -> str:
        """Extract text from a PyMuPDF page preserving layout."""
        # Use "text" extraction for clean text; "blocks" for layout-aware
        text = page.get_text("text")
        # Clean up excessive whitespace while preserving paragraph breaks
        lines = text.split("\n")
        cleaned = []
        for line in lines:
            stripped = line.strip()
            if stripped:
                cleaned.append(stripped)
            elif cleaned and cleaned[-1] != "":
                cleaned.append("")
        return "\n".join(cleaned)

    def _extract_tables(self, page: pdfplumber.page.Page, page_number: int) -> list[TableData]:
        """Extract tables from a pdfplumber page."""
        tables = []
        try:
            extracted = page.extract_tables(
                table_settings={
                    "vertical_strategy": "lines",
                    "horizontal_strategy": "lines",
                    "snap_tolerance": 5,
                }
            )
            for table in extracted:
                if not table or len(table) < 2:
                    continue

                # First row as headers, rest as data
                headers = [str(cell).strip() if cell else "" for cell in table[0]]
                rows = []
                for row in table[1:]:
                    cleaned_row = [str(cell).strip() if cell else "" for cell in row]
                    if any(cleaned_row):  # Skip empty rows
                        rows.append(cleaned_row)

                if headers or rows:
                    tables.append(
                        TableData(
                            headers=headers,
                            rows=rows,
                            page_number=page_number,
                        )
                    )
        except Exception as e:
            logger.warning(f"Table extraction failed on page {page_number}: {e}")

        return tables

    def _extract_images(self, page: fitz.Page) -> list[bytes]:
        """Extract significant images from a PyMuPDF page."""
        images = []
        try:
            for img_info in page.get_images(full=True):
                xref = img_info[0]
                base_image = page.parent.extract_image(xref)
                if base_image:
                    width = base_image.get("width", 0)
                    height = base_image.get("height", 0)

                    # Skip small images (icons, bullets, etc.)
                    if width >= self.min_image_size and height >= self.min_image_size:
                        image_bytes = base_image["image"]

                        # Convert to PNG if needed
                        try:
                            img = Image.open(io.BytesIO(image_bytes))
                            png_buffer = io.BytesIO()
                            img.save(png_buffer, format="PNG")
                            images.append(png_buffer.getvalue())
                        except Exception:
                            images.append(image_bytes)
        except Exception as e:
            logger.warning(f"Image extraction failed on page {page.number + 1}: {e}")

        return images

    def parse_directory(self, directory: str | Path) -> list[ParsedDocument]:
        """Parse all PDF files in a directory."""
        directory = Path(directory)
        pdf_files = sorted(directory.glob("*.pdf"))

        if not pdf_files:
            logger.warning(f"No PDF files found in: {directory}")
            return []

        documents = []
        for pdf_path in pdf_files:
            try:
                doc = self.parse(pdf_path)
                documents.append(doc)
            except Exception as e:
                logger.error(f"Failed to parse {pdf_path.name}: {e}")

        return documents
