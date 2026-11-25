"""
Unit and Integration Tests for GRANDEC NEXT 8.0:
- Smart Classroom and Single-Use Student Targeted Invitations
- Safe Group Deletion Prevention with Academic History Audit & Archiving/Restore
- Idempotent Educational XP Awarding with Duplicate Prevention
- Essay Classroom & Human Review Center (Appeal Workflow, Teacher Final Review, Voice Feedback)
- Group vs Platform Leaderboard Scoping and Pseudonymous Privacy Masking
- TMA Profile Gamification (Streak, Weekly XP, Weekly League)
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.accounts.gamification import award_educational_xp, get_platform_leaderboard
from apps.accounts.models import EducationalXPEvent, User
from apps.courses.group_service import (
    archive_group,
    delete_group_safely,
    get_group_dependencies,
    restore_group,
)
from apps.courses.invitation_service import (
    create_group_invitation,
    join_group_by_code,
    join_group_by_token,
)
from apps.courses.models import Course, GroupInvitation, Homework, HomeworkSubmission, StudentGroup
from apps.essays.models import EssayCriterionScore, EssaySubmission, EssayTopic, TeacherReview
from apps.essays.services import TeacherReviewService


@pytest.fixture(autouse=True)
def mock_telegram_transport():
    with patch("apps.notifications.services.telegram_service.TelegramService._send_message", return_value={"ok": True, "result": {"message_id": 991}}), \
         patch("apps.notifications.services.telegram_service.TelegramService.send_message", return_value=True), \
         patch("apps.notifications.services.telegram_service.TelegramService.send_message_with_keyboard", return_value=True), \
         patch("apps.notifications.services.telegram_service.TelegramService._send_document", return_value={"ok": True, "result": {"message_id": 992}}):
        yield


@pytest.mark.django_db
class TestSmartClassroomInvitations:
    def test_targeted_student_invitation_enforcement(self):
        teacher = User.objects.create_user(
            email="teacher80@example.com",
            password="pass",
            role="teacher",
            is_active=True,
        )
        student_target = User.objects.create_user(
            email="target@example.com",
            password="pass",
            role="student",
            is_active=True,
        )
        student_other = User.objects.create_user(
            email="other@example.com",
            password="pass",
            role="student",
            is_active=True,
        )
        group = StudentGroup.objects.create(
            name="8-Sinf Ona Tili",
            teacher=teacher,
            max_students=20,
            status="active",
        )

        # Create targeted single-use invitation
        inv = create_group_invitation(
            teacher,
            group.id,
            target_student=student_target,
        )
        assert inv.max_uses == 1
        assert inv.target_student == student_target
        assert inv.is_student_authorized(student_target) is True
        assert inv.is_student_authorized(student_other) is False

        # Other student attempts to use token -> must fail
        with pytest.raises(Exception) as exc_info:
            join_group_by_token(student_other, inv.token)
        assert "boshqa o'quvchi uchun mo'ljallangan" in str(exc_info.value)
        assert group.students.filter(id=student_other.id).exists() is False

        # Targeted student joins successfully
        res = join_group_by_token(student_target, inv.token)
        assert res["status"] == "joined"
        assert group.students.filter(id=student_target.id).exists() is True

        # Token cannot be reused (max_uses=1 exhausted)
        with pytest.raises(Exception) as exc_reused:
            join_group_by_token(student_target, inv.token)
        assert "chegarasiga yetildi" in str(exc_reused.value) or "tugagan" in str(exc_reused.value)

    def test_group_capacity_exhaustion(self):
        teacher = User.objects.create_user(
            email="teachercap@example.com",
            password="pass",
            role="teacher",
        )
        group = StudentGroup.objects.create(
            name="Fizika Kichik Guruh",
            teacher=teacher,
            max_students=1,
            status="active",
        )
        s1 = User.objects.create_user(email="s1@example.com", password="pass", role="student")
        s2 = User.objects.create_user(email="s2@example.com", password="pass", role="student")

        inv = create_group_invitation(teacher, group.id, max_uses=5)
        # s1 joins -> fills group to capacity (1/1)
        res1 = join_group_by_token(s1, inv.token)
        assert res1["status"] == "joined"

        # s2 attempts to join -> rejected due to capacity
        with pytest.raises(Exception) as exc:
            join_group_by_token(s2, inv.token)
        assert "to'lgan" in str(exc.value)


@pytest.mark.django_db
class TestGroupArchivingAndSafeDeletion:
    def test_safe_delete_prevention_when_academic_history_exists(self):
        teacher = User.objects.create_user(
            email="tarch@example.com",
            password="pass",
            role="teacher",
        )
        student = User.objects.create_user(
            email="sarch@example.com",
            password="pass",
            role="student",
        )
        group = StudentGroup.objects.create(name="Tarix-A", teacher=teacher, status="active")
        group.students.add(student)

        # Create homework
        hw = Homework.objects.create(
            group=group,
            title="1-Mavzu Tarix",
            created_by=teacher,
            due_date=timezone.now() + timezone.timedelta(days=7),
        )
        HomeworkSubmission.objects.create(homework=hw, student=student, status="submitted")

        # Audit dependencies
        deps = get_group_dependencies(group)
        assert deps["can_delete"] is False
        assert deps["dependencies"]["students_count"] == 1
        assert deps["dependencies"]["homeworks_count"] == 1
        assert deps["dependencies"]["homework_submissions_count"] == 1

        # Attempt to delete safely must raise ValidationError and enforce archiving
        with pytest.raises(Exception) as exc:
            delete_group_safely(group, actor=teacher)
        assert "arxivlang" in str(exc.value).lower()
        assert StudentGroup.objects.filter(id=group.id).exists() is True

        # Archive group
        archive_group(group, actor=teacher)
        group.refresh_from_db()
        assert group.status == "archived"
        assert group.is_active is False

        # Joining an archived group is strictly blocked
        inv = GroupInvitation.objects.create(group=group, created_by=teacher, token="token_archived", is_revoked=False)
        new_student = User.objects.create_user(email="snew@example.com", password="pass")
        with pytest.raises(Exception) as exc_arch:
            join_group_by_token(new_student, inv.token)
        assert "arxivlangan" in str(exc_arch.value)

        # Restore group
        restore_group(group, actor=teacher)
        group.refresh_from_db()
        assert group.status == "active"
        assert group.is_active is True

    def test_safe_delete_empty_group_succeeds(self):
        teacher = User.objects.create_user(email="tdel@example.com", password="pass", role="teacher")
        group = StudentGroup.objects.create(name="Bo'sh Guruh", teacher=teacher, status="active")

        deps = get_group_dependencies(group)
        assert deps["can_delete"] is True

        delete_group_safely(group, actor=teacher)
        assert StudentGroup.objects.filter(id=group.id).exists() is False


@pytest.mark.django_db
class TestGamificationEducationalXP:
    def test_idempotent_xp_awarding_prevents_duplicate_xp(self):
        student = User.objects.create_user(email="xp@example.com", password="pass", role="student")
        profile = student.profile
        initial_xp = profile.xp_points

        # Award 30 XP for test attempt
        event1, is_new1 = award_educational_xp(student, "test_attempt", "attempt_1001", 30)
        assert is_new1 is True
        assert event1.xp_amount == 30
        profile.refresh_from_db()
        assert profile.xp_points == initial_xp + 30

        # Duplicate award with same event_type and reference_id (e.g. repeated callback or page refresh)
        event2, is_new2 = award_educational_xp(student, "test_attempt", "attempt_1001", 30)
        assert is_new2 is False
        assert event2.id == event1.id
        profile.refresh_from_db()
        # XP must NOT double!
        assert profile.xp_points == initial_xp + 30

        # Different reference_id awards cleanly
        event3, is_new3 = award_educational_xp(student, "test_attempt", "attempt_1002", 20)
        assert is_new3 is True
        profile.refresh_from_db()
        assert profile.xp_points == initial_xp + 50

    def test_platform_leaderboard_privacy_masking(self):
        student_opt_out = User.objects.create_user(
            first_name="Maxfiy",
            last_name="Talaba",
            email="hidden@example.com",
            password="pass",
        )
        student_opt_out.profile.xp_points = 999
        student_opt_out.profile.leaderboard_opt_in = False
        student_opt_out.profile.save()

        student1 = User.objects.create_user(
            first_name="Alisher",
            last_name="Navoiy",
            email="ali@example.com",
            password="pass",
        )
        student1.profile.xp_points = 500
        student1.profile.leaderboard_opt_in = True
        student1.profile.leaderboard_pseudonym = "Lochin2026"
        student1.profile.save()

        student2 = User.objects.create_user(
            first_name="Bobur",
            last_name="Mirzo",
            email="bobur@example.com",
            password="pass",
        )
        student2.profile.xp_points = 300
        student2.profile.leaderboard_opt_in = True
        student2.profile.save()

        lb = get_platform_leaderboard(student1, period="all_time", limit=10)
        # Non-participating user (999 XP) is strictly excluded!
        assert lb["user_rank"] == 1
        user_ids = [item["user_id"] for item in lb["items"]]
        assert student_opt_out.id not in user_ids
        assert len(lb["items"]) == 2

        top_entry = lb["items"][0]
        second_entry = lb["items"][1]
        # User-selected pseudonym is shown; real first/last names and emails are never exposed!
        assert top_entry["display_name"] == "Lochin2026"
        assert "Alisher" not in top_entry["display_name"]
        assert "@" not in top_entry["display_name"]
        # Without pseudonym, opaque anonymous participant ID is used (not FirstName L.)
        assert second_entry["display_name"].startswith("Ishtirokchi #")
        assert "Bobur" not in second_entry["display_name"]

    def test_interrupted_xp_transaction_rolls_back_event_atomically(self):
        student = User.objects.create_user(email="atomicxp@example.com", password="pass", role="student")
        with patch("apps.accounts.gamification.record_user_activity", side_effect=RuntimeError("DB interrupted")):
            with pytest.raises(RuntimeError, match="DB interrupted"):
                award_educational_xp(student, "test_attempt", "attempt_atomic_1", 40)

        # Event must NOT persist if XP balance update failed!
        assert not EducationalXPEvent.objects.filter(user=student, reference_id="attempt_atomic_1").exists()
        student.profile.refresh_from_db()
        assert student.profile.xp_points == 0

        # Retry succeeds cleanly and awards full XP
        event, created = award_educational_xp(student, "test_attempt", "attempt_atomic_1", 40)
        assert created is True
        student.profile.refresh_from_db()
        assert student.profile.xp_points == 40


@pytest.mark.django_db
class TestEssayReviewAndAppealWorkflow:
    def test_appeal_submission_withdrawal_and_teacher_voice_review(self):
        teacher = User.objects.create_user(
            email="trev@example.com",
            password="pass",
            role="teacher",
            is_active=True,
        )
        student = User.objects.create_user(
            email="sessay@example.com",
            password="pass",
            role="student",
            is_active=True,
        )
        topic = EssayTopic.objects.create(
            title="Ona tilim — jon-u dilim",
            word_limit_min=50,
            word_limit_max=200,
            time_limit_minutes=30,
        )
        submission = EssaySubmission.objects.create(
            student=student,
            topic=topic,
            essay_text="Ona tili millatning ruhi va ma'naviy ko'zgusidir.",
            word_count=60,
            status=EssaySubmission.Status.GRADED,
            total_score=16,
            max_score=24,
        )

        # Student submits an appeal
        submission = TeacherReviewService.request_teacher_review(
            submission=submission,
            student=student,
            reason="Lug'at boyligi uchun mezon balli kam qo'yilgan deb hisoblayman.",
            criteria=["vocabulary"],
        )
        submission.refresh_from_db()
        assert submission.appeal_status == EssaySubmission.AppealStatus.AWAITING_REVIEWER or submission.appeal_status == EssaySubmission.AppealStatus.SUBMITTED
        assert submission.appeal_reason == "Lug'at boyligi uchun mezon balli kam qo'yilgan deb hisoblayman."

        # Duplicate active appeal request is blocked
        with pytest.raises(Exception) as exc_dup:
            TeacherReviewService.request_teacher_review(submission, student, "Yana bir ariza")
        assert "apellatsiya ko'rib chiqilmoqda" in str(exc_dup.value).lower()

        # Assign reviewer to submission
        submission.assigned_reviewer = teacher
        submission.save(update_fields=["assigned_reviewer"])

        # Teacher completes review with criteria adjustments and voice audio feedback
        audio_content = b"RIFF....WAVEfmt ...."
        voice_file = SimpleUploadedFile("feedback.wav", audio_content, content_type="audio/wav")
        scores = {i: 1.5 for i in range(1, 13)}

        TeacherReviewService.submit_review(
            submission=submission,
            teacher=teacher,
            criteria_scores=scores,
            teacher_comments="Ajoyib esse, mezon balli adolatli oshirildi.",
            voice_file=voice_file,
            voice_duration_seconds=45,
        )

        submission.refresh_from_db()
        assert submission.appeal_status == EssaySubmission.AppealStatus.RESOLVED
        assert submission.appeal_resolved_at is not None
        assert submission.status == EssaySubmission.Status.TEACHER_REVIEWED

        # Check teacher review record
        t_review = TeacherReview.objects.filter(submission=submission).first()
        assert t_review is not None
        assert t_review.final_score == 18.0
        assert t_review.voice_duration_seconds == 45
        assert bool(t_review.voice_feedback) is True
        assert t_review.voice_feedback.name.startswith("essays/audio/")

    def test_multi_group_essay_routing_and_gradebook_zero_score_integrity(self):
        from apps.essays.models import EssayAssignment
        from apps.essays.services import _find_reviewer_for_student, can_review_submission
        from rest_framework.test import APIClient

        t_uzbek = User.objects.create_user(email="tuz@example.com", password="pass", role="teacher", is_active=True)
        t_math = User.objects.create_user(email="tmath@example.com", password="pass", role="teacher", is_active=True)
        s_active = User.objects.create_user(email="sgrade@example.com", password="pass", role="student", is_active=True)
        s_missing = User.objects.create_user(email="smissing@example.com", password="pass", role="student", is_active=True)

        g_math = StudentGroup.objects.create(name="Matematika", teacher=t_math, subject="math", status="active")
        g_uzbek = StudentGroup.objects.create(name="Ona Tili", teacher=t_uzbek, subject="uzbek", status="active")
        g_math.students.add(s_active)
        g_uzbek.students.add(s_active, s_missing)

        topic_uz = EssayTopic.objects.create(
            title="Alisher Navoiy merosi",
            subject="uzbek",
            word_limit_min=50,
            word_limit_max=200,
        )
        assignment = EssayAssignment.objects.create(
            topic=topic_uz,
            group=g_uzbek,
            assigned_by=t_uzbek,
            due_at=timezone.now() + timezone.timedelta(days=3),
        )
        sub_zero = EssaySubmission.objects.create(
            student=s_active,
            topic=topic_uz,
            assignment=assignment,
            essay_text="Butunlay boshqa mavzu.",
            word_count=55,
            status=EssaySubmission.Status.GRADED,
            total_score=0,
            max_score=20,
            is_completely_off_topic=True,
        )

        # Reviewer routing picks t_uzbek, NEVER t_math
        assert _find_reviewer_for_student(s_active, submission=sub_zero) == t_uzbek
        assert can_review_submission(t_uzbek, sub_zero) is True
        assert can_review_submission(t_math, sub_zero) is False

        # Group gradebook includes both submitted (genuine 0) and missing student, and max_score=20
        client = APIClient()
        client.force_authenticate(t_uzbek)
        resp = client.get(f"/api/classroom/groups/{g_uzbek.id}/essays/{assignment.id}/gradebook/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["metrics"]["total_assigned"] == 2
        assert data["metrics"]["submitted_count"] == 1
        assert data["metrics"]["not_submitted_count"] == 1
        assert data["metrics"]["graded_count"] == 1
        assert data["metrics"]["avg_valid_score"] == 0.0
        assert data["metrics"]["max_score"] == 20


@pytest.mark.django_db
class TestGrandec8DefensiveSecurity:
    def test_voice_feedback_upload_rejects_html_and_playback_enforces_object_acl(self):
        from rest_framework.test import APIClient

        teacher = User.objects.create_user(email="sec-t@example.com", password="pass", role="teacher", is_active=True)
        other_teacher = User.objects.create_user(email="sec-t2@example.com", password="pass", role="teacher", is_active=True)
        student = User.objects.create_user(email="sec-s@example.com", password="pass", role="student", is_active=True)
        other_student = User.objects.create_user(email="sec-s2@example.com", password="pass", role="student", is_active=True)

        group = StudentGroup.objects.create(name="Sec Group", teacher=teacher, status="active")
        group.students.add(student)
        topic = EssayTopic.objects.create(title="Sec Topic", word_limit_min=50, word_limit_max=200)
        sub = EssaySubmission.objects.create(
            student=student,
            topic=topic,
            essay_text="Test essay text.",
            word_count=55,
            status=EssaySubmission.Status.GRADED,
            total_score=15,
            assigned_reviewer=teacher,
        )

        # 1. Malicious HTML upload as voice feedback is rejected
        html_payload = SimpleUploadedFile("evil.html", b"<script>alert(1)</script>", content_type="text/html")
        scores = {i: 1.5 for i in range(1, 13)}
        with pytest.raises(ValueError, match="audio"):
            TeacherReviewService.submit_review(sub, teacher, scores, voice_file=html_payload)

        # 2. Valid WAV upload succeeds and streams ONLY to owner student or assigned teacher
        wav_file = SimpleUploadedFile("note.wav", b"RIFF....WAVEfmt ", content_type="audio/wav")
        TeacherReviewService.submit_review(sub, teacher, scores, voice_file=wav_file, voice_duration_seconds=12)

        client = APIClient()
        # Unauthenticated blocked
        assert client.get(f"/api/classroom/essays/{sub.id}/voice/").status_code == 401
        # Other student blocked
        client.force_authenticate(other_student)
        assert client.get(f"/api/classroom/essays/{sub.id}/voice/").status_code == 403
        # Unrelated teacher blocked
        client.force_authenticate(other_teacher)
        assert client.get(f"/api/classroom/essays/{sub.id}/voice/").status_code == 403
        # Owner student succeeds with hardened private response headers
        client.force_authenticate(student)
        res = client.get(f"/api/classroom/essays/{sub.id}/voice/")
        assert res.status_code == 200
        assert res["X-Content-Type-Options"] == "nosniff"
        assert "no-store" in res["Cache-Control"]
        assert "sandbox" in res["Content-Security-Policy"]
        # X-Accel-Redirect mode hands off internal /_private_media/essays/audio/... path with empty body
        from django.test import override_settings

        with override_settings(PRIVATE_MEDIA_ACCEL_PREFIX="/_private_media/"):
            accel_res = client.get(f"/api/classroom/essays/{sub.id}/voice/")
        assert accel_res.status_code == 200
        assert accel_res["X-Accel-Redirect"].startswith("/_private_media/essays/audio/")
        assert accel_res.content == b""
        assert "no-store" in accel_res["Cache-Control"]
        # Assigned teacher also succeeds
        client.force_authenticate(teacher)
        assert client.get(f"/api/classroom/essays/{sub.id}/voice/").status_code == 200

    def test_public_leaderboard_endpoints_require_auth_and_redact_user_ids(self):
        from rest_framework.test import APIClient

        u1 = User.objects.create_user(first_name="Ali", last_name="Vali", email="u1lb@example.com", password="pass")
        u1.profile.xp_points = 200
        u1.profile.leaderboard_opt_in = True
        u1.profile.leaderboard_pseudonym = "Qalqon01"
        u1.profile.save()

        viewer = User.objects.create_user(email="viewer@example.com", password="pass")
        client = APIClient()

        # Anonymous access blocked
        assert client.get("/api/classroom/leaderboard/platform/").status_code == 401
        assert client.get("/api/v1/gamification/league/").status_code == 401

        # Authenticated viewer gets pseudonymized leaderboard with other user_id redacted
        client.force_authenticate(viewer)
        resp = client.get("/api/classroom/leaderboard/platform/?period=all_time")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["display_name"] == "Qalqon01"
        assert "user_id" not in items[0]
