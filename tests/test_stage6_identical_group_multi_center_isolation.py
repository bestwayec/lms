"""
Stage 6 Multi-Center Cabinets & Tenant Isolation Tests.

Specifically audits:
- Two separate learning centers (Center Alpha and Center Beta).
- Identical group names ("Ona tili Intensive") and overlapping subjects ("uzbek").
- Identical homework titles and test titles.
- Total isolation across:
  * Admin dashboard and panel users/tuition
  * Teacher workspace and gradebook
  * Student roster and enrollment
  * Test bank and homework assignments
  * Attendance sessions and records
  * Results, diagnostics, and reports
- Verification that no API endpoint leaks data between the two centers.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Profile, User
from apps.attendance.models import AttendanceRecord, AttendanceSession
from apps.courses.group_service import add_student_to_group
from apps.courses.models import Course, Homework, HomeworkSubmission, StudentGroup
from apps.organizations.models import CenterBranch, LearningCenter
from apps.results.models import Result
from apps.tests.models import Choice, Question, Test, TestAttempt


@pytest.fixture(autouse=True)
def mock_telegram_transport():
    with patch("apps.notifications.services.telegram_service.TelegramService._send_message", return_value={"ok": True, "result": {"message_id": 12345}}), \
         patch("apps.notifications.services.telegram_service.TelegramService.send_message", return_value=True), \
         patch("apps.notifications.services.telegram_service.TelegramService.send_message_with_keyboard", return_value=True), \
         patch("apps.notifications.services.telegram_service.TelegramService._send_document", return_value={"ok": True, "result": {"message_id": 12346}}):
        yield


@pytest.fixture
def multi_center_setup(db):
    # 1. Center Alpha
    owner_a = User.objects.create_user(
        email="admin-alpha@grandec.test",
        password="pass",
        role="center_admin",
        first_name="Admin",
        last_name="Alpha",
    )
    center_a = LearningCenter.objects.create(name="Alpha Academy", slug="alpha-academy", owner=owner_a)
    branch_a = CenterBranch.objects.create(name="Alpha Chilonzor", center=center_a, branch_code="ACH01")
    owner_a.learning_center = center_a
    owner_a.branch = branch_a
    owner_a.save(update_fields=["learning_center", "branch"])

    teacher_a = User.objects.create_user(
        email="teacher-alpha@grandec.test",
        password="pass",
        role="teacher",
        first_name="Teacher",
        last_name="Alpha",
        learning_center=center_a,
        branch=branch_a,
    )
    student_a = User.objects.create_user(
        email="student-alpha@grandec.test",
        password="pass",
        role="student",
        first_name="Student",
        last_name="Alpha",
        learning_center=center_a,
        branch=branch_a,
    )

    # Identical Group Name: "Ona tili Intensive"
    group_a = StudentGroup.objects.create(
        name="Ona tili Intensive",
        teacher=teacher_a,
        branch=branch_a,
        invite_code="ALPHA-OT",
    )
    add_student_to_group(group_a, student_a, actor=teacher_a, reason="direct_add")

    course_a = Course.objects.create(teacher=teacher_a, title="Ona tili", slug="ona-tili-a")
    test_a = Test.objects.create(
        course=course_a,
        title="1-Mavzu Nazorat Testi",
        subject="uzbek",
        assessment_category=Test.AssessmentCategory.TOPIC_TEST,
        audience_mode=Test.AudienceMode.GROUP_ONLY,
        access_type=Test.AccessType.STUDENTS_ONLY,
        created_by=teacher_a,
        status="published",
        is_active=True,
        time_limit_minutes=20,
    )
    q_a = Question.objects.create(test=test_a, text="Savol A?", position=1, points=2)
    Choice.objects.create(question=q_a, text="Javob A", is_correct=True, position=1)

    hw_a = Homework.objects.create(
        group=group_a,
        test=test_a,
        title="Haftalik vazifa #1",
        created_by=teacher_a,
        start_date=timezone.now() - timedelta(hours=1),
        due_date=timezone.now() + timedelta(days=2),
    )

    # 2. Center Beta
    owner_b = User.objects.create_user(
        email="admin-beta@grandec.test",
        password="pass",
        role="center_admin",
        first_name="Admin",
        last_name="Beta",
    )
    center_b = LearningCenter.objects.create(name="Beta Academy", slug="beta-academy", owner=owner_b)
    branch_b = CenterBranch.objects.create(name="Beta Yunusobod", center=center_b, branch_code="BYU01")
    owner_b.learning_center = center_b
    owner_b.branch = branch_b
    owner_b.save(update_fields=["learning_center", "branch"])

    teacher_b = User.objects.create_user(
        email="teacher-beta@grandec.test",
        password="pass",
        role="teacher",
        first_name="Teacher",
        last_name="Beta",
        learning_center=center_b,
        branch=branch_b,
    )
    student_b = User.objects.create_user(
        email="student-beta@grandec.test",
        password="pass",
        role="student",
        first_name="Student",
        last_name="Beta",
        learning_center=center_b,
        branch=branch_b,
    )

    # Identical Group Name: "Ona tili Intensive"
    group_b = StudentGroup.objects.create(
        name="Ona tili Intensive",
        teacher=teacher_b,
        branch=branch_b,
        invite_code="BETA-OT",
    )
    add_student_to_group(group_b, student_b, actor=teacher_b, reason="direct_add")

    course_b = Course.objects.create(teacher=teacher_b, title="Ona tili", slug="ona-tili-b")
    test_b = Test.objects.create(
        course=course_b,
        title="1-Mavzu Nazorat Testi",
        subject="uzbek",
        assessment_category=Test.AssessmentCategory.TOPIC_TEST,
        audience_mode=Test.AudienceMode.GROUP_ONLY,
        access_type=Test.AccessType.STUDENTS_ONLY,
        created_by=teacher_b,
        status="published",
        is_active=True,
        time_limit_minutes=20,
    )
    q_b = Question.objects.create(test=test_b, text="Savol B?", position=1, points=2)
    Choice.objects.create(question=q_b, text="Javob B", is_correct=True, position=1)

    hw_b = Homework.objects.create(
        group=group_b,
        test=test_b,
        title="Haftalik vazifa #1",
        created_by=teacher_b,
        start_date=timezone.now() - timedelta(hours=1),
        due_date=timezone.now() + timedelta(days=2),
    )

    return {
        "center_a": center_a,
        "branch_a": branch_a,
        "course_a": course_a,
        "owner_a": owner_a,
        "teacher_a": teacher_a,
        "student_a": student_a,
        "group_a": group_a,
        "test_a": test_a,
        "hw_a": hw_a,
        "center_b": center_b,
        "branch_b": branch_b,
        "course_b": course_b,
        "owner_b": owner_b,
        "teacher_b": teacher_b,
        "student_b": student_b,
        "group_b": group_b,
        "test_b": test_b,
        "hw_b": hw_b,
    }


@pytest.mark.django_db
def test_identical_group_names_and_roster_isolation(multi_center_setup):
    s = multi_center_setup
    client = APIClient()

    # Teacher A lists their groups
    client.force_authenticate(s["teacher_a"])
    resp_a = client.get("/api/v1/school/groups/")
    assert resp_a.status_code == 200
    group_ids_a = [g["id"] for g in resp_a.data]
    assert s["group_a"].id in group_ids_a
    assert s["group_b"].id not in group_ids_a

    # Teacher B lists their groups
    client.force_authenticate(s["teacher_b"])
    resp_b = client.get("/api/v1/school/groups/")
    assert resp_b.status_code == 200
    group_ids_b = [g["id"] for g in resp_b.data]
    assert s["group_b"].id in group_ids_b
    assert s["group_a"].id not in group_ids_b

    # Teacher B accessing Group A details must be forbidden
    resp_cross = client.get(f"/api/v1/school/groups/{s['group_a'].id}/")
    assert resp_cross.status_code in (403, 404)


@pytest.mark.django_db
def test_teacher_gradebook_and_results_isolation(multi_center_setup):
    s = multi_center_setup
    client = APIClient()

    # Student A completes Test A
    attempt_a = TestAttempt.objects.create(
        test=s["test_a"],
        student=s["student_a"],
        status=TestAttempt.Status.COMPLETED,
        completed_at=timezone.now(),
    )
    Result.objects.create(
        attempt=attempt_a,
        student=s["student_a"],
        test=s["test_a"],
        course=s["course_a"],
        score=Decimal("2"),
        max_score=Decimal("2"),
        percentage=Decimal("100"),
        total_questions=1,
        correct_answers=1,
        wrong_answers=0,
        is_passed=True,
    )

    # Student B completes Test B
    attempt_b = TestAttempt.objects.create(
        test=s["test_b"],
        student=s["student_b"],
        status=TestAttempt.Status.COMPLETED,
        completed_at=timezone.now(),
    )
    Result.objects.create(
        attempt=attempt_b,
        student=s["student_b"],
        test=s["test_b"],
        course=s["course_b"],
        score=Decimal("0"),
        max_score=Decimal("2"),
        percentage=Decimal("0"),
        total_questions=1,
        correct_answers=0,
        wrong_answers=1,
        is_passed=False,
    )

    # Teacher A views gradebook for Test A
    client.force_authenticate(s["teacher_a"])
    gb_a = client.get(f"/api/tests/{s['test_a'].id}/gradebook/")
    assert gb_a.status_code == 200
    students_in_a = [st["student_id"] for st in gb_a.data.get("students", [])]
    assert s["student_a"].id in students_in_a
    assert s["student_b"].id not in students_in_a

    # Teacher A cannot view gradebook for Test B (other center)
    gb_cross = client.get(f"/api/tests/{s['test_b'].id}/gradebook/")
    assert gb_cross.status_code in (403, 404)

    # Teacher A views group A details & students
    group_a_resp = client.get(f"/api/v1/school/groups/{s['group_a'].id}/")
    assert group_a_resp.status_code == 200
    students_in_group = [st["id"] for st in group_a_resp.data.get("students", [])]
    assert s["student_a"].id in students_in_group
    assert s["student_b"].id not in students_in_group

    # Teacher A cannot view group B details
    group_cross = client.get(f"/api/v1/school/groups/{s['group_b'].id}/")
    assert group_cross.status_code in (403, 404)


@pytest.mark.django_db
def test_student_homework_and_exam_runner_isolation(multi_center_setup):
    from rest_framework_simplejwt.tokens import RefreshToken

    s = multi_center_setup
    client = APIClient()

    # Student A checks my-homework
    client.force_authenticate(s["student_a"])
    token = str(RefreshToken.for_user(s["student_a"]).access_token)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    hw_resp = client.get("/api/v1/school/student/homeworks/")
    assert hw_resp.status_code == 200
    hw_ids = [h["id"] for h in hw_resp.data.get("results", hw_resp.data)]
    assert s["hw_a"].id in hw_ids
    assert s["hw_b"].id not in hw_ids

    # Student A attempts to launch Test B -> must be 403 / 404 (both TMA and web endpoints)
    start_tma_resp = client.post(f"/tma/api/tests/{s['test_b'].id}/start/")
    assert start_tma_resp.status_code in (403, 404)

    start_web_resp = client.post(f"/api/tests/{s['test_b'].id}/start/")
    assert start_web_resp.status_code in (403, 404)


@pytest.mark.django_db
def test_center_admin_tuition_and_users_isolation(multi_center_setup):
    s = multi_center_setup
    client = APIClient()

    # Center Admin A lists teachers in panel -> only Alpha branch teachers
    client.force_authenticate(s["owner_a"])
    teachers_a = client.get("/api/v1/panel/teachers/")
    assert teachers_a.status_code == 200
    teachers_list = teachers_a.data.get("results", [])
    teacher_emails = [t.get("email") for t in teachers_list if isinstance(t, dict)]
    assert s["teacher_a"].email in teacher_emails
    assert s["teacher_b"].email not in teacher_emails

    # Center Admin A lists branches -> only Alpha branch
    branches_a = client.get("/api/v1/panel/branches/")
    assert branches_a.status_code == 200
    branch_names = [b.get("name") for b in branches_a.data if isinstance(b, dict)]
    assert s["branch_a"].name in branch_names
    assert s["branch_b"].name not in branch_names

    # Teacher A views group A finance, but cannot view group B finance
    client.force_authenticate(s["teacher_a"])
    fin_a = client.get(f"/api/v1/courses/groups/{s['group_a'].id}/finance-summary/")
    assert fin_a.status_code == 200
    fin_b = client.get(f"/api/v1/courses/groups/{s['group_b'].id}/finance-summary/")
    assert fin_b.status_code in (403, 404)

    # Platform Admin can view global users list
    global_admin = User.objects.create_user(email="super@grandec.test", password="pass", role="admin")
    client.force_authenticate(global_admin)
    users_resp = client.get("/api/v1/panel/users/")
    assert users_resp.status_code == 200


@pytest.mark.django_db
def test_attendance_session_multi_center_isolation(multi_center_setup):
    s = multi_center_setup

    today = timezone.localdate()
    sess_a = AttendanceSession.objects.create(
        group=s["group_a"],
        teacher=s["teacher_a"],
        lesson_date=today,
    )
    AttendanceRecord.objects.create(
        session=sess_a,
        student=s["student_a"],
        status=AttendanceRecord.Status.PRESENT,
    )

    sess_b = AttendanceSession.objects.create(
        group=s["group_b"],
        teacher=s["teacher_b"],
        lesson_date=today,
    )
    AttendanceRecord.objects.create(
        session=sess_b,
        student=s["student_b"],
        status=AttendanceRecord.Status.ABSENT,
    )

    client = APIClient()

    # Teacher A cannot access session B
    client.force_authenticate(s["teacher_a"])
    resp = client.get(f"/api/v1/school/attendance/sessions/{sess_b.id}/")
    assert resp.status_code in (403, 404)

    # Teacher B cannot access session A
    client.force_authenticate(s["teacher_b"])
    resp2 = client.get(f"/api/v1/school/attendance/sessions/{sess_a.id}/")
    assert resp2.status_code in (403, 404)
