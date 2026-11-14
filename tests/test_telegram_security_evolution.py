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


@pytest.mark.django_db(transaction=True)
def test_teacher_menu_is_private_and_only_shows_assigned_group_tests():
    from apps.courses.models import Course
    from apps.tests.models import Test, TestAttempt
    from apps.notifications.bot.group_assistant import ustoz_menu_command
    teacher = User.objects.create_user(email="menu-teacher@example.test", password="test", role="teacher", telegram_chat_id=85201, telegram_identity_verified_at=timezone.now())
    student = User.objects.create_user(email="menu-student@example.test", password="test")
    group = StudentGroup.objects.create(name="Private group", teacher=teacher)
    group.students.add(student)
    course = Course.objects.create(title="Course", slug="menu-private-course", teacher=teacher)
    assigned = Test.objects.create(title="Assigned", course=course, assigned_group=group)
    unrelated = Test.objects.create(title="Unrelated", course=course)
    for test, score in ((assigned, 42), (unrelated, 99)):
        TestAttempt.objects.create(student=student, test=test, score=score, percentage=score, status=TestAttempt.Status.COMPLETED)
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=85201, username="teacher"),
        effective_chat=SimpleNamespace(id=-100, type="supergroup"),
        message=SimpleNamespace(reply_text=AsyncMock()), callback_query=None,
    )
    async_to_sync(ustoz_menu_command)(update, SimpleNamespace())
    group_reply = update.message.reply_text.await_args.args[0]
    assert "Private group" not in group_reply and "99" not in group_reply
    update.effective_chat = SimpleNamespace(id=85201, type="private")
    async_to_sync(ustoz_menu_command)(update, SimpleNamespace())
    private_reply = update.message.reply_text.await_args.args[0]
    assert "42" in private_reply and "99" not in private_reply


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("action", ["adj_5", "adj_9999", "pass", "set_100", "grade"])
def test_old_grade_buttons_do_not_modify_scores(action):
    from apps.courses.models import Course
    from apps.tests.models import Test, TestAttempt
    from apps.notifications.bot.group_assistant import group_assistant_callback_handler
    teacher = User.objects.create_user(email="override-teacher@example.test", password="test", role="teacher")
    student = User.objects.create_user(email="override-student@example.test", password="test")
    course = Course.objects.create(title="Course", slug="override-private-course", teacher=teacher)
    test = Test.objects.create(title="Test", course=course)
    attempt = TestAttempt.objects.create(student=student, test=test, score=30, percentage=30, status=TestAttempt.Status.COMPLETED)
    parts = action.split("_", 1)
    payload = f"ustoz_{parts[0]}_{attempt.id}" + (f"_{parts[1]}" if len(parts) > 1 else "")
    query = SimpleNamespace(data=payload, answer=AsyncMock(), edit_message_text=AsyncMock())
    update = SimpleNamespace(callback_query=query)
    async_to_sync(group_assistant_callback_handler)(update, SimpleNamespace())
    assert query.answer.await_args.kwargs["show_alert"] is True
    query.edit_message_text.assert_not_awaited()
    attempt.refresh_from_db()
    assert attempt.score == 30 and attempt.percentage == 30 and not attempt.teacher_overridden


@pytest.mark.django_db
def test_parent_invitation_expiry_replay_and_revocation():
    from datetime import timedelta
    from apps.accounts.models import ParentInvitation
    from apps.accounts.services.parent_link import (
        generate_parent_deep_link_token, redeem_parent_invitation,
        revoke_parent_invitations, verify_parent_deep_link_token,
    )
    student = User.objects.create_user(email="invite-lifecycle@example.test", password="test", role="student")
    expired = generate_parent_deep_link_token(student.id)
    ParentInvitation.objects.filter(student=student).update(expires_at=timezone.now() - timedelta(seconds=1))
    assert not verify_parent_deep_link_token(student.id, expired)
    with pytest.raises(ValueError):
        redeem_parent_invitation(student_id=student.id, token=expired, telegram_id=21311)

    revoked = generate_parent_deep_link_token(student.id)
    revoke_parent_invitations(student.id)
    with pytest.raises(ValueError):
        redeem_parent_invitation(student_id=student.id, token=revoked, telegram_id=21311)

    valid = generate_parent_deep_link_token(student.id)
    redeem_parent_invitation(student_id=student.id, token=valid, telegram_id=21311)
    with pytest.raises(ValueError):
        redeem_parent_invitation(student_id=student.id, token=valid, telegram_id=21311)


@pytest.mark.django_db
def test_parent_invitation_revocation_is_scoped_to_current_student():
    from rest_framework.test import APIClient
    from apps.accounts.services.parent_link import generate_parent_deep_link_token, verify_parent_deep_link_token
    one = User.objects.create_user(email="invite-one@example.test", password="test", role="student")
    two = User.objects.create_user(email="invite-two@example.test", password="test", role="student")
    one_token = generate_parent_deep_link_token(one.id)
    two_token = generate_parent_deep_link_token(two.id)
    client = APIClient()
    client.force_authenticate(one)
    assert client.delete("/api/v1/parents/invitations/").status_code == 200
    assert not verify_parent_deep_link_token(one.id, one_token)
    assert verify_parent_deep_link_token(two.id, two_token)


@pytest.mark.django_db(transaction=True)
def test_concurrent_invitation_redemption_only_one_succeeds():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from django.db import close_old_connections, connection
    from apps.accounts.services.parent_link import generate_parent_deep_link_token, redeem_parent_invitation
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL row locking test")
    student = User.objects.create_user(email="invite-race@example.test", password="test", role="student")
    token = generate_parent_deep_link_token(student.id)
    barrier = Barrier(2)
    def redeem(telegram_id):
        close_old_connections()
        try:
            barrier.wait(timeout=20)
            redeem_parent_invitation(student_id=student.id, token=token, telegram_id=telegram_id)
            return True
        except ValueError:
            return False
        finally:
            close_old_connections()
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(redeem, (21321, 21322))) == [False, True]


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


@pytest.mark.django_db(transaction=True)
def test_parent_link_requires_signed_invitation_and_cannot_replace_parent():
    from apps.accounts.models import ParentStudentRelation
    from apps.accounts.services.parent_link import generate_parent_deep_link_token
    from apps.notifications.bot.handlers import parent_start_handler, start_handler
    student = User.objects.create_user(email="parent-child@example.test", password="test", role="student")
    message = SimpleNamespace(reply_text=AsyncMock(), text="")
    tg_user = SimpleNamespace(id=7441, full_name="Parent", first_name="Parent", last_name="", username="")
    update = SimpleNamespace(effective_user=tg_user, effective_chat=SimpleNamespace(id=7441, type="private"), message=message, callback_query=None)
    context = SimpleNamespace(args=[str(student.id)], user_data={})
    async_to_sync(parent_start_handler)(update, context)
    assert not ParentStudentRelation.objects.filter(student=student).exists()
    context.args = [f"parent_{student.id}_{generate_parent_deep_link_token(student.id)}"]
    async_to_sync(start_handler)(update, context)
    relation = ParentStudentRelation.objects.get(student=student)
    assert relation.parent_telegram_id == 7441 and relation.is_verified
    tg_user.id = 7442
    async_to_sync(start_handler)(update, context)
    relation.refresh_from_db()
    assert relation.parent_telegram_id == 7441
    assert ParentStudentRelation.objects.filter(student=student).count() == 1


@pytest.mark.django_db
def test_parent_code_api_cannot_verify_or_disclose_another_students_relation():
    from apps.accounts.models import ParentStudentRelation
    from rest_framework.test import APIClient
    owner = User.objects.create_user(email="code-owner@example.test", password="test")
    attacker = User.objects.create_user(email="code-attacker@example.test", password="test")
    relation = ParentStudentRelation.objects.create(student=owner, parent_phone="+998900001111", verification_code="827341")
    client = APIClient()
    client.force_authenticate(attacker)
    response = client.post("/api/v1/parents/verify-code/", {"verification_code": "827341"}, format="json")
    assert response.status_code == 404
    assert "+998900001111" not in str(response.data)
    relation.refresh_from_db()
    assert not relation.is_verified


@pytest.mark.django_db(transaction=True)
def test_parent_invitation_concurrent_redemption_is_single_use():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from django.db import close_old_connections, connection
    from apps.accounts.models import ParentStudentRelation
    from apps.accounts.services.parent_link import link_parent_to_student
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL row locking test")
    student = User.objects.create_user(email="parent-race@example.test", password="test")
    barrier = Barrier(2)
    def redeem(telegram_id):
        close_old_connections()
        barrier.wait(timeout=20)
        try:
            link_parent_to_student(student=student, telegram_id=telegram_id)
            return True
        except ValueError:
            return False
        finally:
            close_old_connections()
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(redeem, (8301, 8302)))
    assert sorted(results) == [False, True]
    assert ParentStudentRelation.objects.filter(student=student, is_verified=True).count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize("path", ["/api/auth/telegram/direct-link/", "/api/v1/accounts/link-telegram/"])
def test_direct_telegram_id_link_is_rejected_without_mutating_accounts(path):
    from rest_framework.test import APIClient
    victim = User.objects.create_user(email="raw-id-victim@example.test", password="test", telegram_chat_id=9713, telegram_identity_verified_at=timezone.now())
    admin = User.objects.create_superuser(email="raw-id-admin@example.test", password="test")
    client = APIClient()
    client.force_authenticate(admin)
    response = client.post(path, {"telegram_chat_id": victim.telegram_chat_id}, format="json")
    assert response.status_code == 400
    assert response.data["challenge_endpoint"] == "/api/auth/telegram/connect/"
    victim.refresh_from_db()
    admin.refresh_from_db()
    assert victim.telegram_chat_id == 9713 and victim.telegram_identity_verified_at is not None
    assert admin.telegram_chat_id is None and admin.telegram_identity_verified_at is None
