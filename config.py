"""
Central configuration for the Data Science Presentation Assistant.
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
CONTEXT_DIR = BASE_DIR / "datasciencecontext"
PDF_PATH = CONTEXT_DIR / "DSAHS-21361-1_Data_Science_Portfolio (1).pdf"
CSV_DIR = CONTEXT_DIR                       # CSVs live alongside the PDF
PROFILES_PATH = DATA_DIR / "dsai_user_profiles.md"

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
BULLETS_MODEL = "gpt-4o-mini"         # cheaper model for bullet summaries
BULLETS_MAX_TOKENS = 256
QUESTION_DEBOUNCE_SEC = 3.0         # group rapid-fire questions (was 5.0 — reduced for follow-ups)
QA_HISTORY_DEPTH = 3                # prior Q&A pairs passed to LLM for continuity
ROUTING_MODEL = "gpt-4o-mini"       # model for semantic question routing

# ── Logging ───────────────────────────────────────────────────────────
LOG_FILE = BASE_DIR / "dsai_debug.log"

# ── UI ────────────────────────────────────────────────────────────────
OVERLAY_WIDTH = 480
OVERLAY_HEIGHT = 700
OVERLAY_OPACITY = 0.92


# ── Settings → Config bridge ─────────────────────────────────────────
def load_from_settings() -> None:
    """Override module-level constants from the persisted settings.json."""
    from settings.settings_manager import settings as sm

    g = globals()

    _MAP = {
        "general.deepgram_api_key":       "DEEPGRAM_API_KEY",
        "general.openai_api_key":         "OPENAI_API_KEY",
        "general.pdf_path":              None,  # handled separately
        "general.log_level":             None,
        "general.debug_log_file":        None,
        "general.debounce_sec":          "QUESTION_DEBOUNCE_SEC",
        "general.qa_history_depth":      "QA_HISTORY_DEPTH",
        "audio.sample_rate":             "AUDIO_SAMPLE_RATE",
        "audio.chunk_ms":                "AUDIO_CHUNK_MS",
        "transcription.model":           "DG_MODEL",
        "transcription.language":        "DG_LANGUAGE",
        "transcription.diarize":         "DG_DIARIZE",
        "transcription.smart_format":    "DG_SMART_FORMAT",
        "transcription.endpointing_ms":  "DG_ENDPOINTING_MS",
        "transcription.utterance_end_ms":"DG_UTTERANCE_END_MS",
        "intelligence.response_model":   "RESPONSE_MODEL",
        "intelligence.response_max_tokens":"RESPONSE_MAX_TOKENS",
        "intelligence.detection_model":  "QUESTION_DETECT_MODEL",
        "intelligence.routing_model":    "ROUTING_MODEL",
        "intelligence.bullets_model":    "BULLETS_MODEL",
        "intelligence.bullets_max_tokens":"BULLETS_MAX_TOKENS",
        "intelligence.min_words":        None,
        "intelligence.regex_min_words":  None,
        "intelligence.similarity_top_k": "SIMILARITY_TOP_K",
        "intelligence.similarity_threshold":"SIMILARITY_THRESHOLD",
        "appearance.width":              "OVERLAY_WIDTH",
        "appearance.height":             "OVERLAY_HEIGHT",
        "appearance.opacity":            "OVERLAY_OPACITY",
    }

    for skey, const_name in _MAP.items():
        if const_name is None:
            continue
        val = sm.get(skey)
        if val is not None and val != "":
            g[const_name] = val

    # PDF path override
    pdf = sm.get("general.pdf_path")
    if pdf:
        g["PDF_PATH"] = Path(pdf)

    # Recompute derived audio constant
    g["AUDIO_CHUNK_SAMPLES"] = int(g["AUDIO_SAMPLE_RATE"] * g["AUDIO_CHUNK_MS"] / 1000)
