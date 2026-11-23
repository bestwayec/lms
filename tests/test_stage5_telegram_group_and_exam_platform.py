"""
Tests for GRANDEC NEXT 5.0:
- Telegram Group Bot 5.0 (Pinned-style menu, persistent attendance, safe unlinking)
- Persistent Attendance backed by AttendanceSession & AttendanceRecord (DB recovery, verification)
- Universal Exam Modes (Timed vs Untimed policy)
- Rasch & Standard Scoring Integrity (Practice label, history preservation, calibration check)
- Teacher & Admin Bot Workspaces 5.0
"""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.attendance.models import AttendanceRecord, AttendanceSession
from apps.courses.models import Course, StudentGroup
from apps.notifications.bot.group_assistant import (
    _build_group_menu_keyboard,
    _db_finalize_session,
    _db_get_attendance_session_info,
    _db_get_or_create_open_attendance,
    _db_mark_student_present,
    _render_group_menu,
    admin_bot_menu_command,
    cmd_unlink_group,
    group_menu_command,
    ustoz_menu_command,
)
from apps.organizations.models import LearningCenter
from apps.results.models import Result
from apps.telegram_app.test_api import tma_test_start_view
from apps.tests.models import Choice, ExamScoringProfile, Question, Test, TestAttempt
from apps.tests.rasch_engine import RaschEngine

User = get_user_model()


@pytest.fixture
def center(db):
    owner = User.objects.create_user(email="center-owner@grandec.test", password="pass", role="admin")
    return LearningCenter.objects.create(name="Grand Education Bosh", slug="grand-bosh", owner=owner)


@pytest.fixture
def teacher(db, center):
    return User.objects.create_user(
        email="teacher-5@grandec.test",
        password="pass",
        role="teacher",
        first_name="Alisher",
        last_name="Navoiy",
        telegram_chat_id=5001,
        telegram_identity_verified_at=timezone.now(),
    )


@pytest.fixture
def student_1(db):
    return User.objects.create_user(
        email="student-1@grandec.test",
        password="pass",
        role="student",
        first_name="Bobur",
        telegram_chat_id=5101,
        telegram_identity_verified_at=timezone.now(),
    )


@pytest.fixture
def student_2(db):
    return User.objects.create_user(
        email="student-2@grandec.test",
        password="pass",
        role="student",
        first_name="Zahiriddin",
        telegram_chat_id=5102,
        telegram_identity_verified_at=timezone.now(),
    )


@pytest.fixture
def group(db, teacher, student_1, student_2):
    grp = StudentGroup.objects.create(
        name="Ona Tili Guruh-A",
        invite_code="GR-5001",
        teacher=teacher,
        telegram_chat_id=-100999888,
        telegram_chat_title="Ona Tili 11-A",
    )
    grp.students.add(student_1, student_2)
    return grp


@pytest.fixture
def course(db, teacher):
    return Course.objects.create(title="Ona Tili 2026", slug="ona-tili-2026", teacher=teacher)


# ===========================================================================
# 1. Group Menu & Pinned Menu Structure
# ===========================================================================
@pytest.mark.django_db
def test_group_menu_keyboard_has_all_required_actions(group):
    markup = _build_group_menu_keyboard(group.id)
    buttons = [btn for row in markup.inline_keyboard for btn in row]
    labels = [b.text for b in buttons]

    assert "📚 Bugungi vazifalar" in labels
    assert "📝 Faol testlar" in labels
    assert "📅 Dars jadvali" in labels
    assert "✅ Davomat" in labels
    assert "📊 Guruh progressi" in labels
    assert "🏆 Ixtiyoriy reyting" in labels
    assert "📱 Mini App" in labels
    assert "👨‍🏫 Ustoz bilan bog‘lanish" in labels


@pytest.mark.django_db
def test_group_menu_renders_for_linked_group(group):
    text, markup = _render_group_menu({
        "id": group.id,
        "name": group.name,
        "code": group.invite_code,
        "teacher": "Alisher Navoiy",
        "students_count": 2,
    })
    assert "GRANDEC | Guruh boshqaruvi" in text
    assert group.name in text
    assert group.invite_code in text
    assert markup is not None


@pytest.mark.django_db(transaction=True)
def test_group_menu_command_denies_private_chat():
    update = SimpleNamespace(
        effective_chat=SimpleNamespace(type="private", id=123),
        effective_user=SimpleNamespace(id=123),
        message=SimpleNamespace(reply_text=AsyncMock()),
    )
    context = SimpleNamespace()
    async_to_sync(group_menu_command)(update, context)
    update.message.reply_text.assert_awaited_once()
    msg_call = update.message.reply_text.await_args[0][0]
    assert "Telegram guruhida ishlatiladi" in msg_call


# ===========================================================================
# 2. Database-Backed Persistent Attendance Lifecycle & Bot Restart Recovery
# ===========================================================================
@pytest.mark.django_db(transaction=True)
def test_persistent_attendance_lifecycle_and_restart_recovery(group, teacher, student_1, student_2):
    # Step 1: Open attendance — creates DRAFT AttendanceSession in DB
    data, err = _db_get_or_create_open_attendance(group.telegram_chat_id, teacher.telegram_chat_id)
    assert err is None
    assert data is not None
    session_id = data["session_id"]
    assert data["present_count"] == 0
    assert data["enrolled_count"] == 2

    # Verify session row in DB
    session = AttendanceSession.objects.get(id=session_id)
    assert session.status == AttendanceSession.Status.DRAFT

    # Step 2: Enrolled student clicks "Keldim"
    res1 = _db_mark_student_present(session_id, student_1.telegram_chat_id)
    assert res1["status"] == "success"
    assert res1["present_count"] == 1

    # Verify AttendanceRecord in DB
    rec = AttendanceRecord.objects.get(session=session, student=student_1)
    assert rec.status == AttendanceRecord.Status.PRESENT

    # Step 3: Duplicate click by same student is handled gracefully
    res_dup = _db_mark_student_present(session_id, student_1.telegram_chat_id)
    assert res_dup["status"] == "already"

    # Step 4: Unverified or unenrolled user is rejected
    res_unknown = _db_mark_student_present(session_id, 9999999)
    assert res_unknown["status"] == "unverified"

    other_student = User.objects.create_user(
        email="other@test.com", password="x", telegram_chat_id=77777, telegram_identity_verified_at=timezone.now()
    )
    res_unenrolled = _db_mark_student_present(session_id, other_student.telegram_chat_id)
    assert res_unenrolled["status"] == "not_enrolled"

    # Step 5: Simulate Bot Restart — state is read fresh from DB
    info = _db_get_attendance_session_info(session_id)
    assert info is not None
    assert info["present_count"] == 1
    assert student_1.get_full_name() in info["present_names"]

    # Step 6: Finalize attendance — unmarked student becomes ABSENT
    fin_data, fin_err = _db_finalize_session(session_id, teacher.telegram_chat_id)
    assert fin_err is None
    assert fin_data["present_count"] == 1
    assert fin_data["absent_count"] == 1
    assert fin_data["total_count"] == 2

    session.refresh_from_db()
    assert session.status == AttendanceSession.Status.FINALIZED

    rec2 = AttendanceRecord.objects.get(session=session, student=student_2)
    assert rec2.status == AttendanceRecord.Status.ABSENT


# ===========================================================================
# 3. Safe Group Unlinking
# ===========================================================================
@pytest.mark.django_db(transaction=True)
def test_safe_group_unlinking_by_teacher(group, teacher):
    update = SimpleNamespace(
        effective_chat=SimpleNamespace(type="supergroup", id=group.telegram_chat_id),
        effective_user=SimpleNamespace(id=teacher.telegram_chat_id),
        message=SimpleNamespace(reply_text=AsyncMock()),
    )
    context = SimpleNamespace()

    async_to_sync(cmd_unlink_group)(update, context)
    update.message.reply_text.assert_awaited_once()

    group.refresh_from_db()
    assert group.telegram_chat_id is None
    assert group.telegram_chat_title == ""


# ===========================================================================
# 4. Universal Exam Modes (Timed vs Untimed Policy)
# ===========================================================================
@pytest.mark.django_db(transaction=True)
def test_tma_test_start_timed_vs_untimed(course, student_1):
    # Untimed test: time_limit_minutes = 0
    test_untimed = Test.objects.create(
        title="Untimed Topic Quiz",
        course=course,
        time_limit_minutes=0,
        status="published",
        is_active=True,
    )
    q1 = Question.objects.create(test=test_untimed, text="Savol 1?", question_type="single", position=1)
    Choice.objects.create(question=q1, text="Variant A", is_correct=True, position=0)

    # Timed test: time_limit_minutes = 30
    test_timed = Test.objects.create(
        title="Timed Mock Exam",
        course=course,
        time_limit_minutes=30,
        status="published",
        is_active=True,
    )
    q2 = Question.objects.create(test=test_timed, text="Savol 2?", question_type="single", position=1)
    Choice.objects.create(question=q2, text="Variant B", is_correct=True, position=0)

    # Mock request authenticated as student_1
    request = SimpleNamespace(body=b"", method="POST")

    with patch("apps.telegram_app.test_api._jwt_auth", return_value=student_1):
        # 1. Start untimed test
        resp_untimed = tma_test_start_view(request, test_untimed.id)
        assert resp_untimed.status_code == 200
        import json
        data_untimed = json.loads(resp_untimed.content)
        assert data_untimed["is_timed"] is False
        assert data_untimed["remaining_seconds"] is None
        assert data_untimed["time_limit_minutes"] == 0

        # 2. Start timed test
        resp_timed = tma_test_start_view(request, test_timed.id)
        assert resp_timed.status_code == 200
        data_timed = json.loads(resp_timed.content)
        assert data_timed["is_timed"] is True
        assert data_timed["remaining_seconds"] is not None
        assert data_timed["remaining_seconds"] > 0
        assert data_timed["time_limit_minutes"] == 30


# ===========================================================================
# 5. Rasch & Standard Scoring Integrity
# ===========================================================================
@pytest.mark.django_db(transaction=True)
def test_rasch_scoring_integrity_and_history_stability(course, student_1, student_2):
    test = Test.objects.create(
        title="Ona Tili Rasch Practice",
        course=course,
        time_limit_minutes=20,
        scoring_type="RASCH_DYNAMIC",
        status="published",
        is_active=True,
    )
    q1 = Question.objects.create(test=test, text="Savol 1?", points=2, position=1)
    c1 = Choice.objects.create(question=q1, text="A", is_correct=True, position=0)
    q2 = Question.objects.create(test=test, text="Savol 2?", points=3, position=2)
    Choice.objects.create(question=q2, text="B", is_correct=True, position=0)

    # Student 1 takes test
    att1 = TestAttempt.objects.create(test=test, student=student_1, status=TestAttempt.Status.IN_PROGRESS)
    from apps.tests.models import StudentAnswer
    sa = StudentAnswer.objects.create(attempt=att1, question=q1, is_correct=True)
    sa.selected_choices.add(c1)

    questions = [q1, q2]
    answers = {q1.id: sa}

    # Evaluate attempt
    score, max_score, grade, explanation = RaschEngine.evaluate_attempt_rasch(att1, questions, answers)
    assert score > 0
    assert max_score >= score
    # Dynamic Weighted Practice mode must clearly be labeled as practice
    assert "(Mashq)" in grade
    assert "Dinamik vaznli mashq bali (taxminiy/tajribaviy)" in explanation

    att1.status = TestAttempt.Status.COMPLETED
    att1.rasch_score = score
    att1.rasch_grade = grade
    att1.save()

    res1 = Result.objects.create(
        attempt=att1,
        test=test,
        student=student_1,
        course=course,
        total_questions=2,
        correct_answers=1,
        wrong_answers=1,
        score=Decimal("2.0"),
        max_score=Decimal("5.0"),
        percentage=Decimal("40.0"),
        is_passed=False,
        rasch_score=score,
        max_rasch_score=max_score,
        rasch_grade=grade,
        rasch_explanation=explanation,
    )

    # Student 2 completes test later, triggering recalculate_test_rasch
    RaschEngine.recalculate_test_rasch(test.id)

    # History preservation: Result 1 must NOT have its historical grade silently rewritten
    res1.refresh_from_db()
    assert res1.rasch_score == score
    assert res1.rasch_grade == grade


@pytest.mark.django_db(transaction=True)
def test_verified_rasch_requires_calibration_volume(course, student_1):
    profile = ExamScoringProfile.objects.create(
        name="Rasmiy BMB Profil", version="2026.1", is_verified=True
    )
    test = Test.objects.create(
        title="Attestatsiya Mock",
        course=course,
        scoring_profile=profile,
        scoring_type="RASCH_DYNAMIC",
        status="published",
        is_active=True,
    )
    q1 = Question.objects.create(test=test, text="Q1", points=2, position=1)
    Choice.objects.create(question=q1, text="A", is_correct=True, position=0)

    att = TestAttempt.objects.create(test=test, student=student_1, status=TestAttempt.Status.IN_PROGRESS)
    # Total sample is 0 (< 30)
    score, max_score, grade, explanation = RaschEngine.evaluate_attempt_rasch(att, [q1], {})
    assert "Kalibratsiya talab qilinadi" in grade
    assert "Kalibratsiya talab qilinadi" in explanation


# ===========================================================================
# 6. Teacher & Admin Bot Workspaces 5.0
# ===========================================================================
@pytest.mark.django_db(transaction=True)
def test_teacher_workspace_command_for_teacher(teacher):
    update = SimpleNamespace(
        effective_chat=SimpleNamespace(type="private", id=teacher.telegram_chat_id),
        effective_user=SimpleNamespace(id=teacher.telegram_chat_id),
        message=SimpleNamespace(reply_text=AsyncMock()),
    )
    context = SimpleNamespace()

    async_to_sync(ustoz_menu_command)(update, context)
    update.message.reply_text.assert_awaited_once()
    msg = update.message.reply_text.await_args[0][0]
    assert "Ustoz Kabineti 5.0" in msg


@pytest.mark.django_db(transaction=True)
def test_admin_workspace_command_for_admin(db):
    admin = User.objects.create_user(
        email="superadmin@grandec.test",
        password="pass",
        role="admin",
        is_superuser=True,
        telegram_chat_id=999901,
        telegram_identity_verified_at=timezone.now(),
    )
    update = SimpleNamespace(
        effective_chat=SimpleNamespace(type="private", id=admin.telegram_chat_id),
        effective_user=SimpleNamespace(id=admin.telegram_chat_id),
        message=SimpleNamespace(reply_text=AsyncMock()),
    )
    context = SimpleNamespace()

    async_to_sync(admin_bot_menu_command)(update, context)
    update.message.reply_text.assert_awaited_once()
    msg = update.message.reply_text.await_args[0][0]
    assert "Admin Boshqaruv Markazi 5.0" in msg
    assert "Platforma Super-Admini" in msg
