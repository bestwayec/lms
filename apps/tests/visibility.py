"""Who may see a test (catalogue entry and content) — one rule shared by list and detail.

Mirrors the membership rules ``StartAttemptService`` already enforces when a student starts
a ``STUDENTS_ONLY`` test, so what a user can *see* never exceeds what they can *take*:

* platform admins / superusers: everything;
* the author (``created_by`` / ``course.teacher``) and the teacher of the group a test is
  assigned to: everything, drafts included, and the question content;
* everybody else: **active** tests that are not ``STUDENTS_ONLY``; ``STUDENTS_ONLY`` tests only
  for members of the assigned group (``assigned_group`` or a studio ``Homework`` group) or, when
  nothing is assigned, students of a group owned by the test's teacher.

Everything is expressed with subqueries (``pk__in`` / ``..._id__in``), never joins, so adding it
to a queryset cannot multiply rows or corrupt ``Count()`` annotations.
"""

from __future__ import annotations

from django.db.models import Q, QuerySet

from apps.accounts.access import is_platform_admin
from apps.courses.models import Homework, StudentGroup

from .models import Test


def _is_admin(user) -> bool:
    return bool(
        user is not None
        and getattr(user, "is_authenticated", False)
        and (is_platform_admin(user) or getattr(user, "is_superuser", False))
    )


def _authenticated(user) -> bool:
    return bool(user is not None and getattr(user, "is_authenticated", False))


def staff_q(user) -> Q:
    """Tests the user authored or teaches through an assigned group."""
    if not _authenticated(user):
        return Q(pk__in=[])
    return (
        Q(created_by_id=user.pk)
        | Q(course__teacher_id=user.pk)
        | Q(assigned_group__teacher_id=user.pk)
        | Q(pk__in=Homework.objects.filter(group__teacher_id=user.pk, test__isnull=False).values("test_id"))
    )


def member_q(user) -> Q:
    """Classroom tests the user belongs to via explicit assignment (Homework or assigned_group)."""
    if not _authenticated(user):
        return Q(pk__in=[])
    my_groups = StudentGroup.objects.filter(students=user)
    return (
        Q(assigned_group_id__in=my_groups.values("pk"))
        | Q(
            pk__in=Homework.objects.filter(Q(group__students=user) | Q(student=user), test__isnull=False)
            .exclude(status=Homework.Status.CANCELLED)
            .values("test_id")
        )
    )


def visible_tests(queryset: QuerySet, user) -> QuerySet:
    """Restrict *queryset* of ``Test`` to what *user* may see in a catalogue or open directly."""
    if _is_admin(user):
        return queryset

    # Published and active tests for non-staff
    published_active = Q(is_active=True, status="published")

    # Group/Classroom tests explicitly assigned
    assigned_members = published_active & (
        Q(audience_mode="GROUP_ONLY") | Q(access_type=Test.AccessType.STUDENTS_ONLY)
    ) & member_q(user)

    # Public free tests
    public_free = published_active & (
        Q(audience_mode="PUBLIC_FREE") | Q(access_type=Test.AccessType.PUBLIC)
    )

    # Subscriber tests (available to subscribers or assigned members)
    subscriber_catalog = published_active & (
        Q(audience_mode__in=["GROUP_AND_SUBSCRIBERS", "SUBSCRIBERS_ONLY"])
        | Q(access_type=Test.AccessType.PRO_ONLY)
    )

    if not _authenticated(user):
        return queryset.filter(public_free | (subscriber_catalog & Q(audience_mode="GROUP_AND_SUBSCRIBERS")))

    # Check if authenticated user is a subscriber
    has_pro = bool(getattr(user, "has_pro_access", False))
    if has_pro:
        allowed_catalog = public_free | subscriber_catalog | assigned_members
    else:
        # Non-subscriber only sees assigned classroom tests, public tests, and catalog preview of subscriber tests
        allowed_catalog = public_free | assigned_members | (subscriber_catalog & Q(audience_mode="GROUP_AND_SUBSCRIBERS") & member_q(user))

    return queryset.filter(allowed_catalog | staff_q(user))


def can_see_test_content(user, test: Test) -> bool:
    """Questions and passages are for the test's staff; students get them through their attempt."""
    if _is_admin(user):
        return True
    if not _authenticated(user):
        return False
    return Test.objects.filter(pk=test.pk).filter(staff_q(user)).exists()
