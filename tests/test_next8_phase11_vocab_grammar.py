"""Phase 11 tests — Vocabulary Exam 3.0 (answer-safe) & Grammar Studio across 10 topics."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.essays.models import EssaySubmission
from apps.vocabulary.models import GrammarCategory, StudentWordMistake

User = get_user_model()


@pytest.mark.django_db
def test_answer_safe_vocab_quiz_and_flashcard_deck():
    student = User.objects.create_user(email="voc_student@example.com", password="StrongPassword123!", role="student")
    StudentWordMistake.objects.create(
        student=student,
        word="resilient",
        translation_uz="chidamli, moslashuvchan",
        definition="The resilient grid recovered after the storm.",
        mistake_count=2,
    )
    StudentWordMistake.objects.create(
        student=student,
        word="mitigate",
        translation_uz="yumshatmoq, kamaytirmoq",
        definition="Trees mitigate heat in dense neighborhoods.",
        mistake_count=1,
    )

    client = APIClient()
    client.force_authenticate(user=student)

    deck_res = client.get("/api/v1/vocabulary/deck/")
    assert deck_res.status_code == 200
    assert deck_res.data["due_count"] == 2
    assert len(deck_res.data["cards"]) == 2

    quiz_res = client.get("/api/v1/vocabulary/student-quiz/")
    assert quiz_res.status_code == 200
    assert quiz_res.data["status"] == "active"
    assert len(quiz_res.data["questions"]) == 2
    for q in quiz_res.data["questions"]:
        assert "correct_answer" not in q  # Answer-safe: key NEVER sent to student client

    first_q = quiz_res.data["questions"][0]
    expected_ans = "chidamli, moslashuvchan" if first_q["type"] in ("listen_choose", "context_meaning") else "resilient"
    sub_res = client.post(
        "/api/v1/vocabulary/student-quiz/submit/",
        {"id": first_q["id"], "word": "resilient", "type": first_q["type"], "answer": expected_ans},
        format="json",
    )
    assert sub_res.status_code == 200
    assert sub_res.data["is_correct"] is True
    assert sub_res.data["streak"] == 1


@pytest.mark.django_db
def test_grammar_studio_10_topics_recommendations_and_submission():
    student = User.objects.create_user(email="gram_student@example.com", password="StrongPassword123!", role="student")
    EssaySubmission.objects.create(
        student=student,
        essay_text="If governments invest in rails, commuting times would improve.",
        word_count=10,
        status=EssaySubmission.Status.GRADED,
        summary="Check conditional clause tense agreement.",
        raw_result={"criteria": [{"id": 4, "reason": "Conditional sentence mismatch", "errors": ["conditional", "tense"]}]},
    )

    client = APIClient()
    client.force_authenticate(user=student)

    topics_res = client.get("/api/v1/vocabulary/grammar/topics/")
    assert topics_res.status_code == 200
    assert GrammarCategory.objects.count() == 10
    assert len(topics_res.data["topics"]) == 10
    rec_slugs = {r["slug"] for r in topics_res.data["recommended"]}
    assert "conditionals" in rec_slugs or "tenses" in rec_slugs

    detail_res = client.get("/api/v1/vocabulary/grammar/topics/conditionals/")
    assert detail_res.status_code == 200
    ex = detail_res.data["exercises"][0]
    assert "correct_answer" not in ex

    sub_res = client.post(
        "/api/v1/vocabulary/grammar/submit/",
        {"exercise_id": ex["id"], "answer": "would fall"},
        format="json",
    )
    assert sub_res.status_code == 200
    assert sub_res.data["is_correct"] is True
    assert sub_res.data["explanation"]
