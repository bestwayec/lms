"""Phase 12 tests — Teacher English Workspace, Separated Analytics, RBAC, Formula-Safe CSV & Paginated PDF."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.courses.models import Course, StudentGroup
from apps.essays.models import EssaySubmission, EssayTopic
from apps.speaking.models import SpeakingSubmission, SpeakingTopic
from apps.tests.models import Test, TestAttempt

User = get_user_model()


@pytest.mark.django_db
def test_teacher_english_workspace_separation_rbac_and_safe_exports():
    teacher = User.objects.create_user(email="te_teacher@example.com", password="StrongPassword123!", role="teacher")
    other_teacher = User.objects.create_user(email="te_other@example.com", password="StrongPassword123!", role="teacher")
    student = User.objects.create_user(
        email="te_student@example.com",
        password="StrongPassword123!",
        role="student",
        first_name="=HYPERLINK(\"http://evil\",\"Ali\")",
    )
    group = StudentGroup.objects.create(teacher=teacher, name="IELTS Cohort 1", subject="english")
    group.students.add(student)

    # Student blocked from teacher endpoint
    s_client = APIClient()
    s_client.force_authenticate(user=student)
    assert s_client.get("/api/v1/english/teacher/workspace/").status_code == 403

    # Create English IELTS & Multilevel artifacts
    topic_w = EssayTopic.objects.create(
        title="Climate Policy", subject="english", rubric_type="ielts_task2", word_limit_min=250
    )
    EssaySubmission.objects.create(
        student=student,
        topic=topic_w,
        essay_text="Climate investment drives growth.",
        word_count=4,
        max_score=9,
        total_score=7.0,
        status=EssaySubmission.Status.PENDING_TEACHER,
    )
    topic_s = SpeakingTopic.objects.create(title="Future Cities", part=SpeakingTopic.PartChoice.PART2, prompt="Describe a city.")
    SpeakingSubmission.objects.create(
        user=student,
        topic=topic_s,
        track=SpeakingSubmission.Track.IELTS,
        overall_band=6.5,
        teacher_review_requested=True,
        status=SpeakingSubmission.Status.PENDING_TEACHER,
    )
    course = Course.objects.create(teacher=teacher, title="English Hub", slug="eng-hub-p12")
    ielts_test = Test.objects.create(course=course, title="=CMD|IELTS Ac 1", subject="english", exam_type=Test.ExamType.IELTS_ACADEMIC)
    ml_test = Test.objects.create(course=course, title="Multilevel B2", subject="english", exam_type=Test.ExamType.CEFR_MULTILEVEL)
    TestAttempt.objects.create(student=student, test=ielts_test, band_score=7.5, status=TestAttempt.Status.COMPLETED)
    TestAttempt.objects.create(student=student, test=ml_test, cefr_level="B2", section_scores={"LISTENING": {"score": 58}}, status=TestAttempt.Status.COMPLETED)

    t_client = APIClient()
    t_client.force_authenticate(user=teacher)
    ws_res = t_client.get("/api/v1/english/teacher/workspace/")
    assert ws_res.status_code == 200
    assert len(ws_res.data["inbox"]["writing"]) == 1
    assert len(ws_res.data["inbox"]["speaking"]) == 1
    # IELTS (/9) and Multilevel (/75) scales kept strictly separate
    assert ws_res.data["ielts_analytics"]["avg_band"] == 7.5
    assert ws_res.data["multilevel_analytics"]["avg_score_75"] == 58.0

    # Other teacher sees empty inbox / cannot access te_student's data
    other_client = APIClient()
    other_client.force_authenticate(user=other_teacher)
    other_ws = other_client.get("/api/v1/english/teacher/workspace/")
    assert other_ws.status_code == 200
    assert len(other_ws.data["inbox"]["writing"]) == 0
    assert len(other_ws.data["inbox"]["speaking"]) == 0

    # Formula-safe CSV export neutralizes leading '=' with leading quote
    csv_res = t_client.get("/api/v1/english/teacher/export/?export_format=csv")
    assert csv_res.status_code == 200
    csv_body = csv_res.content.decode("utf-8")
    assert "'=HYPERLINK" in csv_body
    assert "'=CMD|IELTS" in csv_body

    # Paginated PDF export starts cleanly with %PDF
    pdf_res = t_client.get("/api/v1/english/teacher/export/?export_format=pdf")
    assert pdf_res.status_code == 200
    assert pdf_res.content[:4] == b"%PDF"
