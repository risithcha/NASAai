"""
Pipeline orchestrator: listens for new transcript segments, detects questions
from remote speakers, runs RAG + LLM, and emits suggested responses.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

from openai import OpenAI

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
    bullets: str = ""                  # accumulated bullet-point text
    answer: str = ""                   # accumulated spoken-ready answer text
    question_id: int = 0               # unique per question; same for all streaming deltas
    timestamp: float = field(default_factory=time.time)
    is_streaming: bool = False     # True while response is still arriving
    redirect_to: str | None = None # If set, question belongs to this other user
    hint_to: str | None = None     # Soft hint: "might be more for X" — still answers


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
        self._kb = kb
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
        self._question_counter: int = 0
        self._qa_history: list[tuple[str, str]] = []  # (question, response) pairs
        self._oai = OpenAI(api_key=config.OPENAI_API_KEY)

        # Pre-build the team roster summary used by LLM routing
        self._team_summary = self._build_team_summary()

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
        # Log every segment for debugging
        if seg.channel == 1:
            log.debug("SEG DROP (mic/ch1): [%s] %s", seg.speaker, seg.text[:80])
            return
        if not seg.is_utterance_end:
            log.debug("SEG DROP (not utterance_end): [%s] %s", seg.speaker, seg.text[:80])
            return
        log.info("SEG QUEUED: ch=%d spk=%s utt_end=%s | %s",
                 seg.channel, seg.speaker, seg.is_utterance_end, seg.text[:100])
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
        elapsed = now - self._last_question_time
        if elapsed < config.QUESTION_DEBOUNCE_SEC:
            log.debug("DEBOUNCE: skipping (%.1fs < %.1fs) | %s",
                      elapsed, config.QUESTION_DEBOUNCE_SEC, seg.text[:80])
            return

        context = self._store.recent_text(seconds=30)
        log.debug("DETECT START: %s", seg.text[:100])
        detected = self._detector.detect(seg.text, context)
        if detected is None:
            log.debug("DETECT MISS: not a question | %s", seg.text[:80])
            return

        log.info("QUESTION DETECTED (conf=%.2f): %s",
                 detected.confidence, detected.question_text[:120])
        self._last_question_time = time.time()

        # Pre-fetch KB results once — shared by routing and response generation
        kb_results = []
        try:
            kb_results = self._kb.search(
                detected.question_text, k=config.SIMILARITY_FETCH_K,
            )
        except Exception:
            log.debug("KB pre-fetch failed", exc_info=True)

        self._question_counter += 1
        qid = self._question_counter

        # Start routing + response generation in PARALLEL.
        # Routing runs on its own thread; response starts immediately
        # with hint=None.  When routing finishes, hint is injected into
        # subsequent streaming emissions.
        routing_result: dict = {"hint": None, "done": False}
        routing_event = threading.Event()   # signalled when routing completes
        route_start = time.time()

        def _route_async() -> None:
            log.debug("ROUTE START qid=%d t=%.3fs", qid, time.time() - route_start)
            try:
                redirect, hint = self._smart_route_question(
                    detected.question_text, kb_results=kb_results,
                )
                elapsed = time.time() - route_start
                if redirect:
                    log.info("ROUTE → REDIRECT qid=%d to '%s' (%.0fms) — showing as hint banner",
                             qid, redirect, elapsed * 1000)
                    routing_result["hint"] = redirect
                elif hint:
                    log.info("ROUTE → HINT qid=%d hint='%s' (%.0fms) — soft banner",
                             qid, hint, elapsed * 1000)
                    routing_result["hint"] = hint
                else:
                    log.info("ROUTE → MINE qid=%d (%.0fms) — no redirect/hint",
                             qid, elapsed * 1000)
            except Exception:
                log.warning("Routing failed qid=%d (%.0fms)",
                            qid, (time.time() - route_start) * 1000, exc_info=True)
            finally:
                routing_result["done"] = True
                routing_event.set()
                log.debug("ROUTE DONE qid=%d — event signalled, hint=%s",
                          qid, routing_result.get("hint"))

        threading.Thread(target=_route_async, daemon=True, name=f"route-q{qid}").start()

        # Fire off streaming immediately (don't wait for routing)
        if self._on_response:
            t = threading.Thread(
                target=self._stream_response,
                args=(detected, context, qid, routing_result, routing_event, kb_results),
                daemon=True,
                name=f"stream-q{qid}",
            )
            t.start()

    def _stream_response(
        self,
        detected: DetectedQuestion,
        context: str,
        qid: int,
        routing_result: dict,
        routing_event: threading.Event,
        kb_results: list,
    ) -> None:
        """Run the dual-stream LLM response on its own thread."""
        stream_start = time.time()
        log.info("STREAM START qid=%d", qid)

        # Brief wait for routing — avoids the UI creating a block with no hint
        # if routing finishes within a reasonable window.
        if not routing_event.wait(timeout=0.35):
            log.debug("STREAM qid=%d: routing not ready after 350ms, proceeding without hint",
                      qid)
        else:
            log.debug("STREAM qid=%d: routing ready before first emit (%.0fms)",
                      qid, (time.time() - stream_start) * 1000)

        # Check routing result
        cur_hint = routing_result.get("hint")
        log.debug("STREAM FIRST EMIT qid=%d: hint=%s", qid, cur_hint)

        # Placeholder: streaming started
        self._on_response(SuggestedResponse(
            question=detected.question_text,
            question_id=qid,
            is_streaming=True,
            hint_to=cur_hint,
        ))

        with self._lock:
            prior = self._qa_history[-config.QA_HISTORY_DEPTH:] if self._qa_history else None

        bullet_q, answer_q = self._generator.generate_dual_stream(
            detected.question_text, context, prior_qa=prior,
            pre_retrieved=kb_results,
        )

        full_bullets: list[str] = []
        full_answer: list[str] = []
        bullets_done = False
        answer_done = False

        while not (bullets_done and answer_done):
            # Drain bullet queue
            while not bullets_done:
                try:
                    chunk = bullet_q.get_nowait()
                except queue.Empty:
                    break
                if chunk is None:
                    bullets_done = True
                else:
                    full_bullets.append(chunk)
            # Drain answer queue
            while not answer_done:
                try:
                    chunk = answer_q.get_nowait()
                except queue.Empty:
                    break
                if chunk is None:
                    answer_done = True
                else:
                    full_answer.append(chunk)

            # Check for newly-arrived routing result each iteration
            new_hint = routing_result.get("hint")

            if new_hint != cur_hint:
                log.info("STREAM qid=%d: hint CHANGED mid-stream (%s→%s) at %.0fms",
                         qid, cur_hint, new_hint,
                         (time.time() - stream_start) * 1000)
                cur_hint = new_hint

            self._on_response(SuggestedResponse(
                question=detected.question_text,
                bullets="".join(full_bullets),
                answer="".join(full_answer),
                question_id=qid,
                is_streaming=True,
                hint_to=cur_hint,
            ))
            if not (bullets_done and answer_done):
                time.sleep(0.05)

        # Final emission
        bullets_text = "".join(full_bullets)
        answer_text = "".join(full_answer)
        final_hint = routing_result.get("hint")
        log.debug("STREAM FINAL EMIT qid=%d: hint=%s", qid, final_hint)
        self._on_response(SuggestedResponse(
            question=detected.question_text,
            bullets=bullets_text,
            answer=answer_text,
            question_id=qid,
            is_streaming=False,
            hint_to=final_hint,
        ))

        # Store for conversation continuity (answer only — bullets are ephemeral)
        with self._lock:
            self._qa_history.append((detected.question_text, answer_text))

        duration = time.time() - stream_start
        log.info("STREAM END qid=%d  %.1fs  bullets=%d chars  answer=%d chars  "
                 "final_hint=%s",
                 qid, duration, len(bullets_text), len(answer_text), final_hint)

    # ── team summary builder ──────────────────────────────────────────

    def _build_team_summary(self) -> str:
        """Build a compact one-liner-per-member summary for LLM routing."""
        lines: list[str] = []
        for uname, p in self._all_profiles.items():
            keywords_preview = ", ".join(p.owned_keywords[:15])
            lines.append(
                f"- {uname} | {p.display_name} | {p.role} | "
                f"expertise: {p.expertise[:120]}… | "
                f"keywords: {keywords_preview}"
            )
        return "\n".join(lines)

    # ── question routing (smart: LLM primary, keyword fallback) ───────

    def _smart_route_question(
        self, question: str,
        kb_results: list | None = None,
    ) -> tuple[str | None, str | None]:
        """Route using LLM first; fall back to keyword scoring on failure."""
        if len(self._all_profiles) < 2:
            return None, None
        try:
            return self._llm_route_question(question, kb_results=kb_results)
        except Exception:
            log.warning("LLM routing failed — falling back to keyword routing",
                        exc_info=True)
            return self._keyword_route_question(question)

    # ── LLM-based routing ─────────────────────────────────────────────

    def _llm_route_question(
        self, question: str,
        kb_results: list | None = None,
    ) -> tuple[str | None, str | None]:
        """Use GPT-4o-mini to semantically classify who should answer.

        Queries the knowledge base for relevant chunks to give the LLM
        grounded context about each team member's actual responsibilities.

        Returns ``(redirect_to, hint_to)`` matching the existing 3-tier interface.
        """
        my_uname = self._profile.username

        # Use pre-fetched KB results if available; otherwise fetch fresh
        kb_context = ""
        try:
            results = kb_results if kb_results else self._kb.search(question, k=3)
            if results:
                snippets = [chunk.text[:200] for chunk, _score in results[:3]]
                kb_context = (
                    "\n\nRelevant project documentation excerpts:\n"
                    + "\n---\n".join(snippets)
                )
        except Exception:
            log.debug("KB search for routing failed", exc_info=True)

        system = (
            "You are a meeting routing assistant. Given a question asked during a "
            "NASA UAS design review and a list of team members with their roles and "
            "expertise, determine which team member the question is MOST directed at.\n\n"
            "Team members:\n"
            f"{self._team_summary}\n"
            f"{kb_context}\n\n"
            "Rules:\n"
            "- If the question clearly belongs to one member's domain, return their username.\n"
            "- If it is a general/shared question not specific to any one domain, return \"generic\".\n"
            "- Transcription may contain garbled words (e.g. \"Pixalk\" = \"Pixhawk\", "
            "\"GST\" = \"GSD\", \"Residt\" = \"Risith\", \"Doshi\" = \"Santhosh\"). "
            "Use context clues to infer the correct term.\n"
            "- Use the project documentation excerpts to accurately match the question "
            "to whichever team member owns that part of the design.\n"
            "- confidence: 1.0 = absolutely certain, 0.5 = could go either way.\n\n"
            "Respond ONLY with JSON: "
            '{"assigned_to": "<username or generic>", "confidence": <0.0-1.0>}'
        )
        user_msg = f"Question: {question}"

        t0 = time.time()
        resp = self._oai.chat.completions.create(
            model=config.ROUTING_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.0,
            max_tokens=60,
            response_format={"type": "json_object"},
        )
        elapsed_ms = (time.time() - t0) * 1000

        payload = json.loads(resp.choices[0].message.content)
        assigned = payload.get("assigned_to", "generic").lower().strip()
        confidence = float(payload.get("confidence", 0.5))

        log.info("LLM ROUTE: assigned_to=%s  conf=%.2f  (%.0fms) | %s",
                 assigned, confidence, elapsed_ms, question[:80])

        # Map to 3-tier result
        if assigned == "generic" or assigned == my_uname:
            return None, None

        # Find the profile for the assigned user
        target = self._all_profiles.get(assigned)
        if target is None:
            log.warning("LLM returned unknown user '%s' — treating as generic", assigned)
            return None, None

        label = f"{target.display_name.split()[0]} ({target.role})"

        if confidence >= 0.8:
            # High confidence → hard redirect
            log.info("LLM ROUTE → REDIRECT to %s (conf=%.2f)", label, confidence)
            return label, None
        else:
            # Lower confidence → soft hint, still answer
            log.info("LLM ROUTE → HINT %s (conf=%.2f)", label, confidence)
            return None, label

    # ── keyword-based routing (fallback) ──────────────────────────────

    def _keyword_route_question(self, question: str) -> tuple[str | None, str | None]:
        """Score the question against each user's owned_keywords.

        Returns ``(redirect_to, hint_to)``:
        * ``(None, None)``          — clearly ours, full answer.
        * ``(None, "Name (Role)")`` — not primarily ours, still answer + soft hint.
        * ``("Name (Role)", None)`` — clearly theirs, hard redirect (no answer).
        """
        if len(self._all_profiles) < 2:
            return None, None

        q_lower = question.lower()
        scores: dict[str, tuple[int, UserProfile]] = {}

        for username, profile in self._all_profiles.items():
            score = sum(1 for kw in profile.owned_keywords if kw.lower() in q_lower)
            scores[username] = (score, profile)

        # Log all scores for debugging
        score_summary = {u: s for u, (s, _) in scores.items()}
        log.info("KEYWORD SCORES: %s | %s", score_summary, question[:80])

        my_score = scores.get(self._profile.username, (0, self._profile))[0]

        # Find the best-matching user
        best_user = max(scores, key=lambda u: scores[u][0])
        best_score, best_profile = scores[best_user]

        if best_score == 0:
            # No keywords matched any user — generic question, answer it
            return None, None

        if best_user == self._profile.username:
            # Current user is the best match — no redirect
            return None, None

        best_label = f"{best_profile.display_name.split()[0]} ({best_profile.role})"

        # Tier 1: overlapping domain — I score well too → full answer, no hint
        if my_score > 0 and my_score >= best_score * 0.5:
            return None, None

        # Tier 2: weak off-domain signal OR partial overlap → answer + soft hint
        if best_score <= 2 or my_score > 0:
            log.info(
                "KW HINT: %s might be better for %s  [me=%d, them=%d]",
                question[:60], best_label, my_score, best_score,
            )
            return None, best_label

        # Tier 3: clearly theirs (3+ keywords, I score 0) → hard redirect
        log.info(
            "KW REDIRECT from %s → %s  [me=%d, them=%d]",
            self._profile.username, best_label, my_score, best_score,
        )
        return best_label, None
