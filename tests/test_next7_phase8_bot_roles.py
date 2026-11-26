"""Regression tests for NEXT 7.0 Phase 08 Telegram Bot role menus, routing & RBAC."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from asgiref.sync import async_to_sync
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.notifications.bot.group_assistant import group_assistant_callback_handler
from apps.notifications.bot.handlers import (
    _admin_main_menu_keyboard,
    _teacher_main_menu_keyboard,
    callback_handler,
    setup_handlers,
)


class _DummyApplication:
    def __init__(self):
        self.handlers = []
        self.error_handlers = []

    def add_error_handler(self, fn):
        self.error_handlers.append(fn)

    def add_handler(self, handler, group=0):
        self.handlers.append((group, handler))


def _make_callback_update(tg_id: int, data: str):
    message = SimpleNamespace(
        text="",
        reply_text=AsyncMock(),
        chat=SimpleNamespace(id=tg_id, type="private"),
        message_id=501,
    )
    query = SimpleNamespace(
        id=f"cb-{tg_id}-{data}",
        data=data,
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
        message=message,
    )
    update = SimpleNamespace(
        update_id=9001,
        effective_user=SimpleNamespace(id=tg_id, first_name="Test", last_name="User", username="testuser"),
        effective_chat=SimpleNamespace(id=tg_id, type="private"),
        message=None,
        callback_query=query,
    )
    return update, query, message


class Next7Phase8BotRolesTests(TestCase):
    def setUp(self):
        self.context = SimpleNamespace(user_data={}, bot=SimpleNamespace(username="uz_essaygrader_bot"))
        self.student = User.objects.create_user(
            email="bot-student-p8@example.test",
            password="StrongPassword123!",
            first_name="Student",
            role=User.Role.STUDENT,
            telegram_chat_id=11002200,
            telegram_identity_verified_at=timezone.now(),
        )
        self.teacher = User.objects.create_user(
            email="bot-teacher-p8@example.test",
            password="StrongPassword123!",
            first_name="Teacher",
            role=User.Role.TEACHER,
            telegram_chat_id=22003300,
            telegram_identity_verified_at=timezone.now(),
        )
        self.admin = User.objects.create_superuser(
            email="bot-admin-p8@example.test",
            password="StrongPassword123!",
            telegram_chat_id=33004400,
            telegram_identity_verified_at=timezone.now(),
        )

    def test_role_keyboards_use_direct_workspace_links(self):
        teacher_kb = _teacher_main_menu_keyboard()
        teacher_urls = [btn.url for row in teacher_kb.inline_keyboard for btn in row if getattr(btn, "url", None)]
        self.assertTrue(any(url.endswith("/dashboard") for url in teacher_urls))
        self.assertFalse(any(url.endswith("/login") for url in teacher_urls))

        admin_kb = _admin_main_menu_keyboard()
        admin_callbacks = {
            btn.callback_data for row in admin_kb.inline_keyboard for btn in row if getattr(btn, "callback_data", None)
        }
        admin_urls = [btn.url for row in admin_kb.inline_keyboard for btn in row if getattr(btn, "url", None)]
        self.assertTrue({"adm_stats", "adm_pending_receipts", "adm_centers", "adm_groups", "adm_tests", "adm_settings"}.issubset(admin_callbacks))
        self.assertTrue(any(url.endswith("/panel") for url in admin_urls))

    def test_group_assistant_regex_does_not_swallow_core_admin_callbacks(self):
        from telegram.ext import CallbackQueryHandler

        app = _DummyApplication()
        setup_handlers(app)
        group_cb_handlers = [
            h
            for grp, h in app.handlers
            if grp == 0 and isinstance(h, CallbackQueryHandler) and h.callback is group_assistant_callback_handler
        ]
        self.assertEqual(len(group_cb_handlers), 1)
        pattern = group_cb_handlers[0].pattern

        # Must match Workspace 5.0 subset
        for data in ("adm_main", "adm_centers", "adm_teachers", "adm_groups", "adm_tests", "tch_groups"):
            self.assertIsNotNone(pattern.match(data), f"Expected pattern to match {data}")

        # Must NOT match core admin callbacks handled by callback_handler
        for data in (
            "adm_stats",
            "adm_pending_receipts",
            "adm_pending_teachers",
            "adm_settings",
            "adm_switch_student",
            "adm_switch_teacher",
            "adm_rec_appr_12",
            "adm_rec_rej_12",
            "adm_appr_tchr_99",
            "adm_rej_tchr_99",
        ):
            self.assertIsNone(pattern.match(data), f"group_assistant must NOT swallow {data}")

    def test_admin_workspace_callbacks_enforce_admin_rbac(self):
        # Student cannot invoke adm_tests / adm_reports / adm_centers via group_assistant_callback_handler
        for cb in ("adm_centers", "adm_groups", "adm_tests", "adm_reports"):
            update, query, _ = _make_callback_update(self.student.telegram_chat_id, cb)
            async_to_sync(group_assistant_callback_handler)(update, self.context)
            query.answer.assert_awaited()
            call_kwargs = query.answer.await_args
            self.assertTrue(call_kwargs.kwargs.get("show_alert"))
            self.assertIn("administrator", call_kwargs.args[0].lower())
            query.edit_message_text.assert_not_awaited()

        # Student cannot invoke tch_groups via group_assistant_callback_handler
        update, query, _ = _make_callback_update(self.student.telegram_chat_id, "tch_groups")
        async_to_sync(group_assistant_callback_handler)(update, self.context)
        self.assertTrue(query.answer.await_args.kwargs.get("show_alert"))
        query.edit_message_text.assert_not_awaited()

    def test_verified_admin_stats_and_centers_callbacks_succeed(self):
        update, query, msg = _make_callback_update(self.admin.telegram_chat_id, "adm_stats")
        async_to_sync(callback_handler)(update, self.context)
        self.assertTrue(query.edit_message_text.called or msg.reply_text.called)

        update2, query2, _ = _make_callback_update(self.admin.telegram_chat_id, "adm_centers")
        async_to_sync(group_assistant_callback_handler)(update2, self.context)
        query2.edit_message_text.assert_awaited()
        self.assertIn("Markazlari", query2.edit_message_text.await_args.args[0])
