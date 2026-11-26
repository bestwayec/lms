"""Phase 09-10 tests — IELTS Academic/General & CEFR Multilevel v2 Full Mock Engines."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.courses.models import Course
from apps.tests import cefr_multilevel
from apps.tests.blueprints import (
    convert_multilevel_speaking_21_to_75,
    convert_multilevel_writing_16_to_75,
    raw_to_ielts_listening_band,
    raw_to_ielts_reading_band,
    respects_word_limit_rule,
)
from apps.tests.models import Choice, ExamSection, Question, Test, TestAttempt
from apps.tests.services import StartAttemptService

User = get_user_model()


def test_ielts_separate_reading_tables_and_word_limit_rules():
    # Academic vs General Reading conversion tables remain strictly separate
    assert raw_to_ielts_reading_band(30, 40, "ielts_academic") == Decimal("7.0")
    assert raw_to_ielts_reading_band(30, 40, "ielts_general") == Decimal("6.0")
    assert raw_to_ielts_reading_band(37, 40, "ielts_academic") == Decimal("8.5")
    assert raw_to_ielts_reading_band(37, 40, "ielts_general") == Decimal("8.0")
    assert raw_to_ielts_listening_band(26, 40) == Decimal("6.5")

    # Word limit rule checks
    assert respects_word_limit_rule("library", "ONE_WORD") is True
    assert respects_word_limit_rule("city library", "ONE_WORD") is False
    assert respects_word_limit_rule("25", "ONE_WORD") is False
    assert respects_word_limit_rule("25 books", "ONE_WORD_AND_OR_NUMBER") is True
    assert respects_word_limit_rule("two large books", "ONE_WORD_AND_OR_NUMBER") is False

    # UZBMB Writing (16 -> 75) and Speaking (21 -> 75) lookup tables
    assert cefr_multilevel.rated_to_scaled(Decimal("11"), Decimal("16")) == convert_multilevel_writing_16_to_75(11)
    assert cefr_multilevel.rated_to_scaled(Decimal("14"), Decimal("21")) == convert_multilevel_speaking_21_to_75(14)


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
