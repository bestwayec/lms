"""GRANDEC 8.3 Phase 4 tests: truthful insights, teacher analytics/CSV export, and outbox automation."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.courses.models import Course, Homework, HomeworkSubmission, StudentGroup, Subject
from apps.essays.models import EssayCriterionScore, EssaySubmission, EssayTopic
from apps.essays.services import TeacherReviewService
from apps.notifications.models import OutboxMessage
from apps.notifications.outbox import (
    enqueue_deadline_reminders,
    enqueue_essay_appeal_submitted,
    render,
)
from apps.results.models import Result
from apps.tests.models import Test, TestAttempt


def _make_result(student, course, teacher, *, subject: str, title: str, percentage: float, offset_hours: int) -> Result:
    test = Test.objects.create(
        title=title,
        course=course,
        created_by=teacher,
        subject=subject,
        audience_mode=Test.AudienceMode.PUBLIC_FREE,
        status="published",
        is_active=True,
    )
    attempt = TestAttempt.objects.create(
        student=student,
        test=test,
        status=TestAttempt.Status.COMPLETED,
        is_preview=False,
    )
    res = Result.objects.create(
        attempt=attempt,
        student=student,
        test=test,
        course=course,
        total_questions=20,
        correct_answers=round(percentage / 5),
        wrong_answers=20 - round(percentage / 5),
        score=Decimal(str(round(percentage / 5))),
        max_score=Decimal("20"),
        percentage=Decimal(str(percentage)),
        is_passed=percentage >= 60,
        time_taken_seconds=120,
    )
    Result.objects.filter(pk=res.pk).update(
        calculated_at=timezone.now() - timedelta(hours=offset_hours)
    )
    return res


@pytest.mark.django_db
class TestGrandec83AnalyticsAndAutomation:
    def test_student_insights_min_samples_trend_assignments_and_feedback(self):
        cache.clear()
        teacher = User.objects.create_user(email="ins-t@example.com", password="pass", role="teacher", is_active=True)
        student = User.objects.create_user(
            email="ins-s@example.com",
            password="pass",
            role="student",
            first_name="Ali",
            last_name="Valiyev",
            is_active=True,
        )
        subj, _ = Subject.objects.get_or_create(name="Insights Subj", slug="ins-subj-83")
        course = Course.objects.create(title="Insights Course", slug="ins-course-83", teacher=teacher, subject=subj)

        client = APIClient()
        client.force_authenticate(student)

        # 0 attempts -> strictly truthful empty state
        res0 = client.get("/api/results/insights/")
        assert res0.status_code == 200
        d0 = res0.json()
        assert d0["has_sufficient_data"] is False
        assert d0["strongest_subject"] is None
        assert d0["weakest_subject"] is None
        assert d0["improvement_trend"] is None
        assert d0["assignments"]["completion_rate"] is None

        # 1 attempt only -> still below min_subject_samples (2)
        _make_result(student, course, teacher, subject="uzbek", title="U1", percentage=85.0, offset_hours=4)
        d1 = client.get("/tma/api/insights/").json()
        assert d1["has_sufficient_data"] is False
        assert d1["strongest_subject"] is None

        # 4 attempts across two subjects (oldest lower, recent higher -> upward trend)
        _make_result(student, course, teacher, subject="english", title="E1", percentage=40.0, offset_hours=10)
        _make_result(student, course, teacher, subject="english", title="E2", percentage=50.0, offset_hours=8)
        _make_result(student, course, teacher, subject="uzbek", title="U2", percentage=90.0, offset_hours=2)

        topic = EssayTopic.objects.create(title="Imlo inshosi", description="Write carefully")
        esub = EssaySubmission.objects.create(
            student=student,
            assigned_reviewer=teacher,
            topic=topic,
            essay_text="Test essay body " * 20,
            word_count=40,
            status=EssaySubmission.Status.AI_EVALUATED,
            total_score=Decimal("18.0"),
        )
        TeacherReviewService.submit_review(
            submission=esub,
            teacher=teacher,
            criteria_scores={str(i): Decimal("1.5") for i in range(1, 13)},
            teacher_comments="Yaxshi dalillar keltirilgan.",
        )

        hw = Homework.objects.create(
            student=student,
            title="Weekly HW",
            content_type=Homework.ContentType.CUSTOM,
            status=Homework.Status.ACTIVE,
            due_date=timezone.now() + timedelta(days=2),
            created_by=teacher,
        )
        HomeworkSubmission.objects.create(homework=hw, student=student, is_completed=True)

        d4 = client.get("/api/results/insights/").json()
        assert d4["has_sufficient_data"] is True
        assert d4["strongest_subject"]["subject"] == "uzbek"
        assert d4["weakest_subject"]["subject"] == "english"
        assert d4["improvement_trend"] is not None
        assert d4["improvement_trend"]["direction"] == "up"
        assert d4["assignments"]["completion_rate"] == 100.0
        assert len(d4["essays"]["recent_teacher_feedback"]) == 1
        assert "Yaxshi dalillar" in d4["essays"]["recent_teacher_feedback"][0]["comments"]

    def test_teacher_group_detail_roster_extended_analytics_and_csv_export(self):
        cache.clear()
        teacher = User.objects.create_user(email="grp-t@example.com", password="pass", role="teacher", is_active=True)
        other_teacher = User.objects.create_user(email="grp-other@example.com", password="pass", role="teacher", is_active=True)
        student1 = User.objects.create_user(
            email="grp-s1@example.com",
            password="pass",
            role="student",
            first_name="=CMD|calc",
            last_name="Student",
            is_active=True,
        )
        student2 = User.objects.create_user(
            email="grp-s2@example.com",
            password="pass",
            role="student",
            first_name="Dilnoza",
            last_name="Karimova",
            is_active=True,
        )
        group = StudentGroup.objects.create(name="=EvilGroup", teacher=teacher, status=StudentGroup.Status.ACTIVE)
        group.students.add(student1, student2)

        subj, _ = Subject.objects.get_or_create(name="Group Subj", slug="grp-subj-83")
        course = Course.objects.create(title="Group Course", slug="grp-course-83", teacher=teacher, subject=subj)

        hard_test = Test.objects.create(
            title="Hard Mock",
            course=course,
            created_by=teacher,
            subject="uzbek",
            audience_mode=Test.AudienceMode.PUBLIC_FREE,
            status="published",
            is_active=True,
        )
        for st, pct in ((student1, 35.0), (student2, 45.0)):
            att = TestAttempt.objects.create(student=st, test=hard_test, status=TestAttempt.Status.COMPLETED, is_preview=False)
            Result.objects.create(
                attempt=att,
                student=st,
                test=hard_test,
                course=course,
                total_questions=20,
                correct_answers=8,
                wrong_answers=12,
                score=Decimal("8"),
                max_score=Decimal("20"),
                percentage=Decimal(str(pct)),
                is_passed=False,
            )

        # Overdue homework completed by only 1/2 students
        hw = Homework.objects.create(
            group=group,
            title="Overdue HW",
            content_type=Homework.ContentType.CUSTOM,
            status=Homework.Status.ACTIVE,
            due_date=timezone.now() - timedelta(days=1),
            created_by=teacher,
        )
        HomeworkSubmission.objects.create(homework=hw, student=student2, is_completed=True)

        topic = EssayTopic.objects.create(title="Group Essay", description="Desc")
        esub = EssaySubmission.objects.create(
            student=student1,
            topic=topic,
            essay_text="Body " * 25,
            word_count=25,
            status=EssaySubmission.Status.AI_EVALUATED,
            total_score=Decimal("12.0"),
        )
        EssayCriterionScore.objects.create(
            submission=esub,
            criterion_id=1,
            name="Mavzu",
            score=Decimal("1.0"),
        )

        # Verify teacher_group_detail_view returns non-empty roster (bugfix check)
        t_client = APIClient()
        t_client.force_authenticate(teacher)
        detail = t_client.get(f"/api/classroom/teacher/groups/{group.id}/")
        assert detail.status_code == 200
        assert len(detail.json()["roster"]) == 2

        # Verify extended analytics payload
        an = t_client.get(f"/api/v1/school/groups/{group.id}/analytics/")
        assert an.status_code == 200
        an_data = an.json()
        assert an_data["assignments_summary"]["completion_rate"] == 50.0
        assert an_data["assignments_summary"]["overdue_count"] == 1
        assert len(an_data["weak_tests"]) == 1
        assert an_data["weak_tests"][0]["test_title"] == "Hard Mock"
        assert an_data["essay_insights"]["criterion_averages"][0]["criterion_id"] == 1

        # Verify CSV export auth + formula neutralization
        s_client = APIClient()
        s_client.force_authenticate(student1)
        assert s_client.get(f"/api/classroom/groups/{group.id}/report/export/").status_code == 403

        o_client = APIClient()
        o_client.force_authenticate(other_teacher)
        assert o_client.get(f"/api/classroom/groups/{group.id}/report/export/").status_code == 403

        csv_resp = t_client.get(f"/api/classroom/groups/{group.id}/report/export/")
        assert csv_resp.status_code == 200
        assert "no-store" in csv_resp["Cache-Control"]
        body = csv_resp.content.decode("utf-8-sig")
        assert "'=EvilGroup" in body
        assert "'=CMD|calc" in body

    def test_outbox_archived_exclusion_and_essay_appeal_review_idempotency(self, settings):
        settings.NOTIFICATION_OUTBOX_ENABLED = False
        teacher = User.objects.create_user(email="ob-t@example.com", password="pass", role="teacher", is_active=True)
        student = User.objects.create_user(email="ob-s@example.com", password="pass", role="student", is_active=True)

        active_group = StudentGroup.objects.create(name="Active Outbox", teacher=teacher, status=StudentGroup.Status.ACTIVE)
        archived_group = StudentGroup.objects.create(name="Archived Outbox", teacher=teacher, status=StudentGroup.Status.ARCHIVED)
        active_group.students.add(student)
        archived_group.students.add(student)

        now = timezone.now()
        hw_active = Homework.objects.create(
            group=active_group,
            title="Active Due",
            content_type=Homework.ContentType.CUSTOM,
            status=Homework.Status.ACTIVE,
            due_date=now + timedelta(hours=6),
            created_by=teacher,
        )
        hw_arch = Homework.objects.create(
            group=archived_group,
            title="Archived Due",
            content_type=Homework.ContentType.CUSTOM,
            status=Homework.Status.ACTIVE,
            due_date=now + timedelta(hours=6),
            created_by=teacher,
        )

        queued = enqueue_deadline_reminders(now=now)
        assert queued >= 1
        assert OutboxMessage.objects.filter(
            event=OutboxMessage.Event.HOMEWORK_REMINDER,
            dedup_key=f"hw_reminder24:{hw_active.id}:{student.id}",
        ).exists()
        assert not OutboxMessage.objects.filter(
            event=OutboxMessage.Event.HOMEWORK_REMINDER,
            dedup_key=f"hw_reminder24:{hw_arch.id}:{student.id}",
        ).exists()

        # Appeal + review transactional outbox chain (no external Telegram sends)
        topic = EssayTopic.objects.create(title="Apellatsiya Mavzusi", description="Desc")
        sub = EssaySubmission.objects.create(
            student=student,
            topic=topic,
            essay_text="Word " * 30,
            word_count=30,
            status=EssaySubmission.Status.GRADED,
            total_score=Decimal("16.0"),
        )
        TeacherReviewService.request_teacher_review(
            submission=sub,
            student=student,
            reason="Mezon 3 qayta ko'rilsin",
        )
        sub.refresh_from_db()
        appeal_msgs = OutboxMessage.objects.filter(
            event=OutboxMessage.Event.ESSAY_APPEAL,
            recipient=teacher,
        )
        assert appeal_msgs.count() == 1
        assert enqueue_essay_appeal_submitted(sub, teacher) is False
        appeal_card = render(appeal_msgs.first())
        assert appeal_card is not None
        assert "Apellatsiya Mavzusi" in appeal_card.text

        rev = TeacherReviewService.submit_review(
            submission=sub,
            teacher=teacher,
            criteria_scores={
                str(i): EssayCriterionScore.CRITERION_MAX_SCORES.get(i, Decimal("1.5"))
                for i in range(1, 13)
            },
            teacher_comments="Ajoyib insho!",
        )
        review_msgs = OutboxMessage.objects.filter(
            event=OutboxMessage.Event.ESSAY_REVIEWED,
            recipient=student,
            dedup_key=f"essay_reviewed:{sub.id}:{rev.id}",
        )
        assert review_msgs.count() == 1
        review_card = render(review_msgs.first())
        assert review_card is not None
        assert f"{rev.final_score:.2f}/24" in review_card.text
