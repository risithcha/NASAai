"""
Profile picker dialog — shown before the main overlay loads.

Dark-themed modal dialog with clickable user cards.
No authentication — click your name to sign in.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from accounts.user_profile import UserProfile

# Palette (matches overlay)
_DARK_BG = "#1E1E2E"
_CARD_BG = "#2A2A3C"
_CARD_HOVER = "#363650"
_TEXT_PRIMARY = "#C0CAF5"
_TEXT_SECONDARY = "#565F89"
_ACCENT_BLUE = "#7AA2F7"
_ACCENT_GREEN = "#9ECE6A"
_ACCENT_YELLOW = "#E0AF68"

# Per-role visual config
_ROLE_CONFIG: dict[str, dict] = {
    "Technical Lead": {"emoji": "🔧", "accent": _ACCENT_BLUE},
    "Mission Lead": {"emoji": "🎯", "accent": _ACCENT_GREEN},
    "Operations & Business Lead": {"emoji": "📊", "accent": _ACCENT_YELLOW},
}


class _UserCard(QWidget):
    """A single clickable user card."""

    def __init__(
        self,
        profile: UserProfile,
        on_click,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._profile = profile
        self._on_click = on_click

        cfg = _ROLE_CONFIG.get(profile.role, {"emoji": "👤", "accent": _ACCENT_BLUE})
        accent = cfg["accent"]
        emoji = cfg["emoji"]

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(200, 220)
        self.setObjectName("userCard")
        self._accent = accent
        self._set_style(False)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(8)
        layout.setContentsMargins(16, 20, 16, 20)

        # Emoji avatar
        avatar = QLabel(emoji)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar.setStyleSheet("font-size: 48px; background: transparent;")
        layout.addWidget(avatar)

        # Display name
        name_label = QLabel(profile.display_name.split()[0])  # first name
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_label.setStyleSheet(
            f"color: {_TEXT_PRIMARY}; font-size: 18px; font-weight: bold; background: transparent;"
        )
        layout.addWidget(name_label)

        # Role subtitle
        role_label = QLabel(profile.role)
        role_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        role_label.setWordWrap(True)
        role_label.setStyleSheet(
            f"color: {accent}; font-size: 12px; font-weight: 600; background: transparent;"
        )
        layout.addWidget(role_label)

    def _set_style(self, hovered: bool) -> None:
        bg = _CARD_HOVER if hovered else _CARD_BG
        self.setStyleSheet(
            f"""
            #userCard {{
                background-color: {bg};
                border: 2px solid {self._accent if hovered else _TEXT_SECONDARY};
                border-radius: 12px;
            }}
            """
        )

    def enterEvent(self, event) -> None:
        self._set_style(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._set_style(False)
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        self._on_click(self._profile)


class ProfilePickerDialog(QDialog):
    """Modal dialog for choosing which team member is using the app."""

    def __init__(
        self,
        profiles: dict[str, UserProfile],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._selected: Optional[UserProfile] = None
        self._profiles = profiles
        self._build_ui()

    @property
    def selected_profile(self) -> Optional[UserProfile]:
        return self._selected

    def _build_ui(self) -> None:
        self.setWindowTitle("NASA Meeting Assistant — Sign In")
        self.setFixedSize(700, 380)
        self.setStyleSheet(f"background-color: {_DARK_BG};")
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(20)

        # Header
        title = QLabel("🚀 NASA Meeting Assistant")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            f"color: {_TEXT_PRIMARY}; font-size: 22px; font-weight: bold;"
        )
        root.addWidget(title)

        subtitle = QLabel("Who's presenting today?")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet(
            f"color: {_TEXT_SECONDARY}; font-size: 14px;"
        )
        root.addWidget(subtitle)

        # User cards row
        cards_row = QHBoxLayout()
        cards_row.setSpacing(16)
        cards_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Fixed display order
        for username in ("risith", "santhosh", "ritvik"):
            profile = self._profiles.get(username)
            if profile:
                card = _UserCard(profile, self._on_select, self)
                cards_row.addWidget(card)

        root.addLayout(cards_row)

        # Footer
        footer = QLabel("Click your name to begin · AI responses will be scoped to your role")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer.setStyleSheet(
            f"color: {_TEXT_SECONDARY}; font-size: 11px;"
        )
        root.addWidget(footer)

    def _on_select(self, profile: UserProfile) -> None:
        self._selected = profile
        self.accept()
