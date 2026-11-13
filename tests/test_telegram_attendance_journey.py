from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.attendance.models import AttendanceRecord, AttendanceSession
from apps.notifications.bot.handlers import (
    _attendance_callback, _attendance_page_callback, _attendance_review_callback,
    _finalize_callback, _mark_callback,
)
from apps.courses.models import StudentGroup


@pytest.mark.django_db(transaction=True)
def test_teacher_marks_across_pages_and_confirms_without_duplicate_notifications():
    User = get_user_model()
    teacher = User.objects.create_user(email="attendance-flow@example.test", password="x", role="teacher", telegram_chat_id=21831, telegram_identity_verified_at=timezone.now())
    group = StudentGroup.objects.create(teacher=teacher, name="Class")
    students = [User.objects.create_user(email=f"att-flow-{i}@example.test", password="x", first_name=f"Student {i:02d}") for i in range(26)]
    group.students.add(*students)
    query = SimpleNamespace(id="update-1", answer=AsyncMock(), edit_message_text=AsyncMock(), message=SimpleNamespace(reply_text=AsyncMock()))
    update = SimpleNamespace(effective_chat=SimpleNamespace(type="private"), effective_user=SimpleNamespace(id=21831), callback_query=query, update_id=122)
    context = SimpleNamespace(user_data={})
    with patch("apps.notifications.bot.handlers._get_or_create_user_async", new=AsyncMock(return_value=teacher)), \
         patch("apps.attendance.notifications.notify_parents_of_session") as parents, \
         patch("apps.attendance.notifications.send_group_attendance_summary") as group_notice, \
         patch("apps.notifications.tasks_parent.send_parent_absence_alert_task.delay") as legacy_alert:
        async_to_sync(_attendance_callback)(update, context, group.id)
        session = AttendanceSession.objects.get(group=group)
        async_to_sync(_attendance_page_callback)(update, context, session.id, 1)
        assert "Student 25" in query.edit_message_text.await_args.args[0]
        async_to_sync(_mark_callback)(update, context, session.id, students[-1].id, "present")
        assert AttendanceRecord.objects.filter(session=session, student=students[-1], status="present").exists()
        async_to_sync(_attendance_review_callback)(update, context, session.id)
        assert "Belgilanmagan: 25" in query.edit_message_text.await_args.args[0]
        async_to_sync(_finalize_callback)(update, context, session.id)
        session.refresh_from_db()
        assert session.status == AttendanceSession.Status.DRAFT
        async_to_sync(_finalize_callback)(update, context, session.id, True)
        session.refresh_from_db()
        assert session.status == AttendanceSession.Status.FINALIZED
        first_finalized_at = session.finalized_at
        async_to_sync(_finalize_callback)(update, context, session.id, True)
        session.refresh_from_db()
        assert session.finalized_at == first_finalized_at
        assert parents.call_count == 1 and group_notice.call_count == 1
        assert legacy_alert.call_count == 25
        assert session.records.count() == 26
        with patch("apps.notifications.bot.handlers.send_reply", new=AsyncMock()) as reply:
            async_to_sync(_mark_callback)(update, context, session.id, students[-1].id, "absent")
            reply.assert_awaited_once()
        assert session.records.get(student=students[-1]).status == "present"


def test_group_chat_cannot_open_attendance():
    from apps.notifications.bot.handlers import _attendance_actor
    update = SimpleNamespace(effective_chat=SimpleNamespace(type="supergroup"))
    with patch("apps.notifications.bot.handlers.send_reply", new=AsyncMock()) as reply:
        assert async_to_sync(_attendance_actor)(update) is None
        reply.assert_awaited_once()


@pytest.mark.django_db(transaction=True)
def test_other_teacher_and_expired_session_cannot_open_register():
    from apps.attendance.services import create_session

    User = get_user_model()
    owner = User.objects.create_user(email="att-owner@example.test", password="x", role="teacher")
    outsider = User.objects.create_user(email="att-outsider@example.test", password="x", role="teacher", telegram_chat_id=12348, telegram_identity_verified_at=timezone.now())
    group = StudentGroup.objects.create(teacher=owner, name="Private")
    session, _ = create_session(group=group, teacher=owner, actor=owner)
    update = SimpleNamespace(effective_chat=SimpleNamespace(type="private"), effective_user=SimpleNamespace(id=12348))
    with patch("apps.notifications.bot.handlers._get_or_create_user_async", new=AsyncMock(return_value=outsider)), \
         patch("apps.notifications.bot.handlers.send_reply", new=AsyncMock()) as reply:
        async_to_sync(_attendance_page_callback)(update, SimpleNamespace(user_data={}), session.id, 0)
        async_to_sync(_attendance_review_callback)(update, SimpleNamespace(user_data={}), 999999)
    assert reply.await_count == 2


@pytest.mark.django_db(transaction=True)
def test_concurrent_finalization_notifies_only_once():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from django.db import close_old_connections, connection
    from apps.attendance.services import create_session, finalize_and_notify, mark

    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL row locks")
    User = get_user_model()
    teacher = User.objects.create_user(email="att-race@example.test", password="x", role="teacher")
    student = User.objects.create_user(email="att-race-student@example.test", password="x")
    group = StudentGroup.objects.create(teacher=teacher, name="Race")
    group.students.add(student)
    session, _ = create_session(group=group, teacher=teacher, actor=teacher)
    mark(session, student, "present", actor=teacher)
    barrier = Barrier(2)

    def finish(_):
        close_old_connections()
        try:
            current = AttendanceSession.objects.get(pk=session.pk)
            actor = User.objects.get(pk=teacher.pk)
            barrier.wait(timeout=10)
            return finalize_and_notify(current, actor=actor).get("already_finalized", False)
        finally:
            close_old_connections()

    with patch("apps.attendance.notifications.notify_parents_of_session") as parents, \
         patch("apps.attendance.notifications.send_group_attendance_summary") as group_notice:
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(finish, range(2)))
        assert sorted(outcomes) == [False, True]
        assert parents.call_count == 1 and group_notice.call_count == 1
