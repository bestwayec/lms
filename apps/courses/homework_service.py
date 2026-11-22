"""
Unified Homework Engine Service (Stage 4):
- Unified assignment architecture covering Tests, Essays, Vocabulary, Lessons, and Custom tasks
- Atomic homework creation, idempotency, and tenant authorization
- Safe cancellation preserving all submissions, test attempts, results, and audit trails
- Student homework lifecycle: List, Detail, Start/Resume, Autosave, Submit, and Result
- Authoritative status derivation (NOT_STARTED, IN_PROGRESS, SUBMITTED, AWAITING_REVIEW, GRADED, OVERDUE, CANCELLED)
- Robust score vs pending review differentiation (score 0 is GRADED, not pending)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from apps.accounts.access import is_platform_admin
from apps.courses.models import Homework, HomeworkSubmission, Lesson, StudentGroup
from apps.courses.teacher_workspace_service import get_teacher_groups
from apps.essays.models import EssaySubmission, EssayTopic
from apps.results.models import Result
from apps.tests.models import Test, TestAttempt

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. Teacher Assignment Creation & Cancellation
# ---------------------------------------------------------------------------


@transaction.atomic
def create_unified_homework(
    user,
    *,
    title: str,
    due_date: datetime,
    group_id: int | None = None,
    student_id: int | None = None,
    content_type: str | None = None,
    description: str = "",
    test_id: int | None = None,
    essay_topic_id: int | None = None,
    vocabulary_pack_id: int | None = None,
    lesson_id: int | None = None,
    start_date: datetime | None = None,
    time_limit: int = 0,
    max_attempts: int = 1,
    idempotency_key: str | None = None,
) -> tuple[Homework, bool]:
    """
    Create a unified homework assignment with strict authorization,
    transactional atomicity, and duplicate protection.
    """
    # 1. Idempotency check — keys are namespaced per creator so one teacher's
    # key can never return (or block) another teacher's homework.
    stored_key = _namespaced_idempotency_key(user, idempotency_key)
    if stored_key:
        existing = Homework.objects.filter(
            idempotency_key=stored_key, created_by=user
        ).first()
        if existing:
            return existing, False

    # 2. Title & Deadline validation
    clean_title = (title or "").strip()
    if not clean_title:
        raise ValueError("Vazifa sarlavhasi talab qilinadi.")

    if timezone.is_naive(due_date):
        due_date = timezone.make_aware(
            due_date, timezone.get_current_timezone()
        )

    if due_date <= timezone.now():
        raise ValueError("Topshirish muddati (deadline) kelajakda bo'lishi kerak.")

    if start_date and timezone.is_naive(start_date):
        start_date = timezone.make_aware(
            start_date, timezone.get_current_timezone()
        )
    if start_date and start_date >= due_date:
        raise ValueError("Boshlanish vaqti topshirish muddatidan oldin bo'lishi kerak.")

    try:
        time_limit = int(time_limit or 0)
        max_attempts = int(max_attempts or 1)
    except (TypeError, ValueError):
        raise ValueError("Vaqt chegarasi va urinishlar soni butun son bo'lishi kerak.")
    if time_limit < 0 or time_limit > 24 * 60:
        raise ValueError("Vaqt chegarasi 0–1440 daqiqa oralig'ida bo'lishi kerak.")
    if max_attempts < 1 or max_attempts > 20:
        raise ValueError("Urinishlar soni 1–20 oralig'ida bo'lishi kerak.")

    # 3. Recipient validation (Group or Individual Student)
    group = None
    target_student = None

    if not group_id and not student_id:
        raise ValueError("Guruh yoki alohida o'quvchi tanlanishi shart.")

    if group_id:
        group = get_teacher_groups(user).filter(id=group_id).first()
        if not group:
            raise PermissionError("Guruh topilmadi yoki sizga biriktirilmagan.")

    if student_id:
        from apps.accounts.models import User

        target_student = User.objects.filter(id=student_id, is_active=True).first()
        if not target_student or getattr(target_student, "role", "") != "student":
            raise ValueError("O'quvchi topilmadi.")
        if group and not group.students.filter(id=target_student.id).exists():
            raise PermissionError("O'quvchi tanlangan guruh a'zosi emas.")

        # Ensure student is authorized (in teacher's group or accessible to center/platform admin)
        if not is_platform_admin(user):
            teacher_groups_qs = get_teacher_groups(user)
            student_accessible = teacher_groups_qs.filter(
                students=target_student
            ).exists()
            if not student_accessible:
                raise PermissionError("Ushbu o'quvchiga kirish huquqingiz yo'q.")

    # 4. Content Validation & Authorization
    test = None
    topic = None
    vocab_pack = None
    lesson = None

    if not content_type:
        if test_id:
            content_type = Homework.ContentType.TEST
        elif essay_topic_id:
            content_type = Homework.ContentType.ESSAY
        elif vocabulary_pack_id:
            content_type = Homework.ContentType.VOCABULARY
        elif lesson_id:
            content_type = Homework.ContentType.LESSON
        else:
            content_type = Homework.ContentType.CUSTOM

    if content_type == Homework.ContentType.TEST or test_id:
        if not test_id:
            raise ValueError("Test topshirig'i uchun test_id talab qilinadi.")
        test = Test.objects.filter(id=test_id).first()
        if not test:
            raise ValueError("Biriktirilgan test topilmadi.")

        # B. Test authorization: must be published
        if test.status != Test.Status.PUBLISHED:
            raise ValueError(
                "Faqat e'lon qilingan (PUBLISHED) testlarni vazifa qilib berish mumkin."
            )

        # B. Ownership check: cannot attach another teacher's private test
        if not is_platform_admin(user):
            is_owner = (
                getattr(test, "created_by_id", None) == user.id
                or getattr(
                    getattr(test, "course", None), "teacher_id", None
                )
                == user.id
            )
            is_official = (
                getattr(test, "is_official", False)
                or getattr(test, "access_type", "") == "PUBLIC"
            )
            if not is_owner and not is_official:
                raise PermissionError(
                    "Boshqa o'qituvchining yopiq testini vazifa qilib biriktirish taqiqlanadi."
                )

        # The test row is shared content (official tests are used by every
        # center); assigning it must not mutate it.  Access for recipients is
        # granted through the Homework row (see tests.studio_service
        # .student_has_assignment and tests.visibility.member_q).
        content_type = Homework.ContentType.TEST

    elif content_type == Homework.ContentType.ESSAY or essay_topic_id:
        if not essay_topic_id:
            raise ValueError("Esse topshirig'i uchun essay_topic_id talab qilinadi.")
        topic = EssayTopic.objects.filter(id=essay_topic_id, is_active=True).first()
        if not topic:
            raise ValueError("Biriktirilgan esse mavzusi topilmadi.")
        if not can_assign_essay_topic(user, topic):
            raise PermissionError("Ushbu esse mavzusini vazifa qilib berish huquqingiz yo'q.")

        if group:
            from apps.essays.group_reports import (
                create_assignment as create_essay_assignment,
            )

            create_essay_assignment(
                topic=topic,
                group=group,
                assigned_by=user,
                due_at=due_date,
                instructions=description,
                actor=user,
            )
        content_type = Homework.ContentType.ESSAY

    elif content_type == Homework.ContentType.VOCABULARY or vocabulary_pack_id:
        from apps.vocabulary.models import VocabularyPack

        if not vocabulary_pack_id:
            raise ValueError("Lug'at topshirig'i uchun vocabulary_pack_id talab qilinadi.")
        vocab_pack = VocabularyPack.objects.filter(id=vocabulary_pack_id).first()
        if not vocab_pack:
            raise ValueError("Biriktirilgan lug'at to'plami topilmadi.")
        if not can_assign_vocabulary_pack(user, vocab_pack):
            raise PermissionError("Ushbu lug'at to'plamini vazifa qilib berish huquqingiz yo'q.")
        content_type = Homework.ContentType.VOCABULARY

    elif content_type == Homework.ContentType.LESSON or lesson_id:
        if not lesson_id:
            raise ValueError("Dars topshirig'i uchun lesson_id talab qilinadi.")
        lesson = Lesson.objects.filter(id=lesson_id).select_related("module__course").first()
        if not lesson:
            raise ValueError("Biriktirilgan dars topilmadi.")
        if not can_assign_lesson(user, lesson):
            raise PermissionError("Ushbu darsni vazifa qilib berish huquqingiz yo'q.")
        content_type = Homework.ContentType.LESSON

    else:
        content_type = Homework.ContentType.CUSTOM

    # 5. Create the unified homework record atomically.  A concurrent request
    # with the same idempotency key loses the unique-constraint race; return
    # the winner instead of a 500.
    fields = dict(
        group=group,
        student=target_student,
        content_type=content_type,
        title=clean_title[:200],
        description=description.strip(),
        test=test,
        essay_topic=topic,
        vocabulary_pack=vocab_pack,
        lesson=lesson,
        start_date=start_date,
        due_date=due_date,
        time_limit=time_limit,
        max_attempts=max_attempts,
        status=Homework.Status.ACTIVE,
        idempotency_key=stored_key,
        created_by=user,
    )
    if stored_key:
        try:
            with transaction.atomic():
                hw = Homework.objects.create(**fields)
        except IntegrityError:
            existing = Homework.objects.filter(
                idempotency_key=stored_key, created_by=user
            ).first()
            if existing:
                return existing, False
            raise
    else:
        hw = Homework.objects.create(**fields)

    from apps.notifications.outbox import enqueue_homework_assigned

    enqueue_homework_assigned(hw)  # same transaction: rolled back together
    return hw, True


def _namespaced_idempotency_key(user, key: str | None) -> str | None:
    key = (key or "").strip()
    if not key:
        return None
    return f"u{user.pk}:{key}"[:120]


def can_assign_essay_topic(user, topic) -> bool:
    """Platform topics (no author / admin author) or the teacher's own topics."""
    if is_platform_admin(user):
        return True
    author = getattr(topic, "created_by", None)
    if author is None:
        return not (getattr(topic, "password", "") or "").strip()
    if author.pk == user.pk:
        return True
    return is_platform_admin(author) and not (getattr(topic, "password", "") or "").strip()


def can_assign_vocabulary_pack(user, pack) -> bool:
    """Own packs, or a pack bound to one of the teacher's groups."""
    if is_platform_admin(user):
        return True
    if pack.teacher_id == user.pk:
        return True
    if pack.group_id and get_teacher_groups(user).filter(id=pack.group_id).exists():
        return True
    return False


def can_assign_lesson(user, lesson) -> bool:
    if is_platform_admin(user):
        return True
    module = getattr(lesson, "module", None)
    course = getattr(module, "course", None)
    return bool(course and course.teacher_id == user.pk)


def cancel_teacher_homework(user, homework_id: int) -> Homework:
    """
    Safely cancel a homework:
    - Transitions Homework.status to CANCELLED
    - Preserves all submissions, grades, test attempts, and results (ZERO data deletion)
    - Sets audit metadata (cancelled_at, cancelled_by)
    """
    hw = (
        Homework.objects.select_related("group", "student")
        .filter(id=homework_id)
        .first()
    )
    if not hw:
        raise ValueError("Vazifa topilmadi.")

    if not is_platform_admin(user):
        allowed = False
        if hw.group and hw.group in get_teacher_groups(user):
            allowed = True
        elif hw.created_by_id == user.id:
            allowed = True
        elif hw.student:
            allowed = get_teacher_groups(user).filter(
                students=hw.student
            ).exists()
        if not allowed:
            raise PermissionError("Ushbu vazifani bekor qilishga ruxsatingiz yo'q.")

    if hw.status != Homework.Status.CANCELLED:
        hw.status = Homework.Status.CANCELLED
        hw.cancelled_at = timezone.now()
        hw.cancelled_by = user
        hw.save(
            update_fields=["status", "cancelled_at", "cancelled_by", "updated_at"]
        )

        # Soft-cancel any incomplete submissions while preserving historical completed submissions
        HomeworkSubmission.objects.filter(
            homework=hw, is_completed=False
        ).update(
            status=HomeworkSubmission.Status.CANCELLED,
            updated_at=timezone.now(),
        )

    return hw


# Backward compatibility alias
delete_teacher_homework = cancel_teacher_homework


# ---------------------------------------------------------------------------
# 2. Student Homework Lifecycle
#
# Invariants (each covered by tests/test_homework_integrity.py):
#   * Only a *current* recipient (member of the homework's group, or the
#     individually assigned student) may start, save or submit.  A student
#     removed from the group keeps read access to work they already handed in.
#   * Writes happen only on POST.  Listing and detail never create or link
#     rows; a test result is linked only through the attempt the homework
#     itself started, never through an older Result for the same test.
#   * A score is recorded only from an official persisted ``Result`` whose
#     grading is finished.  Grader exceptions, missing results and missing
#     attempts produce GRADING_FAILED (retryable) — never GRADED with 0.
#   * Start/save/submit respect the assignment window (start_date, due_date),
#     cancellation, the server-side time limit and max_attempts; the
#     submission row is locked so autosave and finish cannot interleave.
# ---------------------------------------------------------------------------

MAX_ANSWERS_PAYLOAD_BYTES = 64 * 1024


class HomeworkNotFound(PermissionError):
    """The homework does not exist or the user is not a recipient (no enumeration)."""


class HomeworkConflict(ValueError):
    """The action is not allowed in the current state (closed, finished, expired)."""

    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.code = code


def _recipient_q(student) -> Q:
    return Q(group__students=student) | Q(student=student)


def _is_current_recipient(hw: Homework, student) -> bool:
    if hw.student_id is not None:
        return hw.student_id == student.pk
    if hw.group_id is None:
        return False
    return hw.group.students.filter(pk=student.pk).exists()


def _readable_homework_ids(student):
    """Homework the student may *see*: current recipient, or already has a submission."""
    current = Homework.objects.filter(_recipient_q(student)).values("id")
    historical = HomeworkSubmission.objects.filter(student=student).values("homework_id")
    return Q(id__in=current) | Q(id__in=historical)


def _lock_homework_for_write(student, homework_id: int) -> Homework:
    """Fetch + row-lock a homework the student currently receives.

    ``SELECT … FOR UPDATE`` cannot be combined with the DISTINCT a M2M join may
    need, so authorization and locking are separate queries on the PK.
    """
    hw = Homework.objects.select_for_update().filter(id=homework_id).first()
    if hw is None or not _is_current_recipient(hw, student):
        raise HomeworkNotFound("Topshiriq topilmadi yoki sizga biriktirilmagan.")
    return hw


def _assert_window_open(hw: Homework, now: datetime) -> None:
    if hw.status == Homework.Status.CANCELLED:
        raise HomeworkConflict("Ushbu topshiriq bekor qilingan.", "cancelled")
    if hw.status != Homework.Status.ACTIVE:
        raise HomeworkConflict("Ushbu topshiriq yopilgan.", "closed")
    if hw.start_date and now < hw.start_date:
        raise HomeworkConflict("Topshiriq hali ochilmagan.", "not_open")
    if hw.due_date and now > hw.due_date:
        raise HomeworkConflict("Topshirish muddati tugagan.", "deadline_passed")


def _uses_own_timer(hw: Homework) -> bool:
    """Tests run on the official attempt timer (Test.time_limit_minutes)."""
    return hw.content_type != Homework.ContentType.TEST


def submission_deadline(hw: Homework, sub: HomeworkSubmission | None) -> datetime | None:
    """Server-side cut-off for this submission: due date, or start + time limit."""
    deadline = hw.due_date
    if sub and sub.started_at and hw.time_limit and _uses_own_timer(hw):
        personal = sub.started_at + timedelta(minutes=hw.time_limit)
        deadline = min(deadline, personal) if deadline else personal
    return deadline


def _official_test_outcome(attempt: TestAttempt | None) -> tuple[str, Result | None]:
    """Read-only view of what the official test pipeline has persisted.

    Returns (state, result) where state is one of
    ``in_progress`` / ``graded`` / ``pending_review`` / ``missing`` / ``cancelled``.
    """
    if attempt is None:
        return "missing", None
    if attempt.status == TestAttempt.Status.IN_PROGRESS:
        return "in_progress", None
    if attempt.status == TestAttempt.Status.CANCELLED:
        return "cancelled", None
    result = Result.objects.filter(attempt=attempt).first()
    if attempt.status == TestAttempt.Status.PENDING_GRADING:
        return "pending_review", result
    if result is None:
        return "missing", None
    if getattr(result, "grading_status", "graded") != "graded":
        return "pending_review", result
    return "graded", result


def _apply_result(sub: HomeworkSubmission, result: Result) -> None:
    sub.result = result
    sub.score = result.score
    sub.max_score = result.max_score
    sub.percentage = float(result.percentage)
    sub.score_display = f"{result.score}/{result.max_score}"
    sub.status = HomeworkSubmission.Status.GRADED
    sub.grading_error = ""


def _sync_test_submission(sub: HomeworkSubmission) -> bool:
    """Copy the official outcome of the linked attempt onto the submission.

    Returns True if the submission row changed.  Only ever *reads* official
    rows; it never invents a score.
    """
    state, result = _official_test_outcome(sub.test_attempt)
    before = (sub.status, sub.result_id, sub.is_completed)
    if state == "graded":
        _apply_result(sub, result)
        sub.is_completed = True
        sub.completed_at = sub.completed_at or result.calculated_at
    elif state == "pending_review":
        sub.status = HomeworkSubmission.Status.AWAITING_REVIEW
        sub.is_completed = True
        sub.completed_at = sub.completed_at or getattr(sub.test_attempt, "completed_at", None)
        sub.grading_error = ""
    elif state == "missing" and sub.test_attempt_id and sub.test_attempt.status != TestAttempt.Status.IN_PROGRESS:
        sub.status = HomeworkSubmission.Status.GRADING_FAILED
        sub.is_completed = True
        sub.grading_error = "Rasmiy natija topilmadi."
    elif state == "cancelled":
        sub.status = HomeworkSubmission.Status.GRADING_FAILED
        sub.is_completed = True
        sub.grading_error = "Test urinishi bekor qilingan."
    return before != (sub.status, sub.result_id, sub.is_completed)


def _effective_attempt(hw: Homework, sub: HomeworkSubmission | None) -> TestAttempt | None:
    """The official attempt that belongs to this homework, or None.

    Only an attempt started at/after the homework was created counts; this
    rejects results from earlier practice that old code linked by test id.
    """
    if sub is None:
        return None
    attempt = sub.test_attempt
    if attempt is None and sub.result_id and sub.result is not None:
        attempt = sub.result.attempt
    if attempt is None or attempt.test_id != hw.test_id:
        return None
    if attempt.started_at and attempt.started_at < hw.created_at:
        return None
    return attempt


def _trusted_submission(hw: Homework, sub: HomeworkSubmission | None) -> HomeworkSubmission | None:
    """Drop legacy rows the old list endpoint created by linking an older Result.

    Those rows were never started through this homework (attempts_count == 0)
    and carry no attempt of their own, so they describe other work.
    """
    if (
        sub is not None
        and hw.content_type == Homework.ContentType.TEST
        and sub.is_completed
        and sub.attempts_count == 0
        and _effective_attempt(hw, sub) is None
    ):
        return None
    return sub


def derive_submission_status(
    homework: Homework,
    submission: HomeworkSubmission | None,
    now: datetime | None = None,
) -> tuple[str, float | None, str]:
    """Authoritative, read-only lifecycle status for one student's homework.

    A score is returned only when it comes from a finished official grade
    (test Result, graded essay, or a teacher's grade on a custom task).
    Score 0 from such a source is GRADED; absence of a grade is never 0.
    """
    if now is None:
        now = timezone.now()
    submission = _trusted_submission(homework, submission)

    if submission is not None:
        # Finished work keeps its outcome even if the homework is cancelled later.
        if submission.essay_submission_id:
            es = submission.essay_submission
            if es.status in (EssaySubmission.Status.GRADED, EssaySubmission.Status.TEACHER_REVIEWED):
                score = es.final_score if getattr(es, "final_score", None) is not None else es.total_score
                if score is not None:
                    return HomeworkSubmission.Status.GRADED, float(score), f"{float(score)} ball"
            if es.status == EssaySubmission.Status.ERROR:
                return HomeworkSubmission.Status.GRADING_FAILED, None, "Baholashda xatolik"
            return HomeworkSubmission.Status.AWAITING_REVIEW, None, "Tekshiruv kutilmoqda"

        if homework.content_type == Homework.ContentType.TEST:
            attempt = _effective_attempt(homework, submission)
            if attempt is None:
                # Legacy rows: a score without the attempt this homework started
                # (old fallback linking / grading-failure zeros) is not trusted.
                if submission.status == HomeworkSubmission.Status.IN_PROGRESS and not submission.is_completed:
                    pass
                elif submission.is_completed:
                    return HomeworkSubmission.Status.GRADING_FAILED, None, "Natija hali tayyor emas"
            else:
                state, result = _official_test_outcome(attempt)
                if state == "graded":
                    return (
                        HomeworkSubmission.Status.GRADED,
                        float(result.percentage),
                        f"{result.score}/{result.max_score}",
                    )
                if state == "pending_review":
                    return HomeworkSubmission.Status.AWAITING_REVIEW, None, "Tekshiruv kutilmoqda"
                if state in ("missing", "cancelled") and submission.is_completed:
                    return HomeworkSubmission.Status.GRADING_FAILED, None, "Natija hali tayyor emas"

        if submission.is_completed:
            if submission.status == HomeworkSubmission.Status.GRADED and (
                submission.percentage is not None or submission.score is not None
            ):
                value = submission.percentage if submission.percentage is not None else submission.score
                return (
                    HomeworkSubmission.Status.GRADED,
                    float(value),
                    submission.score_display or f"{float(value)}",
                )
            if submission.status == HomeworkSubmission.Status.GRADING_FAILED:
                return HomeworkSubmission.Status.GRADING_FAILED, None, "Natija hali tayyor emas"
            if submission.status == HomeworkSubmission.Status.AWAITING_REVIEW:
                return HomeworkSubmission.Status.AWAITING_REVIEW, None, "Tekshiruv kutilmoqda"
            return HomeworkSubmission.Status.SUBMITTED, None, "Topshirildi"

        if submission.status == HomeworkSubmission.Status.GRADING_FAILED:
            return HomeworkSubmission.Status.GRADING_FAILED, None, "Natija hali tayyor emas"

    if homework.status == Homework.Status.CANCELLED:
        return HomeworkSubmission.Status.CANCELLED, None, "Bekor qilingan"

    if submission is not None and submission.status == HomeworkSubmission.Status.IN_PROGRESS:
        deadline = submission_deadline(homework, submission)
        if deadline and deadline < now:
            return HomeworkSubmission.Status.OVERDUE, None, "Muddati o'tgan"
        return HomeworkSubmission.Status.IN_PROGRESS, None, "Jarayonda"

    if homework.due_date < now:
        return HomeworkSubmission.Status.OVERDUE, None, "Muddati o'tgan"
    return HomeworkSubmission.Status.NOT_STARTED, None, "Boshlanmagan"


def _action_target(hw: Homework) -> tuple[str, int | None]:
    if hw.content_type == Homework.ContentType.TEST and hw.test_id:
        return f"/tests/{hw.test_id}", hw.test_id
    if hw.content_type == Homework.ContentType.ESSAY and hw.essay_topic_id:
        return f"/essays/{hw.essay_topic_id}/write", hw.essay_topic_id
    if hw.content_type == Homework.ContentType.VOCABULARY and hw.vocabulary_pack_id:
        return f"/vocabulary/packs/{hw.vocabulary_pack_id}", hw.vocabulary_pack_id
    return "", None


def _serialize_item(
    hw: Homework, sub: HomeworkSubmission | None, student, now: datetime, is_recipient: bool | None = None
) -> dict[str, Any]:
    sub = _trusted_submission(hw, sub)
    eff_status, eff_score, status_label = derive_submission_status(hw, sub, now)
    graded = eff_status == HomeworkSubmission.Status.GRADED
    action_url, action_id = _action_target(hw)
    deadline = submission_deadline(hw, sub)
    attempts_used = sub.attempts_count if sub else 0
    if is_recipient is None:
        is_recipient = _is_current_recipient(hw, student)
    can_start = (
        is_recipient
        and hw.status == Homework.Status.ACTIVE
        and not (hw.start_date and now < hw.start_date)
        and hw.due_date >= now
        and (
            sub is None
            or not sub.is_completed
            or attempts_used < hw.max_attempts
        )
    )
    max_score = percentage = None
    score_display = ""
    if graded and sub is not None:
        if hw.content_type == Homework.ContentType.TEST:
            _, result = _official_test_outcome(_effective_attempt(hw, sub))
            if result is not None:
                max_score = float(result.max_score)
                percentage = float(result.percentage)
                score_display = f"{result.score}/{result.max_score}"
        else:
            max_score = float(sub.max_score) if sub.max_score is not None else None
            percentage = float(sub.percentage) if sub.percentage is not None else None
            score_display = sub.score_display or status_label
    return {
        "id": hw.id,
        "title": hw.title,
        "description": hw.description,
        "content_type": hw.content_type,
        "group_id": hw.group_id,
        "group_name": hw.group.name if hw.group else "",
        "is_individual": hw.group_id is None,
        "teacher_name": hw.created_by.get_full_name() if hw.created_by else "",
        "start_date": hw.start_date.isoformat() if hw.start_date else None,
        "due_date": hw.due_date.isoformat(),
        "deadline_at": deadline.isoformat() if deadline else None,
        "time_limit": hw.time_limit,
        "max_attempts": hw.max_attempts,
        "attempts_used": attempts_used,
        "can_start": bool(can_start),
        "is_current_recipient": bool(is_recipient),
        "status": eff_status,
        "status_label": status_label,
        "is_completed": bool(sub and sub.is_completed),
        "is_late": bool(sub and sub.completed_at and sub.completed_at > hw.due_date),
        "score": eff_score if graded else None,
        "max_score": max_score,
        "percentage": percentage,
        "score_display": score_display,
        "action_url": action_url,
        "action_id": action_id,
        "attempt_id": sub.test_attempt_id if sub else None,
        "submission_id": sub.id if sub else None,
        "created_at": hw.created_at.isoformat(),
    }


_LIST_FILTERS = {
    "pending": {HomeworkSubmission.Status.NOT_STARTED, HomeworkSubmission.Status.IN_PROGRESS},
    "completed": {
        HomeworkSubmission.Status.SUBMITTED,
        HomeworkSubmission.Status.AWAITING_REVIEW,
        HomeworkSubmission.Status.GRADED,
        HomeworkSubmission.Status.GRADING_FAILED,
    },
    "overdue": {HomeworkSubmission.Status.OVERDUE},
}


def get_student_homework_list(student, *, status_filter: str | None = None) -> list[dict[str, Any]]:
    """All homework the student may see, with derived status. Read-only."""
    now = timezone.now()
    homework_qs = (
        Homework.objects.filter(_readable_homework_ids(student))
        .exclude(status=Homework.Status.ARCHIVED)
        .select_related("group", "student", "test", "essay_topic", "vocabulary_pack", "lesson", "created_by")
        .order_by("due_date", "-created_at")
    )
    homeworks = list(homework_qs)
    submissions = {
        sub.homework_id: sub
        for sub in HomeworkSubmission.objects.filter(
            student=student, homework_id__in=[h.id for h in homeworks]
        ).select_related("result", "essay_submission", "test_attempt")
    }
    current_ids = set(Homework.objects.filter(_recipient_q(student)).values_list("id", flat=True))
    norm = (status_filter or "").lower().strip()
    out: list[dict[str, Any]] = []
    for hw in homeworks:
        item = _serialize_item(hw, submissions.get(hw.id), student, now, hw.id in current_ids)
        if norm and norm != "all":
            allowed = _LIST_FILTERS.get(norm)
            if allowed is not None and item["status"] not in allowed:
                continue
            if allowed is None and item["status"] != norm:
                continue
        out.append(item)
    return out


def _get_readable_homework(student, homework_id: int) -> Homework:
    hw = (
        Homework.objects.filter(_readable_homework_ids(student), id=homework_id)
        .select_related("group", "student", "test", "essay_topic", "vocabulary_pack", "lesson", "created_by")
        .first()
    )
    if hw is None:
        raise HomeworkNotFound("Ushbu topshiriq topilmadi yoki sizga biriktirilmagan.")
    return hw


def get_student_homework_detail(student, homework_id: int) -> dict[str, Any]:
    """Detail view (read-only). Never exposes answer keys."""
    now = timezone.now()
    hw = _get_readable_homework(student, homework_id)
    sub = (
        HomeworkSubmission.objects.filter(student=student, homework=hw)
        .select_related("result", "essay_submission", "test_attempt")
        .first()
    )
    data = _serialize_item(hw, sub, student, now)

    content_details: dict[str, Any] = {}
    if hw.content_type == Homework.ContentType.TEST and hw.test:
        content_details = {
            "test_id": hw.test.id,
            "test_title": hw.test.title,
            "subject": hw.test.subject,
            "questions_count": hw.test.questions.count(),
            "time_limit": hw.test.time_limit_minutes or 0,
        }
    elif hw.content_type == Homework.ContentType.ESSAY and hw.essay_topic:
        content_details = {
            "topic_id": hw.essay_topic.id,
            "topic_title": hw.essay_topic.title,
            "subject": getattr(hw.essay_topic, "subject", ""),
            "min_words": getattr(hw.essay_topic, "word_limit_min", None),
            "max_words": getattr(hw.essay_topic, "word_limit_max", None),
        }
    elif hw.content_type == Homework.ContentType.VOCABULARY and hw.vocabulary_pack:
        content_details = {
            "pack_id": hw.vocabulary_pack.id,
            "pack_title": hw.vocabulary_pack.title,
            "words_count": hw.vocabulary_pack.word_count,
        }
    elif hw.content_type == Homework.ContentType.LESSON and hw.lesson:
        content_details = {"lesson_id": hw.lesson.id, "lesson_title": hw.lesson.title}

    data.update(
        {
            "content_details": content_details,
            "answers_payload": sub.answers_payload if sub else {},
            "feedback": sub.feedback if sub else "",
            "started_at": sub.started_at.isoformat() if (sub and sub.started_at) else None,
            "completed_at": sub.completed_at.isoformat() if (sub and sub.completed_at) else None,
            "server_now": now.isoformat(),
        }
    )
    return data


def _get_or_create_submission_locked(hw: Homework, student) -> tuple[HomeworkSubmission, bool]:
    sub = HomeworkSubmission.objects.select_for_update().filter(homework=hw, student=student).first()
    if sub is not None:
        return sub, False
    try:
        with transaction.atomic():
            sub = HomeworkSubmission.objects.create(
                homework=hw, student=student, status=HomeworkSubmission.Status.NOT_STARTED
            )
        return sub, True
    except IntegrityError:
        return HomeworkSubmission.objects.select_for_update().get(homework=hw, student=student), False


@transaction.atomic
def start_student_homework(student, homework_id: int) -> dict[str, Any]:
    """Start or resume. Only a current recipient, inside the window, within attempts."""
    now = timezone.now()
    hw = _lock_homework_for_write(student, homework_id)
    sub, _ = _get_or_create_submission_locked(hw, student)

    # A finished official attempt the student completed in the runner: record it first.
    if hw.content_type == Homework.ContentType.TEST and sub.test_attempt_id and not sub.is_completed:
        if _sync_test_submission(sub):
            sub.save()
            _announce(sub)

    in_progress = not sub.is_completed and sub.status in (
        HomeworkSubmission.Status.IN_PROGRESS,
        HomeworkSubmission.Status.GRADING_FAILED,
    )
    if (
        in_progress
        and hw.content_type == Homework.ContentType.TEST
        and sub.test_attempt_id
        and sub.test_attempt.status == TestAttempt.Status.IN_PROGRESS
        and sub.test_attempt.is_time_expired
    ):
        # The official timer ran out: finalise it (TIMEOUT, answers kept) instead
        # of letting the runner silently open a fresh attempt.
        return _finalize_test_submission(sub, hw, student, now)
    if not in_progress:
        _assert_window_open(hw, now)
        if sub.attempts_count >= hw.max_attempts:
            raise HomeworkConflict("Barcha urinishlaringiz tugagan.", "attempts_exhausted")
    else:
        # Resuming is allowed only while the window and personal timer are open.
        _assert_window_open(hw, now)
        deadline = submission_deadline(hw, sub)
        if deadline and now > deadline:
            raise HomeworkConflict("Vaqt tugagan.", "time_expired")

    attempt_id = sub.test_attempt_id if in_progress else None
    if hw.content_type == Homework.ContentType.TEST and hw.test_id:
        from apps.tests.services import StartAttemptService

        attempt = StartAttemptService.execute(test_id=hw.test_id, student=student)
        if not in_progress and attempt.started_at < hw.created_at:
            # An attempt opened before this homework existed is not homework work.
            raise HomeworkConflict(
                "Sizda bu test bo'yicha oldin boshlangan urinish bor. Avval uni yakunlang.",
                "foreign_attempt_in_progress",
            )
        attempt_id = attempt.id
        sub.test_attempt = attempt

    if not in_progress:
        # A new attempt: previous outcome stays in the official Result history.
        sub.status = HomeworkSubmission.Status.IN_PROGRESS
        sub.is_completed = False
        sub.started_at = now
        sub.completed_at = None
        sub.result = None
        sub.score = sub.max_score = sub.percentage = None
        sub.score_display = ""
        sub.grading_error = ""
        sub.answers_payload = {}
        sub.attempts_count += 1
    sub.save()

    deadline = submission_deadline(hw, sub)
    return {
        "ok": True,
        "homework_id": hw.id,
        "submission_id": sub.id,
        "status": sub.status,
        "attempt_id": attempt_id,
        "attempts_used": sub.attempts_count,
        "started_at": sub.started_at.isoformat() if sub.started_at else None,
        "deadline_at": deadline.isoformat() if deadline else None,
        "server_now": now.isoformat(),
        "time_limit": hw.time_limit,
    }


def _validate_payload(payload: Any) -> dict[str, Any]:
    import json

    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValueError("Javoblar formati noto'g'ri.")
    if len(json.dumps(payload, default=str)) > MAX_ANSWERS_PAYLOAD_BYTES:
        raise ValueError("Javoblar hajmi juda katta.")
    return payload


@transaction.atomic
def save_student_homework_progress(student, homework_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    """Autosave. Rejected after finish, after the deadline, or for non-recipients."""
    now = timezone.now()
    payload = _validate_payload(payload)
    hw = _lock_homework_for_write(student, homework_id)
    sub = HomeworkSubmission.objects.select_for_update().filter(homework=hw, student=student).first()
    if sub is None or sub.status == HomeworkSubmission.Status.NOT_STARTED:
        raise HomeworkConflict("Avval topshiriqni boshlang.", "not_started")
    if sub.is_completed:
        raise HomeworkConflict("Topshiriq allaqachon yakunlangan.", "already_completed")
    _assert_window_open(hw, now)
    deadline = submission_deadline(hw, sub)
    if deadline and now > deadline:
        raise HomeworkConflict("Vaqt tugagan.", "time_expired")

    sub.answers_payload = payload
    sub.save(update_fields=["answers_payload", "updated_at"])
    return {"ok": True, "saved_at": now.isoformat(), "deadline_at": deadline.isoformat() if deadline else None}


def _completion_payload(sub: HomeworkSubmission, hw: Homework) -> dict[str, Any]:
    eff_status, eff_score, label = derive_submission_status(hw, sub)
    graded = eff_status == HomeworkSubmission.Status.GRADED
    return {
        "ok": eff_status != HomeworkSubmission.Status.GRADING_FAILED,
        "status": eff_status,
        "status_label": label,
        "is_completed": sub.is_completed,
        "score": float(sub.score) if (graded and sub.score is not None) else None,
        "max_score": float(sub.max_score) if (graded and sub.max_score is not None) else None,
        "percentage": float(sub.percentage) if (graded and sub.percentage is not None) else None,
        "score_display": sub.score_display if graded else "",
        "grading_error": sub.grading_error if eff_status == HomeworkSubmission.Status.GRADING_FAILED else "",
        "completed_at": sub.completed_at.isoformat() if sub.completed_at else None,
    }


def _link_recent_essay(sub: HomeworkSubmission, hw: Homework, student) -> None:
    """Link the student's essay on this topic written since the homework started."""
    since = sub.started_at or hw.created_at
    es = (
        EssaySubmission.objects.filter(student=student, topic_id=hw.essay_topic_id, created_at__gte=since)
        .exclude(status=EssaySubmission.Status.DRAFT)
        .order_by("-created_at")
        .first()
    )
    if es is not None:
        sub.essay_submission = es


def _finalize_test_submission(sub: HomeworkSubmission, hw: Homework, student, now: datetime) -> dict[str, Any]:
    """Finish the linked official attempt (if still open) and record its outcome."""
    attempt = sub.test_attempt
    if attempt.status == TestAttempt.Status.IN_PROGRESS:
        # The official service owns its own timer: an expired attempt is
        # finalised as TIMEOUT with the answers saved so far.
        from apps.tests.services import SubmitAttemptService

        try:
            with transaction.atomic():
                SubmitAttemptService.execute(attempt.id, student)
        except Exception as exc:  # a grader failure must never become a grade
            logger.exception("Homework %s: official grading failed for attempt %s", hw.id, attempt.id)
            attempt.refresh_from_db()
            if attempt.status == TestAttempt.Status.IN_PROGRESS:
                sub.status = HomeworkSubmission.Status.GRADING_FAILED
                sub.grading_error = f"Baholash xatosi: {type(exc).__name__}"[:500]
                sub.save(update_fields=["status", "grading_error", "updated_at"])
                return _completion_payload(sub, hw)
        attempt.refresh_from_db()
    sub.test_attempt = attempt
    sub.completed_at = sub.completed_at or now
    if not _sync_test_submission(sub) and not sub.is_completed:
        sub.status = HomeworkSubmission.Status.GRADING_FAILED
        sub.grading_error = "Rasmiy natija topilmadi."
        sub.is_completed = True
    sub.save()
    _announce(sub)
    return _completion_payload(sub, hw)


def homework_pending_for_attempt(attempt_id: int) -> bool:
    """One cheap EXISTS so ordinary (non-homework) submits pay a single query."""
    return (
        HomeworkSubmission.objects.filter(test_attempt_id=attempt_id)
        .exclude(status=HomeworkSubmission.Status.GRADED)
        .exists()
    )


def sync_homework_for_attempt(attempt_id: int) -> int:
    """Record the official outcome on every homework submission linked to this attempt."""
    changed = 0
    for sub in (
        HomeworkSubmission.objects.select_for_update(of=("self",))
        .select_related("test_attempt", "homework")
        .filter(test_attempt_id=attempt_id)
        .exclude(status=HomeworkSubmission.Status.GRADED)
    ):
        if _sync_test_submission(sub):
            sub.completed_at = sub.completed_at or timezone.now()
            sub.save()
            _announce(sub)
            changed += 1
    return changed


def _announce(sub: HomeworkSubmission) -> None:
    from apps.notifications.outbox import enqueue_homework_outcome

    enqueue_homework_outcome(sub)


@transaction.atomic
def submit_student_homework(student, homework_id: int, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Finish and grade through the official services.

    Idempotent: a second call returns the stored outcome; for a test whose
    grading failed it retries the official sync (never fabricates a score).
    """
    now = timezone.now()
    payload = _validate_payload(payload) if payload else {}
    hw = _lock_homework_for_write(student, homework_id)
    sub = (
        HomeworkSubmission.objects.select_for_update(of=("self",))
        .select_related("test_attempt", "essay_submission")
        .filter(homework=hw, student=student)
        .first()
    )
    if sub is None or sub.status == HomeworkSubmission.Status.NOT_STARTED:
        raise HomeworkConflict("Avval topshiriqni boshlang.", "not_started")

    if sub.is_completed:
        if hw.content_type == Homework.ContentType.TEST and sub.status != HomeworkSubmission.Status.GRADED:
            if _sync_test_submission(sub):
                sub.save()
                _announce(sub)
        return _completion_payload(sub, hw)

    if hw.content_type == Homework.ContentType.TEST:
        if sub.test_attempt_id is None:
            raise HomeworkConflict("Test urinishi topilmadi. Topshiriqni qayta boshlang.", "attempt_missing")
        if sub.test_attempt.status == TestAttempt.Status.IN_PROGRESS and hw.status == Homework.Status.CANCELLED:
            raise HomeworkConflict("Ushbu topshiriq bekor qilingan.", "cancelled")
        return _finalize_test_submission(sub, hw, student, now)

    # Non-test content is subject to the homework window and personal timer.
    _assert_window_open(hw, now)
    deadline = submission_deadline(hw, sub)
    if deadline and now > deadline:
        raise HomeworkConflict("Vaqt tugagan.", "time_expired")

    if payload:
        sub.answers_payload = payload
    if hw.content_type == Homework.ContentType.ESSAY:
        _link_recent_essay(sub, hw, student)
        if sub.essay_submission_id is None:
            raise HomeworkConflict("Avval esseni yozib topshiring.", "essay_missing")
        sub.status = HomeworkSubmission.Status.AWAITING_REVIEW
    elif hw.content_type == Homework.ContentType.CUSTOM:
        if not sub.answers_payload:
            raise HomeworkConflict("Javob kiritilmagan.", "empty_answer")
        sub.status = HomeworkSubmission.Status.AWAITING_REVIEW
    else:
        # Lesson / vocabulary: completion is recorded, nothing is graded.
        sub.status = HomeworkSubmission.Status.SUBMITTED
    sub.is_completed = True
    sub.completed_at = now
    sub.save()
    _announce(sub)
    return _completion_payload(sub, hw)


def official_exam_summary(hw: Homework, sub: HomeworkSubmission | None) -> dict[str, Any] | None:
    """The subject-specific scale exactly as the official pipeline persisted it.

    IELTS tests expose the band, CEFR Multi-level exposes the level and its
    per-section 0–75 scores; every other exam (Milliy Sertifikat, Studio,
    general) exposes only its raw score — the pipeline also stores an IELTS
    conversion for those, which is not meaningful there and is not shown.
    """
    if hw.content_type != Homework.ContentType.TEST or hw.test is None:
        return None
    attempt = _effective_attempt(hw, _trusted_submission(hw, sub))
    state, result = _official_test_outcome(attempt)
    if state != "graded":
        return None
    exam_type = hw.test.exam_type
    out: dict[str, Any] = {
        "exam_type": exam_type,
        "correct": result.correct_answers,
        "total": result.total_questions,
        "is_passed": result.is_passed,
    }
    if exam_type in (Test.ExamType.IELTS_ACADEMIC, Test.ExamType.IELTS_GENERAL) and attempt.band_score is not None:
        out["band"] = float(attempt.band_score)
    if exam_type == Test.ExamType.CEFR_MULTILEVEL:
        out["cefr_level"] = attempt.cefr_level or ""
        out["section_scores"] = attempt.section_scores or {}
    return out


def get_student_homework_result(student, homework_id: int) -> dict[str, Any]:
    """Result of finished work only; scores only from official grades."""
    data = get_student_homework_detail(student, homework_id)
    if not data["is_completed"]:
        raise HomeworkConflict("Ushbu topshiriq hali yakunlanmagan.", "not_completed")
    hw = Homework.objects.select_related("test").get(id=homework_id)
    sub = HomeworkSubmission.objects.filter(homework=hw, student=student).select_related("test_attempt", "result").first()
    return {
        "official": official_exam_summary(hw, sub),
        "homework_id": data["id"],
        "title": data["title"],
        "status": data["status"],
        "status_label": data["status_label"],
        "score": data["score"],
        "max_score": data["max_score"],
        "percentage": data["percentage"],
        "score_display": data["score_display"],
        "feedback": data["feedback"],
        "completed_at": data["completed_at"],
        "is_late": data["is_late"],
        "attempt_id": data["attempt_id"],
    }


# ---------------------------------------------------------------------------
# 3. Teacher grading of custom / lesson work
# ---------------------------------------------------------------------------


def _teacher_can_manage(user, hw: Homework) -> bool:
    if is_platform_admin(user):
        return True
    if hw.group_id and get_teacher_groups(user).filter(id=hw.group_id).exists():
        return True
    if hw.created_by_id == user.pk:
        return True
    return False


@transaction.atomic
def grade_custom_submission(user, submission_id: int, *, score, max_score, feedback: str = "") -> HomeworkSubmission:
    """Teacher grade for CUSTOM/LESSON work. Tests/essays are graded by their official pipelines."""
    from decimal import Decimal, InvalidOperation

    sub = HomeworkSubmission.objects.select_for_update(of=("self",)).select_related("homework").filter(id=submission_id).first()
    if sub is None or not _teacher_can_manage(user, sub.homework):
        raise HomeworkNotFound("Topshiriq topilmadi.")
    if sub.homework.content_type in (Homework.ContentType.TEST, Homework.ContentType.ESSAY):
        raise HomeworkConflict("Test va esse rasmiy tizimda baholanadi.", "official_grader")
    if not sub.is_completed:
        raise HomeworkConflict("O'quvchi hali topshirmagan.", "not_completed")
    try:
        score_d = Decimal(str(score))
        max_d = Decimal(str(max_score))
    except (InvalidOperation, TypeError):
        raise ValueError("Ball noto'g'ri.")
    if max_d <= 0 or score_d < 0 or score_d > max_d:
        raise ValueError("Ball 0 va maksimal ball oralig'ida bo'lishi kerak.")
    sub.score = score_d
    sub.max_score = max_d
    sub.percentage = float((score_d / max_d * 100).quantize(Decimal("0.01")))
    sub.score_display = f"{score_d}/{max_d}"
    sub.feedback = (feedback or "").strip()[:5000]
    sub.status = HomeworkSubmission.Status.GRADED
    sub.graded_by = user
    sub.save()
    _announce(sub)
    return sub


# ---------------------------------------------------------------------------
# 4. Teacher view of progress — same derivation as the student sees
# ---------------------------------------------------------------------------


def _roster_students(hw: Homework):
    """Current recipients plus anyone who already has a submission (removed students keep history)."""
    from apps.accounts.models import User

    ids: set[int] = set(HomeworkSubmission.objects.filter(homework=hw).values_list("student_id", flat=True))
    if hw.student_id:
        ids.add(hw.student_id)
    elif hw.group_id:
        ids.update(hw.group.students.values_list("id", flat=True))
    return User.objects.filter(id__in=ids).order_by("last_name", "first_name", "id")


def homework_roster(hw: Homework, now: datetime | None = None) -> list[dict[str, Any]]:
    now = now or timezone.now()
    current = set()
    if hw.student_id:
        current.add(hw.student_id)
    elif hw.group_id:
        current.update(hw.group.students.values_list("id", flat=True))
    subs = {
        s.student_id: s
        for s in HomeworkSubmission.objects.filter(homework=hw).select_related(
            "result", "essay_submission", "test_attempt"
        )
    }
    rows = []
    for st in _roster_students(hw):
        sub = _trusted_submission(hw, subs.get(st.id))
        status, score, _label = derive_submission_status(hw, sub, now)
        rows.append(
            {
                "student_id": st.id,
                "student_name": st.get_full_name() or st.email,
                "is_current_member": st.id in current,
                "status": status,
                "score": score if status == HomeworkSubmission.Status.GRADED else None,
                "submission_id": sub.id if sub else None,
                "attempts_used": sub.attempts_count if sub else 0,
                "completed_at": sub.completed_at.isoformat() if (sub and sub.completed_at) else None,
                "is_late": bool(sub and sub.completed_at and sub.completed_at > hw.due_date),
                "needs_review": status == HomeworkSubmission.Status.AWAITING_REVIEW,
                "grading_failed": status == HomeworkSubmission.Status.GRADING_FAILED,
            }
        )
    return rows


_DONE = {
    HomeworkSubmission.Status.SUBMITTED,
    HomeworkSubmission.Status.AWAITING_REVIEW,
    HomeworkSubmission.Status.GRADED,
    HomeworkSubmission.Status.GRADING_FAILED,
}


def summarize_homework_progress(hw: Homework, now: datetime | None = None) -> dict[str, int]:
    rows = [r for r in homework_roster(hw, now) if r["is_current_member"] or r["submission_id"]]
    return {
        "total_students": sum(1 for r in rows if r["is_current_member"]),
        "submitted": sum(1 for r in rows if r["status"] in _DONE),
        "graded": sum(1 for r in rows if r["status"] == HomeworkSubmission.Status.GRADED),
        "awaiting_review": sum(1 for r in rows if r["needs_review"]),
        "grading_failed": sum(1 for r in rows if r["grading_failed"]),
        "in_progress": sum(1 for r in rows if r["status"] == HomeworkSubmission.Status.IN_PROGRESS),
    }


def get_teacher_homework_roster(user, homework_id: int) -> dict[str, Any]:
    hw = Homework.objects.select_related("group", "student").filter(id=homework_id).first()
    if hw is None or not _teacher_can_manage(user, hw):
        raise HomeworkNotFound("Vazifa topilmadi.")
    now = timezone.now()
    return {
        "homework_id": hw.id,
        "title": hw.title,
        "content_type": hw.content_type,
        "status": hw.status,
        "due_date": hw.due_date.isoformat(),
        "summary": summarize_homework_progress(hw, now),
        "students": homework_roster(hw, now),
    }


def get_homework_live_board(user, homework_id: int) -> dict[str, Any]:
    """Live tablo for one homework: progress from persisted answers, no simulation.

    ``revision`` is a hash of the visible state so clients can poll with
    If-None-Match and reconnect at any time without replaying anything.
    """
    import hashlib
    import json

    from apps.tests.models import StudentAnswer

    hw = Homework.objects.select_related("group", "student", "test").filter(id=homework_id).first()
    if hw is None or not _teacher_can_manage(user, hw):
        raise HomeworkNotFound("Vazifa topilmadi.")
    now = timezone.now()
    rows = homework_roster(hw, now)
    total_questions = hw.test.questions.count() if hw.test_id else None
    subs = {s.student_id: s for s in HomeworkSubmission.objects.filter(homework=hw).select_related("test_attempt")}
    attempt_ids = [s.test_attempt_id for s in subs.values() if s.test_attempt_id]
    answered: dict[int, int] = {}
    last_answer: dict[int, Any] = {}
    if attempt_ids:
        from django.db.models import Count, Max

        for row in (
            StudentAnswer.objects.filter(attempt_id__in=attempt_ids)
            .values("attempt_id")
            .annotate(n=Count("id"), last=Max("answered_at"))
        ):
            answered[row["attempt_id"]] = row["n"]
            last_answer[row["attempt_id"]] = row["last"]
    for r in rows:
        sub = subs.get(r["student_id"])
        aid = sub.test_attempt_id if sub else None
        r["answered"] = answered.get(aid, 0) if aid else 0
        last = last_answer.get(aid) if aid else None
        r["last_activity_at"] = (last or (sub.updated_at if sub else None))
        r["last_activity_at"] = r["last_activity_at"].isoformat() if r["last_activity_at"] else None
        remaining = None
        if sub and sub.test_attempt_id and r["status"] == HomeworkSubmission.Status.IN_PROGRESS:
            remaining = sub.test_attempt.remaining_seconds
        elif sub and r["status"] == HomeworkSubmission.Status.IN_PROGRESS:
            deadline = submission_deadline(hw, sub)
            remaining = max(0, int((deadline - now).total_seconds())) if deadline else None
        r["remaining_seconds"] = remaining
    state = [(r["student_id"], r["status"], r["answered"], r["score"]) for r in rows]
    revision = hashlib.sha256(json.dumps(state, default=str).encode()).hexdigest()[:16]
    return {
        "homework_id": hw.id,
        "title": hw.title,
        "total_questions": total_questions,
        "revision": revision,
        "server_now": now.isoformat(),
        "summary": summarize_homework_progress(hw, now),
        "students": rows,
    }
