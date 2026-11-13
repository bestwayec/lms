from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from asgiref.sync import async_to_sync

from apps.notifications.bot.handlers import cancel_handler


def test_cancel_clears_pending_inputs_and_restores_teacher_menu():
    user = SimpleNamespace(role="teacher")
    update = SimpleNamespace(effective_user=SimpleNamespace(id=123))
    context = SimpleNamespace(user_data={
        "awaiting_mock_code": True, "awaiting_create_group": True,
        "awaiting_parent_code": True, "awaiting_teacher_contact": True,
        "payment_state": "awaiting_screenshot", "selected_plan_slug": "pro",
        "selected_plan_id": 1, "unrelated_preference": "uz",
    })
    with patch("apps.notifications.bot.handlers._get_or_create_user_async", new=AsyncMock(return_value=user)), \
         patch("apps.notifications.bot.handlers._get_user_role", return_value="teacher"), \
         patch("apps.notifications.bot.handlers.send_reply", new=AsyncMock()) as reply:
        async_to_sync(cancel_handler)(update, context)
    assert context.user_data == {"unrelated_preference": "uz"}
    text = reply.await_args.args[1]
    assert "test kodi" in text and "guruh yaratish" in text
    keyboard = reply.await_args.kwargs["reply_markup"]
    assert any(button.callback_data == "tgrplist" for row in keyboard.inline_keyboard for button in row)
