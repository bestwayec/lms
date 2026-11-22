"""
Tests for GRANDEC NEXT 6.0:
- Unified Test Access Policy (resolve_test_access, access matrix, classroom entitlement)
- Group Invitations & Direct Enrollment (token, code, expiry, max_uses, revocation, capacity)
- Teacher Classroom Endpoints & Fast Assignment Wizard
- Student Classroom Experience & Truthful Billing State
"""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client
from django.utils import timezone

from apps.courses.group_service import add_student_to_group, remove_student_from_group
from apps.courses.homework_service import create_unified_homework
from apps.courses.invitation_service import (
    create_group_invitation,
    join_group_by_code,
    join_group_by_token,
    list_teacher_pending_requests,
    review_join_request,
    revoke_group_invitation,
    rotate_group_invitation,
)
from apps.courses.models import (
    Course,
    GroupEnrollment,
    GroupInvitation,
    GroupJoinRequest,
    Homework,
    StudentGroup,
    Subject,
)
from apps.organizations.models import LearningCenter
from apps.results.models import Result
from apps.tests.access_policy import resolve_test_access
from apps.tests.models import Choice, Question, Test, TestAttempt
from apps.tests.services import StartAttemptService, TestAccessDeniedError as AccessDeniedError

User = get_user_model()


@pytest.fixture
def center(db):
    owner = User.objects.create_user(email="center-owner6@grandec.test", password="pass", role="admin")
    return LearningCenter.objects.create(name="Grand Test Center", slug="grand-center-6", owner=owner)


@pytest.fixture
def teacher_1(db):
    return User.objects.create_user(
        email="teacher1@grandec.test",
        password="pass",
        role="teacher",
        first_name="Ustoz",
        last_name="Birinchi",
    )


@pytest.fixture
def teacher_2(db):
    return User.objects.create_user(
        email="teacher2@grandec.test",
        password="pass",
        role="teacher",
        first_name="Ustoz",
        last_name="Ikkinchi",
    )


@pytest.fixture
def free_student_1(db):
    return User.objects.create_user(
        email="free1@grandec.test",
        password="pass",
        role="student",
        first_name="Ali",
        last_name="Valiyev",
    )


@pytest.fixture
def free_student_2(db):
    return User.objects.create_user(
        email="free2@grandec.test",
        password="pass",
        role="student",
        first_name="Gani",
        last_name="Salimov",
    )


@pytest.fixture
def pro_student(db):
    u = User.objects.create_user(
        email="pro@grandec.test",
        password="pass",
        role="student",
        first_name="Pro",
        last_name="Talaba",
    )
    from apps.payments.models import SubscriptionPlan, UserSubscription
    plan, _ = SubscriptionPlan.objects.get_or_create(
        plan_type="pro",
        defaults={
            "name": "PRO Test Plan",
            "price_monthly": Decimal("49000.00"),
            "description": "PRO plan description",
        },
    )
    UserSubscription.objects.create(
        user=u,
        plan=plan,
        status=UserSubscription.Status.ACTIVE,
        started_at=timezone.now(),
        expires_at=timezone.now() + timedelta(days=30),
    )
    return u


@pytest.fixture
def course_1(db, teacher_1):
    subject, _ = Subject.objects.get_or_create(
        name="Ona tili",
        slug="ona-tili-c6",
    )
    return Course.objects.create(
        title="Ona Tili 2026",
        slug="ona-tili-2026-c6",
        teacher=teacher_1,
        subject=subject,
    )


@pytest.fixture
def group_1(db, teacher_1):
    return StudentGroup.objects.create(
        name="Ona Tili 10-A",
        invite_code="GR-10A",
        teacher=teacher_1,
        max_students=5,
    )


@pytest.fixture
def test_group_only(db, teacher_1, course_1):
    t = Test.objects.create(
        course=course_1,
        title="Ona Tili Attestatsiya 2026",
        created_by=teacher_1,
        audience_mode="GROUP_ONLY",
        access_type=Test.AccessType.STUDENTS_ONLY,
        status="published",
        is_active=True,
        time_limit_minutes=20,
        max_attempts=2,
    )
    q = Question.objects.create(test=t, text="Savol 1?", position=1)
    Choice.objects.create(question=q, text="Javob A", is_correct=True, position=0)
    return t


@pytest.fixture
def test_group_and_subscribers(db, teacher_1, course_1):
    t = Test.objects.create(
        course=course_1,
        title="Ona Tili BMB Mock #1",
        created_by=teacher_1,
        audience_mode="GROUP_AND_SUBSCRIBERS",
        access_type=Test.AccessType.PRO_ONLY,
        status="published",
        is_active=True,
        time_limit_minutes=30,
    )
    q = Question.objects.create(test=t, text="Savol BMB?", position=1)
    Choice.objects.create(question=q, text="Javob 1", is_correct=True, position=0)
    return t


# ===========================================================================
# 1. Access Matrix & Unified Access Policy Tests
# ===========================================================================
@pytest.mark.django_db(transaction=True)
def test_access_matrix_classroom_vs_subscribers(
    teacher_1, teacher_2, free_student_1, free_student_2, pro_student, group_1, test_group_only, test_group_and_subscribers
):
    # Enclose free_student_1 into group_1
    add_student_to_group(group_1, free_student_1, actor=teacher_1)

    # Assign test_group_only to group_1
    hw, _ = create_unified_homework(
        teacher_1,
        title="Uyga vazifa #1",
        due_date=timezone.now() + timedelta(days=5),
        group_id=group_1.id,
        test_id=test_group_only.id,
        max_attempts=2,
    )

    # 1. FREE student in assigned group: ALLOWED (0 quota, classroom entitlement)
    d1 = resolve_test_access(free_student_1, test_group_only, action="start")
    assert d1.allowed is True
    assert d1.reason_code == "ALLOWED_CLASSROOM_ASSIGNMENT"
    assert d1.is_classroom_entitlement is True
    assert d1.consumes_quota is False

    # 2. FREE student outside assigned group: DENIED (GROUP_ONLY)
    d2 = resolve_test_access(free_student_2, test_group_only, action="start")
    assert d2.allowed is False
    assert d2.reason_code == "DENIED_GROUP_ONLY"
    assert d2.is_paid_catalog is False

    # 3. PRO student outside group, GROUP_ONLY test: DENIED
    d3 = resolve_test_access(pro_student, test_group_only, action="start")
    assert d3.allowed is False
    assert d3.reason_code == "DENIED_GROUP_ONLY"

    # 4. PRO student outside group, GROUP_AND_SUBSCRIBERS test: ALLOWED
    d4 = resolve_test_access(pro_student, test_group_and_subscribers, action="start")
    assert d4.allowed is True
    assert d4.reason_code == "ALLOWED_SUBSCRIBER"
    assert d4.is_classroom_entitlement is False

    # 5. FREE student outside group, GROUP_AND_SUBSCRIBERS test: DENIED_SUBSCRIPTION_REQUIRED
    d5 = resolve_test_access(free_student_2, test_group_and_subscribers, action="start")
    assert d5.allowed is False
    assert d5.reason_code == "DENIED_SUBSCRIPTION_REQUIRED"
    assert d5.is_paid_catalog is True

    # 6. Another teacher accessing private test: DENIED
    d6 = resolve_test_access(teacher_2, test_group_only, action="start")
    assert d6.allowed is False
    assert d6.reason_code == "DENIED_TEACHER_PRIVATE"

    # 7. Cancelled homework assignment: DENIED
    hw.status = Homework.Status.CANCELLED
    hw.save()
    d7 = resolve_test_access(free_student_1, test_group_only, assignment=hw, action="start")
    assert d7.allowed is False
    assert d7.reason_code == "DENIED_CANCELLED"

    # 8. Unpublished test: DENIED
    test_group_only.status = "draft"
    test_group_only.save()
    d8 = resolve_test_access(free_student_1, test_group_only, action="start")
    assert d8.allowed is False
    assert d8.reason_code == "DENIED_UNPUBLISHED"


# ===========================================================================
# 2. StartAttemptService & Quota Exemption for Classroom Attempts
# ===========================================================================
@pytest.mark.django_db(transaction=True)
def test_start_attempt_classroom_quota_exemption(teacher_1, free_student_1, group_1, test_group_only):
    add_student_to_group(group_1, free_student_1, actor=teacher_1)
    create_unified_homework(
        teacher_1,
        title="Classroom Homework",
        due_date=timezone.now() + timedelta(days=3),
        group_id=group_1.id,
        test_id=test_group_only.id,
    )

    # Start attempt as FREE student without PRO plan and without commercial quota
    attempt = StartAttemptService.execute(test_id=test_group_only.id, student=free_student_1)
    assert attempt is not None
    assert attempt.is_classroom_entitlement is True
    assert attempt.access_source == "classroom"
    assert attempt.classroom_group_id == group_1.id

    # Resume attempt: does not charge quota
    resume_decision = resolve_test_access(free_student_1, test_group_only, action="resume")
    assert resume_decision.allowed is True
    assert resume_decision.consumes_quota is False


# ===========================================================================
# 3. Student Removal Preserves Historical Results & Blocks New Attempts
# ===========================================================================
@pytest.mark.django_db(transaction=True)
def test_student_removal_preserves_results_and_blocks_future(teacher_1, free_student_1, group_1, test_group_only):
    add_student_to_group(group_1, free_student_1, actor=teacher_1)
    create_unified_homework(
        teacher_1,
        title="Attestation Homework",
        due_date=timezone.now() + timedelta(days=3),
        group_id=group_1.id,
        test_id=test_group_only.id,
    )

    # Complete an attempt and create result
    att = StartAttemptService.execute(test_id=test_group_only.id, student=free_student_1)
    att.status = TestAttempt.Status.COMPLETED
    att.score = Decimal("10.0")
    att.percentage = Decimal("100.0")
    att.save()

    res = Result.objects.create(
        attempt=att,
        test=test_group_only,
        course=test_group_only.course,
        student=free_student_1,
        total_questions=1,
        correct_answers=1,
        wrong_answers=0,
        score=Decimal("10.0"),
        max_score=Decimal("10.0"),
        percentage=Decimal("100.0"),
        is_passed=True,
    )

    # Teacher removes student from group
    removed = remove_student_from_group(group_1, free_student_1, actor=teacher_1, reason="Kursni tugatdi")
    assert removed is True

    # Historical result is completely intact!
    res.refresh_from_db()
    assert res.score == Decimal("10.0")
    assert res.percentage == Decimal("100.0")

    # Future starts on the GROUP_ONLY test are now blocked
    decision = resolve_test_access(free_student_1, test_group_only, action="start")
    assert decision.allowed is False
    assert decision.reason_code == "DENIED_GROUP_ONLY"


# ===========================================================================
# 4. Group Invitations Lifecycle & Truthful Billing
# ===========================================================================
@pytest.mark.django_db(transaction=True)
def test_group_invitations_and_truthful_billing(teacher_1, free_student_1, free_student_2, group_1):
    # Create invitation with max 1 use
    inv = create_group_invitation(
        teacher_1,
        group_1.id,
        expires_in_days=3,
        max_uses=1,
        requires_approval=False,
    )
    assert inv.token is not None
    assert inv.is_usable is True

    # Student 1 joins via token
    res1 = join_group_by_token(free_student_1, inv.token)
    assert res1["status"] == "joined"
    assert group_1.students.filter(id=free_student_1.id).exists()

    # Truthful billing verification:
    # Joining a group does NOT set payment_status=PAID and does NOT grant PRO
    enrollment = GroupEnrollment.objects.get(group=group_1, student=free_student_1)
    assert enrollment.payment_status == GroupEnrollment.PaymentStatus.DUE_SOON
    assert enrollment.last_payment_date is None
    assert free_student_1.has_pro_access is False

    # Second student tries to use the same single-use invitation: BLOCKED
    inv.refresh_from_db()
    assert inv.is_usable is False
    with pytest.raises(ValidationError) as exc:
        join_group_by_token(free_student_2, inv.token)
    assert "chegarasiga yetildi" in str(exc.value)

    # Rotate invitation: generates new token
    rotated = rotate_group_invitation(teacher_1, inv.id)
    assert rotated.token != inv.token
    assert rotated.uses_count == 0

    # Revoke invitation: immediately disabled
    revoked = revoke_group_invitation(teacher_1, rotated.id)
    assert revoked.is_revoked is True
    with pytest.raises(ValidationError):
        join_group_by_token(free_student_2, revoked.token)


# ===========================================================================
# 5. Group Capacity Enforcement
# ===========================================================================
@pytest.mark.django_db(transaction=True)
def test_group_capacity_blocks_overflow(teacher_1, group_1):
    group_1.max_students = 2
    group_1.save()

    u1 = User.objects.create_user(email="s1@test.com", password="x", role="student")
    u2 = User.objects.create_user(email="s2@test.com", password="x", role="student")
    u3 = User.objects.create_user(email="s3@test.com", password="x", role="student")

    add_student_to_group(group_1, u1, actor=teacher_1)
    add_student_to_group(group_1, u2, actor=teacher_1)
    assert group_1.students.count() == 2

    # Third student join exceeds capacity
    with pytest.raises(ValueError) as exc:
        add_student_to_group(group_1, u3, actor=teacher_1)
    assert "to'lgan" in str(exc.value)


# ===========================================================================
# 6. Approval Requests Workflow
# ===========================================================================
@pytest.mark.django_db(transaction=True)
def test_approval_request_workflow(teacher_1, free_student_1, group_1):
    inv = create_group_invitation(
        teacher_1,
        group_1.id,
        requires_approval=True,
    )

    # Student requests join
    res = join_group_by_token(free_student_1, inv.token)
    assert res["status"] == "pending_approval"
    assert not group_1.students.filter(id=free_student_1.id).exists()

    # Teacher sees pending request
    pending = list_teacher_pending_requests(teacher_1)
    assert len(pending) == 1
    req_id = pending[0]["id"]

    # Teacher approves
    review_res = review_join_request(teacher_1, req_id, approved=True)
    assert review_res["status"] == "approved"
    assert group_1.students.filter(id=free_student_1.id).exists()


# ===========================================================================
# 7. Teacher Classroom API Endpoints
# ===========================================================================
@pytest.mark.django_db(transaction=True)
def test_classroom_api_endpoints(teacher_1, free_student_1, group_1, test_group_only):
    client = Client()
    client.force_login(teacher_1)

    # 1. Overview
    resp1 = client.get("/api/classroom/teacher/overview/")
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["total_groups"] >= 1

    # 2. Assign Test Wizard
    resp2 = client.post(
        "/api/classroom/teacher/assign-test/",
        data={
            "test_id": test_group_only.id,
            "group_id": group_1.id,
            "due_days": 5,
            "max_attempts": 2,
            "audience_mode": "GROUP_ONLY",
        },
        content_type="application/json",
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["status"] == "success"

    # 3. Access check preflight endpoint
    client.force_login(free_student_1)
    resp3 = client.get(f"/api/classroom/tests/{test_group_only.id}/access/")
    assert resp3.status_code == 200
    data3 = resp3.json()
    assert "allowed" in data3
