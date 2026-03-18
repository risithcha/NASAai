"""
Dual-stream audio capture using PyAudioWPatch.

Stream A – WASAPI loopback (what remote Teams participants say)
Stream B – Default microphone (the user's own voice)

Both streams are resampled to a common rate and forwarded to a callback
as interleaved stereo PCM-16 frames (ch0 = remote, ch1 = mic).
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
    interleave_stereo,
    numpy_to_pcm_bytes,
)
import config

log = logging.getLogger(__name__)

# Type alias for the callback that receives ready stereo frames.
AudioFrameCallback = Callable[[bytes], None]


class AudioCapture:
    """
    Opens a loopback device and the default mic simultaneously,
    resamples both to ``config.AUDIO_SAMPLE_RATE``, and delivers
    interleaved stereo PCM-16 frames via *on_audio_frame*.
    """

    def __init__(self, on_audio_frame: AudioFrameCallback) -> None:
        self._on_frame = on_audio_frame
        self._pa = pyaudio.PyAudio()
        self._loopback_stream = None
        self._mic_stream = None
        self._running = False

        # Buffers filled by the two independent callbacks
        self._loopback_buf: deque[np.ndarray] = deque()
        self._mic_buf: deque[np.ndarray] = deque()
        self._lock = threading.Lock()

        # Device info (resolved on start)
        self._loopback_dev: dict | None = None
        self._mic_dev: dict | None = None

    # ── public API ────────────────────────────────────────────────────

    def start(self) -> None:
        """Discover devices and open both streams."""
        self._resolve_devices()
        self._running = True
        self._open_loopback()
        self._open_mic()
        # A mixer thread pulls from both buffers and combines them
        self._mixer_thread = threading.Thread(target=self._mixer_loop, daemon=True)
        self._mixer_thread.start()
        log.info("AudioCapture started  (loopback=%s, mic=%s)",
                 self._loopback_dev["name"], self._mic_dev["name"])

    def stop(self) -> None:
        self._running = False
        for stream in (self._loopback_stream, self._mic_stream):
            if stream and stream.is_active():
                stream.stop_stream()
            if stream:
                stream.close()
        self._pa.terminate()
        log.info("AudioCapture stopped")

    def list_devices(self) -> list[dict]:
        """Return a list of all audio devices (useful for debugging)."""
        devices = []
        for i in range(self._pa.get_device_count()):
            devices.append(self._pa.get_device_info_by_index(i))
        return devices

    # ── device resolution ─────────────────────────────────────────────

    def _resolve_devices(self) -> None:
        # --- loopback ---
        try:
            wasapi_info = self._pa.get_host_api_info_by_type(pyaudio.paWASAPI)
        except OSError:
            raise RuntimeError("WASAPI is not available on this system.")

        default_output = self._pa.get_device_info_by_index(
            wasapi_info["defaultOutputDevice"]
        )
        if not default_output.get("isLoopbackDevice"):
            for lb in self._pa.get_loopback_device_info_generator():
                if default_output["name"] in lb["name"]:
                    default_output = lb
                    break
            else:
                raise RuntimeError(
                    "No loopback device found for the default output.  "
                    "Run `python -m pyaudiowpatch` to inspect devices."
                )
        self._loopback_dev = default_output

        # --- mic ---
        default_input_idx = self._pa.get_default_input_device_info()["index"]
        self._mic_dev = self._pa.get_device_info_by_index(default_input_idx)

    # ── stream helpers ────────────────────────────────────────────────

    def _open_loopback(self) -> None:
        dev = self._loopback_dev
        self._loopback_native_rate = int(dev["defaultSampleRate"])
        self._loopback_channels = dev["maxInputChannels"]

        self._loopback_stream = self._pa.open(
            format=pyaudio.paInt16,
            channels=self._loopback_channels,
            rate=self._loopback_native_rate,
            input=True,
            input_device_index=dev["index"],
            frames_per_buffer=config.AUDIO_CHUNK_SAMPLES,
            stream_callback=self._loopback_cb,
        )

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

    # ── callbacks (called from PortAudio threads) ─────────────────────

    def _loopback_cb(self, in_data, frame_count, time_info, status):
        if not self._running:
            return (None, pyaudio.paComplete)
        arr = pcm_bytes_to_numpy(in_data)
        # Down-mix to mono if stereo
        if self._loopback_channels > 1:
            arr = arr.reshape(-1, self._loopback_channels)[:, 0].copy()
        arr = resample_audio(arr, self._loopback_native_rate, config.AUDIO_SAMPLE_RATE)
        with self._lock:
            self._loopback_buf.append(arr)
        return (None, pyaudio.paContinue)

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

    # ── mixer loop ────────────────────────────────────────────────────

    def _mixer_loop(self) -> None:
        """
        Runs on a dedicated thread.  Pulls chunks from both buffers,
        interleaves them into stereo, and fires the callback.
        """
        import time

        target = config.AUDIO_CHUNK_SAMPLES
        while self._running:
            lb_chunk = self._drain(self._loopback_buf, target)
            mic_chunk = self._drain(self._mic_buf, target)

            if lb_chunk is None and mic_chunk is None:
                time.sleep(config.AUDIO_CHUNK_MS / 1000 / 2)
                continue

            if lb_chunk is None:
                lb_chunk = np.zeros(target, dtype=np.int16)
            if mic_chunk is None:
                mic_chunk = np.zeros(target, dtype=np.int16)

            stereo = interleave_stereo(lb_chunk, mic_chunk)
            try:
                self._on_frame(numpy_to_pcm_bytes(stereo))
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
