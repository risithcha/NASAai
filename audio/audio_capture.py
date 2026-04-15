"""
Microphone-only audio capture using PyAudioWPatch.

Captures audio from the default (or configured) microphone, resamples
to the target rate, and forwards mono PCM-16 frames to a callback.
"""

from __future__ import annotations

import threading
import logging
from collections import deque
from typing import Callable

import numpy as np

try:
    import pyaudiowpatch as pyaudio
except ImportError:
    raise ImportError(
        "PyAudioWPatch is required.  Install it with:  pip install PyAudioWPatch"
    )

from audio.audio_utils import (
    pcm_bytes_to_numpy,
    resample_audio,
    numpy_to_pcm_bytes,
)
import config

log = logging.getLogger(__name__)

# Type alias for the callback that receives ready mono frames.
AudioFrameCallback = Callable[[bytes], None]


class AudioCapture:
    """
    Opens the default (or configured) microphone, resamples to
    ``config.AUDIO_SAMPLE_RATE``, and delivers mono PCM-16 frames
    via *on_audio_frame*.
    """

    def __init__(self, on_audio_frame: AudioFrameCallback) -> None:
        self._on_frame = on_audio_frame
        self._pa = pyaudio.PyAudio()
        self._mic_stream = None
        self._running = False

        # Buffer filled by the mic callback
        self._mic_buf: deque[np.ndarray] = deque()
        self._lock = threading.Lock()

        # Device info (resolved on start)
        self._mic_dev: dict | None = None

    # ── public API ────────────────────────────────────────────────────

    def start(self) -> None:
        """Discover the mic device and open the stream."""
        self._resolve_device()
        self._running = True
        self._open_mic()
        # A feeder thread pulls from the buffer and fires the callback
        self._feeder_thread = threading.Thread(target=self._feeder_loop, daemon=True)
        self._feeder_thread.start()
        log.info("AudioCapture started  (mic=%s)", self._mic_dev["name"])

    def stop(self) -> None:
        self._running = False
        if self._mic_stream and self._mic_stream.is_active():
            self._mic_stream.stop_stream()
        if self._mic_stream:
            self._mic_stream.close()
        self._pa.terminate()
        log.info("AudioCapture stopped")

    def list_devices(self) -> list[dict]:
        """Return a list of all audio devices (useful for debugging)."""
        devices = []
        for i in range(self._pa.get_device_count()):
            devices.append(self._pa.get_device_info_by_index(i))
        return devices

    # ── device resolution ─────────────────────────────────────────────

    def _resolve_device(self) -> None:
        from settings.settings_manager import settings as sm

        cfg_mic = sm.get("audio.mic_device")

        if cfg_mic:
            try:
                self._mic_dev = self._pa.get_device_info_by_index(int(cfg_mic))
                log.info("Using settings-selected mic device: %s", self._mic_dev["name"])
                return
            except Exception:
                log.warning("Configured mic device %s not found, falling back to auto-detect", cfg_mic)

        default_input_idx = self._pa.get_default_input_device_info()["index"]
        self._mic_dev = self._pa.get_device_info_by_index(default_input_idx)

    # ── stream helpers ────────────────────────────────────────────────

    def _open_mic(self) -> None:
        dev = self._mic_dev
        self._mic_native_rate = int(dev["defaultSampleRate"])
        self._mic_channels = min(dev["maxInputChannels"], 1)  # mono

        self._mic_stream = self._pa.open(
            format=pyaudio.paInt16,
            channels=self._mic_channels,
            rate=self._mic_native_rate,
            input=True,
            input_device_index=dev["index"],
            frames_per_buffer=config.AUDIO_CHUNK_SAMPLES,
            stream_callback=self._mic_cb,
        )

    # ── callback (called from PortAudio thread) ──────────────────────

    def _mic_cb(self, in_data, frame_count, time_info, status):
        if not self._running:
            return (None, pyaudio.paComplete)
        arr = pcm_bytes_to_numpy(in_data)
        if self._mic_channels > 1:
            arr = arr.reshape(-1, self._mic_channels)[:, 0].copy()
        arr = resample_audio(arr, self._mic_native_rate, config.AUDIO_SAMPLE_RATE)
        with self._lock:
            self._mic_buf.append(arr)
        return (None, pyaudio.paContinue)

    # ── feeder loop ──────────────────────────────────────────────────

    def _feeder_loop(self) -> None:
        """
        Runs on a dedicated thread.  Pulls chunks from the mic buffer
        and fires the callback with mono PCM-16 frames.
        """
        import time

        target = config.AUDIO_CHUNK_SAMPLES
        while self._running:
            mic_chunk = self._drain(self._mic_buf, target)

            if mic_chunk is None:
                time.sleep(config.AUDIO_CHUNK_MS / 1000 / 2)
                continue

            try:
                self._on_frame(numpy_to_pcm_bytes(mic_chunk))
            except Exception:
                log.exception("Error in audio frame callback")

    def _drain(self, buf: deque, target: int) -> np.ndarray | None:
        """Accumulate *target* samples from *buf*; return None if empty."""
        collected: list[np.ndarray] = []
        total = 0
        with self._lock:
            while buf and total < target:
                chunk = buf.popleft()
                collected.append(chunk)
                total += len(chunk)
        if not collected:
            return None
        joined = np.concatenate(collected)
        if len(joined) > target:
            # Put leftover back
            with self._lock:
                buf.appendleft(joined[target:])
            joined = joined[:target]
        return joined
