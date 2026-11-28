"""Phase 06-07 tests — Writing Studio 3.0, Evidence Offsets, Calibration & English Teacher Review."""

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APIClient

from apps.core.ai_gateway import compute_calibrated_stats, verify_evidence_items
from apps.courses.models import StudentGroup
from apps.essays.models import EssaySubmission, EssayTopic

User = get_user_model()


def test_evidence_offset_grounding_and_calibration_math():
    source = (
        "Renewable microgrids cut diesel reliance. Furthermore, solar storage keeps clinics powered. "
        "However, solar storage also lowers outage costs during storms."
    )
    items = verify_evidence_items(
        [
            {"id": 1, "quote": "solar storage", "reason": "Clinics context"},
            {"id": 2, "quote": "solar storage", "reason": "Storm outage costs"},
            {"id": 3, "quote": "fabricated quote not in text"},
        ],
        source,
    )
    assert items[0]["quote_verified"] is True
    s0, e0 = items[0]["start_offset"], items[0]["end_offset"]
    assert source[s0:e0] == "solar storage"
    assert items[1]["quote_verified"] is True
    s1, e1 = items[1]["start_offset"], items[1]["end_offset"]
    assert source[s1:e1] == "solar storage"
    assert s1 > s0  # Repeated phrase resolves distinctly
    assert items[2]["quote_verified"] is False
    assert items[2]["start_offset"] == -1

    # Unicode curly apostrophe & whitespace normalization grounding
    uni_source = "Children\u2019s   access\u00a0to\nclean public libraries improves literacy."
    uni_items = verify_evidence_items([{"id": 4, "quote": "Children's access to clean public libraries"}], uni_source)
    assert uni_items[0]["quote_verified"] is True
    assert uni_source[uni_items[0]["start_offset"] : uni_items[0]["end_offset"]].startswith("Children")

    cal = compute_calibrated_stats(
        [
            {"predicted": 6.5, "expected": 6.5},
            {"predicted": 7.0, "expected": 6.5},
            {"predicted": 5.5, "expected": 6.0},
        ]
    )
    assert cal["count"] == 3
    assert cal["within_half_band_pct"] == 100.0
    assert cal["mae"] <= 0.5


@pytest.mark.django_db
def test_writing_studio_ielts_and_multilevel_grading_no_fake_scores_and_teacher_review():
    teacher = User.objects.create_user(email="w_teacher@example.com", password="StrongPassword123!", role="teacher")
    student = User.objects.create_user(email="w_student@example.com", password="StrongPassword123!", role="student")

    client = APIClient()
    client.force_authenticate(user=student)

    # Insufficient text (<10 words) rejected honestly without inventing a band
    short_res = client.post(
        "/api/v1/essays/ielts/grade/",
        {"task_type": "ielts_task2", "topic_title": "Cities", "essay_text": "Too short only four"},
        format="json",
    )
    assert short_res.status_code == 400
    assert short_res.data["code"] == "rejected"

    # Full IELTS Task 2 response grades with grounded char offsets
    essay_text = (
        "Public investment in reliable railways reduces urban gridlock and lowers carbon emissions significantly. "
        "Firstly, clean electric transit encourages commuters to leave private cars at home during peak hours. "
        "Secondly, affordable regional connections expand employment access for rural households across the country.\n\n"
        "In conclusion, modernizing public transport yields durable economic and environmental rewards for cities."
    )
    # When no AI key and mock mode off -> honest 503 with zero invented band
    with override_settings(ESSAY_AI_MOCK_MODE=False, DEEPSEEK_API_KEY="", OPENROUTER_API_KEY=""):
        unavail = client.post(
            "/api/v1/essays/ielts/grade/",
            {"task_type": "ielts_task2", "topic_title": "Public Transport", "essay_text": essay_text},
            format="json",
        )
        assert unavail.status_code == 503
        assert unavail.data["code"] == "not_graded"

    with override_settings(ESSAY_AI_MOCK_MODE=True):
        ok_res = client.post(
            "/api/v1/essays/ielts/grade/",
            {"task_type": "ielts_task2", "topic_title": "Public Transport", "essay_text": essay_text},
            format="json",
        )
        assert ok_res.status_code == 200
        assert ok_res.data["ok"] is True
        assert isinstance(ok_res.data["criteria"], list) and len(ok_res.data["criteria"]) == 4
        first_crit = ok_res.data["criteria"][0]
        assert first_crit["quote_verified"] is True
        s, e = first_crit["start_offset"], first_crit["end_offset"]
        assert essay_text[s:e] == first_crit["quote"]

        # Multi-level Task 1.2 endpoint contract (fresh student quota)
        ml_student = User.objects.create_user(email="w_ml_student@example.com", password="StrongPassword123!", role="student")
        ml_client = APIClient()
        ml_client.force_authenticate(user=ml_student)

        # Draft save & restore workflow in Writing Studio 3.0
        draft_save = ml_client.post(
            "/api/v1/essays/ielts/draft/",
            {
                "task_type": "ielts_gt_letter",
                "topic_title": "Library extension request",
                "essay_text": "Dear Librarian, I am writing to request a two-week extension.",
            },
            format="json",
        )
        assert draft_save.status_code == 200
        draft_get = ml_client.get("/api/v1/essays/ielts/draft/?task_type=ielts_gt_letter")
        assert draft_get.status_code == 200
        assert "two-week extension" in draft_get.data["draft"]["essay_text"]

        ml_res = ml_client.post(
            "/api/v1/essays/ielts/grade/",
            {"task_type": "multilevel_1_2", "topic_title": "Formal Request", "essay_text": essay_text},
            format="json",
        )
        assert ml_res.status_code == 200
        assert ml_res.data["task_type"] == "multilevel_1_2"
        assert ml_res.data["is_estimate"] is True
        assert isinstance(ml_res.data.get("corrections"), list) and len(ml_res.data["corrections"]) >= 1
        assert ml_res.data["corrections"][0]["quote_verified"] is True
        assert isinstance(ml_res.data.get("vocabulary_upgrades"), list) and len(ml_res.data["vocabulary_upgrades"]) >= 1
        assert bool(ml_res.data.get("next_level_example"))

    # N8-004: Teacher reviews English IELTS essay with 1.0..9.0 rubric
    sub = EssaySubmission.objects.get(id=ok_res.data["submission_id"])
    other_teacher = User.objects.create_user(email="w_other_teacher@example.com", password="StrongPassword123!", role="teacher")
    group = StudentGroup.objects.create(teacher=teacher, name="IELTS Cohort A", subject="english")
    group.students.add(student)

    # Unrelated teacher is blocked (RBAC isolation)
    other_client = APIClient()
    other_client.force_authenticate(user=other_teacher)
    blocked_res = other_client.get(f"/api/v1/essays/teacher/{sub.id}/")
    assert blocked_res.status_code == 403

    t_client = APIClient()
    t_client.force_authenticate(user=teacher)
    detail_res = t_client.get(f"/api/v1/essays/teacher/{sub.id}/")
    assert detail_res.status_code == 200
    assert detail_res.data["rubric_scale"] == "ielts"
    assert detail_res.data["display_max"] == 9

    review_res = t_client.post(
        f"/api/v1/essays/teacher/{sub.id}/review/",
        {"criteria_scores": {"1": 7.5, "2": 7.0, "3": 7.5, "4": 6.5}, "teacher_comments": "Solid cohesion."},
        format="json",
    )
    assert review_res.status_code == 200
    assert review_res.data["final_score"] == 7.0  # (7.5+7+7.5+6.5)/4 = 7.125 -> nearest 0.5 = 7.0
