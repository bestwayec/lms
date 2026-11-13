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


def test_student_menu_and_extra_navigation():
    from apps.notifications.bot.handlers import _student_main_menu_keyboard, callback_handler

    main = _student_main_menu_keyboard()
    actions = {b.callback_data for row in main.inline_keyboard for b in row}
    assert {"menu_tests", "menu_quiz", "menu_essays", "menu_results", "menu_student_more"} <= actions
    query = SimpleNamespace(data="menu_student_more", answer=AsyncMock(), edit_message_text=AsyncMock())
    update = SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=123))
    context = SimpleNamespace(user_data={})
    with patch("apps.notifications.bot.handlers._get_or_create_user_async", new=AsyncMock(return_value=None)):
        async_to_sync(callback_handler)(update, context)
    keyboard = query.edit_message_text.await_args.kwargs["reply_markup"]
    more_actions = {b.callback_data for row in keyboard.inline_keyboard for b in row}
    assert {"menu_certs", "menu_arena", "menu_main"} <= more_actions


def test_home_leaves_mock_code_entry():
    from apps.notifications.bot.handlers import callback_handler

    query = SimpleNamespace(data="menu_main", answer=AsyncMock(), edit_message_text=AsyncMock())
    update = SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=123))
    context = SimpleNamespace(user_data={"awaiting_mock_code": True, "preference": "uz"})
    with patch("apps.notifications.bot.handlers._get_or_create_user_async", new=AsyncMock(return_value=None)), \
         patch("apps.notifications.bot.handlers._get_user_role", return_value="student"):
        async_to_sync(callback_handler)(update, context)
    assert context.user_data == {"preference": "uz"}
    query.edit_message_text.assert_awaited_once()
