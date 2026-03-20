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

# Pre-compiled patterns that strongly indicate a question directed at the user
_QUESTION_PATTERNS = re.compile(
    r"(?:"
    r"\?\s*$"                           # ends with ?
    r"|^(?:what|how|why|when|where|who|which|can you|could you|do you|would you|"
    r"have you|are you|is there|tell us|walk us|explain|describe|elaborate|"
    r"share your|what's your)"
    r")",
    re.IGNORECASE | re.MULTILINE,
)


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
        # Stage 1: regex pre-filter
        if _QUESTION_PATTERNS.search(segment_text):
            return DetectedQuestion(
                question_text=segment_text,
                context=context,
                confidence=0.85,
            )

        # Stage 2: LLM classification for subtler questions
        return self._llm_classify(segment_text, context)

    def _llm_classify(
        self, segment: str, context: str
    ) -> DetectedQuestion | None:
        system = (
            "You are a meeting assistant.  Given the recent transcript context "
            "and the latest segment from a remote speaker, determine whether the "
            "remote speaker is asking or directing a question at the presenter "
            "(the user).  If it IS a question, extract the COMPLETE question "
            "EXACTLY as spoken — do NOT summarize, shorten, rephrase, or "
            "paraphrase.  Copy the full question verbatim from the segment.  "
            "Respond ONLY with JSON: "
            '{"is_question": true/false, "question": "<full verbatim question or empty>"}'
        )
        user_msg = (
            f"### Recent transcript\n{context}\n\n"
            f"### Latest segment from remote speaker\n{segment}"
        )

        try:
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
            import json
            payload = json.loads(resp.choices[0].message.content)
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
