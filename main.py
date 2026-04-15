"""
Data Science Presentation Assistant — main entry point.

Startup sequence:
  1. Validate environment (API keys present).
  2. Build / load the FAISS knowledge base from the PDF and CSV datasets.
  3. Launch the PyQt6 overlay window.
  4. Start microphone capture → transcription → intelligence pipeline.
  5. Run the Qt event loop (blocks until user closes the window).
  6. Tear down all background threads gracefully.
"""

from __future__ import annotations

import logging
import sys
import os

# ── Logging ───────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("main")

# File handler — captures DEBUG-level for post-run analysis
def _attach_file_logger() -> None:
    import config
    fh = logging.FileHandler(config.LOG_FILE, mode="w", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    ))
    logging.getLogger().addHandler(fh)
    log.info("Debug log → %s", config.LOG_FILE)

_attach_file_logger()


def _preflight() -> None:
    """Ensure mandatory env vars / files are present."""
    import config

    missing: list[str] = []
    if not config.DEEPGRAM_API_KEY:
        missing.append("DEEPGRAM_API_KEY")
    if not config.OPENAI_API_KEY:
        missing.append("OPENAI_API_KEY")
    if missing:
        log.error(
            "Missing API keys: %s.  Set them in .env or environment.", ", ".join(missing)
        )
        sys.exit(1)

    if not config.PDF_PATH.exists():
        log.warning(
            "PDF not found at %s — knowledge base will be empty.  "
            "Place your Data Science portfolio PDF there and re-run.",
            config.PDF_PATH,
        )


def main() -> None:
    # Load persisted settings into config constants before anything else
    import config
    config.load_from_settings()

    _preflight()

    # Import heavy modules after preflight so errors surface quickly
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QTimer

    import config
    from accounts.user_profile import load_profiles, UserSession
    from audio.audio_capture import AudioCapture
    from intelligence.pipeline import Pipeline
    from knowledge.knowledge_base import KnowledgeBase
    from transcription.transcript_store import TranscriptStore
    from transcription.transcription_service import TranscriptionService
    from ui.overlay_window import OverlayWindow
    from ui.profile_picker import ProfilePickerDialog

    app = QApplication(sys.argv)
    app.setApplicationName("Data Science Presentation Assistant")

    # ── Profile picker ────────────────────────────────────────────────
    profiles = load_profiles()
    if not profiles:
        log.error("No user profiles found. Check %s", config.PROFILES_PATH)
        sys.exit(1)

    picker = ProfilePickerDialog(profiles)
    if picker.exec() != ProfilePickerDialog.DialogCode.Accepted or not picker.selected_profile:
        log.info("No profile selected — exiting.")
        sys.exit(0)

    session = UserSession()
    session.current_user = picker.selected_profile
    user_profile = session.current_user
    log.info("Signed in as %s (%s)", user_profile.display_name, user_profile.role)

    # ── Knowledge base ────────────────────────────────────────────────
    log.info("Preparing knowledge base …")
    kb = KnowledgeBase()
    kb.ensure_ready()
    log.info("Knowledge base ready  (%d chunks indexed)", len(kb._chunks))

    # ── Core objects ──────────────────────────────────────────────────
    store = TranscriptStore()
    transcription = TranscriptionService(store)
    pipeline = Pipeline(store, kb, user_profile, all_profiles=profiles)

    # ── UI ────────────────────────────────────────────────────────────
    window = OverlayWindow(user_profile)

    # Wire transcript events → UI
    def on_segment(seg):
        if not seg.is_final:
            window.post_interim(seg)
        elif not seg.is_utterance_end:
            # Show individual sub-finals; skip combined utterance_end (duplicate)
            window.post_segment(seg)

    store.add_listener(on_segment)

    # Wire pipeline responses → UI
    pipeline.set_callback(window.post_response)

    # ── Audio capture ─────────────────────────────────────────────────
    def on_audio_frame(pcm_bytes: bytes) -> None:
        transcription.send_audio(pcm_bytes)

    capture = AudioCapture(on_audio_frame)

    # ── Start everything ──────────────────────────────────────────────
    def _start_services() -> None:
        try:
            transcription.start()
            window.set_status("deepgram", True)
            log.info("Deepgram connected")
        except Exception:
            log.exception("Failed to start transcription service")
            window.set_error("deepgram")

        try:
            capture.start()
            window.set_status("audio", True)
            log.info("Audio capture started")
        except Exception:
            log.exception("Failed to start audio capture")
            window.set_error("audio")

        pipeline.start()
        window.set_status("ai", True)
        log.info("Intelligence pipeline running")

    # Defer heavy startup until the Qt event loop is spinning
    QTimer.singleShot(100, _start_services)

    window.show()
    log.info("Overlay window visible — listening …")

    exit_code = app.exec()

    # ── Teardown ──────────────────────────────────────────────────────
    log.info("Shutting down …")
    pipeline.stop()
    capture.stop()
    transcription.stop()
    log.info("Goodbye.")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
