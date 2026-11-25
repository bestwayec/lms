"""GRANDEC 8.3 backend performance, cache invalidation, and queue pagination tests."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.cache import cache
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.gamification import (
    award_educational_xp,
    get_platform_leaderboard,
    get_weekly_league_leaderboard,
)
from apps.accounts.models import User
from apps.courses.group_service import archive_group, get_group_full_analytics, remove_student_from_group
from apps.courses.models import Course, Homework, StudentGroup, Subject
from apps.essays.models import EssaySubmission, EssayTopic
from apps.tests.models import Question, Test


@pytest.mark.django_db
class TestGrandec83PerformanceAndCache:
    def test_tma_tests_view_avoids_n_plus_one_question_count_queries(self):
        cache.clear()
        teacher = User.objects.create_user(email="perf-t@example.com", password="pass", role="teacher", is_active=True)
        student = User.objects.create_user(email="perf-s@example.com", password="pass", role="student", is_active=True)
        subj, _ = Subject.objects.get_or_create(name="Perf Subj", slug="perf-subj-83")
        course = Course.objects.create(title="Perf Course", slug="perf-course-83", teacher=teacher, subject=subj)

        # Create 12 active public tests with questions
        for idx in range(12):
            t = Test.objects.create(
                title=f"Perf Test {idx}",
                course=course,
                created_by=teacher,
                audience_mode=Test.AudienceMode.PUBLIC_FREE,
                status="published",
                is_active=True,
            )
            Question.objects.create(
                test=t,
                text=f"Q{idx}",
                position=1,
            )

        client = APIClient()
        client.force_authenticate(student)

        with CaptureQueriesContext(connection) as cold_ctx:
            res = client.get("/tma/api/tests/")
        assert res.status_code == 200
        payload_tests = res.json()["tests"]
        assert len(payload_tests) >= 12
        assert all(item["total_questions"] >= 1 for item in payload_tests if item["title"].startswith("Perf Test "))
        # Must stay O(1) queries regardless of test count (annotated total_questions prevents per-test COUNT)
        assert len(cold_ctx) <= 12

        # Add 10 more tests: query count must NOT grow with test count
        for idx in range(12, 22):
            t = Test.objects.create(
                title=f"Perf Test {idx}",
                course=course,
                created_by=teacher,
                audience_mode=Test.AudienceMode.PUBLIC_FREE,
                status="published",
                is_active=True,
            )
            Question.objects.create(test=t, text=f"Q{idx}", position=1)
        cache.clear()
        with CaptureQueriesContext(connection) as scaled_ctx:
            res_scaled = client.get("/tma/api/tests/")
        assert res_scaled.status_code == 200
        assert len(scaled_ctx) == len(cold_ctx)

        with CaptureQueriesContext(connection) as warm_ctx:
            res2 = client.get("/tma/api/tests/")
        assert res2.status_code == 200
        assert len(warm_ctx) < len(cold_ctx)

    @pytest.mark.django_db(transaction=True)
    def test_tma_tests_cache_invalidates_immediately_on_group_archive_and_removal(self):
        cache.clear()
        teacher = User.objects.create_user(email="inv-t@example.com", password="pass", role="teacher", is_active=True)
        student = User.objects.create_user(email="inv-s@example.com", password="pass", role="student", is_active=True)
        subj, _ = Subject.objects.get_or_create(name="Inv Subj", slug="inv-subj-83")
        course = Course.objects.create(title="Inv Course", slug="inv-course-83", teacher=teacher, subject=subj)
        group = StudentGroup.objects.create(name="G-Inv", teacher=teacher, status="active")
        group.students.add(student)

        test = Test.objects.create(
            title="Private Group Quiz",
            course=course,
            created_by=teacher,
            audience_mode=Test.AudienceMode.GROUP_ONLY,
            assigned_group=group,
            status="published",
            is_active=True,
        )
        Homework.objects.create(
            group=group,
            test=test,
            title="HW Quiz",
            created_by=teacher,
            due_date=timezone.now() + timedelta(days=2),
        )

        client = APIClient()
        client.force_authenticate(student)
        assert any(t["id"] == test.id for t in client.get("/tma/api/tests/").json()["tests"])

        # Archiving group must immediately revoke cached visibility
        archive_group(group, teacher)
        assert not any(t["id"] == test.id for t in client.get("/tma/api/tests/").json()["tests"])

        # Restoring and removing student also updates visibility immediately
        group.status = StudentGroup.Status.ACTIVE
        group.save(update_fields=["status"])
        remove_student_from_group(group, student, actor=teacher)
        assert not any(t["id"] == test.id for t in client.get("/tma/api/tests/").json()["tests"])

    def test_empty_group_analytics_and_leaderboard_skip_wasted_queries(self):
        teacher = User.objects.create_user(email="emp-t@example.com", password="pass", role="teacher", is_active=True)
        group = StudentGroup.objects.create(name="Empty Group", teacher=teacher, status="active")

        with CaptureQueriesContext(connection) as analytics_ctx:
            data = get_group_full_analytics(group)
        assert data["total_students"] == 0
        assert data["students"] == []
        assert len(analytics_ctx) <= 2

        client = APIClient()
        client.force_authenticate(teacher)
        with CaptureQueriesContext(connection) as lb_ctx:
            resp = client.get(f"/api/classroom/groups/{group.id}/leaderboard/")
        assert resp.status_code == 200
        assert resp.json()["total_students"] == 0
        assert len(lb_ctx) <= 3

    def test_essay_review_queue_filter_pagination_and_null_timestamp_order(self):
        teacher = User.objects.create_user(email="q-t@example.com", password="pass", role="teacher", is_active=True)
        student = User.objects.create_user(email="q-s@example.com", password="pass", role="student", is_active=True)
        topic = EssayTopic.objects.create(title="Queue Topic", word_limit_min=20, word_limit_max=200)

        EssaySubmission.objects.create(
            student=student,
            topic=topic,
            essay_text="Pending without appeal timestamp.",
            word_count=5,
            status=EssaySubmission.Status.PENDING_TEACHER,
            assigned_reviewer=teacher,
        )
        EssaySubmission.objects.create(
            student=student,
            topic=topic,
            essay_text="Appealed submission.",
            word_count=4,
            status=EssaySubmission.Status.PENDING_TEACHER,
            assigned_reviewer=teacher,
            teacher_review_requested=True,
            appeal_status=EssaySubmission.AppealStatus.SUBMITTED,
        )

        client = APIClient()
        client.force_authenticate(teacher)

        all_res = client.get("/api/classroom/teacher/essays/reviews/?limit=1&offset=0").json()
        assert all_res["total_count"] == 2
        assert all_res["count"] == 1

        appeals_res = client.get("/api/classroom/teacher/essays/reviews/?filter=appeals").json()
        assert appeals_res["total_count"] == 1
        assert appeals_res["pending_reviews"][0]["appeal_status"] == "submitted"

        pending_res = client.get("/api/classroom/teacher/essays/reviews/?filter=pending").json()
        assert pending_res["total_count"] == 1
        assert pending_res["pending_reviews"][0]["appeal_status"] == "none"

    @pytest.mark.django_db(transaction=True)
    def test_gamification_leaderboard_cache_invalidates_after_xp_award(self):
        cache.clear()
        student = User.objects.create_user(email="xp-lb@example.com", password="pass", role="student", is_active=True)
        student.profile.leaderboard_opt_in = True
        student.profile.leaderboard_pseudonym = "FastRunner"
        student.profile.save(update_fields=["leaderboard_opt_in", "leaderboard_pseudonym"])

        # Prime caches
        get_platform_leaderboard(user=student, period="weekly")
        get_weekly_league_leaderboard(student)

        award_educational_xp(student, "test_passed", "perf-xp-1", xp_amount=60)
        plat = get_platform_leaderboard(user=student, period="weekly")
        league = get_weekly_league_leaderboard(student)
        assert any(i["display_name"] == "FastRunner" and i["xp"] >= 60 for i in plat["items"])
        assert any(p["name"] == "FastRunner" and p["weekly_xp"] >= 60 for p in league["participants"])
