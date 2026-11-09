import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.accounts.models import Profile

User = get_user_model()


@pytest.mark.django_db
def test_daily_blitz_get_fallback_questions():
    client = APIClient()
    user = User.objects.create_user(
        email="blitz_student@example.com",
        password="Password123!",
        role="student",
    )
    client.force_authenticate(user=user)

    response = client.get("/api/v1/tests/daily-blitz/?subject=uzbek")
    assert response.status_code == 200
    data = response.json()

    assert data["subject"] == "uzbek"
    assert data["duration_seconds"] == 60
    assert data["total_questions"] == 5
    assert data["xp_reward"] == 25
    assert len(data["questions"]) == 5
    for q in data["questions"]:
        assert "id" in q
        assert "text" in q
        assert len(q["choices"]) > 0


@pytest.mark.django_db
def test_daily_blitz_post_and_streak_flame_increment():
    client = APIClient()
    user = User.objects.create_user(
        email="blitz_student2@example.com",
        password="Password123!",
        role="student",
    )
    client.force_authenticate(user=user)

    # 1. Fetch questions first
    get_res = client.get("/api/v1/tests/daily-blitz/?subject=uzbek")
    assert get_res.status_code == 200
    q_data = get_res.json()
    questions = q_data["questions"]

    # Provide choices for fallback questions
    answers = {}
    for q in questions:
        answers[str(q["id"])] = q["choices"][0]["id"]

    post_res = client.post(
        "/api/v1/tests/daily-blitz/",
        {"subject": "uzbek", "answers": answers},
        format="json",
    )
    assert post_res.status_code == 200
    res_data = post_res.json()

    assert res_data["ok"] is True
    assert res_data["total"] == 5
    assert res_data["xp_earned"] == 25
    assert "current_streak" in res_data
    assert "streak_days" in res_data
    assert res_data["streak_days"] >= 1

    # Verify profile current_streak in DB
    profile = Profile.objects.get(user=user)
    assert profile.current_streak >= 1


@pytest.mark.django_db
def test_daily_blitz_unauthenticated():
    client = APIClient()
    response = client.get("/api/v1/tests/daily-blitz/?subject=uzbek")
    assert response.status_code == 401
