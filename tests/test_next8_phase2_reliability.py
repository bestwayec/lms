"""Phase 02 tests — Exam Engine Reliability 2.0, N8-001, N8-002, revisions & session takeover."""

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.courses.models import Course
from apps.tests.models import (
    Choice,
    GapBlank,
    MatchingOption,
    MatchingPair,
    MatchingPrompt,
    Question,
    Test,
)
from apps.tests.serializers import _student_question_payload

User = get_user_model()


@pytest.mark.django_db
def test_n8_002_canonical_question_type_serialization():
    teacher = User.objects.create_user(email="t_n8002@example.com", password="StrongPassword123!", role="teacher")
    course = Course.objects.create(title="IELTS Course", teacher=teacher)
    test = Test.objects.create(title="CD Test", subject="english", course=course, status=Test.Status.PUBLISHED)

    q_gap = Question.objects.create(
        test=test,
        text="The capital is (1) ____",
        question_type=Question.QuestionType.INLINE_GAP_FILL,
        position=1,
    )
    GapBlank.objects.create(question=q_gap, position=1, answer_text="London")

    q_match = Question.objects.create(
        test=test,
        text="Match headings",
        question_type=Question.QuestionType.MATCHING,
        position=2,
    )
    p1 = MatchingPrompt.objects.create(question=q_match, text="Paragraph A", position=1)
    o1 = MatchingOption.objects.create(question=q_match, text="Heading I", position=1)
    MatchingPair.objects.create(prompt=p1, correct_option=o1)

    gap_payload = _student_question_payload(q_gap, shuffle_choices=False)
    assert gap_payload["gaps"] == [{"position": 1}]
    assert "gap_answers" in gap_payload

    match_payload = _student_question_payload(q_match, shuffle_choices=False)
    assert len(match_payload["prompts"]) == 1
    assert len(match_payload["matching_options"]) == 1
    assert "matching" in match_payload


@pytest.mark.django_db
def test_monotonic_revision_and_session_takeover_and_idempotent_submit():
    teacher = User.objects.create_user(email="t_rel@example.com", password="StrongPassword123!", role="teacher")
    student = User.objects.create_user(email="s_rel@example.com", password="StrongPassword123!", role="student")
    course = Course.objects.create(title="Reliability English", teacher=teacher)
    test = Test.objects.create(
        title="Reliability Mock",
        subject="english",
        course=course,
        status=Test.Status.PUBLISHED,
        is_strict_mode=True,
    )
    q1 = Question.objects.create(test=test, text="Choose A or B", question_type=Question.QuestionType.SINGLE_CHOICE, position=1)
    c_a = Choice.objects.create(question=q1, text="Option A", is_correct=True, position=1)
    c_b = Choice.objects.create(question=q1, text="Option B", is_correct=False, position=2)

    client = APIClient()
    client.force_authenticate(user=student)

    start = client.post(f"/api/tests/{test.id}/start/", {"mode": "strict"}, format="json")
    assert start.status_code in (200, 201)
    attempt_id = start.data["id"] if "id" in start.data else start.data["attempt_id"]
    token_1 = start.data["session_token"]
    assert token_1

    # Save rev 5 succeeds
    save_ok = client.post(
        f"/api/tests/attempts/{attempt_id}/save-answer/",
        {"question_id": q1.id, "choice_ids": [c_a.id], "revision": 5, "session_token": token_1},
        format="json",
    )
    assert save_ok.status_code == 200
    assert save_ok.data["revision"] == 5
    assert save_ok.data["attempt_last_revision"] == 5

    # Stale write rev 2 fails with 409 STALE_REVISION
    save_stale = client.post(
        f"/api/tests/attempts/{attempt_id}/save-answer/",
        {"question_id": q1.id, "choice_ids": [c_b.id], "revision": 2, "session_token": token_1},
        format="json",
    )
    assert save_stale.status_code == 409
    assert save_stale.data["code"] == "STALE_REVISION"
    assert save_stale.data["server_revision"] == 5

    # Session takeover rotates lease
    takeover = client.post(f"/api/tests/attempts/{attempt_id}/session-takeover/", {}, format="json")
    assert takeover.status_code == 200
    token_2 = takeover.data["session_token"]
    assert token_2 != token_1

    # Old token blocked with 409 SESSION_TAKEN_OVER
    old_tab = client.post(
        f"/api/tests/attempts/{attempt_id}/save-answer/",
        {"question_id": q1.id, "choice_ids": [c_b.id], "revision": 6, "session_token": token_1},
        format="json",
    )
    assert old_tab.status_code == 409
    assert old_tab.data["code"] == "SESSION_TAKEN_OVER"

    # New token succeeds
    new_tab = client.post(
        f"/api/tests/attempts/{attempt_id}/save-answer/",
        {"question_id": q1.id, "choice_ids": [c_a.id], "revision": 6, "session_token": token_2},
        format="json",
    )
    assert new_tab.status_code == 200
    assert new_tab.data["revision"] == 6

    # Idempotent submit with idempotency_key
    s1 = client.post(
        f"/api/tests/attempts/{attempt_id}/submit/",
        {"idempotency_key": "idem-key-123"},
        format="json",
    )
    assert s1.status_code == 200
    s2 = client.post(
        f"/api/tests/attempts/{attempt_id}/submit/",
        {"idempotency_key": "idem-key-123"},
        format="json",
    )
    assert s2.status_code == 200


@pytest.mark.django_db
def test_n8_001_report_violation_auto_submit_returns_valid_result_id():
    teacher = User.objects.create_user(email="t_v@example.com", password="StrongPassword123!", role="teacher")
    student = User.objects.create_user(email="s_v@example.com", password="StrongPassword123!", role="student")
    course = Course.objects.create(title="Strict English", teacher=teacher)
    test = Test.objects.create(
        title="Strict Exam",
        subject="english",
        course=course,
        status=Test.Status.PUBLISHED,
        is_strict_mode=True,
    )
    q1 = Question.objects.create(test=test, text="Q1", question_type=Question.QuestionType.SINGLE_CHOICE, position=1)
    Choice.objects.create(question=q1, text="True", is_correct=True, position=1)

    client = APIClient()
    client.force_authenticate(user=student)
    start = client.post(f"/api/tests/{test.id}/start/", {"mode": "strict"}, format="json")
    attempt_id = start.data["id"] if "id" in start.data else start.data["attempt_id"]

    r1 = client.post(f"/api/tests/attempts/{attempt_id}/report-violation/", {"type": "tab_switch"}, format="json")
    r2 = client.post(f"/api/tests/attempts/{attempt_id}/report-violation/", {"type": "tab_switch"}, format="json")
    r3 = client.post(f"/api/tests/attempts/{attempt_id}/report-violation/", {"type": "tab_switch"}, format="json")
    assert r1.status_code == 200 and not r1.data["terminated"]
    assert r2.status_code == 200 and not r2.data["terminated"]
    assert r3.status_code == 200
    assert r3.data["terminated"] is True
    assert r3.data["result_id"] is not None
