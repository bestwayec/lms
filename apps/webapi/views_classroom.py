"""
Classroom Web APIs for Teacher & Student Workspaces (GRANDEC NEXT 6.0).

Endpoints:
- /api/classroom/teacher/overview/
- /api/classroom/teacher/groups/<group_id>/
- /api/classroom/teacher/invitations/create/
- /api/classroom/teacher/invitations/<id>/revoke/
- /api/classroom/teacher/invitations/<id>/rotate/
- /api/classroom/teacher/join-requests/
- /api/classroom/teacher/join-requests/<id>/review/
- /api/classroom/teacher/assign-test/
- /api/classroom/student/join/
- /api/classroom/student/my-groups/
- /api/classroom/tests/<id>/access/
"""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import Any

from django.db.models import Q
from django.http import HttpRequest, JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from apps.accounts.access import is_platform_admin
from apps.courses.group_service import get_group_analytics
from apps.courses.homework_service import create_unified_homework
from apps.courses.invitation_service import (
    create_group_invitation,
    join_group_by_code,
    join_group_by_token,
    list_teacher_pending_requests,
    review_join_request,
    revoke_group_invitation,
    rotate_group_invitation,
)
from apps.courses.models import GroupInvitation, GroupJoinRequest, Homework, StudentGroup
from apps.tests.access_policy import resolve_test_access
from apps.tests.models import Test

logger = logging.getLogger(__name__)


def _parse_body(request: HttpRequest) -> dict[str, Any]:
    if not request.body:
        return {}
    try:
        return json.loads(request.body.decode("utf-8"))
    except Exception:
        return {}


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def teacher_classroom_overview_view(request: HttpRequest) -> JsonResponse:
    """Teacher Classroom 6.0 dashboard overview."""
    user = request.user
    is_admin = is_platform_admin(user) or getattr(user, "is_superuser", False)
    is_teacher = getattr(user, "role", "") in ("teacher", "admin", "center_admin") or is_admin

    if not is_teacher:
        return JsonResponse({"error": "Faqat o'qituvchilar uchun."}, status=403)

    if is_admin:
        groups_qs = StudentGroup.objects.all()
    else:
        groups_qs = StudentGroup.objects.filter(teacher=user)

    groups_data = []
    for g in groups_qs.select_related("teacher", "branch"):
        active_hw = Homework.objects.filter(group=g, status=Homework.Status.ACTIVE).count()
        groups_data.append({
            "id": g.id,
            "name": g.name,
            "subject": g.subject,
            "teacher_name": g.teacher.get_full_name() or g.teacher.email,
            "students_count": g.students.filter(is_active=True).count(),
            "max_students": getattr(g, "max_students", 50),
            "invite_code": g.invite_code or "",
            "active_homework_count": active_hw,
        })

    pending_requests = list_teacher_pending_requests(user)

    return JsonResponse({
        "groups": groups_data,
        "total_groups": len(groups_data),
        "pending_join_requests_count": len(pending_requests),
        "pending_join_requests": pending_requests[:10],
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def teacher_group_detail_view(request: HttpRequest, group_id: int) -> JsonResponse:
    """Detailed group view: roster with truthful PRO status, invitations, assignments."""
    user = request.user
    group = StudentGroup.objects.filter(id=group_id).select_related("teacher").first()
    if not group:
        return JsonResponse({"error": "Guruh topilmadi."}, status=404)

    is_admin = is_platform_admin(user) or getattr(user, "is_superuser", False)
    if not is_admin and group.teacher_id != user.id:
        return JsonResponse({"error": "Ruxsat etilmagan."}, status=403)

    analytics = get_group_analytics(group)

    invitations = GroupInvitation.objects.filter(group=group).order_by("-created_at")[:10]
    inv_data = [
        {
            "id": inv.id,
            "code": inv.code,
            "token": inv.token,
            "expires_at": inv.expires_at.strftime("%d.%m.%Y %H:%M") if inv.expires_at else "Cheksiz",
            "max_uses": inv.max_uses,
            "uses_count": inv.uses_count,
            "is_revoked": inv.is_revoked,
            "is_usable": inv.is_usable,
            "requires_approval": inv.requires_approval,
        }
        for inv in invitations
    ]

    assignments = Homework.objects.filter(group=group).exclude(status=Homework.Status.CANCELLED).select_related("test")[:15]
    hw_data = [
        {
            "id": hw.id,
            "title": hw.title,
            "content_type": hw.content_type,
            "test_id": hw.test_id,
            "test_title": hw.test.title if hw.test else "",
            "due_date": hw.due_date.strftime("%d.%m.%Y %H:%M") if hw.due_date else None,
            "status": hw.status,
            "max_attempts": hw.max_attempts,
        }
        for hw in assignments
    ]

    return JsonResponse({
        "group": {
            "id": group.id,
            "name": group.name,
            "subject": group.subject,
            "invite_code": group.invite_code or "",
            "students_count": analytics.get("total_students", 0),
            "max_students": getattr(group, "max_students", 50),
        },
        "roster": analytics.get("roster", []),
        "invitations": inv_data,
        "assignments": hw_data,
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def teacher_create_invitation_view(request: HttpRequest) -> JsonResponse:
    """Creates a new invitation link/code."""
    payload = _parse_body(request)
    group_id = payload.get("group_id")
    if not group_id:
        return JsonResponse({"error": "group_id majburiy."}, status=400)

    expires_days = int(payload.get("expires_in_days", 7))
    max_uses = payload.get("max_uses")
    if max_uses is not None:
        max_uses = int(max_uses)
    requires_approval = bool(payload.get("requires_approval", False))
    code = payload.get("code")

    try:
        inv = create_group_invitation(
            request.user,
            int(group_id),
            expires_in_days=expires_days,
            max_uses=max_uses,
            requires_approval=requires_approval,
            code=code,
        )
        return JsonResponse({
            "status": "success",
            "invitation": {
                "id": inv.id,
                "code": inv.code,
                "token": inv.token,
                "expires_at": inv.expires_at.isoformat() if inv.expires_at else None,
                "max_uses": inv.max_uses,
                "requires_approval": inv.requires_approval,
            },
        })
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=400)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def teacher_revoke_invitation_view(request: HttpRequest, inv_id: int) -> JsonResponse:
    try:
        inv = revoke_group_invitation(request.user, inv_id)
        return JsonResponse({"status": "success", "id": inv.id, "is_revoked": inv.is_revoked})
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=400)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def teacher_rotate_invitation_view(request: HttpRequest, inv_id: int) -> JsonResponse:
    try:
        inv = rotate_group_invitation(request.user, inv_id)
        return JsonResponse({"status": "success", "id": inv.id, "token": inv.token})
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=400)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def teacher_join_requests_view(request: HttpRequest) -> JsonResponse:
    reqs = list_teacher_pending_requests(request.user)
    return JsonResponse({"requests": reqs, "count": len(reqs)})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def teacher_review_join_request_view(request: HttpRequest, req_id: int) -> JsonResponse:
    payload = _parse_body(request)
    approved = bool(payload.get("approved", True))
    reason = payload.get("reason", "")
    try:
        res = review_join_request(request.user, req_id, approved=approved, rejection_reason=reason)
        return JsonResponse(res)
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=400)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def teacher_assign_test_wizard_view(request: HttpRequest) -> JsonResponse:
    """Fast assignment wizard: assigns test to group or individual student."""
    payload = _parse_body(request)
    test_id = payload.get("test_id")
    group_id = payload.get("group_id")
    student_id = payload.get("student_id")
    due_days = int(payload.get("due_days", 7))
    max_attempts = int(payload.get("max_attempts", 3))
    audience_mode = payload.get("audience_mode", "GROUP_ONLY")

    if not test_id or (not group_id and not student_id):
        return JsonResponse({"error": "test_id va group_id yoki student_id majburiy."}, status=400)

    test = Test.objects.filter(id=test_id).first()
    if not test:
        return JsonResponse({"error": "Test topilmadi."}, status=404)

    is_admin = is_platform_admin(request.user) or getattr(request.user, "is_superuser", False)
    if not is_admin and test.created_by_id != request.user.id and getattr(getattr(test, "course", None), "teacher_id", None) != request.user.id:
        return JsonResponse({"error": "Ushbu testni biriktirish huquqiga ega emassiz."}, status=403)

    # Update audience mode if specified
    if audience_mode in ("GROUP_ONLY", "GROUP_AND_SUBSCRIBERS", "SUBSCRIBERS_ONLY", "PUBLIC_FREE"):
        if test.audience_mode != audience_mode:
            test.audience_mode = audience_mode
            test.save(update_fields=["audience_mode"])

    due_date = timezone.now() + timedelta(days=max(1, due_days))
    title = f"{test.title} (Klassrum vazifasi)"[:200]

    try:
        hw, _ = create_unified_homework(
            request.user,
            title=title,
            due_date=due_date,
            group_id=int(group_id) if group_id else None,
            student_id=int(student_id) if student_id else None,
            test_id=test.id,
            max_attempts=max_attempts,
            description=f"Ushbu guruh a'zolari testni alohida PRO obunasiz ishlay oladi. ({audience_mode})",
        )
        return JsonResponse({
            "status": "success",
            "homework_id": hw.id,
            "title": hw.title,
            "due_date": hw.due_date.strftime("%d.%m.%Y %H:%M"),
            "audience_mode": test.audience_mode,
            "message": "Vazifa muvaffaqiyatli biriktirildi. Guruh o'quvchilari alohida PRO obunasiz topshira oladi.",
        })
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=400)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def student_join_group_view(request: HttpRequest) -> JsonResponse:
    """Student joins a group via code or invitation token."""
    payload = _parse_body(request)
    code = payload.get("code")
    token = payload.get("token")

    try:
        if token:
            res = join_group_by_token(request.user, token)
        elif code:
            res = join_group_by_code(request.user, code)
        else:
            return JsonResponse({"error": "Kod yoki havola tokeni kiritilmadi."}, status=400)
        return JsonResponse(res)
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=400)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def student_my_groups_view(request: HttpRequest) -> JsonResponse:
    """Student Classroom Portal: Groups, assigned tests, upcoming homework, results."""
    user = request.user
    my_groups = StudentGroup.objects.filter(students=user).select_related("teacher", "branch")

    groups_data = []
    for g in my_groups:
        hw_qs = (
            Homework.objects.filter(Q(group=g) | Q(student=user), status=Homework.Status.ACTIVE)
            .select_related("test")
            .order_by("due_date")
        )
        assignments = []
        for hw in hw_qs:
            access = resolve_test_access(user, hw.test, assignment=hw, action="view") if hw.test else None
            assignments.append({
                "id": hw.id,
                "title": hw.title,
                "test_id": hw.test_id,
                "test_title": hw.test.title if hw.test else "",
                "due_date": hw.due_date.strftime("%d.%m.%Y %H:%M") if hw.due_date else None,
                "is_classroom_entitlement": True,
                "can_start": access.allowed if access else False,
                "access_reason": access.reason if access else "",
            })

        groups_data.append({
            "id": g.id,
            "name": g.name,
            "subject": g.subject,
            "teacher_name": g.teacher.get_full_name() or g.teacher.email,
            "assignments": assignments,
        })

    return JsonResponse({
        "groups": groups_data,
        "total_groups": len(groups_data),
    })


@api_view(["GET"])
def test_access_check_view(request: HttpRequest, test_id: int) -> JsonResponse:
    """Pre-flight access check for UI / Mini App / Bot."""
    test = Test.objects.filter(id=test_id).first()
    if not test:
        return JsonResponse({"error": "Test topilmadi."}, status=404)

    decision = resolve_test_access(request.user if request.user.is_authenticated else None, test, action="start")
    return JsonResponse(decision.to_dict())
