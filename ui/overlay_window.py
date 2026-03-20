"""
Main overlay window: frameless, always-on-top, semi-transparent, drag-to-move.

All cross-thread UI updates are marshalled through Qt signals so that only
the GUI thread touches widgets.
"""

from __future__ import annotations

import ctypes
import logging
import sys
from typing import Optional

from PyQt6.QtCore import QPoint, Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

# Windows Display Affinity constants
WDA_NONE = 0x00000000
WDA_EXCLUDEFROMCAPTURE = 0x00000011

import config
from accounts.user_profile import UserProfile
from intelligence.pipeline import SuggestedResponse
from transcription.transcript_store import TranscriptSegment
from ui.ui_components import (
    ACCENT_GREEN,
    ACCENT_RED,
    ACCENT_YELLOW,
    DARK_BG,
    TEXT_SECONDARY,
    AlertCard,
    StatusBar,
    TranscriptPanel,
)

log = logging.getLogger(__name__)


class OverlayWindow(QWidget):
    """Primary always-on-top overlay."""

    # Signals (thread-safe bridge from worker → GUI)
    sig_segment = pyqtSignal(object)       # TranscriptSegment
    sig_interim = pyqtSignal(object)       # TranscriptSegment
    sig_response = pyqtSignal(object)      # SuggestedResponse
    sig_status = pyqtSignal(str, bool)     # (indicator_name, active)
    sig_error = pyqtSignal(str)            # (indicator_name,)

    def __init__(self, user_profile: UserProfile | None = None) -> None:
        super().__init__()
        self._drag_pos: Optional[QPoint] = None
        self._stealth_active = False
        self._user_profile = user_profile
        self._current_question_id: int = -1
        self._build_ui()
        self._connect_signals()

    # ── build ─────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.setWindowTitle("NASA Meeting Assistant")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setWindowOpacity(config.OVERLAY_OPACITY)
        self.resize(config.OVERLAY_WIDTH, config.OVERLAY_HEIGHT)

        # Move to top-right of screen
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self.move(geo.width() - config.OVERLAY_WIDTH - 20, 60)

        self.setStyleSheet(f"background-color: {DARK_BG};")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Title bar
        title_bar = self._make_title_bar()
        root.addWidget(title_bar)

        # Alert card (hidden initially, dismissed manually)
        self.alert_card = AlertCard()
        root.addWidget(self.alert_card)

        # Live transcript (takes remaining space)
        self.transcript_panel = TranscriptPanel()
        root.addWidget(self.transcript_panel, 1)

        # Status bar
        self.status_bar = StatusBar()
        root.addWidget(self.status_bar)

    def _make_title_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(32)
        bar.setStyleSheet(
            f"background-color: #16161E; border-bottom: 1px solid {TEXT_SECONDARY};"
        )
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(10, 0, 6, 0)

        from PyQt6.QtWidgets import QLabel

        if self._user_profile:
            name = self._user_profile.display_name.split()[0]
            role = self._user_profile.role
            title_text = f"🚀 {name} — {role}"
        else:
            title_text = "🚀 NASA Meeting Assistant"

        title = QLabel(title_text)
        title.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 12px; font-weight: bold;"
        )
        layout.addWidget(title, 1)

        # Stealth toggle button (hide from screen capture)
        self._stealth_btn = QPushButton("👁")
        self._stealth_btn.setFixedSize(24, 24)
        self._stealth_btn.setToolTip("Toggle stealth mode (hide from screen capture)")
        self._stealth_btn.setStyleSheet(
            f"""
            QPushButton {{
                background: transparent;
                color: {TEXT_SECONDARY};
                border: none;
                font-size: 14px;
            }}
            QPushButton:hover {{
                color: {ACCENT_YELLOW};
            }}
            """
        )
        self._stealth_btn.clicked.connect(self._toggle_stealth)
        layout.addWidget(self._stealth_btn)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setStyleSheet(
            f"""
            QPushButton {{
                background: transparent;
                color: {TEXT_SECONDARY};
                border: none;
                font-size: 14px;
            }}
            QPushButton:hover {{
                color: {ACCENT_RED};
            }}
            """
        )
        close_btn.clicked.connect(QApplication.instance().quit)
        layout.addWidget(close_btn)

        return bar

    # ── signal wiring ─────────────────────────────────────────────────

    def _connect_signals(self) -> None:
        self.sig_segment.connect(self._on_segment)
        self.sig_interim.connect(self._on_interim)
        self.sig_response.connect(self._on_response)
        self.sig_status.connect(self._on_status)
        self.sig_error.connect(self._on_error)
        self.alert_card.dismissed.connect(self.transcript_panel.expand)

    # ── slots (always on GUI thread) ──────────────────────────────────

    @pyqtSlot(object)
    def _on_segment(self, seg: TranscriptSegment) -> None:
        self.transcript_panel.append_segment(seg.speaker, seg.text, seg.is_final)

    @pyqtSlot(object)
    def _on_interim(self, seg: TranscriptSegment) -> None:
        self.transcript_panel.set_interim(seg.speaker, seg.text)

    @pyqtSlot(object)
    def _on_response(self, resp: SuggestedResponse) -> None:
        # Redirect: question belongs to another user
        if resp.redirect_to:
            self._current_question_id = resp.question_id
            self.alert_card.show_redirect(resp.question, resp.redirect_to)
            return
        # New question — append a new block
        if resp.question_id != self._current_question_id:
            self._current_question_id = resp.question_id
            self.alert_card.show_question(resp.question, hint_to=resp.hint_to or "")
            self.transcript_panel.collapse()
        # Streaming update for the current question
        if resp.is_streaming:
            self.alert_card.update_response(resp.bullets, resp.answer, streaming=True)
        else:
            self.alert_card.finish_response(resp.bullets, resp.answer)

    @pyqtSlot(str, bool)
    def _on_status(self, name: str, active: bool) -> None:
        indicator = getattr(self.status_bar, f"{name}_indicator", None)
        if indicator:
            indicator.set_active(active)

    @pyqtSlot(str)
    def _on_error(self, name: str) -> None:
        indicator = getattr(self.status_bar, f"{name}_indicator", None)
        if indicator:
            indicator.set_error()

    # ── public helpers for worker threads ─────────────────────────────

    def post_segment(self, seg: TranscriptSegment) -> None:
        """Thread-safe: emit segment to GUI."""
        self.sig_segment.emit(seg)

    def post_interim(self, seg: TranscriptSegment) -> None:
        self.sig_interim.emit(seg)

    def post_response(self, resp: SuggestedResponse) -> None:
        self.sig_response.emit(resp)

    def set_status(self, name: str, active: bool) -> None:
        self.sig_status.emit(name, active)

    def set_error(self, name: str) -> None:
        self.sig_error.emit(name)

    # ── drag to move ──────────────────────────────────────────────────

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_pos and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_pos = None

    # ── screen capture hiding (Windows) ───────────────────────────────

    def showEvent(self, event) -> None:
        """Apply stealth mode automatically when the window first appears."""
        super().showEvent(event)
        if sys.platform == "win32":
            self._set_display_affinity(WDA_EXCLUDEFROMCAPTURE)

    def _set_display_affinity(self, affinity: int) -> bool:
        """Call SetWindowDisplayAffinity via ctypes. Returns True on success."""
        if sys.platform != "win32":
            return False
        try:
            hwnd = int(self.winId())
            result = ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, affinity)
            success = result != 0
            if success:
                self._stealth_active = (affinity == WDA_EXCLUDEFROMCAPTURE)
                log.info("Display affinity set to 0x%X (stealth=%s)", affinity, self._stealth_active)
            else:
                err = ctypes.GetLastError()
                log.warning("SetWindowDisplayAffinity failed (error %d)", err)
            self._update_stealth_ui()
            return success
        except Exception:
            log.exception("Failed to set display affinity")
            return False

    def _toggle_stealth(self) -> None:
        """Toggle between hidden and visible in screen capture."""
        new_affinity = WDA_NONE if self._stealth_active else WDA_EXCLUDEFROMCAPTURE
        self._set_display_affinity(new_affinity)

    def _update_stealth_ui(self) -> None:
        """Update the stealth button appearance based on current state."""
        if self._stealth_active:
            self._stealth_btn.setText("🛡")
            self._stealth_btn.setToolTip("Stealth ON — hidden from screen capture (click to disable)")
            self._stealth_btn.setStyleSheet(
                f"""
                QPushButton {{
                    background: transparent;
                    color: {ACCENT_GREEN};
                    border: none;
                    font-size: 14px;
                }}
                QPushButton:hover {{
                    color: {ACCENT_YELLOW};
                }}
                """
            )
            self.status_bar.stealth_indicator.set_active(True)
        else:
            self._stealth_btn.setText("👁")
            self._stealth_btn.setToolTip("Stealth OFF — visible in screen capture (click to enable)")
            self._stealth_btn.setStyleSheet(
                f"""
                QPushButton {{
                    background: transparent;
                    color: {TEXT_SECONDARY};
                    border: none;
                    font-size: 14px;
                }}
                QPushButton:hover {{
                    color: {ACCENT_YELLOW};
                }}
                """
            )
            self.status_bar.stealth_indicator.set_active(False)
