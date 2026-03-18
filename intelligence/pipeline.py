"""
Pipeline orchestrator: listens for new transcript segments, detects questions
from remote speakers, runs RAG + LLM, and emits suggested responses.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

import config
from intelligence.question_detector import QuestionDetector, DetectedQuestion
from intelligence.response_generator import ResponseGenerator
from knowledge.knowledge_base import KnowledgeBase
from transcription.transcript_store import TranscriptSegment, TranscriptStore

log = logging.getLogger(__name__)


@dataclass
class SuggestedResponse:
    """Payload emitted when a question is detected and answered."""
    question: str
    response: str
    timestamp: float = field(default_factory=time.time)
    is_streaming: bool = False     # True while response is still arriving


ResponseCallback = Callable[[SuggestedResponse], None]


class Pipeline:
    """
    Connects TranscriptStore → QuestionDetector → ResponseGenerator.
    Runs analysis on a background thread to keep the UI responsive.
    """

    def __init__(
        self,
        store: TranscriptStore,
        kb: KnowledgeBase,
        on_response: ResponseCallback | None = None,
    ) -> None:
        self._store = store
        self._detector = QuestionDetector()
        self._generator = ResponseGenerator(kb)
        self._on_response = on_response
        self._running = False
        self._thread: threading.Thread | None = None
        self._queue: list[TranscriptSegment] = []
        self._lock = threading.Lock()
        self._last_question_time: float = 0.0

    # ── public API ────────────────────────────────────────────────────

    def start(self) -> None:
        self._running = True
        self._store.add_listener(self._on_segment)
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()
        log.info("Intelligence pipeline started")

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def set_callback(self, cb: ResponseCallback) -> None:
        self._on_response = cb

    # ── segment listener ──────────────────────────────────────────────

    def _on_segment(self, seg: TranscriptSegment) -> None:
        """Called by TranscriptStore on every new segment."""
        # Only analyse final segments from remote speakers
        if not seg.is_final or seg.channel == 1:
            return
        with self._lock:
            self._queue.append(seg)

    # ── background worker ─────────────────────────────────────────────

    def _worker(self) -> None:
        while self._running:
            seg = self._pop_segment()
            if seg is None:
                time.sleep(0.15)
                continue
            self._process(seg)

    def _pop_segment(self) -> TranscriptSegment | None:
        with self._lock:
            if self._queue:
                return self._queue.pop(0)
        return None

    def _process(self, seg: TranscriptSegment) -> None:
        # Debounce: skip if we just handled a question
        now = time.time()
        if now - self._last_question_time < config.QUESTION_DEBOUNCE_SEC:
            return

        context = self._store.recent_text(seconds=30)
        detected = self._detector.detect(seg.text, context)
        if detected is None:
            return

        log.info("Question detected: %s", detected.question_text)
        self._last_question_time = time.time()

        # Stream the response
        if self._on_response:
            # First emit a "streaming started" placeholder
            placeholder = SuggestedResponse(
                question=detected.question_text,
                response="",
                is_streaming=True,
            )
            self._on_response(placeholder)

            full_response = []
            for delta in self._generator.generate_stream(
                detected.question_text, context
            ):
                full_response.append(delta)
                partial = SuggestedResponse(
                    question=detected.question_text,
                    response="".join(full_response),
                    is_streaming=True,
                )
                self._on_response(partial)

            final = SuggestedResponse(
                question=detected.question_text,
                response="".join(full_response),
                is_streaming=False,
            )
            self._on_response(final)
