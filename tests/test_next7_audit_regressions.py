"""Release-audit regression tests for TMA test CSRF/submit, group idempotency, and bot callback safety."""

from __future__ import annotations

from unittest.mock import AsyncMock

from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.courses.models import Course, StudentGroup
from apps.notifications.bot.group_assistant import group_assistant_callback_handler
from apps.notifications.bot.handlers import callback_handler, newmock_handler
from apps.tests.models import Choice, Question, Test
from tests.test_next7_phase1_api_and_csrf import _signed_init_data
from tests.test_next7_phase8_bot_roles import _make_callback_update

User = get_user_model()


class TmaTestApiCsrfAndSubmitTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            email="audit-tchr@example.test",
            password="StrongPassword123!",
            role=User.Role.TEACHER,
        )
        self.course = Course.objects.create(
            teacher=self.teacher,
            title="Audit Course",
            subject="uzbek",
        )
        self.test = Test.objects.create(
            course=self.course,
            title="Audit Public Test",
            subject="uzbek",
            audience_mode=Test.AudienceMode.PUBLIC_FREE,
            status=Test.Status.PUBLISHED,
            is_active=True,
            time_limit_minutes=0,
            pass_percentage=50,
            max_attempts=5,
        )
        self.q = Question.objects.create(
            test=self.test,
            text="2 + 2 = ?",
            question_type=Question.QuestionType.SINGLE_CHOICE,
            points=1,
            position=1,
        )
        self.c_ok = Choice.objects.create(question=self.q, text="4", is_correct=True)
        self.c_bad = Choice.objects.create(question=self.q, text="5", is_correct=False)

    def test_tma_test_start_and_submit_enforce_csrf_for_cookies_and_allow_jwt(self):
        with self.settings(TELEGRAM_BOT_TOKEN="bot-secret-audit"):
            init_data = _signed_init_data(tg_id=44556677, bot_token="bot-secret-audit")
            csrf_client = Client(enforce_csrf_checks=True)
            auth = csrf_client.post(
                "/tma/api/auth/",
                {"init_data": init_data},
                content_type="application/json",
            )
            self.assertEqual(auth.status_code, 200)
            csrf_token = csrf_client.cookies["csrftoken"].value
            access = auth.json()["tokens"]["access"]

            # Cookie-session POST without X-CSRFToken MUST be rejected with 403
            no_csrf = csrf_client.post(
                f"/tma/api/tests/{self.test.id}/start/",
                {},
                content_type="application/json",
            )
            self.assertEqual(no_csrf.status_code, 403)

            # Cookie-session POST with valid X-CSRFToken succeeds
            started = csrf_client.post(
                f"/tma/api/tests/{self.test.id}/start/",
                {},
                content_type="application/json",
                HTTP_X_CSRFTOKEN=csrf_token,
            )
            self.assertEqual(started.status_code, 200)
            attempt_id = started.json()["attempt_id"]

            # Cookie-session submit without X-CSRFToken MUST be rejected with 403
            submit_no_csrf = csrf_client.post(
                f"/tma/api/tests/{self.test.id}/submit/",
                {"attempt_id": attempt_id, "answers": {str(self.q.id): [self.c_ok.id]}},
                content_type="application/json",
            )
            self.assertEqual(submit_no_csrf.status_code, 403)

            # Bearer JWT submit succeeds without X-CSRFToken even when sessionid cookie is present
            submit_jwt = csrf_client.post(
                f"/tma/api/tests/{self.test.id}/submit/",
                {"attempt_id": attempt_id, "answers": {str(self.q.id): [self.c_ok.id]}},
                content_type="application/json",
                HTTP_AUTHORIZATION=f"Bearer {access}",
            )
            self.assertEqual(submit_jwt.status_code, 200)
            payload = submit_jwt.json()
            self.assertTrue(payload["success"])
            self.assertTrue(payload["is_passed"])
            self.assertEqual(payload["percentage"], 100.0)


class GroupIdempotencyAuditTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            email="audit-grp-tchr@example.test",
            password="StrongPassword123!",
            role=User.Role.TEACHER,
        )

    def test_idempotency_key_invalidates_deleted_group_and_separates_payloads(self):
        client = APIClient()
        client.force_authenticate(user=self.teacher)
        headers = {"HTTP_X_IDEMPOTENCY_KEY": "audit-key-1"}

        r1 = client.post(
            "/api/v1/school/groups/",
            {"name": "Audit G1", "subject": "uzbek"},
            format="json",
            **headers,
        )
        self.assertEqual(r1.status_code, 201)
        g1_id = r1.json()["id"]

        # Same key + different group name creates distinct group
        r2 = client.post(
            "/api/v1/school/groups/",
            {"name": "Audit G2", "subject": "uzbek"},
            format="json",
            **headers,
        )
        self.assertEqual(r2.status_code, 201)
        self.assertNotEqual(r2.json()["id"], g1_id)

        # Delete G1 and recreate G1 with same idempotency key -> must create fresh DB row, not stale ID
        StudentGroup.objects.filter(id=g1_id).delete()
        r3 = client.post(
            "/api/v1/school/groups/",
            {"name": "Audit G1", "subject": "uzbek"},
            format="json",
            **headers,
        )
        self.assertEqual(r3.status_code, 201)
        self.assertNotEqual(r3.json()["id"], g1_id)
        self.assertTrue(StudentGroup.objects.filter(id=r3.json()["id"]).exists())


class BotCallbackMalformedAndRoleTests(TestCase):
    def setUp(self):
        self.context = SimpleNamespace_context()
        self.admin = User.objects.create_superuser(
            email="audit-bot-adm@example.test",
            password="StrongPassword123!",
            telegram_chat_id=919191,
            telegram_identity_verified_at=timezone.now(),
        )
        self.center_admin = User.objects.create_user(
            email="audit-bot-cadm@example.test",
            password="StrongPassword123!",
            role=User.Role.CENTER_ADMIN,
            telegram_chat_id=929292,
            telegram_identity_verified_at=timezone.now(),
        )
        self.student = User.objects.create_user(
            email="audit-bot-stu@example.test",
            password="StrongPassword123!",
            role=User.Role.STUDENT,
            telegram_chat_id=939393,
            telegram_identity_verified_at=timezone.now(),
        )

    def test_malformed_numeric_callbacks_do_not_crash(self):
        for cb in ("adm_appr_tchr_abc", "adm_rej_tchr_nan", "publish_feedback_xyz", "reject_feedback_???"):
            update, query, _ = _make_callback_update(self.admin.telegram_chat_id, cb)
            async_to_sync(callback_handler)(update, self.context)
            query.answer.assert_awaited()

        for cb in ("tch_inv_bad", "tch_appr_bad", "tch_rej_bad"):
            update, query, _ = _make_callback_update(self.center_admin.telegram_chat_id, cb)
            async_to_sync(group_assistant_callback_handler)(update, self.context)
            query.answer.assert_awaited()

    def test_student_denied_on_menu_teacher_newmock_callback(self):
        update, query, msg = _make_callback_update(self.student.telegram_chat_id, "menu_teacher_newmock")
        async_to_sync(callback_handler)(update, self.context)
        self.assertTrue(msg.reply_text.called)
        self.assertIn("o'qituvchilar", msg.reply_text.await_args.args[0].lower())

        # Direct call also enforces role
        msg.reply_text.reset_mock()
        async_to_sync(newmock_handler)(update, self.context)
        self.assertTrue(msg.reply_text.called)
        self.assertIn("o'qituvchilar", msg.reply_text.await_args.args[0].lower())


def SimpleNamespace_context():
    from types import SimpleNamespace

    return SimpleNamespace(user_data={}, bot=SimpleNamespace(username="uz_essaygrader_bot", send_message=AsyncMock()))
