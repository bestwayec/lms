"""Phase 04 tests — Listening Engine: Range streaming, play limits, transcripts & WAV fixtures."""

import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from rest_framework.test import APIClient

from apps.courses.models import Course
from apps.tests.audio_fixtures import generate_synthetic_wav
from apps.tests.models import ExamPart, ExamSection, Question, QuestionGroup, Test

User = get_user_model()


@pytest.mark.django_db
def test_listening_range_streaming_does_not_count_play_and_enforces_strict_limit():
    teacher = User.objects.create_user(email="t_lis@example.com", password="StrongPassword123!", role="teacher")
    student = User.objects.create_user(email="s_lis@example.com", password="StrongPassword123!", role="student")
    course = Course.objects.create(title="Listening Course", teacher=teacher)
    test = Test.objects.create(
        title="IELTS Listening Mock",
        subject="english",
        exam_type=Test.ExamType.IELTS_ACADEMIC,
        course=course,
        status=Test.Status.PUBLISHED,
    )
    sec = ExamSection.objects.create(test=test, code="LISTENING", name="Listening", order=1)
    part = ExamPart.objects.create(
        section=sec,
        number="1",
        part_number=1,
        title="Part 1",
        audio_play_limit=1,
        transcript="Caller asks for library membership.",
        order=1,
    )
    wav_bytes = generate_synthetic_wav(duration_seconds=1.0)
    assert wav_bytes[:4] == b"RIFF"
    part.audio.save("test_lis_part1.wav", ContentFile(wav_bytes), save=True)
    grp = QuestionGroup.objects.create(part=part, title="Notes", order=1)
    Question.objects.create(
        test=test,
        section=sec,
        group=grp,
        text="Name?",
        question_type=Question.QuestionType.SHORT_ANSWER,
        audio_start_sec=0.4,
        position=1,
    )

    client = APIClient()
    client.force_authenticate(user=student)

    # Strict mode hides transcript & audio_start_sec
    start = client.post(f"/api/tests/{test.id}/start/", {"mode": "strict"}, format="json")
    attempt_id = start.data["id"]
    detail = client.get(f"/api/tests/attempts/{attempt_id}/")
    assert detail.status_code == 200
    assert detail.data["structure"][0]["parts"][0]["transcript"] == ""
    assert "audio_start_sec" not in detail.data["questions"][0]

    # HTTP Range probe returns 206 Partial Content & MUST NOT consume plays
    stream_url = detail.data["structure"][0]["parts"][0]["private_audio_url"]
    r_probe1 = client.get(stream_url, HTTP_RANGE="bytes=0-199")
    r_probe2 = client.get(stream_url, HTTP_RANGE="bytes=200-399")
    assert r_probe1.status_code == 206
    assert r_probe2.status_code == 206
    assert r_probe1["Accept-Ranges"] == "bytes"
    assert r_probe1["Content-Range"].startswith("bytes 0-199/")

    sched_before = client.get(f"/api/tests/attempts/{attempt_id}/listening/{part.id}/play/")
    assert sched_before.status_code == 200
    assert sched_before.data["plays_used"] == 0
    assert sched_before.data["remaining_plays"] == 1

    # First official play consumes limit
    play1 = client.post(
        f"/api/tests/attempts/{attempt_id}/listening/{part.id}/play/",
        {"duration_seconds": 60},
        format="json",
    )
    assert play1.status_code == 200
    assert play1.data["plays_used"] == 1
    assert play1.data["remaining_plays"] == 0
    assert play1.data["reading_ends_at"] is not None

    # Second official play in strict mode rejected
    play2 = client.post(f"/api/tests/attempts/{attempt_id}/listening/{part.id}/play/", {}, format="json")
    assert play2.status_code == 400


@pytest.mark.django_db
def test_listening_practice_mode_allows_replays_and_exposes_transcript_and_timestamps():
    teacher = User.objects.create_user(email="t_lis_p@example.com", password="StrongPassword123!", role="teacher")
    student = User.objects.create_user(email="s_lis_p@example.com", password="StrongPassword123!", role="student")
    course = Course.objects.create(title="Listening Practice", teacher=teacher)
    test = Test.objects.create(
        title="IELTS Listening Practice",
        subject="english",
        exam_type=Test.ExamType.IELTS_ACADEMIC,
        course=course,
        status=Test.Status.PUBLISHED,
    )
    sec = ExamSection.objects.create(test=test, code="LISTENING", name="Listening", order=1)
    part = ExamPart.objects.create(
        section=sec,
        number="1",
        audio_play_limit=1,
        transcript="Practice transcript text here.",
        order=1,
    )
    grp = QuestionGroup.objects.create(part=part, title="Notes", order=1)
    Question.objects.create(
        test=test,
        section=sec,
        group=grp,
        text="Q1",
        question_type=Question.QuestionType.SHORT_ANSWER,
        audio_start_sec=14.2,
        position=1,
    )

    client = APIClient()
    client.force_authenticate(user=student)
    start = client.post(f"/api/tests/{test.id}/start/", {"mode": "practice"}, format="json")
    attempt_id = start.data["id"]

    detail = client.get(f"/api/tests/attempts/{attempt_id}/")
    assert detail.status_code == 200
    assert detail.data["structure"][0]["parts"][0]["transcript"] == "Practice transcript text here."
    assert detail.data["questions"][0]["audio_start_sec"] == 14.2

    # Replays allowed unlimited in practice mode
    p1 = client.post(f"/api/tests/attempts/{attempt_id}/listening/{part.id}/play/", {}, format="json")
    p2 = client.post(f"/api/tests/attempts/{attempt_id}/listening/{part.id}/play/", {}, format="json")
    assert p1.status_code == 200 and p2.status_code == 200
    assert p2.data["plays_used"] == 2
    assert p2.data["remaining_plays"] is None
