"""
Teacher-owned test assignment using the Unified Homework Engine.

Ensures strict authorization, group validation, and synchronizes
with the Unified Homework Engine while preventing test hijack across groups.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.attendance.services import teacher_groups
from apps.courses.homework_service import create_unified_homework
from apps.courses.models import Homework
from apps.tests.models import Test

logger = logging.getLogger(__name__)


class AssignmentError(Exception):
    pass


def available_tests(actor, group=None):
    """
    Returns tests available for teacher assignment.
    Filters tests created by the teacher or belonging to courses taught by the teacher.
    """
    from apps.accounts.access import is_platform_admin

    qs = Test.objects.filter(is_active=True).exclude(status="archived")
    if not is_platform_admin(actor):
        qs = qs.filter(Q(created_by=actor) | Q(course__teacher=actor))
    if group is not None:
        qs = qs.filter(Q(assigned_group__isnull=True) | Q(assigned_group=group))
    return qs.distinct().order_by("title", "id")


@transaction.atomic
def assign_test(actor, group_id: int, test_id: int, due_days: int = 3):
    """
    Assigns a test to a student group and synchronizes with Unified Homework Engine.
    Serializes concurrent confirmations and prevents moving another group's test.
    """
    from apps.accounts.access import is_platform_admin

    if (
        not actor.is_active
        or not actor.telegram_identity_verified_at
        or not (actor.role == "teacher" or is_platform_admin(actor))
    ):
        raise AssignmentError("Hisobingizni qayta tasdiqlang.")

    group = teacher_groups(actor).filter(pk=group_id).first()
    if group is None:
        raise AssignmentError("Guruh topilmadi yoki sizga tegishli emas.")

    test = (
        Test.objects.select_for_update(of=("self",))
        .filter(pk=test_id, is_active=True)
        .filter(Q(created_by=actor) | Q(course__teacher=actor))
        .first()
    )
    if test is None:
        raise AssignmentError("Test topilmadi yoki sizga tegishli emas.")

    if test.assigned_group_id == group.id:
        return test, False

    if test.assigned_group_id is not None:
        raise AssignmentError("Bu test boshqa guruhga biriktirilgan.")

    test.assigned_group = group
    test.save(update_fields=["assigned_group"])

    # Synchronize with Unified Homework Engine
    due_date = timezone.now() + timedelta(days=max(1, due_days))
    title = f"{test.title} (Vazifa)"[:200]
    try:
        create_unified_homework(
            actor,
            title=title,
            due_date=due_date,
            group_id=group.id,
            test_id=test.id,
            description=test.description or "",
        )
    except Exception as exc:
        logger.warning("Unified homework sync warning during telegram assignment: %s", exc)

    return test, True
