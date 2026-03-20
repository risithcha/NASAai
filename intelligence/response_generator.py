"""
Generate concise talking-point responses by combining RAG retrieval
with GPT-4o streaming.
"""

from __future__ import annotations

import logging
from typing import Generator

from openai import OpenAI

import config
from accounts.user_profile import UserProfile
from intelligence.user_context_filter import UserContextFilter
from knowledge.knowledge_base import KnowledgeBase

log = logging.getLogger(__name__)

SYSTEM_PROMPT_TEMPLATE = """\
You are a real-time meeting assistant helping {display_name}, the {role}, \
answer questions about the NASA TerraScan report during a live Microsoft Teams call.

{display_name}'s expertise: {expertise}

RULES:
- Be concise: 2-4 bullet points max.
- Each bullet should be a clear, self-contained talking point the presenter can say aloud.
- Only suggest talking points within {display_name}'s domain as {role}.
- Do NOT suggest talking points about areas other team members handle.
- Cite the page number or section if known.
- If the document does not contain relevant info, say so briefly.
- Never fabricate data – only use what is in the provided document excerpts.
"""


class ResponseGenerator:
    def __init__(self, kb: KnowledgeBase, user_profile: UserProfile) -> None:
        self._client = OpenAI(api_key=config.OPENAI_API_KEY)
        self._kb = kb
        self._profile = user_profile
        self._system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            display_name=user_profile.display_name.split()[0],
            role=user_profile.role,
            expertise=user_profile.expertise,
        )

    def generate(self, question: str, context: str) -> str:
        """
        Blocking call: retrieve relevant chunks, call GPT-4o,
        return the full response string.
        """
        chunks = self._retrieve(question)
        return self._call_llm(question, context, chunks)

    def generate_stream(
        self, question: str, context: str
    ) -> Generator[str, None, None]:
        """
        Yield incremental text deltas as GPT-4o streams its response.
        """
        chunks = self._retrieve(question)
        yield from self._call_llm_stream(question, context, chunks)

    # ── retrieval ─────────────────────────────────────────────────────

    def _retrieve(self, question: str) -> str:
        results = self._kb.search(question, k=config.SIMILARITY_FETCH_K)
        if not results:
            return "(No relevant document excerpts found.)"

        # Per-user filtering: re-rank and keep top-K
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

    # ── LLM calls ────────────────────────────────────────────────────

    def _build_messages(self, question: str, context: str, excerpts: str):
        user_msg = (
            f"## Question being asked\n{question}\n\n"
            f"## Recent meeting transcript (for context)\n{context}\n\n"
            f"## Relevant document excerpts\n{excerpts}"
        )
        return [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": user_msg},
        ]

    def _call_llm(self, question: str, context: str, excerpts: str) -> str:
        msgs = self._build_messages(question, context, excerpts)
        resp = self._client.chat.completions.create(
            model=config.RESPONSE_MODEL,
            messages=msgs,
            temperature=0.3,
            max_tokens=config.RESPONSE_MAX_TOKENS,
        )
        return resp.choices[0].message.content.strip()

    def _call_llm_stream(
        self, question: str, context: str, excerpts: str
    ) -> Generator[str, None, None]:
        msgs = self._build_messages(question, context, excerpts)
        stream = self._client.chat.completions.create(
            model=config.RESPONSE_MODEL,
            messages=msgs,
            temperature=0.3,
            max_tokens=config.RESPONSE_MAX_TOKENS,
            stream=True,
        )
        for event in stream:
            delta = event.choices[0].delta
            if delta and delta.content:
                yield delta.content
