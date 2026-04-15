"""
Parse CSV dataset files into text chunks for the knowledge base.

Reads each CSV, converts rows into readable text, and produces
TextChunk objects compatible with the existing knowledge base pipeline.
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path

from knowledge.pdf_parser import TextChunk

log = logging.getLogger(__name__)


def parse_csv(csv_path: Path, chunk_rows: int = 30) -> list[TextChunk]:
    """
    Read a CSV file and split it into chunks of *chunk_rows* rows each.
    Returns a list of TextChunk objects.
    """
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    with open(csv_path, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f)
        rows = list(reader)

    if not rows:
        log.warning("Empty CSV: %s", csv_path)
        return []

    header = rows[0]
    data_rows = rows[1:]
    filename = csv_path.stem

    chunks: list[TextChunk] = []
    idx = 0

    for start in range(0, len(data_rows), chunk_rows):
        batch = data_rows[start : start + chunk_rows]
        lines = [f"Dataset: {filename}"]
        lines.append(f"Columns: {', '.join(header)}")
        lines.append(f"Rows {start + 1}–{start + len(batch)} of {len(data_rows)}:")
        lines.append("")
        for row in batch:
            row_text = " | ".join(
                f"{header[i]}: {row[i]}" if i < len(header) else row[i]
                for i in range(len(row))
            )
            lines.append(row_text)

        chunks.append(TextChunk(
            text="\n".join(lines),
            page=0,  # CSVs don't have pages
            section=f"Dataset: {filename}",
            chunk_index=idx,
        ))
        idx += 1

    log.info("Parsed CSV %s → %d chunks (%d data rows)", csv_path.name, len(chunks), len(data_rows))
    return chunks
