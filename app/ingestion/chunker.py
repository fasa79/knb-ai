"""Hybrid multi-strategy chunker — adapts to content instead of one-size-fits-all.

Architecture (3 layers):

  Layer 1 — Content-Type Router
    Detects block type (table, bullet list, financial figure, narrative)
    and applies the right chunking strategy per type.

  Layer 2 — Embedding-Based Semantic Splitting
    For narrative text: compute sentence embeddings, find cosine similarity
    drops between consecutive sentences → split at natural topic boundaries.
    Data-driven, not regex-driven. Works regardless of PDF formatting.

  Layer 3 — Context Enrichment
    Prepends [Source | Page | Section] to each chunk before embedding,
    so the vector captures full context, not isolated text.

Trade-off: ~2x slower than naive regex chunking, but zero API calls
(embeddings are local) and significantly better retrieval quality.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from app.core.pdf_parser import ParsedDocument, PageContent, TableData

logger = logging.getLogger(__name__)


@dataclass
class Chunk:
    """A single chunk ready for embedding."""

    id: str
    text: str                                   # Context-enriched text (used for embedding)
    raw_text: str = ""                          # Original text without context prefix
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def token_estimate(self) -> int:
        """Rough token count (words * 1.3)."""
        return int(len(self.text.split()) * 1.3)


class HybridChunker:
    """3-layer hybrid chunker that adapts to content type.

    Layer 1 — Content-Type Router:
        Detects tables, bullet lists, financial snippets, narrative text.
        Each type gets the right chunking strategy.

    Layer 2 — Embedding-Based Semantic Splitting:
        For narrative text: compute sentence embeddings, find cosine similarity
        drops between consecutive sentences, split at topic boundaries.
        Fully local (sentence-transformers), zero API calls.

    Layer 3 — Context Enrichment:
        Prepends [Source | Page | Section] metadata to each chunk text
        so the embedding vector captures context, not just isolated words.
    """

    # ── Regex patterns ────────────────────────────────────────────

    HEADING_PATTERNS = [
        re.compile(r"^#{1,3}\s+.+", re.IGNORECASE),
        re.compile(r"^[A-Z][A-Z\s&,]{5,}$"),
        re.compile(r"^(?:Section|Chapter|Part)\s+\d+", re.IGNORECASE),
        re.compile(r"^\d+\.\s+[A-Z]"),
        re.compile(
            r"^(?:Overview|Introduction|Summary|Highlights|Performance|Portfolio|"
            r"Sustainability|ESG|Financial|Investment|Strategy|Governance|"
            r"Chairman|Managing Director|Key Metrics|Appendix|Notes)",
            re.IGNORECASE,
        ),
    ]

    BULLET_RE = re.compile(r"^\s*(?:[•●○▪▸►\-–—]|\d+[.)]\s|[a-z][.)]\s|[ivxIVX]+[.)]\s)", re.MULTILINE)
    FINANCIAL_RE = re.compile(r"(?:RM|USD|MYR|%|\$)\s*[\d,.]+|[\d,.]+\s*(?:billion|million|bn|mn|%)", re.IGNORECASE)

    NOISE_PATTERNS = [
        re.compile(r"^khazanah\s+nasional\s+berhad\s*©?\s*\d*\s*\|?\s*\d*$", re.IGNORECASE),
        re.compile(r"^\d+$"),
        re.compile(r"^©\s*\d{4}", re.IGNORECASE),
        re.compile(r"^page\s+\d+\s*(of\s+\d+)?$", re.IGNORECASE),
        re.compile(r"^khazanah annual review\s*\d*$", re.IGNORECASE),
    ]

    # ── Init ──────────────────────────────────────────────────────

    def __init__(
        self,
        chunk_size: int = 600,
        chunk_overlap: int = 100,
        similarity_threshold: float = 0.5,
        embedding_service=None,
    ):
        """
        Args:
            chunk_size: Target max chunk size in tokens.
            chunk_overlap: Overlap tokens between consecutive chunks.
            similarity_threshold: Cosine similarity drop threshold for splitting.
                Lower = more aggressive splitting. 0.5 is a balanced default.
            embedding_service: Injected EmbeddingService (avoids circular import).
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.similarity_threshold = similarity_threshold
        self._embedding_service = embedding_service

    @property
    def embedding_service(self):
        if self._embedding_service is None:
            from app.core.embeddings import get_embedding_service
            self._embedding_service = get_embedding_service()
        return self._embedding_service

    # ── Main entry point ──────────────────────────────────────────

    def chunk_document(self, document: ParsedDocument) -> list[Chunk]:
        """Chunk an entire parsed document using the hybrid strategy."""
        all_chunks: list[Chunk] = []

        for page in document.pages:
            page_chunks = self._process_page(page, document.filename)
            all_chunks.extend(page_chunks)

        # Deduplicate and filter noise
        deduped = self._deduplicate(all_chunks)

        logger.info(
            f"Chunked {document.filename}: {len(deduped)} chunks "
            f"(from {document.total_pages} pages, raw={len(all_chunks)})"
        )
        return deduped

    # ── Layer 1: Content-Type Router ──────────────────────────────

    def _process_page(self, page: PageContent, filename: str) -> list[Chunk]:
        """Route each content block to the right chunking strategy."""
        chunks: list[Chunk] = []
        section = self._detect_section(page.text)

        # Tables → standalone chunks (atomic, never split)
        for i, table in enumerate(page.tables):
            table_md = table.to_markdown()
            if table_md.strip() and len(table_md.strip()) > 30:
                chunks.append(self._make_chunk(
                    raw_text=table_md,
                    filename=filename,
                    page=page.page_number,
                    section=section,
                    content_type="table",
                    index=f"table_{i}",
                ))

        # Text → classify and route
        if page.text.strip():
            text_blocks = self._split_into_blocks(page.text)
            for i, block in enumerate(text_blocks):
                block_type = self._classify_block(block)

                if block_type == "bullet_list":
                    # Keep the entire list as one chunk
                    chunks.append(self._make_chunk(
                        raw_text=block,
                        filename=filename,
                        page=page.page_number,
                        section=section,
                        content_type="list",
                        index=f"list_{i}",
                    ))
                elif block_type == "financial":
                    # Financial figures — keep with surrounding context
                    chunks.append(self._make_chunk(
                        raw_text=block,
                        filename=filename,
                        page=page.page_number,
                        section=section,
                        content_type="financial",
                        index=f"fin_{i}",
                    ))
                else:
                    # Narrative text → Layer 2 (embedding-based splitting)
                    narrative_chunks = self._split_narrative_by_embeddings(
                        block, filename, page.page_number, section, i,
                    )
                    chunks.extend(narrative_chunks)

        return chunks

    def _classify_block(self, text: str) -> str:
        """Classify a text block by content type."""
        lines = text.strip().split("\n")
        non_empty = [l.strip() for l in lines if l.strip()]
        if not non_empty:
            return "narrative"

        # Bullet list: >50% of lines start with bullet markers
        bullet_count = sum(1 for l in non_empty if self.BULLET_RE.match(l))
        if bullet_count > len(non_empty) * 0.5 and bullet_count >= 2:
            return "bullet_list"

        # Financial: contains multiple financial figures
        fin_matches = self.FINANCIAL_RE.findall(text)
        if len(fin_matches) >= 2:
            return "financial"

        return "narrative"

    def _split_into_blocks(self, text: str) -> list[str]:
        """Split page text into blocks separated by double newlines or heading changes."""
        lines = text.split("\n")
        blocks: list[str] = []
        current: list[str] = []

        for line in lines:
            stripped = line.strip()
            # Heading = boundary
            if self._is_heading(stripped) and current:
                blocks.append("\n".join(current))
                current = [line]
            # Empty line after content = potential boundary
            elif not stripped and current and any(l.strip() for l in current):
                # Only split if current block has some substance
                joined = "\n".join(current)
                if self._estimate_tokens(joined) > 20:
                    blocks.append(joined)
                    current = []
                else:
                    current.append(line)
            else:
                current.append(line)

        if current:
            blocks.append("\n".join(current))

        # Merge consecutive tiny blocks
        merged: list[str] = []
        buffer: list[str] = []
        buffer_tokens = 0
        for block in blocks:
            block_tokens = self._estimate_tokens(block)
            if block_tokens < 30 and buffer_tokens + block_tokens < self.chunk_size:
                buffer.append(block)
                buffer_tokens += block_tokens
            else:
                if buffer:
                    merged.append("\n\n".join(buffer))
                    buffer = []
                    buffer_tokens = 0
                if block_tokens < 30:
                    buffer.append(block)
                    buffer_tokens = block_tokens
                else:
                    merged.append(block)
        if buffer:
            merged.append("\n\n".join(buffer))

        return [b for b in merged if b.strip()]

    # ── Layer 2: Embedding-Based Semantic Splitting ───────────────

    def _split_narrative_by_embeddings(
        self, text: str, filename: str, page: int, section: str, block_idx: int,
    ) -> list[Chunk]:
        """Split narrative text at natural topic boundaries using embedding similarity.

        How it works:
        1. Split into sentences
        2. Embed each sentence (local, no API)
        3. Compute cosine similarity between consecutive sentences
        4. Where similarity drops below threshold → topic boundary → split
        5. Respect chunk_size limits even if no boundary detected
        """
        sentences = self._split_to_sentences(text)

        if not sentences:
            return []

        # If the whole block fits in one chunk, just return it
        if self._estimate_tokens(text) <= self.chunk_size:
            return [self._make_chunk(
                raw_text=text.strip(),
                filename=filename,
                page=page,
                section=section,
                content_type="text",
                index=f"text_{block_idx}_0",
            )]

        # Embed all sentences at once (batched, fast)
        embeddings = self.embedding_service.embed_texts(sentences)

        # Find semantic boundaries: where similarity drops
        boundaries = self._find_semantic_boundaries(embeddings)

        # Build chunks from sentence groups
        chunks: list[Chunk] = []
        current_sentences: list[str] = []
        current_tokens = 0

        for i, sent in enumerate(sentences):
            sent_tokens = self._estimate_tokens(sent)

            # Should we split here?
            should_split = (
                i in boundaries  # Semantic boundary detected
                or (current_tokens + sent_tokens > self.chunk_size and current_sentences)  # Size limit
            )

            if should_split and current_sentences:
                chunk_text = " ".join(current_sentences)
                chunks.append(self._make_chunk(
                    raw_text=chunk_text,
                    filename=filename,
                    page=page,
                    section=section,
                    content_type="text",
                    index=f"text_{block_idx}_{len(chunks)}",
                ))

                # Overlap: carry last 1-2 sentences if they fit
                overlap = self._get_overlap_sentences(current_sentences)
                current_sentences = overlap
                current_tokens = self._estimate_tokens(" ".join(overlap))

            current_sentences.append(sent)
            current_tokens += sent_tokens

        # Flush remaining
        if current_sentences:
            chunk_text = " ".join(current_sentences)
            if self._estimate_tokens(chunk_text) > 15:  # Skip tiny leftovers
                chunks.append(self._make_chunk(
                    raw_text=chunk_text,
                    filename=filename,
                    page=page,
                    section=section,
                    content_type="text",
                    index=f"text_{block_idx}_{len(chunks)}",
                ))

        return chunks

    def _find_semantic_boundaries(self, embeddings: list[list[float]]) -> set[int]:
        """Find indices where topic shifts occur based on embedding similarity drops."""
        if len(embeddings) < 3:
            return set()

        # Compute cosine similarities between consecutive sentences
        similarities = []
        for i in range(len(embeddings) - 1):
            a = np.array(embeddings[i])
            b = np.array(embeddings[i + 1])
            cos_sim = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))
            similarities.append(cos_sim)

        if not similarities:
            return set()

        # Find boundaries: where similarity is significantly below the local average
        mean_sim = np.mean(similarities)
        std_sim = np.std(similarities) if len(similarities) > 2 else 0.1

        boundaries: set[int] = set()
        for i, sim in enumerate(similarities):
            # Split if similarity drops below (mean - 0.5 * std) AND below absolute threshold
            if sim < mean_sim - 0.5 * std_sim and sim < self.similarity_threshold:
                boundaries.add(i + 1)  # Split BEFORE the next sentence

        return boundaries

    def _split_to_sentences(self, text: str) -> list[str]:
        """Split text into sentences, handling abbreviations and numbers."""
        # Split on sentence-ending punctuation followed by space + capital or newline
        raw = re.split(r"(?<=[.!?])\s+(?=[A-Z\"\'])|(?<=[.!?])\n+", text)
        sentences = []
        for s in raw:
            s = s.strip()
            if s and len(s) > 5:
                sentences.append(s)
        return sentences

    def _get_overlap_sentences(self, sentences: list[str]) -> list[str]:
        """Get overlap sentences from the end of a chunk."""
        if not sentences:
            return []
        # Take last sentence if it fits in overlap budget
        last = sentences[-1]
        if self._estimate_tokens(last) <= self.chunk_overlap:
            return [last]
        return []

    # ── Layer 3: Context Enrichment ───────────────────────────────

    def _make_chunk(
        self,
        raw_text: str,
        filename: str,
        page: int,
        section: str,
        content_type: str,
        index: str,
    ) -> Chunk:
        """Create chunk with context-enriched text for better embedding quality.

        The enriched text prepends metadata so the embedding captures:
        - What document this is from
        - What page/section
        - What type of content (table, list, financial, narrative)
        """
        raw_text = raw_text.strip()

        # Build context prefix
        parts = [f"Source: {filename}", f"Page {page}"]
        if section:
            parts.append(f"Section: {section}")
        parts.append(f"Type: {content_type}")
        context_prefix = " | ".join(parts)

        enriched_text = f"[{context_prefix}]\n{raw_text}"

        chunk_id = f"{filename}::p{page}::{index}"

        return Chunk(
            id=chunk_id,
            text=enriched_text,
            raw_text=raw_text,
            metadata={
                "source": filename,
                "page": page,
                "content_type": content_type,
                "section": section,
            },
        )

    # ── Utilities ─────────────────────────────────────────────────

    def _detect_section(self, text: str) -> str:
        """Detect section title from the first few lines of page text."""
        for line in text.split("\n")[:5]:
            stripped = line.strip()
            if self._is_heading(stripped):
                return stripped
        return ""

    def _is_heading(self, line: str) -> bool:
        """Detect if a line is a section heading."""
        if not line or len(line) > 120 or len(line) < 3:
            return False
        return any(p.match(line) for p in self.HEADING_PATTERNS)

    def _deduplicate(self, chunks: list[Chunk]) -> list[Chunk]:
        """Remove duplicate and noise chunks."""
        seen: set[str] = set()
        result: list[Chunk] = []
        for chunk in chunks:
            raw = chunk.raw_text.strip() if chunk.raw_text else chunk.text.strip()
            if len(raw) < 50:
                continue
            if self._is_noise(raw):
                continue
            h = hashlib.md5(raw.encode()).hexdigest()
            if h not in seen:
                seen.add(h)
                result.append(chunk)
        return result

    @classmethod
    def _is_noise(cls, text: str) -> bool:
        """Detect header/footer noise."""
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        if not lines:
            return True
        noise_count = sum(
            1 for line in lines
            if any(p.match(line) for p in cls.NOISE_PATTERNS)
        )
        return noise_count >= len(lines)

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Rough token estimate: words * 1.3."""
        return int(len(text.split()) * 1.3)


# Backwards compatibility alias
SemanticChunker = HybridChunker
