"""Regression tests for Telegram identity and group authorization."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.accounts.services.telegram_identity import get_or_create_telegram_user
from apps.courses.models import StudentGroup
from apps.notifications.bot.group_assistant import bind_telegram_group_by_code
from apps.notifications.bot.handlers import _authenticate_or_provision_tg_user, _get_user_role
from apps.notifications.models import TelegramAuthToken

User = get_user_model()


@pytest.mark.django_db
def test_sso_never_claims_a_matching_username_or_reactivates_accounts():
    victim = User.objects.create_user(email="victim@example.test", password="test", telegram_username="sharedname")
    token = TelegramAuthToken.objects.create(token="safe-sso-regression")
    user, created = _authenticate_or_provision_tg_user(token.token, {"id": 1928374, "username": "sharedname"})
    victim.refresh_from_db()
    assert created and user.pk != victim.pk
    assert victim.telegram_chat_id is None
    assert user.telegram_chat_id == 1928374
    token.refresh_from_db()
    assert token.user_id == user.id
    again, _ = _authenticate_or_provision_tg_user(token.token, {"id": 1928374})
    assert again is None


@pytest.mark.django_db
def test_sso_refuses_inactive_or_unverified_existing_numeric_link():
    user = User.objects.create_user(email="legacy@example.test", password="test", telegram_chat_id=3333)
    token = TelegramAuthToken.objects.create(token="legacy-sso-regression")
    assert _authenticate_or_provision_tg_user(token.token, {"id": 3333}) == (None, False)
    user.telegram_identity_verified_at = timezone.now()
    user.is_active = False
    user.save()
    assert _authenticate_or_provision_tg_user(token.token, {"id": 3333}) == (None, False)
    user.refresh_from_db()
    assert not user.is_active
    token.refresh_from_db()
    assert not token.is_verified


@pytest.mark.django_db
def test_old_hardcoded_telegram_id_cannot_grant_privilege():
    user, _ = get_or_create_telegram_user({"id": 5582178765})
    assert user.role == "student" and not user.is_superuser and not user.is_staff
    assert _get_user_role(user, 5582178765) == "student"


@pytest.mark.django_db(transaction=True)
def test_group_binding_requires_verified_owner_and_telegram_admin_and_no_replacement():
    owner = User.objects.create_user(email="owner@example.test", password="test", role="teacher", telegram_chat_id=1111, telegram_identity_verified_at=timezone.now())
    other = User.objects.create_user(email="other@example.test", password="test", role="teacher", telegram_chat_id=2222, telegram_identity_verified_at=timezone.now())
    group = StudentGroup.objects.create(name="Private class", teacher=owner)
    reply = AsyncMock()
    update = SimpleNamespace(effective_chat=SimpleNamespace(id=-1001, type="supergroup", title="Class"), effective_user=SimpleNamespace(id=other.telegram_chat_id, username="owner"), message=SimpleNamespace(reply_text=reply))
    context = SimpleNamespace(bot=SimpleNamespace(get_chat_member=AsyncMock(return_value=SimpleNamespace(status="administrator"))))
    bind = lambda: async_to_sync(bind_telegram_group_by_code)(update, context, group.invite_code)
    assert not bind()
    update.effective_user.id = 9999
    assert not bind()
    update.effective_user.id = owner.telegram_chat_id
    context.bot.get_chat_member.return_value.status = "member"
    assert not bind()
    context.bot.get_chat_member.return_value.status = "administrator"
    assert bind()
    assert bind()  # retry of the same update is idempotent
    update.effective_chat.id = -1002
    assert not bind()
    group.refresh_from_db()
    assert group.telegram_chat_id == -1001


@pytest.mark.django_db(transaction=True)
def test_private_report_callback_rechecks_group_ownership_and_chat():
    from apps.notifications.bot.group_assistant import group_assistant_callback_handler
    owner = User.objects.create_user(email="report-owner@example.test", password="test", role="teacher", telegram_chat_id=4451, telegram_identity_verified_at=timezone.now())
    attacker = User.objects.create_user(email="report-other@example.test", password="test", role="teacher", telegram_chat_id=4452, telegram_identity_verified_at=timezone.now())
    group = StudentGroup.objects.create(name="Owner group", teacher=owner)
    query = SimpleNamespace(data=f"grp_cmd_vedomost_{group.id}", answer=AsyncMock(), message=SimpleNamespace(chat_id=4452))
    update = SimpleNamespace(callback_query=query, effective_chat=SimpleNamespace(id=4452, type="private"), effective_user=SimpleNamespace(id=attacker.telegram_chat_id))
    context = SimpleNamespace(bot=SimpleNamespace(send_document=AsyncMock()))
    async_to_sync(group_assistant_callback_handler)(update, context)
    assert query.answer.await_args.kwargs["show_alert"] is True
    context.bot.send_document.assert_not_awaited()
    update.effective_user.id = owner.telegram_chat_id
    update.effective_chat.type = "supergroup"
    async_to_sync(group_assistant_callback_handler)(update, context)
    assert query.answer.await_args.kwargs["show_alert"] is True
    context.bot.send_document.assert_not_awaited()


@pytest.mark.django_db(transaction=True)
def test_crm_callbacks_block_other_groups_and_unsafe_receipt_approval():
    from apps.bot.crm import handle_crm_callback
    owner = User.objects.create_user(email="crm-owner@example.test", password="test", role="teacher", telegram_chat_id=5511, telegram_identity_verified_at=timezone.now())
    attacker = User.objects.create_user(email="crm-other@example.test", password="test", role="teacher", telegram_chat_id=5522, telegram_identity_verified_at=timezone.now())
    group = StudentGroup.objects.create(name="Private CRM", teacher=owner)
    query = SimpleNamespace(answer=AsyncMock(), edit_message_text=AsyncMock())
    update = SimpleNamespace(callback_query=query, effective_chat=SimpleNamespace(id=5522, type="private"), effective_user=SimpleNamespace(id=attacker.telegram_chat_id))
    context = SimpleNamespace(user_data={})
    async_to_sync(handle_crm_callback)(update, context, f"dav_grp_{group.id}")
    assert query.answer.await_args.kwargs["show_alert"] is True
    query.edit_message_text.assert_not_awaited()
    update.effective_user.id = owner.telegram_chat_id
    async_to_sync(handle_crm_callback)(update, context, "rcpt_appr_1_100000")
    assert query.answer.await_args.kwargs["show_alert"] is True
    assert "LMS" in query.answer.await_args.args[0]
    query.edit_message_text.assert_not_awaited()


@pytest.mark.django_db(transaction=True)
def test_concurrent_group_bindings_do_not_share_chat():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from django.db import close_old_connections, connection
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL advisory locking test")
    teachers = [User.objects.create_user(email=f"concurrent-{i}@example.test", password="test", role="teacher", telegram_chat_id=6610 + i, telegram_identity_verified_at=timezone.now()) for i in range(2)]
    groups = [StudentGroup.objects.create(name=f"Class {i}", teacher=teachers[i]) for i in range(2)]
    barrier = Barrier(2)
    def attempt(i):
        close_old_connections()
        update = SimpleNamespace(effective_chat=SimpleNamespace(id=-2000, type="supergroup", title="Class"), effective_user=SimpleNamespace(id=teachers[i].telegram_chat_id), message=SimpleNamespace(reply_text=AsyncMock()))
        context = SimpleNamespace(bot=SimpleNamespace(get_chat_member=AsyncMock(return_value=SimpleNamespace(status="administrator"))))
        barrier.wait(timeout=20)
        result = async_to_sync(bind_telegram_group_by_code)(update, context, groups[i].invite_code)
        close_old_connections()
        return result
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(attempt, range(2)))
    assert sorted(results) == [False, True]
    assert StudentGroup.objects.filter(telegram_chat_id=-2000, pk__in=[g.pk for g in groups]).count() == 1


@pytest.mark.django_db
def test_receipt_alert_has_no_hardcoded_recipient(settings, monkeypatch):
    from apps.payments.services import notify_admin_new_receipt
    settings.ADMIN_TELEGRAM_ID = 0
    settings.TELEGRAM_BOT_TOKEN = "local-test-token"
    owner = User.objects.create_user(email="receipt@example.test", password="test")
    receipt = SimpleNamespace(user=owner, plan="pro", created_at=timezone.now(), amount=100, id=1, receipt_image=None)
    from unittest.mock import Mock
    send = Mock()
    monkeypatch.setattr("apps.payments.services.requests.post", send)
    notify_admin_new_receipt(receipt)
    send.assert_not_called()
    settings.ADMIN_TELEGRAM_ID = 4422
    notify_admin_new_receipt(receipt)
    assert send.call_args.kwargs["json"]["chat_id"] == 4422
