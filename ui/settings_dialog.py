"""
Tabbed settings dialog — opened from the gear icon in the overlay title bar.

Six tabs: General, Audio, Transcription, Intelligence, Speaker, Appearance.
Each tab has an optional "Show Advanced" toggle that reveals power-user settings.
Dark themed to match the overlay palette.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from settings.settings_manager import RESTART_REQUIRED_KEYS, settings
from ui.ui_components import (
    ACCENT_BLUE,
    ACCENT_GREEN,
    ACCENT_RED,
    ACCENT_YELLOW,
    CARD_BG,
    DARK_BG,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)

log = logging.getLogger(__name__)

# ── Stylesheet ────────────────────────────────────────────────────────

_DIALOG_SS = f"""
QDialog {{
    background-color: {DARK_BG};
}}
QTabWidget::pane {{
    border: 1px solid {TEXT_SECONDARY};
    background-color: {DARK_BG};
    border-radius: 4px;
}}
QTabBar::tab {{
    background: {CARD_BG};
    color: {TEXT_SECONDARY};
    padding: 6px 14px;
    margin-right: 2px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}}
QTabBar::tab:selected {{
    background: {DARK_BG};
    color: {TEXT_PRIMARY};
    border-bottom: 2px solid {ACCENT_BLUE};
}}
QLabel {{
    color: {TEXT_PRIMARY};
    font-size: 12px;
}}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    background-color: {CARD_BG};
    color: {TEXT_PRIMARY};
    border: 1px solid {TEXT_SECONDARY};
    border-radius: 4px;
    padding: 4px 6px;
    font-size: 12px;
    min-height: 22px;
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 1px solid {ACCENT_BLUE};
}}
QCheckBox {{
    color: {TEXT_PRIMARY};
    font-size: 12px;
    spacing: 6px;
}}
QCheckBox::indicator {{
    width: 16px; height: 16px;
    border: 1px solid {TEXT_SECONDARY};
    border-radius: 3px;
    background: {CARD_BG};
}}
QCheckBox::indicator:checked {{
    background: {ACCENT_BLUE};
    border-color: {ACCENT_BLUE};
}}
QPushButton {{
    background-color: {CARD_BG};
    color: {TEXT_PRIMARY};
    border: 1px solid {TEXT_SECONDARY};
    border-radius: 4px;
    padding: 5px 14px;
    font-size: 12px;
}}
QPushButton:hover {{
    border-color: {ACCENT_BLUE};
    color: {ACCENT_BLUE};
}}
QPushButton#okBtn {{
    background-color: {ACCENT_BLUE};
    color: {DARK_BG};
    font-weight: bold;
    border: none;
}}
QPushButton#okBtn:hover {{
    background-color: #8FB2FF;
}}
QSlider::groove:horizontal {{
    height: 6px;
    background: {CARD_BG};
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    width: 14px; height: 14px;
    margin: -4px 0;
    background: {ACCENT_BLUE};
    border-radius: 7px;
}}
QSlider::sub-page:horizontal {{
    background: {ACCENT_BLUE};
    border-radius: 3px;
}}
"""

# ── Helper to enumerate audio devices ─────────────────────────────────

def enumerate_audio_devices() -> list[dict]:
    """Return a list of audio device dicts with keys: index, name, is_loopback, is_input."""
    devices: list[dict] = []
    try:
        import pyaudiowpatch as pyaudio
        pa = pyaudio.PyAudio()
        try:
            for i in range(pa.get_device_count()):
                info = pa.get_device_info_by_index(i)
                devices.append({
                    "index": info["index"],
                    "name": info["name"],
                    "is_loopback": bool(info.get("isLoopbackDevice", False)),
                    "is_input": info.get("maxInputChannels", 0) > 0,
                })
        finally:
            pa.terminate()
    except Exception:
        log.exception("Failed to enumerate audio devices")
    return devices


# ── Tab Builder Helpers ───────────────────────────────────────────────

class _SettingsTab(QWidget):
    """Base for a single settings tab with optional advanced toggle."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._form = QFormLayout()
        self._form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self._form.setContentsMargins(16, 12, 16, 8)
        self._form.setSpacing(10)

        self._advanced_rows: list[tuple[QWidget, QWidget | None]] = []
        self._advanced_visible = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addLayout(self._form)

        self._adv_toggle = QCheckBox("Show Advanced")
        self._adv_toggle.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
        self._adv_toggle.toggled.connect(self._on_adv_toggle)
        outer.addWidget(self._adv_toggle, alignment=Qt.AlignmentFlag.AlignLeft)
        outer.addStretch()

    def add_row(self, label: str, widget: QWidget, advanced: bool = False) -> None:
        lbl = QLabel(label)
        self._form.addRow(lbl, widget)
        if advanced:
            self._advanced_rows.append((lbl, widget))
            lbl.setVisible(False)
            widget.setVisible(False)

    def add_widget_row(self, widget: QWidget, advanced: bool = False) -> None:
        self._form.addRow(widget)
        if advanced:
            self._advanced_rows.append((widget, None))
            widget.setVisible(False)

    def _on_adv_toggle(self, checked: bool) -> None:
        self._advanced_visible = checked
        for lbl, w in self._advanced_rows:
            lbl.setVisible(checked)
            if w is not None:
                w.setVisible(checked)

    @property
    def has_advanced(self) -> bool:
        return len(self._advanced_rows) > 0


# ── Per-tab builder functions ─────────────────────────────────────────

def _make_api_key_row(current: str) -> tuple[QLineEdit, QPushButton]:
    """Create a password-masked QLineEdit + reveal toggle button."""
    edit = QLineEdit(current)
    edit.setEchoMode(QLineEdit.EchoMode.Password)
    edit.setPlaceholderText("Enter API key…")
    btn = QPushButton("👁")
    btn.setFixedSize(28, 28)
    btn.setToolTip("Show / hide key")
    btn.setCheckable(True)
    btn.toggled.connect(
        lambda checked: edit.setEchoMode(
            QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        )
    )
    return edit, btn


def _build_general_tab() -> tuple[_SettingsTab, dict[str, Any]]:
    tab = _SettingsTab()
    widgets: dict[str, Any] = {}

    # Deepgram key
    dg_edit, dg_reveal = _make_api_key_row(settings.get("general.deepgram_api_key"))
    row = QHBoxLayout()
    row.addWidget(dg_edit)
    row.addWidget(dg_reveal)
    container = QWidget()
    container.setLayout(row)
    tab.add_row("Deepgram API Key", container)
    widgets["general.deepgram_api_key"] = dg_edit

    # OpenAI key
    oai_edit, oai_reveal = _make_api_key_row(settings.get("general.openai_api_key"))
    row2 = QHBoxLayout()
    row2.addWidget(oai_edit)
    row2.addWidget(oai_reveal)
    container2 = QWidget()
    container2.setLayout(row2)
    tab.add_row("OpenAI API Key", container2)
    widgets["general.openai_api_key"] = oai_edit

    # PDF path
    pdf_edit = QLineEdit(settings.get("general.pdf_path"))
    pdf_btn = QPushButton("Browse…")
    pdf_btn.setFixedWidth(72)
    pdf_btn.clicked.connect(
        lambda: _browse_pdf(pdf_edit)
    )
    row3 = QHBoxLayout()
    row3.addWidget(pdf_edit)
    row3.addWidget(pdf_btn)
    container3 = QWidget()
    container3.setLayout(row3)
    tab.add_row("PDF Path", container3)
    widgets["general.pdf_path"] = pdf_edit

    # Log level
    log_combo = QComboBox()
    log_combo.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
    log_combo.setCurrentText(settings.get("general.log_level"))
    tab.add_row("Log Level", log_combo)
    widgets["general.log_level"] = log_combo

    # Advanced
    debug_cb = QCheckBox()
    debug_cb.setChecked(settings.get("general.debug_log_file"))
    tab.add_row("Debug Log File", debug_cb, advanced=True)
    widgets["general.debug_log_file"] = debug_cb

    debounce = QDoubleSpinBox()
    debounce.setRange(0.5, 10.0)
    debounce.setSingleStep(0.5)
    debounce.setValue(settings.get("general.debounce_sec"))
    debounce.setSuffix(" s")
    tab.add_row("Question Debounce", debounce, advanced=True)
    widgets["general.debounce_sec"] = debounce

    qa_depth = QSpinBox()
    qa_depth.setRange(0, 10)
    qa_depth.setValue(settings.get("general.qa_history_depth"))
    tab.add_row("Q&&A History Depth", qa_depth, advanced=True)
    widgets["general.qa_history_depth"] = qa_depth

    return tab, widgets


def _browse_pdf(edit: QLineEdit) -> None:
    path, _ = QFileDialog.getOpenFileName(
        None, "Select PDF", str(Path.home()), "PDF Files (*.pdf)"
    )
    if path:
        edit.setText(path)


def _build_audio_tab() -> tuple[_SettingsTab, dict[str, Any]]:
    tab = _SettingsTab()
    widgets: dict[str, Any] = {}

    devices = enumerate_audio_devices()

    # Mic device
    mic_combo = QComboBox()
    mic_combo.addItem("Auto-detect", "")
    current_mic = settings.get("audio.mic_device")
    for d in devices:
        if d["is_input"] and not d["is_loopback"]:
            mic_combo.addItem(d["name"], str(d["index"]))
    _select_combo_by_data(mic_combo, current_mic)
    tab.add_row("Microphone", mic_combo)
    widgets["audio.mic_device"] = mic_combo

    # Refresh button
    refresh_btn = QPushButton("🔄 Refresh Devices")
    refresh_btn.clicked.connect(lambda: _refresh_audio_devices(mic_combo))
    tab.add_widget_row(refresh_btn)

    # Advanced
    sr_combo = QComboBox()
    for rate in [16000, 44100, 48000]:
        sr_combo.addItem(str(rate), rate)
    _select_combo_by_data(sr_combo, settings.get("audio.sample_rate"))
    tab.add_row("Sample Rate (Hz)", sr_combo, advanced=True)
    widgets["audio.sample_rate"] = sr_combo

    chunk_spin = QSpinBox()
    chunk_spin.setRange(50, 500)
    chunk_spin.setSingleStep(50)
    chunk_spin.setValue(settings.get("audio.chunk_ms"))
    chunk_spin.setSuffix(" ms")
    tab.add_row("Chunk Size", chunk_spin, advanced=True)
    widgets["audio.chunk_ms"] = chunk_spin

    return tab, widgets


def _refresh_audio_devices(mic_combo: QComboBox) -> None:
    devices = enumerate_audio_devices()
    cur_mic = mic_combo.currentData()

    mic_combo.clear()
    mic_combo.addItem("Auto-detect", "")
    for d in devices:
        if d["is_input"] and not d["is_loopback"]:
            mic_combo.addItem(d["name"], str(d["index"]))
    _select_combo_by_data(mic_combo, cur_mic)


def _build_transcription_tab() -> tuple[_SettingsTab, dict[str, Any]]:
    tab = _SettingsTab()
    widgets: dict[str, Any] = {}

    model = QComboBox()
    model.addItems(["nova-3", "nova-2", "enhanced", "base"])
    model.setCurrentText(settings.get("transcription.model"))
    tab.add_row("Deepgram Model", model)
    widgets["transcription.model"] = model

    lang = QComboBox()
    lang.addItems(["en", "es", "fr", "de", "ja", "zh"])
    lang.setCurrentText(settings.get("transcription.language"))
    tab.add_row("Language", lang)
    widgets["transcription.language"] = lang

    diarize = QCheckBox()
    diarize.setChecked(settings.get("transcription.diarize"))
    tab.add_row("Diarize (speaker labels)", diarize)
    widgets["transcription.diarize"] = diarize

    smart = QCheckBox()
    smart.setChecked(settings.get("transcription.smart_format"))
    tab.add_row("Smart Format", smart)
    widgets["transcription.smart_format"] = smart

    # Advanced
    ep = QSpinBox()
    ep.setRange(100, 2000)
    ep.setSingleStep(100)
    ep.setValue(settings.get("transcription.endpointing_ms"))
    ep.setSuffix(" ms")
    tab.add_row("Endpointing", ep, advanced=True)
    widgets["transcription.endpointing_ms"] = ep

    ue = QSpinBox()
    ue.setRange(500, 5000)
    ue.setSingleStep(250)
    ue.setValue(settings.get("transcription.utterance_end_ms"))
    ue.setSuffix(" ms")
    tab.add_row("Utterance End", ue, advanced=True)
    widgets["transcription.utterance_end_ms"] = ue

    return tab, widgets


def _build_intelligence_tab() -> tuple[_SettingsTab, dict[str, Any]]:
    tab = _SettingsTab()
    widgets: dict[str, Any] = {}

    _MODELS = ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano"]

    resp_model = QComboBox()
    resp_model.addItems(_MODELS)
    resp_model.setCurrentText(settings.get("intelligence.response_model"))
    tab.add_row("Response Model", resp_model)
    widgets["intelligence.response_model"] = resp_model

    resp_tokens = QSpinBox()
    resp_tokens.setRange(64, 2048)
    resp_tokens.setSingleStep(64)
    resp_tokens.setValue(settings.get("intelligence.response_max_tokens"))
    tab.add_row("Max Response Tokens", resp_tokens)
    widgets["intelligence.response_max_tokens"] = resp_tokens

    # Advanced
    det_model = QComboBox()
    det_model.addItems(_MODELS)
    det_model.setCurrentText(settings.get("intelligence.detection_model"))
    tab.add_row("Detection Model", det_model, advanced=True)
    widgets["intelligence.detection_model"] = det_model

    rout_model = QComboBox()
    rout_model.addItems(_MODELS)
    rout_model.setCurrentText(settings.get("intelligence.routing_model"))
    tab.add_row("Routing Model", rout_model, advanced=True)
    widgets["intelligence.routing_model"] = rout_model

    bull_model = QComboBox()
    bull_model.addItems(_MODELS)
    bull_model.setCurrentText(settings.get("intelligence.bullets_model"))
    tab.add_row("Bullets Model", bull_model, advanced=True)
    widgets["intelligence.bullets_model"] = bull_model

    bull_tokens = QSpinBox()
    bull_tokens.setRange(64, 1024)
    bull_tokens.setSingleStep(64)
    bull_tokens.setValue(settings.get("intelligence.bullets_max_tokens"))
    tab.add_row("Bullets Max Tokens", bull_tokens, advanced=True)
    widgets["intelligence.bullets_max_tokens"] = bull_tokens

    min_w = QSpinBox()
    min_w.setRange(1, 30)
    min_w.setValue(settings.get("intelligence.min_words"))
    tab.add_row("Min Words (detect)", min_w, advanced=True)
    widgets["intelligence.min_words"] = min_w

    regex_w = QSpinBox()
    regex_w.setRange(1, 50)
    regex_w.setValue(settings.get("intelligence.regex_min_words"))
    tab.add_row("Regex Min Words", regex_w, advanced=True)
    widgets["intelligence.regex_min_words"] = regex_w

    top_k = QSpinBox()
    top_k.setRange(1, 20)
    top_k.setValue(settings.get("intelligence.similarity_top_k"))
    tab.add_row("Similarity Top-K", top_k, advanced=True)
    widgets["intelligence.similarity_top_k"] = top_k

    sim_thresh = QDoubleSpinBox()
    sim_thresh.setRange(0.0, 1.0)
    sim_thresh.setSingleStep(0.05)
    sim_thresh.setDecimals(2)
    sim_thresh.setValue(settings.get("intelligence.similarity_threshold"))
    tab.add_row("Similarity Threshold", sim_thresh, advanced=True)
    widgets["intelligence.similarity_threshold"] = sim_thresh

    return tab, widgets


def _build_speaker_tab() -> tuple[_SettingsTab, dict[str, Any]]:
    tab = _SettingsTab()
    widgets: dict[str, Any] = {}

    gap = QDoubleSpinBox()
    gap.setRange(0.5, 10.0)
    gap.setSingleStep(0.5)
    gap.setValue(settings.get("speaker.gap_threshold_sec"))
    gap.setSuffix(" s")
    tab.add_row("Gap Threshold", gap)
    widgets["speaker.gap_threshold_sec"] = gap

    cont = QDoubleSpinBox()
    cont.setRange(0.1, 5.0)
    cont.setSingleStep(0.1)
    cont.setValue(settings.get("speaker.continuity_sec"))
    cont.setSuffix(" s")
    tab.add_row("Continuity Window", cont)
    widgets["speaker.continuity_sec"] = cont

    # Advanced
    echo_sim = QDoubleSpinBox()
    echo_sim.setRange(0.0, 1.0)
    echo_sim.setSingleStep(0.05)
    echo_sim.setDecimals(2)
    echo_sim.setValue(settings.get("speaker.echo_similarity_threshold"))
    tab.add_row("Echo Similarity", echo_sim, advanced=True)
    widgets["speaker.echo_similarity_threshold"] = echo_sim

    echo_win = QDoubleSpinBox()
    echo_win.setRange(1.0, 10.0)
    echo_win.setSingleStep(0.5)
    echo_win.setValue(settings.get("speaker.echo_window_sec"))
    echo_win.setSuffix(" s")
    tab.add_row("Echo Window", echo_win, advanced=True)
    widgets["speaker.echo_window_sec"] = echo_win

    return tab, widgets


def _build_appearance_tab(dialog: QDialog) -> tuple[_SettingsTab, dict[str, Any]]:
    tab = _SettingsTab()
    widgets: dict[str, Any] = {}

    # Opacity slider (0.30 – 1.00, displayed as %)
    opacity_layout = QHBoxLayout()
    opacity_slider = QSlider(Qt.Orientation.Horizontal)
    opacity_slider.setRange(30, 100)
    opacity_slider.setValue(int(settings.get("appearance.opacity") * 100))
    opacity_label = QLabel(f"{opacity_slider.value()}%")
    opacity_label.setFixedWidth(36)
    opacity_slider.valueChanged.connect(lambda v: opacity_label.setText(f"{v}%"))
    opacity_layout.addWidget(opacity_slider)
    opacity_layout.addWidget(opacity_label)
    container = QWidget()
    container.setLayout(opacity_layout)
    tab.add_row("Window Opacity", container)
    widgets["appearance.opacity"] = opacity_slider

    width_spin = QSpinBox()
    width_spin.setRange(300, 800)
    width_spin.setSingleStep(20)
    width_spin.setValue(settings.get("appearance.width"))
    width_spin.setSuffix(" px")
    tab.add_row("Window Width", width_spin)
    widgets["appearance.width"] = width_spin

    height_spin = QSpinBox()
    height_spin.setRange(400, 1200)
    height_spin.setSingleStep(20)
    height_spin.setValue(settings.get("appearance.height"))
    height_spin.setSuffix(" px")
    tab.add_row("Window Height", height_spin)
    widgets["appearance.height"] = height_spin

    font_spin = QSpinBox()
    font_spin.setRange(8, 24)
    font_spin.setValue(settings.get("appearance.font_size"))
    font_spin.setSuffix(" px")
    tab.add_row("Font Size", font_spin)
    widgets["appearance.font_size"] = font_spin

    stealth_cb = QCheckBox()
    stealth_cb.setChecked(settings.get("appearance.stealth_start"))
    tab.add_row("Start in Stealth Mode", stealth_cb)
    widgets["appearance.stealth_start"] = stealth_cb

    return tab, widgets


# ── Combo helper ──────────────────────────────────────────────────────

def _select_combo_by_data(combo: QComboBox, value: Any) -> None:
    """Select the combo item whose user-data matches *value*."""
    for i in range(combo.count()):
        if combo.itemData(i) == value:
            combo.setCurrentIndex(i)
            return
    # If the value is the text itself (e.g. model name)
    idx = combo.findText(str(value))
    if idx >= 0:
        combo.setCurrentIndex(idx)


# ── Main Dialog ───────────────────────────────────────────────────────

class SettingsDialog(QDialog):
    """Modal settings dialog with 6 tabs and restart-required warnings."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setFixedSize(600, 520)
        self.setStyleSheet(_DIALOG_SS)
        self.setWindowFlags(
            Qt.WindowType.Dialog | Qt.WindowType.WindowCloseButtonHint
        )

        self._widgets: dict[str, Any] = {}
        self._restart_needed = False

        self._build_ui()
        self._center_on_screen()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        # Restart warning banner (hidden by default)
        self._restart_banner = QLabel(
            "⚠  Some changes require an app restart to take effect."
        )
        self._restart_banner.setStyleSheet(
            f"background-color: #3D3520; color: {ACCENT_YELLOW}; "
            f"padding: 6px 10px; border-radius: 4px; font-size: 11px; font-weight: bold;"
        )
        self._restart_banner.setVisible(False)
        root.addWidget(self._restart_banner)

        # Tab widget
        tabs = QTabWidget()
        tabs.setDocumentMode(True)

        gen_tab, gen_w = _build_general_tab()
        tabs.addTab(gen_tab, "General")
        self._widgets.update(gen_w)

        audio_tab, audio_w = _build_audio_tab()
        tabs.addTab(audio_tab, "Audio")
        self._widgets.update(audio_w)

        trans_tab, trans_w = _build_transcription_tab()
        tabs.addTab(trans_tab, "Transcription")
        self._widgets.update(trans_w)

        intel_tab, intel_w = _build_intelligence_tab()
        tabs.addTab(intel_tab, "Intelligence")
        self._widgets.update(intel_w)

        spk_tab, spk_w = _build_speaker_tab()
        tabs.addTab(spk_tab, "Speaker")
        self._widgets.update(spk_w)

        app_tab, app_w = _build_appearance_tab(self)
        tabs.addTab(app_tab, "Appearance")
        self._widgets.update(app_w)

        root.addWidget(tabs, 1)

        # Bottom button row
        btn_layout = QHBoxLayout()
        reset_btn = QPushButton("Reset Defaults")
        reset_btn.clicked.connect(self._on_reset_defaults)
        btn_layout.addWidget(reset_btn)
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        apply_btn = QPushButton("Apply")
        apply_btn.clicked.connect(self._on_apply)
        btn_layout.addWidget(apply_btn)

        ok_btn = QPushButton("OK")
        ok_btn.setObjectName("okBtn")
        ok_btn.clicked.connect(self._on_ok)
        btn_layout.addWidget(ok_btn)

        root.addLayout(btn_layout)

    # ── collect values from widgets ───────────────────────────────────

    def _collect(self) -> dict[str, Any]:
        """Read current widget values into a flat dict."""
        out: dict[str, Any] = {}
        for key, widget in self._widgets.items():
            if isinstance(widget, QLineEdit):
                out[key] = widget.text()
            elif isinstance(widget, QCheckBox):
                out[key] = widget.isChecked()
            elif isinstance(widget, QComboBox):
                data = widget.currentData()
                out[key] = data if data is not None else widget.currentText()
            elif isinstance(widget, QSpinBox):
                out[key] = widget.value()
            elif isinstance(widget, QDoubleSpinBox):
                out[key] = widget.value()
            elif isinstance(widget, QSlider):
                out[key] = widget.value() / 100.0  # opacity
        return out

    def _apply_values(self, values: dict[str, Any]) -> None:
        """Push collected values into SettingsManager."""
        restart = False
        for key, val in values.items():
            old = settings.get(key)
            if old != val:
                settings.set(key, val)
                if key in RESTART_REQUIRED_KEYS:
                    restart = True
        if restart:
            self._restart_needed = True
            self._restart_banner.setVisible(True)

    def _load_into_widgets(self) -> None:
        """Push current SettingsManager values back into widgets."""
        for key, widget in self._widgets.items():
            val = settings.get(key)
            if isinstance(widget, QLineEdit):
                widget.setText(str(val) if val else "")
            elif isinstance(widget, QCheckBox):
                widget.setChecked(bool(val))
            elif isinstance(widget, QComboBox):
                _select_combo_by_data(widget, val)
            elif isinstance(widget, QSpinBox):
                widget.setValue(int(val))
            elif isinstance(widget, QDoubleSpinBox):
                widget.setValue(float(val))
            elif isinstance(widget, QSlider):
                widget.setValue(int(float(val) * 100))

    # ── button handlers ───────────────────────────────────────────────

    def _on_apply(self) -> None:
        values = self._collect()
        self._apply_values(values)
        settings.save()

    def _on_ok(self) -> None:
        self._on_apply()
        self.accept()

    def _on_reset_defaults(self) -> None:
        settings.reset_to_defaults()
        self._load_into_widgets()

    @property
    def restart_needed(self) -> bool:
        return self._restart_needed

    # ── positioning ───────────────────────────────────────────────────

    def _center_on_screen(self) -> None:
        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = (geo.width() - self.width()) // 2
            y = (geo.height() - self.height()) // 2
            self.move(x, y)
