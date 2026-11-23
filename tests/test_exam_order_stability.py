"""Shuffled question/option order is random per attempt but stable across reloads.

Before: an unseeded random.shuffle ran on every request, so a refresh moved
options (A↔C) and, with question shuffling, renumbered questions mid-exam.
"""

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.courses.models import Course
from apps.tests.models import Choice, Question, Test, TestAttempt


@pytest.mark.django_db
def test_order_is_stable_across_reloads_and_differs_between_attempts():
    t = User.objects.create_user(email="ord_t@example.com", password="p", role="teacher")
    course = Course.objects.create(teacher=t, title="O", slug="ord")
    test = Test.objects.create(
        course=course, created_by=t, title="O", status="published", is_active=True,
        shuffle_questions=True, shuffle_choices=True, max_attempts=0,
    )
    for i in range(12):
        q = Question.objects.create(test=test, position=i + 1, text=f"Q{i}", points=1, question_type="single")
        for j in range(5):
            Choice.objects.create(question=q, text=f"{i}-{j}", is_correct=j == 0, position=j + 1)

    def order(student):
        api = APIClient()
        api.force_authenticate(student)
        attempt = TestAttempt.objects.create(test=test, student=student)
        snaps = []
        for _ in range(3):
            data = api.get(f"/api/tests/attempts/{attempt.id}/").data
            snaps.append([(q["id"], [c["id"] for c in q["choices"]]) for q in data["questions"]])
        return snaps

    a = order(User.objects.create_user(email="ord_s1@example.com", password="p", role="student"))
    b = order(User.objects.create_user(email="ord_s2@example.com", password="p", role="student"))
    assert a[0] == a[1] == a[2]
    assert b[0] == b[1] == b[2]
    assert a[0] != b[0]  # still shuffled per attempt (12 questions × 5 options: collision ~impossible)
