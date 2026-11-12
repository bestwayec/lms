"""
Parent-Student Linking Service and Deep Link Security.
Provides HMAC-backed deep linking and verification for Telegram bot integration.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction

from apps.accounts.models import ParentStudentRelation

logger = logging.getLogger(__name__)
User = get_user_model()


def generate_parent_deep_link_token(student_id: int) -> str:
    """Generate deterministic HMAC hash token for student's parent link."""
    secret = getattr(settings, "SECRET_KEY", "grandec-parent-secret")
    raw = f"grandec_parent_link:{student_id}:{secret[:16]}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def verify_parent_deep_link_token(student_id: int, token: str) -> bool:
    """Safely verify HMAC hash token."""
    if not token or not student_id:
        return False
    expected = generate_parent_deep_link_token(student_id)
    return hmac.compare_digest(expected.lower(), str(token).lower())


def get_parent_deep_link(student_id: int) -> str:
    """Build full Telegram bot deep link URL for student."""
    token = generate_parent_deep_link_token(student_id)
    bot_username = getattr(settings, "TELEGRAM_BOT_USERNAME", "grandec_bot")
    return f"https://t.me/{bot_username}?start=parent_{student_id}_{token}"


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
