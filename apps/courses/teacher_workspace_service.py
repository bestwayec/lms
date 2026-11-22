"""
Teacher Workspace 3.0 Service — High-performance aggregation for teacher dashboard:
- Primary Actions (Davomat olish, Uy vazifasi berish, Guruhlarim, Natijalar)
- Today's lessons schedule with AttendanceSession integration
- Homework assignments & upcoming deadlines
- Review queues (pending essays & submissions)
- Backward-compatible statistics for teacher overview
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from django.db.models import Avg, F, Q
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.accounts.access import is_platform_admin
from apps.attendance.models import AttendanceSession
from apps.courses.models import Homework, StudentGroup
from apps.essays.models import EssaySubmission, EssayTopic
from apps.results.models import Result
from apps.tests.models import Test

logger = logging.getLogger(__name__)


def get_teacher_groups(user):
    """Return queryset of groups accessible to the teacher or admin."""
    if is_platform_admin(user):
        return StudentGroup.objects.all()
    if getattr(user, "role", None) == "center_admin":
        scope = Q(branch__director=user) | Q(branch__center__owner=user)
        if getattr(user, "branch_id", None):
            scope |= Q(branch_id=user.branch_id)
        if getattr(user, "learning_center_id", None):
            scope |= Q(branch__center_id=user.learning_center_id)
        return StudentGroup.objects.filter(scope).distinct()
    return StudentGroup.objects.filter(teacher=user)


def get_teacher_workspace_overview(user) -> dict[str, Any]:
    """
    Build the complete Teacher Workspace 3.0 overview payload.
    Provides data for the 4 primary action cards and operational streams:
      1. Davomat olish (today's lessons, attendance sessions & statuses)
      2. Uy vazifasi berish (assignments, upcoming deadlines, completion rates)
      3. Guruhlarim (groups list, student counts, invites)
      4. Natijalar (recent submissions, BMB scores, review queue)
    """
    groups_qs = get_teacher_groups(user).prefetch_related("students")
    groups_list = list(groups_qs)
    student_ids: set[int] = set()
    for g in groups_list:
        student_ids.update(g.students.values_list("id", flat=True))

    now = timezone.now()
    today = timezone.localdate()

    # 1. Today's Lessons & Attendance Workspace
    sessions_today = (
        AttendanceSession.objects.filter(group__in=groups_list, lesson_date=today)
        .exclude(status=AttendanceSession.Status.CANCELLED)
        .select_related("group")
        .prefetch_related("records")
    )
    sessions_by_group: dict[int, AttendanceSession] = {
        s.group_id: s for s in sessions_today
    }

    today_lessons = []
    for g in groups_list:
        sess = sessions_by_group.get(g.id)
        st_count = g.students.count()
        if sess:
            records = list(sess.records.all())
            pres_count = sum(1 for r in records if r.status == "present")
            abs_count = sum(1 for r in records if r.status == "absent")
            late_count = sum(1 for r in records if r.status == "late")
            exc_count = sum(1 for r in records if r.status == "excused")
            today_lessons.append(
                {
                    "session_id": sess.id,
                    "group_id": g.id,
                    "group_name": g.name,
                    "lesson_date": str(today),
                    "start_time": (
                        sess.start_time.strftime("%H:%M")
                        if sess.start_time
                        else None
                    ),
                    "end_time": (
                        sess.end_time.strftime("%H:%M")
                        if sess.end_time
                        else None
                    ),
                    "status": sess.status,
                    "title": sess.title,
                    "student_count": st_count,
                    "present_count": pres_count,
                    "absent_count": abs_count,
                    "late_count": late_count,
                    "excused_count": exc_count,
                    "unmarked_count": max(0, st_count - len(records)),
                }
            )
        else:
            today_lessons.append(
                {
                    "session_id": None,
                    "group_id": g.id,
                    "group_name": g.name,
                    "lesson_date": str(today),
                    "start_time": None,
                    "end_time": None,
                    "status": "not_started",
                    "title": "",
                    "student_count": st_count,
                    "present_count": 0,
                    "absent_count": 0,
                    "late_count": 0,
                    "excused_count": 0,
                    "unmarked_count": st_count,
                }
            )

    attendance_today_summary = {
        "total_groups": len(groups_list),
        "today_sessions_count": len(sessions_today),
        "finalized_count": sum(
            1
            for s in sessions_today
            if s.status == AttendanceSession.Status.FINALIZED
        ),
        "draft_count": sum(
            1
            for s in sessions_today
            if s.status == AttendanceSession.Status.DRAFT
        ),
        "not_started_count": max(0, len(groups_list) - len(sessions_today)),
    }

    # 2. Homework Assignments & Upcoming Deadlines
    homework_qs = (
        Homework.objects.filter(group__in=groups_list)
        .exclude(status=Homework.Status.CANCELLED)
        .select_related("group", "test", "essay_topic")
        .order_by("-created_at")[:25]
    )
    assignments = []
    for hw in homework_qs:
        total_students = hw.group.students.count()
        if hw.test_id:
            completed_count = (
                Result.objects.filter(
                    test_id=hw.test_id, student__in=hw.group.students.all()
                )
                .values("student_id")
                .distinct()
                .count()
            )
        elif hw.essay_topic_id:
            completed_count = (
                EssaySubmission.objects.filter(
                    topic_id=hw.essay_topic_id,
                    student__in=hw.group.students.all(),
                )
                .values("student_id")
                .distinct()
                .count()
            )
        else:
            completed_count = hw.submissions.filter(is_completed=True).count()

        is_overdue = hw.due_date < now
        assignments.append(
            {
                "id": hw.id,
                "title": hw.title,
                "description": hw.description,
                "group_id": hw.group_id,
                "group_name": hw.group.name,
                "due_date": hw.due_date.isoformat(),
                "is_overdue": is_overdue,
                "type": (
                    "test"
                    if hw.test_id
                    else ("essay" if hw.essay_topic_id else "custom")
                ),
                "test_id": hw.test_id,
                "test_title": hw.test.title if hw.test else None,
                "essay_topic_id": hw.essay_topic_id,
                "essay_topic_title": (
                    hw.essay_topic.title if hw.essay_topic else None
                ),
                "submissions_count": completed_count,
                "total_students": total_students,
                "created_at": hw.created_at.isoformat(),
            }
        )

    # Upcoming deadlines: filter non-overdue and sort by due_date ascending
    upcoming_deadlines = sorted(
        [a for a in assignments if not a["is_overdue"]],
        key=lambda x: x["due_date"],
    )[:10]

    # 3. Review Queue (Essays & submissions requiring teacher grading)
    _graded_statuses = [
        EssaySubmission.Status.GRADED,
        EssaySubmission.Status.TEACHER_REVIEWED,
    ]
    essay_pending_qs = EssaySubmission.objects.filter(
        status=EssaySubmission.Status.PENDING_TEACHER
    )
    essay_graded_qs = EssaySubmission.objects.filter(
        status__in=_graded_statuses
    )

    if not is_platform_admin(user) and student_ids:
        essay_pending_qs = essay_pending_qs.filter(student_id__in=student_ids)
        essay_graded_qs = essay_graded_qs.filter(student_id__in=student_ids)
    elif not is_platform_admin(user) and not student_ids:
        essay_pending_qs = essay_pending_qs.none()
        essay_graded_qs = essay_graded_qs.none()

    essay_pending_count = essay_pending_qs.count()
    essay_graded_count = essay_graded_qs.count()
    essay_avg = essay_graded_qs.aggregate(
        avg=Avg(Coalesce(F("final_score"), F("total_score")))
    )["avg"]

    pending_items = essay_pending_qs.select_related(
        "student", "topic"
    ).order_by("-submitted_at")[:15]
    review_queue = [
        {
            "id": item.id,
            "student_id": item.student_id,
            "student_name": item.student.get_full_name() or item.student.email,
            "topic_title": item.topic.title if item.topic else "Esse topshirig'i",
            "submitted_at": (
                item.submitted_at.isoformat()
                if item.submitted_at
                else (
                    item.teacher_review_requested_at.isoformat()
                    if getattr(item, "teacher_review_requested_at", None)
                    else (
                        item.updated_at.isoformat()
                        if getattr(item, "updated_at", None)
                        else ""
                    )
                )
            ),
            "word_count": getattr(item, "word_count", 0) or 0,
            "total_score": (
                float(item.total_score)
                if getattr(item, "total_score", None) is not None
                else None
            ),
        }
        for item in pending_items
    ]

    # 4. Results & Tests
    if is_platform_admin(user):
        results_qs = Result.objects.all()
        tests_qs = Test.objects.filter(status=Test.Status.PUBLISHED)
    else:
        results_qs = Result.objects.filter(test__course__teacher=user)
        tests_qs = Test.objects.filter(
            course__teacher=user, status=Test.Status.PUBLISHED
        )

    recent = results_qs.select_related("test", "student", "attempt").order_by(
        "-calculated_at"
    )[:12]

    from apps.webapi.serializers import StudentGroupSerializer

    return {
        # Core Stage 3c additions:
        "today_lessons": today_lessons,
        "assignments": assignments,
        "upcoming_deadlines": upcoming_deadlines,
        "review_queue": review_queue,
        "review_queue_count": essay_pending_count,
        "attendance_today_summary": attendance_today_summary,
        # Existing & backward-compatible overview contract:
        "groups": StudentGroupSerializer(groups_list, many=True).data,
        "student_count": len(student_ids),
        "published_tests": tests_qs.count(),
        "active_topics": EssayTopic.objects.filter(is_active=True).count(),
        "essay_pending": essay_pending_count,
        "essay_graded": essay_graded_count,
        "essay_avg_score": round(float(essay_avg or 0), 1),
        "recent_results": [
            {
                "student": r.student.get_full_name() or r.student.email,
                "test": r.test.title,
                "subject": r.test.subject,
                "percentage": float(r.percentage),
                "is_passed": r.is_passed,
                "cheating_detected": bool(
                    getattr(r.attempt, "cheating_detected", False)
                )
                if getattr(r, "attempt", None)
                else False,
                "violation_count": int(
                    getattr(r.attempt, "violation_count", 0) or 0
                )
                if getattr(r, "attempt", None)
                else 0,
                "date": r.calculated_at.isoformat(),
            }
            for r in recent
        ],
    }


def create_teacher_homework(
    user,
    *,
    group_id: int | None = None,
    student_id: int | None = None,
    title: str,
    due_date: datetime,
    description: str = "",
    test_id: int | None = None,
    essay_topic_id: int | None = None,
    vocabulary_pack_id: int | None = None,
    lesson_id: int | None = None,
    start_date: datetime | None = None,
    time_limit: int = 0,
    max_attempts: int = 1,
    idempotency_key: str | None = None,
) -> Homework:
    """
    Assign a homework (Test, Essay, Vocabulary, Lesson, or Custom) to a teacher's group or individual student.
    Ensures authorization, valid future deadlines, and cross-model synchronization.
    """
    from apps.courses.homework_service import create_unified_homework

    hw, _ = create_unified_homework(
        user,
        title=title,
        due_date=due_date,
        group_id=group_id,
        student_id=student_id,
        description=description,
        test_id=test_id,
        essay_topic_id=essay_topic_id,
        vocabulary_pack_id=vocabulary_pack_id,
        lesson_id=lesson_id,
        start_date=start_date,
        time_limit=time_limit,
        max_attempts=max_attempts,
        idempotency_key=idempotency_key,
    )
    return hw


def delete_teacher_homework(user, homework_id: int) -> bool:
    """Safely cancel a homework assigned to a group (preserves submissions & grades)."""
    from apps.courses.homework_service import cancel_teacher_homework

    cancel_teacher_homework(user, homework_id)
    return True
