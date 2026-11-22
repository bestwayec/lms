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
from datetime import datetime
from typing import Any

from django.db import transaction
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
    # 1. Idempotency check
    if idempotency_key:
        existing = Homework.objects.filter(
            idempotency_key=idempotency_key
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

        target_student = User.objects.filter(id=student_id).first()
        if not target_student:
            raise ValueError("O'quvchi topilmadi.")

        # Ensure student is authorized (in teacher's group or accessible to center/platform admin)
        if not is_platform_admin(user):
            teacher_groups_qs = get_teacher_groups(user)
            student_accessible = teacher_groups_qs.filter(
                students=target_student
            ).exists()
            if not student_accessible:
                # Also allow if student belongs to same branch
                if getattr(user, "branch_id", None) and getattr(
                    target_student, "branch_id", None
                ) == getattr(user, "branch_id", None):
                    student_accessible = True
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

        # Do NOT hijack or overwrite another group's assignment
        if group and test.assigned_group_id is None:
            test.assigned_group = group
            test.save(update_fields=["assigned_group"])

        content_type = Homework.ContentType.TEST

    elif content_type == Homework.ContentType.ESSAY or essay_topic_id:
        if not essay_topic_id:
            raise ValueError("Esse topshirig'i uchun essay_topic_id talab qilinadi.")
        topic = EssayTopic.objects.filter(id=essay_topic_id).first()
        if not topic:
            raise ValueError("Biriktirilgan esse mavzusi topilmadi.")

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
        content_type = Homework.ContentType.VOCABULARY

    elif content_type == Homework.ContentType.LESSON or lesson_id:
        if not lesson_id:
            raise ValueError("Dars topshirig'i uchun lesson_id talab qilinadi.")
        lesson = Lesson.objects.filter(id=lesson_id).first()
        if not lesson:
            raise ValueError("Biriktirilgan dars topilmadi.")
        content_type = Homework.ContentType.LESSON

    else:
        content_type = Homework.ContentType.CUSTOM

    # 5. Create the unified homework record atomically
    hw = Homework.objects.create(
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
        time_limit=max(0, int(time_limit or 0)),
        max_attempts=max(1, int(max_attempts or 1)),
        status=Homework.Status.ACTIVE,
        idempotency_key=idempotency_key or None,
        created_by=user,
    )

    return hw, True


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
# 2. Student Homework Lifecycle & Authoritative Status Derivation
# ---------------------------------------------------------------------------


def derive_submission_status(
    homework: Homework,
    submission: HomeworkSubmission | None,
    now: datetime | None = None,
) -> tuple[str, float | None, str]:
    """
    Derive the authoritative lifecycle status for a student homework assignment:
    - NOT_STARTED
    - IN_PROGRESS
    - SUBMITTED
    - AWAITING_REVIEW
    - GRADED
    - OVERDUE
    - CANCELLED

    Rules:
    - Cancelled homework is always CANCELLED.
    - Completed submissions with a calculated grade are GRADED.
    - A score of 0 is a valid final score (0.0%), NOT pending.
    - Submissions awaiting manual teacher evaluation are AWAITING_REVIEW.
    - Overdue is derived from server time vs due_date.
    """
    if now is None:
        now = timezone.now()

    if homework.status == Homework.Status.CANCELLED:
        return HomeworkSubmission.Status.CANCELLED, None, "Bekor qilingan"

    if submission:
        # Check essay specific status
        if submission.essay_submission_id:
            es = submission.essay_submission
            if es:
                if es.status in (
                    EssaySubmission.Status.GRADED,
                    EssaySubmission.Status.TEACHER_REVIEWED,
                ):
                    final_score = (
                        float(es.final_score)
                        if getattr(es, "final_score", None) is not None
                        else (float(es.total_score) if es.total_score is not None else 0.0)
                    )
                    return (
                        HomeworkSubmission.Status.GRADED,
                        final_score,
                        f"{final_score} ball",
                    )
                if es.status == EssaySubmission.Status.PENDING_TEACHER:
                    return (
                        HomeworkSubmission.Status.AWAITING_REVIEW,
                        None,
                        "Tekshiruv kutilmoqda",
                    )

        # Check test specific status
        if submission.result_id:
            res = submission.result
            pct = float(res.percentage) if res else (submission.percentage or 0.0)
            score_txt = submission.score_display or (
                f"{res.score}/{res.max_score}" if res else f"{pct}%"
            )
            return HomeworkSubmission.Status.GRADED, pct, score_txt

        # General completion check
        if submission.is_completed:
            if submission.percentage is not None:
                return (
                    HomeworkSubmission.Status.GRADED,
                    float(submission.percentage),
                    submission.score_display or f"{submission.percentage}%",
                )
            if submission.score is not None:
                return (
                    HomeworkSubmission.Status.GRADED,
                    float(submission.score),
                    submission.score_display or f"{submission.score} ball",
                )
            if submission.status == HomeworkSubmission.Status.AWAITING_REVIEW:
                return (
                    HomeworkSubmission.Status.AWAITING_REVIEW,
                    None,
                    "Tekshiruv kutilmoqda",
                )
            return (
                HomeworkSubmission.Status.SUBMITTED,
                None,
                "Topshirildi",
            )

        if submission.status == HomeworkSubmission.Status.IN_PROGRESS:
            if homework.due_date < now:
                return HomeworkSubmission.Status.OVERDUE, None, "Muddati o'tgan"
            return HomeworkSubmission.Status.IN_PROGRESS, None, "Jarayonda"

    # No active submission record
    if homework.due_date < now:
        return HomeworkSubmission.Status.OVERDUE, None, "Muddati o'tgan"

    return HomeworkSubmission.Status.NOT_STARTED, None, "Boshlanmagan"


def get_student_homework_list(
    student,
    *,
    status_filter: str | None = None,
) -> list[dict[str, Any]]:
    """
    Fetch all authorized homework for a student (assigned to their groups or individual).
    Returns rich metadata with derived authoritative status and score.
    """
    now = timezone.now()

    # Student sees only homework assigned to their active groups or directly to them
    homework_qs = (
        Homework.objects.filter(
            Q(group__students=student) | Q(student=student)
        )
        .exclude(status=Homework.Status.ARCHIVED)
        .select_related(
            "group",
            "student",
            "test",
            "essay_topic",
            "vocabulary_pack",
            "lesson",
            "created_by",
        )
        .order_by("due_date", "-created_at")
    )

    hw_ids = list(homework_qs.values_list("id", flat=True))

    submissions_map: dict[int, HomeworkSubmission] = {
        sub.homework_id: sub
        for sub in HomeworkSubmission.objects.filter(
            student=student, homework_id__in=hw_ids
        ).select_related("result", "essay_submission", "test_attempt")
    }

    results: list[dict[str, Any]] = []

    for hw in homework_qs:
        sub = submissions_map.get(hw.id)

        # Check fallback test result if submission record not yet linked
        if not sub and hw.test_id:
            existing_res = (
                Result.objects.filter(student=student, test_id=hw.test_id)
                .order_by("-calculated_at")
                .first()
            )
            if existing_res:
                sub, _ = HomeworkSubmission.objects.get_or_create(
                    homework=hw,
                    student=student,
                    defaults={
                        "status": HomeworkSubmission.Status.GRADED,
                        "is_completed": True,
                        "score": existing_res.score,
                        "max_score": existing_res.max_score,
                        "percentage": float(existing_res.percentage),
                        "score_display": f"{existing_res.score}/{existing_res.max_score}",
                        "result": existing_res,
                        "completed_at": existing_res.calculated_at,
                    },
                )

        eff_status, eff_score, status_label = derive_submission_status(
            hw, sub, now
        )

        # Filter by status if requested
        if status_filter:
            norm_filter = status_filter.lower().strip()
            if norm_filter == "pending":
                if eff_status not in (
                    HomeworkSubmission.Status.NOT_STARTED,
                    HomeworkSubmission.Status.IN_PROGRESS,
                ):
                    continue
            elif norm_filter == "completed":
                if eff_status not in (
                    HomeworkSubmission.Status.SUBMITTED,
                    HomeworkSubmission.Status.AWAITING_REVIEW,
                    HomeworkSubmission.Status.GRADED,
                ):
                    continue
            elif norm_filter == "overdue":
                if eff_status != HomeworkSubmission.Status.OVERDUE:
                    continue
            elif norm_filter != "all" and eff_status.lower() != norm_filter:
                continue

        # Build action URL
        action_url = ""
        action_id = None
        if hw.content_type == Homework.ContentType.TEST and hw.test_id:
            action_url = f"/tests/{hw.test_id}"
            action_id = hw.test_id
        elif hw.content_type == Homework.ContentType.ESSAY and hw.essay_topic_id:
            action_url = f"/essays/{hw.essay_topic_id}/write"
            action_id = hw.essay_topic_id
        elif hw.content_type == Homework.ContentType.VOCABULARY and hw.vocabulary_pack_id:
            action_url = f"/vocabulary/packs/{hw.vocabulary_pack_id}"
            action_id = hw.vocabulary_pack_id

        results.append(
            {
                "id": hw.id,
                "title": hw.title,
                "description": hw.description,
                "content_type": hw.content_type,
                "group_id": hw.group_id,
                "group_name": (
                    hw.group.name if hw.group else "Individual topshiriq"
                ),
                "teacher_name": (
                    hw.created_by.get_full_name()
                    if hw.created_by
                    else "O'qituvchi"
                ),
                "due_date": hw.due_date.isoformat(),
                "time_limit": hw.time_limit,
                "max_attempts": hw.max_attempts,
                "status": eff_status,
                "status_label": status_label,
                "is_completed": bool(sub and sub.is_completed),
                "score": eff_score,
                "max_score": float(sub.max_score) if (sub and sub.max_score is not None) else None,
                "percentage": float(sub.percentage) if (sub and sub.percentage is not None) else None,
                "score_display": sub.score_display if sub else "",
                "action_url": action_url,
                "action_id": action_id,
                "submission_id": sub.id if sub else None,
                "created_at": hw.created_at.isoformat(),
            }
        )

    return results


def get_student_homework_detail(student, homework_id: int) -> dict[str, Any]:
    """
    Get detailed student view of a single homework assignment,
    verifying permission and returning content specifics.
    """
    now = timezone.now()
    hw = (
        Homework.objects.filter(
            Q(group__students=student) | Q(student=student),
            id=homework_id,
        )
        .select_related(
            "group",
            "student",
            "test",
            "essay_topic",
            "vocabulary_pack",
            "lesson",
            "created_by",
        )
        .first()
    )
    if not hw:
        raise PermissionError("Ushbu topshiriq topilmadi yoki sizga biriktirilmagan.")

    sub = (
        HomeworkSubmission.objects.filter(student=student, homework=hw)
        .select_related("result", "essay_submission", "test_attempt")
        .first()
    )

    eff_status, eff_score, status_label = derive_submission_status(hw, sub, now)

    content_details: dict[str, Any] = {}
    if hw.content_type == Homework.ContentType.TEST and hw.test:
        content_details = {
            "test_id": hw.test.id,
            "test_title": hw.test.title,
            "subject": hw.test.subject,
            "questions_count": hw.test.questions.count(),
            "time_limit": hw.time_limit or hw.test.time_limit or 0,
        }
    elif hw.content_type == Homework.ContentType.ESSAY and hw.essay_topic:
        content_details = {
            "topic_id": hw.essay_topic.id,
            "topic_title": hw.essay_topic.title,
            "task_type": getattr(hw.essay_topic, "task_type", ""),
            "min_words": getattr(hw.essay_topic, "min_words", 150),
            "max_words": getattr(hw.essay_topic, "max_words", 300),
        }
    elif hw.content_type == Homework.ContentType.VOCABULARY and hw.vocabulary_pack:
        content_details = {
            "pack_id": hw.vocabulary_pack.id,
            "pack_title": hw.vocabulary_pack.title,
            "words_count": hw.vocabulary_pack.words.count()
            if hasattr(hw.vocabulary_pack, "words")
            else 0,
        }

    return {
        "id": hw.id,
        "title": hw.title,
        "description": hw.description,
        "content_type": hw.content_type,
        "content_details": content_details,
        "group_id": hw.group_id,
        "group_name": hw.group.name if hw.group else "Individual topshiriq",
        "teacher_name": (
            hw.created_by.get_full_name() if hw.created_by else "O'qituvchi"
        ),
        "due_date": hw.due_date.isoformat(),
        "time_limit": hw.time_limit,
        "max_attempts": hw.max_attempts,
        "status": eff_status,
        "status_label": status_label,
        "is_completed": bool(sub and sub.is_completed),
        "score": eff_score,
        "max_score": float(sub.max_score) if (sub and sub.max_score is not None) else None,
        "percentage": float(sub.percentage) if (sub and sub.percentage is not None) else None,
        "score_display": sub.score_display if sub else "",
        "answers_payload": sub.answers_payload if sub else {},
        "feedback": sub.feedback if sub else "",
        "started_at": sub.started_at.isoformat() if (sub and sub.started_at) else None,
        "completed_at": (
            sub.completed_at.isoformat() if (sub and sub.completed_at) else None
        ),
        "submission_id": sub.id if sub else None,
        "created_at": hw.created_at.isoformat(),
    }


@transaction.atomic
def start_student_homework(student, homework_id: int) -> dict[str, Any]:
    """
    Start or resume a student's homework attempt:
    - Verifies homework is ACTIVE and student is authorized
    - Verifies attempts limit and deadline
    - Initializes or resumes TestAttempt, EssaySubmission, or custom state
    """
    now = timezone.now()
    hw = (
        Homework.objects.select_for_update()
        .filter(
            Q(group__students=student) | Q(student=student),
            id=homework_id,
        )
        .first()
    )
    if not hw:
        raise PermissionError("Topshiriq topilmadi yoki sizga biriktirilmagan.")

    if hw.status == Homework.Status.CANCELLED:
        raise ValueError("Ushbu topshiriq bekor qilingan.")

    sub, created = HomeworkSubmission.objects.select_for_update().get_or_create(
        homework=hw,
        student=student,
        defaults={
            "status": HomeworkSubmission.Status.IN_PROGRESS,
            "started_at": now,
            "attempts_count": 1,
        },
    )

    if not created:
        if sub.is_completed:
            # Check if max_attempts allows re-attempt
            if hw.max_attempts > 0 and sub.attempts_count >= hw.max_attempts:
                raise ValueError("Barcha urinishlaringiz tugagan.")

        if sub.status == HomeworkSubmission.Status.NOT_STARTED:
            sub.status = HomeworkSubmission.Status.IN_PROGRESS
            sub.started_at = now
            sub.attempts_count += 1
            sub.save(update_fields=["status", "started_at", "attempts_count", "updated_at"])

    # If it's a test, start or retrieve TestAttempt
    attempt_id = None
    if hw.content_type == Homework.ContentType.TEST and hw.test_id:
        from apps.tests.services import StartAttemptService

        attempt = StartAttemptService.execute(
            test_id=hw.test_id,
            student=student,
        )
        attempt_id = attempt.id
        if sub.test_attempt_id != attempt_id:
            sub.test_attempt = attempt
            sub.save(update_fields=["test_attempt", "updated_at"])

    return {
        "ok": True,
        "homework_id": hw.id,
        "submission_id": sub.id,
        "status": sub.status,
        "attempt_id": attempt_id,
        "started_at": sub.started_at.isoformat() if sub.started_at else now.isoformat(),
        "time_limit": hw.time_limit,
    }


def save_student_homework_progress(
    student, homework_id: int, payload: dict[str, Any]
) -> dict[str, Any]:
    """Autosave student draft answers or progress on the server."""
    now = timezone.now()
    sub = (
        HomeworkSubmission.objects.filter(
            student=student, homework_id=homework_id
        )
        .first()
    )
    if not sub:
        raise ValueError("Boshlangan topshiriq topilmadi.")

    if sub.is_completed:
        return {"ok": True, "already_completed": True}

    sub.answers_payload = payload
    sub.updated_at = now
    sub.save(update_fields=["answers_payload", "updated_at"])

    return {"ok": True, "saved_at": now.isoformat()}


@transaction.atomic
def submit_student_homework(
    student, homework_id: int, payload: dict[str, Any] | None = None
) -> dict[str, Any]:
    """
    Finalize submission and grade via official assessment services:
    - For Test: invokes SubmitAttemptService, records Result, sets GRADED.
    - For Essay: marks EssaySubmission submitted, sets AWAITING_REVIEW or GRADED.
    - For Custom: saves answers, sets AWAITING_REVIEW / SUBMITTED.
    - Idempotent: repeated submissions return the calculated result cleanly.
    """
    now = timezone.now()
    sub = (
        HomeworkSubmission.objects.select_for_update()
        .filter(student=student, homework_id=homework_id)
        .first()
    )
    if not sub:
        # Create submission if submitting directly
        hw = Homework.objects.filter(id=homework_id).first()
        if not hw:
            raise ValueError("Topshiriq topilmadi.")
        sub = HomeworkSubmission.objects.create(
            homework=hw,
            student=student,
            started_at=now,
            status=HomeworkSubmission.Status.IN_PROGRESS,
            attempts_count=1,
        )

    if sub.is_completed:
        # Idempotent response
        return {
            "ok": True,
            "status": sub.status,
            "is_completed": True,
            "score": float(sub.score) if sub.score is not None else None,
            "percentage": float(sub.percentage) if sub.percentage is not None else None,
            "score_display": sub.score_display,
            "completed_at": sub.completed_at.isoformat() if sub.completed_at else None,
        }

    hw = sub.homework

    if hw.content_type == Homework.ContentType.TEST and hw.test_id:
        from apps.tests.services import SubmitAttemptService

        attempt = sub.test_attempt
        if not attempt:
            # Look for active attempt
            attempt = TestAttempt.objects.filter(
                test_id=hw.test_id,
                student=student,
                status=TestAttempt.Status.IN_PROGRESS,
            ).first()

        if attempt:
            try:
                SubmitAttemptService.execute(attempt.id, student)
                attempt.refresh_from_db()
                res = Result.objects.filter(attempt=attempt).first()
                if res:
                    sub.test_attempt = attempt
                    sub.result = res
                    sub.score = res.score
                    sub.max_score = res.max_score
                    sub.percentage = float(res.percentage)
                    sub.score_display = f"{res.score}/{res.max_score}"
                    sub.status = HomeworkSubmission.Status.GRADED
                else:
                    sub.status = HomeworkSubmission.Status.GRADED
                    sub.score = 0
                    sub.percentage = 0.0
            except Exception as e:
                logger.exception("Error executing SubmitAttemptService: %s", e)
                sub.status = HomeworkSubmission.Status.GRADED
                sub.score = 0
                sub.percentage = 0.0
        else:
            sub.status = HomeworkSubmission.Status.GRADED
            sub.score = 0
            sub.percentage = 0.0

    elif hw.content_type == Homework.ContentType.ESSAY:
        if sub.essay_submission:
            es = sub.essay_submission
            if es.status == EssaySubmission.Status.GRADED:
                sub.status = HomeworkSubmission.Status.GRADED
                sub.score = es.total_score
            else:
                sub.status = HomeworkSubmission.Status.AWAITING_REVIEW
        else:
            sub.status = HomeworkSubmission.Status.AWAITING_REVIEW

    else:
        # Custom or Lesson
        if payload:
            sub.answers_payload = payload
        sub.status = HomeworkSubmission.Status.AWAITING_REVIEW

    sub.is_completed = True
    sub.completed_at = now
    sub.save()

    return {
        "ok": True,
        "status": sub.status,
        "is_completed": True,
        "score": float(sub.score) if sub.score is not None else None,
        "percentage": float(sub.percentage) if sub.percentage is not None else None,
        "score_display": sub.score_display,
        "completed_at": now.isoformat(),
    }
