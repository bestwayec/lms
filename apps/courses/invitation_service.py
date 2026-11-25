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
from django.db.models import F
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
    target_student: Any | None = None,
) -> GroupInvitation:
    """Creates a new secure group invitation (optionally student-targeted)."""
    group = StudentGroup.objects.select_related("teacher").get(pk=group_id)
    _assert_can_manage_group(teacher, group)

    if group.status == StudentGroup.Status.ARCHIVED:
        raise ValidationError("Arxivlangan guruhga yangi taklifnoma yaratib bo'lmaydi.")

    if target_student is not None:
        max_uses = 1

    token = secrets.token_urlsafe(32)
    inv_code = (code or f"{group.invite_code or 'GR'}-{secrets.token_hex(2).upper()}").strip()
    expires_at = timezone.now() + timedelta(days=max(1, expires_in_days)) if expires_in_days > 0 else None

    invitation = GroupInvitation.objects.create(
        group=group,
        created_by=teacher,
        target_student=target_student,
        token=token,
        code=inv_code,
        expires_at=expires_at,
        max_uses=max_uses,
        requires_approval=requires_approval,
    )
    logger.info(
        "Group invitation created: id=%d group=%s teacher=%s code=%s target=%s",
        invitation.id,
        group.name,
        teacher.email,
        inv_code,
        getattr(target_student, "id", None),
    )
    return invitation


def rotate_group_invitation(teacher: Any, invitation_id: int) -> GroupInvitation:
    """Rotates token and resets usage for an existing invitation."""
    invitation = GroupInvitation.objects.select_related("group").get(pk=invitation_id)
    _assert_can_manage_group(teacher, invitation.group)

    if invitation.group.status == StudentGroup.Status.ARCHIVED:
        raise ValidationError("Arxivlangan guruh taklifnomasini yangilab bo'lmaydi.")

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
    Uses database row-locking and atomic conditional updates to prevent race conditions.
    """
    if student is None or not getattr(student, "is_authenticated", False):
        raise ValidationError("Guruhga qo'shilish uchun avval ro'yxatdan o'ting yoki tizimga kiring.")

    token = (token or "").strip()
    if not token:
        raise ValidationError("Taklifnoma havolasi noto'g'ri yoki topilmadi.")

    with transaction.atomic():
        try:
            invitation = (
                GroupInvitation.objects.select_for_update()
                .get(token=token)
            )
        except GroupInvitation.DoesNotExist:
            raise ValidationError("Taklifnoma havolasi noto'g'ri yoki topilmadi.")

        if not invitation.is_usable:
            if invitation.group and getattr(invitation.group, "status", None) == StudentGroup.Status.ARCHIVED:
                raise ValidationError("Ushbu guruh arxivlangan. Unga qo'shilish mumkin emas.")
            if invitation.is_revoked:
                raise ValidationError("Ushbu taklifnoma bekor qilingan.")
            if invitation.is_expired:
                raise ValidationError("Taklifnomaning amal qilish muddati tugagan.")
            if invitation.max_uses and invitation.uses_count >= invitation.max_uses:
                raise ValidationError("Ushbu taklifnomadan foydalanish chegarasiga yetildi.")
            raise ValidationError("Ushbu taklifnomadan foydalanib bo'lmaydi.")

        group = (
            StudentGroup.objects.select_for_update()
            .select_related("branch", "teacher")
            .get(pk=invitation.group_id)
        )

        if group.status == StudentGroup.Status.ARCHIVED:
            raise ValidationError("Ushbu guruh arxivlangan. Unga qo'shilish mumkin emas.")

        if invitation.target_student_id is not None and invitation.target_student_id != getattr(student, "id", None):
            raise ValidationError("Ushbu taklifnoma boshqa o'quvchi uchun mo'ljallangan.")

        # Cross-center tenant validation before pending request or enrollment
        if group.branch_id:
            target_center_id = group.branch.center_id
            if getattr(student, "learning_center_id", None) and student.learning_center_id != target_center_id:
                raise ValueError("Talaba boshqa o'quv markaziga biriktirilgan.")
            if getattr(student, "branch_id", None) and getattr(student.branch, "center_id", None) != target_center_id:
                raise ValueError("Talaba boshqa o'quv markaziga biriktirilgan.")

        # Check if already a member
        if group.students.filter(id=student.id).exists():
            return {
                "status": "already_member",
                "message": f"Siz allaqachon '{group.name}' guruhi a'zosisiz.",
                "group_id": group.id,
                "group_name": group.name,
            }

        # Check group capacity (consistent ValueError contract across group & invitation services)
        max_cap = getattr(group, "max_students", 50) or 50
        if group.students.count() >= max_cap:
            raise ValueError(f"Guruh to'lgan. Maksimal sig'im: {max_cap} nafar o'quvchi.")

        # Check approval requirement
        if invitation.requires_approval:
            join_req, created = GroupJoinRequest.objects.get_or_create(
                group=group,
                student=student,
                status=GroupJoinRequest.Status.PENDING,
                defaults={"invitation": invitation},
            )
            if created:
                from apps.notifications.outbox import enqueue_join_request_submitted
                enqueue_join_request_submitted(join_req)

            return {
                "status": "pending_approval",
                "message": f"'{group.name}' guruhiga qo'shilish so'rovingiz qabul qilindi va ustoz tasdig'i kutilmoqda.",
                "request_id": join_req.id,
                "group_id": group.id,
                "group_name": group.name,
            }

        # Direct addition: check max_uses with atomic conditional update
        if invitation.max_uses:
            rows_updated = GroupInvitation.objects.filter(
                pk=invitation.pk,
                is_revoked=False,
                uses_count__lt=invitation.max_uses,
            ).update(uses_count=F("uses_count") + 1)
            if rows_updated == 0:
                raise ValidationError("Ushbu taklifnomadan foydalanish chegarasiga yetildi.")
        else:
            rows_updated = GroupInvitation.objects.filter(
                pk=invitation.pk,
                is_revoked=False,
            ).update(uses_count=F("uses_count") + 1)
            if rows_updated == 0:
                raise ValidationError("Ushbu taklifnoma bekor qilingan.")

        added, _ = add_student_to_group(
            group,
            student,
            actor=invitation.created_by,
            reason="invitation_link",
            metadata={"invitation_id": invitation.id},
        )

        if added:
            from apps.notifications.outbox import enqueue_group_welcome
            enqueue_group_welcome(group, student)

        return {
            "status": "joined",
            "message": f"'{group.name}' guruhiga muvaffaqiyatli qo'shildingiz!",
            "group_id": group.id,
            "group_name": group.name,
            "teacher_name": group.teacher.get_full_name() or group.teacher.email,
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
    with transaction.atomic():
        try:
            group = (
                StudentGroup.objects.select_for_update()
                .get(invite_code__iexact=code)
            )
        except StudentGroup.DoesNotExist:
            raise ValidationError("Kiritilgan taklif kodi bo'yicha guruh topilmadi.")

        if group.status == StudentGroup.Status.ARCHIVED:
            raise ValidationError("Ushbu guruh arxivlangan. Unga qo'shilish mumkin emas.")

        if group.students.filter(id=student.id).exists():
            return {
                "status": "already_member",
                "message": f"Siz allaqachon '{group.name}' guruhi a'zosisiz.",
                "group_id": group.id,
                "group_name": group.name,
            }

        max_cap = getattr(group, "max_students", 50) or 50
        if group.students.count() >= max_cap:
            raise ValueError(f"Guruh to'lgan. Maksimal sig'im: {max_cap} nafar o'quvchi.")

        added, _ = add_student_to_group(
            group,
            student,
            actor=group.teacher,
            reason="group_invite_code",
        )

        if added:
            from apps.notifications.outbox import enqueue_group_welcome
            enqueue_group_welcome(group, student)

        return {
            "status": "joined",
            "message": f"'{group.name}' guruhiga muvaffaqiyatli qo'shildingiz!",
            "group_id": group.id,
            "group_name": group.name,
            "teacher_name": group.teacher.get_full_name() or group.teacher.email,
        }


def review_join_request(
    teacher: Any,
    request_id: int,
    *,
    approved: bool,
    rejection_reason: str = "",
) -> dict[str, Any]:
    """
    Teacher approves or rejects a pending student join request.
    Hardened against duplicate callbacks, simultaneous reviews, capacity races,
    and post-request invitation revocation.
    """
    with transaction.atomic():
        try:
            join_req = (
                GroupJoinRequest.objects.select_for_update()
                .get(pk=request_id)
            )
        except GroupJoinRequest.DoesNotExist:
            raise ValidationError("Qo'shilish so'rovi topilmadi.")

        _assert_can_manage_group(teacher, join_req.group)

        if join_req.status != GroupJoinRequest.Status.PENDING:
            raise ValidationError("Ushbu so'rov allaqachon ko'rib chiqilgan.")

        now = timezone.now()
        if approved:
            if join_req.group.status == StudentGroup.Status.ARCHIVED:
                raise ValidationError("Guruh arxivlangan, so'rovni tasdiqlab bo'lmaydi.")

            max_cap = getattr(join_req.group, "max_students", 50) or 50
            if join_req.group.students.count() >= max_cap:
                raise ValueError(f"Guruh to'lgan. Maksimal sig'im: {max_cap} nafar o'quvchi.")

            # Check if associated invitation was revoked or expired while request was pending
            if join_req.invitation_id:
                inv = GroupInvitation.objects.select_for_update().get(pk=join_req.invitation_id)
                if inv.is_revoked:
                    raise ValidationError("Taklifnoma bekor qilingan, so'rovni tasdiqlab bo'lmaydi.")
                if inv.is_expired:
                    raise ValidationError("Taklifnomaning muddati tugagan, so'rovni tasdiqlab bo'lmaydi.")
                if inv.max_uses and inv.uses_count >= inv.max_uses:
                    raise ValidationError("Taklifnomadan foydalanish chegarasiga yetilgan, so'rovni tasdiqlab bo'lmaydi.")

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

            if join_req.invitation_id:
                GroupInvitation.objects.filter(pk=join_req.invitation_id).update(
                    uses_count=F("uses_count") + 1
                )

            from apps.notifications.outbox import enqueue_join_request_reviewed
            enqueue_join_request_reviewed(join_req)

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

            from apps.notifications.outbox import enqueue_join_request_reviewed
            enqueue_join_request_reviewed(join_req)

            return {
                "status": "rejected",
                "message": "So'rov rad etildi.",
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
