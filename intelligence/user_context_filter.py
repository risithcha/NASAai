"""
Post-retrieval re-ranking of RAG chunks based on the active user's profile.

Boosts chunks matching the user's owned sections/keywords and demotes
chunks matching their exclude keywords, so each team member gets
domain-appropriate talking points.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from accounts.user_profile import UserProfile
    from knowledge.pdf_parser import TextChunk

log = logging.getLogger(__name__)

# Tuning constants for score adjustment (lower L2 = more relevant)
_SECTION_BOOST = 0.15       # subtract from dist if chunk matches owned section
_KEYWORD_BOOST = 0.05       # per keyword match (capped)
_KEYWORD_BOOST_CAP = 0.20   # max total keyword boost
_EXCLUDE_PENALTY = 0.20     # add to dist if chunk matches exclude keywords


class UserContextFilter:
    """Re-rank retrieved chunks to match a user's domain."""

    @staticmethod
    def filter(
        results: list[tuple[TextChunk, float]],
        profile: UserProfile,
        top_k: int = 5,
    ) -> list[tuple[TextChunk, float]]:
        """
        Re-score *results* for *profile* and return the top-*k*.

        Scoring adjustments (applied to L2 distance — lower is better):
          - Section match:  -0.15 per owned section prefix match
          - Keyword match:  -0.05 per keyword found in chunk text (max -0.20)
          - Exclude match:  +0.20 if any exclude keyword appears
        """
        if not results or not profile:
            return results[:top_k]

        # Pre-lowercase for faster matching
        owned_sections = [s.lower() for s in profile.owned_sections]
        owned_kw = [kw.lower() for kw in profile.owned_keywords]
        exclude_kw = [kw.lower() for kw in profile.exclude_keywords]

        scored: list[tuple[TextChunk, float]] = []
        for chunk, dist in results:
            adjusted = dist
            text_lower = chunk.text.lower()
            section_lower = chunk.section.lower() if chunk.section else ""

            # Boost: section ownership
            for sec in owned_sections:
                if section_lower.startswith(sec) or sec in section_lower:
                    adjusted -= _SECTION_BOOST
                    break  # one match is enough

            # Boost: keyword presence
            kw_bonus = 0.0
            for kw in owned_kw:
                if kw in text_lower:
                    kw_bonus += _KEYWORD_BOOST
                    if kw_bonus >= _KEYWORD_BOOST_CAP:
                        break
            adjusted -= kw_bonus

            # Penalty: exclude keyword presence
            for kw in exclude_kw:
                if kw in text_lower:
                    adjusted += _EXCLUDE_PENALTY
                    break  # one match is enough to penalise

            scored.append((chunk, adjusted))

        # Sort by adjusted distance (ascending = most relevant first)
        scored.sort(key=lambda x: x[1])
        return scored[:top_k]
