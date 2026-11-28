"""Phase 08 tests — Speaking AI 3.0: audio duration verifier, honest pronunciation, async eval & teacher review."""

from __future__ import annotations

import io
import wave
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.courses.models import StudentGroup
from apps.speaking.audio_verify import InvalidSpeakingAudio, inspect_uploaded_audio
from apps.speaking.models import SpeakingSubmission, SpeakingTopic
from apps.speaking.services import convert_multilevel_speaking_21_to_75, evaluate_speaking_submission
from apps.speaking.tasks import evaluate_speaking_submission_task

User = get_user_model()


def _make_wav_bytes(duration_sec: float = 3.0, rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    nframes = int(duration_sec * rate)
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(b"\x00\x00" * nframes)
    return buf.getvalue()


def _make_encoded_audio_bytes(fmt: str = "webm", codec: str = "libopus", duration_sec: float = 2.0) -> bytes:
    import os
    import tempfile
    import av

    buf = io.BytesIO()
    rate = 48000
    frame_size = 960  # 20ms at 48kHz
    total_samples = int(duration_sec * rate)
    # Write via temp file so Matroska/WebM muxer writes clean seekable duration metadata
    with tempfile.NamedTemporaryFile(suffix=f".{fmt}", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        with av.open(tmp_path, mode="w", format=fmt) as out:
            stream = out.add_stream(codec, rate=rate)
            stream.layout = "mono"
            pts = 0
            while pts < total_samples:
                frame = av.AudioFrame(format="flt", layout="mono", samples=frame_size)
                frame.sample_rate = rate
                frame.pts = pts
                for pkt in stream.encode(frame):
                    out.mux(pkt)
                pts += frame_size
            for pkt in stream.encode(None):
                out.mux(pkt)
        with open(tmp_path, "rb") as fh:
            buf.write(fh.read())
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
    return buf.getvalue()


def test_audio_duration_verifier_accepts_valid_wav_and_rejects_corrupt_or_short():
    wav_ok = SimpleUploadedFile("ok.wav", _make_wav_bytes(3.0), content_type="audio/wav")
    meta = inspect_uploaded_audio(wav_ok, expected_seconds=3)
    assert meta["is_verified_audio"] is True
    assert 2900 <= meta["decoded_duration_ms"] <= 3100
    assert len(meta["audio_hash"]) == 64

    # Real encoded WebM/Opus & OGG/Opus browser blobs decoded locally via PyAV
    webm_bytes = _make_encoded_audio_bytes(fmt="webm", codec="libopus", duration_sec=2.0)
    webm_ok = SimpleUploadedFile("rec.webm", webm_bytes, content_type="audio/webm;codecs=opus")
    webm_meta = inspect_uploaded_audio(webm_ok, expected_seconds=2)
    assert webm_meta["is_verified_audio"] is True
    assert 1500 <= webm_meta["decoded_duration_ms"] <= 2500

    ogg_bytes = _make_encoded_audio_bytes(fmt="ogg", codec="libopus", duration_sec=2.0)
    ogg_ok = SimpleUploadedFile("rec.ogg", ogg_bytes, content_type="audio/ogg;codecs=opus")
    ogg_meta = inspect_uploaded_audio(ogg_ok, expected_seconds=2)
    assert ogg_meta["is_verified_audio"] is True
    assert 1500 <= ogg_meta["decoded_duration_ms"] <= 2500

    # Corrupt RIFF payload rejected
    bad_wav = SimpleUploadedFile("bad.wav", b"RIFF" + b"\x00" * 60, content_type="audio/wav")
    with pytest.raises(InvalidSpeakingAudio) as exc:
        inspect_uploaded_audio(bad_wav)
    assert exc.value.code == "SPEAKING_AUDIO_DURATION_INVALID"

    # Corrupt WebM container (>=44 bytes) rejected cleanly by PyAV
    bad_webm = SimpleUploadedFile("bad.webm", b"\x1a\x45\xdf\xa3" + b"\x00" * 80, content_type="audio/webm")
    with pytest.raises(InvalidSpeakingAudio) as exc_webm:
        inspect_uploaded_audio(bad_webm)
    assert exc_webm.value.code == "SPEAKING_AUDIO_DURATION_INVALID"

    # Too short vs expected window (3.0s audio vs expected 10s)
    short_wav = SimpleUploadedFile("short.wav", _make_wav_bytes(3.0), content_type="audio/wav")
    with pytest.raises(InvalidSpeakingAudio) as exc2:
        inspect_uploaded_audio(short_wav, expected_seconds=10)
    assert exc2.value.code == "SPEAKING_AUDIO_DURATION_INVALID"


def test_multilevel_speaking_21_to_75_lookup_table():
    assert float(convert_multilevel_speaking_21_to_75(0)) == 0.0
    assert float(convert_multilevel_speaking_21_to_75(14)) == 51.0  # B2 threshold
    assert float(convert_multilevel_speaking_21_to_75(21)) == 75.0


@pytest.mark.django_db
def test_honest_pronunciation_policy_and_multilevel_async_and_teacher_review():
    teacher = User.objects.create_user(email="spk_teacher@example.com", password="StrongPassword123!", role="teacher")
    other_teacher = User.objects.create_user(email="spk_other@example.com", password="StrongPassword123!", role="teacher")
    student = User.objects.create_user(email="spk_student@example.com", password="StrongPassword123!", role="student")
    group = StudentGroup.objects.create(teacher=teacher, name="Speaking Group A", subject="english")
    group.students.add(student)

    topic_ielts = SpeakingTopic.objects.create(
        title="Technology Today",
        part=SpeakingTopic.PartChoice.PART2,
        prompt="Describe a piece of technology you find useful.",
    )
    topic_ml = SpeakingTopic.objects.create(
        title="Neighborhood Changes",
        part=SpeakingTopic.PartChoice.MULTILEVEL,
        prompt="Talk about changes in your town.",
    )

    # 1. Transcript-only evaluation keeps pronunciation_score=None and overall_band=None (never presents 3-criterion average as a complete IELTS Speaking band)
    eval_no_pron = {
        "fluency_score": 7.0,
        "lexical_score": 6.5,
        "grammar_score": 7.5,
        "pronunciation_score": None,
        "overall_band": 7.0,
        "feedback": {"summary": "Clear response."},
    }
    wav1 = SimpleUploadedFile("ans1.wav", _make_wav_bytes(4.0), content_type="audio/wav")
    with patch("apps.speaking.services._process_audio_stream_fish_audio", return_value="Smartphones organize daily schedules effectively."), \
         patch("apps.speaking.services._evaluate_speech_deepseek_r1", return_value=eval_no_pron):
        sub1 = evaluate_speaking_submission(wav1, topic_ielts.pk, student, duration_seconds=4, transcript_only=True)
    assert sub1.pronunciation_score is None
    assert sub1.overall_band is None
    assert sub1.final_score is None
    assert sub1.feedback.get("is_partial_estimate") is True
    assert sub1.feedback.get("partial_band_estimate") == 7.0
    assert sub1.feedback.get("pronunciation_status") == "not_measured_from_transcript"
    assert sub1.is_verified_audio is True

    # 2. Implicit audio access blocked for group teacher BEFORE explicit review request (privacy preserved)
    t_client = APIClient()
    t_client.force_authenticate(user=teacher)
    assert t_client.get(f"/api/v1/files/speaking/{sub1.pk}/audio/").status_code == 404
    assert t_client.post(f"/api/v1/speaking/teacher/{sub1.pk}/review/", {"score": 7.5}, format="json").status_code == 403

    # 3. Student requests teacher review -> group teacher can listen + grade; unrelated teacher blocked
    s_client = APIClient()
    s_client.force_authenticate(user=student)
    req_res = s_client.post(f"/api/v1/speaking/submissions/{sub1.pk}/request-review/", {}, format="json")
    assert req_res.status_code == 200
    assert req_res.data["submission"]["teacher_review_requested"] is True
    assert req_res.data["submission"]["status"] == "pending_teacher"

    queue_res = t_client.get("/api/v1/speaking/teacher/queue/")
    assert queue_res.status_code == 200
    assert any(item["id"] == sub1.pk for item in queue_res.data["pending"])
    assert t_client.get(f"/api/v1/files/speaking/{sub1.pk}/audio/").status_code == 200

    other_client = APIClient()
    other_client.force_authenticate(user=other_teacher)
    assert other_client.post(f"/api/v1/speaking/teacher/{sub1.pk}/review/", {"score": 7.5}, format="json").status_code == 403
    assert other_client.get(f"/api/v1/files/speaking/{sub1.pk}/audio/").status_code == 404

    rev_res = t_client.post(
        f"/api/v1/speaking/teacher/{sub1.pk}/review/",
        {"score": 7.5, "comments": "Strong vocabulary."},
        format="json",
    )
    assert rev_res.status_code == 200
    assert rev_res.data["submission"]["teacher_score"] == 7.5
    assert rev_res.data["submission"]["final_score"] == 7.5
    assert rev_res.data["submission"]["status"] == "completed"

    # 4. Async Celery flow + CEFR Multilevel /75 scoring
    ml_student = User.objects.create_user(email="spk_ml_student@example.com", password="StrongPassword123!", role="student")
    ml_client = APIClient()
    ml_client.force_authenticate(user=ml_student)
    wav2 = SimpleUploadedFile("ans2.wav", _make_wav_bytes(3.0), content_type="audio/wav")

    # Reject bad WAV at submit endpoint before queuing
    bad_upload = SimpleUploadedFile("bad2.wav", b"RIFF" + b"\x00" * 60, content_type="audio/wav")
    bad_res = ml_client.post(
        "/api/v1/speaking/submit/",
        {"audio": bad_upload, "topic_id": topic_ml.pk, "async": "1"},
        format="multipart",
    )
    assert bad_res.status_code == 400
    assert bad_res.data["code"] == "SPEAKING_AUDIO_DURATION_INVALID"

    with patch("apps.speaking.tasks.evaluate_speaking_submission_task.delay") as mock_delay:
        async_res = ml_client.post(
            "/api/v1/speaking/submit/",
            {"audio": wav2, "topic_id": topic_ml.pk, "async": "1"},
            format="multipart",
        )
    assert async_res.status_code == 202
    assert async_res.data["submission"]["status"] == "evaluating"
    assert async_res.data["submission"]["track"] == "cefr_multilevel"
    assert mock_delay.called
    sub2_id = async_res.data["submission"]["id"]

    eval_ml = {
        "fluency_score": 6.5,
        "lexical_score": 7.0,
        "grammar_score": 6.5,
        "pronunciation_score": 7.0,
        "overall_band": 7.0,
        "feedback": {"summary": "Solid B2 level performance."},
    }
    with patch("apps.speaking.services._process_audio_stream_fish_audio", return_value="Public parks have expanded significantly."), \
         patch("apps.speaking.services._evaluate_speech_deepseek_r1", return_value=eval_ml):
        task_out = evaluate_speaking_submission_task.apply(args=[sub2_id]).result
    assert task_out["ok"] is True
    sub2 = SpeakingSubmission.objects.get(pk=sub2_id)
    assert sub2.status == SpeakingSubmission.Status.COMPLETED
    assert sub2.task_scores.get("raw_max") == 21
    assert 50 <= float(sub2.final_score) <= 75
