"""
Main overlay window: frameless, always-on-top, semi-transparent, drag-to-move.

All cross-thread UI updates are marshalled through Qt signals so that only
the GUI thread touches widgets.
"""

from __future__ import annotations

import logging
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

import config
from intelligence.pipeline import SuggestedResponse
from transcription.transcript_store import TranscriptSegment
from ui.ui_components import (
    ACCENT_RED,
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

    def __init__(self) -> None:
        super().__init__()
        self._drag_pos: Optional[QPoint] = None
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

        # Alert card (hidden initially)
        self.alert_card = AlertCard(dismiss_sec=45)
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

        title = QLabel("🚀 NASA Meeting Assistant")
        title.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 12px; font-weight: bold;"
        )
        layout.addWidget(title, 1)

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

    # ── slots (always on GUI thread) ──────────────────────────────────

    @pyqtSlot(object)
    def _on_segment(self, seg: TranscriptSegment) -> None:
        self.transcript_panel.append_segment(seg.speaker, seg.text, seg.is_final)

    @pyqtSlot(object)
    def _on_interim(self, seg: TranscriptSegment) -> None:
        self.transcript_panel.set_interim(seg.speaker, seg.text)

    @pyqtSlot(object)
    def _on_response(self, resp: SuggestedResponse) -> None:
        if resp.is_streaming and not self.alert_card.isVisible():
            self.alert_card.show_question(resp.question)
        if resp.is_streaming:
            self.alert_card.update_response(resp.response, streaming=True)
        else:
            self.alert_card.finish_response(resp.response)

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
