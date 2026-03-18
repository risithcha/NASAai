"""
Extract text from a PDF and split it into overlapping token-based chunks.
Uses PyMuPDF (fitz) for robust layout handling.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF
import tiktoken

import config

log = logging.getLogger(__name__)


@dataclass
class TextChunk:
    """A single chunk of document text with metadata."""
    text: str
    page: int               # 1-based page number
    section: str             # best-effort heading / section name
    chunk_index: int         # sequential chunk id


def extract_text_by_page(pdf_path: Path) -> list[tuple[int, str]]:
    """Return a list of (1-based page number, page text)."""
    doc = fitz.open(str(pdf_path))
    pages: list[tuple[int, str]] = []
    for i, page in enumerate(doc):
        text = page.get_text("text")
        if text.strip():
            pages.append((i + 1, text))
    doc.close()
    return pages


def _guess_section(text: str) -> str:
    """Return the first line that looks like a section heading."""
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        # Heuristic: short, title-cased or all-caps line
        if len(line) < 120 and (line.istitle() or line.isupper()):
            return line
        break
    return ""


def chunk_text(
    pages: list[tuple[int, str]],
    max_tokens: int = config.CHUNK_SIZE_TOKENS,
    overlap_tokens: int = config.CHUNK_OVERLAP_TOKENS,
) -> list[TextChunk]:
    """
    Split page texts into overlapping token-sized chunks.
    Preserves page numbers and best-effort section headings.
    """
    enc = tiktoken.encoding_for_model("gpt-4o")
    chunks: list[TextChunk] = []
    idx = 0

    for page_num, page_text in pages:
        section = _guess_section(page_text)
        tokens = enc.encode(page_text)

        start = 0
        while start < len(tokens):
            end = min(start + max_tokens, len(tokens))
            chunk_tokens = tokens[start:end]
            chunk_text_str = enc.decode(chunk_tokens)

            chunks.append(TextChunk(
                text=chunk_text_str.strip(),
                page=page_num,
                section=section,
                chunk_index=idx,
            ))
            idx += 1
            start += max_tokens - overlap_tokens

    log.info("Parsed %d pages → %d chunks", len(pages), len(chunks))
    return chunks


def parse_pdf(pdf_path: Path | None = None) -> list[TextChunk]:
    """High-level: parse the PDF at *pdf_path* (default: config) into chunks."""
    pdf_path = pdf_path or config.PDF_PATH
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    pages = extract_text_by_page(pdf_path)
    return chunk_text(pages)
