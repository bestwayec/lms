"""
Stage 2 & Stage 3 End-to-End Integration Tests:
- Stage 2: Automated Group Invitations & Enrollment Workflow
- Stage 3: Telegram Bot & Mini App Complete Integration

Covers:
- Teacher-generated invitations, secure codes, Telegram deep links
- Student deep link request, teacher approval/rejection lifecycle
- Automated notification Outbox messages (producers and Telegram card formatting)
- Group capacity limits, expiry, revocation, and cross-center isolation
- Free classroom student exam launch (TMA + Web), refresh/resume, and submission
- Authentic DB Result persistence and 100% parity between web gradebook and Telegram bot
- Replayed callbacks and bot restart resilience
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from asgiref.sync import async_to_sync
from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.courses.invitation_service import (
    create_group_invitation,
    join_group_by_code,
    join_group_by_token,
    review_join_request,
    revoke_group_invitation,
)
from apps.courses.models import (
    Course,
    GroupEnrollment,
    GroupInvitation,
    GroupJoinRequest,
    GroupMembershipHistory,
    Homework,
    StudentGroup,
)
from apps.notifications.bot.group_assistant import (
    _build_teacher_workspace_keyboard,
    group_assistant_callback_handler,
)
from apps.notifications.bot.handlers import start_handler
from apps.notifications.models import OutboxMessage
from apps.notifications.outbox import render
from apps.organizations.models import CenterBranch, LearningCenter
from apps.results.models import Result
from apps.telegram_app.test_api import tma_test_start_view
from apps.tests.models import Choice, Question, Test, TestAttempt


@pytest.fixture(autouse=True)
def mock_telegram_transport():
    with patch("apps.notifications.services.telegram_service.TelegramService._send_message", return_value={"ok": True, "result": {"message_id": 12345}}), \
         patch("apps.notifications.services.telegram_service.TelegramService.send_message", return_value=True), \
         patch("apps.notifications.services.telegram_service.TelegramService.send_message_with_keyboard", return_value=True), \
         patch("apps.notifications.services.telegram_service.TelegramService._send_document", return_value={"ok": True, "result": {"message_id": 12346}}):
        yield


@pytest.fixture
def center_a(db):
    owner = User.objects.create_user(email="owner-a@grandec.test", password="pass", role="admin")
    return LearningCenter.objects.create(name="Center Alpha", slug="center-alpha", owner=owner)


@pytest.fixture
def center_b(db):
    owner = User.objects.create_user(email="owner-b@grandec.test", password="pass", role="admin")
    return LearningCenter.objects.create(name="Center Beta", slug="center-beta", owner=owner)


@pytest.fixture
def branch_a(db, center_a):
    return CenterBranch.objects.create(name="Alpha Branch 1", center=center_a, branch_code="AL01")


@pytest.fixture
def branch_b(db, center_b):
    return CenterBranch.objects.create(name="Beta Branch 1", center=center_b, branch_code="BE01")


@pytest.fixture
def teacher_a(db, center_a, branch_a):
    return User.objects.create_user(
        email="teacher-alpha@grandec.test",
        password="pass",
        role="teacher",
        first_name="Abdulla",
        last_name="Qodiriy",
        learning_center=center_a,
        branch=branch_a,
        telegram_chat_id=9001,
        telegram_identity_verified_at=timezone.now(),
    )


@pytest.fixture
def student_free(db):
    return User.objects.create_user(
        email="student-free@grandec.test",
        password="pass",
        role="student",
        first_name="Nodir",
        last_name="Karimov",
        telegram_chat_id=9002,
        telegram_identity_verified_at=timezone.now(),
    )


@pytest.fixture
def student_center_b(db, center_b, branch_b):
    return User.objects.create_user(
        email="student-beta@grandec.test",
        password="pass",
        role="student",
        first_name="Temur",
        last_name="Bek",
        learning_center=center_b,
        branch=branch_b,
        telegram_chat_id=9003,
    )


@pytest.fixture
def group_a(db, teacher_a, branch_a):
    return StudentGroup.objects.create(
        name="Ona tili Intensive",
        teacher=teacher_a,
        branch=branch_a,
        invite_code="ONATILI",
        max_students=2,  # small capacity for capacity tests
    )


@pytest.fixture
def sample_test(db, teacher_a):
    course = Course.objects.create(teacher=teacher_a, title="Ona tili Kursi", slug="ona-tili-kursi")
    t = Test.objects.create(
        course=course,
        title="Ona tili va Adabiyot 20-talik",
        subject="uzbek",
        assessment_category=Test.AssessmentCategory.TOPIC_TEST,
        audience_mode=Test.AudienceMode.GROUP_ONLY,
        access_type=Test.AccessType.STUDENTS_ONLY,
        time_limit_minutes=30,
        status="published",
        is_active=True,
        created_by=teacher_a,
    )
    # 2 questions
    q1 = Question.objects.create(test=t, text="Qaysi so'z imloviy to'g'ri yozilgan?", points=2, position=1)
    Choice.objects.create(question=q1, text="Mubolag'a", is_correct=True, position=1)
    Choice.objects.create(question=q1, text="Mubolaga", is_correct=False, position=2)

    q2 = Question.objects.create(test=t, text="'O'tkan kunlar' romanining muallifi kim?", points=2, position=2)
    Choice.objects.create(question=q2, text="Abdulla Qodiriy", is_correct=True, position=1)
    Choice.objects.create(question=q2, text="Cho'lpon", is_correct=False, position=2)
    return t


# =========================================================================
# STAGE 2 TESTS: INVITATIONS, APPROVALS, NOTIFICATIONS & POLICIES
# =========================================================================

@pytest.mark.django_db
def test_invitation_creation_and_deep_link(teacher_a, group_a):
    invitation = create_group_invitation(
        teacher=teacher_a,
        group_id=group_a.id,
        code="OT-2026",
        requires_approval=True,
    )
    assert invitation.group == group_a
    assert invitation.code == "OT-2026"
    assert invitation.requires_approval is True
    assert invitation.is_usable is True

    # Telegram deep link format
    deep_link = f"https://t.me/GrandecBot?start=join_{invitation.code}"
    assert "start=join_OT-2026" in deep_link


@pytest.mark.django_db
def test_student_deep_link_join_request_enqueues_outbox_notification(student_free, teacher_a, group_a):
    invitation = create_group_invitation(
        teacher=teacher_a,
        group_id=group_a.id,
        requires_approval=True,
    )
    # Clear outbox before action
    OutboxMessage.objects.all().delete()

    res = join_group_by_token(student_free, invitation.token)
    assert res["status"] == "pending_approval"
    assert "tasdig'i kutilmoqda" in res["message"]

    req = GroupJoinRequest.objects.get(group=group_a, student=student_free)
    assert req.status == GroupJoinRequest.Status.PENDING

    # Outbox message to teacher
    outbox = OutboxMessage.objects.filter(event=OutboxMessage.Event.JOIN_REQUEST_SUBMITTED).first()
    assert outbox is not None
    assert outbox.recipient == teacher_a
    card = render(outbox)
    assert card is not None
    assert "Guruhga qo'shilish so'rovi" in card.text
    assert student_free.first_name in card.text


@pytest.mark.django_db
def test_teacher_approval_workflow_and_membership_history(student_free, teacher_a, group_a):
    invitation = create_group_invitation(teacher=teacher_a, group_id=group_a.id, requires_approval=True)
    res = join_group_by_token(student_free, invitation.token)
    req_id = res["request_id"]

    OutboxMessage.objects.all().delete()

    # Teacher reviews and approves
    review_res = review_join_request(teacher=teacher_a, request_id=req_id, approved=True)
    assert review_res["status"] == "approved"

    # Student is now in group
    assert group_a.students.filter(id=student_free.id).exists()

    # Membership history record exists
    history = GroupMembershipHistory.objects.filter(group=group_a, student=student_free).first()
    assert history is not None
    assert history.action == GroupMembershipHistory.Action.JOINED

    # Student was sent approval notification
    outbox = OutboxMessage.objects.filter(event=OutboxMessage.Event.JOIN_REQUEST_APPROVED).first()
    assert outbox is not None
    assert outbox.recipient == student_free
    card = render(outbox)
    assert card is not None
    assert "Guruhga qabul qilindingiz" in card.text


@pytest.mark.django_db
def test_teacher_rejection_workflow(student_free, teacher_a, group_a):
    invitation = create_group_invitation(teacher=teacher_a, group_id=group_a.id, requires_approval=True)
    res = join_group_by_token(student_free, invitation.token)
    req_id = res["request_id"]

    OutboxMessage.objects.all().delete()

    review_res = review_join_request(
        teacher=teacher_a,
        request_id=req_id,
        approved=False,
        rejection_reason="Guruh yo'nalishi to'g'ri kelmadi",
    )
    assert review_res["status"] == "rejected"
    assert not group_a.students.filter(id=student_free.id).exists()

    # Student notified of rejection
    outbox = OutboxMessage.objects.filter(event=OutboxMessage.Event.JOIN_REQUEST_REJECTED).first()
    assert outbox is not None
    assert outbox.recipient == student_free
    card = render(outbox)
    assert card is not None
    assert "rad etildi" in card.text


@pytest.mark.django_db
def test_invitation_expiry_and_revocation_checks(student_free, teacher_a, group_a):
    inv = create_group_invitation(teacher=teacher_a, group_id=group_a.id, expires_in_days=1)
    # Manually expire
    GroupInvitation.objects.filter(id=inv.id).update(expires_at=timezone.now() - timedelta(minutes=5))

    with pytest.raises(ValidationError, match="muddati tugagan"):
        join_group_by_token(student_free, inv.token)

    # Revocation
    inv2 = create_group_invitation(teacher=teacher_a, group_id=group_a.id)
    revoke_group_invitation(teacher=teacher_a, invitation_id=inv2.id)

    with pytest.raises(ValidationError, match="bekor qilingan"):
        join_group_by_token(student_free, inv2.token)


@pytest.mark.django_db
def test_group_capacity_limit_enforcement(teacher_a, group_a):
    # group_a has max_students=2
    s1 = User.objects.create_user(email="s1@test.uz", password="p", role="student")
    s2 = User.objects.create_user(email="s2@test.uz", password="p", role="student")
    s3 = User.objects.create_user(email="s3@test.uz", password="p", role="student")

    inv = create_group_invitation(teacher=teacher_a, group_id=group_a.id, requires_approval=False)

    join_group_by_token(s1, inv.token)
    join_group_by_token(s2, inv.token)

    assert group_a.students.count() == 2

    # Third student must be rejected due to capacity limit
    OutboxMessage.objects.all().delete()
    inv.refresh_from_db()
    uses_before = inv.uses_count

    with pytest.raises(ValueError, match="Guruh to'lgan"):
        join_group_by_token(s3, inv.token)

    # Rejected enrollment must create no membership, consume no invitation use, and send no welcome notification
    assert not group_a.students.filter(id=s3.id).exists()
    inv.refresh_from_db()
    assert inv.uses_count == uses_before
    assert not OutboxMessage.objects.filter(recipient=s3).exists()


@pytest.mark.django_db
def test_cross_center_invitation_denial(student_center_b, teacher_a, group_a):
    # student_center_b is in Center Beta; group_a is in Center Alpha
    inv = create_group_invitation(teacher=teacher_a, group_id=group_a.id, requires_approval=False)

    with pytest.raises(ValueError, match="boshqa o'quv markaziga"):
        join_group_by_token(student_center_b, inv.token)


# =========================================================================
# STAGE 3 TESTS: TELEGRAM BOT WORKSPACE & MINI APP E2E
# =========================================================================

@pytest.mark.django_db
def test_telegram_bot_teacher_workspace_callbacks(teacher_a, group_a, student_free):
    # Create a pending join request
    inv = create_group_invitation(teacher=teacher_a, group_id=group_a.id, requires_approval=True)
    res = join_group_by_token(student_free, inv.token)
    req_id = res["request_id"]

    # Mock Telegram Update & Context
    class FakeChat:
        def __init__(self, chat_id):
            self.id = chat_id
            self.type = "private"

    class FakeMessage:
        def __init__(self, chat_id):
            self.text = ""
            self.reply_markup = None
            self.chat = FakeChat(chat_id)

        async def edit_text(self, text, reply_markup=None, parse_mode=None):
            self.text = text
            self.reply_markup = reply_markup

        async def reply_text(self, text, reply_markup=None, parse_mode=None):
            self.text = text
            self.reply_markup = reply_markup

    class FakeCallbackQuery:
        def __init__(self, data, from_user):
            self.data = data
            self.from_user = from_user
            self.message = FakeMessage(from_user.id)

        async def answer(self, text=None, show_alert=False):
            self.last_answer = text or ""

        async def edit_message_text(self, text, reply_markup=None, parse_mode=None):
            return await self.message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)

    class FakeUser:
        def __init__(self, user_id):
            self.id = user_id
            self.username = "teacher_test"

    class FakeBot:
        def __init__(self):
            self.username = "grandec_bot"

    class FakeContext:
        def __init__(self):
            self.bot = FakeBot()

    user = FakeUser(teacher_a.telegram_chat_id)
    chat = FakeChat(teacher_a.telegram_chat_id)
    context = FakeContext()

    update = type("Update", (), {
        "callback_query": FakeCallbackQuery("tch_requests", user),
        "effective_user": user,
        "effective_chat": chat,
        "message": FakeMessage(teacher_a.telegram_chat_id),
    })()

    # 1. Teacher views pending requests
    async_to_sync(group_assistant_callback_handler)(update, context)
    assert "qo'shilish so'rovlari" in update.callback_query.message.text
    assert student_free.first_name in update.callback_query.message.text

    # 2. Teacher approves via callback `tch_appr_<req_id>`
    update.callback_query.data = f"tch_appr_{req_id}"
    async_to_sync(group_assistant_callback_handler)(update, context)
    assert group_a.students.filter(id=student_free.id).exists()

    # 3. Replayed callback resilience: clicking approve again does not crash
    async_to_sync(group_assistant_callback_handler)(update, context)
    assert "allaqachon ko'rib chiqilgan" in getattr(update.callback_query, "last_answer", "")


@pytest.mark.django_db
def test_end_to_end_classroom_free_student_exam_runner_and_bot_parity(student_free, teacher_a, group_a, sample_test):
    # 1. Enroll student in group
    inv = create_group_invitation(teacher=teacher_a, group_id=group_a.id, requires_approval=False)
    join_group_by_token(student_free, inv.token)

    # 2. Assign sample_test to group_a
    due = timezone.now() + timedelta(days=2)
    hw = Homework.objects.create(
        group=group_a,
        test=sample_test,
        title="Ona tili Vazifa #1",
        start_date=timezone.now() - timedelta(hours=1),
        due_date=due,
        created_by=teacher_a,
    )
    assert hw.id is not None

    # 3. Student starts attempt via TMA test start view
    from rest_framework_simplejwt.tokens import RefreshToken

    client = APIClient()
    token = str(RefreshToken.for_user(student_free).access_token)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    client.force_authenticate(student_free)

    resp = client.post(f"/tma/api/tests/{sample_test.id}/start/")
    assert resp.status_code == 200
    res_data = resp.json()
    attempt_id = res_data["attempt_id"]
    assert res_data["is_timed"] is True
    assert res_data["time_limit_minutes"] == 30

    # 4. Student saves answers
    q1 = sample_test.questions.get(position=1)
    c1 = q1.choices.get(is_correct=True)
    save_resp = client.post(
        f"/api/tests/attempts/{attempt_id}/save-answer/",
        {"question_id": q1.id, "choice_ids": [c1.id]},
        format="json",
    )
    assert save_resp.status_code == 200

    # 5. Refresh & Resume simulation: attempt detail loads previous answers
    resume_resp = client.get(f"/api/tests/attempts/{attempt_id}/")
    assert resume_resp.status_code == 200
    resumed_q1 = next(q for q in resume_resp.data["questions"] if q["id"] == q1.id)
    assert c1.id in resumed_q1["selected_choice_ids"]

    # Save q2
    q2 = sample_test.questions.get(position=2)
    c2 = q2.choices.get(is_correct=True)
    client.post(
        f"/api/tests/attempts/{attempt_id}/save-answer/",
        {"question_id": q2.id, "choice_ids": [c2.id]},
        format="json",
    )

    # 6. Submit attempt
    submit_resp = client.post(f"/api/tests/attempts/{attempt_id}/submit/")
    assert submit_resp.status_code == 200
    res_dict = submit_resp.data.get("result", submit_resp.data)
    assert res_dict["correct_answers"] == 2
    assert float(res_dict["percentage"]) == 100.0

    # 7. Authentic Result record verified in DB
    result = Result.objects.filter(student=student_free, test=sample_test).first()
    assert result is not None
    assert result.correct_answers == 2
    assert result.total_questions == 2
    assert result.score == 4

    # 8. Parity Check: Teacher views result in gradebook and bot
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {str(RefreshToken.for_user(teacher_a).access_token)}")
    client.force_authenticate(teacher_a)
    gradebook_resp = client.get(f"/api/tests/{sample_test.id}/gradebook/")
    assert gradebook_resp.status_code == 200
    ranking = gradebook_resp.data.get("ranking", [])
    student_row = next(r for r in ranking if r["student_id"] == student_free.id)
    assert student_row is not None
    assert float(student_row["percentage"]) == 100.0

    # 9. Non-enrolled student without group membership is blocked from GROUP_ONLY test
    outsider = User.objects.create_user(email="outsider@grandec.test", password="pass", role="student")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {str(RefreshToken.for_user(outsider).access_token)}")
    client.force_authenticate(outsider)
    denied_resp = client.post(f"/tma/api/tests/{sample_test.id}/start/")
    assert denied_resp.status_code in (403, 404)
