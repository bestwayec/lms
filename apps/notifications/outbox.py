"""Transactional notification outbox (Telegram Bot 3.0).

Producers call :func:`enqueue` inside the same database transaction as the
business change (homework created, grade recorded). If that transaction
rolls back, so does the message — there is no "announced but never
happened" state. Each event has a deterministic ``dedup_key`` (UNIQUE), so
retries, double clicks and replays enqueue at most one message.

A worker (:func:`process_batch`) leases due rows (``SELECT … FOR UPDATE
SKIP LOCKED`` on PostgreSQL), applies per-user preferences, quiet hours and
a per-recipient rate limit, renders the card from the *current official
state* and sends it. Completion is fenced by the lease owner, so a worker
whose lease expired cannot overwrite the row another worker now owns.
Failures back off exponentially up to ``max_attempts`` and then go DEAD.

Nothing here runs unless ``NOTIFICATION_OUTBOX_ENABLED`` is true; the
Celery task is not in the beat schedule by default.
"""

from __future__ import annotations

import html
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from apps.attendance.models import NotificationPreference
from apps.notifications.models import OutboxMessage

logger = logging.getLogger(__name__)

LEASE_SECONDS = 120
RATE_LIMIT_PER_MINUTE = 5
BACKOFF_BASE_SECONDS = 60
LOCAL_TZ = ZoneInfo("Asia/Tashkent")

Event = OutboxMessage.Event


# ---------------------------------------------------------------------------
# Producing
# ---------------------------------------------------------------------------


def enqueue(recipient, event: str, dedup_key: str, payload: dict[str, Any] | None = None, *, not_before=None):
    """Write one outbox row in the caller's transaction. Idempotent by ``dedup_key``.

    Returns the row, or None if a row with that key already exists.
    """
    if recipient is None or not dedup_key:
        return None
    try:
        with transaction.atomic():
            return OutboxMessage.objects.create(
                recipient=recipient,
                event=event,
                dedup_key=dedup_key[:200],
                payload=payload or {},
                next_attempt_at=not_before or timezone.now(),
            )
    except IntegrityError:
        return None


def enqueue_homework_assigned(hw) -> int:
    """One message per current recipient of a newly created homework."""
    if hw.student_id:
        recipients = [hw.student]
    elif hw.group_id:
        recipients = list(hw.group.students.filter(is_active=True))
    else:
        recipients = []
    count = 0
    for student in recipients:
        if enqueue(student, Event.HOMEWORK_ASSIGNED, f"hw_assigned:{hw.id}:{student.id}", {"homework_id": hw.id}):
            count += 1
    return count


def enqueue_homework_outcome(sub) -> None:
    """Private result card to the student, or a review request to the teacher.

    Keyed by submission + attempt number, so each finished attempt is
    announced exactly once, however often the outcome is re-synced.
    """
    from apps.courses.homework_service import derive_submission_status
    from apps.courses.models import HomeworkSubmission

    hw = sub.homework
    status, _score, _label = derive_submission_status(hw, sub)
    attempt_no = sub.attempts_count or 1
    if status == HomeworkSubmission.Status.GRADED:
        enqueue(
            sub.student,
            Event.HOMEWORK_RESULT,
            f"hw_result:{sub.id}:{attempt_no}",
            {"homework_id": hw.id, "submission_id": sub.id},
        )
    elif status in (HomeworkSubmission.Status.AWAITING_REVIEW, HomeworkSubmission.Status.GRADING_FAILED):
        teacher = hw.created_by or (hw.group.teacher if hw.group_id else None)
        if teacher is not None:
            enqueue(
                teacher,
                Event.HOMEWORK_REVIEW,
                f"hw_review:{sub.id}:{attempt_no}:{status}",
                {"homework_id": hw.id, "submission_id": sub.id},
            )


def enqueue_deadline_reminders(now: datetime | None = None, within: timedelta = timedelta(hours=24)) -> int:
    """Remind current recipients who have not finished homework due within ``within``."""
    from apps.courses.homework_service import _DONE, derive_submission_status
    from apps.courses.models import Homework, HomeworkSubmission

    now = now or timezone.now()
    count = 0
    from django.db.models import Q

    due = (
        Homework.objects.filter(
            status=Homework.Status.ACTIVE,
            due_date__gt=now,
            due_date__lte=now + within,
        )
        .filter(Q(group__isnull=True) | ~Q(group__status="archived"))
        .select_related("group", "student")
    )
    for hw in due:
        if hw.start_date and hw.start_date > now:
            continue
        students = [hw.student] if hw.student_id else list(hw.group.students.filter(is_active=True)) if hw.group_id else []
        subs = {s.student_id: s for s in HomeworkSubmission.objects.filter(homework=hw)}
        for st in students:
            status, _, _ = derive_submission_status(hw, subs.get(st.id), now)
            if status in _DONE:
                continue
            if enqueue(st, Event.HOMEWORK_REMINDER, f"hw_reminder24:{hw.id}:{st.id}", {"homework_id": hw.id}):
                count += 1
    return count


def enqueue_join_request_submitted(join_req) -> None:
    teacher = getattr(join_req.group, "teacher", None)
    if teacher:
        enqueue(
            teacher,
            Event.JOIN_REQUEST_SUBMITTED,
            f"join_req_submitted:{join_req.id}",
            {"request_id": join_req.id, "group_id": join_req.group_id, "student_id": join_req.student_id},
        )


def enqueue_join_request_reviewed(join_req) -> None:
    from apps.courses.models import GroupJoinRequest

    if join_req.status == GroupJoinRequest.Status.APPROVED:
        enqueue(
            join_req.student,
            Event.JOIN_REQUEST_APPROVED,
            f"join_req_approved:{join_req.id}",
            {"request_id": join_req.id, "group_id": join_req.group_id},
        )
    elif join_req.status == GroupJoinRequest.Status.REJECTED:
        enqueue(
            join_req.student,
            Event.JOIN_REQUEST_REJECTED,
            f"join_req_rejected:{join_req.id}",
            {"request_id": join_req.id, "group_id": join_req.group_id},
        )


def enqueue_group_welcome(group, student) -> None:
    enqueue(
        student,
        Event.GROUP_WELCOME,
        f"group_welcome:{group.id}:{student.id}",
        {"group_id": group.id},
    )


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------

_PREF_FIELD = {
    Event.HOMEWORK_ASSIGNED: "homework_assigned_alerts",
    Event.HOMEWORK_REMINDER: "homework_deadline_alerts",
    Event.HOMEWORK_RESULT: "test_result_alerts",
    Event.HOMEWORK_REVIEW: "teacher_homework_review",
    Event.JOIN_REQUEST_SUBMITTED: "teacher_homework_review",
    Event.JOIN_REQUEST_APPROVED: "homework_assigned_alerts",
    Event.JOIN_REQUEST_REJECTED: "homework_assigned_alerts",
    Event.GROUP_WELCOME: "homework_assigned_alerts",
}


def _preference(user) -> NotificationPreference:
    return NotificationPreference.objects.filter(user=user).first() or NotificationPreference(user=user)


def quiet_hours_end(pref: NotificationPreference, now: datetime) -> datetime | None:
    """If ``now`` is inside the user's quiet hours, the moment they end; else None."""
    start, end = pref.quiet_hours_start, pref.quiet_hours_end
    if start is None or end is None or start == end:
        return None
    local = now.astimezone(LOCAL_TZ)
    t = local.time()
    inside = (start <= t < end) if start < end else (t >= start or t < end)
    if not inside:
        return None
    end_dt = datetime.combine(local.date(), end, tzinfo=LOCAL_TZ)
    if end_dt <= local:
        end_dt += timedelta(days=1)
    return end_dt


def _rate_limited(user, now: datetime) -> bool:
    return (
        OutboxMessage.objects.filter(
            recipient=user, status=OutboxMessage.Status.SENT, sent_at__gte=now - timedelta(minutes=1)
        ).count()
        >= RATE_LIMIT_PER_MINUTE
    )


# ---------------------------------------------------------------------------
# Rendering — only from official persisted state
# ---------------------------------------------------------------------------


@dataclass
class Card:
    text: str
    buttons: list[list[dict[str, str]]]


def _site() -> str:
    return getattr(settings, "SITE_URL", "").rstrip("/")


def _open_buttons(path: str) -> list[list[dict[str, str]]]:
    url = f"{_site()}{path}"
    if not url.startswith("https://"):
        return []  # Telegram rejects non-HTTPS buttons; text still contains the action
    rows = [[{"text": "🌐 Saytda ochish", "url": url}]]
    return rows


def render(msg: OutboxMessage) -> Card | None:
    """Build the card from current DB state. None → nothing true to say any more."""
    from apps.courses.homework_service import derive_submission_status, official_exam_summary
    from apps.courses.models import Homework, HomeworkSubmission

    if msg.event == Event.ESSAY_APPEAL:
        from apps.essays.models import EssaySubmission

        esub = (
            EssaySubmission.objects.select_related("student", "topic")
            .filter(id=msg.payload.get("submission_id"))
            .first()
        )
        if esub is None or esub.appeal_status not in (
            EssaySubmission.AppealStatus.SUBMITTED,
            EssaySubmission.AppealStatus.AWAITING_REVIEWER,
            EssaySubmission.AppealStatus.UNDER_REVIEW,
        ):
            return None
        who = html.escape(esub.student.get_full_name() or "O'quvchi")
        topic_name = html.escape(esub.topic.title if esub.topic_id else f"#{esub.id}")
        return Card(
            f"⚖️ <b>Yangi esse apellatsiyasi</b>\n\n{topic_name}\nO'quvchi: {who}",
            _open_buttons("/teacher/essays"),
        )

    if msg.event == Event.ESSAY_REVIEWED:
        from apps.essays.models import EssaySubmission

        esub = (
            EssaySubmission.objects.select_related("topic", "teacher_review")
            .filter(id=msg.payload.get("submission_id"))
            .first()
        )
        if esub is None or not hasattr(esub, "teacher_review"):
            return None
        rev = esub.teacher_review
        topic_name = html.escape(esub.topic.title if esub.topic_id else f"#{esub.id}")
        lines = [
            "✍️ <b>Ustoz essengizni tekshirdi</b>",
            "",
            topic_name,
            f"Yakuniy ball: {rev.final_score}/24",
        ]
        if rev.teacher_comments:
            lines.append(f"Izoh: {html.escape(rev.teacher_comments[:400])}")
        return Card("\n".join(lines), _open_buttons(f"/essay-result/{esub.id}"))

    if msg.event == Event.JOIN_REQUEST_SUBMITTED:
        from apps.courses.models import GroupJoinRequest

        req = GroupJoinRequest.objects.filter(id=msg.payload.get("request_id")).select_related("group", "student").first()
        if not req or req.status != GroupJoinRequest.Status.PENDING:
            return None
        st_name = html.escape(req.student.get_full_name() or req.student.email)
        grp_name = html.escape(req.group.name)
        text = (
            f"🔔 <b>Guruhga qo'shilish so'rovi</b>\n\n"
            f"O'quvchi: <b>{st_name}</b>\n"
            f"Guruh: <b>{grp_name}</b>\n\n"
            "Iltimos, ustoz kabinetida a'zolikni tasdiqlang yoki rad eting."
        )
        return Card(text, _open_buttons("/teacher"))

    if msg.event == Event.JOIN_REQUEST_APPROVED:
        from apps.courses.models import GroupJoinRequest

        req = GroupJoinRequest.objects.filter(id=msg.payload.get("request_id")).select_related("group").first()
        if not req or req.status != GroupJoinRequest.Status.APPROVED:
            return None
        grp_name = html.escape(req.group.name)
        text = (
            f"🎉 <b>Guruhga qabul qilindingiz!</b>\n\n"
            f"Siz <b>{grp_name}</b> guruhiga muvaffaqiyatli qabul qilindingiz. "
            "Ustozingiz bergan darslar va sinf testlari endi siz uchun ochiq."
        )
        return Card(text, _open_buttons("/my-homework"))

    if msg.event == Event.JOIN_REQUEST_REJECTED:
        from apps.courses.models import GroupJoinRequest

        req = GroupJoinRequest.objects.filter(id=msg.payload.get("request_id")).select_related("group").first()
        if not req or req.status != GroupJoinRequest.Status.REJECTED:
            return None
        grp_name = html.escape(req.group.name)
        reason = html.escape(req.rejection_reason or "Ustoz tomonidan rad etildi.")
        text = (
            f"❌ <b>Guruh so'rovingiz rad etildi</b>\n\n"
            f"Guruh: <b>{grp_name}</b>\n"
            f"Sabab: {reason}"
        )
        return Card(text, _open_buttons("/my-homework"))

    if msg.event == Event.GROUP_WELCOME:
        from apps.courses.models import StudentGroup

        grp = StudentGroup.objects.filter(id=msg.payload.get("group_id")).first()
        if not grp:
            return None
        grp_name = html.escape(grp.name)
        text = (
            f"👋 <b>Guruhga xush kelibsiz!</b>\n\n"
            f"Siz <b>{grp_name}</b> guruhiga a'zo bo'ldingiz. "
            "Ustozingiz bergan barcha dars testlarini bepul topshirishingiz mumkin."
        )
        return Card(text, _open_buttons("/my-homework"))

    hw = Homework.objects.filter(id=msg.payload.get("homework_id")).select_related("test", "group").first()
    if hw is None:
        return None
    title = html.escape(hw.title)
    due = hw.due_date.astimezone(LOCAL_TZ).strftime("%d.%m.%Y %H:%M")

    if msg.event in (Event.HOMEWORK_ASSIGNED, Event.HOMEWORK_REMINDER):
        if hw.status != Homework.Status.ACTIVE or hw.due_date <= timezone.now():
            return None
        from apps.courses.homework_service import _is_current_recipient

        if not _is_current_recipient(hw, msg.recipient):
            return None
        if msg.event == Event.HOMEWORK_REMINDER:
            sub = HomeworkSubmission.objects.filter(homework=hw, student=msg.recipient).first()
            status, _, _ = derive_submission_status(hw, sub)
            if status not in (HomeworkSubmission.Status.NOT_STARTED, HomeworkSubmission.Status.IN_PROGRESS):
                return None
            head = "⏰ <b>Vazifa muddati yaqinlashmoqda</b>"
        else:
            head = "📚 <b>Yangi vazifa</b>"
        return Card(f"{head}\n\n{title}\nMuddat: {due}", _open_buttons("/my-homework"))

    sub = HomeworkSubmission.objects.filter(id=msg.payload.get("submission_id"), homework=hw).select_related(
        "student", "test_attempt", "result", "essay_submission"
    ).first()
    if sub is None:
        return None
    status, score, _ = derive_submission_status(hw, sub)

    if msg.event == Event.HOMEWORK_RESULT:
        if msg.recipient_id != sub.student_id or status != HomeworkSubmission.Status.GRADED:
            return None  # private, and only a finished official grade
        lines = [f"✅ <b>Natija tayyor</b>\n\n{title}"]
        official = official_exam_summary(hw, sub)
        if official:
            lines.append(f"To'g'ri javoblar: {official['correct']}/{official['total']}")
            if "band" in official:
                lines.append(f"IELTS band: {official['band']}")
            if official.get("cefr_level"):
                lines.append(f"CEFR daraja: {html.escape(official['cefr_level'])}")
        elif sub.score_display:
            lines.append(f"Ball: {html.escape(sub.score_display)}")
        if sub.feedback:
            lines.append(f"Ustoz izohi: {html.escape(sub.feedback[:500])}")
        return Card("\n".join(lines), _open_buttons("/my-homework"))

    if msg.event == Event.HOMEWORK_REVIEW:
        if status not in (HomeworkSubmission.Status.AWAITING_REVIEW, HomeworkSubmission.Status.GRADING_FAILED):
            return None
        who = html.escape(sub.student.get_full_name() or "O'quvchi")
        head = "📝 <b>Tekshiruv kutilmoqda</b>" if status == HomeworkSubmission.Status.AWAITING_REVIEW else "⚠️ <b>Natija hisoblanmadi</b>"
        return Card(f"{head}\n\n{title}\n{who}", _open_buttons("/teacher"))

    return None


def enqueue_essay_appeal_submitted(submission, reviewer) -> bool:
    """Queue teacher notification in the same transaction as the student appeal."""
    if not reviewer:
        return False
    req_at = getattr(submission, "teacher_review_requested_at", None)
    stamp = int(req_at.timestamp()) if req_at else "initial"
    return bool(
        enqueue(
            reviewer,
            Event.ESSAY_APPEAL,
            f"essay_appeal:{submission.id}:{reviewer.id}:{stamp}",
            {"submission_id": submission.id},
        )
    )


def enqueue_essay_reviewed(submission, review) -> bool:
    """Queue student notification in the same transaction as the finalized review."""
    student = getattr(submission, "student", None)
    if not student:
        return False
    return bool(
        enqueue(
            student,
            Event.ESSAY_REVIEWED,
            f"essay_reviewed:{submission.id}:{review.id}",
            {"submission_id": submission.id, "review_id": review.id},
        )
    )


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------

Sender = Callable[[int, Card], str]


def telegram_sender(chat_id: int, card: Card) -> str:
    """Default sender. Returns the Telegram message id or raises."""
    from apps.notifications.services.telegram_service import TelegramService

    res = TelegramService.send_message_with_keyboard(
        chat_id=chat_id, text=card.text, buttons=card.buttons or None, parse_mode="HTML"
    )
    if not res.get("success"):
        raise RuntimeError(str(res.get("error") or "telegram error")[:300])
    return str(res.get("message_id") or "")


def claim_batch(worker_id: str, limit: int = 50, now: datetime | None = None) -> list[int]:
    """Lease up to ``limit`` due rows for ``worker_id``; returns their ids."""
    now = now or timezone.now()
    from django.db.models import Q

    due = Q(status=OutboxMessage.Status.PENDING, next_attempt_at__lte=now) | Q(
        status=OutboxMessage.Status.LEASED, lease_expires_at__lt=now
    )
    with transaction.atomic():
        qs = OutboxMessage.objects.filter(due).order_by("next_attempt_at", "id")
        if connection.features.has_select_for_update_skip_locked:
            qs = qs.select_for_update(skip_locked=True)
        ids = list(qs.values_list("id", flat=True)[:limit])
        OutboxMessage.objects.filter(id__in=ids).update(
            status=OutboxMessage.Status.LEASED,
            lease_owner=worker_id,
            lease_expires_at=now + timedelta(seconds=LEASE_SECONDS),
        )
    return ids


def _finish(msg_id: int, worker_id: str, **fields) -> bool:
    """Fenced update: only the current lease owner may complete the row."""
    return bool(
        OutboxMessage.objects.filter(id=msg_id, lease_owner=worker_id, status=OutboxMessage.Status.LEASED).update(
            lease_owner="", lease_expires_at=None, **fields
        )
    )


def deliver(msg_id: int, worker_id: str, sender: Sender = telegram_sender, now: datetime | None = None) -> str:
    """Deliver one leased row. Returns the resulting status."""
    now = now or timezone.now()
    msg = OutboxMessage.objects.select_related("recipient").filter(id=msg_id, lease_owner=worker_id).first()
    if msg is None or msg.status != OutboxMessage.Status.LEASED:
        return "not_owner"
    user = msg.recipient
    pref = _preference(user)

    if not user.is_active or not pref.telegram_enabled or not getattr(pref, _PREF_FIELD.get(msg.event, "test_result_alerts"), True):
        _finish(msg.id, worker_id, status=OutboxMessage.Status.SUPPRESSED, last_error="preference")
        return OutboxMessage.Status.SUPPRESSED
    chat_id = getattr(user, "telegram_chat_id", None)
    if not chat_id:
        _finish(msg.id, worker_id, status=OutboxMessage.Status.SUPPRESSED, last_error="no_telegram")
        return OutboxMessage.Status.SUPPRESSED

    quiet_end = quiet_hours_end(pref, now)
    if quiet_end is not None:
        _finish(msg.id, worker_id, status=OutboxMessage.Status.PENDING, next_attempt_at=quiet_end)
        return "deferred_quiet_hours"
    if _rate_limited(user, now):
        _finish(msg.id, worker_id, status=OutboxMessage.Status.PENDING, next_attempt_at=now + timedelta(minutes=1))
        return "deferred_rate_limit"

    card = render(msg)
    if card is None:
        _finish(msg.id, worker_id, status=OutboxMessage.Status.SUPPRESSED, last_error="stale")
        return OutboxMessage.Status.SUPPRESSED

    attempts = msg.attempts + 1
    try:
        external_id = sender(int(chat_id), card)
    except Exception as exc:  # network, Telegram API, blocked bot …
        logger.warning("Outbox %s delivery failed (attempt %s): %s", msg.id, attempts, exc)
        if attempts >= msg.max_attempts:
            _finish(msg.id, worker_id, status=OutboxMessage.Status.DEAD, attempts=attempts, last_error=str(exc)[:500])
            return OutboxMessage.Status.DEAD
        backoff = BACKOFF_BASE_SECONDS * (2 ** (attempts - 1))
        _finish(
            msg.id,
            worker_id,
            status=OutboxMessage.Status.PENDING,
            attempts=attempts,
            last_error=str(exc)[:500],
            next_attempt_at=now + timedelta(seconds=backoff),
        )
        return OutboxMessage.Status.PENDING
    _finish(
        msg.id,
        worker_id,
        status=OutboxMessage.Status.SENT,
        attempts=attempts,
        sent_at=now,
        external_id=external_id[:100],
        last_error="",
    )
    return OutboxMessage.Status.SENT


def process_batch(limit: int = 50, sender: Sender = telegram_sender, now: datetime | None = None) -> dict[str, int]:
    worker_id = uuid.uuid4().hex
    stats: dict[str, int] = {}
    for msg_id in claim_batch(worker_id, limit, now):
        outcome = deliver(msg_id, worker_id, sender, now)
        stats[outcome] = stats.get(outcome, 0) + 1
    return stats


def outbox_enabled() -> bool:
    return bool(getattr(settings, "NOTIFICATION_OUTBOX_ENABLED", False))


__all__ = [
    "Card",
    "claim_batch",
    "deliver",
    "enqueue",
    "enqueue_deadline_reminders",
    "enqueue_essay_appeal_submitted",
    "enqueue_essay_reviewed",
    "enqueue_group_welcome",
    "enqueue_homework_assigned",
    "enqueue_homework_outcome",
    "enqueue_join_request_reviewed",
    "enqueue_join_request_submitted",
    "outbox_enabled",
    "process_batch",
    "quiet_hours_end",
    "render",
]
