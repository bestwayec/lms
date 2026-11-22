"""Transactional outbox: exactly-once enqueue, leases, policy and private cards.

No real Telegram call is made: every delivery uses a fake sender.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from unittest import mock
from zoneinfo import ZoneInfo

import pytest
from django.db import transaction
from django.test import override_settings
from django.utils import timezone

from apps.accounts.models import User
from apps.attendance.models import NotificationPreference
from apps.courses.homework_service import (
    cancel_teacher_homework,
    create_unified_homework,
    start_student_homework,
    submit_student_homework,
)
from apps.courses.models import Course, StudentGroup
from apps.notifications import outbox
from apps.notifications.models import OutboxMessage
from apps.tests.models import Choice, Question, Test, TestAttempt
from apps.tests.services import SaveAnswerService, SubmitAttemptService

TASHKENT = ZoneInfo("Asia/Tashkent")


class FakeSender:
    def __init__(self, fail_times: int = 0):
        self.fail_times = fail_times
        self.sent: list[tuple[int, str]] = []

    def __call__(self, chat_id, card):
        if self.fail_times > 0:
            self.fail_times -= 1
            raise RuntimeError("telegram 502")
        self.sent.append((chat_id, card.text))
        return str(len(self.sent))


def _user(email, role="student", chat=None):
    return User.objects.create_user(
        email=email, password="p", role=role, first_name="Ali", last_name="V", telegram_chat_id=chat
    )


@pytest.fixture
def teacher(db):
    return _user("ob_teacher@example.com", "teacher", chat=9001)


@pytest.fixture
def student(db):
    return _user("ob_student@example.com", chat=9002)


@pytest.fixture
def peer(db):
    return _user("ob_peer@example.com", chat=9003)


@pytest.fixture
def group(teacher, student, peer):
    g = StudentGroup.objects.create(name="OB", teacher=teacher)
    g.students.add(student, peer)
    return g


@pytest.fixture
def test_obj(teacher):
    course = Course.objects.create(teacher=teacher, title="OB", slug="ob-course")
    t = Test.objects.create(
        course=course, title="OB quiz", created_by=teacher, status=Test.Status.PUBLISHED,
        access_type=Test.AccessType.STUDENTS_ONLY, time_limit_minutes=30, max_attempts=0,
    )
    q = Question.objects.create(test=t, position=1, text="Q", points=1)
    Choice.objects.create(question=q, text="r", is_correct=True, position=1)
    Choice.objects.create(question=q, text="w", is_correct=False, position=2)
    return t


def _hw(teacher, group, test_obj=None, **kw):
    kw.setdefault("due_date", timezone.now() + timedelta(days=2))
    if test_obj is None:
        kw.setdefault("content_type", "custom")
    hw, _ = create_unified_homework(
        teacher, title="Uy <vazifa>", group_id=group.id, test_id=test_obj.id if test_obj else None, **kw
    )
    return hw


def _deliver_all(sender, now=None):
    return outbox.process_batch(sender=sender, now=now)


# --------------------------------------------------------------------------- enqueue


@pytest.mark.django_db
def test_assignment_enqueues_one_per_recipient_and_replay_adds_none(teacher, group, student, peer):
    due = timezone.now() + timedelta(days=1)
    hw, _ = create_unified_homework(
        teacher, title="x", group_id=group.id, content_type="custom", due_date=due, idempotency_key="k"
    )
    create_unified_homework(teacher, title="x", group_id=group.id, content_type="custom", due_date=due, idempotency_key="k")
    rows = OutboxMessage.objects.filter(event="homework_assigned")
    assert sorted(rows.values_list("recipient_id", flat=True)) == sorted([student.id, peer.id])
    assert outbox.enqueue_homework_assigned(hw) == 0  # replay of the producer itself


@pytest.mark.django_db(transaction=True)
def test_rolled_back_assignment_leaves_no_message(teacher, group):
    with pytest.raises(RuntimeError):
        with transaction.atomic():
            _hw(teacher, group)
            raise RuntimeError("business failure after create")
    assert not OutboxMessage.objects.exists()


@pytest.mark.django_db
def test_result_card_is_queued_exactly_once_and_is_private(teacher, group, student, peer, test_obj):
    hw = _hw(teacher, group, test_obj)
    attempt = TestAttempt.objects.get(id=start_student_homework(student, hw.id)["attempt_id"])
    q = test_obj.questions.get()
    SaveAnswerService.execute(attempt.id, q.id, choice_ids=[q.choices.get(is_correct=True).id], student=student)
    submit_student_homework(student, hw.id)
    submit_student_homework(student, hw.id)  # duplicate finish
    results = OutboxMessage.objects.filter(event="homework_result")
    assert results.count() == 1 and results.get().recipient_id == student.id

    sender = FakeSender()
    _deliver_all(sender)
    texts = {chat: text for chat, text in sender.sent}
    assert "Natija tayyor" in texts[9002]
    assert "To'g'ri javoblar: 1/1" in texts[9002]
    assert all("Natija tayyor" not in t for c, t in sender.sent if c != 9002)  # private
    assert "&lt;vazifa&gt;" in texts[9002]  # HTML-escaped title


@pytest.mark.django_db
def test_runner_finish_then_start_announces_once(teacher, group, student, test_obj):
    hw = _hw(teacher, group, test_obj, max_attempts=1)
    attempt = TestAttempt.objects.get(id=start_student_homework(student, hw.id)["attempt_id"])
    SubmitAttemptService.execute(attempt.id, student)  # TakeTest finished it
    for _ in range(2):
        submit_student_homework(student, hw.id)
    assert OutboxMessage.objects.filter(event="homework_result").count() == 1


@pytest.mark.django_db
def test_grading_failure_notifies_teacher_not_student(teacher, group, student, test_obj):
    hw = _hw(teacher, group, test_obj)
    start_student_homework(student, hw.id)
    with mock.patch.object(SubmitAttemptService, "execute", side_effect=RuntimeError("down")):
        submit_student_homework(student, hw.id)
    assert not OutboxMessage.objects.filter(event="homework_result").exists()
    # Not completed yet (retryable): no teacher alert until the failure is final.
    def finish_without_result(aid, user):
        TestAttempt.objects.filter(id=aid).update(status=TestAttempt.Status.COMPLETED, completed_at=timezone.now())

    with mock.patch.object(SubmitAttemptService, "execute", side_effect=finish_without_result):
        submit_student_homework(student, hw.id)
    review = OutboxMessage.objects.get(event="homework_review")
    assert review.recipient_id == teacher.id
    assert not OutboxMessage.objects.filter(event="homework_result").exists()


# --------------------------------------------------------------------------- delivery


@pytest.mark.django_db
def test_failed_send_backs_off_then_dead(teacher, group, student):
    _hw(teacher, group)
    msg = OutboxMessage.objects.get(recipient=student)
    OutboxMessage.objects.exclude(id=msg.id).delete()
    OutboxMessage.objects.filter(id=msg.id).update(max_attempts=2)
    now = timezone.now()
    sender = FakeSender(fail_times=5)
    assert _deliver_all(sender, now) == {"pending": 1}
    msg.refresh_from_db()
    assert msg.attempts == 1 and msg.next_attempt_at == now + timedelta(seconds=60) and "502" in msg.last_error
    assert _deliver_all(sender, now) == {}  # not due yet
    assert _deliver_all(sender, now + timedelta(seconds=61)) == {"dead": 1}
    msg.refresh_from_db()
    assert msg.status == "dead" and sender.sent == []


@pytest.mark.django_db
def test_retry_succeeds_once(teacher, group, student):
    _hw(teacher, group)
    OutboxMessage.objects.exclude(recipient=student).delete()
    now = timezone.now()
    sender = FakeSender(fail_times=1)
    _deliver_all(sender, now)
    _deliver_all(sender, now + timedelta(minutes=5))
    _deliver_all(sender, now + timedelta(minutes=10))
    assert len(sender.sent) == 1
    assert OutboxMessage.objects.get(recipient=student).status == "sent"


@pytest.mark.django_db
def test_expired_lease_is_fenced(teacher, group, student):
    _hw(teacher, group)
    msg = OutboxMessage.objects.get(recipient=student)
    OutboxMessage.objects.exclude(id=msg.id).delete()
    now = timezone.now()
    assert outbox.claim_batch("worker-a", now=now) == [msg.id]
    assert outbox.claim_batch("worker-b", now=now) == []  # still leased
    later = now + timedelta(seconds=outbox.LEASE_SECONDS + 1)
    assert outbox.claim_batch("worker-b", now=later) == [msg.id]  # lease expired
    sender = FakeSender()
    assert outbox.deliver(msg.id, "worker-a", sender, later) == "not_owner"
    assert outbox.deliver(msg.id, "worker-b", sender, later) == "sent"
    assert len(sender.sent) == 1


@pytest.mark.django_db
def test_quiet_hours_defer_to_their_end(teacher, group, student):
    NotificationPreference.objects.create(user=student, quiet_hours_start=time(22, 0), quiet_hours_end=time(7, 0))
    _hw(teacher, group)
    OutboxMessage.objects.exclude(recipient=student).delete()
    night = datetime(2026, 11, 22, 23, 30, tzinfo=TASHKENT)
    OutboxMessage.objects.update(next_attempt_at=night - timedelta(minutes=1))
    with mock.patch("apps.notifications.outbox.timezone.now", return_value=night):
        sender = FakeSender()
        assert _deliver_all(sender, night) == {"deferred_quiet_hours": 1}
    msg = OutboxMessage.objects.get()
    assert msg.next_attempt_at == datetime(2026, 11, 23, 7, 0, tzinfo=TASHKENT)
    assert msg.attempts == 0 and sender.sent == []


@pytest.mark.django_db
def test_preferences_and_missing_telegram_suppress(teacher, group, student, peer):
    NotificationPreference.objects.create(user=student, homework_assigned_alerts=False)
    User.objects.filter(id=peer.id).update(telegram_chat_id=None)
    _hw(teacher, group)
    sender = FakeSender()
    assert _deliver_all(sender) == {"suppressed": 2}
    assert sender.sent == []
    assert set(OutboxMessage.objects.values_list("last_error", flat=True)) == {"preference", "no_telegram"}


@pytest.mark.django_db
def test_rate_limit_defers(teacher, group, student):
    now = timezone.now()
    for i in range(outbox.RATE_LIMIT_PER_MINUTE):
        OutboxMessage.objects.create(
            recipient=student, event="homework_assigned", dedup_key=f"old{i}", status="sent", sent_at=now
        )
    _hw(teacher, group)
    OutboxMessage.objects.filter(status="pending").exclude(recipient=student).delete()
    assert _deliver_all(FakeSender(), timezone.now()) == {"deferred_rate_limit": 1}


@pytest.mark.django_db
def test_stale_messages_are_not_sent(teacher, group, student):
    hw = _hw(teacher, group)
    cancel_teacher_homework(teacher, hw.id)
    sender = FakeSender()
    assert _deliver_all(sender) == {"suppressed": 2}
    assert sender.sent == []


@pytest.mark.django_db
def test_deadline_reminders_skip_finished_students_and_dedup(teacher, group, student, peer):
    hw = _hw(teacher, group, due_date=timezone.now() + timedelta(hours=5))
    start_student_homework(student, hw.id)
    submit_student_homework(student, hw.id, {"text": "done"})
    assert outbox.enqueue_deadline_reminders() == 1
    assert outbox.enqueue_deadline_reminders() == 0
    assert OutboxMessage.objects.get(event="homework_reminder").recipient_id == peer.id


@pytest.mark.django_db
def test_worker_task_is_disabled_by_default(teacher, group):
    from apps.notifications.tasks import process_outbox_task

    _hw(teacher, group)
    with mock.patch("apps.notifications.outbox.telegram_sender") as real:
        assert process_outbox_task() == {"skipped": "disabled"}
        real.assert_not_called()
    assert OutboxMessage.objects.filter(status="pending").count() == 2


# --------------------------------------------------------------------------- webhook


@pytest.mark.django_db
@override_settings(TELEGRAM_WEBHOOK_SECRET="s3cret")
def test_webhook_processes_each_update_once_and_rejects_bad_secret(client):
    from django.core.cache import cache

    cache.clear()
    fake_app = mock.MagicMock()
    fake_app.process_update = mock.AsyncMock()
    body = '{"update_id": 777, "message": {"message_id": 1, "date": 0, "chat": {"id": 1, "type": "private"}}}'
    with mock.patch("apps.notifications.views._get_bot_app", return_value=fake_app):
        bad = client.post("/api/notifications/telegram/webhook/", body, content_type="application/json",
                          HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="nope")
        assert bad.status_code == 401
        for _ in range(2):
            ok = client.post("/api/notifications/telegram/webhook/", body, content_type="application/json",
                             HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="s3cret")
            assert ok.status_code == 200
    assert fake_app.process_update.await_count == 1


# --------------------------------------------------------------------------- bot /vazifalarim


@pytest.mark.django_db
def test_bot_homework_list_matches_website_and_requires_verified_link(teacher, group, student, test_obj):
    from apps.notifications.bot.homework_commands import render_homework_list, verified_user_for_telegram

    assert verified_user_for_telegram(9002) is None  # linked but not verified
    User.objects.filter(id=student.id).update(telegram_identity_verified_at=timezone.now())
    user = verified_user_for_telegram(9002)
    assert user == student

    _hw(teacher, group, test_obj)
    text, _ = render_homework_list(user)
    assert "Uy &lt;vazifa&gt;" in text and "Boshlanmagan" in text
    other = _user("ob_other@example.com", chat=9100)
    User.objects.filter(id=other.id).update(telegram_identity_verified_at=timezone.now())
    text_other, _ = render_homework_list(verified_user_for_telegram(9100))
    assert "Uy" not in text_other  # never another student's homework


@pytest.mark.django_db
def test_bot_homework_command_is_registered():
    from telegram.ext import Application, CommandHandler

    from apps.notifications.bot.handlers import setup_handlers

    app = Application.builder().token("123:TEST").build()
    setup_handlers(app)
    commands = {c for hs in app.handlers.values() for h in hs if isinstance(h, CommandHandler) for c in h.commands}
    assert {"vazifalarim", "homework"} <= commands
