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

from django.core.exceptions import PermissionDenied, ValidationError
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


def _error_response(exc: Exception) -> JsonResponse:
    if isinstance(exc, PermissionDenied):
        msg = exc.args[0] if exc.args else "Ruxsat etilmagan."
        return JsonResponse({"error": str(msg)}, status=403)
    if isinstance(exc, ValidationError) and getattr(exc, "messages", None):
        msg = ", ".join(exc.messages)
        return JsonResponse({"error": msg}, status=400)
    return JsonResponse({"error": str(exc)}, status=400)


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
            "status": g.status,
            "is_active": g.is_active,
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
    target_student = None
    target_student_id = payload.get("target_student_id")
    if target_student_id:
        from apps.accounts.models import User
        target_student = User.objects.filter(id=int(target_student_id), is_active=True, role="student").first()
        if not target_student:
            return JsonResponse({"error": "Tanlangan o'quvchi topilmadi."}, status=404)

    try:
        inv = create_group_invitation(
            request.user,
            int(group_id),
            expires_in_days=expires_days,
            max_uses=max_uses,
            requires_approval=requires_approval,
            code=code,
            target_student=target_student,
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
        return _error_response(exc)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def teacher_revoke_invitation_view(request: HttpRequest, inv_id: int) -> JsonResponse:
    try:
        inv = revoke_group_invitation(request.user, inv_id)
        return JsonResponse({"status": "success", "id": inv.id, "is_revoked": inv.is_revoked})
    except Exception as exc:
        return _error_response(exc)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def teacher_rotate_invitation_view(request: HttpRequest, inv_id: int) -> JsonResponse:
    try:
        inv = rotate_group_invitation(request.user, inv_id)
        return JsonResponse({"status": "success", "id": inv.id, "token": inv.token})
    except Exception as exc:
        return _error_response(exc)


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
        return _error_response(exc)


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

    if group_id:
        target_group = StudentGroup.objects.filter(id=int(group_id)).first()
        if not target_group:
            return JsonResponse({"error": "Guruh topilmadi."}, status=404)
        if not is_admin and target_group.teacher_id != request.user.id:
            return JsonResponse({"error": "Ushbu guruhga vazifa biriktirish huquqiga ega emassiz."}, status=403)
        if target_group.status == StudentGroup.Status.ARCHIVED:
            return JsonResponse({"error": "Arxivlangan guruhga yangi test biriktirib bo'lmaydi."}, status=400)

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
        return _error_response(exc)


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
        return _error_response(exc)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def student_my_groups_view(request: HttpRequest) -> JsonResponse:
    """Student Classroom Portal: Groups, assigned tests, upcoming homework, results."""
    user = request.user
    my_groups = StudentGroup.objects.filter(students=user, status=StudentGroup.Status.ACTIVE).select_related("teacher", "branch")

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


# ---------------------------------------------------------------------------
# Group Lifecycle & Management (GRANDEC NEXT 8.0)
# ---------------------------------------------------------------------------


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def teacher_group_dependencies_view(request: HttpRequest, group_id: int) -> JsonResponse:
    """Preview group dependencies before archiving or safe deletion."""
    from apps.courses.group_service import get_group_dependencies

    group = StudentGroup.objects.filter(id=group_id).first()
    if not group:
        return JsonResponse({"error": "Guruh topilmadi."}, status=404)

    is_admin = is_platform_admin(request.user) or getattr(request.user, "is_superuser", False)
    if not is_admin and group.teacher_id != request.user.id:
        return JsonResponse({"error": "Ruxsat etilmagan."}, status=403)

    deps = get_group_dependencies(group)
    return JsonResponse(deps)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def teacher_archive_group_view(request: HttpRequest, group_id: int) -> JsonResponse:
    """Safely archives a group, preserving all history and revoking invitations."""
    from apps.courses.group_service import archive_group

    group = StudentGroup.objects.filter(id=group_id).first()
    if not group:
        return JsonResponse({"error": "Guruh topilmadi."}, status=404)

    try:
        archived = archive_group(group, request.user)
        return JsonResponse({
            "status": "success",
            "group_id": archived.id,
            "group_status": archived.status,
            "message": f"'{archived.name}' guruhi muvaffaqiyatli arxivlandi.",
        })
    except Exception as exc:
        return _error_response(exc)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def teacher_restore_group_view(request: HttpRequest, group_id: int) -> JsonResponse:
    """Restores an archived group back to ACTIVE."""
    from apps.courses.group_service import restore_group

    group = StudentGroup.objects.filter(id=group_id).first()
    if not group:
        return JsonResponse({"error": "Guruh topilmadi."}, status=404)

    try:
        restored = restore_group(group, request.user)
        return JsonResponse({
            "status": "success",
            "group_id": restored.id,
            "group_status": restored.status,
            "message": f"'{restored.name}' guruhi qayta faollashtirildi.",
        })
    except Exception as exc:
        return _error_response(exc)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def teacher_delete_group_view(request: HttpRequest, group_id: int) -> JsonResponse:
    """Deletes an empty group with NO academic history. Rejects if history exists."""
    from apps.courses.group_service import delete_group_safely

    group = StudentGroup.objects.filter(id=group_id).first()
    if not group:
        return JsonResponse({"error": "Guruh topilmadi."}, status=404)

    try:
        delete_group_safely(group, request.user)
        return JsonResponse({
            "status": "success",
            "message": "Guruh muvaffaqiyatli o'chirildi.",
        })
    except Exception as exc:
        return _error_response(exc)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def teacher_transfer_group_view(request: HttpRequest, group_id: int) -> JsonResponse:
    """Transfers group responsibility to another verified teacher."""
    from apps.accounts.models import User
    from apps.courses.group_service import transfer_group_teacher

    group = StudentGroup.objects.filter(id=group_id).first()
    if not group:
        return JsonResponse({"error": "Guruh topilmadi."}, status=404)

    payload = _parse_body(request)
    new_teacher_id = payload.get("new_teacher_id")
    if not new_teacher_id:
        return JsonResponse({"error": "new_teacher_id kiritilmadi."}, status=400)

    new_teacher = User.objects.filter(id=new_teacher_id).first()
    if not new_teacher:
        return JsonResponse({"error": "Yangi o'qituvchi topilmadi."}, status=404)

    try:
        updated = transfer_group_teacher(group, new_teacher, request.user)
        return JsonResponse({
            "status": "success",
            "teacher_id": updated.teacher_id,
            "teacher_name": updated.teacher.get_full_name() or updated.teacher.email,
            "message": f"Guruh mas'uliyati {updated.teacher.get_full_name()} ga muvaffaqiyatli o'tkazildi.",
        })
    except Exception as exc:
        return _error_response(exc)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def teacher_remove_student_view(request: HttpRequest, group_id: int) -> JsonResponse:
    """Removes a student from a group, preserving all historical results and attendance."""
    from apps.accounts.models import User
    from apps.courses.group_service import remove_student_from_group

    group = StudentGroup.objects.filter(id=group_id).first()
    if not group:
        return JsonResponse({"error": "Guruh topilmadi."}, status=404)

    is_admin = is_platform_admin(request.user) or getattr(request.user, "is_superuser", False)
    if not is_admin and group.teacher_id != request.user.id:
        return JsonResponse({"error": "Ruxsat etilmagan."}, status=403)

    payload = _parse_body(request)
    student_id = payload.get("student_id")
    reason = payload.get("reason", "teacher_removal")
    if not student_id:
        return JsonResponse({"error": "student_id kiritilmadi."}, status=400)

    student = User.objects.filter(id=student_id).first()
    if not student:
        return JsonResponse({"error": "O'quvchi topilmadi."}, status=404)

    try:
        removed = remove_student_from_group(group, student, actor=request.user, reason=reason)
        return JsonResponse({
            "status": "success",
            "removed": removed,
            "message": f"O'quvchi guruhdan chiqarildi (natijalari to'liq saqlab qolindi).",
        })
    except Exception as exc:
        return _error_response(exc)


# ---------------------------------------------------------------------------
# Leaderboards: Group Classroom vs Platform
# ---------------------------------------------------------------------------


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def classroom_group_leaderboard_view(request: HttpRequest, group_id: int) -> JsonResponse:
    """Group leaderboard restricted to enrolled classroom members."""
    from apps.results.models import Result
    from apps.essays.models import EssaySubmission

    group = StudentGroup.objects.filter(id=group_id).first()
    if not group:
        return JsonResponse({"error": "Guruh topilmadi."}, status=404)

    user = request.user
    is_admin = is_platform_admin(user) or getattr(user, "is_superuser", False)
    is_member = group.students.filter(id=user.id).exists()
    is_teacher = group.teacher_id == user.id

    if not (is_admin or is_teacher or is_member):
        return JsonResponse({"error": "Faqat ushbu guruh a'zolari reytingni ko'ra oladi."}, status=403)

    students = list(group.students.filter(is_active=True).order_by("first_name", "last_name"))
    student_ids = [s.id for s in students]

    results_map: dict[int, dict[str, Any]] = {}
    from django.db.models import Avg, Count
    for row in Result.objects.filter(student_id__in=student_ids).values("student_id").annotate(
        count=Count("id"),
        avg_pct=Avg("percentage"),
    ):
        results_map[row["student_id"]] = row

    essays_map: dict[int, int] = {}
    for row in EssaySubmission.objects.filter(student_id__in=student_ids).exclude(status=EssaySubmission.Status.DRAFT).values("student_id").annotate(
        count=Count("id")
    ):
        essays_map[row["student_id"]] = row["count"]

    rows = []
    for s in students:
        r_info = results_map.get(s.id, {})
        avg_pct = round(float(r_info.get("avg_pct") or 0), 1)
        tests_count = r_info.get("count", 0)
        essays_count = essays_map.get(s.id, 0)
        # Learning score calculation
        score_metric = (avg_pct * 10) + (tests_count * 5) + (essays_count * 15)

        rows.append({
            "student_id": s.id,
            "full_name": s.get_full_name() or s.email.split("@")[0],
            "tests_count": tests_count,
            "avg_percentage": avg_pct,
            "essays_count": essays_count,
            "score_metric": round(score_metric, 1),
            "is_me": s.id == user.id,
        })

    rows.sort(key=lambda x: x["score_metric"], reverse=True)
    for idx, r in enumerate(rows, start=1):
        r["rank"] = idx
        r["badge"] = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"#{idx}"

    return JsonResponse({
        "group_id": group.id,
        "group_name": group.name,
        "leaderboard": rows,
        "total_students": len(rows),
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def platform_leaderboard_view(request: HttpRequest) -> JsonResponse:
    """Privacy-preserving platform-wide leaderboard ranked by verified learning XP."""
    from apps.accounts.gamification import get_platform_leaderboard

    period = request.GET.get("period", "weekly")
    limit = min(50, max(5, int(request.GET.get("limit", 20))))
    data = get_platform_leaderboard(user=request.user, period=period, limit=limit)
    # Never expose other participants' internal database user IDs over the public API
    for item in data.get("items", []):
        if not item.get("is_current_user"):
            item.pop("user_id", None)
    return JsonResponse(data)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def gamification_privacy_settings_view(request: HttpRequest) -> JsonResponse:
    """Allows students to opt in/out of public leaderboards, choose a pseudonym, or toggle streak reminders."""
    import re
    from apps.accounts.gamification import _invalidate_gamification_caches
    from apps.accounts.models import Profile

    profile, _ = Profile.objects.get_or_create(user=request.user)
    if request.method == "POST":
        payload = _parse_body(request)
        update_fields = []
        if "leaderboard_opt_in" in payload:
            profile.leaderboard_opt_in = bool(payload["leaderboard_opt_in"])
            update_fields.append("leaderboard_opt_in")
        if "streak_opt_in" in payload:
            profile.streak_opt_in = bool(payload["streak_opt_in"])
            update_fields.append("streak_opt_in")
        if "leaderboard_pseudonym" in payload:
            raw_pseudo = re.sub(r"[<>\"'&@]", "", str(payload["leaderboard_pseudonym"] or "")).strip()[:40]
            profile.leaderboard_pseudonym = raw_pseudo
            update_fields.append("leaderboard_pseudonym")
        if update_fields:
            profile.save(update_fields=update_fields)
            _invalidate_gamification_caches(user_id=request.user.id, league=profile.weekly_league)

    return JsonResponse({
        "leaderboard_opt_in": bool(profile.leaderboard_opt_in),
        "leaderboard_pseudonym": profile.leaderboard_pseudonym,
        "streak_opt_in": bool(profile.streak_opt_in),
    })


# ---------------------------------------------------------------------------
# Essay Classroom & Human Review Center (GRANDEC NEXT 8.0)
# ---------------------------------------------------------------------------


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def student_request_essay_appeal_view(request: HttpRequest, submission_id: int) -> JsonResponse:
    """Student requests reassessment/appeal on an AI-graded essay."""
    from apps.essays.models import EssaySubmission
    from apps.essays.services import TeacherReviewService

    submission = EssaySubmission.objects.filter(id=submission_id, student=request.user).first()
    if not submission:
        return JsonResponse({"error": "Esse topilmadi."}, status=404)

    payload = _parse_body(request)
    reason = str(payload.get("reason", "")).strip()
    criteria = payload.get("criteria", [])
    if not reason:
        reason = "Menimcha, esseyim noto'g'ri baholandi."

    try:
        updated = TeacherReviewService.request_teacher_review(
            submission,
            request.user,
            reason=reason,
            criteria=criteria if isinstance(criteria, list) else [],
        )
        return JsonResponse({
            "status": "success",
            "submission_id": updated.id,
            "appeal_status": updated.appeal_status,
            "reviewer_name": updated.assigned_reviewer.get_full_name() if updated.assigned_reviewer else None,
            "message": "Apellatsiya so'rovingiz qabul qilindi va ustozga yuborildi.",
        })
    except Exception as exc:
        return _error_response(exc)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def student_withdraw_essay_appeal_view(request: HttpRequest, submission_id: int) -> JsonResponse:
    """Student withdraws an active essay reassessment request."""
    from apps.essays.models import EssaySubmission
    from apps.essays.services import TeacherReviewService

    submission = EssaySubmission.objects.filter(id=submission_id, student=request.user).first()
    if not submission:
        return JsonResponse({"error": "Esse topilmadi."}, status=404)

    try:
        updated = TeacherReviewService.withdraw_appeal(submission, request.user)
        return JsonResponse({
            "status": "success",
            "appeal_status": updated.appeal_status,
            "message": "Apellatsiya qaytarib olindi.",
        })
    except Exception as exc:
        return _error_response(exc)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def teacher_list_essay_reviews_view(request: HttpRequest) -> JsonResponse:
    """List pending essay reviews and student appeals for the teacher."""
    from apps.essays.models import EssaySubmission

    user = request.user
    is_admin = is_platform_admin(user) or getattr(user, "is_superuser", False)
    is_teacher = getattr(user, "role", "") in ("teacher", "admin", "center_admin") or is_admin

    if not is_teacher:
        return JsonResponse({"error": "Faqat o'qituvchilar uchun."}, status=403)

    if is_admin:
        qs = EssaySubmission.objects.filter(
            Q(status=EssaySubmission.Status.PENDING_TEACHER) | Q(teacher_review_requested=True)
        )
    else:
        qs = EssaySubmission.objects.filter(
            Q(assigned_reviewer=user)
            | Q(assignment__group__teacher=user)
            | Q(assignment__isnull=False, assignment__group__isnull=True, assignment__assigned_by=user)
            | Q(
                assignment__isnull=True,
                assigned_reviewer__isnull=True,
                group_visibility=EssaySubmission.GroupVisibility.GROUP_VISIBLE,
                student__student_groups__teacher=user,
                student__student_groups__status=StudentGroup.Status.ACTIVE,
            )
        ).filter(
            Q(status=EssaySubmission.Status.PENDING_TEACHER) | Q(teacher_review_requested=True)
        ).distinct()

    reviews_data = []
    for sub in qs.select_related("student", "topic", "assignment", "assignment__group").order_by("-teacher_review_requested_at")[:50]:
        reviews_data.append({
            "id": sub.id,
            "student_id": sub.student_id,
            "student_name": sub.student.get_full_name() or sub.student.email,
            "topic_title": sub.topic.title if sub.topic else sub.custom_title,
            "group_name": sub.assignment.group.name if sub.assignment and sub.assignment.group else None,
            "ai_score": str(sub.total_score) if sub.total_score is not None else None,
            "word_count": sub.word_count,
            "appeal_status": getattr(sub, "appeal_status", "none"),
            "appeal_reason": getattr(sub, "appeal_reason", "") or getattr(sub, "teacher_review_reason", ""),
            "appeal_criteria": getattr(sub, "appeal_criteria", []),
            "requested_at": sub.teacher_review_requested_at.strftime("%d.%m.%Y %H:%M") if sub.teacher_review_requested_at else None,
        })

    return JsonResponse({
        "pending_reviews": reviews_data,
        "count": len(reviews_data),
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def teacher_submit_essay_review_view(request: HttpRequest, submission_id: int) -> JsonResponse:
    """Teacher finalizes human grading, adjusts criteria scores, adds comments and optional voice feedback."""
    from decimal import Decimal
    from apps.essays.models import EssaySubmission
    from apps.essays.services import TeacherReviewService

    submission = EssaySubmission.objects.filter(id=submission_id).first()
    if not submission:
        return JsonResponse({"error": "Esse topilmadi."}, status=404)

    # Support JSON or multipart form data
    if request.content_type and "multipart/form-data" in request.content_type:
        criteria_raw = request.POST.get("criteria_scores", "{}")
        try:
            criteria_scores = json.loads(criteria_raw)
        except Exception:
            criteria_scores = {}
        teacher_comments = request.POST.get("teacher_comments", "")
        voice_duration = int(request.POST.get("voice_duration_seconds", 0) or 0)
        voice_file = request.FILES.get("voice_feedback")
    else:
        payload = _parse_body(request)
        criteria_scores = payload.get("criteria_scores", {})
        teacher_comments = payload.get("teacher_comments", "")
        voice_duration = int(payload.get("voice_duration_seconds", 0) or 0)
        voice_file = None

    try:
        review = TeacherReviewService.submit_review(
            submission=submission,
            teacher=request.user,
            criteria_scores=criteria_scores,
            teacher_comments=teacher_comments,
            voice_file=voice_file,
            voice_duration_seconds=voice_duration,
        )
        return JsonResponse({
            "status": "success",
            "review_id": review.id,
            "final_score": str(review.final_score),
            "has_voice_feedback": bool(review.voice_feedback),
            "message": "Ustoz baholashi va xulosasi muvaffaqiyatli saqlandi.",
        })
    except Exception as exc:
        return _error_response(exc)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def essay_voice_playback_view(request: HttpRequest, submission_id: int):
    """Secure private audio streaming for teacher voice feedback."""
    from apps.core.private_files import private_file_response
    from apps.essays.models import EssaySubmission, TeacherReview

    submission = EssaySubmission.objects.filter(id=submission_id).select_related("student", "assignment__group").first()
    if not submission:
        return JsonResponse({"error": "Esse topilmadi."}, status=404)

    review = TeacherReview.objects.filter(submission=submission).first()
    user = request.user
    is_admin = is_platform_admin(user) or getattr(user, "is_superuser", False)
    is_student = submission.student_id == user.id
    is_teacher = (
        (submission.assignment and submission.assignment.group and submission.assignment.group.teacher_id == user.id)
        or (submission.assigned_reviewer_id == user.id)
        or (review is not None and review.teacher_id == user.id)
    )

    if not (is_admin or is_student or is_teacher):
        return JsonResponse({"error": "Ushbu audio fikrni tinglash huquqiga ega emassiz."}, status=403)

    if not review or not review.voice_feedback:
        return JsonResponse({"error": "Ushbu esse uchun audio fikr mavjud emas."}, status=404)

    return private_file_response(review.voice_feedback)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def classroom_group_essay_gradebook_view(
    request: HttpRequest, group_id: int, assignment_id: int
) -> JsonResponse:
    """Comprehensive group essay gradebook with all students, submission states, and rubric scale."""
    from apps.essays.models import EssayAssignment, EssaySubmission

    group = StudentGroup.objects.filter(id=group_id).first()
    if not group:
        return JsonResponse({"error": "Guruh topilmadi."}, status=404)

    is_admin = is_platform_admin(request.user) or getattr(request.user, "is_superuser", False)
    if not is_admin and group.teacher_id != request.user.id:
        return JsonResponse({"error": "Ruxsat etilmagan."}, status=403)

    assignment = EssayAssignment.objects.filter(id=assignment_id, group=group).select_related("topic").first()
    if not assignment:
        return JsonResponse({"error": "Esse topshirig'i topilmadi."}, status=404)

    students = list(group.students.filter(is_active=True).order_by("first_name", "last_name"))
    student_ids = [s.id for s in students]

    submissions = {
        sub.student_id: sub
        for sub in EssaySubmission.objects.filter(
            assignment=assignment,
            student_id__in=student_ids,
        ).select_related("student", "teacher_review")
    }

    rows = []
    submitted_count = 0
    graded_count = 0
    pending_review_count = 0
    total_score_sum = 0.0

    for s in students:
        sub = submissions.get(s.id)
        if sub:
            submitted_count += 1
            has_review = hasattr(sub, "teacher_review") and sub.teacher_review is not None
            has_voice = bool(has_review and sub.teacher_review.voice_feedback)
            final_val = float(sub.final_score) if sub.final_score is not None else None
            ai_val = float(sub.total_score) if sub.total_score is not None else None

            if sub.status in (
                EssaySubmission.Status.TEACHER_REVIEWED,
                EssaySubmission.Status.GRADED,
                EssaySubmission.Status.AI_EVALUATED,
            ):
                eff_score = final_val if final_val is not None else ai_val
                if eff_score is not None:
                    graded_count += 1
                    total_score_sum += eff_score
            elif sub.status == EssaySubmission.Status.PENDING_TEACHER or sub.teacher_review_requested:
                pending_review_count += 1

            sub_dt = sub.submitted_at or sub.updated_at
            rows.append({
                "student_id": s.id,
                "student_name": s.get_full_name() or s.email.split("@")[0],
                "submission_id": sub.id,
                "status": "submitted",
                "grading_status": sub.status,
                "submitted_at": sub_dt.strftime("%d.%m.%Y %H:%M") if sub_dt else None,
                "ai_score": ai_val,
                "final_score": final_val,
                "appeal_status": getattr(sub, "appeal_status", "none"),
                "has_voice_feedback": has_voice,
                "teacher_comments": sub.teacher_review.teacher_comments if has_review else "",
            })
        else:
            rows.append({
                "student_id": s.id,
                "student_name": s.get_full_name() or s.email.split("@")[0],
                "submission_id": None,
                "status": "not_submitted",
                "grading_status": "unsubmitted",
                "submitted_at": None,
                "ai_score": None,
                "final_score": None,
                "appeal_status": "none",
                "has_voice_feedback": False,
                "teacher_comments": "",
            })

    total_assigned = len(students)
    not_submitted_count = total_assigned - submitted_count
    avg_score = round(total_score_sum / graded_count, 1) if graded_count > 0 else 0.0

    from apps.essays.services import ESSAY_RUBRIC_MAX_SCORE

    topic_rubric = getattr(assignment.topic, "rubric_type", "") if assignment.topic else ""
    max_scale = 9 if str(topic_rubric).startswith("ielts") else ESSAY_RUBRIC_MAX_SCORE

    return JsonResponse({
        "group_id": group.id,
        "group_name": group.name,
        "assignment_id": assignment.id,
        "topic_title": assignment.topic.title,
        "due_at": assignment.due_at.strftime("%d.%m.%Y %H:%M") if assignment.due_at else None,
        "metrics": {
            "total_assigned": total_assigned,
            "submitted_count": submitted_count,
            "not_submitted_count": not_submitted_count,
            "pending_review_count": pending_review_count,
            "graded_count": graded_count,
            "avg_valid_score": avg_score,
            "max_score": max_scale,
        },
        "roster": rows,
    })

