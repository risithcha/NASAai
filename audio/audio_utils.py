"""
Utility helpers for audio format conversion, resampling, and interleaving.
"""

import numpy as np
from scipy.signal import resample_poly
from math import gcd


def resample_audio(audio: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    """Resample *audio* (1-D int16 array) from *src_rate* to *dst_rate*."""
    if src_rate == dst_rate:
        return audio
    # Use rational resampling for exact results
    g = gcd(src_rate, dst_rate)
    up = dst_rate // g
    down = src_rate // g
    resampled = resample_poly(audio.astype(np.float32), up, down)
    return np.clip(resampled, -32768, 32767).astype(np.int16)


def pcm_bytes_to_numpy(data: bytes) -> np.ndarray:
    """Convert raw PCM-16 LE bytes to a 1-D int16 numpy array."""
    return np.frombuffer(data, dtype=np.int16)


def numpy_to_pcm_bytes(arr: np.ndarray) -> bytes:
    """Convert a 1-D int16 numpy array back to PCM-16 LE bytes."""
    return arr.astype(np.int16).tobytes()


def interleave_stereo(ch0: np.ndarray, ch1: np.ndarray) -> np.ndarray:
    """
    Interleave two mono int16 arrays into a stereo int16 array.
    If lengths differ, the shorter one is zero-padded.
    """
    length = max(len(ch0), len(ch1))
    if len(ch0) < length:
        ch0 = np.pad(ch0, (0, length - len(ch0)))
    if len(ch1) < length:
        ch1 = np.pad(ch1, (0, length - len(ch1)))
    stereo = np.empty(length * 2, dtype=np.int16)
    stereo[0::2] = ch0
    stereo[1::2] = ch1
    return stereo
