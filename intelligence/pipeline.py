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
from accounts.user_profile import UserProfile
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
    redirect_to: str | None = None # If set, question belongs to this other user


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
        user_profile: UserProfile,
        all_profiles: dict[str, UserProfile] | None = None,
        on_response: ResponseCallback | None = None,
    ) -> None:
        self._store = store
        self._detector = QuestionDetector()
        self._generator = ResponseGenerator(kb, user_profile)
        self._profile = user_profile
        self._all_profiles = all_profiles or {user_profile.username: user_profile}
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
        # Only analyse complete utterances from remote speakers
        if not seg.is_utterance_end or seg.channel == 1:
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

        # Question routing: check if this question belongs to another user
        redirect = self._route_question(detected.question_text)
        if redirect and self._on_response:
            self._on_response(SuggestedResponse(
                question=detected.question_text,
                response="",
                redirect_to=redirect,
            ))
            return

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

    # ── question routing ──────────────────────────────────────────────

    def _route_question(self, question: str) -> str | None:
        """
        Score the question against each user's owned_keywords.
        Returns the display name of a *different* user if the question
        clearly belongs to someone else, or None if it's ours (or ambiguous).
        """
        if len(self._all_profiles) < 2:
            return None  # only one user — no routing needed

        q_lower = question.lower()
        scores: dict[str, tuple[int, UserProfile]] = {}

        for username, profile in self._all_profiles.items():
            score = sum(1 for kw in profile.owned_keywords if kw.lower() in q_lower)
            scores[username] = (score, profile)

        my_score = scores.get(self._profile.username, (0, self._profile))[0]

        # Find the best-matching user
        best_user = max(scores, key=lambda u: scores[u][0])
        best_score, best_profile = scores[best_user]

        if best_score == 0:
            # No keywords matched any user — generic question, answer it
            return None

        if best_user == self._profile.username:
            # Current user is the best match — no redirect
            return None

        # Another user scores higher — only redirect if we clearly don't own it
        if my_score > 0 and my_score >= best_score * 0.5:
            # Overlapping domain — answer it (both users relevant)
            return None

        # This question belongs to someone else
        name = best_profile.display_name.split()[0]
        role = best_profile.role
        log.info(
            "Question routed away from %s → %s (%s)  [scores: me=%d, them=%d]",
            self._profile.username, name, role, my_score, best_score,
        )
        return f"{name} ({role})"
