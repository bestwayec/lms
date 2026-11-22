"""
API views for the Unified Homework Engine (Stage 4):
- Student Homework Endpoints: list, detail, start, save, submit, result
- Teacher Homework Catalog: tests, essay topics, vocabulary packs, lessons
"""

from __future__ import annotations

import logging
from typing import Any

from django.db.models import Q
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.access import is_platform_admin
from apps.courses.homework_service import (
    HomeworkConflict,
    HomeworkNotFound,
    can_assign_essay_topic,
    can_assign_vocabulary_pack,
    get_student_homework_detail,
    get_student_homework_list,
    get_homework_live_board,
    get_student_homework_result,
    get_teacher_homework_roster,
    grade_custom_submission,
    save_student_homework_progress,
    start_student_homework,
    submit_student_homework,
)
from apps.courses.models import Homework
from apps.courses.teacher_workspace_service import get_teacher_groups
from apps.essays.models import EssayTopic
from apps.tests.models import Test
from apps.webapi.permissions import IsTeacherOrAdmin

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Student Homework Endpoints
# ---------------------------------------------------------------------------


def _service_call(fn, *args, success_status=status.HTTP_200_OK, **kwargs):
    """Map service exceptions to HTTP without leaking internals.

    HomeworkNotFound (non-recipient or missing) → 404, never 403, so ids
    cannot be probed; HomeworkConflict → 409 with a stable ``code``.
    """
    try:
        return Response(fn(*args, **kwargs), status=success_status)
    except HomeworkNotFound as exc:
        return Response({"detail": str(exc), "code": "not_found"}, status=status.HTTP_404_NOT_FOUND)
    except HomeworkConflict as exc:
        return Response({"detail": str(exc), "code": exc.code}, status=status.HTTP_409_CONFLICT)
    except PermissionError as exc:
        return Response({"detail": str(exc), "code": "forbidden"}, status=status.HTTP_403_FORBIDDEN)
    except ValueError as exc:
        return Response({"detail": str(exc), "code": "invalid"}, status=status.HTTP_400_BAD_REQUEST)


def _answers_from(request):
    payload = request.data.get("answers", request.data) if hasattr(request.data, "get") else request.data
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        payload = {"answers": payload}
    return payload


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def student_homeworks_view(request):
    """GET /api/v1/school/student/homeworks/?status=all|pending|completed|overdue — read-only."""
    items = get_student_homework_list(request.user, status_filter=request.GET.get("status"))
    return Response({"results": items, "count": len(items)})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def student_homework_detail_view(request, homework_id: int):
    """GET /api/v1/school/student/homeworks/<id>/ — read-only."""
    return _service_call(get_student_homework_detail, request.user, homework_id)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def student_homework_start_view(request, homework_id: int):
    """POST …/<id>/start/ — start or resume (current recipients only)."""
    return _service_call(start_student_homework, request.user, homework_id)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def student_homework_save_view(request, homework_id: int):
    """POST …/<id>/save/ — autosave; 409 after finish or deadline."""
    return _service_call(save_student_homework_progress, request.user, homework_id, _answers_from(request))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def student_homework_submit_view(request, homework_id: int):
    """POST …/<id>/submit/ — finish via the official grader. Idempotent."""
    return _service_call(submit_student_homework, request.user, homework_id, _answers_from(request))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def student_homework_result_view(request, homework_id: int):
    """GET …/<id>/result/ — authoritative outcome of finished work."""
    return _service_call(get_student_homework_result, request.user, homework_id)


@api_view(["GET"])
@permission_classes([IsTeacherOrAdmin])
def teacher_homework_roster_view(request, homework_id: int):
    """GET /api/v1/school/teacher/homeworks/<id>/roster/ — per-student authoritative status."""
    return _service_call(get_teacher_homework_roster, request.user, homework_id)


@api_view(["GET"])
@permission_classes([IsTeacherOrAdmin])
def teacher_homework_live_view(request, homework_id: int):
    """GET …/teacher/homeworks/<id>/live/ — live tablo; If-None-Match → 304."""
    try:
        data = get_homework_live_board(request.user, homework_id)
    except HomeworkNotFound as exc:
        return Response({"detail": str(exc), "code": "not_found"}, status=status.HTTP_404_NOT_FOUND)
    etag = f'"{data["revision"]}"'
    if request.headers.get("If-None-Match") == etag:
        resp = Response(status=status.HTTP_304_NOT_MODIFIED)
    else:
        resp = Response(data)
    resp["ETag"] = etag
    resp["Cache-Control"] = "private, no-cache"
    return resp


@api_view(["POST"])
@permission_classes([IsTeacherOrAdmin])
def teacher_grade_submission_view(request, submission_id: int):
    """POST /api/v1/school/teacher/homework-submissions/<id>/grade/ — custom/lesson work only."""

    def _grade():
        sub = grade_custom_submission(
            request.user,
            submission_id,
            score=request.data.get("score"),
            max_score=request.data.get("max_score"),
            feedback=str(request.data.get("feedback") or ""),
        )
        return {
            "id": sub.id,
            "status": sub.status,
            "score": float(sub.score),
            "max_score": float(sub.max_score),
            "percentage": sub.percentage,
            "feedback": sub.feedback,
        }

    return _service_call(_grade)


# ---------------------------------------------------------------------------
# Teacher Homework Catalog (Wizard Content Selector)
# ---------------------------------------------------------------------------


@api_view(["GET"])
@permission_classes([IsTeacherOrAdmin])
def teacher_homework_catalog_view(request):
    """
    GET /api/v1/school/teacher/homework-catalog/
    Returns content available for assigning:
    - Tests (strictly published only, owned or official)
    - Essay topics (active topics)
    - Vocabulary packs (if vocabulary app is available)
    - Lessons (from teacher's courses)
    """
    user = request.user
    content_type = request.GET.get("content_type", "all").lower()

    response_data: dict[str, list[dict[str, Any]]] = {
        "tests": [],
        "essays": [],
        "vocabulary": [],
        "lessons": [],
    }

    # 1. Tests (STRICTLY PUBLISHED ONLY)
    if content_type in ("all", "test"):
        tests_qs = Test.objects.filter(status=Test.Status.PUBLISHED)
        if not is_platform_admin(user):
            tests_qs = tests_qs.filter(
                models_q_for_teacher_tests(user)
            )

        response_data["tests"] = [
            {
                "id": t.id,
                "title": t.title,
                "subject": getattr(t, "subject", ""),
                "time_limit": getattr(t, "time_limit_minutes", 0) or 0,
                "questions_count": t.questions.count(),
                "is_official": getattr(t, "access_type", "") == "PUBLIC",
            }
            for t in tests_qs[:100]
        ]

    # 2. Essays
    if content_type in ("all", "essay"):
        topics_qs = EssayTopic.objects.filter(is_active=True).select_related("created_by").order_by("-created_at")
        topics = [t for t in topics_qs[:200] if can_assign_essay_topic(user, t)][:50]
        response_data["essays"] = [
            {
                "id": topic.id,
                "title": topic.title,
                "subject": getattr(topic, "subject", ""),
                "min_words": getattr(topic, "word_limit_min", None),
                "max_words": getattr(topic, "word_limit_max", None),
            }
            for topic in topics
        ]

    # 3. Vocabulary
    if content_type in ("all", "vocabulary"):
        try:
            from apps.vocabulary.models import VocabularyPack

            packs_qs = VocabularyPack.objects.all().order_by("-created_at")
            if not is_platform_admin(user):
                packs_qs = packs_qs.filter(
                    Q(teacher=user) | Q(group__in=get_teacher_groups(user))
                )
            response_data["vocabulary"] = [
                {"id": p.id, "title": p.title, "words_count": p.word_count}
                for p in packs_qs[:50]
                if can_assign_vocabulary_pack(user, p)
            ]
        except ImportError:
            pass

    # 4. Lessons
    if content_type in ("all", "lesson"):
        from apps.courses.models import Lesson

        if is_platform_admin(user):
            lessons_qs = Lesson.objects.all()
        else:
            lessons_qs = Lesson.objects.filter(module__course__teacher=user)

        response_data["lessons"] = [
            {
                "id": les.id,
                "title": les.title,
                "course_title": les.module.course.title if les.module_id else "",
            }
            for les in lessons_qs.select_related("module__course")[:50]
        ]

    return Response(response_data)


def models_q_for_teacher_tests(user):
    from django.db.models import Q

    return (
        Q(created_by=user)
        | Q(course__teacher=user)
        | Q(access_type="PUBLIC")
    )
