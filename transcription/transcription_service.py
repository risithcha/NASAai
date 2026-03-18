"""
Real-time transcription via Deepgram's WebSocket streaming API.

Uses a raw websockets connection (not the SDK convenience wrapper) for
full control over the multichannel, diarized payload.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from typing import Callable

import websockets

import config
from transcription.transcript_store import TranscriptSegment, TranscriptStore

log = logging.getLogger(__name__)

# Callback for raw audio bytes coming from AudioCapture
AudioBytesCallback = Callable[[bytes], None]


class TranscriptionService:
    """
    Connects to Deepgram streaming, accepts interleaved stereo PCM-16
    frames, and writes speaker-labelled segments into a TranscriptStore.
    """

    def __init__(self, store: TranscriptStore) -> None:
        self._store = store
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._running = False

    # ── public API ────────────────────────────────────────────────────

    def start(self) -> None:
        """Spin up the asyncio event loop in a background thread."""
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._close_ws(), self._loop)
        if self._thread:
            self._thread.join(timeout=5)

    def send_audio(self, pcm_bytes: bytes) -> None:
        """
        Called from the AudioCapture mixer thread with interleaved
        stereo PCM-16 data.  Forwards to the WebSocket.
        """
        if self._ws and self._loop and self._running:
            asyncio.run_coroutine_threadsafe(
                self._send(pcm_bytes), self._loop
            )

    # ── internals ─────────────────────────────────────────────────────

    def _build_url(self) -> str:
        params = (
            f"model={config.DG_MODEL}"
            f"&language={config.DG_LANGUAGE}"
            f"&smart_format={'true' if config.DG_SMART_FORMAT else 'false'}"
            f"&diarize={'true' if config.DG_DIARIZE else 'false'}"
            f"&multichannel=true"
            f"&channels=2"
            f"&sample_rate={config.AUDIO_SAMPLE_RATE}"
            f"&encoding=linear16"
            f"&interim_results={'true' if config.DG_INTERIM_RESULTS else 'false'}"
            f"&utterance_end_ms={config.DG_UTTERANCE_END_MS}"
            f"&endpointing={config.DG_ENDPOINTING_MS}"
            f"&punctuate=true"
        )
        return f"wss://api.deepgram.com/v1/listen?{params}"

    def _run_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._listen())

    async def _listen(self) -> None:
        url = self._build_url()
        headers = {"Authorization": f"Token {config.DEEPGRAM_API_KEY}"}

        try:
            async with websockets.connect(
                url,
                additional_headers=headers,
                ping_interval=20,
                ping_timeout=10,
                max_size=None,
            ) as ws:
                self._ws = ws
                log.info("Connected to Deepgram streaming endpoint")
                async for raw_msg in ws:
                    if not self._running:
                        break
                    self._handle_message(raw_msg)
        except websockets.ConnectionClosed as exc:
            log.warning("Deepgram WebSocket closed: %s", exc)
        except Exception:
            log.exception("Deepgram connection error")
        finally:
            self._ws = None
            log.info("Deepgram listener exited")

    async def _send(self, data: bytes) -> None:
        if self._ws:
            try:
                await self._ws.send(data)
            except Exception:
                log.debug("Failed to send audio frame", exc_info=True)

    async def _close_ws(self) -> None:
        if self._ws:
            try:
                # Send Deepgram close-stream message
                await self._ws.send(json.dumps({"type": "CloseStream"}))
                await self._ws.close()
            except Exception:
                pass

    # ── message parsing ───────────────────────────────────────────────

    def _handle_message(self, raw: str | bytes) -> None:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return

        msg_type = msg.get("type", "")

        if msg_type == "Results":
            self._handle_results(msg)
        elif msg_type == "Metadata":
            log.debug("Deepgram metadata: %s", msg)
        elif msg_type == "UtteranceEnd":
            pass  # handled via endpointing
        elif msg_type == "SpeechStarted":
            pass
        else:
            log.debug("Unknown Deepgram event: %s", msg_type)

    def _handle_results(self, msg: dict) -> None:
        is_final: bool = msg.get("is_final", False)
        channel_index: list[int] = msg.get("channel_index", [0, 1])
        channel_id = channel_index[0] if channel_index else 0

        channel_data = msg.get("channel", {})
        alternatives = channel_data.get("alternatives", [])
        if not alternatives:
            return

        alt = alternatives[0]
        transcript = alt.get("transcript", "").strip()
        if not transcript:
            return

        # Determine speaker label
        words = alt.get("words", [])
        speaker = self._extract_speaker(words, channel_id)

        seg = TranscriptSegment(
            text=transcript,
            speaker=speaker,
            channel=channel_id,
            is_final=is_final,
        )

        if is_final:
            self._store.add_segment(seg)
        else:
            self._store.set_interim(seg)

    @staticmethod
    def _extract_speaker(words: list[dict], channel: int) -> str:
        """
        Channel 1 = mic → "You".
        Channel 0 = remote → use diarization speaker id.
        """
        if channel == 1:
            return "You"

        # Find the most common speaker id across words
        speaker_ids = [w.get("speaker") for w in words if w.get("speaker") is not None]
        if not speaker_ids:
            return "Remote"

        # majority vote
        from collections import Counter
        most_common = Counter(speaker_ids).most_common(1)[0][0]
        return f"Speaker {most_common}"
