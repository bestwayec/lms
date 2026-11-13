"""
Parent-Student Linking Service and Deep Link Security.
Provides HMAC-backed deep linking and verification for Telegram bot integration.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import ParentInvitation, ParentStudentRelation

logger = logging.getLogger(__name__)
User = get_user_model()


def generate_parent_deep_link_token(student_id: int) -> str:
    """Issue a random invitation that expires after 24 hours."""
    token = secrets.token_hex(16)
    with transaction.atomic():
        student = User.objects.select_for_update().get(pk=student_id, role=User.Role.STUDENT, is_active=True)
        ParentInvitation.objects.create(
            student=student, token_hash=hashlib.sha256(token.encode()).hexdigest(),
            expires_at=timezone.now() + timedelta(hours=24),
        )
    return token


def verify_parent_deep_link_token(student_id: int, token: str) -> bool:
    """Check whether an invitation is currently usable (redemption rechecks under lock)."""
    if not token or not student_id or not isinstance(token, str):
        return False
    return ParentInvitation.objects.filter(
        student_id=student_id, token_hash=hashlib.sha256(token.encode()).hexdigest(),
        expires_at__gt=timezone.now(), consumed_at__isnull=True, revoked_at__isnull=True,
    ).exists()


@transaction.atomic
def redeem_parent_invitation(*, student_id: int, token: str, telegram_id: int, parent_name: str = "") -> Any:
    """Serialize redemption, revocation and relation changes on the student row."""
    student = User.objects.select_for_update().filter(pk=student_id, role=User.Role.STUDENT, is_active=True).first()
    if not student:
        raise ValueError("Invalid student.")
    invite = ParentInvitation.objects.select_for_update().filter(
        student=student, token_hash=hashlib.sha256(token.encode()).hexdigest(),
        expires_at__gt=timezone.now(), consumed_at__isnull=True, revoked_at__isnull=True,
    ).first()
    if not invite:
        raise ValueError("Invalid or expired invitation.")
    link_parent_to_student(student=student, telegram_id=telegram_id, parent_name=parent_name)
    invite.consumed_at = timezone.now()
    invite.save(update_fields=["consumed_at"])
    return student


def get_parent_deep_link(student_id: int) -> str:
    """Build full Telegram bot deep link URL for student."""
    token = generate_parent_deep_link_token(student_id)
    bot_username = getattr(settings, "TELEGRAM_BOT_USERNAME", "grandec_bot")
    return f"https://t.me/{bot_username}?start=parent_{student_id}_{token}"


@transaction.atomic
def revoke_parent_invitations(student_id: int) -> int:
    User.objects.select_for_update().get(pk=student_id)
    return ParentInvitation.objects.filter(
        student_id=student_id, consumed_at__isnull=True, revoked_at__isnull=True,
    ).update(revoked_at=timezone.now())


@transaction.atomic
def link_parent_to_student(
    *,
    student: Any,
    telegram_id: int,
    parent_name: str = "",
    parent_phone: str = "",
) -> tuple[ParentStudentRelation, bool]:
    """
    Link or update parent Telegram profile to student.
    Ensures unique relations and sets verified status.
    """
    # One deterministic invitation per student must not silently authorize
    # additional Telegram accounts. Lock the student to serialize redemption.
    User.objects.select_for_update().get(pk=student.pk)
    if not parent_phone and ParentStudentRelation.objects.filter(
        student=student, parent_phone__startswith="tg:", is_verified=True
    ).exclude(parent_telegram_id=telegram_id).exists():
        raise ValueError("Parent invitation is already linked to another Telegram account.")
    phone_val = parent_phone.strip() if parent_phone else f"tg:{telegram_id}"
    relation, created = ParentStudentRelation.objects.get_or_create(
        student=student,
        parent_phone=phone_val,
        defaults={
            "parent_telegram_id": telegram_id,
            "parent_name": parent_name.strip(),
            "is_verified": True,
            "notifications_enabled": True,
            "weekly_report_enabled": True,
            "instant_alerts_enabled": True,
        },
    )

    if not created:
        if relation.parent_telegram_id not in (None, telegram_id):
            raise ValueError("Parent relation is already linked to another Telegram account.")
        relation.parent_telegram_id = telegram_id
        if parent_name:
            relation.parent_name = parent_name.strip()
        relation.is_verified = True
        relation.save(
            update_fields=[
                "parent_telegram_id",
                "parent_name",
                "is_verified",
                "updated_at",
            ]
        )

    logger.info(
        "Parent linked: student_id=%s, telegram_id=%s, created=%s",
        student.id,
        telegram_id,
        created,
    )
    return relation, created
