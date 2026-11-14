from unittest.mock import AsyncMock, patch
from types import SimpleNamespace

import pytest
from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.courses.models import Course, StudentGroup
from apps.notifications.bot.teacher_assignments import AssignmentError, assign_test, available_tests
from apps.notifications.bot.handlers import _assignment_action
from apps.tests.models import Test


@pytest.mark.django_db
def test_assignment_ownership_duplicates_and_existing_group():
    User = get_user_model()
    teacher = User.objects.create_user(email="assignment-teacher@example.test", password="x", role="teacher", telegram_chat_id=34111, telegram_identity_verified_at=timezone.now())
    other = User.objects.create_user(email="assignment-other@example.test", password="x", role="teacher", telegram_chat_id=34112, telegram_identity_verified_at=timezone.now())
    group = StudentGroup.objects.create(name="One", teacher=teacher)
    other_group = StudentGroup.objects.create(name="Two", teacher=other)
    course = Course.objects.create(title="My course", slug="assignment-course", teacher=teacher)
    other_course = Course.objects.create(title="Other", slug="assignment-other", teacher=other)
    test = Test.objects.create(title="Real test", course=course, is_active=True)
    private_test = Test.objects.create(title="Other test", course=other_course, is_active=True)
    assert list(available_tests(teacher, group)) == [test]
    with pytest.raises(AssignmentError):
        assign_test(teacher, other_group.id, test.id)
    with pytest.raises(AssignmentError):
        assign_test(teacher, group.id, private_test.id)
    with pytest.raises(AssignmentError):
        assign_test(teacher, group.id, 999999)
    saved, created = assign_test(teacher, group.id, test.id)
    assert created and saved.assigned_group_id == group.id
    assert assign_test(teacher, group.id, test.id)[1] is False
    second_group = StudentGroup.objects.create(name="Second", teacher=teacher)
    with pytest.raises(AssignmentError):
        assign_test(teacher, second_group.id, test.id)
    test.refresh_from_db()
    assert test.assigned_group_id == group.id


def test_assignment_denies_group_chat():
    from apps.notifications.bot.handlers import _assignment_actor
    update = SimpleNamespace(effective_chat=SimpleNamespace(type="supergroup"))
    with patch("apps.notifications.bot.handlers.send_reply", new=AsyncMock()) as reply:
        assert async_to_sync(_assignment_actor)(update) is None
        reply.assert_awaited_once()


@pytest.mark.django_db(transaction=True)
def test_teacher_reviews_and_confirms_assignment():
    from apps.notifications.bot.handlers import _assignment_list

    User = get_user_model()
    teacher = User.objects.create_user(email="assignment-flow@example.test", password="x", role="teacher", telegram_chat_id=34113, telegram_identity_verified_at=timezone.now())
    group = StudentGroup.objects.create(name="My group", teacher=teacher)
    course = Course.objects.create(title="My course", slug="assignment-flow", teacher=teacher)
    test = Test.objects.create(title="Biology", course=course, is_active=True)
    query = SimpleNamespace(answer=AsyncMock(), edit_message_text=AsyncMock(), message=SimpleNamespace(reply_text=AsyncMock()))
    update = SimpleNamespace(effective_chat=SimpleNamespace(type="private"), effective_user=SimpleNamespace(id=34113), callback_query=query)
    context = SimpleNamespace(user_data={})
    with patch("apps.notifications.bot.handlers._get_or_create_user_async", new=AsyncMock(return_value=teacher)):
        async_to_sync(_assignment_list)(update, context, group.id)
        assert query.edit_message_text.await_args.kwargs["reply_markup"].inline_keyboard[0][0].callback_data == f"tasreview_{group.id}_{test.id}"
        async_to_sync(_assignment_action)(update, context, group.id, test.id, False)
        assert "Biology" in query.edit_message_text.await_args.args[0]
        test.refresh_from_db()
        assert test.assigned_group_id is None
        async_to_sync(_assignment_action)(update, context, group.id, test.id, True)
        test.refresh_from_db()
        assert test.assigned_group_id == group.id
        assert f"/tests/{test.id}" in query.edit_message_text.await_args.kwargs["reply_markup"].inline_keyboard[0][0].url
        async_to_sync(_assignment_action)(update, context, group.id, test.id, True)
        assert "allaqachon" in query.edit_message_text.await_args.args[0]


@pytest.mark.django_db(transaction=True)
def test_concurrent_assignments_cannot_move_test():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from django.db import close_old_connections, connection

    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL row locks")
    User = get_user_model()
    teacher = User.objects.create_user(email="assignment-race@example.test", password="x", role="teacher", telegram_identity_verified_at=timezone.now())
    groups = [StudentGroup.objects.create(name=name, teacher=teacher) for name in ("A", "B")]
    course = Course.objects.create(title="Race", slug="assignment-race", teacher=teacher)
    test = Test.objects.create(title="Race", course=course, is_active=True)
    barrier = Barrier(2)

    def attempt(group_id):
        close_old_connections()
        try:
            actor = User.objects.get(pk=teacher.id)
            barrier.wait(timeout=10)
            try:
                assign_test(actor, group_id, test.id)
                return "saved"
            except AssignmentError:
                return "rejected"
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(attempt, [group.id for group in groups]))
    assert sorted(outcomes) == ["rejected", "saved"]
    test.refresh_from_db()
    assert test.assigned_group_id in [group.id for group in groups]


@pytest.mark.django_db(transaction=True)
def test_assignment_list_pages_include_all_owned_tests():
    from apps.notifications.bot.handlers import _assignment_list

    User = get_user_model()
    teacher = User.objects.create_user(email="assignment-pages@example.test", password="x", role="teacher", telegram_chat_id=34114, telegram_identity_verified_at=timezone.now())
    group = StudentGroup.objects.create(name="My group", teacher=teacher)
    course = Course.objects.create(title="My course", slug="assignment-pages", teacher=teacher)
    for number in range(10):
        Test.objects.create(title=f"Test {number:02d}", course=course, is_active=True)
    query = SimpleNamespace(answer=AsyncMock(), edit_message_text=AsyncMock(), message=SimpleNamespace(reply_text=AsyncMock()))
    update = SimpleNamespace(effective_chat=SimpleNamespace(type="private"), effective_user=SimpleNamespace(id=34114), callback_query=query)
    with patch("apps.notifications.bot.handlers._get_or_create_user_async", new=AsyncMock(return_value=teacher)):
        async_to_sync(_assignment_list)(update, SimpleNamespace(), group.id)
        buttons = [b for row in query.edit_message_text.await_args.kwargs["reply_markup"].inline_keyboard for b in row]
        assert len([b for b in buttons if b.callback_data.startswith("tasreview_")]) == 8
        assert any(b.callback_data == f"taspage_{group.id}_1" for b in buttons)
        async_to_sync(_assignment_list)(update, SimpleNamespace(), group.id, 1)
        buttons = [b for row in query.edit_message_text.await_args.kwargs["reply_markup"].inline_keyboard for b in row]
        assert len([b for b in buttons if b.callback_data.startswith("tasreview_")]) == 2
        assert any(b.callback_data == f"taspage_{group.id}_0" for b in buttons)
