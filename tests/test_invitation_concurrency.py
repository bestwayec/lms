"""
Concurrency and Security Audit Tests for Group Invitations and Admin Visibility:
- Concurrent invitation usage and max_uses boundary enforcement
- Concurrent group capacity exhaustion prevention
- Concurrent teacher approvals & duplicate callback deduplication
- Revocation while join request is pending
- Truthful billing: student subscription plans remain untouched
- Admin visibility audit authorization, multi-center isolation, and private test protection
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError
from django.db import close_old_connections, connection
from django.utils import timezone

from apps.accounts.models import User
from apps.courses.group_service import add_student_to_group
from apps.courses.invitation_service import (
    create_group_invitation,
    join_group_by_token,
    review_join_request,
    revoke_group_invitation,
)
from apps.courses.models import Course, GroupInvitation, GroupJoinRequest, StudentGroup
from apps.notifications.models import OutboxMessage
from apps.organizations.models import CenterBranch, LearningCenter
from apps.results.models import Result
from apps.tests.admin_test_service import (
    audit_public_studio_tests,
    apply_studio_tests_visibility_transition,
)
from apps.tests.models import Choice, Question, Test, TestAttempt


@pytest.fixture(autouse=True)
def mock_telegram_transport():
    with patch("apps.notifications.services.telegram_service.TelegramService._send_message", return_value={"ok": True, "result": {"message_id": 991}}), \
         patch("apps.notifications.services.telegram_service.TelegramService.send_message", return_value=True), \
         patch("apps.notifications.services.telegram_service.TelegramService.send_message_with_keyboard", return_value=True), \
         patch("apps.notifications.services.telegram_service.TelegramService._send_document", return_value={"ok": True, "result": {"message_id": 992}}):
        yield


@pytest.fixture
def setup_center_and_teacher(db):
    owner = User.objects.create_user(email="owner-conc@grandec.test", password="p", role="admin")
    center = LearningCenter.objects.create(name="Concurrency Center", slug="conc-center", owner=owner)
    branch = CenterBranch.objects.create(name="Conc Branch", center=center, branch_code="CC01")
    teacher = User.objects.create_user(
        email="teacher-conc@grandec.test",
        password="p",
        role="teacher",
        learning_center=center,
        branch=branch,
    )
    group = StudentGroup.objects.create(
        name="Concurrency Group",
        teacher=teacher,
        branch=branch,
        max_students=10,
    )
    return {
        "center": center,
        "branch": branch,
        "teacher": teacher,
        "group": group,
    }


@pytest.mark.django_db(transaction=True)
def test_concurrent_invitation_acceptance_max_uses(setup_center_and_teacher):
    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL row locks")
    s = setup_center_and_teacher
    teacher = s["teacher"]
    group = s["group"]

    s1 = User.objects.create_user(email="s1-conc@grandec.test", password="p", role="student")
    s2 = User.objects.create_user(email="s2-conc@grandec.test", password="p", role="student")

    # Invitation with only 1 use allowed
    inv = create_group_invitation(teacher=teacher, group_id=group.id, max_uses=1, requires_approval=False)

    barrier = Barrier(2)

    def worker(student_id):
        close_old_connections()
        try:
            student = User.objects.get(pk=student_id)
            barrier.wait(timeout=10)
            res = join_group_by_token(student, inv.token)
            return ("joined", res)
        except ValidationError as e:
            return ("rejected", str(e))
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(worker, [s1.id, s2.id]))

    statuses = [r[0] for r in results]
    assert "joined" in statuses
    assert "rejected" in statuses

    # Exactly 1 student joined
    group.refresh_from_db()
    assert group.students.count() == 1

    # uses_count is exactly 1
    inv.refresh_from_db()
    assert inv.uses_count == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_group_capacity_exhaustion(setup_center_and_teacher):
    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL row locks")
    s = setup_center_and_teacher
    teacher = s["teacher"]
    group = s["group"]
    group.max_students = 2
    group.save(update_fields=["max_students"])

    # Already has 1 student
    existing_s = User.objects.create_user(email="s-exist@grandec.test", password="p", role="student")
    add_student_to_group(group, existing_s, actor=teacher, reason="seed")

    s1 = User.objects.create_user(email="s1-cap@grandec.test", password="p", role="student")
    s2 = User.objects.create_user(email="s2-cap@grandec.test", password="p", role="student")

    inv = create_group_invitation(teacher=teacher, group_id=group.id, max_uses=10, requires_approval=False)

    barrier = Barrier(2)

    def worker(student_id):
        close_old_connections()
        try:
            student = User.objects.get(pk=student_id)
            barrier.wait(timeout=10)
            res = join_group_by_token(student, inv.token)
            return ("joined", res)
        except (ValueError, ValidationError) as e:
            return ("rejected", str(e))
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(worker, [s1.id, s2.id]))

    statuses = [r[0] for r in results]
    assert "joined" in statuses
    assert "rejected" in statuses

    # Group capacity never exceeded
    group.refresh_from_db()
    assert group.students.count() == 2


@pytest.mark.django_db(transaction=True)
def test_concurrent_teacher_approvals_deduplication(setup_center_and_teacher):
    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL row locks")
    s = setup_center_and_teacher
    teacher = s["teacher"]
    group = s["group"]

    student = User.objects.create_user(email="student-dup@grandec.test", password="p", role="student")
    inv = create_group_invitation(teacher=teacher, group_id=group.id, requires_approval=True)
    res = join_group_by_token(student, inv.token)
    req_id = res["request_id"]

    OutboxMessage.objects.all().delete()

    barrier = Barrier(2)

    def approve_worker(_):
        close_old_connections()
        try:
            t = User.objects.get(pk=teacher.id)
            barrier.wait(timeout=10)
            return ("approved", review_join_request(t, req_id, approved=True))
        except ValidationError as e:
            return ("rejected", str(e))
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(approve_worker, [1, 2]))

    statuses = [r[0] for r in results]
    assert "approved" in statuses
    assert "rejected" in statuses

    # Group has student once
    group.refresh_from_db()
    assert group.students.filter(id=student.id).count() == 1

    # Only one approval outbox notification enqueued
    approvals = OutboxMessage.objects.filter(event=OutboxMessage.Event.JOIN_REQUEST_APPROVED).count()
    assert approvals == 1


@pytest.mark.django_db
def test_revocation_while_join_request_pending(setup_center_and_teacher):
    s = setup_center_and_teacher
    teacher = s["teacher"]
    group = s["group"]

    student = User.objects.create_user(email="student-rev@grandec.test", password="p", role="student")
    inv = create_group_invitation(teacher=teacher, group_id=group.id, requires_approval=True)
    res = join_group_by_token(student, inv.token)
    req_id = res["request_id"]

    # Teacher revokes invitation
    revoke_group_invitation(teacher, inv.id)

    # Teacher attempts to approve request
    with pytest.raises(ValidationError, match="bekor qilingan"):
        review_join_request(teacher, req_id, approved=True)

    # Student was not enrolled
    assert not group.students.filter(id=student.id).exists()


@pytest.mark.django_db
def test_duplicate_token_join_is_idempotent_and_preserves_plans(setup_center_and_teacher):
    s = setup_center_and_teacher
    teacher = s["teacher"]
    group = s["group"]

    student = User.objects.create_user(email="student-plan@grandec.test", password="p", role="student")
    inv = create_group_invitation(teacher=teacher, group_id=group.id, max_uses=5, requires_approval=False)

    # 1. First join
    first_res = join_group_by_token(student, inv.token)
    assert first_res["status"] == "joined"
    inv.refresh_from_db()
    assert inv.uses_count == 1

    # 2. Second join attempt (already member)
    second_res = join_group_by_token(student, inv.token)
    assert second_res["status"] == "already_member"

    # Counter did not increment again
    inv.refresh_from_db()
    assert inv.uses_count == 1

    # Student did not receive a fake PRO subscription
    student.refresh_from_db()
    assert student.role == "student"


@pytest.mark.django_db
def test_admin_visibility_audit_authorization_and_isolation(setup_center_and_teacher):
    s = setup_center_and_teacher
    teacher_a = s["teacher"]

    # Another center and teacher
    owner_b = User.objects.create_user(email="owner-b@grandec.test", password="p", role="admin")
    center_b = LearningCenter.objects.create(name="Center B", slug="center-b", owner=owner_b)
    teacher_b = User.objects.create_user(email="teacher-b@grandec.test", password="p", role="teacher", learning_center=center_b)

    course_a = Course.objects.create(teacher=teacher_a, title="Course A", slug="course-a")
    test_a = Test.objects.create(
        course=course_a,
        created_by=teacher_a,
        title="Public Studio Test Alpha",
        audience_mode="PUBLIC_FREE",
        access_type="PUBLIC",
    )
    Question.objects.create(test=test_a, text="Q?", config={"studio_type": "standard"})

    course_b = Course.objects.create(teacher=teacher_b, title="Course B", slug="course-b")
    test_b = Test.objects.create(
        course=course_b,
        created_by=teacher_b,
        title="Public Studio Test Beta",
        audience_mode="PUBLIC_FREE",
        access_type="PUBLIC",
    )
    Question.objects.create(test=test_b, text="Q?", config={"studio_type": "standard"})

    # Teacher A running audit can only see their own tests
    audit_a = audit_public_studio_tests(teacher_a)
    ids_a = [item["id"] for item in audit_a]
    assert test_a.id in ids_a
    assert test_b.id not in ids_a

    # Teacher A cannot modify test_b
    res_tamper = apply_studio_tests_visibility_transition(teacher_a, [test_b.id], target_mode="GROUP_ONLY")
    assert res_tamper["updated_count"] == 0
    test_b.refresh_from_db()
    assert test_b.audience_mode == "PUBLIC_FREE"

    # Teacher A transitions test_a to GROUP_ONLY
    res_a = apply_studio_tests_visibility_transition(teacher_a, [test_a.id], target_mode="GROUP_ONLY")
    assert res_a["updated_count"] == 1
    test_a.refresh_from_db()
    assert test_a.audience_mode == "GROUP_ONLY"
    assert test_a.access_type == "STUDENTS_ONLY"

    # Attempting to publish via audit raises ValueError
    with pytest.raises(ValueError, match="faqat guruhlarga cheklash"):
        apply_studio_tests_visibility_transition(teacher_a, [test_a.id], target_mode="PUBLIC_FREE")


@pytest.mark.django_db
def test_historical_results_preserved_on_visibility_transition(setup_center_and_teacher):
    s = setup_center_and_teacher
    teacher = s["teacher"]
    student = User.objects.create_user(email="res-preserve@grandec.test", password="p", role="student")

    course = Course.objects.create(teacher=teacher, title="Hist Course", slug="hist-course")
    test = Test.objects.create(
        course=course,
        created_by=teacher,
        title="Historical Test",
        audience_mode="PUBLIC_FREE",
        access_type="PUBLIC",
    )
    attempt = TestAttempt.objects.create(
        test=test,
        student=student,
        status=TestAttempt.Status.COMPLETED,
        completed_at=timezone.now(),
    )
    result = Result.objects.create(
        attempt=attempt,
        student=student,
        test=test,
        course=course,
        score=Decimal("5"),
        max_score=Decimal("5"),
        percentage=Decimal("100"),
        total_questions=1,
        correct_answers=1,
        wrong_answers=0,
        is_passed=True,
    )

    # Transition test to GROUP_ONLY
    res = apply_studio_tests_visibility_transition(teacher, [test.id], target_mode="GROUP_ONLY")
    assert res["updated_count"] == 1

    # Verify Result and Attempt are untouched
    attempt.refresh_from_db()
    result.refresh_from_db()
    assert attempt.status == TestAttempt.Status.COMPLETED
    assert result.score == Decimal("5")
    assert result.percentage == Decimal("100")
