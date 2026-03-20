"""
Detect when a remote speaker is asking the user a question.

Two-stage approach:
  1. Fast regex pre-filter for obvious question patterns.
  2. LLM classification (GPT-4o-mini) for ambiguous cases.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from openai import OpenAI

import config

log = logging.getLogger(__name__)

# Pre-compiled patterns for strong technical question indicators.
# Matches anywhere in the segment (not just the start) so questions
# preceded by a preamble still hit the fast-path.
_QUESTION_PATTERNS = re.compile(
    r"(?:"
    r"can you|could you|walk us|tell us|explain|describe|elaborate"
    r"|how (?:did|do|does|would|will|can|could)"
    r"|what (?:is|are|was|were|would|did|do|does)"
    r"|why (?:did|do|does|would|is|are|was|were)"
    r"|where (?:did|do|does|would|is|are|was|were)"
    r"|who (?:is|was|will|would|did)"
    r"|which (?:is|are|was|were|would|did)"
    r"|share your|what's your"
    r")",
    re.IGNORECASE,
)

# Minimum word count — reject trivial fragments
_MIN_WORDS = 6
# Minimum word count for regex fast-path (skip LLM)
_REGEX_MIN_WORDS = 10


@dataclass
class DetectedQuestion:
    """A question we've identified from transcript."""
    question_text: str
    context: str           # surrounding transcript for RAG prompt
    confidence: float      # 0-1


class QuestionDetector:
    def __init__(self) -> None:
        self._client = OpenAI(api_key=config.OPENAI_API_KEY)

    def detect(self, segment_text: str, context: str) -> DetectedQuestion | None:
        """
        Check if *segment_text* (from a remote speaker) contains a question
        directed at the user.  *context* is the last ~30 s of transcript.
        Returns a DetectedQuestion or None.
        """
        import time as _t
        t0 = _t.time()

        word_count = len(segment_text.split())

        # Gate: reject trivial fragments
        if word_count < _MIN_WORDS:
            log.debug("DETECT REJECT (too short %d words): %s",
                      word_count, segment_text[:80])
            return None

        # Stage 1: regex fast-path — only for long, clearly interrogative segments
        if word_count >= _REGEX_MIN_WORDS and _QUESTION_PATTERNS.search(segment_text):
            log.info("DETECT REGEX HIT (%d words, %.0fms): %s",
                     word_count, (_t.time() - t0) * 1000, segment_text[:100])
            return DetectedQuestion(
                question_text=segment_text,
                context=context,
                confidence=0.85,
            )

        # Stage 2: LLM classification for everything else
        result = self._llm_classify(segment_text, context)
        elapsed = (_t.time() - t0) * 1000
        if result:
            log.info("DETECT LLM HIT (%.0fms conf=%.2f): %s",
                     elapsed, result.confidence, result.question_text[:100])
        else:
            log.debug("DETECT LLM MISS (%.0fms): %s", elapsed, segment_text[:80])
        return result

    def _llm_classify(
        self, segment: str, context: str
    ) -> DetectedQuestion | None:
        system = (
            "You are a question filter for a NASA UAS (drone) design review meeting. "
            "An evaluator panel is questioning a student team about their aircraft design, "
            "mission payload, detect-and-avoid system, operations plan, and budget.\n\n"
            "Given the recent transcript and the latest segment from an evaluator, "
            "decide: is this a SUBSTANTIVE TECHNICAL or DESIGN question that the "
            "presenting team needs to answer with project-specific knowledge?\n\n"
            "ACCEPT as a question:\n"
            "- Technical questions about the aircraft, payload, sensors, avionics, DAA, GSD, "
            "flight parameters, algorithms, control logic, mission planning, operations, budget, cost\n"
            "- Requests to explain, walk through, or elaborate on a design decision\n"
            "- Follow-up probing questions about a previous technical answer\n\n"
            "REJECT (is_question=false):\n"
            "- Casual chatter, greetings, banter, off-topic talk\n"
            "- Rhetorical or phatic questions: 'Right?', 'Okay?', 'You know?', 'Correct?'\n"
            "- Meeting logistics / meta-talk: 'Can you share screen?', 'Scroll down', "
            "'Can you hear me?', 'Are you there?'\n"
            "- Commands disguised as questions: 'Can you click that?', 'Would you scroll?'\n"
            "- Personal questions unrelated to the project: 'How are you?', 'What did you eat?'\n"
            "- Fragments or incomplete thoughts under ~6 words\n"
            "- Statements with a question mark\n"
            "- Questions directed at the meeting host, not the presenting team\n\n"
            "If it IS a substantive question, extract the COMPLETE question EXACTLY as spoken "
            "— do NOT summarize, shorten, rephrase, or paraphrase.\n"
            "Respond ONLY with JSON: "
            '{"is_question": true/false, "question": "<full verbatim question or empty>"}'
        )
        user_msg = (
            f"### Recent transcript\n{context}\n\n"
            f"### Latest segment from remote speaker\n{segment}"
        )

        try:
            import time as _t
            t0 = _t.time()
            resp = self._client.chat.completions.create(
                model=config.QUESTION_DETECT_MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.0,
                max_tokens=300,
                response_format={"type": "json_object"},
            )
            elapsed_ms = (_t.time() - t0) * 1000
            import json
            payload = json.loads(resp.choices[0].message.content)
            log.debug("LLM CLASSIFY (%.0fms): %s", elapsed_ms, payload)
            if payload.get("is_question"):
                q_text = payload.get("question", segment).strip() or segment
                return DetectedQuestion(
                    question_text=q_text,
                    context=context,
                    confidence=0.75,
                )
        except Exception:
            log.exception("LLM question detection failed")

        return None
