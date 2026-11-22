"""
API views for the Unified Homework Engine (Stage 4):
- Student Homework Endpoints: list, detail, start, save, submit, result
- Teacher Homework Catalog: tests, essay topics, vocabulary packs, lessons
"""

from __future__ import annotations

import logging
from typing import Any

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.access import is_platform_admin
from apps.courses.homework_service import (
    get_student_homework_detail,
    get_student_homework_list,
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


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def student_homeworks_view(request):
    """
    GET /api/v1/school/student/homeworks/
    List all homework assignments authorized for the current student.
    Query params:
      - status: 'all' | 'pending' | 'completed' | 'overdue'
    """
    status_filter = request.GET.get("status")
    try:
        items = get_student_homework_list(
            request.user, status_filter=status_filter
        )
        return Response({"results": items, "count": len(items)})
    except Exception as exc:
        logger.exception("Error fetching student homework list")
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def student_homework_detail_view(request, homework_id: int):
    """
    GET /api/v1/school/student/homeworks/<id>/
    Get detailed specification of a homework assignment for the student.
    """
    try:
        data = get_student_homework_detail(request.user, homework_id)
        return Response(data)
    except PermissionError as pe:
        return Response({"detail": str(pe)}, status=status.HTTP_403_FORBIDDEN)
    except ValueError as ve:
        return Response({"detail": str(ve)}, status=status.HTTP_404_NOT_FOUND)
    except Exception as exc:
        logger.exception("Error fetching student homework detail: %s", homework_id)
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def student_homework_start_view(request, homework_id: int):
    """
    POST /api/v1/school/student/homeworks/<id>/start/
    Start or resume a homework attempt.
    """
    try:
        res = start_student_homework(request.user, homework_id)
        return Response(res, status=status.HTTP_200_OK)
    except PermissionError as pe:
        return Response({"detail": str(pe)}, status=status.HTTP_403_FORBIDDEN)
    except ValueError as ve:
        return Response({"detail": str(ve)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as exc:
        logger.exception("Error starting student homework: %s", homework_id)
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def student_homework_save_view(request, homework_id: int):
    """
    POST /api/v1/school/student/homeworks/<id>/save/
    Autosave student progress and draft answers.
    """
    payload = request.data.get("answers", request.data)
    if not isinstance(payload, dict):
        payload = {"answers": payload}
    try:
        res = save_student_homework_progress(request.user, homework_id, payload)
        return Response(res)
    except PermissionError as pe:
        return Response({"detail": str(pe)}, status=status.HTTP_403_FORBIDDEN)
    except ValueError as ve:
        return Response({"detail": str(ve)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as exc:
        logger.exception("Error saving student homework progress: %s", homework_id)
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def student_homework_submit_view(request, homework_id: int):
    """
    POST /api/v1/school/student/homeworks/<id>/submit/
    Submit homework for official grading. Idempotent.
    """
    payload = request.data.get("answers", request.data)
    if not isinstance(payload, dict):
        payload = {"answers": payload}
    try:
        res = submit_student_homework(request.user, homework_id, payload)
        return Response(res, status=status.HTTP_200_OK)
    except PermissionError as pe:
        return Response({"detail": str(pe)}, status=status.HTTP_403_FORBIDDEN)
    except ValueError as ve:
        return Response({"detail": str(ve)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as exc:
        logger.exception("Error submitting student homework: %s", homework_id)
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def student_homework_result_view(request, homework_id: int):
    """
    GET /api/v1/school/student/homeworks/<id>/result/
    View authoritative results, scores, and teacher feedback.
    """
    try:
        data = get_student_homework_detail(request.user, homework_id)
        if not data.get("is_completed") and data.get("status") not in (
            "graded",
            "awaiting_review",
            "submitted",
        ):
            return Response(
                {"detail": "Ushbu topshiriq hali yakunlanmagan."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {
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
            }
        )
    except PermissionError as pe:
        return Response({"detail": str(pe)}, status=status.HTTP_403_FORBIDDEN)
    except ValueError as ve:
        return Response({"detail": str(ve)}, status=status.HTTP_404_NOT_FOUND)


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
        topics_qs = EssayTopic.objects.filter(is_active=True).order_by("-created_at")
        response_data["essays"] = [
            {
                "id": topic.id,
                "title": topic.title,
                "task_type": getattr(topic, "task_type", ""),
                "min_words": getattr(topic, "min_words", 150),
                "max_words": getattr(topic, "max_words", 300),
            }
            for topic in topics_qs[:50]
        ]

    # 3. Vocabulary
    if content_type in ("all", "vocabulary"):
        try:
            from apps.vocabulary.models import VocabularyPack

            packs_qs = VocabularyPack.objects.all().order_by("-created_at")
            response_data["vocabulary"] = [
                {
                    "id": p.id,
                    "title": p.title,
                    "words_count": p.words.count() if hasattr(p, "words") else 0,
                }
                for p in packs_qs[:50]
            ]
        except ImportError:
            pass

    # 4. Lessons
    if content_type in ("all", "lesson"):
        from apps.courses.models import Course, Lesson

        if is_platform_admin(user):
            lessons_qs = Lesson.objects.all()
        else:
            lessons_qs = Lesson.objects.filter(course__teacher=user)

        response_data["lessons"] = [
            {
                "id": les.id,
                "title": les.title,
                "course_title": les.course.title if les.course else "",
            }
            for les in lessons_qs.select_related("course")[:50]
        ]

    return Response(response_data)


def models_q_for_teacher_tests(user):
    from django.db.models import Q

    return (
        Q(created_by=user)
        | Q(course__teacher=user)
        | Q(access_type="PUBLIC")
    )
