"""Synthetic deterministic WAV fixtures for Listening tests & local demos."""

from __future__ import annotations

import io
import math
import struct
import wave


def generate_synthetic_wav(duration_seconds: float = 1.5, frequency_hz: float = 440.0, sample_rate: int = 16000) -> bytes:
    """Build deterministic mono 16-bit PCM WAV bytes without external tools."""
    total_frames = max(1, int(round(duration_seconds * sample_rate)))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        frames = bytearray()
        for i in range(total_frames):
            val = int(12000 * math.sin(2.0 * math.pi * frequency_hz * (i / sample_rate)))
            frames.extend(struct.pack("<h", val))
        wf.writeframes(bytes(frames))
    return buf.getvalue()
