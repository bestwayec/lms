"""Telegram Bot English Center commands (/english) for students and teachers."""

from __future__ import annotations

import logging
from typing import Any

from asgiref.sync import sync_to_async
from django.conf import settings
from django.db.models import Q
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


def build_english_bot_payload(user: Any) -> dict[str, Any]:
    """Role-aware English summary & safe deep links for Telegram Bot & TMA."""
    from apps.accounts.access import is_platform_admin
    from apps.accounts.models import Profile
    from apps.courses.models import StudentGroup
    from apps.essays.models import EssaySubmission
    from apps.speaking.models import SpeakingSubmission
    from apps.vocabulary.models import GrammarCategory, StudentWordMistake

    base_url = getattr(settings, "SITE_URL", "https://grandec.uz").rstrip("/")
    role = getattr(user, "role", "student")
    is_teacher_or_admin = role in ("teacher", "center_admin", "admin") or is_platform_admin(user) or user.is_superuser

    if is_teacher_or_admin:
        group_ids = list(
            StudentGroup.objects.filter(teacher=user, status=StudentGroup.Status.ACTIVE).values_list("id", flat=True)
        )
        student_ids = list(
            StudentGroup.objects.filter(id__in=group_ids).values_list("students__id", flat=True).distinct()
        )
        pending_w = EssaySubmission.objects.filter(
            status=EssaySubmission.Status.PENDING_TEACHER,
        ).filter(Q(topic__subject="english") | Q(max_score__in=(9, 16, 75)))
        if not (is_platform_admin(user) or user.is_superuser):
            pending_w = pending_w.filter(Q(student_id__in=student_ids) | Q(assigned_reviewer=user))

        pending_s = SpeakingSubmission.objects.filter(
            Q(teacher_review_requested=True) | Q(status=SpeakingSubmission.Status.PENDING_TEACHER),
            teacher_reviewed_at__isnull=True,
        )
        if not (is_platform_admin(user) or user.is_superuser):
            pending_s = pending_s.filter(user_id__in=student_ids)

        return {
            "role": "teacher",
            "pending_writing": pending_w.count(),
            "pending_speaking": pending_s.count(),
            "workspace_url": f"{base_url}/teacher/english",
            "web_fallback_urls": {
                "workspace": f"{base_url}/teacher/english",
                "essay_queue": f"{base_url}/teacher/essays",
            },
        }

    profile, _ = Profile.objects.get_or_create(user=user)
    due_vocab = StudentWordMistake.objects.filter(student=user, is_mastered=False).count()
    grammar_count = GrammarCategory.objects.count()
    return {
        "role": "student",
        "track": profile.english_track,
        "target_band": float(profile.target_band) if profile.target_band is not None else None,
        "target_cefr_level": profile.target_cefr_level or "",
        "due_vocab": due_vocab,
        "grammar_topics": grammar_count,
        "full_mock_web_only": True,
        "web_fallback_urls": {
            "center": f"{base_url}/english",
            "vocabulary": f"{base_url}/vocabulary",
            "grammar": f"{base_url}/grammar",
            "speaking": f"{base_url}/speaking",
            "writing_studio": f"{base_url}/essays/studio",
        },
    }


async def english_bot_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Interactive /english command with Student Practice & Teacher Workspace deep links."""
    if not update.effective_user or not update.message:
        return

    from apps.accounts.models import User

    user = await sync_to_async(
        lambda: User.objects.filter(telegram_chat_id=update.effective_user.id).first()
    )()
    if not user:
        await update.message.reply_text(
            "Ingliz tili markazini ochish uchun avval hisobingizni bog'lang (/start)."
        )
        return

    payload = await sync_to_async(build_english_bot_payload)(user)
    if payload["role"] == "teacher":
        text = (
            "🎓 <b>GRANDEC English — Ustoz Kabineti</b>\n\n"
            f"✍️ Tekshirilmagan Writing: <b>{payload['pending_writing']}</b>\n"
            f"🎙️ Tekshirilmagan Speaking: <b>{payload['pending_speaking']}</b>\n\n"
            "Batafsil baholash, IELTS/Multi-level tahlili va eksport uchun veb ish joyini oching."
        )
        kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton("🧑‍🏫 English Teacher Workspace", web_app=WebAppInfo(url=payload["workspace_url"]))]]
        )
    else:
        urls = payload["web_fallback_urls"]
        text = (
            "🇬🇧 <b>GRANDEC English Learning Center</b>\n\n"
            f"🎯 Yo'nalish: <b>{payload['track']}</b>\n"
            f"🃏 Takrorlash kerak so'zlar: <b>{payload['due_vocab']}</b>\n"
            f"📘 Grammatika mavzulari: <b>{payload['grammar_topics']}</b>\n\n"
            "ℹ️ <i>To'liq 4-ko'nikmali Full Mock va mikrofonli Speaking sessiyalari brauzerda barqaror ishlaydi.</i>"
        )
        kb = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("🎓 English Center", web_app=WebAppInfo(url=urls["center"]))],
                [
                    InlineKeyboardButton("🃏 Vocabulary", web_app=WebAppInfo(url=urls["vocabulary"])),
                    InlineKeyboardButton("📘 Grammar", web_app=WebAppInfo(url=urls["grammar"])),
                ],
                [InlineKeyboardButton("🌐 Speaking & Mocks (Web)", url=urls["speaking"])],
            ]
        )

    await update.message.reply_text(text, parse_mode="HTML", reply_markup=kb)
