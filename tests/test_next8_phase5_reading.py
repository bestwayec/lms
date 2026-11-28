"""Phase 05 tests — Reading Engine: stimulusRef identity separation & evidence review."""

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.tests.package_service import import_exam_package

User = get_user_model()


@pytest.mark.django_db
def test_reading_stimulus_ref_identity_separation_and_review_evidence():
    teacher = User.objects.create_user(email="t_read@example.com", password="StrongPassword123!", role="teacher")
    student = User.objects.create_user(email="s_read@example.com", password="StrongPassword123!", role="student")

    shared_text = "Section 1: Renewable microgrids reduce transmission losses across remote towns."
    pkg = {
        "schemaVersion": "1.0",
        "title": "Reading Stimulus Separation Mock",
        "subject": "english",
        "examType": "ielts_academic",
        "assessmentCategory": "topic_test",
        "timeLimitMinutes": 60,
        "sections": [
            {
                "code": "READING",
                "name": "Reading",
                "durationMinutes": 60,
                "parts": [
                    {
                        "number": "1",
                        "partNumber": 1,
                        "title": "Passage Set",
                        "groups": [
                            {
                                "title": "Group A",
                                "stimulusRef": "passage_alpha",
                                "contentLayout": "passage",
                                "passage": {
                                    "title": "Section 1 — Energy",
                                    "stimulusRef": "passage_alpha",
                                    "content": shared_text,
                                },
                                "questions": [
                                    {
                                        "number": 1,
                                        "questionType": "TRUE_FALSE_NOT_GIVEN",
                                        "text": "Microgrids lower transmission losses.",
                                        "evidenceText": "Renewable microgrids reduce transmission losses across remote towns.",
                                        "options": [
                                            {"text": "TRUE", "isCorrect": True},
                                            {"text": "FALSE", "isCorrect": False},
                                            {"text": "NOT GIVEN", "isCorrect": False},
                                        ],
                                    }
                                ],
                            },
                            {
                                "title": "Group B",
                                "stimulusRef": "passage_beta",
                                "contentLayout": "passage",
                                "passage": {
                                    "title": "Section 1 — Energy (Duplicate Heading Boundary)",
                                    "stimulusRef": "passage_beta",
                                    "content": shared_text,
                                },
                                "questions": [
                                    {
                                        "number": 2,
                                        "questionType": "TRUE_FALSE_NOT_GIVEN",
                                        "text": "Remote towns benefit from microgrids.",
                                        "evidenceText": "reduce transmission losses across remote towns.",
                                        "options": [
                                            {"text": "TRUE", "isCorrect": True},
                                            {"text": "FALSE", "isCorrect": False},
                                            {"text": "NOT GIVEN", "isCorrect": False},
                                        ],
                                    }
                                ],
                            },
                        ],
                    }
                ],
            }
        ],
    }

    test_obj = import_exam_package(teacher, pkg)
    test_obj.status = test_obj.Status.PUBLISHED
    test_obj.save()

    # Two distinct ReadingPassage objects despite identical text because stimulusRef differs!
    passages = list(test_obj.passages.order_by("order"))
    assert len(passages) == 2
    assert {p.stimulus_ref for p in passages} == {"passage_alpha", "passage_beta"}

    client = APIClient()
    client.force_authenticate(user=student)
    start = client.post(f"/api/tests/{test_obj.id}/start/", {"mode": "practice"}, format="json")
    attempt_id = start.data["id"]

    attempt_res = client.get(f"/api/tests/attempts/{attempt_id}/")
    assert attempt_res.status_code == 200
    assert len(attempt_res.data["passages"]) == 2
    assert {p["stimulus_ref"] for p in attempt_res.data["passages"]} == {"passage_alpha", "passage_beta"}
    # Student exam view NEVER leaks evidenceText before completion
    for q in attempt_res.data["questions"]:
        assert "evidence_text" not in q
        assert "evidence" not in q

    # Answer both questions and submit
    q1, q2 = attempt_res.data["questions"][0], attempt_res.data["questions"][1]
    client.post(
        f"/api/tests/attempts/{attempt_id}/save-answer/",
        {"question_id": q1["id"], "choice_ids": [q1["choices"][0]["id"]]},
        format="json",
    )
    client.post(
        f"/api/tests/attempts/{attempt_id}/save-answer/",
        {"question_id": q2["id"], "choice_ids": [q2["choices"][1]["id"]]},
        format="json",
    )
    sub = client.post(f"/api/tests/attempts/{attempt_id}/submit/", {}, format="json")
    assert sub.status_code == 200
    result_id = sub.data["result"]["result_id"]

    review = client.get(f"/api/results/{result_id}/detail/")
    assert review.status_code == 200
    rev_qs = review.data["question_details"]
    assert len(rev_qs) == 2
    assert rev_qs[0]["stimulus_ref"] == "passage_alpha"
    assert "Renewable microgrids reduce transmission losses" in rev_qs[0]["evidence"]
    assert rev_qs[1]["stimulus_ref"] == "passage_beta"
