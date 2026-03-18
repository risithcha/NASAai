"""
Reusable PyQt6 widgets for the overlay window.

- TranscriptPanel: scrolling live transcript with speaker colours.
- AlertCard:       question + AI-generated talking-points.
- StatusBar:       connection / recording / processing indicators.
"""

from __future__ import annotations

import time
from typing import List

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

# ── colour palette ────────────────────────────────────────────────────
DARK_BG = "#1E1E2E"
CARD_BG = "#2A2A3C"
ACCENT_BLUE = "#7AA2F7"
ACCENT_GREEN = "#9ECE6A"
ACCENT_YELLOW = "#E0AF68"
ACCENT_RED = "#F7768E"
TEXT_PRIMARY = "#C0CAF5"
TEXT_SECONDARY = "#565F89"
TEXT_INTERIM = "#565F89"

SPEAKER_COLOURS: dict[str, str] = {
    "You": ACCENT_GREEN,
    "Speaker 0": ACCENT_BLUE,
    "Speaker 1": ACCENT_YELLOW,
    "Speaker 2": "#BB9AF7",
    "Speaker 3": "#FF9E64",
}


def _speaker_colour(speaker: str) -> str:
    return SPEAKER_COLOURS.get(speaker, ACCENT_BLUE)


# ── Transcript Panel ──────────────────────────────────────────────────

class TranscriptPanel(QWidget):
    """Live scrolling transcript with colour-coded speakers."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()
        self._auto_scroll = True

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        header = QLabel("LIVE TRANSCRIPT")
        header.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 11px; font-weight: bold; padding: 4px 8px;"
        )
        layout.addWidget(header)

        self._text = QTextEdit()
        self._text.setReadOnly(True)
        self._text.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._text.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._text.setStyleSheet(
            f"""
            QTextEdit {{
                background-color: {DARK_BG};
                color: {TEXT_PRIMARY};
                border: none;
                padding: 6px 10px;
                font-family: 'Cascadia Code', 'Consolas', monospace;
                font-size: 13px;
            }}
            """
        )
        layout.addWidget(self._text)

    # ── public API ────────────────────────────────────────────────────

    def append_segment(self, speaker: str, text: str, is_final: bool = True) -> None:
        """Append one transcript segment (thread-safe via Qt signals)."""
        cursor = self._text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        # Speaker label
        fmt_speaker = QTextCharFormat()
        fmt_speaker.setForeground(QColor(_speaker_colour(speaker)))
        fmt_speaker.setFontWeight(700)
        cursor.insertText(f"{speaker}: ", fmt_speaker)

        # Transcript body
        fmt_body = QTextCharFormat()
        colour = TEXT_PRIMARY if is_final else TEXT_INTERIM
        fmt_body.setForeground(QColor(colour))
        if not is_final:
            fmt_body.setFontItalic(True)
        cursor.insertText(text + "\n", fmt_body)

        # Auto-scroll
        if self._auto_scroll:
            sb = self._text.verticalScrollBar()
            sb.setValue(sb.maximum())

    def set_interim(self, speaker: str, text: str) -> None:
        """Replace or append an interim (partial) segment."""
        self.append_segment(speaker, text, is_final=False)

    def clear(self) -> None:
        self._text.clear()


# ── Alert Card ────────────────────────────────────────────────────────

class AlertCard(QFrame):
    """
    Displays a detected question and the AI-suggested talking points.
    Auto-dismisses after ``dismiss_sec`` seconds.
    """

    dismissed = pyqtSignal()

    def __init__(
        self, dismiss_sec: int = 45, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._dismiss_sec = dismiss_sec
        self._build_ui()
        self.hide()

    def _build_ui(self) -> None:
        self.setObjectName("alertCard")
        self.setStyleSheet(
            f"""
            #alertCard {{
                background-color: {CARD_BG};
                border: 1px solid {ACCENT_YELLOW};
                border-radius: 8px;
                padding: 10px;
            }}
            """
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        # Header row
        header_row = QHBoxLayout()
        icon_lbl = QLabel("❓")
        icon_lbl.setStyleSheet("font-size: 16px;")
        self._header_label = QLabel("Question Detected")
        self._header_label.setStyleSheet(
            f"color: {ACCENT_YELLOW}; font-size: 12px; font-weight: bold;"
        )
        header_row.addWidget(icon_lbl)
        header_row.addWidget(self._header_label, 1)
        self._timer_label = QLabel("")
        self._timer_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
        header_row.addWidget(self._timer_label)
        layout.addLayout(header_row)

        # Question text
        self._question_label = QLabel()
        self._question_label.setWordWrap(True)
        self._question_label.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 13px; font-style: italic; padding: 2px 0;"
        )
        layout.addWidget(self._question_label)

        # Divider
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet(f"color: {TEXT_SECONDARY};")
        layout.addWidget(divider)

        # Response / talking points
        self._response_label = QLabel()
        self._response_label.setWordWrap(True)
        self._response_label.setTextFormat(Qt.TextFormat.RichText)
        self._response_label.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 13px; line-height: 1.5;"
        )
        layout.addWidget(self._response_label)

        # Auto-dismiss timer
        self._countdown = 0
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)

    # ── public API ────────────────────────────────────────────────────

    def show_question(self, question: str) -> None:
        self._question_label.setText(f'"{question}"')
        self._response_label.setText(
            f'<span style="color:{TEXT_SECONDARY}">Generating talking points…</span>'
        )
        self._countdown = self._dismiss_sec
        self._timer_label.setText(f"{self._countdown}s")
        self._timer.start()
        self.show()

    def update_response(self, response_text: str, streaming: bool = True) -> None:
        """Update the response area. ``response_text`` may contain markdown-ish bullets."""
        html = self._md_to_html(response_text)
        if streaming:
            html += f' <span style="color:{ACCENT_BLUE}">▌</span>'
        self._response_label.setText(html)

    def finish_response(self, response_text: str) -> None:
        self.update_response(response_text, streaming=False)

    def dismiss(self) -> None:
        self._timer.stop()
        self.hide()
        self.dismissed.emit()

    # ── internal ──────────────────────────────────────────────────────

    def _tick(self) -> None:
        self._countdown -= 1
        self._timer_label.setText(f"{self._countdown}s")
        if self._countdown <= 0:
            self.dismiss()

    @staticmethod
    def _md_to_html(text: str) -> str:
        """Minimal markdown → html: bullets, bold."""
        lines = text.split("\n")
        out: list[str] = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("- ") or stripped.startswith("• "):
                stripped = stripped[2:]
                out.append(f"&bull; {stripped}<br/>")
            elif stripped.startswith("* "):
                stripped = stripped[2:]
                out.append(f"&bull; {stripped}<br/>")
            elif stripped:
                out.append(f"{stripped}<br/>")
        html = "".join(out)
        # Bold markers **text**
        import re
        html = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", html)
        return html


# ── Status Bar ────────────────────────────────────────────────────────

class StatusIndicator(QWidget):
    """A single coloured dot with a label."""

    def __init__(self, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self._dot = QLabel("●")
        self._dot.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 10px;")
        self._label = QLabel(label)
        self._label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
        layout.addWidget(self._dot)
        layout.addWidget(self._label)

    def set_active(self, active: bool) -> None:
        colour = ACCENT_GREEN if active else TEXT_SECONDARY
        self._dot.setStyleSheet(f"color: {colour}; font-size: 10px;")

    def set_error(self) -> None:
        self._dot.setStyleSheet(f"color: {ACCENT_RED}; font-size: 10px;")


class StatusBar(QWidget):
    """Bottom status bar with connection/recording/processing indicators."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(28)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(16)

        self.audio_indicator = StatusIndicator("Audio")
        self.deepgram_indicator = StatusIndicator("Deepgram")
        self.ai_indicator = StatusIndicator("AI")

        layout.addWidget(self.audio_indicator)
        layout.addWidget(self.deepgram_indicator)
        layout.addWidget(self.ai_indicator)
        layout.addStretch()

        self.setStyleSheet(
            f"background-color: #16161E; border-top: 1px solid {TEXT_SECONDARY};"
        )
