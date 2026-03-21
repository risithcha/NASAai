"""
Singleton settings manager backed by a JSON file.

Usage:
    from settings.settings_manager import settings
    val = settings.get("audio.sample_rate")
    settings.set("audio.sample_rate", 48000)
    settings.save()
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, Callable

import config as _config

log = logging.getLogger(__name__)

# Keys that require an app restart to take effect.
RESTART_REQUIRED_KEYS: frozenset[str] = frozenset(
    {
        "general.deepgram_api_key",
        "general.openai_api_key",
        "audio.sample_rate",
        "audio.channels",
        "audio.loopback_device",
        "audio.mic_device",
        "audio.encoding",
    }
)

# Default values for every known setting.
_DEFAULTS: dict[str, Any] = {
    # ── General ───────────────────────────────────────────────────────
    "general.deepgram_api_key": "",
    "general.openai_api_key": "",
    "general.pdf_path": str(_config.PDF_PATH),
    "general.log_level": "INFO",
    "general.debug_log_file": True,
    "general.debounce_sec": 3.0,
    "general.qa_history_depth": 3,
    # ── Audio ─────────────────────────────────────────────────────────
    "audio.sample_rate": 16000,
    "audio.channels": 1,
    "audio.chunk_ms": 100,
    "audio.encoding": "linear16",
    "audio.loopback_device": "",
    "audio.mic_device": "",
    "audio.aec_enabled": True,
    "audio.aec_filter_length": 256,
    "audio.aec_step_size": 0.05,
    # ── Transcription ─────────────────────────────────────────────────
    "transcription.model": "nova-3",
    "transcription.language": "en",
    "transcription.diarize": True,
    "transcription.smart_format": True,
    "transcription.endpointing_ms": 500,
    "transcription.utterance_end_ms": 1000,
    # ── Intelligence ──────────────────────────────────────────────────
    "intelligence.response_model": "gpt-4o",
    "intelligence.response_max_tokens": 512,
    "intelligence.bullets_model": "gpt-4o-mini",
    "intelligence.bullets_max_tokens": 256,
    "intelligence.detection_model": "gpt-4o-mini",
    "intelligence.routing_model": "gpt-4o-mini",
    "intelligence.min_words": 6,
    "intelligence.regex_min_words": 10,
    "intelligence.embedding_model": "text-embedding-3-small",
    "intelligence.embedding_dims": 1536,
    "intelligence.chunk_size": 500,
    "intelligence.chunk_overlap": 100,
    "intelligence.similarity_top_k": 5,
    "intelligence.similarity_fetch_k": 10,
    "intelligence.similarity_threshold": 0.35,
    # ── Speaker ───────────────────────────────────────────────────────
    "speaker.gap_threshold_sec": 2.5,
    "speaker.continuity_sec": 1.5,
    "speaker.echo_similarity_threshold": 0.55,
    "speaker.echo_window_sec": 3.0,
    # ── Appearance ────────────────────────────────────────────────────
    "appearance.opacity": 0.92,
    "appearance.width": 480,
    "appearance.height": 700,
    "appearance.stealth_start": True,
    "appearance.font_size": 13,
}


class SettingsManager:
    """Thread-safe, JSON-backed settings store."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or (_config.DATA_DIR / "settings.json")
        self._lock = threading.Lock()
        self._data: dict[str, Any] = dict(_DEFAULTS)
        self._subscribers: list[Callable[[set[str]], None]] = []
        self._load()

    # ── public API ────────────────────────────────────────────────────

    def get(self, key: str) -> Any:
        """Return the value for *key*, falling back to the built-in default."""
        with self._lock:
            return self._data.get(key, _DEFAULTS.get(key))

    def set(self, key: str, value: Any) -> None:
        """Set *key* to *value* in memory (call ``save()`` to persist)."""
        with self._lock:
            self._data[key] = value

    def save(self) -> None:
        """Persist current state to disk and notify subscribers."""
        with self._lock:
            data_snapshot = dict(self._data)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data_snapshot, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self._path)
        log.info("Settings saved → %s", self._path)
        changed = self._changed_keys(data_snapshot)
        self._notify(changed)

    def subscribe(self, callback: Callable[[set[str]], None]) -> None:
        """Register a listener called with the set of changed keys after save()."""
        self._subscribers.append(callback)

    def reset_to_defaults(self) -> None:
        """Restore every key to its built-in default (in-memory only)."""
        with self._lock:
            self._data = dict(_DEFAULTS)

    def all_keys(self) -> list[str]:
        """Return a sorted list of every known setting key."""
        return sorted(_DEFAULTS.keys())

    def defaults(self) -> dict[str, Any]:
        """Return a copy of the built-in defaults."""
        return dict(_DEFAULTS)

    def get_changed_from_defaults(self) -> set[str]:
        """Return keys whose current value differs from the default."""
        with self._lock:
            return {k for k, v in _DEFAULTS.items() if self._data.get(k) != v}

    # ── internal ──────────────────────────────────────────────────────

    def _load(self) -> None:
        """Load settings from disk, merging with defaults for any missing keys."""
        if not self._path.exists():
            log.info("No settings file found — using defaults.")
            self.save()
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            with self._lock:
                for key in _DEFAULTS:
                    if key in raw:
                        self._data[key] = raw[key]
            log.info("Settings loaded from %s (%d keys)", self._path, len(raw))
        except Exception:
            log.exception("Failed to load settings — using defaults.")

    def _changed_keys(self, snapshot: dict[str, Any]) -> set[str]:
        """Compare snapshot against saved-on-disk to find diffs."""
        try:
            on_disk = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return set(snapshot.keys())
        return {k for k in snapshot if snapshot.get(k) != on_disk.get(k)}

    def _notify(self, changed: set[str]) -> None:
        for cb in self._subscribers:
            try:
                cb(changed)
            except Exception:
                log.exception("Settings subscriber raised")


# ── Module-level singleton ────────────────────────────────────────────
settings = SettingsManager()
