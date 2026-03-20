"""
Central configuration for the NASA AI Meeting Assistant.
Loads API keys from environment / .env and exposes tunable constants.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Paths ─────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
FAISS_INDEX_DIR = DATA_DIR / "faiss_index"
PDF_PATH = DATA_DIR / "nasa_report.pdf"
PROFILES_PATH = DATA_DIR / "NASAai_user_profiles.md"

# ── API Keys ──────────────────────────────────────────────────────────
DEEPGRAM_API_KEY: str = os.getenv("DEEPGRAM_API_KEY", "")
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

# ── Audio ─────────────────────────────────────────────────────────────
AUDIO_SAMPLE_RATE = 16_000          # Hz – Deepgram-friendly rate
AUDIO_CHANNELS = 1                  # mono per stream
AUDIO_CHUNK_MS = 100                # milliseconds per frame
AUDIO_CHUNK_SAMPLES = int(AUDIO_SAMPLE_RATE * AUDIO_CHUNK_MS / 1000)
AUDIO_FORMAT_WIDTH = 2              # 16-bit PCM = 2 bytes

# ── Deepgram ──────────────────────────────────────────────────────────
DG_MODEL = "nova-3"
DG_LANGUAGE = "en"
DG_SMART_FORMAT = True
DG_DIARIZE = True
DG_INTERIM_RESULTS = True
DG_UTTERANCE_END_MS = 1000
DG_ENDPOINTING_MS = 500

# ── RAG / Knowledge Base ─────────────────────────────────────────────
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536
CHUNK_SIZE_TOKENS = 500
CHUNK_OVERLAP_TOKENS = 100
SIMILARITY_TOP_K = 5
SIMILARITY_FETCH_K = 10              # over-fetch before per-user filtering
SIMILARITY_THRESHOLD = 0.35         # cosine distance (lower = more similar in FAISS L2)

# ── LLM ───────────────────────────────────────────────────────────────
QUESTION_DETECT_MODEL = "gpt-4o-mini"
RESPONSE_MODEL = "gpt-4o"
RESPONSE_MAX_TOKENS = 512
QUESTION_DEBOUNCE_SEC = 5.0         # group rapid-fire questions

# ── UI ────────────────────────────────────────────────────────────────
OVERLAY_WIDTH = 480
OVERLAY_HEIGHT = 700
OVERLAY_OPACITY = 0.92
