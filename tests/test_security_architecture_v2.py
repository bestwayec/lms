"""Comprehensive Security & High-Load Architecture Audit Tests (v1.99.0).

Covers:
1. 0-Day Answer Key Leak Prevention (_student_question_payload & SocraticTutorExplainView).
2. BOLA / IDOR Protection on test attempts and Socratic Tutor result_id.
3. Privilege Escalation & Stored XSS Sanitization on ProfileUpdateSerializer.
4. Race Condition / Idempotency on PaymentReceipt approval.
5. Telegram WebApp HMAC-SHA256 & 24h Replay Protection + Webhook Secret Token.
6. Redis Cache & Cache Invalidation on Mock Exam Leaderboard.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from decimal import Decimal
from urllib.parse import urlencode

import pytest
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.accounts.serializers import ProfileUpdateSerializer
from apps.core.validators import sanitize_text_xss
from apps.courses.models import Course
from apps.payments.models import PaymentHistory, PaymentReceipt, SubscriptionPlan
from apps.payments.services import approve_payment_receipt
from apps.results.models import Result
from apps.telegram_app.services import TelegramMiniAppService
from apps.tests.mock_service import get_mock_leaderboard, invalidate_mock_leaderboard_cache
from apps.tests.models import Choice, Question, Test, TestAttempt
from apps.tests.serializers import _student_question_payload


@pytest.mark.django_db
class TestZeroDayAnswerKeyProtection:
    def test_student_question_payload_strips_answer_keys_and_config_secrets(self):
        teacher = User.objects.create_user(
            email="sec_teacher_1@grandec.uz", password="Password123!", role="teacher"
        )
        course = Course.objects.create(title="Security Course", teacher=teacher)
        test = Test.objects.create(
            title="Zero Day Check Test",
            course=course,
            created_by=teacher,
            is_active=True,
        )
        q = Question.objects.create(
            test=test,
            text="What is the capital of Uzbekistan?",
            question_type="single",
            explanation="Tashkent is the capital city.",
            config={
                "number": 1,
                "correct_answer": "A",
                "correct_text": "Tashkent",
                "accepted_answers": ["Tashkent", "Toshkent"],
                "explanation": "Secret explanation in config",
                "evidence": "Paragraph 2",
                "answer_key": "A",
            },
        )
        Choice.objects.create(question=q, text="Tashkent", is_correct=True)
        Choice.objects.create(question=q, text="Samarkand", is_correct=False)

        payload = _student_question_payload(q, shuffle_choices=False)

        # Must never expose explanation or answer keys during an active attempt
        assert "explanation" not in payload
        assert "correct_answer" not in payload
        assert payload["config"] == {"number": 1}
        for choice in payload["choices"]:
            assert "is_correct" not in choice

    def test_socratic_tutor_blocks_student_with_active_attempt_and_blocks_idor(self):
        teacher = User.objects.create_user(
            email="sec_teacher_2@grandec.uz", password="Password123!", role="teacher"
        )
        student_a = User.objects.create_user(
            email="sec_student_a@grandec.uz", password="Password123!", role="student"
        )
        student_b = User.objects.create_user(
            email="sec_student_b@grandec.uz", password="Password123!", role="student"
        )
        course = Course.objects.create(title="Tutor Sec Course", teacher=teacher)
        test = Test.objects.create(
            title="Tutor Sec Test", course=course, created_by=teacher, is_active=True
        )
        q = Question.objects.create(
            test=test, text="2 + 2 = ?", question_type="single", explanation="4"
        )
        c_right = Choice.objects.create(question=q, text="4", is_correct=True)
        c_wrong = Choice.objects.create(question=q, text="5", is_correct=False)

        # Student A has an active IN_PROGRESS attempt -> Socratic Tutor must reject with 403
        active_attempt = TestAttempt.objects.create(
            student=student_a,
            test=test,
            status=TestAttempt.Status.IN_PROGRESS,
        )
        client_a = APIClient()
        client_a.force_authenticate(user=student_a)
        res_active = client_a.post(
            "/api/tests/socratic-tutor/",
            {"question_id": q.id, "selected_choice_id": c_wrong.id},
            format="json",
        )
        assert res_active.status_code == 403
        assert res_active.data.get("code") == "active_attempt_forbidden"

        # Complete Student A's attempt and create a Result for Student A
        active_attempt.status = TestAttempt.Status.COMPLETED
        active_attempt.save(update_fields=["status"])
        result_a = Result.objects.create(
            attempt=active_attempt,
            student=student_a,
            test=test,
            course=course,
            total_questions=1,
            correct_answers=0,
            wrong_answers=1,
            unanswered=0,
            score=Decimal("0.00"),
            max_score=Decimal("1.00"),
            percentage=Decimal("0.00"),
            is_passed=False,
            time_taken_seconds=25,
        )

        # Student B tries to query Socratic Tutor using Student A's result_id (IDOR attempt)
        client_b = APIClient()
        client_b.force_authenticate(user=student_b)
        res_idor = client_b.post(
            "/api/tests/socratic-tutor/",
            {"question_id": q.id, "result_id": result_a.id},
            format="json",
        )
        assert res_idor.status_code == 403
        assert c_right.is_correct is True


@pytest.mark.django_db
class TestPrivilegeEscalationAndXssHardening:
    def test_profile_update_blocks_privilege_escalation_and_sanitizes_xss(self):
        student = User.objects.create_user(
            email="priv_student@grandec.uz",
            password="Password123!",
            role="student",
            first_name="Old",
        )
        malicious_payload = {
            "first_name": "<script>alert(1)</script>O'tkirbek",
            "last_name": '<img src=x onerror="alert(2)">G\'ulomov',
            "role": "admin",
            "is_staff": True,
            "is_superuser": True,
            "is_pro": True,
            "plan": "PRO",
        }
        serializer = ProfileUpdateSerializer(
            instance=student, data=malicious_payload, partial=True
        )
        assert serializer.is_valid(), serializer.errors
        updated = serializer.save()

        updated.refresh_from_db()
        assert updated.role == "student"
        assert updated.is_staff is False
        assert updated.is_superuser is False
        assert "<script>" not in updated.first_name
        assert "onerror" not in updated.last_name
        assert updated.first_name == "O'tkirbek"
        assert updated.last_name == "G'ulomov"

    def test_sanitize_text_xss_preserves_uzbek_and_math_while_stripping_payloads(self):
        sample = (
            "O'zbekiston g'olib! H₂SO₄ konsentratsiyasi x < 5 mol/l. "
            "<script>window.location='http://evil.com'</script>"
            "<iframe src='javascript:alert(1)'></iframe>"
        )
        cleaned = sanitize_text_xss(sample)
        assert "O'zbekiston g'olib!" in cleaned
        assert "H₂SO₄ konsentratsiyasi x < 5 mol/l." in cleaned
        assert "<script" not in cleaned
        assert "<iframe" not in cleaned
        assert "javascript:" not in cleaned


@pytest.mark.django_db
class TestPaymentReceiptRaceConditionIdempotency:
    def test_approve_payment_receipt_is_idempotent_under_repeated_calls(self):
        admin_user = User.objects.create_user(
            email="pay_admin@grandec.uz", password="Password123!", role="admin", is_staff=True
        )
        student = User.objects.create_user(
            email="pay_student@grandec.uz", password="Password123!", role="student"
        )
        plan, _ = SubscriptionPlan.objects.get_or_create(
            plan_type=SubscriptionPlan.PlanType.PRO,
            defaults={
                "name": "PRO Monthly",
                "description": "Pro plan",
                "price_monthly": Decimal("49000.00"),
            },
        )
        receipt = PaymentReceipt.objects.create(
            user=student,
            plan=plan,
            amount=Decimal("49000.00"),
            status=PaymentReceipt.Status.PENDING,
        )

        sub1 = approve_payment_receipt(receipt, admin_user=admin_user)
        sub2 = approve_payment_receipt(receipt, admin_user=admin_user)

        assert sub1.id == sub2.id
        assert (
            PaymentHistory.objects.filter(
                user=student, payment_id=f"RECEIPT-{receipt.id}"
            ).count()
            == 1
        )


@pytest.mark.django_db
class TestTelegramHmacAndWebhookSecurity:
    @override_settings(TELEGRAM_BOT_TOKEN="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11")
    def test_telegram_webapp_hmac_accepts_valid_and_rejects_tampered_or_stale(self):
        bot_token = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
        secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()

        def sign_payload(auth_date_val: int, user_id: int = 998877) -> str:
            params = {
                "auth_date": str(auth_date_val),
                "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
                "user": json.dumps({"id": user_id, "first_name": "Sardor"}),
            }
            data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
            sig = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
            params["hash"] = sig
            return urlencode(params)

        now_ts = int(time.time())
        valid_init_data = sign_payload(now_ts)
        parsed = TelegramMiniAppService.validate_init_data(valid_init_data)
        assert parsed is not None
        assert parsed["id"] == 998877

        # Tampered signature must be rejected
        tampered = valid_init_data.replace("Sardor", "Hacker")
        assert TelegramMiniAppService.validate_init_data(tampered) is None

        # Replay attack (> 86400s old) must be rejected
        stale_init_data = sign_payload(now_ts - 90000)
        assert TelegramMiniAppService.validate_init_data(stale_init_data) is None

    @override_settings(TELEGRAM_WEBHOOK_SECRET="top-secret-webhook-token-2026")
    def test_telegram_webhook_enforces_secret_token_header(self):
        client = APIClient()
        res_missing = client.post(
            "/api/notifications/telegram/webhook/",
            {"update_id": 1},
            format="json",
        )
        assert res_missing.status_code in (401, 403)

        res_wrong = client.post(
            "/api/notifications/telegram/webhook/",
            {"update_id": 1},
            format="json",
            HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="wrong-token",
        )
        assert res_wrong.status_code in (401, 403)


@pytest.mark.django_db
class TestHighLoadMockLeaderboardCaching:
    def test_mock_leaderboard_caches_and_invalidates_cleanly(self):
        teacher = User.objects.create_user(
            email="cache_teacher@grandec.uz", password="Password123!", role="teacher"
        )
        course = Course.objects.create(title="Cache Course", teacher=teacher)
        test = Test.objects.create(
            title="Cache Mock Test", course=course, created_by=teacher, is_active=True
        )
        cache_key = f"grandec:mock_leaderboard_v1:{test.id}"
        cache.delete(cache_key)

        board = get_mock_leaderboard(test.id)
        assert board["ranking"] == []
        assert cache.get(cache_key) is not None

        invalidate_mock_leaderboard_cache(test.id)
        assert cache.get(cache_key) is None
