"""Study plan persistence and public discovery contract regressions."""
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient


@pytest.fixture
def student():
    return get_user_model().objects.create_user(email="quality@example.test", password="local-test-only")


@pytest.mark.django_db
@pytest.mark.parametrize("payload", [
    {"goal_questions": -5}, {"goal_questions": "bad"},
    {"daily_goal_minutes": 0}, {"active_subject": "unknown"},
    {"goal_questions": 15, "daily_goal_questions": 50},
])
def test_rejected_onboarding_does_not_complete_profile(student, payload):
    client = APIClient()
    client.force_authenticate(student)
    response = client.post("/api/auth/onboarding/", payload, format="json")
    assert response.status_code == 400
    student.profile.refresh_from_db()
    assert student.profile.onboarding_completed is False


@pytest.mark.django_db
def test_plan_save_matches_me_and_dashboard_after_refresh(student):
    client = APIClient()
    client.force_authenticate(student)
    payload = {"target_exam": "ielts", "active_subject": "english", "target_grade": "Band 7.0",
               "goal_questions": 50, "daily_goal_minutes": 50, "reminder_slot": "morning"}
    response = client.post("/api/auth/onboarding/", payload, format="json")
    assert response.status_code == 200
    saved = response.json()["user"]
    restored = client.get("/api/auth/me/").json()
    for key in ("active_subject", "target_exam", "target_grade", "daily_goal_minutes", "reminder_slot", "onboarding_completed"):
        assert saved[key] == restored[key]
    assert restored["active_subject"] == "english"
    assert restored["reminder_slot"] == "morning"
    assert client.get("/api/v1/dashboard/?subject=english").json()["daily_goal"]["goal_questions"] == 50


@pytest.mark.django_db
def test_public_catalogue_does_not_expose_private_billing():
    client = APIClient()
    response = client.get("/api/v1/billing/plans/")
    assert response.status_code == 200
    assert response.json()["my_plan_id"] is None
    assert all(plan["is_public"] for plan in response.json()["results"])
    for path in ("/api/v1/billing/my/", "/api/v1/billing/entitlement/"):
        assert client.get(path).status_code in (401, 403)
