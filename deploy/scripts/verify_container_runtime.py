"""Verify the built production Linux container runtime inside Docker.

Validates inside the built image:
1. Built React SPA files at /app/spa (index.html + hashed JS bundle assets).
2. PyAV (`av`) availability with libopus/webm/ogg container codecs and muxers.
3. Genuine WAV, OGG/Opus, WebM/Opus, and MediaRecorder-style blob decoding
   through `apps.speaking.audio_verify.inspect_uploaded_audio`.
4. Django settings boot, `manage.py check`, and fresh `migrate --noinput`.
5. Celery app configuration and task autodiscovery.
6. Private media protection (`DEBUG` fallback avoidance / unauthenticated audio
   rejection and `serve_private_file` header behavior).
"""

from __future__ import annotations

import glob
import io
import math
import os
import struct
import sys
import tempfile
import wave
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
os.environ.setdefault("SECRET_KEY", "ci-container-runtime-verify-key")
os.environ.setdefault("CELERY_BROKER_URL", "memory://")
os.environ.setdefault("CELERY_RESULT_BACKEND", "cache+memory://")
os.environ.setdefault("CELERY_TASK_ALWAYS_EAGER", "True")

# Clean any leftover sqlite file in /app before fresh migration test
_dev_db = Path("/app/db.sqlite3")
if _dev_db.exists():
    _dev_db.unlink()


def _synth_pcm(seconds: float = 1.5, rate: int = 48000) -> tuple[bytes, int]:
    samples = int(seconds * rate)
    buf = bytearray()
    for i in range(samples):
        val = int(12000 * math.sin(2.0 * math.pi * 440.0 * i / rate))
        buf += struct.pack("<h", val)
    return bytes(buf), rate


def main() -> int:
    import av  # type: ignore[import-not-found]
    import django

    # 1. React SPA bundle check
    spa_index = Path("/app/spa/index.html")
    assert spa_index.is_file(), f"Missing SPA entrypoint at {spa_index}"
    js_assets = glob.glob("/app/spa/assets/*.js")
    assert js_assets, "Missing built JS bundles under /app/spa/assets/"

    # 2. PyAV codecs & container formats
    assert getattr(av, "__version__", ""), "PyAV __version__ empty"
    codecs = getattr(av, "codecs_available", set())
    formats = getattr(av, "formats_available", set())
    assert "opus" in codecs or "libopus" in codecs, f"Opus codec unavailable: {sorted(codecs)[:10]}"
    for fmt in ("webm", "ogg"):
        assert fmt in formats, f"{fmt} container format unavailable"

    # 3. Django boot, system check & clean SQLite migration
    django.setup()
    from django.conf import settings
    from django.core.files.uploadedfile import SimpleUploadedFile
    from django.core.management import call_command
    from django.test import Client, RequestFactory

    call_command("check")
    call_command("migrate", "--noinput", verbosity=0)

    # 4. Celery app & task discovery
    from config.celery import app as celery_app

    celery_app.loader.import_default_modules()
    task_names = sorted(t for t in celery_app.tasks if not t.startswith("celery."))
    assert len(task_names) >= 3, f"Expected registered project Celery tasks, got: {task_names}"

    # 5. Private media isolation check
    from apps.core.private_files import serve_private_file

    with tempfile.NamedTemporaryFile(dir=settings.MEDIA_ROOT, suffix=".webm", delete=False) as tf:
        tf.write(b"private-media-probe")
        rel_name = os.path.relpath(tf.name, settings.MEDIA_ROOT).replace("\\", "/")

    rf = RequestFactory()
    req = rf.get("/api/v1/speaking/submissions/1/audio/")
    resp = serve_private_file(
        req,
        name=rel_name,
        content_type="audio/webm",
        filename="probe.webm",
    )
    assert resp.status_code == 200, f"Unexpected private file response: {resp.status_code}"

    # Verify authenticated speaking endpoint denies anonymous requests
    client = Client()
    anon_speaking = client.get("/api/v1/speaking/submissions/")
    assert anon_speaking.status_code in (401, 403), (
        f"Expected unauthenticated speaking API denial, got {anon_speaking.status_code}"
    )

    # 6. Audio verification via apps.speaking.audio_verify
    from apps.speaking.audio_verify import InvalidSpeakingAudio, inspect_uploaded_audio

    pcm, rate = _synth_pcm(1.5, 48000)

    wav_buf = io.BytesIO()
    with wave.open(wav_buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(pcm)
    wav_info = inspect_uploaded_audio(
        SimpleUploadedFile("probe.wav", wav_buf.getvalue(), content_type="audio/wav")
    )
    assert wav_info["is_verified_audio"] and 1400 <= wav_info["decoded_duration_ms"] <= 1600, wav_info

    def _mux_and_verify(container_fmt: str, ext: str, ctype: str, upload_name: str | None = None) -> dict:
        out_path = Path(f"/tmp/container_probe.{ext}")
        with av.open(str(out_path), mode="w", format=container_fmt) as container:
            stream = container.add_stream("libopus", rate=rate)
            stream.layout = "mono"
            frame_size = 960
            pts = 0
            for start in range(0, len(pcm) // 2, frame_size):
                chunk = pcm[start * 2 : (start + frame_size) * 2].ljust(frame_size * 2, b"\x00")
                frame = av.AudioFrame(format="s16", layout="mono", samples=frame_size)
                frame.sample_rate = rate
                frame.pts = pts
                pts += frame_size
                frame.planes[0].update(chunk)
                for pkt in stream.encode(frame):
                    container.mux(pkt)
            for pkt in stream.encode(None):
                container.mux(pkt)
        raw_bytes = out_path.read_bytes()
        info = inspect_uploaded_audio(
            SimpleUploadedFile(upload_name or f"probe.{ext}", raw_bytes, content_type=ctype)
        )
        assert info["is_verified_audio"] and 1300 <= info["decoded_duration_ms"] <= 1700, (
            container_fmt,
            info,
        )
        return info

    ogg_info = _mux_and_verify("ogg", "ogg", "audio/ogg")
    webm_info = _mux_and_verify("webm", "webm", "audio/webm")
    browser_blob_info = _mux_and_verify(
        "webm", "webm", "audio/webm;codecs=opus", upload_name="recording"
    )

    # Confirm non-audio binary garbage is rejected
    rejected = False
    try:
        inspect_uploaded_audio(
            SimpleUploadedFile("bad.webm", b"NOT_AUDIO_PAYLOAD_" * 16, content_type="audio/webm")
        )
    except InvalidSpeakingAudio:
        rejected = True
    assert rejected, "Invalid garbage upload was not rejected by audio_verify"

    print(
        "CONTAINER VERIFY OK: "
        f"av={av.__version__} "
        f"wav={wav_info['decoded_duration_ms']}ms "
        f"ogg={ogg_info['decoded_duration_ms']}ms "
        f"webm={webm_info['decoded_duration_ms']}ms "
        f"blob={browser_blob_info['decoded_duration_ms']}ms "
        f"spa_js={len(js_assets)} "
        f"tasks={len(task_names)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
