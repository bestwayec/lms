"""
Telegram Group Assistant & Universal Bot Platform 5.0 for Grand Education.
Integrates Telegram groups and bot workspaces with LMS records:
  - 1-Click Deep-Link (/start link_GR-XXXX) and /ulash, /link, /link_group to bind group with StudentGroup
  - /uzish, /unlink_group for safe group unlinking with audit
  - /menu, /guruh, /boshqaruv for clean pinned-style classroom group management menu:
      * 📚 Bugungi vazifalar
      * 📝 Faol testlar
      * 📅 Dars jadvali
      * ✅ Davomat (Database-backed persistent AttendanceSession)
      * 📊 Guruh progressi
      * 🏆 Ixtiyoriy reyting
      * 📱 Mini App
      * 👨‍🏫 Ustoz bilan bog‘lanish
  - Persistent daily attendance (/davomat, /davomat_yakun) backed by AttendanceSession & AttendanceRecord
      * Present, Absent, Late, Excused
      * Multiple lessons per day
      * Explicit review before finalization
      * Stale revision & 409 conflict recovery
      * Full bot restart recovery
  - Teacher Bot Workspace 5.0 (/ustoz):
      * 👥 Guruhlarim, 📝 Test yaratish, 📤 Test yuborish (Unified Homework Engine)
      * ✅ Davomat, 📊 Natijalar, 📈 Live monitoring, 🔔 Eslatmalar, ⚙️ Sozlamalar
  - Admin Bot Workspace 5.0 (/admin):
      * Scoped by tenant: Platform admin vs Center admin
      * Markazlar, Ustozlar, Guruhlar, Barcha testlar, Hisobotlar, Xavfsizlik, Sozlamalar
"""

from __future__ import annotations

import logging
from html import escape
import os
from typing import Any

from asgiref.sync import sync_to_async
from django.conf import settings
from django.utils import timezone
from telegram import (
    ChatMember,
    ChatMemberUpdated,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
    WebAppInfo,
)
from telegram.constants import ChatType, ParseMode
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def _run_db(func, *args, **kwargs):
    return await sync_to_async(func)(*args, **kwargs)


async def _send_group_reply(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, **kwargs):
    """Send reply via update.message.reply_text or fallback to context.bot.send_message."""
    msg = getattr(update, "message", None)
    if msg and hasattr(msg, "reply_text"):
        return await msg.reply_text(text, **kwargs)
    chat = getattr(update, "effective_chat", None)
    if chat and getattr(context, "bot", None):
        return await context.bot.send_message(chat_id=chat.id, text=text, **kwargs)
    return None


async def _authorized_group_teacher(update: Update) -> bool:
    chat, actor = update.effective_chat, update.effective_user
    if not chat or not actor:
        return False

    def check():
        from apps.accounts.access import is_platform_admin
        from apps.accounts.models import User
        from apps.courses.models import StudentGroup

        user = User.objects.filter(
            telegram_chat_id=actor.id,
            telegram_identity_verified_at__isnull=False,
            is_active=True,
        ).first()
        group = StudentGroup.objects.filter(telegram_chat_id=chat.id).first()
        return bool(user and group and (is_platform_admin(user) or (user.role == "teacher" and group.teacher_id == user.id)))

    return await _run_db(check)


# ---------------------------------------------------------------------------
# 1. Greeting when Bot joins group or is promoted
# ---------------------------------------------------------------------------
async def on_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Triggered when bot is added to a group or promoted to administrator."""
    result: ChatMemberUpdated | None = update.my_chat_member
    if not result:
        return

    chat = update.effective_chat
    if not chat or chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP, "group", "supergroup"):
        return

    new_status = result.new_chat_member.status
    old_status = result.old_chat_member.status if result.old_chat_member else None

    # Bot became a member or administrator
    if new_status in (ChatMember.MEMBER, ChatMember.ADMINISTRATOR) and old_status not in (
        ChatMember.MEMBER,
        ChatMember.ADMINISTRATOR,
    ):
        await send_group_welcome_message(chat.id, context)


async def on_new_chat_members(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Fallback handler for service message when bot is added to group."""
    message = update.message
    if not message or not message.new_chat_members:
        return

    chat = update.effective_chat
    if not chat or chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP, "group", "supergroup"):
        return

    bot_user = context.bot
    if any(m.id == bot_user.id for m in message.new_chat_members):
        await send_group_welcome_message(chat.id, context)


async def send_group_welcome_message(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send welcome greeting and linking instructions to group."""
    text = (
        "👋 <b>Salom! Men Grand Education — ta'lim tizimi botiman.</b> Ushbu guruh qaysi ustozga tegishli?\n\n"
        "Ustoz, ushbu guruhni platformadagi sinfingizga ulash uchun guruhda quyidagi buyruqni yuboring:\n"
        "👉 <code>/ulash Guruh_Kodi</code> yoki <code>/link_group Guruh_Kodi</code> (masalan: <code>/ulash GR-11A</code>)\n\n"
        "<i>Guruh kodingizni yoki 1-klik ulash havolasini LMS kabinetingizdagi 'Guruhlar' bo'limidan olishingiz mumkin.</i>"
    )
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=ParseMode.HTML,
        )
    except Exception as exc:
        logger.warning("Failed to send welcome message to group %s: %s", chat_id, exc)


# ---------------------------------------------------------------------------
# 2. Link & Unlink Group Helpers & Commands (/ulash, /link, /uzish)
# ---------------------------------------------------------------------------
async def bind_telegram_group_by_code(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    code: str,
) -> bool:
    """
    Bind a Telegram group/supergroup chat to a StudentGroup by its invite_code (or name).
    Used by both 1-click deep-link (/start link_GR-8492) and manual commands (/ulash, /link, /link_group).
    """
    chat = update.effective_chat
    user = update.effective_user
    if not chat:
        return False

    if chat.type in (ChatType.PRIVATE, "private"):
        await _send_group_reply(
            update,
            context,
            "Ushbu buyruqni o'quvchilaringizning Telegram guruhida yozishingiz kerak.\n"
            "Guruhga botni admin qilib qo'shing va u yerda yozing:\n"
            "👉 <code>/ulash Guruh_Kodi</code> yoki <code>/link_group Guruh_Kodi</code>",
            parse_mode=ParseMode.HTML,
        )
        return False

    clean_code = (code or "").strip()
    if clean_code.lower().startswith("link_"):
        clean_code = clean_code[5:].strip()
    code_input = clean_code.upper()

    if not code_input:
        await _send_group_reply(
            update,
            context,
            "⚠️ Iltimos, guruh kodini ko'rsating!\n"
            "Masalan: <code>/ulash GR-8492</code> yoki <code>/link_group GR-11A</code>",
            parse_mode=ParseMode.HTML,
        )
        return False

    from apps.courses.models import StudentGroup
    from apps.accounts.models import User as UserModel

    chat_title = getattr(chat, "title", "") or ""
    user_id = getattr(user, "id", None) if user else None
    if not user_id:
        await _send_group_reply(update, context, "⛔️ Tasdiqlangan hisob talab qilinadi.")
        return False
    try:
        member = await context.bot.get_chat_member(chat.id, user_id)
        if member.status not in (ChatMember.OWNER, ChatMember.ADMINISTRATOR, "creator", "administrator"):
            raise PermissionError("actor is not a Telegram group administrator")
    except Exception:
        logger.warning("Group binding denied: Telegram administrator verification failed for actor=%s chat=%s", user_id, chat.id)
        await _send_group_reply(update, context, "⛔️ Telegram guruhi administratori huquqi talab qilinadi.")
        return False

    def _link_db():
        from django.db import connection, transaction
        from apps.accounts.access import is_platform_admin

        with transaction.atomic():
            if connection.vendor == "postgresql":
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_advisory_xact_lock(%s, hashtext(%s))", [0x475250, str(chat.id)])
            actor = UserModel.objects.select_for_update().filter(
                telegram_chat_id=user_id, telegram_identity_verified_at__isnull=False, is_active=True
            ).first()
            if not actor:
                return None, "Tasdiqlangan LMS hisobi talab qilinadi."
            group = (
                StudentGroup.objects.select_for_update()
                .filter(invite_code__iexact=code_input)
                .select_related("teacher")
                .first()
            )
            if not group:
                return None, "Guruh topilmadi"
            if not (group.teacher_id == actor.id and actor.role == "teacher") and not is_platform_admin(actor):
                return None, "Faqat guruhning o'z ustozi yoki platforma administratori ulay oladi."
            if group.telegram_chat_id not in (None, chat.id):
                return None, "Guruh boshqa Telegram chatga ulangan. Avval xavfsiz uzing."
            if StudentGroup.objects.select_for_update().filter(telegram_chat_id=chat.id).exclude(pk=group.pk).exists():
                return None, "Bu Telegram chat boshqa guruhga ulangan."
            group.telegram_chat_id = chat.id
            group.telegram_chat_title = str(chat_title)[:255]
            group.save(update_fields=["telegram_chat_id", "telegram_chat_title"])
            logger.info("Group binding actor=%s group=%s chat=%s", actor.pk, group.pk, chat.id)
            teacher_name = group.teacher.get_full_name() or group.teacher.email
            return {
                "id": group.id,
                "name": escape(group.name),
                "code": escape(group.invite_code),
                "teacher": escape(teacher_name),
                "students_count": group.students.count(),
            }, None

    res, err = await _run_db(_link_db)
    if err and err != "Guruh topilmadi":
        await _send_group_reply(update, context, f"⛔️ {err}")
        return False
    if err or not res:
        await _send_group_reply(
            update,
            context,
            f"❌ <b>{code_input}</b> kodi bo'yicha guruh topilmadi!\n"
            "Iltimos, kod to'g'ri kiritilganini tekshiring (masalan: <code>/ulash GR-8492</code>).",
            parse_mode=ParseMode.HTML,
        )
        return False

    text = (
        "✅ <b>Guruh muvaffaqiyatli bog'landi!</b>\n\n"
        f"👥 <b>Guruh:</b> {res['name']}\n"
        f"👨‍🏫 <b>Ustoz:</b> {res['teacher']}\n"
        f"🔑 <b>Guruh kodi:</b> <code>{res['code']}</code>\n"
        f"🎓 <b>O'quvchilar:</b> {res['students_count']} ta\n\n"
        "Boshqaruv menyusini ochish uchun: <code>/menu</code> yoki <code>/guruh</code>"
    )
    keyboard = _build_group_menu_keyboard(res["id"])
    await _send_group_reply(update, context, text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    return True


async def cmd_link_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ustoz o'z Telegram guruhini LMS tizimidagi StudentGroup ga bog'laydi (/ulash, /link, /link_group)."""
    chat = update.effective_chat
    if not chat:
        return

    if chat.type in (ChatType.PRIVATE, "private"):
        await _send_group_reply(
            update,
            context,
            "Ushbu buyruqni o'quvchilaringizning Telegram guruhida yozishingiz kerak.\n"
            "Guruhga botni admin qilib qo'shing va u yerda yozing:\n"
            "👉 <code>/link_group Guruh_Kodi</code> yoki <code>/ulash Guruh_Kodi</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    args = list(context.args) if getattr(context, "args", None) else []
    if not args and getattr(update, "message", None) and isinstance(getattr(update.message, "text", None), str):
        parts = update.message.text.strip().split()
        if len(parts) > 1 and parts[0].startswith("/"):
            args = parts[1:]

    if not args:
        await _send_group_reply(
            update,
            context,
            "⚠️ Iltimos, guruh kodini ko'rsating!\n"
            "Masalan: <code>/ulash GR-8492</code> yoki <code>/link_group GR-11A</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    code_input = " ".join(args).strip()
    await bind_telegram_group_by_code(update, context, code_input)


link_group_command = cmd_link_group


async def cmd_unlink_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ustoz yoki admin Telegram guruhni LMS sinfidan xavfsiz uzadi (/uzish, /unlink_group)."""
    chat = update.effective_chat
    if not chat or chat.type in (ChatType.PRIVATE, "private"):
        await _send_group_reply(update, context, "Ushbu buyruq Telegram guruhida ishlatiladi.")
        return

    if not await _authorized_group_teacher(update):
        await _send_group_reply(update, context, "⛔️ Faqat shu guruhning tasdiqlangan ustozi yoki platforma admini guruhni uza oladi.")
        return

    def _unlink():
        from apps.courses.models import StudentGroup
        group = StudentGroup.objects.filter(telegram_chat_id=chat.id).first()
        if not group:
            return None, "Ushbu chat biron bir LMS guruhiga ulanmagan."
        g_name = group.name
        group.telegram_chat_id = None
        group.telegram_chat_title = ""
        group.save(update_fields=["telegram_chat_id", "telegram_chat_title"])
        return g_name, None

    g_name, err = await _run_db(_unlink)
    if err:
        await _send_group_reply(update, context, f"⚠️ {err}")
        return

    await _send_group_reply(
        update,
        context,
        f"✅ «{escape(g_name)}» guruhi Telegram chatidan muvaffaqiyatli uzildi.\n"
        "Qayta ulash uchun: <code>/ulash Guruh_Kodi</code>",
        parse_mode=ParseMode.HTML,
    )


# ---------------------------------------------------------------------------
# 3. Pinned-Style Classroom Group Management Menu (/menu, /guruh, /boshqaruv)
# ---------------------------------------------------------------------------
def _build_group_menu_keyboard(group_id: int) -> InlineKeyboardMarkup:
    site_url = getattr(settings, "SITE_URL", "https://grandec.uz").rstrip("/")
    tma_url = f"{site_url}/tma"
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📚 Bugungi vazifalar", callback_data=f"grp_m_hw_{group_id}"),
            InlineKeyboardButton("📝 Faol testlar", callback_data=f"grp_m_tests_{group_id}"),
        ],
        [
            InlineKeyboardButton("📅 Dars jadvali", callback_data=f"grp_m_sched_{group_id}"),
            InlineKeyboardButton("✅ Davomat", callback_data=f"grp_m_att_{group_id}"),
        ],
        [
            InlineKeyboardButton("📊 Guruh progressi", callback_data=f"grp_m_prog_{group_id}"),
            InlineKeyboardButton("🏆 Ixtiyoriy reyting", callback_data=f"grp_m_rank_{group_id}"),
        ],
        [
            InlineKeyboardButton("📱 Mini App", web_app=WebAppInfo(url=tma_url)),
            InlineKeyboardButton("👨‍🏫 Ustoz bilan bog‘lanish", callback_data=f"grp_m_tch_{group_id}"),
        ],
    ])


def _render_group_menu(data: dict[str, Any]) -> tuple[str, InlineKeyboardMarkup]:
    text = (
        "🎓 <b>GRANDEC | Guruh boshqaruvi</b>\n\n"
        f"👥 <b>Guruh:</b> {escape(data['name'])}\n"
        f"👨‍🏫 <b>Ustoz:</b> {escape(data['teacher'])}\n"
        f"🔑 <b>Guruh kodi:</b> <code>{escape(data['code'])}</code>\n"
        f"🎓 <b>O'quvchilar:</b> {data['students_count']} ta\n\n"
        "<i>Kerakli bo'limni tanlang:</i>"
    )
    keyboard = _build_group_menu_keyboard(data["id"])
    return text, keyboard


async def group_menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Classroom group pinned-style management menu (/menu, /guruh, /boshqaruv)."""
    chat = update.effective_chat
    if not chat or chat.type in (ChatType.PRIVATE, "private"):
        await _send_group_reply(update, context, "Ushbu buyruq Telegram guruhida ishlatiladi.")
        return

    def _get_group_info():
        from apps.courses.models import StudentGroup
        group = StudentGroup.objects.filter(telegram_chat_id=chat.id).select_related("teacher").first()
        if not group:
            return None
        return {
            "id": group.id,
            "name": group.name,
            "code": group.invite_code,
            "teacher": group.teacher.get_full_name() or group.teacher.email,
            "students_count": group.students.filter(is_active=True).count(),
        }

    data = await _run_db(_get_group_info)
    if not data:
        await _send_group_reply(
            update,
            context,
            "⚠️ Ushbu guruh hali LMS sinfiga ulanmagan.\n"
            "Ulashingiz uchun ustoz guruhda yozishi kerak:\n"
            "👉 <code>/ulash Guruh_Kodi</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    text, markup = _render_group_menu(data)
    await _send_group_reply(update, context, text, parse_mode=ParseMode.HTML, reply_markup=markup)


# ---------------------------------------------------------------------------
# 4. Database-Backed Persistent Daily Attendance (/davomat, /davomat_yakun)
# ---------------------------------------------------------------------------
def _db_get_or_create_open_attendance(chat_id: int, actor_id: int):
    """
    Retrieves or creates a DRAFT AttendanceSession in PostgreSQL/SQLite database.
    Recovers seamlessly across bot restarts.
    """
    from apps.courses.models import StudentGroup
    from apps.accounts.models import User
    from apps.accounts.access import is_platform_admin
    from apps.attendance.models import AttendanceSession, AttendanceRecord
    from apps.attendance.services import create_session, revision

    group = StudentGroup.objects.filter(telegram_chat_id=chat_id).select_related("teacher").first()
    if not group:
        return None, "Guruh topilmadi"

    actor = User.objects.filter(telegram_chat_id=actor_id, telegram_identity_verified_at__isnull=False, is_active=True).first()
    if not actor or not (is_platform_admin(actor) or (actor.role == "teacher" and group.teacher_id == actor.id)):
        return None, "Faqat guruh ustozi davomat ochishi mumkin"

    today = timezone.localdate()
    # Check for unfinalized session today
    session = (
        AttendanceSession.objects.filter(
            group=group,
            lesson_date=today,
            status=AttendanceSession.Status.DRAFT,
        )
        .order_by("-id")
        .first()
    )
    if not session:
        session, _ = create_session(
            group=group,
            teacher=group.teacher,
            lesson_date=today,
            title=f"{group.name} Telegram davomati",
        )

    # Get records
    present_records = list(
        AttendanceRecord.objects.filter(session=session, status=AttendanceRecord.Status.PRESENT)
        .select_related("student")
        .order_by("updated_at")
    )
    present_names = [r.student.get_full_name() or r.student.email for r in present_records]
    enrolled_count = group.students.filter(is_active=True).count()

    return {
        "session_id": session.id,
        "group_id": group.id,
        "group_name": group.name,
        "teacher_name": group.teacher.get_full_name() or group.teacher.email,
        "date_str": today.strftime("%d.%m.%Y"),
        "enrolled_count": enrolled_count,
        "present_count": len(present_records),
        "present_names": present_names,
        "revision_token": revision(session),
    }, None


def _db_mark_student_present(session_id: int, tg_user_id: int):
    """Marks student present in the active AttendanceSession in database."""
    from apps.accounts.models import User
    from apps.attendance.models import AttendanceSession, AttendanceRecord
    from apps.attendance.services import mark

    student = User.objects.filter(
        telegram_chat_id=tg_user_id,
        telegram_identity_verified_at__isnull=False,
        is_active=True,
    ).first()
    if not student:
        return {"status": "unverified", "message": "⛔️ Avval hisobingizni botda tasdiqlang (/start)."}

    session = AttendanceSession.objects.select_related("group", "group__teacher").filter(id=session_id).first()
    if not session:
        return {"status": "error", "message": "⚠️ Davomat sessiyasi topilmadi."}

    if session.status != AttendanceSession.Status.DRAFT:
        return {"status": "closed", "message": "ℹ️ Ushbu davomat allaqachon yakunlangan."}

    if not session.group.students.filter(id=student.id).exists():
        return {"status": "not_enrolled", "message": "⛔️ Siz bu guruh ro'yxatida emassiz."}

    existing = AttendanceRecord.objects.filter(session=session, student=student).first()
    if existing and existing.status == AttendanceRecord.Status.PRESENT:
        return {"status": "already", "message": "Siz allaqachon 'Keldim' deb belgilangansiz! 🟢"}

    # Atomic mark
    mark(
        session,
        student,
        AttendanceRecord.Status.PRESENT,
        actor=student,
        reason="Telegram guruh orqali 'Keldim'",
    )

    present_records = list(
        AttendanceRecord.objects.filter(session=session, status=AttendanceRecord.Status.PRESENT)
        .select_related("student")
        .order_by("updated_at")
    )
    present_names = [r.student.get_full_name() or r.student.email for r in present_records]
    enrolled_count = session.group.students.filter(is_active=True).count()

    return {
        "status": "success",
        "message": "Davomatingiz qabul qilindi! 🟢",
        "session_id": session.id,
        "group_name": session.group.name,
        "teacher_name": session.group.teacher.get_full_name() or session.group.teacher.email,
        "date_str": session.lesson_date.strftime("%d.%m.%Y"),
        "present_count": len(present_records),
        "enrolled_count": enrolled_count,
        "present_names": present_names,
    }


def _db_get_attendance_session_info(session_id: int):
    from apps.attendance.models import AttendanceSession, AttendanceRecord

    session = AttendanceSession.objects.select_related("group", "group__teacher").filter(id=session_id).first()
    if not session:
        return None
    present_records = list(
        AttendanceRecord.objects.filter(session=session, status=AttendanceRecord.Status.PRESENT)
        .select_related("student")
        .order_by("updated_at")
    )
    present_names = [r.student.get_full_name() or r.student.email for r in present_records]
    enrolled_count = session.group.students.filter(is_active=True).count()
    return {
        "session_id": session.id,
        "group_id": session.group.id,
        "group_name": session.group.name,
        "teacher_name": session.group.teacher.get_full_name() or session.group.teacher.email,
        "date_str": session.lesson_date.strftime("%d.%m.%Y"),
        "enrolled_count": enrolled_count,
        "present_count": len(present_records),
        "present_names": present_names,
        "status": session.status,
    }


def _db_finalize_session(session_id: int, actor_tg_id: int):
    from apps.accounts.models import User
    from apps.accounts.access import is_platform_admin
    from apps.attendance.models import AttendanceSession, AttendanceRecord
    from apps.attendance.services import finalize, StaleAttendanceError

    actor = User.objects.filter(telegram_chat_id=actor_tg_id, telegram_identity_verified_at__isnull=False, is_active=True).first()
    session = AttendanceSession.objects.select_related("group", "group__teacher").filter(id=session_id).first()
    if not session:
        return None, "Davomat sessiyasi topilmadi."
    if not actor or not (is_platform_admin(actor) or (actor.role == "teacher" and session.group.teacher_id == actor.id)):
        return None, "Faqat guruh ustozi davomatni yakunlay oladi."

    if session.status == AttendanceSession.Status.FINALIZED:
        return None, "Ushbu davomat allaqachon yakunlangan."

    try:
        finalized_res = finalize(
            session,
            actor=actor,
            mark_unmarked_as_absent=True,
            reason="Telegram guruh orqali yakunlandi",
        )
        if not finalized_res.get("ok"):
            return None, "Davomatni yakunlab bo'lmadi."
    except StaleAttendanceError:
        return None, "Davomat tahrirlandi, qayta tekshirib tasdiqlang."

    records = AttendanceRecord.objects.filter(session=session).select_related("student")
    present_cnt = records.filter(status=AttendanceRecord.Status.PRESENT).count()
    absent_cnt = records.filter(status=AttendanceRecord.Status.ABSENT).count()
    late_cnt = records.filter(status=AttendanceRecord.Status.LATE).count()
    excused_cnt = records.filter(status=AttendanceRecord.Status.EXCUSED).count()
    total_cnt = records.count()

    present_names = [r.student.get_full_name() or r.student.email for r in records.filter(status=AttendanceRecord.Status.PRESENT)]
    absent_names = [r.student.get_full_name() or r.student.email for r in records.filter(status=AttendanceRecord.Status.ABSENT)]

    return {
        "group_name": session.group.name,
        "date_str": session.lesson_date.strftime("%d.%m.%Y"),
        "total_count": total_cnt,
        "present_count": present_cnt,
        "absent_count": absent_cnt,
        "late_count": late_cnt,
        "excused_count": excused_cnt,
        "present_names": present_names,
        "absent_names": absent_names,
    }, None


def _format_attendance_message(data: dict[str, Any]) -> tuple[str, InlineKeyboardMarkup]:
    g_name = escape(data["group_name"])
    t_name = escape(data["teacher_name"])
    d_str = escape(data["date_str"])
    p_cnt = data["present_count"]
    e_cnt = data["enrolled_count"]
    sid = data["session_id"]

    roster_lines = [f"{i}. 🟢 {escape(name)}" for i, name in enumerate(data.get("present_names", []), 1)]
    roster_text = "\n".join(roster_lines) if roster_lines else "<i>Hozircha hech kim belgilanmadi</i>"

    text = (
        f"📋 <b>{g_name} — KUNLIK DAVOMAT</b>\n"
        f"📅 Sana: <b>{d_str}</b>\n"
        f"👨‍🏫 Ustoz: <b>{t_name}</b>\n"
        "Holat: <b>🟢 Ochiq (Qoralama)</b>\n\n"
        "👇 O'quvchilar, darsda hozir bo'lsangiz quyidagi tugmani bosing:\n\n"
        f"🟢 <b>Darsda qatnashayotganlar ({p_cnt}/{e_cnt} ta):</b>\n"
        f"{roster_text}"
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🟢 Keldim / Darsdaman", callback_data=f"grp_att_here_{sid}")],
        [InlineKeyboardButton("🏁 Tekshirish va yakunlash", callback_data=f"grp_att_rev_{sid}")],
        [InlineKeyboardButton("🔄 Yangilash", callback_data=f"grp_att_ref_{sid}")],
    ])
    return text, keyboard


def _format_attendance_review_message(data: dict[str, Any]) -> tuple[str, InlineKeyboardMarkup]:
    g_name = escape(data["group_name"])
    d_str = escape(data["date_str"])
    p_cnt = data["present_count"]
    e_cnt = data["enrolled_count"]
    sid = data["session_id"]
    unmarked_cnt = max(0, e_cnt - p_cnt)

    text = (
        f"📋 <b>{g_name} — DAVOMATNI TEKSHIRISH</b>\n"
        f"📅 Sana: <b>{d_str}</b>\n\n"
        f"🟢 Kelganlar: <b>{p_cnt} nafar</b>\n"
        f"🔴 Belgilanmaganlar: <b>{unmarked_cnt} nafar</b> (yakunlanganda avtomatik 'Kelmadi' deb yoziladi)\n"
        f"👥 Jami ro'yxat: <b>{e_cnt} nafar</b>\n\n"
        "Davomatni yakunlashga tayyormisiz?"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Ha, yakunlash va LMS ga saqlash", callback_data=f"grp_att_fin_{sid}")],
        [InlineKeyboardButton("🔙 Ortga (Davomatga qaytish)", callback_data=f"grp_att_ref_{sid}")],
    ])
    return text, keyboard


async def group_davomat_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ustoz dars boshida guruhda /davomat buyrug'ini yuboradi."""
    chat = update.effective_chat
    actor = update.effective_user
    if not chat or chat.type in (ChatType.PRIVATE, "private"):
        await _send_group_reply(update, context, "Ushbu buyruq Telegram guruhida ishlatiladi.")
        return
    if not actor:
        return

    if not await _authorized_group_teacher(update):
        await _send_group_reply(update, context, "⛔️ Faqat shu guruhning tasdiqlangan ustozi davomat ochishi mumkin.")
        return

    data, err = await _run_db(_db_get_or_create_open_attendance, chat.id, actor.id)
    if err or not data:
        await _send_group_reply(update, context, f"⚠️ {err or 'Davomat ochishda xatolik'}")
        return

    text, markup = _format_attendance_message(data)
    await _send_group_reply(update, context, text, parse_mode=ParseMode.HTML, reply_markup=markup)


async def group_attendance_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """O'quvchi 'Keldim' tugmasini bosganda bazada AttendanceRecord yaratiladi."""
    query = update.callback_query
    if not query or not query.data:
        return

    user = update.effective_user
    if not user:
        return

    try:
        session_id = int(query.data.rsplit("_", 1)[-1])
    except (ValueError, IndexError):
        await query.answer("Xatolik yuz berdi.", show_alert=True)
        return

    res = await _run_db(_db_mark_student_present, session_id, user.id)
    if res["status"] in ("unverified", "not_enrolled", "closed", "error"):
        await query.answer(res["message"], show_alert=True)
        return
    if res["status"] == "already":
        await query.answer(res["message"], show_alert=False)
        return

    await query.answer(res["message"])

    # Re-render updated attendance message in-place
    text, markup = _format_attendance_message(res)
    try:
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
    except Exception as exc:
        logger.debug("Failed to edit attendance message: %s", exc)


async def group_davomat_yakun_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ustoz dars oxirida davomatni yakunlaydi va LMS tizimiga saqlaydi."""
    chat = update.effective_chat
    actor = update.effective_user
    if not chat or chat.type in (ChatType.PRIVATE, "private"):
        await _send_group_reply(update, context, "Ushbu buyruq Telegram guruhida ishlatiladi.")
        return
    if not actor:
        return

    if not await _authorized_group_teacher(update):
        await _send_group_reply(update, context, "⛔️ Faqat shu guruhning tasdiqlangan ustozi davomatni yakunlay oladi.")
        return

    # Fetch active session
    data, err = await _run_db(_db_get_or_create_open_attendance, chat.id, actor.id)
    if err or not data:
        await _send_group_reply(update, context, f"⚠️ {err or 'Faol davomat topilmadi.'}")
        return

    res, fin_err = await _run_db(_db_finalize_session, data["session_id"], actor.id)
    if fin_err or not res:
        await _send_group_reply(update, context, f"⚠️ {fin_err or 'Yakunlashda xatolik'}")
        return

    report_text = (
        f"📊 <b>{escape(res['group_name'])} — DAVOMAT YAKUNLANDI</b>\n"
        f"📅 Sana: <b>{escape(res['date_str'])}</b>\n\n"
        f"✅ <b>Darsda qatnashganlar:</b> {res['present_count']} nafar\n"
        f"❌ <b>Darsda qatnashmaganlar:</b> {res['absent_count']} nafar\n"
        f"👥 <b>Jami o'quvchilar:</b> {res['total_count']} nafar\n\n"
        "💾 <i>Davomat ma'lumotlari LMS kabinetingizga to'liq saqlandi!</i>"
    )
    await _send_group_reply(update, context, report_text, parse_mode=ParseMode.HTML)


# ---------------------------------------------------------------------------
# 5. Group Test Announcement & PIN (/yangi_test & /test)
# ---------------------------------------------------------------------------
async def group_yangi_test_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Guruhga yangi test havolasi, PIN kodi va Mini App tugmasini e'lon qiladi."""
    chat = update.effective_chat
    if not chat or chat.type in (ChatType.PRIVATE, "private"):
        await _send_group_reply(update, context, "Ushbu buyruq Telegram guruhida test e'lon qilish uchun ishlatiladi.")
        return

    if not await _authorized_group_teacher(update):
        await _send_group_reply(update, context, "⛔️ Faqat shu guruhning tasdiqlangan ustozi bu amalni bajara oladi.")
        return

    from apps.courses.models import StudentGroup
    from apps.tests.models import Test

    def _get_test_details(chat_id):
        group = StudentGroup.objects.filter(telegram_chat_id=chat_id).first()
        g_name = group.name if group else "Sinf"

        test = (
            Test.objects.filter(is_active=True, status="published", course__teacher_id=group.teacher_id)
            .order_by("-id")
            .first()
            if group
            else None
        )

        if not test:
            return None

        pin_code = test.access_pin or test.mock_code or ""
        q_count = test.questions.count()
        return {
            "group_name": g_name,
            "test_id": test.id,
            "title": test.title,
            "duration": getattr(test, "time_limit_minutes", 60),
            "questions_count": q_count,
            "pin": pin_code,
        }

    info = await _run_db(_get_test_details, chat.id)
    if not info:
        await _send_group_reply(update, context, "⚠️ Hozircha platformada nashr qilingan faol test mavjud emas.")
        return

    site_url = getattr(settings, "SITE_URL", "https://grandec.uz").rstrip("/")
    test_url = f"{site_url}/tma/#/tests/{info['test_id']}"
    web_url = f"{site_url}/take-test/{info['test_id']}"
    pin_text = f"🔑 <b>Kirish kodi:</b> <code>{escape(info['pin'])}</code>\n" if info["pin"] else ""

    text = (
        f"📢 <b>Diqqat, {escape(info['group_name'])} o'quvchilari!</b>\n"
        "Yangi test ochildi!\n\n"
        f"📝 <b>Test nomi:</b> {escape(info['title'])}\n"
        f"⏱ <b>Vaqt:</b> {info['duration']} daqiqa | {info['questions_count']} ta savol\n"
        f"{pin_text}\n"
        "👇 Testni topshirish uchun quyidagi tugmani bosing:"
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Testni Boshlash (Mini App)", web_app=WebAppInfo(url=test_url))],
        [InlineKeyboardButton("🌐 Veb-saytda topshirish", url=web_url)],
    ])

    await _send_group_reply(update, context, text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


# ---------------------------------------------------------------------------
# 6. Group Leaderboard & Mistake Analysis (/leaderboard & /reyting)
# ---------------------------------------------------------------------------
async def group_results_leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Guruh test natijalari reytingi, o'rtacha ball va tahlili."""
    chat = update.effective_chat
    if not chat:
        return

    from apps.courses.models import StudentGroup
    from apps.results.models import Result
    from apps.tests.bmb_grading import calculate_bmb_grade
    from django.db.models import Avg, Q
    from apps.accounts.models import User
    from apps.accounts.access import is_platform_admin

    def _calc_group_stats(chat_id, actor_id):
        group = StudentGroup.objects.filter(telegram_chat_id=chat_id).first()
        if not group:
            return "unbound", None
        actor = User.objects.filter(
            telegram_chat_id=actor_id, telegram_identity_verified_at__isnull=False, is_active=True,
        ).first()
        if not actor or not (is_platform_admin(actor) or (actor.role == "teacher" and group.teacher_id == actor.id)):
            return "forbidden", None

        students = list(group.students.filter(is_active=True))
        st_ids = [s.id for s in students]

        results = (
            Result.objects.filter(student_id__in=st_ids)
            .filter(Q(test__assigned_group=group) | Q(test__homework_assignments__group=group))
            .distinct()
            .select_related("student")
            .order_by("-percentage")
        )

        board = []
        seen_students = set()
        for r in results:
            if r.student_id in seen_students:
                continue
            seen_students.add(r.student_id)
            uname = r.student.get_full_name() or r.student.email
            pct = round(float(r.percentage or 0), 1)
            grd = calculate_bmb_grade(pct)["grade"]
            board.append({"name": uname, "score": pct, "grade": grd})

        avg_pct = 0.0
        if results.exists():
            avg_res = results.aggregate(avg=Avg("percentage"))["avg"]
            avg_pct = round(float(avg_res), 1) if avg_res else 0.0

        branch = getattr(group, "branch", None)
        branch_name = branch.name if branch else "Grand Education Bosh Filiali"
        if branch and getattr(branch, "branch_code", None):
            branch_name += f" ({branch.branch_code})"

        subj_slug = getattr(group, "subject", "uzbek")
        subj_map = {
            "biology": "🧬 Biologiya (Milliy sertifikat)",
            "chemistry": "🧪 Kimyo (Milliy sertifikat)",
            "law": "⚖️ Huquqshunoslik (Yurisprudensiya)",
            "uzbek": "🇺🇿 Ona tili va Adabiyot",
            "english": "🇬🇧 Ingliz tili (CEFR / IELTS)",
        }
        subj_title = subj_map.get(subj_slug, str(subj_slug).title())

        return "ok", {
            "group_name": group.name,
            "branch_name": branch_name,
            "subject_title": subj_title,
            "board": board[:10],
            "avg_score": avg_pct,
        }

    actor = update.effective_user
    result, stats = await _run_db(_calc_group_stats, chat.id, actor.id if actor else None)
    if result == "unbound":
        await _send_group_reply(update, context, "Bu guruh LMS guruhiga bog'lanmagan.")
        return
    if result != "ok":
        await _send_group_reply(update, context, "Bu batafsil hisobot faqat guruhning tasdiqlangan ustoziga shaxsiy yuboriladi.")
        return

    medals = ["🥇 1.", "🥈 2.", "🥉 3.", "4.", "5.", "6.", "7.", "8.", "9.", "10."]
    rows = []
    for i, item in enumerate(stats["board"]):
        prefix = medals[i] if i < len(medals) else f"{i + 1}."
        rows.append(f"{prefix} {escape(item['name'])} — <b>{item['score']} ball</b> ({item['grade']})")

    leaderboard_content = "\n".join(rows) if rows else "<i>Hozircha test topshirganlar yo'q</i>"
    b_name = stats.get("branch_name", "Grand Education Bosh Filiali")
    s_title = stats.get("subject_title", "Fan")
    text = (
        f"🏆 <b>Guruh Natijalari va Jonli Reyting:</b>\n"
        f"🏛 <b>Filial:</b> {escape(b_name)}\n"
        f"👥 <b>Guruh:</b> {escape(stats['group_name'])}\n"
        f"📚 <b>Fan yo'nalishi:</b> {escape(s_title)}\n\n"
        f"{leaderboard_content}\n\n"
        f"📊 <b>Guruh o'rtacha ko'rsatkichi:</b> {stats['avg_score']}%"
    )

    try:
        await context.bot.send_message(chat_id=actor.id, text=text, parse_mode=ParseMode.HTML)
        await _send_group_reply(update, context, "📊 Batafsil hisobot ustozning shaxsiy chatiga yuborildi.")
    except Exception:
        logger.exception("Could not send group leaderboard privately")
        await _send_group_reply(update, context, "Hisobotni olish uchun bot bilan shaxsiy suhbatni boshlang.")


cmd_reyting = group_results_leaderboard_command


# ---------------------------------------------------------------------------
# 7. Group Vedomost & Exam PDF Report (/vedomost & /report)
# ---------------------------------------------------------------------------
async def group_vedomost_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Guruh imtihon vedomostini PDF formatida generatsiya qilib yuborish."""
    chat = update.effective_chat
    user = update.effective_user
    if not chat:
        return

    if chat.type != "private":
        await _send_group_reply(update, context, "🔒 Shaxsiy hisobotni olish uchun botga shaxsiy chatda /vedomost yuboring.")
        return

    from apps.accounts.models import User as UserModel
    from apps.courses.models import StudentGroup

    def _get_teacher_groups(tg_id):
        teacher = UserModel.objects.filter(telegram_chat_id=tg_id, telegram_identity_verified_at__isnull=False, is_active=True).first()
        if not teacher:
            return []
        return list(StudentGroup.objects.filter(teacher=teacher).values("id", "name"))

    groups = await _run_db(_get_teacher_groups, user.id) if user else []
    if not groups:
        await _send_group_reply(
            update,
            context,
            "Sizga biriktirilgan guruhlar topilmadi.",
            parse_mode=ParseMode.HTML,
        )
        return

    buttons = [
        [InlineKeyboardButton(f"📄 {g['name']} vedomosti", callback_data=f"grp_cmd_vedomost_{g['id']}")]
        for g in groups
    ]
    await _send_group_reply(
        update,
        context,
        "📊 <b>Qaysi guruhning imtihon vedomostini olmoqchisiz?</b>",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode=ParseMode.HTML,
    )


cmd_vedomost = group_vedomost_command


# ---------------------------------------------------------------------------
# 8. Teacher Bot Workspace 5.0 (/ustoz)
# ---------------------------------------------------------------------------
def _build_teacher_workspace_keyboard() -> InlineKeyboardMarkup:
    site_url = getattr(settings, "SITE_URL", "https://grandec.uz").rstrip("/")
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👥 Guruhlarim", callback_data="tch_groups"),
            InlineKeyboardButton("📝 Test yaratish", callback_data="tch_create"),
        ],
        [
            InlineKeyboardButton("📤 Test yuborish", callback_data="tassign_quick"),
            InlineKeyboardButton("✅ Davomat", callback_data="tch_att"),
        ],
        [
            InlineKeyboardButton("📊 Natijalar", callback_data="tch_results"),
            InlineKeyboardButton("📈 Live monitoring", callback_data="tch_live"),
        ],
        [
            InlineKeyboardButton("🔔 Eslatmalar", callback_data="tch_reminders"),
            InlineKeyboardButton("⚙️ Sozlamalar", callback_data="tch_settings"),
        ],
        [
            InlineKeyboardButton("📱 Teacher Studio (Web)", web_app=WebAppInfo(url=f"{site_url}/teacher/studio")),
        ],
    ])


async def ustoz_menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ustoz shaxsiy chatda /ustoz deb yozganda Teacher Workspace 5.0 menyusini ochadi."""
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat:
        return
    if chat.type != "private" or chat.id != user.id:
        await _send_group_reply(update, context, "🔒 Ustoz menyusi faqat shaxsiy suhbatda mavjud.")
        return

    from apps.accounts.models import User as UserModel
    from apps.courses.models import StudentGroup

    def _get_teacher_overview(tg_id):
        teacher = UserModel.objects.filter(telegram_chat_id=tg_id, telegram_identity_verified_at__isnull=False, is_active=True).first()
        is_teacher_role = teacher and (
            getattr(teacher, "role", "") in ("teacher", "admin", "superadmin")
            or getattr(teacher, "is_superuser", False)
        )
        if not teacher or not is_teacher_role:
            return None, "Ustoz hisobi topilmadi"

        groups = list(StudentGroup.objects.filter(teacher=teacher).values("id", "name", "invite_code", "telegram_chat_id"))
        return {
            "name": teacher.get_full_name() or teacher.email,
            "groups_count": len(groups),
        }, None

    data, err = await _run_db(_get_teacher_overview, user.id)
    if err or not data:
        await _send_group_reply(
            update,
            context,
            "👨‍🏫 <b>Ustoz Kabineti:</b>\n"
            "Ushbu menyu faqat tasdiqlangan o'qituvchilar uchun mo'ljallangan.\n"
            "Agar siz o'qituvchi bo'lsangiz, avval saytda ro'yxatdan o'tib, Telegramingizni bog'lang.",
            parse_mode=ParseMode.HTML,
        )
        return

    text = (
        f"👨‍🏫 <b>Ustoz Kabineti 5.0 | {escape(data['name'])}</b>\n\n"
        f"👥 Biriktirilgan guruhlaringiz: <b>{data['groups_count']} ta</b>\n"
        "Quyidagi boshqaruv amallaridan birini tanlang:"
    )
    markup = _build_teacher_workspace_keyboard()

    target_msg = getattr(update, "message", None) or (update.callback_query.message if getattr(update, "callback_query", None) else None)
    if getattr(update, "callback_query", None):
        try:
            await update.callback_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
        except Exception:
            if target_msg:
                await target_msg.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
    else:
        if target_msg:
            await target_msg.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)


# ---------------------------------------------------------------------------
# 9. Admin Bot Workspace 5.0 (/admin)
# ---------------------------------------------------------------------------
def _build_admin_workspace_keyboard() -> InlineKeyboardMarkup:
    site_url = getattr(settings, "SITE_URL", "https://grandec.uz").rstrip("/")
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🏫 Markazlar", callback_data="adm_centers"),
            InlineKeyboardButton("👨‍🏫 Ustozlar", callback_data="adm_teachers"),
        ],
        [
            InlineKeyboardButton("👥 Guruhlar", callback_data="adm_groups"),
            InlineKeyboardButton("📝 Barcha testlar", callback_data="adm_tests"),
        ],
        [
            InlineKeyboardButton("📊 Hisobotlar", callback_data="adm_reports"),
            InlineKeyboardButton("🔔 Xabarnomalar", callback_data="adm_broadcast"),
        ],
        [
            InlineKeyboardButton("🛡️ Xavfsizlik", callback_data="adm_security"),
            InlineKeyboardButton("⚙️ Sozlamalar", callback_data="adm_settings"),
        ],
        [
            InlineKeyboardButton("🌐 Admin Panel (Web)", web_app=WebAppInfo(url=f"{site_url}/panel")),
        ],
    ])


async def admin_bot_menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Administrator shaxsiy chatda /admin deb yozganda Admin Workspace 5.0 ochiladi."""
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat:
        return
    if chat.type != "private" or chat.id != user.id:
        await _send_group_reply(update, context, "🔒 Admin boshqaruv menyusi faqat shaxsiy suhbatda mavjud.")
        return

    from apps.accounts.models import User as UserModel
    from apps.accounts.access import is_platform_admin

    def _get_admin_overview(tg_id):
        admin = UserModel.objects.filter(telegram_chat_id=tg_id, telegram_identity_verified_at__isnull=False, is_active=True).first()
        if not admin or not (is_platform_admin(admin) or getattr(admin, "role", "") in ("admin", "superadmin") or getattr(admin, "is_superuser", False)):
            return None, "Admin hisobi topilmadi"

        is_global = is_platform_admin(admin)
        role_label = "Platforma Super-Admini" if is_global else "O'quv Markazi Admini"
        return {
            "name": admin.get_full_name() or admin.email,
            "role_title": role_label,
            "is_global": is_global,
        }, None

    data, err = await _run_db(_get_admin_overview, user.id)
    if err or not data:
        await _send_group_reply(
            update,
            context,
            "⛔️ <b>Kirish taqiqlandi:</b> Ushbu buyruq faqat tasdiqlangan administratorlar uchun mo'ljallangan.",
            parse_mode=ParseMode.HTML,
        )
        return

    text = (
        f"🛡️ <b>Admin Boshqaruv Markazi 5.0 | {escape(data['name'])}</b>\n\n"
        f"Vakolatingiz: <b>{data['role_title']}</b>\n"
        "Platformani boshqarish uchun bo'limni tanlang:"
    )
    markup = _build_admin_workspace_keyboard()

    target_msg = getattr(update, "message", None) or (update.callback_query.message if getattr(update, "callback_query", None) else None)
    if getattr(update, "callback_query", None):
        try:
            await update.callback_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
        except Exception:
            if target_msg:
                await target_msg.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
    else:
        if target_msg:
            await target_msg.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)


# ---------------------------------------------------------------------------
# 10. Unified Dispatcher for Group & Workspace Callbacks
# ---------------------------------------------------------------------------
async def group_assistant_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Dispatches group menu, attendance, teacher, and admin callbacks."""
    query = update.callback_query
    if not query or not query.data:
        return

    data = query.data
    tg_user = update.effective_user

    # 1. Attendance callbacks
    if data.startswith("grp_att_here_"):
        await group_attendance_callback(update, context)
        return
    elif data.startswith("grp_att_rev_"):
        sid = int(data.split("_")[-1])
        info = await _run_db(_db_get_attendance_session_info, sid)
        if not info:
            await query.answer("Sessiya topilmadi.", show_alert=True)
            return
        text, markup = _format_attendance_review_message(info)
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
        await query.answer()
        return
    elif data.startswith("grp_att_fin_"):
        sid = int(data.split("_")[-1])
        res, err = await _run_db(_db_finalize_session, sid, tg_user.id if tg_user else 0)
        if err or not res:
            await query.answer(f"Xatolik: {err}", show_alert=True)
            return
        report_text = (
            f"📊 <b>{escape(res['group_name'])} — DAVOMAT YAKUNLANDI</b>\n"
            f"📅 Sana: <b>{escape(res['date_str'])}</b>\n\n"
            f"✅ <b>Darsda qatnashganlar:</b> {res['present_count']} nafar\n"
            f"❌ <b>Darsda qatnashmaganlar:</b> {res['absent_count']} nafar\n"
            f"👥 <b>Jami o'quvchilar:</b> {res['total_count']} nafar\n\n"
            "💾 <i>Davomat ma'lumotlari LMS kabinetingizga to'liq saqlandi!</i>"
        )
        await query.edit_message_text(report_text, parse_mode=ParseMode.HTML)
        await query.answer("Davomat yakunlandi va saqlandi! ✅")
        return
    elif data.startswith("grp_att_ref_"):
        sid = int(data.split("_")[-1])
        info = await _run_db(_db_get_attendance_session_info, sid)
        if not info:
            await query.answer("Sessiya topilmadi.", show_alert=True)
            return
        text, markup = _format_attendance_message(info)
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
        await query.answer("Yangilandi")
        return

    # 2. Group menu sub-views (grp_m_*)
    if data.startswith("grp_m_"):
        parts = data.split("_")
        action = parts[2]
        gid = int(parts[3])

        if action == "main":
            def _get_g(g_id):
                from apps.courses.models import StudentGroup
                g = StudentGroup.objects.filter(id=g_id).select_related("teacher").first()
                if not g:
                    return None
                return {
                    "id": g.id,
                    "name": g.name,
                    "code": g.invite_code,
                    "teacher": g.teacher.get_full_name() or g.teacher.email,
                    "students_count": g.students.filter(is_active=True).count(),
                }
            g_data = await _run_db(_get_g, gid)
            if g_data:
                text, markup = _render_group_menu(g_data)
                await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
            await query.answer()
            return

        elif action == "hw":
            def _get_hw(g_id):
                from apps.courses.models import Homework
                items = list(Homework.objects.filter(group_id=g_id, status="published").order_by("-due_date")[:5])
                return [
                    {
                        "title": h.title,
                        "due": timezone.localtime(h.due_date).strftime("%d.%m %H:%M") if h.due_date else "Muddatsiz",
                    }
                    for h in items
                ]
            hw_items = await _run_db(_get_hw, gid)
            lines = [f"📚 <b>Guruhning faol vazifalari:</b>\n"]
            if hw_items:
                for idx, h in enumerate(hw_items, 1):
                    lines.append(f"{idx}. 📝 <b>{escape(h['title'])}</b>\n   Muddat: {h['due']}")
            else:
                lines.append("<i>Hozircha faol vazifalar yo'q.</i>")
            site_url = getattr(settings, "SITE_URL", "https://grandec.uz").rstrip("/")
            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("📱 Mini Appda ishlash", web_app=WebAppInfo(url=f"{site_url}/tma/#/homework"))],
                [InlineKeyboardButton("🔙 Guruh boshqaruvi", callback_data=f"grp_m_main_{gid}")],
            ])
            await query.edit_message_text("\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=markup)
            await query.answer()
            return

        elif action == "tests":
            def _get_tests(g_id):
                from apps.courses.models import StudentGroup
                from apps.tests.models import Test
                group = StudentGroup.objects.filter(id=g_id).first()
                if not group:
                    return []
                tests = list(
                    Test.objects.filter(is_active=True, status="published", course__teacher_id=group.teacher_id)
                    .order_by("-id")[:5]
                )
                return [
                    {"id": t.id, "title": t.title, "questions": t.questions.count(), "pin": t.access_pin or ""}
                    for t in tests
                ]
            t_items = await _run_db(_get_tests, gid)
            lines = [f"📝 <b>Guruh uchun faol testlar:</b>\n"]
            if t_items:
                for idx, t in enumerate(t_items, 1):
                    pin_str = f" | PIN: <code>{t['pin']}</code>" if t["pin"] else ""
                    lines.append(f"{idx}. ✍️ <b>{escape(t['title'])}</b> ({t['questions']} ta savol{pin_str})")
            else:
                lines.append("<i>Hozircha faol testlar yo'q.</i>")
            site_url = getattr(settings, "SITE_URL", "https://grandec.uz").rstrip("/")
            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("📱 Mini Appda topshirish", web_app=WebAppInfo(url=f"{site_url}/tma/#/tests"))],
                [InlineKeyboardButton("🔙 Guruh boshqaruvi", callback_data=f"grp_m_main_{gid}")],
            ])
            await query.edit_message_text("\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=markup)
            await query.answer()
            return

        elif action == "sched":
            def _get_sched(g_id):
                from apps.courses.models import StudentGroup
                g = StudentGroup.objects.filter(id=g_id).select_related("teacher", "branch").first()
                if not g:
                    return None
                return {
                    "name": g.name,
                    "teacher": g.teacher.get_full_name() or g.teacher.email,
                    "branch": g.branch.name if g.branch else "Bosh Filial",
                    "subject": g.subject or "Umumiy",
                }
            s_data = await _run_db(_get_sched, gid)
            text = (
                f"📅 <b>Dars Jadvali va Ma'lumot:</b>\n\n"
                f"👥 Guruh: <b>{escape(s_data['name'] if s_data else '')}</b>\n"
                f"🏛 Filial: <b>{escape(s_data['branch'] if s_data else '')}</b>\n"
                f"📚 Fan: <b>{escape(s_data['subject'] if s_data else '')}</b>\n"
                f"👨‍🏫 Ustoz: <b>{escape(s_data['teacher'] if s_data else '')}</b>\n"
            )
            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Guruh boshqaruvi", callback_data=f"grp_m_main_{gid}")],
            ])
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
            await query.answer()
            return

        elif action == "att":
            def _get_group_chat(g_id):
                from apps.courses.models import StudentGroup
                g = StudentGroup.objects.filter(id=g_id).first()
                return g.telegram_chat_id if g else None

            c_id = await _run_db(_get_group_chat, gid)
            if c_id:
                data, err = await _run_db(_db_get_or_create_open_attendance, c_id, tg_user.id if tg_user else 0)
                if data and not err:
                    text, markup = _format_attendance_message(data)
                    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
                    await query.answer()
                    return
            await query.answer("Davomat faqat ustoz tomonidan ochilishi mumkin.", show_alert=True)
            return

        elif action == "prog":
            def _get_prog(g_id):
                from apps.courses.models import StudentGroup, Homework, HomeworkSubmission
                from apps.attendance.models import AttendanceSession, AttendanceRecord
                from django.db.models import Avg
                group = StudentGroup.objects.filter(id=g_id).first()
                if not group:
                    return None
                st_count = group.students.filter(is_active=True).count()
                hw_count = Homework.objects.filter(group_id=g_id).count()
                sub_count = HomeworkSubmission.objects.filter(homework__group_id=g_id).count()
                sub_rate = round((sub_count / max(1, hw_count * max(1, st_count))) * 100, 1)

                att_sessions = AttendanceSession.objects.filter(group_id=g_id, status=AttendanceSession.Status.FINALIZED)
                att_records = AttendanceRecord.objects.filter(session__in=att_sessions)
                total_att = att_records.count()
                present_att = att_records.filter(status=AttendanceRecord.Status.PRESENT).count()
                att_rate = round((present_att / max(1, total_att)) * 100, 1) if total_att > 0 else 100.0

                return {
                    "group_name": group.name,
                    "students_count": st_count,
                    "hw_count": hw_count,
                    "sub_rate": min(100.0, sub_rate),
                    "att_rate": min(100.0, att_rate),
                }

            prog = await _run_db(_get_prog, gid)
            text = (
                f"📊 <b>Guruh Umumiy Progressi:</b>\n\n"
                f"👥 Guruh: <b>{escape(prog['group_name'] if prog else '')}</b>\n"
                f"🎓 O'quvchilar: <b>{prog['students_count'] if prog else 0} nafar</b>\n"
                f"📚 Berilgan vazifalar: <b>{prog['hw_count'] if prog else 0} ta</b>\n"
                f"📈 Vazifa topshirish ko'rsatkichi: <b>{prog['sub_rate'] if prog else 0}%</b>\n"
                f"✅ O'rtacha davomat: <b>{prog['att_rate'] if prog else 100}%</b>\n\n"
                "<i>Individual shaxsiy baholar maxfiylik yuzasidan bu yerda ko'rsatilmaydi.</i>"
            )
            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Guruh boshqaruvi", callback_data=f"grp_m_main_{gid}")],
            ])
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
            await query.answer()
            return

        elif action == "rank":
            def _get_anon_rank(g_id):
                from apps.courses.models import StudentGroup
                from apps.results.models import Result
                from django.db.models import Q
                group = StudentGroup.objects.filter(id=g_id).first()
                if not group:
                    return []
                st_ids = list(group.students.filter(is_active=True).values_list("id", flat=True))
                results = (
                    Result.objects.filter(student_id__in=st_ids)
                    .filter(Q(test__assigned_group=group) | Q(test__homework_assignments__group=group))
                    .distinct()
                    .order_by("-percentage")[:5]
                )
                return [{"code": f"O'quvchi #{r.student_id}", "pct": float(r.percentage)} for r in results]

            board = await _run_db(_get_anon_rank, gid)
            lines = ["🏆 <b>Ixtiyoriy Anonim Reyting (Top-5):</b>\n"]
            if board:
                medals = ["🥇", "🥈", "🥉", "4.", "5."]
                for i, b in enumerate(board):
                    lines.append(f"{medals[i]} {b['code']} — <b>{b['pct']}%</b>")
            else:
                lines.append("<i>Hozircha natijalar mavjud emas.</i>")
            lines.append("\n<i>To'liq shaxsiy natijalarni ustoz o'z kabinetida ko'radi.</i>")
            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Guruh boshqaruvi", callback_data=f"grp_m_main_{gid}")],
            ])
            await query.edit_message_text("\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=markup)
            await query.answer()
            return

        elif action == "tch":
            def _get_tch_info(g_id):
                from apps.courses.models import StudentGroup
                g = StudentGroup.objects.filter(id=g_id).select_related("teacher").first()
                if not g:
                    return None
                return {
                    "name": g.teacher.get_full_name() or g.teacher.email,
                    "username": g.teacher.telegram_username or "",
                    "subject": g.subject or "Fan",
                }
            t_info = await _run_db(_get_tch_info, gid)
            text = (
                f"👨‍🏫 <b>Guruh Ustozi:</b>\n\n"
                f"Ism: <b>{escape(t_info['name'] if t_info else '')}</b>\n"
                f"Fan: <b>{escape(t_info['subject'] if t_info else '')}</b>\n"
            )
            if t_info and t_info["username"]:
                text += f"Telegram: @{escape(t_info['username'])}\n"
            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Guruh boshqaruvi", callback_data=f"grp_m_main_{gid}")],
            ])
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
            await query.answer()
            return

    # 3. Teacher Workspace callbacks (tch_*)
    if data.startswith("tch_"):
        if data == "tch_main":
            await ustoz_menu_command(update, context)
            await query.answer()
            return
        elif data == "tch_groups":
            def _get_groups_list(tg_id):
                from apps.accounts.models import User
                from apps.courses.models import StudentGroup
                teacher = User.objects.filter(telegram_chat_id=tg_id, is_active=True).first()
                if not teacher:
                    return []
                return list(StudentGroup.objects.filter(teacher=teacher).values("id", "name", "invite_code", "telegram_chat_id"))
            groups = await _run_db(_get_groups_list, tg_user.id if tg_user else 0)
            lines = ["👥 <b>Sizning Guruhlaringiz:</b>\n"]
            btn_rows = []
            for g in groups:
                status_icon = "🟢" if g["telegram_chat_id"] else "⚪️"
                lines.append(f"• <b>{escape(g['name'])}</b> (Kodi: <code>{g['invite_code']}</code>) {status_icon}")
                btn_rows.append([
                    InlineKeyboardButton(f"📋 {g['name']} vedomosti", callback_data=f"grp_cmd_vedomost_{g['id']}"),
                ])
            btn_rows.append([InlineKeyboardButton("🔙 Ustoz Menyusi", callback_data="tch_main")])
            await query.edit_message_text("\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(btn_rows))
            await query.answer()
            return
        elif data == "tch_create":
            site_url = getattr(settings, "SITE_URL", "https://grandec.uz").rstrip("/")
            text = (
                "📝 <b>Test Yaratish:</b>\n\n"
                "Tezkor savollar tuzish yoki Smart Import (DOCX, XLSX, PDF, Matn) orqali "
                "keng qamrovli test yaratish uchun Teacher Studio dan foydalaning:"
            )
            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("📱 Teacher Studio (Mini App)", web_app=WebAppInfo(url=f"{site_url}/tma/#/teacher/studio"))],
                [InlineKeyboardButton("🌐 Veb-saytda ochish", url=f"{site_url}/teacher/studio")],
                [InlineKeyboardButton("🔙 Ustoz Menyusi", callback_data="tch_main")],
            ])
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
            await query.answer()
            return
        elif data == "tch_att":
            def _get_teacher_groups_att(tg_id):
                from apps.accounts.models import User
                from apps.courses.models import StudentGroup
                teacher = User.objects.filter(telegram_chat_id=tg_id, is_active=True).first()
                if not teacher:
                    return []
                return list(StudentGroup.objects.filter(teacher=teacher).values("id", "name"))
            groups = await _run_db(_get_teacher_groups_att, tg_user.id if tg_user else 0)
            lines = ["✅ <b>Davomat olish uchun guruhni tanlang:</b>\n"]
            btn_rows = [
                [InlineKeyboardButton(f"👥 {g['name']}", callback_data=f"grp_m_att_{g['id']}")]
                for g in groups
            ]
            btn_rows.append([InlineKeyboardButton("🔙 Ustoz Menyusi", callback_data="tch_main")])
            await query.edit_message_text("\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(btn_rows))
            await query.answer()
            return
        elif data == "tch_results":
            def _get_recent_attempts(tg_id):
                from apps.accounts.models import User
                from apps.tests.models import TestAttempt
                teacher = User.objects.filter(telegram_chat_id=tg_id, is_active=True).first()
                if not teacher:
                    return []
                attempts = list(
                    TestAttempt.objects.filter(test__course__teacher=teacher, status__in=[TestAttempt.Status.COMPLETED, TestAttempt.Status.TIMEOUT])
                    .select_related("student", "test")
                    .order_by("-completed_at")[:6]
                )
                return [
                    {
                        "student": a.student.get_full_name() or a.student.email,
                        "test": a.test.title[:22],
                        "score": float(a.score),
                        "pct": float(a.percentage),
                        "passed": a.is_passed,
                    }
                    for a in attempts
                ]
            atts = await _run_db(_get_recent_attempts, tg_user.id if tg_user else 0)
            lines = ["📊 <b>So'nggi topshirilgan natijalar:</b>\n"]
            if atts:
                for a in atts:
                    chk = "✅" if a["passed"] else "⚠️"
                    lines.append(f"• <b>{escape(a['student'])}</b>: {escape(a['test'])}\n   Ball: {a['score']} ({a['pct']}%) {chk}")
            else:
                lines.append("<i>Hozircha natijalar yo'q.</i>")
            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Ustoz Menyusi", callback_data="tch_main")],
            ])
            await query.edit_message_text("\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=markup)
            await query.answer()
            return
        elif data == "tch_live":
            def _get_live(tg_id):
                from apps.accounts.models import User
                from apps.tests.models import TestAttempt
                from apps.courses.models import Homework
                teacher = User.objects.filter(telegram_chat_id=tg_id, is_active=True).first()
                if not teacher:
                    return None
                in_progress_count = TestAttempt.objects.filter(test__course__teacher=teacher, status=TestAttempt.Status.IN_PROGRESS).count()
                active_hw_count = Homework.objects.filter(course__teacher=teacher, status="published").count()
                return {"in_prog": in_progress_count, "active_hw": active_hw_count}
            live_data = await _run_db(_get_live, tg_user.id if tg_user else 0)
            text = (
                "📈 <b>Jonli Monitoring:</b>\n\n"
                f"✍️ Ayni damda test ishlayotganlar: <b>{live_data['in_prog'] if live_data else 0} nafar</b>\n"
                f"📚 Faol topshiriqlar: <b>{live_data['active_hw'] if live_data else 0} ta</b>\n"
            )
            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Ustoz Menyusi", callback_data="tch_main")],
            ])
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
            await query.answer()
            return
        elif data == "tch_reminders":
            site_url = getattr(settings, "SITE_URL", "https://grandec.uz").rstrip("/")
            text = (
                "🔔 <b>Eslatmalar va Bildirishnomalar:</b>\n\n"
                "O'quvchilarga muddati yaqinlashgan vazifalar va imtihonlar haqida avtomatik "
                "eslatma yuborish tizimi faol."
            )
            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Ustoz Menyusi", callback_data="tch_main")],
            ])
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
            await query.answer()
            return
        elif data == "tch_settings":
            text = (
                "⚙️ <b>Ustoz Sozlamalari:</b>\n\n"
                "Profil ma'lumotlari, filial va fan yo'nalishlarini veb-platforma orqali tahrirlashingiz mumkin."
            )
            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Ustoz Menyusi", callback_data="tch_main")],
            ])
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
            await query.answer()
            return

    # 4. Admin Workspace callbacks (adm_*)
    if data.startswith("adm_"):
        if data == "adm_main":
            await admin_bot_menu_command(update, context)
            await query.answer()
            return
        elif data == "adm_centers":
            def _get_centers(tg_id):
                from apps.accounts.models import User
                from apps.accounts.access import is_platform_admin
                from apps.organizations.models import LearningCenter
                user = User.objects.filter(telegram_chat_id=tg_id, is_active=True).first()
                if not user:
                    return []
                if is_platform_admin(user):
                    return list(LearningCenter.objects.values("id", "name", "slug")[:10])
                if getattr(user, "learning_center_id", None):
                    return list(LearningCenter.objects.filter(id=user.learning_center_id).values("id", "name", "slug"))
                return []
            centers = await _run_db(_get_centers, tg_user.id if tg_user else 0)
            lines = ["🏫 <b>O'quv Markazlari:</b>\n"]
            for c in centers:
                lines.append(f"• <b>{escape(c['name'])}</b> (Slug: <code>{c['slug']}</code>)")
            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Admin Menyusi", callback_data="adm_main")],
            ])
            await query.edit_message_text("\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=markup)
            await query.answer()
            return
        elif data == "adm_teachers":
            def _get_teachers_count(tg_id):
                from apps.accounts.models import User
                from apps.accounts.access import is_platform_admin
                user = User.objects.filter(telegram_chat_id=tg_id, is_active=True).first()
                if not user:
                    return 0
                if is_platform_admin(user):
                    return User.objects.filter(role="teacher", is_active=True).count()
                return User.objects.filter(role="teacher", is_active=True, learning_center_id=user.learning_center_id).count()
            t_cnt = await _run_db(_get_teachers_count, tg_user.id if tg_user else 0)
            text = f"👨‍🏫 <b>O'qituvchilar soni:</b> {t_cnt} nafar"
            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Admin Menyusi", callback_data="adm_main")],
            ])
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
            await query.answer()
            return
        elif data == "adm_groups":
            def _get_groups_count(tg_id):
                from apps.accounts.models import User
                from apps.accounts.access import is_platform_admin
                from apps.courses.models import StudentGroup
                user = User.objects.filter(telegram_chat_id=tg_id, is_active=True).first()
                if not user:
                    return 0
                if is_platform_admin(user):
                    return StudentGroup.objects.count()
                return StudentGroup.objects.filter(branch__center_id=user.learning_center_id).count()
            g_cnt = await _run_db(_get_groups_count, tg_user.id if tg_user else 0)
            text = f"👥 <b>Guruhlar soni:</b> {g_cnt} ta"
            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Admin Menyusi", callback_data="adm_main")],
            ])
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
            await query.answer()
            return
        elif data == "adm_tests":
            def _get_test_stats(tg_id):
                from apps.accounts.models import User
                from apps.tests.admin_test_service import get_scoped_tests_queryset, calculate_test_stats
                user = User.objects.filter(telegram_chat_id=tg_id, is_active=True).first()
                if not user:
                    return None
                qs = get_scoped_tests_queryset(user)
                return calculate_test_stats(qs)
            stats = await _run_db(_get_test_stats, tg_user.id if tg_user else 0)
            text = (
                "📝 <b>Testlar Statistikasi:</b>\n\n"
                f"Jami testlar: <b>{stats['total_tests'] if stats else 0} ta</b>\n"
                f"Nashr etilgan: <b>{stats['published_tests'] if stats else 0} ta</b>\n"
                f"Qoralama: <b>{stats['draft_tests'] if stats else 0} ta</b>\n"
                f"Arxivlangan: <b>{stats['archived_tests'] if stats else 0} ta</b>\n"
                f"Urinishlar mavjud: <b>{stats['attempted_tests'] if stats else 0} ta</b>\n"
            )
            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Admin Menyusi", callback_data="adm_main")],
            ])
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
            await query.answer()
            return
        elif data in ("adm_reports", "adm_broadcast", "adm_security", "adm_settings"):
            text = f"🛡️ <b>Admin Bo'limi ({data.replace('adm_', '').title()}):</b>\n\nUshbu bo'lim to'liq veb-boshqaruv panelida mavjud."
            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Admin Menyusi", callback_data="adm_main")],
            ])
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
            await query.answer()
            return

    # 5. Legacy / Vedomost PDF callbacks
    if data.startswith("grp_cmd_vedomost_"):
        chat, user = update.effective_chat, update.effective_user
        if not chat or chat.type != "private" or not user or chat.id != user.id:
            await query.answer("⛔️ Bu amal faqat tasdiqlangan ustozning shaxsiy chatida mavjud.", show_alert=True)
            return
        gid = int(data.split("_")[-1])
        await query.answer("Vedomost tayyorlanmoqda...")
        from apps.results.pdf_generator import generate_group_vedomost_pdf
        from apps.courses.models import StudentGroup

        def _build_pdf(g_id):
            grp = StudentGroup.objects.get(id=g_id)
            path = generate_group_vedomost_pdf(g_id)
            return grp.name, path

        pdf_path = None
        try:
            grp_name, pdf_path = await _run_db(_build_pdf, gid)
            with open(pdf_path, "rb") as f:
                await context.bot.send_document(
                    chat_id=user.id,
                    document=f,
                    filename=os.path.basename(pdf_path),
                    caption=f"📄 <b>{grp_name} Guruhi Imtihon Vedomosti (PDF)</b>",
                    parse_mode=ParseMode.HTML,
                )
        except Exception as exc:
            logger.exception("Failed to generate/send vedomost PDF: %s", exc)
            await query.message.reply_text("❌ Vedomost faylini yaratishda xatolik yuz berdi.")
        finally:
            if pdf_path and os.path.exists(pdf_path):
                try:
                    os.unlink(pdf_path)
                except Exception:
                    pass
        return

    await query.answer()


# ---------------------------------------------------------------------------
# 11. Unified Command Routers (Group vs Private) & Handler Registration
# ---------------------------------------------------------------------------
async def unified_davomat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Routes /davomat to group live attendance in groups, or CRM menu in private chat."""
    chat = update.effective_chat
    if chat and chat.type in (ChatType.GROUP, ChatType.SUPERGROUP, "group", "supergroup"):
        await group_davomat_command(update, context)
    else:
        from apps.bot.crm import davomat_handler
        await davomat_handler(update, context)


async def unified_leaderboard_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Routes /leaderboard and /reyting to group test results in groups, or platform leaderboard in private chat."""
    chat = update.effective_chat
    if chat and chat.type in (ChatType.GROUP, ChatType.SUPERGROUP, "group", "supergroup"):
        await group_results_leaderboard_command(update, context)
    else:
        from apps.notifications.bot.handlers import leaderboard_handler
        await leaderboard_handler(update, context)


async def unified_test_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Routes /test to group announcement with PIN in groups, or personal tests catalog in private chat."""
    chat = update.effective_chat
    if chat and chat.type in (ChatType.GROUP, ChatType.SUPERGROUP, "group", "supergroup"):
        await group_yangi_test_command(update, context)
    else:
        from apps.notifications.bot.handlers import tests_handler
        await tests_handler(update, context)


def setup_group_handlers(app) -> None:
    """Register all group assistant commands and handlers on the PTB Application."""
    from telegram.ext import (
        CallbackQueryHandler,
        ChatMemberHandler,
        CommandHandler,
        MessageHandler,
        filters,
    )

    app.add_handler(ChatMemberHandler(on_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, on_new_chat_members))
    app.add_handler(CommandHandler(["menu", "guruh", "boshqaruv"], group_menu_command))
    app.add_handler(CommandHandler(["ulash", "link", "link_group"], cmd_link_group))
    app.add_handler(CommandHandler(["uzish", "unlink_group"], cmd_unlink_group))
    app.add_handler(CommandHandler(["reyting", "leaderboard"], unified_leaderboard_handler))
    app.add_handler(CommandHandler(["vedomost", "report"], group_vedomost_command))
    app.add_handler(CommandHandler("davomat", unified_davomat_handler))
    app.add_handler(CommandHandler("davomat_yakun", group_davomat_yakun_command))
    app.add_handler(CommandHandler("yangi_test", group_yangi_test_command))
    app.add_handler(CommandHandler("ustoz", ustoz_menu_command))
    app.add_handler(CommandHandler("admin", admin_bot_menu_command))
    app.add_handler(
        CallbackQueryHandler(group_assistant_callback_handler, pattern=r"^(grp_att_|grp_cmd_|grp_m_|ustoz_|tch_|adm_)")
    )
