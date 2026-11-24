"""Classroom access policy matrix + tenant scope (Priority 3/4).

Teacher A owns Group A and assigns a private 30-question test:
FREE members of Group A may take it (no quota); outsiders may not, PRO or
not; Group B only if separately assigned; removed students lose future
access but keep results; a center admin administers only their own center.
"""

from datetime import timedelta
from unittest import mock

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.courses.group_service import remove_student_from_group
from apps.courses.homework_service import cancel_teacher_homework, create_unified_homework
from apps.courses.models import Course, StudentGroup
from apps.organizations.models import LearningCenter
from apps.tests.access_policy import resolve_test_access
from apps.tests.models import Test
from apps.tests.visibility import visible_tests


def mk(email, role="student", center=None):
    return User.objects.create_user(email=email, password="p", role=role, learning_center=center)


@pytest.fixture
def world(db):
    owner = mk("own@x.uz", "center_admin")
    ca = LearningCenter.objects.create(name="A", slug="ca", owner=owner)
    cb = LearningCenter.objects.create(name="B", slug="cb", owner=mk("ownb@x.uz", "center_admin"))
    t_a = mk("ta@x.uz", "teacher", ca)
    t_b = mk("tb@x.uz", "teacher", cb)
    admin_a = mk("aa@x.uz", "center_admin", ca)
    admin_b = mk("ab@x.uz", "center_admin", cb)
    free_member = mk("fm@x.uz", center=ca)
    pro_outsider = mk("po@x.uz", center=cb)
    free_outsider = mk("fo@x.uz")
    b_student = mk("bs@x.uz", center=cb)
    ga = StudentGroup.objects.create(name="GA", teacher=t_a)
    ga.students.add(free_member)
    gb = StudentGroup.objects.create(name="GB", teacher=t_b)
    gb.students.add(b_student)
    course = Course.objects.create(teacher=t_a, title="C", slug="c-a")
    test = Test.objects.create(
        course=course, created_by=t_a, title="Ona tili attestatsiya", status="published", is_active=True,
        access_type=Test.AccessType.STUDENTS_ONLY,  # audience_mode keeps its PUBLIC_FREE default
        max_attempts=0,
    )
    hw, _ = create_unified_homework(t_a, title="Attestatsiya", group_id=ga.id, test_id=test.id,
                                    due_date=timezone.now() + timedelta(days=2))
    return locals()


def allowed(user, test, action="start"):
    return resolve_test_access(user, test, action=action)


@pytest.mark.django_db
def test_access_matrix(world):
    w = world
    with mock.patch.object(User, "has_pro_access", new_callable=mock.PropertyMock, return_value=False):
        d = allowed(w["free_member"], w["test"])
        assert d.allowed and d.access_source == "classroom" and d.consumes_quota is False
        assert not allowed(w["free_outsider"], w["test"]).allowed
        assert not allowed(w["b_student"], w["test"]).allowed
    with mock.patch.object(User, "has_pro_access", new_callable=mock.PropertyMock, return_value=True):
        # A subscription never overrides private teacher ownership.
        assert not allowed(w["pro_outsider"], w["test"]).allowed
    assert not allowed(w["t_b"], w["test"]).allowed  # another teacher


@pytest.mark.django_db
def test_paid_catalog_only_when_explicitly_published(world):
    w = world
    Test.objects.filter(pk=w["test"].pk).update(access_type="PUBLIC", audience_mode="GROUP_AND_SUBSCRIBERS")
    w["test"].refresh_from_db()
    with mock.patch.object(User, "has_pro_access", new_callable=mock.PropertyMock, return_value=True), \
         mock.patch("apps.payments.entitlements.get_effective_entitlement") as ent:
        ent.return_value = mock.Mock(is_paid=True, plan_type="pro")
        assert allowed(w["pro_outsider"], w["test"]).allowed
    with mock.patch.object(User, "has_pro_access", new_callable=mock.PropertyMock, return_value=False), \
         mock.patch("apps.payments.entitlements.get_effective_entitlement") as ent:
        ent.return_value = mock.Mock(is_paid=False, plan_type="free")
        assert not allowed(w["free_outsider"], w["test"]).allowed
        assert allowed(w["free_member"], w["test"]).allowed  # still free for the group


@pytest.mark.django_db
def test_group_b_only_when_separately_assigned(world):
    w = world
    assert not allowed(w["b_student"], w["test"]).allowed
    # Teacher B cannot assign Teacher A's private test.
    with pytest.raises(PermissionError):
        create_unified_homework(w["t_b"], title="x", group_id=w["gb"].id, test_id=w["test"].id,
                                due_date=timezone.now() + timedelta(days=1))
    # Teacher A assigning it to a second group of theirs works.
    gb2 = StudentGroup.objects.create(name="GA2", teacher=w["t_a"])
    gb2.students.add(w["b_student"])
    create_unified_homework(w["t_a"], title="y", group_id=gb2.id, test_id=w["test"].id,
                            due_date=timezone.now() + timedelta(days=1))
    assert allowed(w["b_student"], w["test"]).allowed


@pytest.mark.django_db
def test_removed_student_loses_future_access(world):
    w = world
    remove_student_from_group(w["ga"], w["free_member"], actor=w["t_a"])
    assert not allowed(w["free_member"], w["test"]).allowed


@pytest.mark.django_db
def test_cancelled_assignment_does_not_hide_an_active_one(world):
    w = world
    hw2, _ = create_unified_homework(w["t_a"], title="z", group_id=w["ga"].id, test_id=w["test"].id,
                                     due_date=timezone.now() + timedelta(days=3))
    cancel_teacher_homework(w["t_a"], hw2.id)  # newest is cancelled; the first is active
    assert allowed(w["free_member"], w["test"]).allowed


@pytest.mark.django_db
def test_center_admin_scope(world):
    w = world
    assert allowed(w["admin_a"], w["test"]).allowed  # own center
    d = allowed(w["admin_b"], w["test"])
    assert not d.allowed and d.reason_code != "ALLOWED_ADMIN"


@pytest.mark.django_db
def test_catalog_hides_students_only_test_with_default_audience(world):
    w = world
    qs = Test.objects.filter(pk=w["test"].pk)
    assert not visible_tests(qs, None).exists()
    assert not visible_tests(qs, w["free_outsider"]).exists()
    assert not visible_tests(qs, w["admin_b"]).exists()
    assert visible_tests(qs, w["free_member"]).exists()
    assert visible_tests(qs, w["t_a"]).exists()


@pytest.mark.django_db
def test_resume_is_never_charged_or_paywalled_and_retake_is_quota_checked(world):
    from apps.payments.entitlements import QuotaDenied
    from apps.tests.models import TestAttempt
    from apps.tests.services import StartAttemptService, TestAccessDeniedError

    w = world
    Test.objects.filter(pk=w["test"].pk).update(access_type="PUBLIC", audience_mode="PUBLIC_FREE")
    student = w["free_outsider"]
    first = StartAttemptService.execute(test_id=w["test"].id, student=student)
    # Quota is now used up (FREE = 1). Resuming the same attempt still works and charges nothing.
    with mock.patch("apps.payments.entitlements.enforce_test_quota") as charge:
        again = StartAttemptService.execute(test_id=w["test"].id, student=student)
        assert again.id == first.id and charge.call_count == 0
    TestAttempt.objects.filter(id=first.id).update(status="completed")
    # A new (public) attempt is a new start: refused once the free quota is spent.
    with pytest.raises((TestAccessDeniedError, QuotaDenied)):
        StartAttemptService.execute(test_id=w["test"].id, student=student)


@pytest.mark.django_db
def test_classroom_start_does_not_consume_free_quota(world):
    from apps.tests.services import StartAttemptService

    w = world
    with mock.patch("apps.payments.entitlements.enforce_test_quota") as charge:
        StartAttemptService.execute(test_id=w["test"].id, student=w["free_member"])
    assert charge.call_count == 0


@pytest.mark.django_db
def test_center_admin_sees_own_teachers_groups_without_branches(world):
    """Many centers have no branches: the admin must still see their teachers' groups — and only theirs."""
    from apps.courses.teacher_workspace_service import get_teacher_groups

    w = world
    ids_a = set(get_teacher_groups(w["admin_a"]).values_list("id", flat=True))
    ids_b = set(get_teacher_groups(w["admin_b"]).values_list("id", flat=True))
    assert w["ga"].id in ids_a and w["gb"].id not in ids_a
    assert w["gb"].id in ids_b and w["ga"].id not in ids_b
