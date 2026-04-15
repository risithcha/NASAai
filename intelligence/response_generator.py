"""
Generate concise talking-point responses by combining RAG retrieval
with GPT-4o streaming.  Supports dual parallel streaming: bullet
talking-points via GPT-4o-mini and a spoken-ready answer via GPT-4o.
"""

from __future__ import annotations

import logging
import queue
import threading
from typing import Generator

from openai import OpenAI

import config
from accounts.user_profile import UserProfile
from intelligence.user_context_filter import UserContextFilter
from knowledge.knowledge_base import KnowledgeBase

log = logging.getLogger(__name__)

# ── Prompt: bullet talking-point summaries (GPT-4o-mini) ────────────
BULLETS_PROMPT_TEMPLATE = """\
You are a real-time presentation assistant helping {display_name}, the {role}, \
prepare talking-point bullets about the Data Science portfolio and datasets \
during a live presentation to judges.

{display_name}'s expertise: {expertise}

OUTPUT — bullet list ONLY, nothing else:
- 3–5 bullet points.
- Each bullet is a self-contained talking point with supporting detail.
- Cite the page, section, or dataset where relevant (e.g. "(Page 3)" or "(Dataset_A_Annual)").
- Only cover topics within {display_name}'s domain as {role}.
- If this is a follow-up, provide NEW information only — never restate points already covered in previous answers.
- Focus on what the documents and datasets DO say — never include bullets about what \
the documents don't cover or what information is missing.
- Never fabricate data.
"""

# ── Prompt: spoken-ready answer paragraph (GPT-4o) ──────────────────
ANSWER_PROMPT_TEMPLATE = """\
You are a real-time presentation assistant helping {display_name}, the {role}, \
answer questions about the Data Science portfolio and datasets during a live \
presentation to judges.

{display_name}'s expertise: {expertise}

OUTPUT — a single spoken-ready paragraph ONLY, nothing else:
- Use as many sentences as the question warrants — be concise for simple \
questions, thorough for complex ones (typically 2–8 sentences).
- This is what {display_name} should SAY OUT LOUD — natural, conversational, \
comprehensive.
- Cover only topics within {display_name}'s domain as {role}.
- If this is a follow-up, answer the NEW question directly — do not repeat or \
summarise what was already said.
- Focus on what you CAN answer from the documents and datasets — never say "the \
document doesn't cover" or "there is no information about". Just answer confidently \
with the available information.
- Never fabricate data.
"""


class ResponseGenerator:
    def __init__(self, kb: KnowledgeBase, user_profile: UserProfile) -> None:
        self._client = OpenAI(api_key=config.OPENAI_API_KEY)
        self._kb = kb
        self._profile = user_profile
        first_name = user_profile.display_name.split()[0]
        self._bullets_prompt = BULLETS_PROMPT_TEMPLATE.format(
            display_name=first_name,
            role=user_profile.role,
            expertise=user_profile.expertise,
        )
        self._answer_prompt = ANSWER_PROMPT_TEMPLATE.format(
            display_name=first_name,
            role=user_profile.role,
            expertise=user_profile.expertise,
        )

    # ── public API ────────────────────────────────────────────────────

    def generate_dual_stream(
        self,
        question: str,
        context: str,
        prior_qa: list[tuple[str, str]] | None = None,
        pre_retrieved: list | None = None,
    ) -> tuple[queue.Queue, queue.Queue]:
        """Start two parallel LLM streams and return (bullet_q, answer_q).

        Each queue receives incremental string deltas.  A *None* sentinel
        signals that the respective stream is finished.

        If *pre_retrieved* is provided (list of (TextChunk, score) tuples),
        skip the embedding search and use those results directly.
        """
        if pre_retrieved:
            excerpts = self._format_retrieved(pre_retrieved)
        else:
            excerpts = self._retrieve(question)

        bullet_q: queue.Queue[str | None] = queue.Queue()
        answer_q: queue.Queue[str | None] = queue.Queue()

        def _stream_to_queue(
            sys_prompt: str, model: str, max_tokens: int,
            q: queue.Queue,
        ) -> None:
            try:
                msgs = self._build_messages(
                    sys_prompt, question, context, excerpts, prior_qa,
                )
                stream = self._client.chat.completions.create(
                    model=model, messages=msgs,
                    temperature=0.3, max_tokens=max_tokens, stream=True,
                )
                for event in stream:
                    delta = event.choices[0].delta
                    if delta and delta.content:
                        q.put(delta.content)
            except Exception:
                log.exception("LLM stream error (%s)", model)
            finally:
                q.put(None)  # sentinel

        threading.Thread(
            target=_stream_to_queue,
            args=(self._bullets_prompt, config.BULLETS_MODEL,
                  config.BULLETS_MAX_TOKENS, bullet_q),
            daemon=True,
        ).start()

        threading.Thread(
            target=_stream_to_queue,
            args=(self._answer_prompt, config.RESPONSE_MODEL,
                  config.RESPONSE_MAX_TOKENS, answer_q),
            daemon=True,
        ).start()

        return bullet_q, answer_q

    # ── retrieval ─────────────────────────────────────────────────────

    def _retrieve(self, question: str) -> str:
        results = self._kb.search(question, k=config.SIMILARITY_FETCH_K)
        return self._format_retrieved(results)

    def _format_retrieved(self, results: list) -> str:
        """Format KB search results into a text block for the LLM prompt."""
        if not results:
            return "(No relevant document excerpts found.)"

        results = UserContextFilter.filter(
            results, self._profile, top_k=config.SIMILARITY_TOP_K
        )

        parts: list[str] = []
        for chunk, dist in results:
            header = f"[Page {chunk.page}"
            if chunk.section:
                header += f" – {chunk.section}"
            header += f"] (relevance {dist:.2f})"
            parts.append(f"{header}\n{chunk.text}")
        return "\n\n---\n\n".join(parts)

    # ── LLM message building ─────────────────────────────────────────

    def _build_messages(
        self, system_prompt: str,
        question: str, context: str, excerpts: str,
        prior_qa: list[tuple[str, str]] | None = None,
    ):
        parts = []
        if prior_qa:
            parts.append("## Previous Q&A in this session (for context — do NOT repeat)")
            for prev_q, prev_a in prior_qa:
                trimmed = prev_a[:200] + "…" if len(prev_a) > 200 else prev_a
                parts.append(f"Q: {prev_q}\nA: {trimmed}")
            parts.append("")
        parts.append(f"## Question being asked\n{question}")
        parts.append(f"## Recent meeting transcript (for context)\n{context}")
        parts.append(f"## Relevant document excerpts\n{excerpts}")
        user_msg = "\n\n".join(parts)
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ]
