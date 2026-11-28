"""Phase 09-10 tests — IELTS Academic/General & CEFR Multilevel v2 Full Mock Engines."""

from __future__ import annotations

from decimal import Decimal
import io
import wave

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.courses.models import Course, StudentGroup
from apps.results.models import Result
from apps.speaking.models import SpeakingSubmission
from apps.tests import cefr_multilevel
from apps.tests.blueprints import (
    SOURCES,
    convert_multilevel_speaking_21_to_75,
    convert_multilevel_writing_16_to_75,
    get_blueprint,
    raw_to_ielts_listening_band,
    raw_to_ielts_reading_band,
    respects_word_limit_rule,
    score_ielts_sections,
)
from apps.tests.models import Choice, ExamSection, ExamWrittenBridge, Question, Test, TestAttempt
from apps.tests.scoring import QuestionScore
from apps.tests.services import StartAttemptService

User = get_user_model()


def test_ielts_separate_reading_tables_and_word_limit_rules():
    # Official IELTS Academic vs General Reading conversion tables across key band cutoffs
    ac_expected = {
        10: Decimal("4.0"), 15: Decimal("5.0"), 19: Decimal("5.5"), 23: Decimal("6.0"),
        27: Decimal("6.5"), 30: Decimal("7.0"), 33: Decimal("7.5"), 35: Decimal("8.0"),
        37: Decimal("8.5"), 39: Decimal("9.0"), 40: Decimal("9.0"),
    }
    gt_expected = {
        10: Decimal("3.0"), 15: Decimal("4.0"), 19: Decimal("4.5"), 23: Decimal("5.0"),
        27: Decimal("5.5"), 30: Decimal("6.0"), 33: Decimal("6.5"), 35: Decimal("7.0"),
        37: Decimal("8.0"), 39: Decimal("8.5"), 40: Decimal("9.0"),
    }
    for raw_score, expected_band in ac_expected.items():
        assert raw_to_ielts_reading_band(raw_score, 40, "ielts_academic") == expected_band
    for raw_score, expected_band in gt_expected.items():
        assert raw_to_ielts_reading_band(raw_score, 40, "ielts_general") == expected_band
    assert raw_to_ielts_listening_band(26, 40) == Decimal("6.5")

    # Official IELTS Writing Task 2 weighting (2x Task 1): (5.0 + 2*8.0)/3 = 7.0 (not 6.5 naive average)
    w_res = score_ielts_sections(
        [
            QuestionScore(question_id=1, section_code="WRITING", kind="written", maximum=Decimal("9"), earned=Decimal("5.0"), is_correct=True, answered=True),
            QuestionScore(question_id=2, section_code="WRITING", kind="written", maximum=Decimal("9"), earned=Decimal("8.0"), is_correct=True, answered=True),
        ],
        exam_type="ielts_academic",
    )
    assert w_res["sections"]["WRITING"]["band"] == 7.0

    # Word limit rule checks
    assert respects_word_limit_rule("library", "ONE_WORD") is True
    assert respects_word_limit_rule("city library", "ONE_WORD") is False
    assert respects_word_limit_rule("25", "ONE_WORD") is False
    assert respects_word_limit_rule("25 books", "ONE_WORD_AND_OR_NUMBER") is True
    assert respects_word_limit_rule("two large books", "ONE_WORD_AND_OR_NUMBER") is False

    # UZBMB Multilevel lookup tables + threshold boundaries (B1>=38, B2>=51, C1>=65)
    assert cefr_multilevel.rated_to_scaled(Decimal("11"), Decimal("16")) == convert_multilevel_writing_16_to_75(11)
    assert cefr_multilevel.rated_to_scaled(Decimal("14"), Decimal("21")) == convert_multilevel_speaking_21_to_75(14)
    assert cefr_multilevel.level_for(37) == "BELOW_B1"
    assert cefr_multilevel.level_for(38) == "B1"
    assert cefr_multilevel.level_for(50) == "B1"
    assert cefr_multilevel.level_for(51) == "B2"
    assert cefr_multilevel.level_for(64) == "B2"
    assert cefr_multilevel.level_for(65) == "C1"

    # Blueprint source citations & timing/estimate disclosures
    ac_bp = get_blueprint("ielts_academic")
    ml_bp = get_blueprint("cefr_multilevel")
    assert ac_bp["is_official"] is False
    assert ml_bp["is_official"] is False
    assert len(ac_bp["sources"]) >= 2 and all(k in SOURCES for k in ac_bp["sources"])
    assert ml_bp["sections"][0]["audio_plays"] == 2
    assert ml_bp["sections"][3]["duration_approximate"] is True


def _build_full_ielts_mock(teacher, exam_type: str, title: str) -> tuple[Test, dict[str, Question]]:
    course = Course.objects.create(teacher=teacher, title=f"Course {title}", slug=f"course-{exam_type}-{teacher.id}")
    test = Test.objects.create(
        course=course,
        title=title,
        exam_type=exam_type,
        assessment_category=Test.AssessmentCategory.FULL_MOCK,
        status=Test.Status.PUBLISHED,
        time_limit_minutes=150,
    )
    l_sec = ExamSection.objects.create(test=test, code="LISTENING", name="Listening", order=1)
    r_sec = ExamSection.objects.create(test=test, code="READING", name="Reading", order=2)
    w_sec = ExamSection.objects.create(test=test, code="WRITING", name="Writing", order=3)

    lq = Question.objects.create(
        test=test,
        section=l_sec,
        question_type=Question.QuestionType.TEXT_MATCH,
        text="Airport bus number?",
        correct_text="14|fourteen",
        config={"word_limit_rule": "ONE_WORD_AND_OR_NUMBER"},
        points=1,
        position=1,
    )
    rq = Question.objects.create(
        test=test,
        section=r_sec,
        question_type=Question.QuestionType.SINGLE_CHOICE,
        text="Main theme?",
        points=1,
        position=2,
    )
    r_ok = Choice.objects.create(question=rq, text="Solar adoption", is_correct=True, position=1)
    Choice.objects.create(question=rq, text="Coal mining", is_correct=False, position=2)

    wq = Question.objects.create(
        test=test,
        section=w_sec,
        question_type=Question.QuestionType.WRITTEN,
        text="Discuss renewable energy investments.",
        points=9,
        position=3,
    )
    return test, {"listening": lq, "reading": rq, "reading_choice": r_ok, "writing": wq}


@pytest.mark.django_db
def test_ielts_academic_and_general_mock_lifecycle_holds_overall_when_writing_pending():
    teacher = User.objects.create_user(email="m9_teacher@example.com", password="StrongPassword123!", role="teacher")
    student = User.objects.create_user(email="m9_student@example.com", password="StrongPassword123!", role="student")

    ac_test, refs = _build_full_ielts_mock(teacher, Test.ExamType.IELTS_ACADEMIC, "IELTS Academic Full Mock 1")
    client = APIClient()
    client.force_authenticate(user=student)

    # Blueprints endpoint check
    bp_res = client.get("/api/tests/english/blueprints/")
    assert bp_res.status_code == 200
    assert "ielts_academic" in bp_res.data["blueprints"]
    assert "ielts_general" in bp_res.data["blueprints"]
    assert bp_res.data["blueprints"]["cefr_multilevel"]["spec_version"] == "UZBMB_MULTILEVEL_EN_2026_V2"

    attempt = StartAttemptService.execute(test_id=ac_test.id, student=student, mode="practice")
    client.post(
        f"/api/tests/attempts/{attempt.id}/save-batch/",
        {
            "answers": [
                {"question_id": refs["listening"].id, "text_answer": "14"},
                {"question_id": refs["reading"].id, "choice_ids": [refs["reading_choice"].id]},
                {"question_id": refs["writing"].id, "written_text": "Renewable energy lowers long term emissions."},
            ]
        },
        format="json",
    )

    sub_res = client.post(f"/api/tests/attempts/{attempt.id}/submit/", format="json")
    assert sub_res.status_code == 200
    attempt.refresh_from_db()
    assert attempt.status == TestAttempt.Status.PENDING_GRADING
    assert attempt.band_score is None  # Overall NEVER invented while Writing is pending!
    assert attempt.section_scores["LISTENING"]["status"] == "scored"
    assert attempt.section_scores["READING"]["status"] == "scored"
    assert attempt.section_scores["WRITING"]["status"] == "pending"

    card_res = client.get(f"/api/tests/attempts/{attempt.id}/certificate-card/")
    assert card_res.status_code == 200
    assert card_res.data["overall_band"] is None
    assert card_res.data["grading_status"] == "pending_grading"
    assert card_res.data["is_estimate"] is True
    assert "READING" in card_res.data["sections"]


@pytest.mark.django_db
def test_cefr_multilevel_v2_mock_holds_overall_when_rated_section_pending():
    teacher = User.objects.create_user(email="m10_teacher@example.com", password="StrongPassword123!", role="teacher")
    student = User.objects.create_user(email="m10_student@example.com", password="StrongPassword123!", role="student")

    course = Course.objects.create(teacher=teacher, title="CEFR B2", slug="cefr-b2-mock")
    test = Test.objects.create(
        course=course,
        title="UZBMB Multilevel Full Mock 1",
        exam_type=Test.ExamType.CEFR_MULTILEVEL,
        assessment_category=Test.AssessmentCategory.FULL_MOCK,
        status=Test.Status.PUBLISHED,
    )
    l_sec = ExamSection.objects.create(test=test, code="LISTENING", name="Listening", order=1)
    r_sec = ExamSection.objects.create(test=test, code="READING", name="Reading", order=2)
    w_sec = ExamSection.objects.create(test=test, code="WRITING", name="Writing", order=3)

    lq = Question.objects.create(test=test, section=l_sec, question_type=Question.QuestionType.TEXT_MATCH, text="L1", correct_text="yes", points=1, position=1)
    rq = Question.objects.create(test=test, section=r_sec, question_type=Question.QuestionType.TEXT_MATCH, text="R1", correct_text="blue", points=1, position=2)
    wq = Question.objects.create(test=test, section=w_sec, question_type=Question.QuestionType.WRITTEN, text="Write a letter", points=16, position=3)

    attempt = StartAttemptService.execute(test_id=test.id, student=student, mode="practice")
    client = APIClient()
    client.force_authenticate(user=student)
    client.post(
        f"/api/tests/attempts/{attempt.id}/save-batch/",
        {
            "answers": [
                {"question_id": lq.id, "text_answer": "yes"},
                {"question_id": rq.id, "text_answer": "blue"},
                {"question_id": wq.id, "written_text": "Dear organizer, I am writing to apply."},
            ]
        },
        format="json",
    )
    sub_res = client.post(f"/api/tests/attempts/{attempt.id}/submit/", format="json")
    assert sub_res.status_code == 200
    attempt.refresh_from_db()
    assert attempt.status == TestAttempt.Status.PENDING_GRADING
    assert attempt.band_score is None  # Never leaks IELTS band into Multilevel

    card = client.get(f"/api/tests/attempts/{attempt.id}/certificate-card/")
    assert card.status_code == 200
    assert card.data["scale"] == "cefr_multilevel"
    assert card.data["is_estimate"] is True
    assert card.data["overall"] is None  # Pending Writing + missing Speaking


def _make_mock_wav(duration_sec: float = 2.0, rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    nframes = int(duration_sec * rate)
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(b"\x00\x00" * nframes)
    return buf.getvalue()


def test_ielts_writing_task2_double_weighting_and_blueprint_sources():
    # Official IELTS rule: Task 2 counts twice as much as Task 1 -> (T1 + 2*T2) / 3
    # T1=6.0, T2=7.5 -> (6.0 + 15.0)/3 = 7.0
    q_scores = [
        QuestionScore(question_id=1, earned=Decimal("40"), maximum=Decimal("40"), is_correct=True, answered=True, section_code="LISTENING"),
        QuestionScore(question_id=2, earned=Decimal("30"), maximum=Decimal("40"), is_correct=True, answered=True, section_code="READING"),
        QuestionScore(question_id=3, earned=Decimal("6.0"), maximum=Decimal("9.0"), is_correct=True, answered=True, section_code="WRITING", kind="written"),
        QuestionScore(question_id=4, earned=Decimal("7.5"), maximum=Decimal("9.0"), is_correct=True, answered=True, section_code="WRITING", kind="written"),
        QuestionScore(question_id=5, earned=Decimal("7.0"), maximum=Decimal("9.0"), is_correct=True, answered=True, section_code="SPEAKING", kind="written"),
    ]
    summary = score_ielts_sections(q_scores, exam_type="ielts_academic")
    assert summary["sections"]["WRITING"]["band"] == 7.0  # unweighted would be 6.75 -> 7.0; test asymmetric case next

    q_asym = [
        QuestionScore(question_id=1, earned=Decimal("5.5"), maximum=Decimal("9.0"), is_correct=True, answered=True, section_code="WRITING", kind="written"),
        QuestionScore(question_id=2, earned=Decimal("7.5"), maximum=Decimal("9.0"), is_correct=True, answered=True, section_code="WRITING", kind="written"),
    ]
    # Unweighted avg = 6.5; weighted (5.5 + 15.0)/3 = 6.833 -> 7.0!
    asym = score_ielts_sections(q_asym, exam_type="ielts_academic")
    assert asym["sections"]["WRITING"]["band"] == 7.0

    # Blueprint official sources & Multilevel 30-min speaking cap disclosure
    bp_all = get_blueprint()
    assert "ielts-scoring" in SOURCES
    assert "uzbmb-speaking-format" in SOURCES
    ml_bp = bp_all["blueprints"]["cefr_multilevel"]
    spk_sec = next(s for s in ml_bp["sections"] if s["code"] == "SPEAKING")
    assert spk_sec["duration_minutes"] == 30
    assert spk_sec["duration_approximate"] is True
    assert spk_sec["official_expected_minutes"] == 15


@pytest.mark.parametrize("exam_type", [Test.ExamType.IELTS_ACADEMIC, Test.ExamType.IELTS_GENERAL, Test.ExamType.CEFR_MULTILEVEL])
@pytest.mark.django_db
def test_complete_four_skill_mock_journey_with_speaking_upload_teacher_review_and_gradebook(exam_type: str):
    teacher = User.objects.create_user(email=f"full_{exam_type}_t@example.com", password="StrongPassword123!", role="teacher")
    student = User.objects.create_user(email=f"full_{exam_type}_s@example.com", password="StrongPassword123!", role="student")
    group = StudentGroup.objects.create(teacher=teacher, name=f"Cohort {exam_type}", subject="english")
    group.students.add(student)

    course = Course.objects.create(teacher=teacher, title=f"Course {exam_type}", slug=f"full-mock-{exam_type}-{teacher.id}")
    test = Test.objects.create(
        course=course,
        created_by=teacher,
        title=f"Full Four-Skill Mock ({exam_type})",
        subject="english",
        exam_type=exam_type,
        assessment_category=Test.AssessmentCategory.FULL_MOCK,
        status=Test.Status.PUBLISHED,
        time_limit_minutes=180,
    )
    l_sec = ExamSection.objects.create(test=test, code="LISTENING", name="Listening", order=1)
    r_sec = ExamSection.objects.create(test=test, code="READING", name="Reading", order=2)
    w_sec = ExamSection.objects.create(test=test, code="WRITING", name="Writing", order=3)
    s_sec = ExamSection.objects.create(test=test, code="SPEAKING", name="Speaking", order=4)

    lq = Question.objects.create(test=test, section=l_sec, question_type=Question.QuestionType.TEXT_MATCH, text="Departure time?", correct_text="nine", points=1, position=1)
    rq = Question.objects.create(test=test, section=r_sec, question_type=Question.QuestionType.SINGLE_CHOICE, text="Key factor?", points=1, position=2)
    rc = Choice.objects.create(question=rq, text="Solar storage", is_correct=True, position=1)
    Choice.objects.create(question=rq, text="Coal", is_correct=False, position=2)

    is_ml = exam_type == Test.ExamType.CEFR_MULTILEVEL
    wq = Question.objects.create(test=test, section=w_sec, question_type=Question.QuestionType.WRITTEN, text="Write essay response.", points=16 if is_ml else 9, position=3)
    sq = Question.objects.create(test=test, section=s_sec, question_type=Question.QuestionType.SPEAKING_PROMPT, text="Describe an inspiring book.", config={"prep_seconds": 1, "answer_seconds": 3}, points=21 if is_ml else 9, position=4)

    s_client = APIClient()
    s_client.force_authenticate(user=student)
    attempt = StartAttemptService.execute(test_id=test.id, student=student, mode="strict")

    # 1. Complete Listening, Reading, and Writing answers
    s_client.post(
        f"/api/tests/attempts/{attempt.id}/save-batch/",
        {
            "answers": [
                {"question_id": lq.id, "text_answer": "nine"},
                {"question_id": rq.id, "choice_ids": [rc.id]},
                {"question_id": wq.id, "written_text": "Renewable energy strengthens grid resilience and reduces harmful urban emissions significantly over the long term."},
            ]
        },
        format="json",
    )

    # 2. Record & upload Speaking audio directly on the mock attempt + verify duplicate hash protection
    wav_blob = SimpleUploadedFile("speaking_part.wav", _make_mock_wav(2.0), content_type="audio/wav")
    spk_up = s_client.post(
        f"/api/tests/attempts/{attempt.id}/questions/{sq.id}/speaking/",
        {"audio": wav_blob, "duration_seconds": "2"},
        format="multipart",
    )
    assert spk_up.status_code == 201
    spk_sub_id = spk_up.data["submission_id"]
    assert spk_up.data["is_verified_audio"] is True

    wav_dup = SimpleUploadedFile("speaking_part.wav", _make_mock_wav(2.0), content_type="audio/wav")
    spk_dup = s_client.post(
        f"/api/tests/attempts/{attempt.id}/questions/{sq.id}/speaking/",
        {"audio": wav_dup, "duration_seconds": "2"},
        format="multipart",
    )
    assert spk_dup.status_code == 200
    assert spk_dup.data["duplicate"] is True
    assert spk_dup.data["submission_id"] == spk_sub_id

    # 3. Submit attempt -> PENDING_GRADING, no invented overall band
    sub_res = s_client.post(f"/api/tests/attempts/{attempt.id}/submit/", format="json")
    assert sub_res.status_code == 200
    attempt.refresh_from_db()
    assert attempt.status == TestAttempt.Status.PENDING_GRADING
    assert attempt.band_score is None
    assert attempt.section_scores["WRITING"]["status"] == "pending"
    assert attempt.section_scores["SPEAKING"]["status"] == "pending"

    # 4. Teacher completes Writing review + Speaking review -> auto-finalizes Attempt & Result
    t_client = APIClient()
    t_client.force_authenticate(user=teacher)
    ws_before = t_client.get("/api/v1/english/teacher/workspace/")
    assert ws_before.status_code == 200
    assert any(m["attempt_id"] == attempt.id for m in ws_before.data["inbox"]["mocks"])

    bridge = ExamWrittenBridge.objects.get(attempt=attempt, question=wq)
    if is_ml:
        w_payload = {"criteria_scores": {"1": 4.0, "2": 4.0, "3": 5.0}, "teacher_comments": "Good coherence."}
        s_score = 58.0
    else:
        w_payload = {"criteria_scores": {"1": 7.0, "2": 7.0, "3": 7.5, "4": 6.5}, "teacher_comments": "Well argued."}
        s_score = 7.5

    rev_w = t_client.post(f"/api/v1/essays/teacher/{bridge.essay_submission_id}/review/", w_payload, format="json")
    assert rev_w.status_code == 200

    # Still pending until Speaking is also finalized
    attempt.refresh_from_db()
    assert attempt.status == TestAttempt.Status.PENDING_GRADING

    rev_s = t_client.post(f"/api/v1/speaking/teacher/{spk_sub_id}/review/", {"score": s_score, "comments": "Fluent."}, format="json")
    assert rev_s.status_code == 200

    # Now finalized automatically!
    attempt.refresh_from_db()
    assert attempt.status == TestAttempt.Status.COMPLETED
    result = Result.objects.get(attempt=attempt)
    assert result.grading_status == "graded"
    assert attempt.section_scores["WRITING"]["status"] == "scored"
    assert attempt.section_scores["SPEAKING"]["status"] == "scored"
    if is_ml:
        assert attempt.band_score is None
        assert attempt.cefr_level in ("B1", "B2", "C1")
    else:
        assert attempt.band_score is not None and float(attempt.band_score) >= 6.5

    # 5. Verify Gradebook, Result History & Teacher English Workspace CSV/XLSX/PDF parity
    gb_res = t_client.get(f"/api/tests/{test.id}/gradebook/")
    assert gb_res.status_code == 200
    assert any(r["attempt_id"] == attempt.id and r["grading_status"] == "graded" for r in gb_res.data["students"])

    for fmt in ("csv", "xlsx", "pdf"):
        exp = t_client.get(f"/api/v1/english/teacher/export/?export_format={fmt}")
        assert exp.status_code == 200
        assert len(exp.content) > 50
