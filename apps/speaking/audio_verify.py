"""Bounded, model-free audio duration and integrity verification for Speaking uploads."""

from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
import sys
import tempfile
import wave
from pathlib import Path
from typing import Any

MAX_BYTES = 25 * 1024 * 1024
SHORT_TOLERANCE_SECONDS = 1.0
LONG_TOLERANCE_SECONDS = 0.5
GAP_TOLERANCE_SECONDS = 0.5
POLICY = "FULL_RESPONSE_WINDOW_V1"

_AUDIO_HEADER_PREFIXES = (
    b"RIFF",          # WAV
    b"\x1a\x45\xdf\xa3",  # WebM / Matroska
    b"OggS",          # Ogg Opus / Vorbis
    b"ID3",           # MP3 ID3
    b"\xff\xfb",      # MP3 frame sync
    b"\xff\xf3",
    b"\xff\xf2",
    b"fLaC",          # FLAC
    b"\x00\x00\x00",  # MP4/M4A ftyp box
)


class InvalidDuration(Exception):
    """Raised when decoded audio structure or duration violates bounds."""


class InvalidSpeakingAudio(Exception):
    """Structured client error raised when uploaded speaking audio is invalid."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def duration_bounds(expected_seconds: float) -> tuple[float, float]:
    """Return (min, max) accepted decoded length in seconds for a response window."""
    return expected_seconds - SHORT_TOLERANCE_SECONDS, expected_seconds + LONG_TOLERANCE_SECONDS


def duration_accepted(expected_seconds: float, duration_seconds: float) -> bool:
    low, high = duration_bounds(expected_seconds)
    return low <= duration_seconds <= high


def decoded_duration(path: str | Path, maximum: float | None = None) -> float:
    """Decode audio frame timeline locally without touching external services."""
    target = Path(path)
    size = target.stat().st_size
    if not 0 < size <= MAX_BYTES:
        raise InvalidDuration("empty_or_too_large")

    max_sec = float(maximum) if maximum is not None else 1800.0
    if target.suffix.lower() == ".wav":
        with wave.open(str(target), "rb") as source:
            rate = source.getframerate()
            channels = source.getnchannels()
            width = source.getsampwidth()
            if not 8000 <= rate <= 192000 or not 1 <= channels <= 8 or not 1 <= width <= 4:
                raise InvalidDuration("invalid_wav_params")
            declared = source.getnframes()
            if declared <= 0 or declared / rate > max_sec:
                raise InvalidDuration("invalid_wav_frames")
            count = 0
            while chunk := source.readframes(4096):
                if len(chunk) % (channels * width):
                    raise InvalidDuration("misaligned_frames")
                count += len(chunk) // (channels * width)
                if count / rate > max_sec:
                    raise InvalidDuration("exceeds_max")
            if count != declared or not count:
                raise InvalidDuration("truncated_wav")
            return count / rate

    try:
        import av  # type: ignore[import-not-found]
    except ImportError as exc:
        raise InvalidDuration("av_not_installed") from exc

    duration = 0.0
    frames = 0
    last_end = None
    with av.open(str(target), mode="r") as source:
        if len(source.streams.audio) != 1 or source.streams.video:
            raise InvalidDuration("invalid_streams")
        stream = source.streams.audio[0]
        for packet in source.demux(stream):
            if packet.is_corrupt:
                raise InvalidDuration("corrupt_packet")
            for frame in packet.decode():
                rate, samples = frame.sample_rate, frame.samples
                if not 8000 <= rate <= 192000 or not 0 < samples <= rate * 2 or len(frame.layout.channels) > 8:
                    raise InvalidDuration("invalid_audio_frame")
                frames += 1
                duration += samples / rate
                if frames > 25000 or duration > max_sec:
                    raise InvalidDuration("frame_budget_exceeded")
                if frame.pts is not None and frame.time_base is not None:
                    start = float(frame.pts * frame.time_base)
                    if last_end is not None and abs(start - last_end) > GAP_TOLERANCE_SECONDS:
                        raise InvalidDuration("timestamp_gap")
                    last_end = start + samples / rate
        declared = float(stream.duration * stream.time_base) if stream.duration is not None and stream.time_base else None
        if not frames or (declared is not None and abs(declared - duration) > GAP_TOLERANCE_SECONDS):
            raise InvalidDuration("container_mismatch")
    return duration


def measure_duration_subprocess(path: str | Path, max_seconds: float) -> int:
    """Measure decoded audio duration inside a clean bounded subprocess (ms)."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "apps.speaking.audio_verify", str(path), str(max_seconds)],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=20,
            check=False,
        )
        if result.returncode or len(result.stdout) > 1000:
            raise InvalidDuration("subprocess_failed")
        duration = json.loads(result.stdout)["duration"]
        if type(duration) not in (int, float) or not math.isfinite(duration) or duration <= 0:
            raise InvalidDuration("invalid_duration_number")
        return round(duration * 1000)
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError, TypeError, InvalidDuration) as exc:
        raise InvalidDuration(str(exc)) from exc


def _looks_like_audio_header(head: bytes) -> bool:
    if any(head.startswith(sig) for sig in _AUDIO_HEADER_PREFIXES):
        return True
    # MP4 / M4A container often has `ftyp` at offset 4
    if len(head) >= 8 and head[4:8] == b"ftyp":
        return True
    return False


def inspect_uploaded_audio(
    audio_file: Any,
    *,
    expected_seconds: int | None = None,
    min_seconds: float | None = None,
    strict_decode: bool = False,
) -> dict[str, Any]:
    """
    Compute SHA-256 hash and decode real WAV (or AV-supported) duration cleanly.
    Always rewinds `audio_file` before returning.
    """
    audio_file.seek(0)
    raw_bytes = audio_file.read()
    audio_file.seek(0)

    if not raw_bytes:
        raise InvalidSpeakingAudio("SPEAKING_AUDIO_EMPTY", "Bo'sh audio fayl yuklandi.")

    audio_hash = hashlib.sha256(raw_bytes).hexdigest()
    name = (getattr(audio_file, "name", "") or "").lower()
    is_wav = name.endswith(".wav") or raw_bytes[:4] == b"RIFF"

    # Non-audio binary payload rejection (when caller supplies real-sized garbage bytes)
    if len(raw_bytes) >= 44 and not _looks_like_audio_header(raw_bytes[:16]):
        raise InvalidSpeakingAudio("SPEAKING_AUDIO_INVALID_CONTAINER", "Audio fayl formati yaroqsiz yoki buzilgan.")

    decoded_ms: int | None = None
    is_verified = False

    if is_wav and len(raw_bytes) >= 44:
        max_bound = (duration_bounds(expected_seconds)[1] if expected_seconds else 1800.0)
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp.write(raw_bytes)
                tmp_path = tmp.name
            decoded_ms = measure_duration_subprocess(tmp_path, max_bound)
            is_verified = True
        except InvalidDuration as exc:
            raise InvalidSpeakingAudio(
                "SPEAKING_AUDIO_DURATION_INVALID",
                "Audio fayl buzilgan yoki davomiyligi talabga javob bermaydi.",
            ) from exc
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
    elif strict_decode or len(raw_bytes) >= 44:
        ext = Path(name).suffix.lower() or (".ogg" if raw_bytes[:4] == b"OggS" else ".webm")
        max_bound = (duration_bounds(expected_seconds)[1] if expected_seconds else 1800.0)
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                tmp.write(raw_bytes)
                tmp_path = tmp.name
            decoded_ms = measure_duration_subprocess(tmp_path, max_bound)
            is_verified = True
        except InvalidDuration as exc:
            raise InvalidSpeakingAudio(
                "SPEAKING_AUDIO_DURATION_INVALID",
                "Audio faylni dekod qilib bo'lmadi yoki davomiyligi talabga javob bermaydi.",
            ) from exc
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    if is_verified and decoded_ms is not None:
        sec = decoded_ms / 1000.0
        if expected_seconds is not None and not duration_accepted(expected_seconds, sec):
            raise InvalidSpeakingAudio(
                "SPEAKING_AUDIO_DURATION_INVALID",
                f"To'liq {expected_seconds} soniyalik javob yozilishi shart ({sec:.1f}s qabul qilinmadi).",
            )
        if min_seconds is not None and sec < min_seconds:
            raise InvalidSpeakingAudio(
                "SPEAKING_AUDIO_TOO_SHORT",
                f"Nutq davomiyligi juda qisqa ({sec:.1f}s < {min_seconds:.0f}s).",
            )

    return {
        "audio_hash": audio_hash,
        "decoded_duration_ms": decoded_ms,
        "is_verified_audio": is_verified,
        "decoded_seconds": round(decoded_ms / 1000.0) if decoded_ms is not None else None,
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(1)
    target = sys.argv[1]
    maximum = float(sys.argv[2]) if len(sys.argv) > 2 else None
    try:
        dur = decoded_duration(target, maximum)
    except Exception:
        raise SystemExit(1) from None
    print(json.dumps({"duration": dur, "policy": POLICY}))
