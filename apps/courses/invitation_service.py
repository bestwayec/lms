"""
Group Invitations & Direct Enrollment Service (GRANDEC NEXT 6.0).

Supports:
- Secure, expiring invitation links (with configurable expiry & usage limits)
- Token revocation & token rotation
- Group capacity enforcement
- Teacher manual approval requests
- Server-side invitation code verification
- Telegram deep link integration
- Billing integrity: Joining a group NEVER automatically grants PRO/Premium
  or invents paid tuition status.
"""

from __future__ import annotations

import logging
import secrets
from datetime import timedelta
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.access import is_platform_admin
from apps.courses.group_service import add_student_to_group
from apps.courses.models import GroupInvitation, GroupJoinRequest, StudentGroup

logger = logging.getLogger(__name__)


def _assert_can_manage_group(user: Any, group: StudentGroup) -> None:
    if user is None or not getattr(user, "is_authenticated", False):
        raise PermissionDenied("Foydalanuvchi tizimga kirmagan.")
    if is_platform_admin(user) or getattr(user, "is_superuser", False):
        return
    if getattr(user, "role", "") == "teacher" and group.teacher_id == user.id:
        return
    raise PermissionDenied("Ushbu guruhni boshqarish huquqiga ega emassiz.")


def create_group_invitation(
    teacher: Any,
    group_id: int,
    *,
    expires_in_days: int = 7,
    max_uses: int | None = None,
    requires_approval: bool = False,
    code: str | None = None,
) -> GroupInvitation:
    """Creates a new secure group invitation."""
    group = StudentGroup.objects.select_related("teacher").get(pk=group_id)
    _assert_can_manage_group(teacher, group)

    token = secrets.token_urlsafe(32)
    inv_code = (code or f"{group.invite_code or 'GR'}-{secrets.token_hex(2).upper()}").strip()
    expires_at = timezone.now() + timedelta(days=max(1, expires_in_days)) if expires_in_days > 0 else None

    invitation = GroupInvitation.objects.create(
        group=group,
        created_by=teacher,
        token=token,
        code=inv_code,
        expires_at=expires_at,
        max_uses=max_uses,
        requires_approval=requires_approval,
    )
    logger.info(
        "Group invitation created: id=%d group=%s teacher=%s code=%s",
        invitation.id,
        group.name,
        teacher.email,
        inv_code,
    )
    return invitation


def rotate_group_invitation(teacher: Any, invitation_id: int) -> GroupInvitation:
    """Rotates token and resets usage for an existing invitation."""
    invitation = GroupInvitation.objects.select_related("group").get(pk=invitation_id)
    _assert_can_manage_group(teacher, invitation.group)

    invitation.token = secrets.token_urlsafe(32)
    invitation.uses_count = 0
    invitation.is_revoked = False
    if invitation.expires_at:
        invitation.expires_at = timezone.now() + timedelta(days=7)
    invitation.save(update_fields=["token", "uses_count", "is_revoked", "expires_at"])
    return invitation


def revoke_group_invitation(teacher: Any, invitation_id: int) -> GroupInvitation:
    """Revokes an invitation immediately."""
    invitation = GroupInvitation.objects.select_related("group").get(pk=invitation_id)
    _assert_can_manage_group(teacher, invitation.group)

    invitation.is_revoked = True
    invitation.save(update_fields=["is_revoked"])
    return invitation


def join_group_by_token(student: Any, token: str) -> dict[str, Any]:
    """
    Validates token and enrolls the student or creates a pending approval request.
    """
    if student is None or not getattr(student, "is_authenticated", False):
        raise ValidationError("Guruhga qo'shilish uchun avval ro'yxatdan o'ting yoki tizimga kiring.")

    token = (token or "").strip()
    invitation = (
        GroupInvitation.objects.select_related("group", "group__branch", "group__teacher")
        .filter(token=token)
        .first()
    )
    if not invitation:
        raise ValidationError("Taklifnoma havolasi noto'g'ri yoki topilmadi.")

    if not invitation.is_usable:
        if invitation.is_revoked:
            raise ValidationError("Ushbu taklifnoma bekor qilingan.")
        if invitation.is_expired:
            raise ValidationError("Taklifnomaning amal qilish muddati tugagan.")
        if invitation.max_uses and invitation.uses_count >= invitation.max_uses:
            raise ValidationError("Ushbu taklifnomadan foydalanish chegarasiga yetildi.")
        raise ValidationError("Ushbu taklifnomadan foydalanib bo'lmaydi.")

    group = invitation.group

    # Check if already a member
    if group.students.filter(id=student.id).exists():
        return {
            "status": "already_member",
            "message": f"Siz allaqachon '{group.name}' guruhi a'zosisiz.",
            "group_id": group.id,
            "group_name": group.name,
        }

    # Check approval requirement
    if invitation.requires_approval:
        join_req, created = GroupJoinRequest.objects.get_or_create(
            group=group,
            student=student,
            status=GroupJoinRequest.Status.PENDING,
            defaults={"invitation": invitation},
        )
        return {
            "status": "pending_approval",
            "message": f"'{group.name}' guruhiga qo'shilish so'rovingiz qabul qilindi va ustoz tasdig'i kutilmoqda.",
            "request_id": join_req.id,
            "group_id": group.id,
            "group_name": group.name,
        }

    # Direct addition
    with transaction.atomic():
        added, _ = add_student_to_group(
            group,
            student,
            actor=invitation.created_by,
            reason="invitation_link",
            metadata={"invitation_id": invitation.id},
        )
        if added:
            GroupInvitation.objects.filter(pk=invitation.pk).update(
                uses_count=invitation.uses_count + 1
            )

    return {
        "status": "joined",
        "message": f"'{group.name}' guruhiga muvaffaqiyatli qo'shildingiz!",
        "group_id": group.id,
        "group_name": group.name,
    }


def join_group_by_code(student: Any, code: str) -> dict[str, Any]:
    """Validates an invitation code or group invite_code and enrolls student."""
    if student is None or not getattr(student, "is_authenticated", False):
        raise ValidationError("Guruhga qo'shilish uchun avval tizimga kiring.")

    code = (code or "").strip().upper()
    if not code:
        raise ValidationError("Taklif kodini kiriting.")

    # 1. Search in GroupInvitation codes
    invitation = (
        GroupInvitation.objects.select_related("group", "group__branch", "group__teacher")
        .filter(code__iexact=code)
        .first()
    )
    if invitation:
        return join_group_by_token(student, invitation.token)

    # 2. Search in StudentGroup.invite_code
    group = (
        StudentGroup.objects.select_related("teacher", "branch")
        .filter(invite_code__iexact=code)
        .first()
    )
    if not group:
        raise ValidationError("Kiritilgan taklif kodi bo'yicha guruh topilmadi.")

    if group.students.filter(id=student.id).exists():
        return {
            "status": "already_member",
            "message": f"Siz allaqachon '{group.name}' guruhi a'zosisiz.",
            "group_id": group.id,
            "group_name": group.name,
        }

    added, _ = add_student_to_group(
        group,
        student,
        actor=group.teacher,
        reason="group_invite_code",
    )
    return {
        "status": "joined",
        "message": f"'{group.name}' guruhiga muvaffaqiyatli qo'shildingiz!",
        "group_id": group.id,
        "group_name": group.name,
    }


def review_join_request(
    teacher: Any,
    request_id: int,
    *,
    approved: bool,
    rejection_reason: str = "",
) -> dict[str, Any]:
    """Teacher approves or rejects a pending student join request."""
    join_req = (
        GroupJoinRequest.objects.select_related("group", "student")
        .get(pk=request_id)
    )
    _assert_can_manage_group(teacher, join_req.group)

    if join_req.status != GroupJoinRequest.Status.PENDING:
        raise ValidationError("Ushbu so'rov allaqachon ko'rib chiqilgan.")

    now = timezone.now()
    if approved:
        with transaction.atomic():
            add_student_to_group(
                join_req.group,
                join_req.student,
                actor=teacher,
                reason="join_request_approved",
                metadata={"request_id": join_req.id},
            )
            join_req.status = GroupJoinRequest.Status.APPROVED
            join_req.reviewed_by = teacher
            join_req.reviewed_at = now
            join_req.save(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"])
            if join_req.invitation:
                GroupInvitation.objects.filter(pk=join_req.invitation.pk).update(
                    uses_count=join_req.invitation.uses_count + 1
                )
        return {
            "status": "approved",
            "message": f"'{join_req.student.get_full_name() or join_req.student.email}' guruhga qabul qilindi.",
            "student_id": join_req.student.id,
            "group_id": join_req.group.id,
        }
    else:
        join_req.status = GroupJoinRequest.Status.REJECTED
        join_req.reviewed_by = teacher
        join_req.reviewed_at = now
        join_req.rejection_reason = rejection_reason[:255]
        join_req.save(update_fields=["status", "reviewed_by", "reviewed_at", "rejection_reason", "updated_at"])
        return {
            "status": "rejected",
            "message": f"So'rov rad etildi.",
            "student_id": join_req.student.id,
            "group_id": join_req.group.id,
        }


def list_teacher_pending_requests(teacher: Any) -> list[dict[str, Any]]:
    """Returns all pending join requests for teacher's groups."""
    if is_platform_admin(teacher) or getattr(teacher, "is_superuser", False):
        reqs = GroupJoinRequest.objects.filter(status=GroupJoinRequest.Status.PENDING)
    else:
        reqs = GroupJoinRequest.objects.filter(
            group__teacher=teacher,
            status=GroupJoinRequest.Status.PENDING,
        )

    reqs = reqs.select_related("group", "student", "invitation").order_by("-created_at")
    return [
        {
            "id": r.id,
            "group_id": r.group.id,
            "group_name": r.group.name,
            "student_id": r.student.id,
            "student_name": r.student.get_full_name() or r.student.email,
            "student_email": r.student.email,
            "created_at": r.created_at.strftime("%d.%m.%Y %H:%M"),
            "invitation_code": r.invitation.code if r.invitation else "",
        }
        for r in reqs
    ]
