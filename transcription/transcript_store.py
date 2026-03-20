"""
Rolling transcript buffer that stores recent speaker-labelled segments.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class TranscriptSegment:
    """One finalised piece of transcript."""
    text: str
    speaker: str            # "You" or "Speaker 0", "Speaker 1", …
    channel: int            # 0 = remote, 1 = mic
    is_final: bool = True
    is_utterance_end: bool = False   # True when speech_final closes a full utterance
    timestamp: float = field(default_factory=time.time)


# Callback type: called every time a new segment arrives.
TranscriptCallback = Callable[[TranscriptSegment], None]


class TranscriptStore:
    """
    Thread-safe store of recent transcript segments.
    Keeps at most *max_segments* entries and notifies listeners.
    """

    def __init__(self, max_segments: int = 200) -> None:
        self._segments: list[TranscriptSegment] = []
        self._lock = threading.Lock()
        self._max = max_segments
        self._listeners: list[TranscriptCallback] = []
        # Interim (not-yet-final) segment shown as preview
        self._interim: TranscriptSegment | None = None

    # ── listeners ─────────────────────────────────────────────────────

    def add_listener(self, cb: TranscriptCallback) -> None:
        self._listeners.append(cb)

    # ── write ─────────────────────────────────────────────────────────

    def add_segment(self, seg: TranscriptSegment) -> None:
        with self._lock:
            self._segments.append(seg)
            if len(self._segments) > self._max:
                self._segments = self._segments[-self._max:]
        for cb in self._listeners:
            cb(seg)

    def set_interim(self, seg: TranscriptSegment) -> None:
        """Replace the current interim (partial) segment."""
        self._interim = seg
        for cb in self._listeners:
            cb(seg)

    # ── read ──────────────────────────────────────────────────────────

    def recent_text(self, seconds: float = 30.0) -> str:
        """Return concatenated transcript from the last *seconds*."""
        cutoff = time.time() - seconds
        with self._lock:
            parts = [
                f"[{s.speaker}]: {s.text}"
                for s in self._segments
                if s.timestamp >= cutoff
            ]
        return "\n".join(parts)

    def recent_segments(self, seconds: float = 30.0) -> list[TranscriptSegment]:
        cutoff = time.time() - seconds
        with self._lock:
            return [s for s in self._segments if s.timestamp >= cutoff]

    @property
    def interim(self) -> TranscriptSegment | None:
        return self._interim

    @property
    def all_segments(self) -> list[TranscriptSegment]:
        with self._lock:
            return list(self._segments)
