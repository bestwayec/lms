"""Student homework in the bot (/vazifalarim) — a read-only view of the website.

Uses the same service as the website (apps.courses.homework_service), so a
status or score shown here is exactly what the student sees online. Only a
verified, active account linked to this Telegram id is served, and only in a
private chat (homework scores are personal).
"""

from __future__ import annotations

import html
from typing import Any

from asgiref.sync import sync_to_async
from django.conf import settings
from django.utils import timezone

STATUS_ICON = {
    "not_started": "🆕",
    "in_progress": "▶️",
    "submitted": "📨",
    "awaiting_review": "🕒",
    "graded": "✅",
    "overdue": "⏰",
    "cancelled": "🚫",
    "grading_failed": "⚠️",
}
STATUS_TEXT = {
    "not_started": "Boshlanmagan",
    "in_progress": "Jarayonda",
    "submitted": "Topshirildi",
    "awaiting_review": "Tekshiruv kutilmoqda",
    "graded": "Baholandi",
    "overdue": "Muddati o'tgan",
    "cancelled": "Bekor qilingan",
    "grading_failed": "Natija hali tayyor emas",
}


def verified_user_for_telegram(telegram_id: int):
    from apps.accounts.models import User

    user = User.objects.filter(telegram_chat_id=telegram_id, is_active=True).first()
    if user is None or not user.telegram_identity_verified_at:
        return None
    return user


def render_homework_list(user, limit: int = 10) -> tuple[str, list[list[dict[str, str]]]]:
    from apps.courses.homework_service import get_student_homework_list

    items = [i for i in get_student_homework_list(user) if i["status"] != "cancelled"]
    open_items = [i for i in items if i["status"] in ("not_started", "in_progress", "grading_failed")]
    done = [i for i in items if i not in open_items]
    if not items:
        return "📚 Sizda hozircha vazifa yo'q.", _buttons()
    lines = ["📚 <b>Mening vazifalarim</b>"]
    for item in (open_items + done)[:limit]:
        due = timezone.localtime(timezone.datetime.fromisoformat(item["due_date"])).strftime("%d.%m %H:%M")
        status = item["status"]
        score = f" — {html.escape(item['score_display'])}" if status == "graded" and item["score_display"] else ""
        lines.append(
            f"{STATUS_ICON.get(status, '•')} {html.escape(item['title'])}\n"
            f"    {STATUS_TEXT.get(status, status)}{score} · {due}"
        )
    return "\n".join(lines), _buttons()


def _buttons() -> list[list[dict[str, Any]]]:
    url = f"{getattr(settings, 'SITE_URL', '').rstrip('/')}/my-homework"
    if not url.startswith("https://"):
        return []
    return [[{"text": "🌐 Saytda ochish", "url": url}, {"text": "📱 Mini App", "web_app": {"url": url}}]]


async def my_homework_handler(update, context) -> None:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

    from apps.notifications.bot.handlers import _require_private_chat, send_reply

    if not await _require_private_chat(update):
        return
    tg_user = update.effective_user
    if tg_user is None:
        return
    user = await sync_to_async(verified_user_for_telegram)(tg_user.id)
    if user is None:
        await send_reply(update, "Avval /start orqali hisobingizni tasdiqlang.")
        return
    text, buttons = await sync_to_async(render_homework_list)(user)
    markup = None
    if buttons:
        row = []
        for b in buttons[0]:
            if "web_app" in b:
                row.append(InlineKeyboardButton(b["text"], web_app=WebAppInfo(url=b["web_app"]["url"])))
            else:
                row.append(InlineKeyboardButton(b["text"], url=b["url"]))
        markup = InlineKeyboardMarkup([row])
    await send_reply(update, text, parse_mode="HTML", reply_markup=markup)
