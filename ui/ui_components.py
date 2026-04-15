"""
Reusable PyQt6 widgets for the overlay window.

- TranscriptPanel: scrolling live transcript with speaker colours.
- AlertCard:       question + AI-generated talking-points.
- StatusBar:       connection / recording / processing indicators.
"""

from __future__ import annotations

import logging
import time
from typing import List

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor

log = logging.getLogger(__name__)
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
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
    "Speaker 0": ACCENT_BLUE,
    "Speaker 1": ACCENT_GREEN,
    "Speaker 2": ACCENT_YELLOW,
    "Speaker 3": "#BB9AF7",
    "Speaker 4": "#FF9E64",
    "Speaker": ACCENT_BLUE,
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
        self._interim_pos: int | None = None   # char offset where interim block starts

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._header = QLabel("LIVE TRANSCRIPT")
        self._header.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 11px; font-weight: bold; padding: 4px 8px;"
        )
        layout.addWidget(self._header)

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
        # If a final segment arrives, wipe any pending interim first
        if is_final:
            self._clear_interim()

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
        """Replace the current interim preview line in-place."""
        # Delete previous interim block if any
        self._clear_interim()

        # Record where the new interim starts
        cursor = self._text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self._interim_pos = cursor.position()

        # Insert interim content
        fmt_speaker = QTextCharFormat()
        fmt_speaker.setForeground(QColor(_speaker_colour(speaker)))
        fmt_speaker.setFontWeight(700)
        fmt_speaker.setFontItalic(True)
        cursor.insertText(f"{speaker}: ", fmt_speaker)

        fmt_body = QTextCharFormat()
        fmt_body.setForeground(QColor(TEXT_INTERIM))
        fmt_body.setFontItalic(True)
        cursor.insertText(text + "\n", fmt_body)

        if self._auto_scroll:
            sb = self._text.verticalScrollBar()
            sb.setValue(sb.maximum())

    def _clear_interim(self) -> None:
        """Remove the current interim preview text if present."""
        if self._interim_pos is None:
            return
        cursor = self._text.textCursor()
        cursor.setPosition(self._interim_pos)
        cursor.movePosition(QTextCursor.MoveOperation.End, QTextCursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText()
        self._interim_pos = None

    def clear(self) -> None:
        self._text.clear()

    def collapse(self) -> None:
        """Shrink to a thin strip showing only the latest transcript line."""
        self._header.hide()
        self.setFixedHeight(50)

    def expand(self) -> None:
        """Restore full transcript panel height."""
        self._header.show()
        self.setMinimumHeight(0)
        self.setMaximumHeight(16777215)  # QWIDGETSIZE_MAX


# ── Alert Card ────────────────────────────────────────────────────────

class _QABlock(QFrame):
    """A single question-and-answer block displayed inside the AlertCard history.

    Layout (top → bottom):
        Question (italic)  →  Bullets (talking points)  →  Divider  →
        "What to say:" header  →  Answer (green, bold, spoken-ready paragraph)
    """

    def __init__(self, question: str, is_redirect: bool = False,
                 redirect_to: str = "", hint_to: str = "",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._is_redirect = is_redirect
        self._hint_label: QLabel | None = None
        self._hint_to = hint_to
        self._created_at = time.time()
        log.debug("QABlock CREATED: question='%s' redirect=%s redirect_to='%s' hint_to='%s'",
                  question[:60], is_redirect, redirect_to, hint_to)
        self._build_ui(question, is_redirect, redirect_to, hint_to)

    def _build_ui(self, question: str, is_redirect: bool,
                  redirect_to: str, hint_to: str) -> None:
        if is_redirect:
            border_colour = TEXT_SECONDARY
        elif hint_to:
            border_colour = ACCENT_BLUE
        else:
            border_colour = ACCENT_YELLOW
        self.setStyleSheet(
            f"background-color: {CARD_BG}; border: none; "
            f"border-left: 3px solid {border_colour}; padding: 4px 0;"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 4, 4)
        layout.setSpacing(3)

        # Question text
        self._question_label = QLabel(f'"{question}"')
        self._question_label.setWordWrap(True)
        self._question_label.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 13px; font-style: italic; padding: 0;"
        )
        layout.addWidget(self._question_label)

        if is_redirect:
            redir_label = QLabel(
                f'<span style="color:{TEXT_SECONDARY}">This one\'s for '
                f'<b style="color:{ACCENT_BLUE}">{redirect_to}</b> — sit tight.</span>'
            )
            redir_label.setWordWrap(True)
            redir_label.setTextFormat(Qt.TextFormat.RichText)
            redir_label.setStyleSheet("font-size: 12px; padding: 0;")
            layout.addWidget(redir_label)
            return

        # Soft hint banner (off-domain but still answering)
        # Created hidden initially; shown when routing result arrives (may be async)
        self._hint_label = QLabel()
        self._hint_label.setWordWrap(True)
        self._hint_label.setTextFormat(Qt.TextFormat.RichText)
        self._hint_label.setStyleSheet("font-size: 11px; padding: 0 0 2px 0;")
        if hint_to:
            self._hint_label.setText(
                f'<span style="color:{ACCENT_BLUE}">ℹ️ This might be more for '
                f'<b>{hint_to}</b> — here\'s what you can say:</span>'
            )
            self._hint_label.setVisible(True)
        else:
            self._hint_label.setVisible(False)
        layout.addWidget(self._hint_label)

        # Bullet talking-points (top section)
        self._bullets_label = QLabel()
        self._bullets_label.setWordWrap(True)
        self._bullets_label.setTextFormat(Qt.TextFormat.RichText)
        self._bullets_label.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 12px; padding: 0;"
        )
        layout.addWidget(self._bullets_label)

        # Thin divider
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFixedHeight(1)
        divider.setStyleSheet(f"background-color: {TEXT_SECONDARY}; border: none;")
        layout.addWidget(divider)

        # "What to say:" sub-header
        say_header = QLabel("What to say:")
        say_header.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 10px; padding: 2px 0 0 0;"
        )
        layout.addWidget(say_header)

        # Spoken-ready answer (green, bold — bottom section)
        self._answer_label = QLabel()
        self._answer_label.setWordWrap(True)
        self._answer_label.setTextFormat(Qt.TextFormat.RichText)
        self._answer_label.setStyleSheet(
            f"color: {ACCENT_GREEN}; font-size: 13px; font-weight: bold; padding: 0;"
        )
        layout.addWidget(self._answer_label)

    # ── public setters (called during streaming) ──────────────────────

    def set_loading(self) -> None:
        gen = f'<span style="color:{TEXT_SECONDARY}">Generating…</span>'
        self._bullets_label.setText(gen)
        self._answer_label.setText(gen)

    def update_hint(self, hint_to: str) -> None:
        """Update the hint banner after block creation (e.g. async routing)."""
        if self._is_redirect or not hint_to or hint_to == self._hint_to:
            log.debug("QABlock update_hint SKIP: is_redirect=%s hint_to='%s' same=%s",
                      self._is_redirect, hint_to, hint_to == self._hint_to)
            return
        age_ms = (time.time() - self._created_at) * 1000
        log.info("QABlock update_hint: '%s' → '%s' (%.0fms after block created)",
                 self._hint_to, hint_to, age_ms)
        self._hint_to = hint_to
        if self._hint_label is not None:
            self._hint_label.setText(
                f'<span style="color:{ACCENT_BLUE}">ℹ️ This might be more for '
                f'<b>{hint_to}</b> — here\'s what you can say:</span>'
            )
            self._hint_label.setVisible(True)
        # Update border colour to blue
        self.setStyleSheet(
            f"background-color: {CARD_BG}; border: none; "
            f"border-left: 3px solid {ACCENT_BLUE}; padding: 4px 0;"
        )

    def set_dual_response(self, bullets: str, answer: str,
                          streaming: bool = True) -> None:
        """Update both the bullets and answer sections simultaneously."""
        # Bullets
        if bullets:
            b_html = _md_to_html(bullets)
            if streaming:
                b_html += f' <span style="color:{ACCENT_BLUE}">▌</span>'
            self._bullets_label.setText(b_html)
        elif streaming:
            self._bullets_label.setText(
                f'<span style="color:{TEXT_SECONDARY}">Generating…</span>'
            )
        # Answer
        if answer:
            a_html = _md_to_html(answer)
            if streaming:
                a_html += f' <span style="color:{ACCENT_BLUE}">▌</span>'
            self._answer_label.setText(a_html)
        elif streaming:
            self._answer_label.setText(
                f'<span style="color:{TEXT_SECONDARY}">Generating…</span>'
            )


def _md_to_html(text: str) -> str:
    """Minimal markdown → html: bullets, bold."""
    import re
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
    html = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", html)
    return html


class AlertCard(QFrame):
    """
    Scrollable Q&A history card.

    Stacks multiple _QABlock widgets; auto-updates when new questions arrive.
    'Got it' button hides the card and clears history.
    """

    dismissed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._active_block: _QABlock | None = None
        self._blocks: list[_QABlock] = []
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
            }}
            """
        )
        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(4)

        # Header row (outside scroll)
        header_row = QHBoxLayout()
        icon_lbl = QLabel("❓")
        icon_lbl.setStyleSheet("font-size: 16px;")
        self._header_label = QLabel("Question Detected")
        self._header_label.setStyleSheet(
            f"color: {ACCENT_YELLOW}; font-size: 12px; font-weight: bold;"
        )
        header_row.addWidget(icon_lbl)
        header_row.addWidget(self._header_label, 1)

        self._dismiss_btn = QPushButton("✕ Got it")
        self._dismiss_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._dismiss_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {TEXT_SECONDARY};
                color: {DARK_BG};
                border: none;
                border-radius: 4px;
                padding: 2px 10px;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {ACCENT_YELLOW};
            }}
            """
        )
        self._dismiss_btn.clicked.connect(self.dismiss)
        header_row.addWidget(self._dismiss_btn)
        outer.addLayout(header_row)

        # Scrollable history area
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setStyleSheet(
            f"""
            QScrollArea {{
                background-color: {CARD_BG};
                border: none;
            }}
            QScrollBar:vertical {{
                background: {CARD_BG};
                width: 6px;
            }}
            QScrollBar::handle:vertical {{
                background: {TEXT_SECONDARY};
                border-radius: 3px;
                min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            """
        )

        self._history_widget = QWidget()
        self._history_widget.setStyleSheet(f"background-color: {CARD_BG};")
        self._history_layout = QVBoxLayout(self._history_widget)
        self._history_layout.setContentsMargins(0, 0, 0, 0)
        self._history_layout.setSpacing(6)
        self._history_layout.addStretch()  # keeps blocks top-aligned

        self._scroll.setWidget(self._history_widget)
        outer.addWidget(self._scroll, 1)

    # ── auto-scroll helper ────────────────────────────────────────────

    def _is_near_bottom(self) -> bool:
        """True when the user hasn't scrolled up (or is within 40px of the bottom)."""
        sb = self._scroll.verticalScrollBar()
        return sb.value() >= sb.maximum() - 40

    def _scroll_to_bottom(self, force: bool = False) -> None:
        """Scroll to bottom only if user is already near the bottom (or *force*)."""
        if not force and not self._is_near_bottom():
            return
        QTimer.singleShot(0, lambda: self._scroll.verticalScrollBar().setValue(
            self._scroll.verticalScrollBar().maximum()
        ))

    # ── public API ────────────────────────────────────────────────────

    def show_question(self, question: str, hint_to: str = "") -> None:
        """Append a new Q&A block for an incoming question."""
        log.info("AlertCard show_question: '%s' hint_to='%s' (block count: %d)",
                 question[:60], hint_to, len(self._blocks))
        self._header_label.setText("Question Detected")
        self._header_label.setStyleSheet(
            f"color: {ACCENT_YELLOW}; font-size: 12px; font-weight: bold;"
        )
        block = _QABlock(question, hint_to=hint_to)
        block.set_loading()
        # Insert before the trailing stretch
        self._history_layout.insertWidget(self._history_layout.count() - 1, block)
        self._blocks.append(block)
        self._active_block = block
        self._dismiss_btn.setVisible(True)
        self.show()
        # Force-scroll for a brand-new question so the user sees it
        self._scroll_to_bottom(force=True)

    def update_hint(self, hint_to: str) -> None:
        """Update the hint banner on the active block (async routing)."""
        if self._active_block:
            log.debug("AlertCard update_hint: forwarding '%s' to active block", hint_to)
            self._active_block.update_hint(hint_to)
        else:
            log.warning("AlertCard update_hint: NO active block to update (hint='%s')", hint_to)

    def update_response(self, bullets: str, answer: str,
                        streaming: bool = True) -> None:
        if self._active_block and not self._active_block._is_redirect:
            self._active_block.set_dual_response(bullets, answer, streaming)
            self._scroll_to_bottom()

    def finish_response(self, bullets: str, answer: str) -> None:
        self.update_response(bullets, answer, streaming=False)
        self._dismiss_btn.setVisible(True)

    def dismiss(self) -> None:
        self.hide()
        self.clear_history()
        self.dismissed.emit()

    def show_redirect(self, question: str, redirect_to: str) -> None:
        """Append a redirect notification block.

        If the active block is a non-redirect QA block (e.g. a stale
        "Generating..." placeholder from before routing finished), remove
        it first so we don't leave an orphaned block.
        """
        log.info("AlertCard show_redirect: '%s' → '%s' (active_block=%s)",
                 question[:60], redirect_to,
                 "redirect" if self._active_block and self._active_block._is_redirect
                 else "qa" if self._active_block else "None")
        # Remove stale placeholder QA block if one exists
        if self._active_block and not self._active_block._is_redirect:
            log.debug("AlertCard show_redirect: removing stale QA block before redirect")
            self._history_layout.removeWidget(self._active_block)
            self._active_block.deleteLater()
            self._blocks.remove(self._active_block)
            self._active_block = None

        block = _QABlock(question, is_redirect=True, redirect_to=redirect_to)
        self._history_layout.insertWidget(self._history_layout.count() - 1, block)
        self._blocks.append(block)
        self._active_block = block
        self._dismiss_btn.setVisible(True)
        self.show()
        self._scroll_to_bottom(force=True)

    def clear_history(self) -> None:
        """Remove all Q&A blocks."""
        for block in self._blocks:
            self._history_layout.removeWidget(block)
            block.deleteLater()
        self._blocks.clear()
        self._active_block = None


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
        self.stealth_indicator = StatusIndicator("Stealth")

        layout.addWidget(self.audio_indicator)
        layout.addWidget(self.deepgram_indicator)
        layout.addWidget(self.ai_indicator)
        layout.addStretch()
        layout.addWidget(self.stealth_indicator)

        self.setStyleSheet(
            f"background-color: #16161E; border-top: 1px solid {TEXT_SECONDARY};"
        )
