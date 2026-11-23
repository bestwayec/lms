"""Ona tili topics: whitelisted per block, round-trip through the editor, weak-topic analysis from real answers."""

import pytest

from apps.accounts.models import User
from apps.tests import studio_service as svc
from apps.tests.models import StudentAnswer, TestAttempt
from apps.tests.services import SaveAnswerService, StartAttemptService, SubmitAttemptService


def _block(topic, n, start):
    return {
        "type": "mcq", "section": "GENERAL", "title": topic, "topic": topic,
        "questions": [
            {"number": start + i, "text": f"{topic} {i}", "options": ["a", "b", "c", "d"], "answer": "A"} for i in range(n)
        ],
    }


@pytest.mark.django_db
def test_topics_round_trip_and_weak_topic_breakdown():
    teacher = User.objects.create_user(email="top_t@example.com", password="p", role="teacher")
    payload = {"title": "Ona tili", "subject": "uzbek", "time_limit_minutes": 20,
               "blocks": [_block("imlo", 2, 1), _block("sintaksis", 2, 3), {**_block("x", 1, 5), "topic": "not-a-topic"}]}
    test = svc.save_test(teacher, payload)
    blocks = svc.load_blocks(test)
    assert [b["topic"] for b in blocks] == ["imlo", "sintaksis", ""]  # unknown topic dropped, not stored
    svc.publish_test(test)

    # Two students: both get every 'imlo' question right, every 'sintaksis' one wrong.
    for k in range(2):
        st = User.objects.create_user(email=f"top_s{k}@example.com", password="p", role="student")
        test.access_type = "PUBLIC"
        test.save(update_fields=["access_type"])
        att = StartAttemptService.execute(test_id=test.id, student=st)
        for q in test.questions.all():
            right = q.config.get("topic") == "imlo"
            choice = q.choices.get(is_correct=True) if right else q.choices.filter(is_correct=False).first()
            SaveAnswerService.execute(att.id, q.id, choice_ids=[choice.id], student=st)
        SubmitAttemptService.execute(att.id, st)

    analysis = svc.item_analysis(test)
    topics = {r["topic"]: r for r in analysis["topics"]}
    assert set(topics) == {"imlo", "sintaksis"}  # untagged question not guessed into a topic
    assert topics["imlo"]["accuracy"] == 100.0 and topics["imlo"]["possible"] == 4
    assert topics["sintaksis"]["accuracy"] == 0.0
    assert analysis["topics"][0]["topic"] == "sintaksis"  # weakest first
    assert TestAttempt.objects.filter(test=test).count() == 2 and StudentAnswer.objects.count() == 10


def test_topic_breakdown_ignores_empty_inputs():
    assert svc.topic_breakdown([]) == []
    assert svc.topic_breakdown([{"topic": "imlo", "correct": 0, "total": 0}]) == []
