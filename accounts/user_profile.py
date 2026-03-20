"""
Per-user profile system.

Parses data/NASAai_user_profiles.md to build UserProfile objects,
and provides a UserSession singleton to hold the active user.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import config

log = logging.getLogger(__name__)


@dataclass
class UserProfile:
    """One team member's identity, role, and domain knowledge boundaries."""

    username: str                          # lowercase key, e.g. "risith"
    display_name: str                      # "Risith Kankanamge"
    role: str                              # "Technical Lead"
    expertise: str                         # natural-language expertise paragraph
    owned_sections: list[str] = field(default_factory=list)   # ["2.3.1", "2.3.2"]
    owned_keywords: list[str] = field(default_factory=list)   # domain terms to boost
    exclude_keywords: list[str] = field(default_factory=list) # other domains to demote


# ── Markdown parser helpers ───────────────────────────────────────────

def _extract_between(text: str, start_heading: str, stop_pattern: str) -> str:
    """Return text between *start_heading* and the next heading matching *stop_pattern*."""
    pattern = re.compile(
        rf"^##\s+{re.escape(start_heading)}\s*$(.+?)(?=^##\s+{stop_pattern}|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    m = pattern.search(text)
    return m.group(1).strip() if m else ""


def _extract_section(text: str, heading: str) -> str:
    """Return content under a ## heading until the next ## heading."""
    pattern = re.compile(
        rf"^##\s+{re.escape(heading)}\s*$(.+?)(?=^##\s|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    m = pattern.search(text)
    return m.group(1).strip() if m else ""


def _parse_section_numbers(block: str) -> list[str]:
    """Extract section numbers from a markdown table like '| 2.3.1 | Air Vehicle |'."""
    sections: list[str] = []
    for line in block.split("\n"):
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.split("|") if c.strip()]
        if len(cells) >= 2:
            candidate = cells[0]
            # Section numbers look like "2.3.1" or "4 (entire)" or "4.1"
            num = re.match(r"^[\d.]+", candidate)
            if num:
                sections.append(num.group())
    return sections


def _parse_backtick_list(block: str) -> list[str]:
    """Extract all backtick-delimited terms from a block of text."""
    return re.findall(r"`([^`]+)`", block)


def _parse_user_block(block: str) -> Optional[UserProfile]:
    """Parse a single '# USER: ...' block into a UserProfile."""
    # Extract name and role from heading: "# USER: Risith Kankanamge — Technical Lead"
    heading_match = re.search(r"#\s+USER:\s+(.+?)\s+[—–-]\s+(.+)", block)
    if not heading_match:
        return None

    full_name = heading_match.group(1).strip()
    role = heading_match.group(2).strip()
    username = full_name.split()[0].lower()  # "risith", "santhosh", "ritvik"

    # Core Domain Expertise — paragraph text
    expertise_block = _extract_section(block, "Core Domain Expertise")
    expertise = expertise_block.strip()

    # Owned Sections — from table
    sections_block = _extract_section(block, "Owned Sections (Lead Authority)")
    owned_sections = _parse_section_numbers(sections_block)

    # Owned Keywords
    keywords_block = _extract_section(block, "Owned Keywords / Domain Terms")
    owned_keywords = _parse_backtick_list(keywords_block)

    # Exclude Keywords
    exclude_block = _extract_section(block, "Exclude Keywords (Other Members' Domains)")
    exclude_keywords = _parse_backtick_list(exclude_block)

    profile = UserProfile(
        username=username,
        display_name=full_name,
        role=role,
        expertise=expertise,
        owned_sections=owned_sections,
        owned_keywords=owned_keywords,
        exclude_keywords=exclude_keywords,
    )
    log.info(
        "Loaded profile: %s (%s) — %d sections, %d keywords, %d excludes",
        username, role, len(owned_sections), len(owned_keywords), len(exclude_keywords),
    )
    return profile


# ── Public API ────────────────────────────────────────────────────────

def load_profiles(path: Optional[Path] = None) -> dict[str, UserProfile]:
    """
    Parse NASAai_user_profiles.md and return {username: UserProfile}.
    """
    path = path or config.PROFILES_PATH
    text = path.read_text(encoding="utf-8")

    # Split on '# USER:' headings
    blocks = re.split(r"(?=^#\s+USER:)", text, flags=re.MULTILINE)

    profiles: dict[str, UserProfile] = {}
    for block in blocks:
        if "# USER:" not in block:
            continue
        profile = _parse_user_block(block)
        if profile:
            profiles[profile.username] = profile

    if not profiles:
        log.warning("No user profiles found in %s", path)
    return profiles


class UserSession:
    """Singleton holding the currently active user profile."""

    _instance: Optional[UserSession] = None
    _profile: Optional[UserProfile] = None

    def __new__(cls) -> UserSession:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @property
    def current_user(self) -> Optional[UserProfile]:
        return self._profile

    @current_user.setter
    def current_user(self, profile: UserProfile) -> None:
        self._profile = profile
        log.info("Active user set to: %s (%s)", profile.display_name, profile.role)
