"""Teacher Studio JSON API (``/api/v1/teacher/studio/…``).

Teachers (and platform admins) only; a teacher sees and edits only tests
they created. Errors carry a machine-readable ``code`` the UI translates.
"""

from __future__ import annotations

from typing import Any

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes, throttle_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from apps.tests import studio_service as svc
from apps.tests.models import Test
from apps.tests.studio_parser import MAX_TEXT_CHARS, parse_smart_paste


class IsStudioTeacher(BasePermission):
    message = "Teacher access required."

    def has_permission(self, request, view) -> bool:
        return svc.is_teacher(request.user)


class _MediaThrottle(UserRateThrottle):
    rate = "60/hour"


def _err(e: svc.StudioError) -> Response:
    code = status.HTTP_409_CONFLICT if isinstance(e, svc.StudioConflict) else status.HTTP_400_BAD_REQUEST
    return Response({"code": e.code, "detail": str(e), **e.extra}, status=code)


def _own_test(request, test_id: int) -> Test:
    return get_object_or_404(svc.teacher_tests(request.user), id=test_id)


def _detail(test: Test) -> dict[str, Any]:
    blocks = svc.load_blocks(test)
    return {
        "test": svc.summarize_test(test),
        "blocks": blocks,
        "issues": svc.validate_blocks(svc.normalize_blocks(_without_urls(blocks))),
        "assignments": svc.assignments_for(test),
        "links": svc.share_links(test),
    }


def _without_urls(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{k: v for k, v in b.items() if k not in ("audio_url", "image_url")} for b in blocks]


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsStudioTeacher])
def studio_parse_view(request):
    text = request.data.get("text", "")
    if not isinstance(text, str) or not text.strip():
        return Response({"code": "text_required"}, status=400)
    if len(text) > MAX_TEXT_CHARS:
        return Response({"code": "text_too_long", "max": MAX_TEXT_CHARS}, status=400)
    return Response(parse_smart_paste(text, str(request.data.get("section") or "GENERAL")))


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsStudioTeacher])
def studio_validate_view(request):
    try:
        blocks = svc.normalize_blocks(request.data.get("blocks"))
    except svc.StudioError as e:
        return _err(e)
    return Response({"issues": svc.validate_blocks(blocks)})


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated, IsStudioTeacher])
def studio_tests_view(request):
    if request.method == "POST":
        try:
            test = svc.save_test(request.user, request.data)
        except svc.StudioError as e:
            return _err(e)
        return Response(_detail(test), status=201)

    from django.db.models import Count, Q

    tests = (
        svc.teacher_tests(request.user)
        .annotate(
            question_count=Count("questions", distinct=True),
            attempt_count=Count(
                "attempts",
                filter=Q(attempts__is_preview=False, attempts__status__in=["completed", "timeout", "pending_grading"]),
                distinct=True,
            ),
            foreign_count=Count(
                "questions", filter=~Q(questions__config__has_key="studio_type"), distinct=True
            ),
        )
        .order_by("-updated_at")[:100]
    )
    return Response(
        [
            {
                "id": t.id,
                "title": t.title,
                "subject": t.subject,
                "status": t.status,
                "mock_code": t.mock_code or "",
                "questions": t.question_count,
                "attempts": t.attempt_count,
                "is_studio": t.foreign_count == 0,
                "updated_at": t.updated_at.isoformat() if t.updated_at else None,
            }
            for t in tests
        ]
    )


@api_view(["GET", "PUT"])
@permission_classes([IsAuthenticated, IsStudioTeacher])
def studio_test_detail_view(request, test_id: int):
    test = _own_test(request, test_id)
    if request.method == "PUT":
        try:
            test = svc.save_test(request.user, request.data, test=test)
        except svc.StudioError as e:
            return _err(e)
    return Response(_detail(test))


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsStudioTeacher])
def studio_publish_view(request, test_id: int):
    test = _own_test(request, test_id)
    ok, issues = svc.publish_test(test)
    if not ok:
        return Response({"code": "invalid", "issues": issues}, status=400)
    test.refresh_from_db()
    return Response(_detail(test))


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsStudioTeacher])
def studio_assign_view(request, test_id: int):
    test = _own_test(request, test_id)
    try:
        payload = svc.assign_test(request.user, test, request.data.get("group_id"), request.data.get("due_at"))
    except svc.StudioError as e:
        return _err(e)
    return Response(payload, status=201)


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsStudioTeacher])
def studio_analysis_view(request, test_id: int):
    test = _own_test(request, test_id)
    group = None
    group_id = request.query_params.get("group")
    if group_id:
        from apps.courses.models import StudentGroup

        try:
            group = svc.teacher_groups(request.user).get(id=int(group_id))
        except (TypeError, ValueError, StudentGroup.DoesNotExist):
            return Response({"code": "group_not_found"}, status=404)
    data = svc.item_analysis(test, group=group)
    data["assignments"] = svc.assignments_for(test)
    return Response(data)


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsStudioTeacher])
@parser_classes([MultiPartParser, FormParser, JSONParser])
@throttle_classes([_MediaThrottle])
def studio_media_view(request):
    upload = request.FILES.get("file")
    if upload is None:
        return Response({"code": "file_required"}, status=400)
    try:
        stored = svc.store_media(upload, str(request.data.get("kind") or ""))
    except svc.StudioError as e:
        return _err(e)
    return Response(stored, status=201)
