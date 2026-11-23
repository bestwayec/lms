"""
Unified Test Access Policy Service (GRANDEC NEXT 6.0).

One authoritative service that resolves whether a given user may view,
start, resume, or submit a test, what entitlement tier applies, whether
commercial test quota must be charged, and the exact reason code.

Access Source Types:
- 'classroom': Active group member or individual assignment (bypasses PRO requirement, 0 commercial quota)
- 'subscription': Paid PRO or Premium subscriber
- 'public': Free public access (subject to commercial free test quota)
- 'author': The teacher who authored the test or teaches the course
- 'admin': Platform administrator / superuser

Audience Modes:
- GROUP_ONLY: Only assigned students through teacher group or individual assignment
- GROUP_AND_SUBSCRIBERS: Assigned students (free) OR paid subscribers (PRO/Premium)
- SUBSCRIBERS_ONLY: Only PRO/Premium subscribers
- PUBLIC_FREE: Open to all users
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.accounts.access import is_platform_admin


@dataclass(frozen=True)
class TestAccessDecision:
    """The structured authoritative decision for a test access request."""

    allowed: bool
    reason_code: str
    reason: str
    access_source: str
    assignment: Any | None = None
    group: Any | None = None
    is_classroom_entitlement: bool = False
    consumes_quota: bool = False
    available_attempts: int | None = None
    deadline: datetime | None = None
    is_paid_catalog: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason_code": self.reason_code,
            "reason": self.reason,
            "access_source": self.access_source,
            "assignment_id": getattr(self.assignment, "id", None),
            "group_id": getattr(self.group, "id", None),
            "group_name": getattr(self.group, "name", "") if self.group else "",
            "is_classroom_entitlement": self.is_classroom_entitlement,
            "consumes_quota": self.consumes_quota,
            "available_attempts": self.available_attempts,
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "is_paid_catalog": self.is_paid_catalog,
        }


def normalize_audience_mode(test: Any) -> str:
    """Derive effective audience_mode, preserving backward compatibility with access_type."""
    access_type = getattr(test, "access_type", "")
    mode = getattr(test, "audience_mode", "")

    if access_type == "STUDENTS_ONLY":
        return "GROUP_ONLY"
    if access_type == "PRO_ONLY" and mode not in ("GROUP_AND_SUBSCRIBERS", "SUBSCRIBERS_ONLY"):
        if getattr(test, "assigned_group_id", None):
            return "GROUP_AND_SUBSCRIBERS"
        return "SUBSCRIBERS_ONLY"

    if mode in ("GROUP_ONLY", "GROUP_AND_SUBSCRIBERS", "SUBSCRIBERS_ONLY", "PUBLIC_FREE"):
        if mode == "GROUP_ONLY" and access_type == "PUBLIC" and not getattr(test, "created_by_id", None) and not getattr(test, "assigned_group_id", None):
            return "PUBLIC_FREE"
        return mode

    if access_type == "PUBLIC":
        return "PUBLIC_FREE"

    return "GROUP_ONLY"


def resolve_test_access(
    user: Any,
    test: Any,
    assignment: Any = None,
    action: str = "start",
) -> TestAccessDecision:
    """
    Authoritative test access resolver.

    Parameters:
    - user: UserModel instance or AnonymousUser or None
    - test: Test instance
    - assignment: Optional Homework instance (if already resolved)
    - action: 'view' | 'start' | 'resume' | 'submit'
    """
    from apps.courses.models import Homework
    from apps.payments.entitlements import can_start_test, get_effective_entitlement
    from apps.tests.models import Test, TestAttempt

    # 1. Anonymous / unauthenticated checks
    if user is None or not getattr(user, "is_authenticated", False):
        mode = normalize_audience_mode(test)
        if action == "view" and mode == "PUBLIC_FREE" and getattr(test, "is_active", True) and getattr(test, "status", "") == "published":
            return TestAccessDecision(
                allowed=True,
                reason_code="ALLOWED_PUBLIC_VIEW",
                reason="Ommaviy test tavsifi ko'rish uchun ochiq.",
                access_source="public",
                is_paid_catalog=False,
            )
        return TestAccessDecision(
            allowed=False,
            reason_code="DENIED_UNAUTHENTICATED",
            reason="Test topshirish uchun avval tizimga kiring.",
            access_source="unknown",
            is_paid_catalog=(mode in ("GROUP_AND_SUBSCRIBERS", "SUBSCRIBERS_ONLY")),
        )

    # 2. Administrator & Superuser Immunity. A center admin is an administrator
    #    only of tests that belong to their own center (never platform-wide).
    if (
        is_platform_admin(user)
        or getattr(user, "is_superuser", False)
        or getattr(user, "role", "") == "admin"
        or (getattr(user, "role", "") == "center_admin" and test_in_user_centers(test, user))
    ):
        return TestAccessDecision(
            allowed=True,
            reason_code="ALLOWED_ADMIN",
            reason="Platforma administratori uchun barcha testlar ochiq.",
            access_source="admin",
            is_classroom_entitlement=True,
            consumes_quota=False,
            is_paid_catalog=False,
        )

    # 3. Author / Course Teacher
    is_author = (
        getattr(test, "created_by_id", None) == user.id
        or getattr(getattr(test, "course", None), "teacher_id", None) == user.id
    )
    if is_author:
        return TestAccessDecision(
            allowed=True,
            reason_code="ALLOWED_AUTHOR",
            reason="Test muallifi yoki kurs ustozi.",
            access_source="author",
            is_classroom_entitlement=True,
            consumes_quota=False,
            is_paid_catalog=False,
        )

    # 4. Another Teacher Check (Private tests cannot be accessed by other teachers)
    user_role = getattr(user, "role", "student")
    mode = normalize_audience_mode(test)
    if user_role == "teacher":
        if mode == "GROUP_ONLY" or getattr(test, "created_by_id", None) is not None:
            return TestAccessDecision(
                allowed=False,
                reason_code="DENIED_TEACHER_PRIVATE",
                reason="Boshqa ustozning shaxsiy testiga kirish taqiqlangan.",
                access_source="unknown",
                is_paid_catalog=False,
            )

    # 5. Active and Publication Status Check (for regular users)
    if not getattr(test, "is_active", True) or getattr(test, "status", "") in ("draft", "archived"):
        return TestAccessDecision(
            allowed=False,
            reason_code="DENIED_UNPUBLISHED",
            reason="Ushbu test hozirda faol emas yoki qoralama holatida.",
            access_source="unknown",
            is_paid_catalog=False,
        )

    # 6. Active In-Progress Attempt Check
    active_attempt = TestAttempt.objects.filter(
        test=test,
        student=user,
        status=TestAttempt.Status.IN_PROGRESS,
    ).first()

    if active_attempt is not None:
        if getattr(active_attempt, "is_expired", False):
            # Expired attempt will be finalized, but does not grant instant resume
            pass
        elif action in ("resume", "view", "submit"):
            return TestAccessDecision(
                allowed=True,
                reason_code="ALLOWED_RESUME",
                reason="Boshlangan test urinishini davom ettirish.",
                access_source=getattr(active_attempt, "access_source", "classroom"),
                is_classroom_entitlement=getattr(active_attempt, "is_classroom_entitlement", True),
                consumes_quota=False,
                assignment=active_attempt.classroom_assignment,
                group=active_attempt.classroom_group,
                is_paid_catalog=False,
            )

    # 7. Classroom Assignment Check
    # Look for active Homework assigned to user or user's active groups
    hw = assignment
    if hw is None:
        # Prefer an active assignment: a cancelled one for another group must
        # not hide a live assignment for the student's current group.
        hw = (
            Homework.objects.filter(test=test)
            .filter(Q(group__students=user) | Q(student=user))
            .select_related("group")
            .order_by(
                # ACTIVE first, then newest
                models.Case(
                    models.When(status=Homework.Status.ACTIVE, then=0),
                    default=1,
                    output_field=models.IntegerField(),
                ),
                "-created_at",
            )
            .first()
        )

    # Also check legacy direct assigned_group
    assigned_group = getattr(test, "assigned_group", None)
    has_legacy_group = bool(assigned_group and assigned_group.students.filter(id=user.id).exists())

    if hw is not None or has_legacy_group:
        target_group = getattr(hw, "group", None) or assigned_group

        # Check if homework was explicitly cancelled
        if hw is not None and hw.status == Homework.Status.CANCELLED:
            return TestAccessDecision(
                allowed=False,
                reason_code="DENIED_CANCELLED",
                reason="Ushbu vazifa bekor qilingan.",
                access_source="classroom",
                assignment=hw,
                group=target_group,
                is_classroom_entitlement=True,
                consumes_quota=False,
            )

        # Check deadline for new attempts
        now = timezone.now()
        due_date = getattr(hw, "due_date", None)
        if due_date and now > due_date and action in ("start", "new"):
            return TestAccessDecision(
                allowed=False,
                reason_code="DENIED_DEADLINE_EXPIRED",
                reason="Vazifani topshirish muddati tugagan.",
                access_source="classroom",
                assignment=hw,
                group=target_group,
                is_classroom_entitlement=True,
                consumes_quota=False,
                deadline=due_date,
            )

        # Check max attempts
        max_attempts = getattr(hw, "max_attempts", None) or getattr(test, "max_attempts", 0)
        completed_count = TestAttempt.objects.filter(
            test=test,
            student=user,
            status__in=[TestAttempt.Status.COMPLETED, TestAttempt.Status.TIMEOUT],
        ).count()

        if max_attempts and max_attempts > 0 and completed_count >= max_attempts and action in ("start", "new"):
            return TestAccessDecision(
                allowed=False,
                reason_code="DENIED_MAX_ATTEMPTS",
                reason=f"Test uchun maksimal urinishlar soni ({max_attempts}) tugadi.",
                access_source="classroom",
                assignment=hw,
                group=target_group,
                is_classroom_entitlement=True,
                consumes_quota=False,
                available_attempts=0,
                deadline=due_date,
            )

        # ALL CLASSROOM CHECKS PASSED: Free classroom entitlement!
        return TestAccessDecision(
            allowed=True,
            reason_code="ALLOWED_CLASSROOM_ASSIGNMENT",
            reason="Ustoz guruhi vazifasi bo'yicha ruxsat berildi (alohida PRO talab qilinmaydi).",
            access_source="classroom",
            assignment=hw,
            group=target_group,
            is_classroom_entitlement=True,
            consumes_quota=False,
            available_attempts=max(0, max_attempts - completed_count) if max_attempts else None,
            deadline=due_date,
            is_paid_catalog=bool(mode in ("GROUP_AND_SUBSCRIBERS", "SUBSCRIBERS_ONLY")),
        )

    # 8. User is NOT in an assigned group for this test. Evaluate based on audience_mode:
    if mode == "GROUP_ONLY":
        return TestAccessDecision(
            allowed=False,
            reason_code="DENIED_GROUP_ONLY",
            reason="Ushbu test faqat o'qituvchining biriktirilgan guruhi o'quvchilari uchun mo'ljallangan.",
            access_source="unknown",
            is_paid_catalog=False,
        )

    if mode in ("GROUP_AND_SUBSCRIBERS", "SUBSCRIBERS_ONLY"):
        has_pro = bool(getattr(user, "has_pro_access", False))
        entitlement = get_effective_entitlement(user)
        is_subscriber = has_pro or entitlement.is_paid or (entitlement.plan_type in ("pro", "premium", "sponsor", "admin"))

        if is_subscriber:
            return TestAccessDecision(
                allowed=True,
                reason_code="ALLOWED_SUBSCRIBER",
                reason="PRO / Premium obuna orqali ruxsat berildi.",
                access_source="subscription",
                is_classroom_entitlement=False,
                consumes_quota=(action == "start"),
                is_paid_catalog=True,
            )
        else:
            return TestAccessDecision(
                allowed=False,
                reason_code="DENIED_SUBSCRIPTION_REQUIRED",
                reason="Ushbu testdan foydalanish uchun PRO yoki Premium obuna talab qilinadi.",
                access_source="unknown",
                is_paid_catalog=True,
            )

    if mode == "PUBLIC_FREE":
        if action == "resume":
            return TestAccessDecision(
                allowed=True,
                reason_code="ALLOWED_RESUME",
                reason="Boshlangan testni davom ettirish.",
                access_source="public",
                is_classroom_entitlement=False,
                consumes_quota=False,
                is_paid_catalog=False,
            )

        can_start, q_reason, remaining = can_start_test(user)
        if can_start:
            return TestAccessDecision(
                allowed=True,
                reason_code="ALLOWED_PUBLIC",
                reason="Ommaviy bepul test.",
                access_source="public",
                is_classroom_entitlement=False,
                consumes_quota=True,
                is_paid_catalog=False,
            )
        else:
            return TestAccessDecision(
                allowed=False,
                reason_code="DENIED_QUOTA_EXCEEDED",
                reason="Bepul test topshirish limitingiz tugadi. PRO tarifiga o'tishingiz mumkin.",
                access_source="public",
                consumes_quota=True,
                is_paid_catalog=False,
            )

    return TestAccessDecision(
        allowed=False,
        reason_code="DENIED_UNKNOWN_POLICY",
        reason="Testga kirish siyosati aniqlanmadi.",
        access_source="unknown",
        is_paid_catalog=False,
    )


# ---------------------------------------------------------------------------
# Tenant scope
# ---------------------------------------------------------------------------


def user_center_ids(user: Any) -> set[int]:
    """Learning centers a user administers or belongs to."""
    from apps.organizations.models import LearningCenter

    ids: set[int] = set()
    if getattr(user, "learning_center_id", None):
        ids.add(user.learning_center_id)
    branch = getattr(user, "branch", None)
    if branch is not None and getattr(branch, "center_id", None):
        ids.add(branch.center_id)
    if getattr(user, "pk", None):
        ids.update(LearningCenter.objects.filter(owner_id=user.pk).values_list("id", flat=True))
    return ids


def test_center_ids(test: Any) -> set[int]:
    """Centers a test belongs to: its author's / course teacher's / assigned group's center."""
    ids: set[int] = set()
    for person in (getattr(test, "created_by", None), getattr(getattr(test, "course", None), "teacher", None)):
        if person is None:
            continue
        if getattr(person, "learning_center_id", None):
            ids.add(person.learning_center_id)
        branch = getattr(person, "branch", None)
        if branch is not None and getattr(branch, "center_id", None):
            ids.add(branch.center_id)
    group = getattr(test, "assigned_group", None)
    if group is not None and getattr(group, "branch", None) is not None and group.branch.center_id:
        ids.add(group.branch.center_id)
    return ids


def test_in_user_centers(test: Any, user: Any) -> bool:
    mine = user_center_ids(user)
    return bool(mine) and bool(mine & test_center_ids(test))


def effective_audience_q() -> dict[str, Q]:
    """Query form of :func:`normalize_audience_mode` (keep the two in step).

    Returns Q objects selecting tests whose *effective* audience is each mode.
    """
    students_only = Q(access_type="STUDENTS_ONLY")
    legacy_pro = Q(access_type="PRO_ONLY") & ~Q(audience_mode__in=["GROUP_AND_SUBSCRIBERS", "SUBSCRIBERS_ONLY"])
    orphan_public = Q(audience_mode="GROUP_ONLY", access_type="PUBLIC", created_by__isnull=True, assigned_group__isnull=True)
    rest = ~students_only & ~legacy_pro
    return {
        "GROUP_ONLY": students_only | (rest & Q(audience_mode="GROUP_ONLY") & ~orphan_public),
        "GROUP_AND_SUBSCRIBERS": ~students_only
        & ((legacy_pro & Q(assigned_group__isnull=False)) | (rest & Q(audience_mode="GROUP_AND_SUBSCRIBERS"))),
        "SUBSCRIBERS_ONLY": ~students_only
        & ((legacy_pro & Q(assigned_group__isnull=True)) | (rest & Q(audience_mode="SUBSCRIBERS_ONLY"))),
        "PUBLIC_FREE": rest & (Q(audience_mode="PUBLIC_FREE") | orphan_public),
    }
