"""
Vector knowledge base: embeds document chunks with OpenAI, indexes with FAISS,
and provides similarity search.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import faiss
import numpy as np
from openai import OpenAI

import config
from knowledge.pdf_parser import TextChunk, parse_pdf

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
        """Parse PDF, embed all chunks, and persist the FAISS index."""
        self._chunks = parse_pdf(pdf_path)
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

    def _embed_texts(self, texts: list[str]) -> np.ndarray:
        """Call OpenAI embeddings and return an (N, dim) float32 array."""
        # OpenAI allows up to 2048 inputs per call; batch if needed
        all_vecs: list[list[float]] = []
        batch_size = 512
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            resp = self._client.embeddings.create(
                model=config.EMBEDDING_MODEL,
                input=batch,
            )
            for item in resp.data:
                all_vecs.append(item.embedding)
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
