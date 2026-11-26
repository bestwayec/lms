"""Phase 13-14 tests — Telegram English Center (Student/Teacher RBAC & Fallback) & Admin AI Cost Control."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.core.ai_gateway import record_ai_usage
from apps.courses.models import StudentGroup
from apps.essays.models import EssaySubmission, EssayTopic
from apps.notifications.bot.english_commands import build_english_bot_payload
from apps.speaking.models import SpeakingSubmission, SpeakingTopic

User = get_user_model()


@pytest.mark.django_db
def test_telegram_english_hub_student_and_teacher_rbac_and_bot_payload():
    teacher = User.objects.create_user(email="tg_teacher@example.com", password="StrongPassword123!", role="teacher")
    student = User.objects.create_user(email="tg_student@example.com", password="StrongPassword123!", role="student")
    group = StudentGroup.objects.create(teacher=teacher, name="TG English Group", subject="english")
    group.students.add(student)

    topic_w = EssayTopic.objects.create(title="Urban Parks", subject="english", rubric_type="ielts_task2", word_limit_min=250)
    EssaySubmission.objects.create(
        student=student, topic=topic_w, essay_text="Parks improve air.", word_count=3,
        max_score=9, status=EssaySubmission.Status.PENDING_TEACHER,
    )
    topic_s = SpeakingTopic.objects.create(title="Hobbies", part=SpeakingTopic.PartChoice.PART1, prompt="Describe your hobby.")
    SpeakingSubmission.objects.create(
        user=student, topic=topic_s, teacher_review_requested=True, status=SpeakingSubmission.Status.PENDING_TEACHER
    )

    # Student TMA & Bot payload
    s_client = APIClient()
    s_client.force_authenticate(user=student)
    s_res = s_client.get("/tma/api/english/")
    assert s_res.status_code == 200
    assert s_res.data["role"] == "student"
    assert s_res.data["full_mock_web_only"] is True
    assert "/english" in s_res.data["web_fallback_urls"]["center"]

    # Teacher TMA & Bot payload
    t_client = APIClient()
    t_client.force_authenticate(user=teacher)
    t_res = t_client.get("/tma/api/english/")
    assert t_res.status_code == 200
    assert t_res.data["role"] == "teacher"
    assert t_res.data["pending_writing"] == 1
    assert t_res.data["pending_speaking"] == 1

    bot_payload = build_english_bot_payload(teacher)
    assert bot_payload["pending_writing"] == 1


@pytest.mark.django_db
def test_admin_ai_cost_control_endpoint_rbac_and_metrics():
    student = User.objects.create_user(email="ai_student@example.com", password="StrongPassword123!", role="student")
    admin = User.objects.create_user(email="ai_admin@example.com", password="StrongPassword123!", role="admin", is_staff=True)

    s_client = APIClient()
    s_client.force_authenticate(user=student)
    assert s_client.get("/api/v1/panel/ai-metrics/").status_code == 403

    record_ai_usage(feature="essay_ielts", model="deepseek/deepseek-r1-0528", tokens_in=400, tokens_out=250, cost_usd=0.0021, latency_ms=850.0, success=True)
    record_ai_usage(feature="speaking", model="fish-audio", tokens_in=100, tokens_out=80, cost_usd=0.0005, latency_ms=420.0, success=True)

    a_client = APIClient()
    a_client.force_authenticate(user=admin)
    res = a_client.get("/api/v1/panel/ai-metrics/")
    assert res.status_code == 200
    assert res.data["total_calls"] >= 2
    assert res.data["total_cost_usd"] >= 0.0026
    assert "essay_ielts" in res.data["features"]
    assert "speaking" in res.data["features"]
