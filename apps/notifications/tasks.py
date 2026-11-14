"""
Celery tasks — asinxron vazifalar.

Lifecycle:
    1. process_test_result_task — test yakunlangandan keyin PDF + Telegram
    2. generate_certificate_task — faqat PDF generatsiya
    3. send_telegram_result_task — faqat Telegram xabar yuborish

Har bir taskda xatolik yuz bersa, task retry qiladi (max 3 marta).
Task bajarilishi NotificationLog da qayd etiladi.
"""

from __future__ import annotations

import logging
from typing import Any

from celery import shared_task

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. Main orchestrator task
# ---------------------------------------------------------------------------


@shared_task(
    bind=True,
    name="notifications.process_test_result",
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
    retry_backoff=True,  # 30s → 60s → 120s … (exponential + jitter)
    retry_backoff_max=300,
    retry_jitter=True,
    time_limit=300,  # PDF gen + Telegram + email can exceed the 120s global
    soft_time_limit=240,
)
def process_test_result_task(
    self: Any,
    result_id: int,
) -> dict[str, Any]:
    """
    Test natijasini qayta ishlash — PDF + Telegram.

    Bu task SubmitAttemptService dan keyin async ravishda chaqiriladi.
    Ketma-ketlik:
        1. Agar o'tgan bo'lsa → Certificate yaratish + PDF generatsiya
        2. Telegram xabar yuborish (natija)
        3. Agar sertifikat bo'lsa → Telegram ga PDF yuborish

    Args:
        result_id: Result model ID.

    Returns:
        {"status": "completed", "certificate_generated": bool, ...}
    """
    try:
        from apps.results.models import Result

        result = Result.objects.select_related(
            "student",
            "test",
            "course",
            "attempt",
        ).get(id=result_id)

        logger.info(
            "Processing result: id=%d, student=%s, passed=%s",
            result_id,
            result.student.email,
            result.is_passed,
        )

        certificate_generated = False

        # -- Step 1: Certificate generatsiya (o'tgan bo'lsa) ----------------
        if result.is_passed:
            certificate_generated = _generate_certificate(result)

        # -- Step 2: Telegram xabar yuborish --------------------------------
        _send_telegram_result(result, certificate_generated)

        # -- Step 3: Email xabar yuborish ------------------------------------
        _send_email_result(result)

        # -- Step 4: Ota-onaga tezkor xabar yuborish -------------------------
        try:
            from apps.notifications.tasks_parent import send_parent_test_alert_task

            send_parent_test_alert_task.delay(result_id)
        except Exception:
            logger.exception("Parent alert dispatch error for result_id=%s", result_id)

        # -- Step 5: Guruhga avtomatik natija va PDF vedomost yuborish ------
        try:
            _send_group_result_and_vedomost(result)
        except Exception:
            logger.exception("Group result broadcasting error for result_id=%s", result_id)

        return {
            "status": "completed",
            "result_id": result_id,
            "certificate_generated": certificate_generated,
        }

    except Result.DoesNotExist as exc:
        logger.warning("Result not visible yet: id=%d; retrying", result_id)
        raise self.retry(exc=exc)

    except Exception as exc:
        logger.exception("Task failed: result_id=%d", result_id)
        raise self.retry(exc=exc)


# ---------------------------------------------------------------------------
# 2. Certificate generation task
# ---------------------------------------------------------------------------


@shared_task(
    bind=True,
    name="notifications.generate_certificate",
    max_retries=3,
    default_retry_delay=30,
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    time_limit=300,
    soft_time_limit=240,
)
def generate_certificate_task(
    self: Any,
    result_id: int,
) -> dict[str, Any]:
    """
    PDF sertifikat generatsiya qilish (mustaqil task).

    Agar Certificate allaqachon mavjud bo'lsa, qayta yaratmaydi.
    """
    try:
        from apps.results.models import Result

        result = Result.objects.select_related(
            "student",
            "test",
            "course",
        ).get(id=result_id)

        success = _generate_certificate(result)
        return {"status": "completed", "success": success}

    except Exception as exc:
        logger.exception("Certificate generation failed: result_id=%d", result_id)
        raise self.retry(exc=exc)


# ---------------------------------------------------------------------------
# 3. Telegram notification task
# ---------------------------------------------------------------------------


@shared_task(
    bind=True,
    name="notifications.send_telegram_result",
    max_retries=3,
    default_retry_delay=30,
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    time_limit=120,
    soft_time_limit=90,
)
def send_telegram_result_task(
    self: Any,
    result_id: int,
) -> dict[str, Any]:
    """
    Telegram xabar yuborish (mustaqil task).
    """
    try:
        from apps.results.models import Result

        result = Result.objects.select_related(
            "student",
            "test",
            "course",
        ).get(id=result_id)

        _send_telegram_result(result, certificate_sent=False)
        return {"status": "completed"}

    except Exception as exc:
        logger.exception("Telegram send failed: result_id=%d", result_id)
        raise self.retry(exc=exc)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _generate_certificate(result: Any) -> bool:
    """
    Certificate yaratish + PDF generatsiya (thin wrapper over canonical service).

    1. Certificate model yaratish (agar mavjud bo'lmasa).
    2. PDF generatsiya qilish (ReportLab).
    3. PDF faylni Certificate.file ga saqlash.
    4. Status ni GENERATED ga o'zgartirish.

    Returns:
        True agar muvaffaqiyatli yaratilgan bo'lsa.
    """
    from apps.certificates.services.generation import generate_certificate as _gen

    try:
        _gen(result)
        return True
    except Exception:
        from apps.results.models import Certificate

        try:
            cert = Certificate.objects.get(result=result)
            cert.status = Certificate.Status.FAILED
            cert.save(update_fields=["status"])
        except Certificate.DoesNotExist:
            pass
        logger.exception(
            "PDF generation failed for cert result=%s", getattr(result, "id", "?")
        )
        return False


def _send_telegram_result(
    result: Any,
    certificate_sent: bool = False,
) -> None:
    """
    Telegram orqali test natijasini yuborish.

    Agar foydalanuvchining telegram_chat_id bo'lsa, xabar yuboriladi.
    Bo'lmasa, faqat log yoziladi.
    """
    from apps.notifications.services.telegram_service import TelegramService

    student = result.student

    # Telegram chat ID mavjudmi?
    if not student.telegram_chat_id or not student.telegram_identity_verified_at:
        logger.info(
            "Student has no telegram_chat_id: %s — skipping notification",
            student.email,
        )
        return

    # Natija xabarini yuborish
    TelegramService.send_test_result(
        chat_id=student.telegram_chat_id,
        student_name=student.get_full_name(),
        test_title=result.test.title,
        percentage=float(result.percentage),
        is_passed=result.is_passed,
        score=str(result.score),
        max_score=str(result.max_score),
        recipient=student,
        attempt=result.attempt,
    )

    # Agar sertifikat yaratilgan bo'lsa, PDF ni ham yuborish
    if certificate_sent and result.is_passed:
        try:
            from apps.results.models import Certificate

            cert = Certificate.objects.get(result=result)
            if cert.file:
                TelegramService.send_certificate(
                    chat_id=student.telegram_chat_id,
                    student_name=student.get_full_name(),
                    certificate_number=cert.certificate_number,
                    course_title=result.course.title,
                    pdf_file_path=cert.file.path if cert.file else None,
                    recipient=student,
                    certificate=cert,
                )
        except Certificate.DoesNotExist:
            logger.warning("Certificate not found for result: %d", result.id)


def _send_email_result(result: Any) -> None:
    """
    Email orqali test natijasini yuborish.
    """
    from apps.notifications.services.email_service import EmailService

    student = result.student

    try:
        EmailService.send_test_result(
            to_email=student.email,
            student_name=student.get_full_name(),
            test_title=result.test.title,
            percentage=float(result.percentage),
            is_passed=result.is_passed,
            score=str(result.score),
            max_score=str(result.max_score),
            recipient=student,
            attempt=result.attempt,
        )
    except Exception as e:
        logger.error("Email send failed for result %d: %s", result.id, e)


def _ensure_telegram_service_helpers() -> None:
    """Ensure TelegramService exposes send_document and _call_api for callers and mocks."""
    from apps.notifications.services.telegram_service import TelegramService

    if not hasattr(TelegramService, "send_document"):
        @classmethod  # type: ignore[misc]
        def _ts_send_document(
            cls,
            chat_id: int,
            file_path: str,
            caption: str = "",
            recipient: Any = None,
            certificate: Any = None,
            parse_mode: str = "HTML",
        ) -> dict[str, Any]:
            return cls._send_document(
                chat_id=chat_id,
                file_path=file_path,
                caption=caption,
                recipient=recipient,
                certificate=certificate,
                parse_mode=parse_mode,
            )

        TelegramService.send_document = _ts_send_document  # type: ignore[attr-defined]

    if not hasattr(TelegramService, "_call_api"):
        @classmethod  # type: ignore[misc]
        def _ts_call_api(
            cls,
            method: str,
            payload: dict[str, Any] | None = None,
            **kwargs: Any,
        ) -> dict[str, Any]:
            data = dict(payload or {})
            data.update(kwargs)
            if method == "sendMessage":
                return cls.send_message(
                    chat_id=int(data.get("chat_id")),
                    text=str(data.get("text", "")),
                    parse_mode=str(data.get("parse_mode", "HTML")),
                    recipient=data.get("recipient"),
                    title=str(data.get("title", "Xabar")),
                )
            return {"ok": False, "success": False, "error": f"Unsupported method: {method}"}

        TelegramService._call_api = _ts_call_api  # type: ignore[attr-defined]


_ensure_telegram_service_helpers()


def _get_student_linked_groups(student: Any, assigned_group: Any = None) -> list[Any]:
    """
    Collect all active StudentGroup records linked to a Telegram group (telegram_chat_id != None)
    for the given student, deduplicated by group.id.
    """
    from apps.courses.models import StudentGroup

    if not student:
        return []

    groups_by_id: dict[int, Any] = {}

    if assigned_group and getattr(assigned_group, "telegram_chat_id", None):
        if getattr(assigned_group, "is_active", True):
            groups_by_id[assigned_group.id] = assigned_group

    try:
        group_field_names = {f.name for f in StudentGroup._meta.get_fields()}
        qs = student.student_groups.filter(telegram_chat_id__isnull=False)
        if "is_active" in group_field_names:
            qs = qs.filter(is_active=True)
        for grp in qs:
            if grp.telegram_chat_id:
                groups_by_id[grp.id] = grp
    except Exception:
        logger.exception(
            "Error querying student.student_groups for student=%s",
            getattr(student, "id", None),
        )

    try:
        from apps.courses.models import GroupEnrollment

        enroll_qs = GroupEnrollment.objects.filter(
            student=student,
            is_active=True,
            group__telegram_chat_id__isnull=False,
        ).select_related("group")
        for enr in enroll_qs:
            grp = enr.group
            if grp and grp.telegram_chat_id and getattr(grp, "is_active", True):
                groups_by_id[grp.id] = grp
    except Exception:
        pass

    return list(groups_by_id.values())


def _extract_test_sections_and_weaknesses(result: Any) -> tuple[str, str]:
    """Extract section score summary and weak question types/sections for a Result."""
    attempt = getattr(result, "attempt", None)
    sec_parts: list[str] = []

    sec_scores = (getattr(attempt, "section_scores", None) if attempt else None) or {}
    if not sec_scores and hasattr(result, "section_scores"):
        try:
            for rss in result.section_scores.all():
                sec_scores[rss.section_code or rss.section_name] = {
                    "earned": float(rss.earned),
                    "maximum": float(rss.maximum),
                    "name": rss.section_name or rss.section_code,
                }
        except Exception:
            pass

    if isinstance(sec_scores, dict) and sec_scores:
        for code, details in sec_scores.items():
            if isinstance(details, dict):
                earned = float(details.get("earned", 0))
                maximum = float(details.get("maximum", 0))
                name = details.get("name", code)
                sec_parts.append(f"{name}: {earned:g}/{maximum:g}")
            else:
                sec_parts.append(f"{code}: {details}")

    weak_areas: list[str] = []
    if attempt and hasattr(attempt, "answers"):
        try:
            wrong_qs = attempt.answers.filter(is_correct=False).select_related(
                "question", "question__section"
            )[:10]
            for ans in wrong_qs:
                q = getattr(ans, "question", None)
                if not q:
                    continue
                label = (
                    (q.section.name if getattr(q, "section", None) else "")
                    or (q.get_question_type_display() if hasattr(q, "get_question_type_display") else "")
                    or str(getattr(q, "question_type", ""))
                )
                if label and label not in weak_areas:
                    weak_areas.append(label)
        except Exception:
            pass

    if not weak_areas:
        if getattr(result, "wrong_answers", 0) == 0 and float(getattr(result, "percentage", 0) or 0) >= 95:
            weak_str = "Xatolar yo'q (100% aniqlik)"
        elif getattr(result, "is_passed", False):
            weak_str = "Murakkab matn tahlili savollari"
        else:
            weak_str = "Asosiy bo'lim savollari ustida ishlash tavsiya etiladi"
    else:
        weak_str = ", ".join(weak_areas[:3])

    return (" | ".join(sec_parts), weak_str)


def _send_group_result_and_vedomost(result: Any) -> None:
    """Retire the unsafe group broadcast; the orchestrator sends privately.

    Keep this entry point for existing callers. Group membership is not consent
    to disclose individual scores, weaknesses or reports to every chat member.
    No report is generated here, including for already queued work.
    """
    logger.info("Group result disclosure blocked: result_id=%s", result.id)


@shared_task(name="notifications.broadcast_essay_result_to_groups")
def broadcast_essay_result_to_groups(submission_or_id: Any) -> dict[str, Any]:
    """Safely consume legacy jobs; private essay delivery is handled separately."""
    return {"status": "skipped", "reason": "private_results_only", "sent_groups": 0}


@shared_task(name="notifications.broadcast_speaking_result_to_groups")
def broadcast_speaking_result_to_groups(submission_or_id: Any) -> dict[str, Any]:
    """Safely consume legacy jobs without disclosing speaking reports to groups.

    Students can still retrieve their persisted assessment through the protected
    speaking page. A reliable private notification is tracked as follow-up work.
    """
    return {"status": "skipped", "reason": "private_results_only", "sent_groups": 0}


@shared_task(name="notifications.send_daily_onboarding_reminders")
def send_daily_onboarding_reminders(slot: str = "evening") -> dict[str, Any]:
    """
    Har kuni belgilangan vaqtda (morning / afternoon / evening) onboardingdan o'tgan
    va Telegram hisobini ulagan o'quvchilarga kunlik shaxsiy mashg'ulot eslatmasini yuborish.
    """
    from apps.accounts.models import Profile, User as CustomUser
    from apps.notifications.services.telegram_service import TelegramService

    _ensure_telegram_service_helpers()

    profile_fields = {f.name for f in Profile._meta.get_fields()}
    base_qs = CustomUser.objects.filter(
        is_active=True,
        telegram_chat_id__isnull=False,
        profile__onboarding_completed=True,
    ).select_related("profile")

    if "reminder_slot" in profile_fields:
        users = list(base_qs.filter(profile__reminder_slot=slot))
    else:
        users = [
            u
            for u in base_qs
            if (
                getattr(u.profile, "reminder_slot", None) == slot
                or (getattr(u.profile, "daily_plan_summary", None) or {}).get(
                    "reminder_slot", "evening"
                )
                == slot
            )
        ]

    slot_greetings = {
        "morning": "☀️ Xayrli tong",
        "afternoon": "🌤 Xayrli kun",
        "evening": "🌙 Xayrli kech",
    }
    greeting = slot_greetings.get(slot, "👋 Salom")

    sent_count = 0
    for user in users:
        profile = getattr(user, "profile", None)
        goal_mins = (
            getattr(profile, "daily_goal_minutes", None)
            or (getattr(profile, "daily_plan_summary", None) or {}).get(
                "daily_goal_minutes"
            )
            or 30
        )
        target_grade = getattr(profile, "target_grade", "A+") or "A+"
        streak = getattr(profile, "current_streak", 0) or 0
        full_name = user.get_full_name() or user.email

        text = (
            f"{greeting}, <b>{_html(full_name)}</b>! 🚀\n\n"
            f"🎯 <b>Kunlik maqsadingiz:</b> <b>{goal_mins} daqiqa</b> shug'ullanish (Maqsad: <b>{_html(target_grade)}</b>)\n"
            f"🔥 <b>Joriy streak:</b> {streak} kun\n\n"
            f"Bugungi shaxsiy o'quv rejangiz sizni kutmoqda. Streak uzilib qolmasligi uchun hoziroq mashqni boshlang!\n\n"
            f"👉 <a href=\"https://grandec.uz/dashboard\">Mashg'ulotni boshlash (grandec.uz/dashboard)</a>"
        )
        try:
            TelegramService._call_api(
                "sendMessage",
                {
                    "chat_id": user.telegram_chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "recipient": user,
                    "title": "Kunlik o'quv rejasi eslatmasi",
                },
            )
            sent_count += 1
        except Exception as exc:
            logger.warning(
                "Daily onboarding reminder failed for user=%s: %s", user.id, exc
            )

    return {"status": "ok", "slot": slot, "sent_count": sent_count}


send_daily_onboarding_reminders_task = send_daily_onboarding_reminders


# Import parent notification tasks so Celery discovers them
from apps.notifications import tasks_parent  # noqa: F401


# ---------------------------------------------------------------------------
# Feedback: admin alert and reply delivery (Celery, never inside the request)
# ---------------------------------------------------------------------------


def _html(value: object) -> str:
    from django.utils.html import escape

    return escape(str(value or ""))


@shared_task(
    bind=True,
    name="notifications.notify_admin_new_feedback",
    max_retries=3,
    default_retry_delay=30,
    retry_backoff=True,
    time_limit=60,
)
def notify_admin_new_feedback(self: Any, feedback_id: int) -> dict[str, Any]:
    """Telegram alert for a new feedback. User text is HTML-escaped; no phone/e-mail."""
    from django.conf import settings

    from apps.notifications.models import UserFeedback
    from apps.notifications.services.telegram_service import TelegramService

    fb = UserFeedback.objects.filter(pk=feedback_id).first()
    admin_id = getattr(settings, "ADMIN_TELEGRAM_ID", None)
    if fb is None or not admin_id:
        return {"status": "skipped"}
    urgent = fb.category == UserFeedback.Category.BUG or fb.rating <= 2
    ctx = fb.context or {}
    text = (
        f"{'🚨' if urgent else '📬'} <b>Yangi fikr #{fb.pk}</b>\n"
        f"🏷 {_html(dict(UserFeedback.Category.choices).get(fb.category, fb.category))}"
        f" · {'⭐' * fb.rating} ({fb.rating}/5)\n"
        f"👤 {_html(fb.short_name or 'Mehmon')} [{_html(ctx.get('role', ''))}/{_html(ctx.get('plan', ''))}]\n"
        f"📍 {_html(ctx.get('path', '-'))}\n\n"
        f"<i>{_html(fb.message[:700])}</i>"
    )
    buttons = []
    if fb.consent_public:
        buttons = [[
            {"text": "✅ Saytda chiqarish", "callback_data": f"publish_feedback_{fb.pk}"},
            {"text": "❌ Rad etish", "callback_data": f"reject_feedback_{fb.pk}"},
        ]]
    try:
        TelegramService.send_message_with_keyboard(
            chat_id=int(admin_id), text=text, buttons=buttons or None, parse_mode="HTML"
        )
    except Exception as exc:
        logger.warning("Feedback #%s admin alert failed: %s", feedback_id, exc)
        raise self.retry(exc=exc)
    return {"status": "sent", "urgent": urgent}


@shared_task(
    bind=True,
    name="notifications.notify_admin_question_needs_review",
    max_retries=3,
    default_retry_delay=30,
    retry_backoff=True,
    time_limit=60,
)
def notify_admin_question_needs_review(self: Any, question_id: int) -> dict[str, Any]:
    """
    ONE Telegram summary when a question collects enough reports to need review
    (not one message per report). Contains the reasons breakdown and a link to
    the question editor; no answer key and no reporter names.
    """
    from django.conf import settings
    from django.db.models import Count

    from apps.notifications.models import UserFeedback
    from apps.notifications.services.telegram_service import TelegramService
    from apps.tests.models import Question

    question = Question.objects.filter(pk=question_id).select_related("test").first()
    admin_id = getattr(settings, "ADMIN_TELEGRAM_ID", None)
    if question is None or not admin_id:
        return {"status": "skipped"}
    active = UserFeedback.objects.filter(
        question=question,
        category=UserFeedback.Category.QUESTION_ISSUE,
        status__in=(UserFeedback.Status.NEW, UserFeedback.Status.SEEN, UserFeedback.Status.IN_PROGRESS),
    )
    labels = dict(UserFeedback.IssueReason.choices)
    breakdown = ", ".join(
        f"{_html(labels.get(r['reason'], r['reason']))}: {r['n']}"
        for r in active.values("reason").annotate(n=Count("id")).order_by("-n")
    )
    link = f"{str(getattr(settings, 'SITE_URL', '')).rstrip('/')}/panel/tests/{question.test_id}/questions"
    text = (
        f"⚠️ <b>Savol ko'rib chiqilsin</b>\n"
        f"📝 {_html(question.test.title)}\n"
        f"❓ {_html(question.text[:160])}\n"
        f"📣 {active.count()} ta faol shikoyat\n"
        f"🏷 {breakdown}\n"
        f"🔗 {_html(link)}"
    )
    try:
        TelegramService.send_message(chat_id=int(admin_id), text=text, parse_mode="HTML")
    except Exception as exc:
        logger.warning("Question #%s review summary failed: %s", question_id, exc)
        raise self.retry(exc=exc)
    return {"status": "sent", "reports": active.count()}


@shared_task(
    bind=True,
    name="notifications.send_feedback_reply",
    max_retries=3,
    default_retry_delay=30,
    retry_backoff=True,
    time_limit=60,
)
def send_feedback_reply(self: Any, feedback_id: int) -> dict[str, Any]:
    """Deliver the admin's reply to the author in the bot, if the account is linked."""
    from apps.notifications.models import UserFeedback
    from apps.notifications.services.telegram_service import TelegramService

    fb = UserFeedback.objects.select_related("user").filter(pk=feedback_id).first()
    chat_id = getattr(getattr(fb, "user", None), "telegram_chat_id", None) if fb else None
    if fb is None or not chat_id or not fb.admin_reply:
        return {"status": "skipped"}
    text = (
        f"💬 <b>Fikringizga javob</b>\n\n"
        f"<i>{_html(fb.message[:300])}</i>\n\n"
        f"{_html(fb.admin_reply)}"
    )
    try:
        TelegramService.send_message(chat_id=int(chat_id), text=text, parse_mode="HTML", recipient=fb.user)
    except Exception as exc:
        logger.warning("Feedback #%s reply delivery failed: %s", feedback_id, exc)
        raise self.retry(exc=exc)
    return {"status": "sent"}
