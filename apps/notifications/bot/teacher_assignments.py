"""Teacher-owned test assignment using the existing test/group relationship."""
from django.db import transaction
from django.db.models import Q

from apps.attendance.services import teacher_groups
from apps.tests.models import Test


class AssignmentError(Exception):
    pass


def available_tests(actor, group):
    return (Test.objects.filter(is_active=True)
            .filter(Q(created_by=actor) | Q(course__teacher=actor))
            .filter(Q(assigned_group__isnull=True) | Q(assigned_group=group))
            .distinct().order_by("title", "id"))


@transaction.atomic
def assign_test(actor, group_id, test_id):
    """Serialize concurrent confirmations; never move another group's test."""
    from apps.accounts.access import is_platform_admin

    if (not actor.is_active or not actor.telegram_identity_verified_at
            or not (actor.role == "teacher" or is_platform_admin(actor))):
        raise AssignmentError("Hisobingizni qayta tasdiqlang.")
    group = teacher_groups(actor).filter(pk=group_id).first()
    if group is None:
        raise AssignmentError("Guruh topilmadi yoki sizga tegishli emas.")
    test = (Test.objects.select_for_update(of=("self",)).filter(pk=test_id, is_active=True)
            .filter(Q(created_by=actor) | Q(course__teacher=actor)).first())
    if test is None:
        raise AssignmentError("Test topilmadi yoki sizga tegishli emas.")
    if test.assigned_group_id == group.id:
        return test, False
    if test.assigned_group_id is not None:
        raise AssignmentError("Bu test boshqa guruhga biriktirilgan.")
    test.assigned_group = group
    test.save(update_fields=["assigned_group"])
    return test, True
