"""
Tests for Telegram Mini App (TMA) 7.0 Tests Access Policy and Isolation.
Verifies that TMA tests view respects unified access policies:
- Group-only tests are visible only to enrolled classroom members.
- Public free tests are visible to all students.
- Subscriber-only tests are restricted to PRO subscribers.
- Response payloads include 7.0 metadata (is_timed, assessment_category, subject).
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.courses.models import Course, StudentGroup, Subject
from apps.tests.models import Test

User = get_user_model()


@pytest.mark.django_db
class TestTmaTestsAccessPolicy7:
    def setup_method(self):
        cache.clear()
        self.client = APIClient()

        # Teachers & Students
        self.teacher = User.objects.create_user(
            email="teacher7@example.com",
            password="SafePassword2026!",
            role=User.Role.TEACHER,
            first_name="Ustoz",
        )
        self.student_group_a = User.objects.create_user(
            email="student_a@example.com",
            password="SafePassword2026!",
            role=User.Role.STUDENT,
            first_name="Talaba A",
        )
        self.student_group_b = User.objects.create_user(
            email="student_b@example.com",
            password="SafePassword2026!",
            role=User.Role.STUDENT,
            first_name="Talaba B",
        )

        subject, _ = Subject.objects.get_or_create(name="Ona tili", slug="ona-tili-7")
        self.course = Course.objects.create(
            title="Ona Tili 7.0 Kurs",
            slug="ona-tili-7-kurs",
            teacher=self.teacher,
            subject=subject,
        )

        # Classroom Group
        self.group_a = StudentGroup.objects.create(
            name="7.0 Guruh A",
            teacher=self.teacher,
            subject="uzbek",
        )
        self.group_a.students.add(self.student_group_a)

        # Tests
        self.public_test = Test.objects.create(
            title="Public 7.0 Ochiq Test",
            course=self.course,
            subject="uzbek",
            assessment_category="topic_test",
            status="published",
            is_active=True,
            audience_mode=Test.AudienceMode.PUBLIC_FREE,
            time_limit_minutes=0,
            total_questions=10,
            created_by=self.teacher,
        )

        self.group_test = Test.objects.create(
            title="Guruh A Uchun Maxsus Test",
            course=self.course,
            subject="uzbek",
            assessment_category="classroom_quiz",
            status="published",
            is_active=True,
            audience_mode=Test.AudienceMode.GROUP_ONLY,
            assigned_group=self.group_a,
            time_limit_minutes=30,
            total_questions=20,
            created_by=self.teacher,
        )

        self.pro_test = Test.objects.create(
            title="Faqat PRO Obunachilar Testi",
            course=self.course,
            subject="uzbek",
            assessment_category="full_mock",
            status="published",
            is_active=True,
            audience_mode=Test.AudienceMode.SUBSCRIBERS_ONLY,
            time_limit_minutes=45,
            total_questions=30,
            created_by=self.teacher,
        )

    def test_unauthenticated_request_is_rejected(self):
        res = self.client.get("/tma/api/tests/")
        assert res.status_code == 401

    def test_student_in_group_sees_classroom_test_and_public_test(self):
        self.client.force_authenticate(user=self.student_group_a)
        res = self.client.get("/tma/api/tests/")
        assert res.status_code == 200
        test_ids = [t["id"] for t in res.data["tests"]]

        assert self.public_test.id in test_ids
        assert self.group_test.id in test_ids
        assert self.pro_test.id not in test_ids

        # Check metadata
        public_item = next(t for t in res.data["tests"] if t["id"] == self.public_test.id)
        assert public_item["is_timed"] is False
        assert public_item["assessment_category"] == "topic_test"
        assert public_item["subject"] == "uzbek"

        group_item = next(t for t in res.data["tests"] if t["id"] == self.group_test.id)
        assert group_item["is_timed"] is True
        assert group_item["time_limit_minutes"] == 30
        assert group_item["assessment_category"] == "classroom_quiz"

    def test_student_outside_group_cannot_see_group_test(self):
        self.client.force_authenticate(user=self.student_group_b)
        res = self.client.get("/tma/api/tests/")
        assert res.status_code == 200
        test_ids = [t["id"] for t in res.data["tests"]]

        assert self.public_test.id in test_ids
        assert self.group_test.id not in test_ids
        assert self.pro_test.id not in test_ids
