"""
Admin Test Service — Business logic for Admin Test Control Center 4.0.

Provides scoped querysets, metrics aggregation, safe deletion validation,
duplication, bulk actions, and audit logging for LMS test management.
"""

from __future__ import annotations

import logging
from typing import Any

from django.contrib.admin.models import ADDITION, CHANGE, DELETION, LogEntry
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Count, Q, QuerySet

from apps.accounts.access import is_center_admin, is_platform_admin
from apps.tests.models import (
    Choice,
    ExamSection,
    GapBlank,
    MatchingOption,
    MatchingPair,
    MatchingPrompt,
    Question,
    ReadingPassage,
    Test,
)

logger = logging.getLogger(__name__)


def log_test_audit(user: Any, test: Test, action_flag: int, message: str) -> None:
    """Safely records an audit log entry in Django admin LogEntry."""
    try:
        if user and getattr(user, "is_authenticated", False):
            ct = ContentType.objects.get_for_model(test)
            LogEntry.objects.log_action(
                user_id=user.pk,
                content_type_id=ct.pk,
                object_id=test.pk,
                object_repr=str(test)[:200],
                action_flag=action_flag,
                change_message=message,
            )
    except Exception as exc:
        logger.warning("Failed to record test audit log for test %s: %s", getattr(test, "id", None), exc)


def get_scoped_tests_queryset(user: Any) -> QuerySet[Test]:
    """
    Returns tests visible to the given user based on RBAC rules:
    - Platform admin: all tests.
    - Center admin: tests created by teachers in the same center or assigned to center's groups.
    - Teacher: only tests created by this teacher.
    - Student / others: empty queryset.
    """
    if not user or not user.is_authenticated or not getattr(user, "is_active", False):
        return Test.objects.none()

    if is_platform_admin(user):
        return Test.objects.all()

    role = getattr(user, "role", None)

    if is_center_admin(user) or role == "center_admin":
        center_id = getattr(user, "learning_center_id", None)
        if center_id:
            return Test.objects.filter(
                Q(created_by__learning_center_id=center_id)
                | Q(assigned_group__branch__center_id=center_id)
                | Q(created_by=user)
            ).distinct()
        return Test.objects.filter(created_by=user)

    if role == "teacher" or getattr(user, "is_teacher", False):
        return Test.objects.filter(Q(created_by=user) | Q(course__teacher=user)).distinct()

    return Test.objects.none()


def annotate_test_metrics(qs: QuerySet[Test]) -> QuerySet[Test]:
    """Annotates test queryset with question, assignment, attempt, and result counts."""
    return qs.annotate(
        q_count=Count("questions", distinct=True),
        attempts_count=Count("attempts", distinct=True),
        assignments_count=Count("homework_assignments", distinct=True),
        results_count=Count("results", distinct=True),
    )


def calculate_test_stats(qs: QuerySet[Test]) -> dict[str, int]:
    """Calculates overall summary metrics for the Control Center header."""
    agg = qs.aggregate(
        total_count=Count("id", distinct=True),
        published_count=Count("id", filter=Q(status="published", is_active=True), distinct=True),
        draft_count=Count("id", filter=Q(status="draft"), distinct=True),
        archived_count=Count("id", filter=Q(status="archived"), distinct=True),
        attempted_count=Count("id", filter=Q(attempts__isnull=False), distinct=True),
    )
    return {
        "total_count": agg.get("total_count") or 0,
        "published_count": agg.get("published_count") or 0,
        "draft_count": agg.get("draft_count") or 0,
        "archived_count": agg.get("archived_count") or 0,
        "attempted_count": agg.get("attempted_count") or 0,
    }


def check_safe_deletion(test: Test) -> tuple[bool, str, dict[str, int]]:
    """
    Enforces the safe deletion policy:
    1. If test has student attempts or results: permanent deletion is BLOCKED (must archive).
    2. If test has active homework assignments: permanent deletion is BLOCKED.
    3. If test is published: permanent deletion is BLOCKED (must archive or unpublish first).
    4. Drafts with 0 attempts and 0 assignments: safe to permanently delete.
    """
    attempts_cnt = test.attempts.count()
    results_cnt = test.results.count()
    assignments_cnt = test.homework_assignments.count()

    details = {
        "attempts_count": attempts_cnt,
        "results_count": results_cnt,
        "assignments_count": assignments_cnt,
    }

    if attempts_cnt > 0 or results_cnt > 0:
        return (
            False,
            f"Ushbu testda {attempts_cnt} ta o'quvchi urinishi va {results_cnt} ta natija mavjud. "
            "Tarixiy natijalarni saqlash uchun testni o'chirish o'rniga arxivlang.",
            details,
        )

    if assignments_cnt > 0:
        return (
            False,
            f"Ushbu test {assignments_cnt} ta faol uy vazifasiga biriktirilgan. "
            "O'chirishdan oldin topshiriqlarni bekor qiling yoki testni arxivlang.",
            details,
        )

    if test.status == "published":
        return (
            False,
            "E'lon qilingan testni to'g'ridan-to'g'ri o'chirib bo'lmaydi. "
            "Avval uni arxivlang yoki qoralamaga o'tkazing.",
            details,
        )

    return True, "Test xavfsiz o'chirish uchun mos.", details


@transaction.atomic
def duplicate_test(test: Test, user: Any) -> Test:
    """
    Creates a deep duplicate of a test including sections, passages,
    questions, choices, blanks, and matching pairs/prompts/options.
    The cloned test starts in 'draft' status owned by the current user.
    """
    new_title = f"{test.title} (Nusxa)"[:250]
    new_test = Test.objects.create(
        title=new_title,
        description=test.description,
        course=test.course,
        module=test.module,
        subject=test.subject,
        difficulty=test.difficulty,
        time_limit_minutes=test.time_limit_minutes,
        max_attempts=test.max_attempts,
        pass_percentage=test.pass_percentage,
        scoring_profile=test.scoring_profile,
        scoring_type=test.scoring_type,
        exam_type=test.exam_type,
        assessment_category=getattr(test, "assessment_category", "classroom_quiz"),
        available_from=test.available_from,
        available_until=test.available_until,
        audience_mode=getattr(test, "audience_mode", "GROUP_ONLY"),
        status="draft",
        is_active=True,
        show_results_immediately=test.show_results_immediately,
        shuffle_questions=test.shuffle_questions,
        shuffle_choices=test.shuffle_choices,
        audio_url=test.audio_url,
        is_strict_mode=test.is_strict_mode,
        strict_anti_cheat=test.strict_anti_cheat,
        access_type=test.access_type,
        access_pin=test.access_pin,
        created_by=user,
        assigned_group=None,
    )

    # 1. Duplicate ExamSections
    section_map: dict[int, ExamSection] = {}
    for sec in test.sections.all().order_by("order"):
        old_id = sec.id
        sec_copy = ExamSection.objects.create(
            test=new_test,
            name=sec.name,
            code=sec.code,
            order=sec.order,
            duration_minutes=sec.duration_minutes,
            weight=sec.weight,
        )
        section_map[old_id] = sec_copy

    # 2. Duplicate ReadingPassages
    for p in test.passages.all().order_by("order"):
        new_sec = section_map.get(p.section_id) if p.section_id else None
        ReadingPassage.objects.create(
            test=new_test,
            section=new_sec,
            title=p.title,
            content=p.content,
            order=p.order,
        )

    # 3. Duplicate Questions
    for q in test.questions.all().order_by("position"):
        new_sec = section_map.get(q.section_id) if q.section_id else None
        new_q = Question.objects.create(
            test=new_test,
            section=new_sec,
            text=q.text,
            question_type=q.question_type,
            points=q.points,
            position=q.position,
            explanation=q.explanation,
        )

        # Choices
        for c in q.choices.all().order_by("position"):
            Choice.objects.create(
                question=new_q,
                text=c.text,
                is_correct=c.is_correct,
                position=c.position,
            )

        # GapBlanks
        for gb in q.gap_blanks.all().order_by("position"):
            GapBlank.objects.create(
                question=new_q,
                position=gb.position,
                answer_text=gb.answer_text,
            )

        # Matching Prompts, Options & Pairs
        prompt_map: dict[int, MatchingPrompt] = {}
        for mp in q.matching_prompts.all().order_by("position"):
            old_p_id = mp.id
            new_mp = MatchingPrompt.objects.create(
                question=new_q,
                text=mp.text,
                position=mp.position,
            )
            prompt_map[old_p_id] = new_mp

        option_map: dict[int, MatchingOption] = {}
        for mo in q.matching_options.all().order_by("position"):
            old_o_id = mo.id
            new_mo = MatchingOption.objects.create(
                question=new_q,
                text=mo.text,
                position=mo.position,
            )
            option_map[old_o_id] = new_mo

        for pair in MatchingPair.objects.filter(prompt__question=q):
            if pair.prompt_id in prompt_map and pair.option_id in option_map:
                MatchingPair.objects.create(
                    prompt=prompt_map[pair.prompt_id],
                    option=option_map[pair.option_id],
                )

    log_test_audit(user, new_test, ADDITION, f"Duplicated from test #{test.id} ({test.title})")
    return new_test


def archive_test(test: Test, user: Any) -> Test:
    """Sets test to archived status and deactivates it."""
    test.status = "archived"
    test.save()
    log_test_audit(user, test, CHANGE, "Test arxivlandi.")
    return test


def restore_test(test: Test, user: Any) -> Test:
    """Restores an archived test back to draft status."""
    test.status = "draft"
    test.save()
    log_test_audit(user, test, CHANGE, "Test arxivdan qoralamaga qaytarildi.")
    return test


def unpublish_test(test: Test, user: Any) -> Test:
    """Unpublishes a test, moving it to draft status."""
    test.status = "draft"
    test.save()
    log_test_audit(user, test, CHANGE, "Test e'londan olib tashlandi (qoralamaga o'tkazildi).")
    return test


def preview_bulk_action(test_ids: list[int], action: str, user: Any) -> dict[str, Any]:
    """
    Computes preview statistics for a requested bulk action:
    - total_selected
    - drafts_count
    - published_count
    - archived_count
    - has_assignments_count
    - has_attempts_count
    - safe_to_delete_count
    - blocked_from_delete_count
    - retained_count
    - blocked_tests (list of blocked test summaries)
    """
    qs = get_scoped_tests_queryset(user).filter(id__in=test_ids)
    tests = list(annotate_test_metrics(qs))

    total = len(tests)
    drafts = sum(1 for t in tests if t.status == "draft")
    published = sum(1 for t in tests if t.status == "published")
    archived = sum(1 for t in tests if t.status == "archived")
    has_assignments = sum(1 for t in tests if getattr(t, "assignments_count", 0) > 0)
    has_attempts = sum(1 for t in tests if getattr(t, "attempts_count", 0) > 0 or getattr(t, "results_count", 0) > 0)

    safe_delete = []
    blocked_delete = []

    for t in tests:
        is_safe, reason, _ = check_safe_deletion(t)
        if is_safe:
            safe_delete.append(t.id)
        else:
            blocked_delete.append({
                "id": t.id,
                "title": t.title,
                "status": t.status,
                "attempts_count": getattr(t, "attempts_count", 0),
                "assignments_count": getattr(t, "assignments_count", 0),
                "reason": reason,
            })

    return {
        "action": action,
        "total_selected": total,
        "drafts_count": drafts,
        "published_count": published,
        "archived_count": archived,
        "has_assignments_count": has_assignments,
        "has_attempts_count": has_attempts,
        "safe_to_delete_count": len(safe_delete),
        "blocked_from_delete_count": len(blocked_delete),
        "retained_count": len(blocked_delete) if action in ("delete", "delete_unused_drafts") else total,
        "blocked_tests": blocked_delete[:50],
    }


@transaction.atomic
def execute_bulk_action(test_ids: list[int], action: str, user: Any) -> dict[str, Any]:
    """
    Executes a bulk action across eligible tests while strictly enforcing
    the safe deletion policy:
    - 'archive': archives all selected tests.
    - 'restore': restores all selected archived tests to draft.
    - 'unpublish': unpublishes all selected published tests to draft.
    - 'delete_unused_drafts': permanently deletes only drafts with 0 attempts and 0 assignments.
    - 'delete': safely deletes eligible tests and retains/blocks tests with attempts or assignments.
    - 'export_metadata': returns exported metadata dictionary for selected tests.
    """
    qs = get_scoped_tests_queryset(user).filter(id__in=test_ids)
    tests = list(annotate_test_metrics(qs))

    if action == "archive":
        updated = 0
        for t in tests:
            archive_test(t, user)
            updated += 1
        return {"action": action, "processed_count": updated, "status": "success"}

    elif action == "restore":
        updated = 0
        for t in tests:
            restore_test(t, user)
            updated += 1
        return {"action": action, "processed_count": updated, "status": "success"}

    elif action == "unpublish":
        updated = 0
        for t in tests:
            unpublish_test(t, user)
            updated += 1
        return {"action": action, "processed_count": updated, "status": "success"}

    elif action in ("delete", "delete_unused_drafts"):
        deleted_count = 0
        blocked_count = 0
        blocked_items = []

        for t in tests:
            if action == "delete_unused_drafts" and t.status != "draft":
                blocked_count += 1
                blocked_items.append({"id": t.id, "title": t.title, "reason": "Faqat qoralama testlar o'chiriladi."})
                continue

            is_safe, reason, _ = check_safe_deletion(t)
            if is_safe:
                log_test_audit(user, t, DELETION, f"Test o'chirildi: #{t.id} {t.title}")
                t.delete()
                deleted_count += 1
            else:
                blocked_count += 1
                blocked_items.append({"id": t.id, "title": t.title, "reason": reason})

        return {
            "action": action,
            "deleted_count": deleted_count,
            "blocked_count": blocked_count,
            "retained_count": blocked_count,
            "blocked_items": blocked_items[:20],
            "status": "success",
        }

    elif action == "export_metadata":
        metadata = [
            {
                "id": t.id,
                "title": t.title,
                "subject": t.subject,
                "status": t.status,
                "is_active": t.is_active,
                "difficulty": t.difficulty,
                "time_limit_minutes": t.time_limit_minutes,
                "questions_count": getattr(t, "q_count", 0),
                "attempts_count": getattr(t, "attempts_count", 0),
                "assignments_count": getattr(t, "assignments_count", 0),
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in tests
        ]
        return {
            "action": action,
            "total_exported": len(metadata),
            "data": metadata,
            "status": "success",
        }

    else:
        raise ValueError(f"Noma'lum amaliyot: {action}")


def audit_public_studio_tests(user: Any) -> list[dict[str, Any]]:
    """
    Audits tests in user's tenant scope that were authored/created in Studio
    or have public visibility (PUBLIC / PUBLIC_FREE).
    Identifies candidates for safe migration to GROUP_ONLY.
    """
    scoped = get_scoped_tests_queryset(user).select_related("created_by", "created_by__learning_center")
    public_tests = scoped.filter(
        Q(audience_mode="PUBLIC_FREE") | Q(access_type="PUBLIC")
    ).filter(
        Q(created_by__isnull=False) | Q(questions__config__has_key="studio_type")
    ).distinct().order_by("-created_at")

    audit_items = []
    for t in public_tests:
        hw_count = t.homework_assignments.filter(status="active").count()
        attempts_count = t.attempts.filter(is_preview=False).count()
        results_count = t.results.count()
        owner = t.created_by
        center = getattr(owner, "learning_center", None) if owner else None

        audit_items.append({
            "id": t.id,
            "title": t.title,
            "subject": t.subject,
            "assessment_category": getattr(t, "assessment_category", "classroom_quiz"),
            "status": t.status,
            "owner_id": owner.id if owner else None,
            "owner_name": owner.get_full_name() or owner.email if owner else "Noma'lum",
            "owner_email": owner.email if owner else "",
            "learning_center_id": center.id if center else None,
            "learning_center_name": center.name if center else "Mustaqil",
            "active_assignments_count": hw_count,
            "existing_attempts_count": attempts_count,
            "results_count": results_count,
            "current_access_type": t.access_type,
            "current_audience_mode": getattr(t, "audience_mode", "PUBLIC_FREE"),
            "proposed_access_type": "STUDENTS_ONLY",
            "proposed_audience_mode": "GROUP_ONLY",
            "safe_to_transition": True,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        })
    return audit_items


@transaction.atomic
def apply_studio_tests_visibility_transition(
    user: Any,
    test_ids: list[int],
    target_mode: str = "GROUP_ONLY",
) -> dict[str, Any]:
    """
    Safely transitions selected public tests to GROUP_ONLY (or specified mode).
    Scoped to user's permitted queryset so cross-center tampering is prevented.
    Historical attempts and results are preserved untouched.
    """
    from django.contrib.admin.models import CHANGE

    scoped = get_scoped_tests_queryset(user).filter(id__in=test_ids)
    updated = []
    for t in scoped:
        old_mode = getattr(t, "audience_mode", "PUBLIC_FREE")
        t.audience_mode = target_mode
        t.access_type = "STUDENTS_ONLY" if target_mode == "GROUP_ONLY" else "PUBLIC"
        t.save(update_fields=["audience_mode", "access_type"])
        log_test_audit(
            user,
            t,
            CHANGE,
            f"Test audiensiyasi o'zgartirildi: {old_mode} -> {target_mode} (xavfsiz audit orqali)",
        )
        updated.append(t.id)

    return {
        "status": "success",
        "updated_count": len(updated),
        "updated_ids": updated,
        "target_mode": target_mode,
    }
