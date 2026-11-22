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

    search = request.query_params.get("q", "").strip()
    status_filter = request.query_params.get("status", "").strip().lower()
    subject_filter = request.query_params.get("subject", "").strip().lower()

    qs = svc.teacher_tests(request.user)
    if search:
        qs = qs.filter(Q(title__icontains=search) | Q(mock_code__icontains=search))
    if status_filter and status_filter != "all":
        qs = qs.filter(status=status_filter)
    if subject_filter and subject_filter != "all":
        qs = qs.filter(subject=subject_filter)

    tests = (
        qs.annotate(
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


@api_view(["GET", "PUT", "DELETE"])
@permission_classes([IsAuthenticated, IsStudioTeacher])
def studio_test_detail_view(request, test_id: int):
    test = _own_test(request, test_id)
    if request.method == "DELETE":
        try:
            svc.delete_draft_test(request.user, test)
        except svc.StudioError as e:
            return _err(e)
        return Response({"deleted": True}, status=200)
    if request.method == "PUT":
        try:
            test = svc.save_test(request.user, request.data, test=test)
        except svc.StudioError as e:
            return _err(e)
    return Response(_detail(test))


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsStudioTeacher])
def studio_duplicate_view(request, test_id: int):
    test = _own_test(request, test_id)
    try:
        new_test = svc.duplicate_test(request.user, test)
    except svc.StudioError as e:
        return _err(e)
    return Response(_detail(new_test), status=201)


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsStudioTeacher])
def studio_export_view(request, test_id: int):
    from django.http import HttpResponse

    test = _own_test(request, test_id)
    csv_data = svc.export_test_questions_csv(test)
    response = HttpResponse(csv_data, content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="test_{test.id}_questions.csv"'
    return response


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsStudioTeacher])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def studio_import_file_view(request):
    """Smart Import Pro: CSV/XLSX/DOCX/text-PDF/plain text → preview only (nothing saved)."""
    from apps.tests.import_extract import MAX_UPLOAD_BYTES

    section = str(request.data.get("section") or "GENERAL")
    upload = request.FILES.get("file")
    if upload is not None:
        if upload.size and upload.size > MAX_UPLOAD_BYTES:
            return Response({"code": "file_too_large", "limit_mb": MAX_UPLOAD_BYTES // (1024 * 1024)}, status=400)
        data = upload.read(MAX_UPLOAD_BYTES + 1)
        name = upload.name or ""
    elif "content" in request.data:
        data = str(request.data["content"]).encode("utf-8")
        name = "pasted.csv"
    else:
        return Response({"code": "file_or_content_required"}, status=400)
    try:
        result = svc.import_test_file(data, name, default_section=section)
    except svc.StudioError as e:
        return _err(e)
    return Response(result, status=200)


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
        payload = svc.assign_test(
            user=request.user,
            test=test,
            group_id=request.data.get("group_id"),
            due_at=request.data.get("due_at"),
            student_id=request.data.get("student_id"),
            time_limit_minutes=request.data.get("time_limit_minutes"),
            max_attempts=request.data.get("max_attempts"),
            idempotency_key=request.data.get("idempotency_key"),
        )
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
