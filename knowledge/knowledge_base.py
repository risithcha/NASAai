"""
Vector knowledge base: embeds document chunks with OpenAI, indexes with FAISS,
and provides similarity search.  Indexes both the PDF portfolio and CSV datasets.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import time

import faiss
import numpy as np
from openai import OpenAI

import config
from knowledge.pdf_parser import TextChunk, parse_pdf
from knowledge.csv_parser import parse_csv

log = logging.getLogger(__name__)

METADATA_FILE = "chunks_meta.json"
INDEX_FILE = "index.faiss"


class KnowledgeBase:
    """
    Build or load a FAISS index over document chunks.  Provides
    `search(query, k)` → list of (TextChunk, score).
    """

    def __init__(self) -> None:
        self._client = OpenAI(api_key=config.OPENAI_API_KEY)
        self._index: faiss.IndexFlatL2 | None = None
        self._chunks: list[TextChunk] = []

    # ── build / load ──────────────────────────────────────────────────

    def build(self, pdf_path: Path | None = None) -> None:
        """Parse PDF and CSV datasets, embed all chunks, and persist the FAISS index."""
        self._chunks = parse_pdf(pdf_path)

        # Also index CSV datasets from the context directory
        csv_dir = config.CSV_DIR
        if csv_dir.exists():
            for csv_file in sorted(csv_dir.glob("*.csv")):
                try:
                    csv_chunks = parse_csv(csv_file)
                    # Re-number chunk indices to continue from PDF chunks
                    offset = len(self._chunks)
                    for i, chunk in enumerate(csv_chunks):
                        chunk.chunk_index = offset + i
                    self._chunks.extend(csv_chunks)
                    log.info("Added %d chunks from %s", len(csv_chunks), csv_file.name)
                except Exception:
                    log.warning("Failed to parse CSV %s", csv_file, exc_info=True)

        embeddings = self._embed_texts([c.text for c in self._chunks])
        dim = embeddings.shape[1]

        self._index = faiss.IndexFlatL2(dim)
        self._index.add(embeddings)

        self._save(config.FAISS_INDEX_DIR)
        log.info("Knowledge base built: %d chunks, dim=%d", len(self._chunks), dim)

    def load(self, index_dir: Path | None = None) -> bool:
        """Load a previously-persisted index.  Returns True on success."""
        index_dir = index_dir or config.FAISS_INDEX_DIR
        idx_path = index_dir / INDEX_FILE
        meta_path = index_dir / METADATA_FILE

        if not idx_path.exists() or not meta_path.exists():
            return False

        self._index = faiss.read_index(str(idx_path))
        with open(meta_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        self._chunks = [TextChunk(**item) for item in raw]
        log.info("Knowledge base loaded: %d chunks", len(self._chunks))
        return True

    def ensure_ready(self, pdf_path: Path | None = None) -> None:
        """Load existing index or build a fresh one."""
        if not self.load():
            log.info("No existing index found – building from PDF …")
            self.build(pdf_path)

    # ── search ────────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        k: int = config.SIMILARITY_TOP_K,
    ) -> list[tuple[TextChunk, float]]:
        """
        Return the top-*k* chunks most similar to *query*.
        Each result is (TextChunk, L2_distance).  Lower = more similar.
        """
        if self._index is None or not self._chunks:
            return []

        q_emb = self._embed_texts([query])
        distances, indices = self._index.search(q_emb, k)

        results: list[tuple[TextChunk, float]] = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx < 0 or idx >= len(self._chunks):
                continue
            results.append((self._chunks[idx], float(dist)))
        return results

    # ── embeddings ────────────────────────────────────────────────────

    @staticmethod
    def _build_token_batches(
        texts: list[str],
        max_tokens: int = 250_000,
    ) -> list[list[str]]:
        """Split *texts* into batches that each stay under *max_tokens*.

        Uses tiktoken to estimate per-text token counts so we never exceed
        the OpenAI embeddings API limit (300 000 tokens per request; we use
        250 000 as a safety margin).
        """
        import tiktoken

        enc = tiktoken.get_encoding("cl100k_base")

        batches: list[list[str]] = []
        current_batch: list[str] = []
        current_tokens = 0

        for text in texts:
            tok_count = len(enc.encode(text))
            # If adding this text would exceed the limit, flush current batch
            if current_batch and current_tokens + tok_count > max_tokens:
                batches.append(current_batch)
                current_batch = []
                current_tokens = 0
            current_batch.append(text)
            current_tokens += tok_count

        if current_batch:
            batches.append(current_batch)

        return batches

    def _embed_texts(self, texts: list[str]) -> np.ndarray:
        """Call OpenAI embeddings and return an (N, dim) float32 array."""
        from openai import RateLimitError, APIError

        all_vecs: list[list[float]] = []
        max_retries = 5

        batches = self._build_token_batches(texts)
        log.info("Embedding %d texts in %d batch(es)", len(texts), len(batches))

        for batch in batches:
            for attempt in range(max_retries):
                try:
                    resp = self._client.embeddings.create(
                        model=config.EMBEDDING_MODEL,
                        input=batch,
                    )
                    for item in resp.data:
                        all_vecs.append(item.embedding)
                    break  # success
                except RateLimitError as exc:
                    # Distinguish transient rate-limit from hard quota error
                    err_body = getattr(exc, "body", {}) or {}
                    err_obj = err_body.get("error", {}) if isinstance(err_body, dict) else {}
                    code = err_obj.get("code", "")

                    if code == "insufficient_quota":
                        log.error(
                            "\n╔══════════════════════════════════════════════════╗\n"
                            "║  OpenAI quota exhausted — no credits remaining.  ║\n"
                            "║                                                  ║\n"
                            "║  1. Go to platform.openai.com/account/billing    ║\n"
                            "║  2. Add credits ($5 is more than enough)         ║\n"
                            "║  3. Re-run: python main.py                       ║\n"
                            "╚══════════════════════════════════════════════════╝"
                        )
                        raise SystemExit(1) from exc

                    # Transient 429 — exponential backoff
                    wait = min(2 ** attempt, 60)
                    log.warning(
                        "Rate-limited (attempt %d/%d). Retrying in %ds …",
                        attempt + 1, max_retries, wait,
                    )
                    time.sleep(wait)
                except APIError:
                    log.exception("OpenAI API error during embedding")
                    raise
            else:
                raise RuntimeError(
                    f"Failed to embed batch after {max_retries} retries"
                )

        return np.array(all_vecs, dtype=np.float32)

    # ── persistence ───────────────────────────────────────────────────

    def _save(self, index_dir: Path) -> None:
        index_dir.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self._index, str(index_dir / INDEX_FILE))
        meta = [
            {
                "text": c.text,
                "page": c.page,
                "section": c.section,
                "chunk_index": c.chunk_index,
            }
            for c in self._chunks
        ]
        with open(index_dir / METADATA_FILE, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False)
