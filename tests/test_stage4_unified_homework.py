"""
Comprehensive Acceptance Tests for Stage 4 — Unified Homework Engine:
- Fix A: Unsafe deletion replaced by non-destructive cancellation (preserves submissions & grades)
- Fix B: Test authorization prevents attaching DRAFT or other teachers' private tests
- Fix C: Atomic transactions prevent orphan assignments and partial states
- Fix D: Idempotency keys prevent duplicate assignments
- Step 2: Unified assignment architecture (Tests, Essays, Vocabulary, Lessons, Custom)
- Step 3: Student Homework API (My homework, Detail, Start/Resume, Autosave, Submit, Result)
- Step 6: Authoritative derived statuses and official grading integration (Score 0 is GRADED, not pending)
"""

from __future__ import annotations

from datetime import timedelta
import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.courses.homework_service import (
    cancel_teacher_homework,
    create_unified_homework,
    derive_submission_status,
    get_student_homework_detail,
    get_student_homework_list,
    save_student_homework_progress,
    start_student_homework,
    submit_student_homework,
)
from apps.courses.models import Course, Homework, HomeworkSubmission, StudentGroup
from apps.essays.models import EssaySubmission, EssayTopic
from apps.results.models import Result
from apps.tests.models import Choice, Question, Test, TestAttempt


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def teacher_a(db):
    return User.objects.create_user(
        email="teacher_a_hw@example.com",
        password="pass",
        role="teacher",
        first_name="Teacher",
        last_name="Alpha",
    )


@pytest.fixture
def teacher_b(db):
    return User.objects.create_user(
        email="teacher_b_hw@example.com",
        password="pass",
        role="teacher",
        first_name="Teacher",
        last_name="Beta",
    )


@pytest.fixture
def student_one(db):
    return User.objects.create_user(
        email="student_1_hw@example.com",
        password="pass",
        role="student",
        first_name="Student",
        last_name="One",
    )


@pytest.fixture
def student_two(db):
    return User.objects.create_user(
        email="student_2_hw@example.com",
        password="pass",
        role="student",
        first_name="Student",
        last_name="Two",
    )


@pytest.fixture
def group_a(db, teacher_a, student_one):
    g = StudentGroup.objects.create(
        name="Group Alpha",
        teacher=teacher_a,
    )
    g.students.add(student_one)
    return g


@pytest.fixture
def group_b(db, teacher_b, student_two):
    g = StudentGroup.objects.create(
        name="Group Beta",
        teacher=teacher_b,
    )
    g.students.add(student_two)
    return g


@pytest.fixture
def course_a(db, teacher_a):
    return Course.objects.create(
        teacher=teacher_a,
        title="Course Alpha",
        slug="course-alpha-hw",
    )


@pytest.fixture
def course_b(db, teacher_b):
    return Course.objects.create(
        teacher=teacher_b,
        title="Course Beta",
        slug="course-beta-hw",
    )


@pytest.fixture
def published_test_teacher_a(db, teacher_a, course_a):
    t = Test.objects.create(
        course=course_a,
        title="Mathematics Quiz 1",
        created_by=teacher_a,
        status=Test.Status.PUBLISHED,
        access_type=Test.AccessType.STUDENTS_ONLY,
        subject="mathematics",
        time_limit_minutes=30,
    )
    q = Question.objects.create(
        test=t,
        position=1,
        text="2 + 2 = ?",
        points=1,
    )
    Choice.objects.create(question=q, text="4", is_correct=True, position=1)
    Choice.objects.create(question=q, text="5", is_correct=False, position=2)
    return t


@pytest.fixture
def draft_test_teacher_a(db, teacher_a, course_a):
    return Test.objects.create(
        course=course_a,
        title="Unpublished Physics Draft",
        created_by=teacher_a,
        status=Test.Status.DRAFT,
        subject="physics",
    )


# ---------------------------------------------------------------------------
# STEP 1: Integrity Fixes
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_safe_deletion_preserves_submissions_and_grades(teacher_a, student_one, group_a, published_test_teacher_a):
    """
    Test Fix A: Deleting/cancelling a homework must NEVER delete historical submissions or grades.
    Transitions status to CANCELLED and marks audit metadata.
    """
    due_date = timezone.now() + timedelta(days=2)
    hw, _ = create_unified_homework(
        teacher_a,
        group_id=group_a.id,
        title="Math Homework 1",
        due_date=due_date,
        test_id=published_test_teacher_a.id,
    )

    # Student starts and completes
    start_student_homework(student_one, hw.id)
    sub = HomeworkSubmission.objects.get(homework=hw, student=student_one)
    sub.is_completed = True
    sub.score = 10.0
    sub.max_score = 10.0
    sub.percentage = 100.0
    sub.score_display = "10/10"
    sub.status = HomeworkSubmission.Status.GRADED
    sub.save()

    # Teacher cancels homework
    cancelled_hw = cancel_teacher_homework(teacher_a, hw.id)

    assert cancelled_hw.status == Homework.Status.CANCELLED
    assert cancelled_hw.cancelled_by == teacher_a
    assert cancelled_hw.cancelled_at is not None

    # CRITICAL: Verify records are STILL in database with exact grades intact
    assert Homework.objects.filter(id=hw.id).exists()
    sub_reload = HomeworkSubmission.objects.get(id=sub.id)
    assert sub_reload.is_completed is True
    assert sub_reload.score == 10.0
    assert sub_reload.percentage == 100.0


@pytest.mark.django_db
def test_test_authorization_rejects_draft_test(teacher_a, group_a, draft_test_teacher_a):
    """
    Test Fix B: Homework creation must reject attaching DRAFT or unpublished tests.
    """
    due_date = timezone.now() + timedelta(days=2)
    with pytest.raises(ValueError, match="Faqat e'lon qilingan"):
        create_unified_homework(
            teacher_a,
            group_id=group_a.id,
            title="Attempting Draft",
            due_date=due_date,
            test_id=draft_test_teacher_a.id,
        )


@pytest.mark.django_db
def test_test_authorization_rejects_other_teachers_private_test(teacher_b, group_b, published_test_teacher_a):
    """
    Test Fix B: Teacher B cannot attach Teacher A's private test.
    """
    due_date = timezone.now() + timedelta(days=2)
    with pytest.raises(PermissionError, match="Boshqa o'qituvchining yopiq testini"):
        create_unified_homework(
            teacher_b,
            group_id=group_b.id,
            title="Attempting Private Test",
            due_date=due_date,
            test_id=published_test_teacher_a.id,
        )


@pytest.mark.django_db
def test_official_test_allowed_for_any_teacher(teacher_b, group_b, course_b):
    """
    Test Fix B: Official published tests (is_official=True) are globally sharable.
    """
    official_test = Test.objects.create(
        course=course_b,
        title="CEFR Official B2 Practice",
        status=Test.Status.PUBLISHED,
        access_type="PUBLIC",
    )
    due_date = timezone.now() + timedelta(days=2)
    hw, created = create_unified_homework(
        teacher_b,
        group_id=group_b.id,
        title="CEFR Mock",
        due_date=due_date,
        test_id=official_test.id,
    )
    assert created is True
    assert hw.test == official_test


@pytest.mark.django_db
def test_multi_group_does_not_hijack_existing_assigned_group(teacher_a, group_a, published_test_teacher_a):
    """
    Test Fix B: Test.assigned_group should not be hijacked if already populated.
    """
    published_test_teacher_a.assigned_group = group_a
    published_test_teacher_a.save()

    # Create another group for teacher A
    group_a2 = StudentGroup.objects.create(name="Group Alpha 2", teacher=teacher_a)

    due_date = timezone.now() + timedelta(days=2)
    hw, _ = create_unified_homework(
        teacher_a,
        group_id=group_a2.id,
        title="Shared Test Assignment",
        due_date=due_date,
        test_id=published_test_teacher_a.id,
    )
    assert hw.group == group_a2
    published_test_teacher_a.refresh_from_db()
    # Still points to original group_a, not overwritten!
    assert published_test_teacher_a.assigned_group_id == group_a.id


@pytest.mark.django_db
def test_idempotent_homework_creation(teacher_a, group_a, published_test_teacher_a):
    """
    Test Fix D: Duplicate requests with same idempotency_key return existing homework.
    """
    due_date = timezone.now() + timedelta(days=2)
    key = "idem_key_unique_101"

    hw1, created1 = create_unified_homework(
        teacher_a,
        group_id=group_a.id,
        title="Idempotent Test",
        due_date=due_date,
        test_id=published_test_teacher_a.id,
        idempotency_key=key,
    )
    assert created1 is True

    hw2, created2 = create_unified_homework(
        teacher_a,
        group_id=group_a.id,
        title="Idempotent Test",
        due_date=due_date,
        test_id=published_test_teacher_a.id,
        idempotency_key=key,
    )
    assert created2 is False
    assert hw1.id == hw2.id
    assert Homework.objects.filter(idempotency_key=key).count() == 1


# ---------------------------------------------------------------------------
# STEP 2 & 3: Unified Content & Student API
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_individual_student_assignment_and_privacy(teacher_a, student_one, student_two, group_a):
    """
    Assigning homework to an individual student only exposes it to that student.
    """
    due_date = timezone.now() + timedelta(days=3)
    hw, _ = create_unified_homework(
        teacher_a,
        student_id=student_one.id,
        title="Personal remedial task",
        due_date=due_date,
        description="Solve 5 extra algebra exercises.",
    )
    assert hw.student == student_one
    assert hw.group is None

    # Student 1 sees it
    list1 = get_student_homework_list(student_one)
    assert any(h["id"] == hw.id for h in list1)

    # Student 2 does NOT see it
    list2 = get_student_homework_list(student_two)
    assert not any(h["id"] == hw.id for h in list2)

    # Student 2 accessing detail is rejected
    with pytest.raises(PermissionError):
        get_student_homework_detail(student_two, hw.id)


@pytest.mark.django_db
def test_score_zero_is_graded_not_pending(teacher_a, student_one, group_a):
    """
    STEP 3 / 6: A score of 0.0 is a valid final score (GRADED), NOT pending or awaiting review.
    """
    due_date = timezone.now() + timedelta(days=2)
    hw, _ = create_unified_homework(
        teacher_a,
        group_id=group_a.id,
        title="Vocabulary Quiz",
        due_date=due_date,
    )

    sub, _ = HomeworkSubmission.objects.get_or_create(
        homework=hw,
        student=student_one,
        defaults={
            "is_completed": True,
            "score": 0.0,
            "max_score": 10.0,
            "percentage": 0.0,
            "status": HomeworkSubmission.Status.GRADED,
        },
    )

    eff_status, eff_score, label = derive_submission_status(hw, sub)
    assert eff_status == HomeworkSubmission.Status.GRADED
    assert eff_score == 0.0


@pytest.mark.django_db
def test_overdue_status_derived_accurately(teacher_a, student_one, group_a):
    """
    Past due date without submission resolves to OVERDUE.
    """
    past_due = timezone.now() - timedelta(days=1)
    hw = Homework.objects.create(
        group=group_a,
        title="Late task",
        due_date=past_due,
        created_by=teacher_a,
    )
    eff_status, _, label = derive_submission_status(hw, None)
    assert eff_status == HomeworkSubmission.Status.OVERDUE
    assert "Muddati o'tgan" in label


@pytest.mark.django_db
def test_student_homework_api_lifecycle(api, teacher_a, student_one, group_a, published_test_teacher_a):
    """
    Full API Integration Test:
    1. Teacher creates homework via POST /api/v1/school/teacher/homeworks/
    2. Student lists homework via GET /api/v1/school/student/homeworks/
    3. Student starts homework via POST /api/v1/school/student/homeworks/<id>/start/
    4. Student saves progress via POST /api/v1/school/student/homeworks/<id>/save/
    5. Student submits via POST /api/v1/school/student/homeworks/<id>/submit/
    6. Student views result via GET /api/v1/school/student/homeworks/<id>/result/
    """
    # 1. Teacher creates homework
    api.force_authenticate(user=teacher_a)
    due_date_str = (timezone.now() + timedelta(days=3)).isoformat()
    create_resp = api.post(
        "/api/v1/school/teacher/homeworks/",
        {
            "group_id": group_a.id,
            "title": "Algebra Unit 1 Test",
            "due_date": due_date_str,
            "test_id": published_test_teacher_a.id,
            "time_limit": 45,
            "max_attempts": 2,
        },
        format="json",
    )
    assert create_resp.status_code == 201
    hw_id = create_resp.data["id"]

    # 2. Student lists homework
    api.force_authenticate(user=student_one)
    list_resp = api.get("/api/v1/school/student/homeworks/")
    assert list_resp.status_code == 200
    assert any(h["id"] == hw_id for h in list_resp.data["results"])

    # 3. Student starts homework
    start_resp = api.post(f"/api/v1/school/student/homeworks/{hw_id}/start/")
    assert start_resp.status_code == 200
    assert start_resp.data["ok"] is True
    assert start_resp.data["attempt_id"] is not None

    # 4. Student autosaves draft
    save_resp = api.post(
        f"/api/v1/school/student/homeworks/{hw_id}/save/",
        {"answers": {"1": "B"}},
        format="json",
    )
    assert save_resp.status_code == 200
    assert save_resp.data["ok"] is True

    # 5. Student submits
    sub_resp = api.post(
        f"/api/v1/school/student/homeworks/{hw_id}/submit/",
        {"answers": {"1": "B"}},
        format="json",
    )
    assert sub_resp.status_code == 200
    assert sub_resp.data["is_completed"] is True
    assert sub_resp.data["status"] == "graded"

    # 6. Student views result
    res_resp = api.get(f"/api/v1/school/student/homeworks/{hw_id}/result/")
    assert res_resp.status_code == 200
    assert res_resp.data["status"] == "graded"
    assert res_resp.data["percentage"] is not None


@pytest.mark.django_db
def test_teacher_homework_catalog_excludes_draft_tests(api, teacher_a, published_test_teacher_a, draft_test_teacher_a):
    """
    Teacher catalog must strictly return only PUBLISHED tests.
    """
    api.force_authenticate(user=teacher_a)
    resp = api.get("/api/v1/school/teacher/homework-catalog/?content_type=test")
    assert resp.status_code == 200
    tests = resp.data["tests"]
    test_ids = [t["id"] for t in tests]
    assert published_test_teacher_a.id in test_ids
    assert draft_test_teacher_a.id not in test_ids
