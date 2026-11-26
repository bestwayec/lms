"""Phase 01 regression & security tests: Groups JSON API + TMA CSRF & Session lifecycle."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from rest_framework.test import APIClient

from apps.courses.models import StudentGroup
from apps.essays.models import EssayTopic

User = get_user_model()


def _signed_init_data(
    *,
    tg_id: int = 99887766,
    first_name: str = "TMA",
    last_name: str = "Student",
    username: str = "tmastudent",
    auth_date: int | None = None,
    bot_token: str | None = None,
) -> str:
    token = bot_token or getattr(settings, "TELEGRAM_BOT_TOKEN", "") or "test-bot-token-123"
    ts = int(time.time()) if auth_date is None else auth_date
    user_json = json.dumps(
        {
            "id": tg_id,
            "first_name": first_name,
            "last_name": last_name,
            "username": username,
            "language_code": "uz",
        },
        separators=(",", ":"),
    )
    fields = {
        "auth_date": str(ts),
        "query_id": "AAEAAAE",
        "user": user_json,
    }
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret_key = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


class UnmatchedApiJsonFallbackTests(TestCase):
    def test_unmatched_api_routes_return_json_404_not_html_200(self):
        for path in (
            "/api/v1/does-not-exist/",
            "/api/classroom/does-not-exist/",
            "/tma/api/does-not-exist/",
            "/essays/api/does-not-exist/",
        ):
            resp = self.client.get(path)
            self.assertEqual(resp.status_code, 404, msg=path)
            self.assertIn("application/json", resp["Content-Type"], msg=path)
            self.assertEqual(resp.json().get("code"), "not_found")


class GroupsApiRecoveryTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            email="grp-teacher@test.local",
            password="Password123!",
            role=User.Role.TEACHER,
            first_name="Teacher",
            last_name="One",
        )
        self.other_teacher = User.objects.create_user(
            email="grp-other@test.local",
            password="Password123!",
            role=User.Role.TEACHER,
        )
        self.student = User.objects.create_user(
            email="grp-student@test.local",
            password="Password123!",
            role=User.Role.STUDENT,
        )

    def test_teacher_group_create_idempotent_edit_archive_restore_and_delete(self):
        client = APIClient()
        client.force_authenticate(user=self.teacher)

        headers = {"HTTP_X_IDEMPOTENCY_KEY": "create-alpha-1"}
        r1 = client.post(
            "/api/v1/school/groups/",
            {"name": "Alpha Group", "description": "D1"},
            format="json",
            **headers,
        )
        self.assertEqual(r1.status_code, 201)
        gid = r1.json()["id"]

        # Duplicate submission with same idempotency key does not fail or duplicate
        r2 = client.post(
            "/api/v1/school/groups/",
            {"name": "Alpha Group", "description": "D1"},
            format="json",
            **headers,
        )
        self.assertEqual(r2.status_code, 201)
        self.assertEqual(r2.json()["id"], gid)
        self.assertEqual(StudentGroup.objects.filter(teacher=self.teacher, name="Alpha Group").count(), 1)

        # Edit
        edit_resp = client.patch(
            f"/api/v1/school/groups/{gid}/",
            {"name": "Alpha Updated", "description": "D2"},
            format="json",
        )
        self.assertEqual(edit_resp.status_code, 200)
        self.assertEqual(edit_resp.json()["name"], "Alpha Updated")

        # Dependencies, Archive, Restore via canonical AND alias endpoints
        for dep_url in (
            f"/api/classroom/teacher/groups/{gid}/dependencies/",
            f"/api/classroom/groups/{gid}/dependencies/",
        ):
            dep = client.get(dep_url)
            self.assertEqual(dep.status_code, 200)
            self.assertIn("application/json", dep["Content-Type"])
            self.assertTrue(dep.json()["can_delete"])

        arch = client.post(f"/api/classroom/teacher/groups/{gid}/archive/")
        self.assertEqual(arch.status_code, 200)
        self.assertEqual(arch.json()["group_status"], "archived")

        rest = client.post(f"/api/classroom/groups/{gid}/restore/")
        self.assertEqual(rest.status_code, 200)
        self.assertEqual(rest.json()["group_status"], "active")

        dele = client.post(f"/api/classroom/teacher/groups/{gid}/delete/")
        self.assertEqual(dele.status_code, 200)
        self.assertFalse(StudentGroup.objects.filter(id=gid).exists())

    def test_cross_teacher_and_student_forbidden(self):
        group = StudentGroup.objects.create(teacher=self.teacher, name="Private Group")

        student_client = APIClient()
        student_client.force_authenticate(user=self.student)
        self.assertEqual(student_client.post("/api/v1/school/groups/", {"name": "X"}, format="json").status_code, 403)
        self.assertEqual(student_client.get(f"/api/classroom/teacher/groups/{group.id}/dependencies/").status_code, 403)

        other_client = APIClient()
        other_client.force_authenticate(user=self.other_teacher)
        self.assertEqual(other_client.get(f"/api/classroom/teacher/groups/{group.id}/dependencies/").status_code, 403)
        self.assertEqual(other_client.post(f"/api/classroom/teacher/groups/{group.id}/archive/").status_code, 403)


class TelegramMiniAppCsrfSecurityTests(TestCase):
    def setUp(self):
        self.topic = EssayTopic.objects.create(
            title="TMA Topic",
            description="Write essay",
            word_limit_min=20,
            word_limit_max=200,
            is_active=True,
        )

    def test_tma_auth_valid_sets_session_and_csrf_and_reopen_never_403s(self):
        with self.settings(TELEGRAM_BOT_TOKEN="bot-secret-xyz"):
            init_data = _signed_init_data(tg_id=55667788, bot_token="bot-secret-xyz")
            client = Client(enforce_csrf_checks=True)

            # First open inside Telegram WebView -> returns tokens + sessionid + csrftoken
            r1 = client.post("/tma/api/auth/", {"init_data": init_data}, content_type="application/json")
            self.assertEqual(r1.status_code, 200)
            self.assertIn("tokens", r1.json())
            self.assertIn("sessionid", client.cookies)
            self.assertIn("csrftoken", client.cookies)

            # Reopen WebView: persisted sessionid cookie is sent without X-CSRFToken or Bearer
            init_data2 = _signed_init_data(tg_id=55667788, bot_token="bot-secret-xyz")
            r2 = client.post("/tma/api/auth/", {"init_data": init_data2}, content_type="application/json")
            self.assertEqual(r2.status_code, 200)
            self.assertIn("tokens", r2.json())

    def test_tma_auth_rejects_invalid_tampered_and_expired_init_data(self):
        with self.settings(TELEGRAM_BOT_TOKEN="bot-secret-xyz"):
            valid = _signed_init_data(tg_id=11223344, bot_token="bot-secret-xyz")
            tampered = valid.replace("tmastudent", "eviluser")
            wrong_sig = _signed_init_data(tg_id=11223344, bot_token="wrong-token")
            expired = _signed_init_data(
                tg_id=11223344,
                auth_date=int(time.time()) - 90000,
                bot_token="bot-secret-xyz",
            )
            for payload in (tampered, wrong_sig, expired, ""):
                resp = self.client.post("/tma/api/auth/", {"init_data": payload}, content_type="application/json")
                self.assertEqual(resp.status_code, 401)
                self.assertNotIn("tokens", resp.json())

    def test_session_authenticated_tma_mutation_still_enforces_csrf(self):
        with self.settings(TELEGRAM_BOT_TOKEN="bot-secret-xyz"):
            init_data = _signed_init_data(tg_id=77889900, bot_token="bot-secret-xyz")
            csrf_client = Client(enforce_csrf_checks=True)
            auth = csrf_client.post("/tma/api/auth/", {"init_data": init_data}, content_type="application/json")
            self.assertEqual(auth.status_code, 200)
            csrf_token = csrf_client.cookies["csrftoken"].value
            access = auth.json()["tokens"]["access"]

            # Missing CSRF on cookie-only session mutation -> 403
            no_csrf = csrf_client.post(f"/tma/api/essays/{self.topic.id}/start/", {}, content_type="application/json")
            self.assertEqual(no_csrf.status_code, 403)
            self.assertIn("CSRF", str(no_csrf.json().get("detail", "")))

            # Invalid CSRF token on cookie-only session mutation -> 403
            bad_csrf = csrf_client.post(
                f"/tma/api/essays/{self.topic.id}/start/",
                {},
                content_type="application/json",
                HTTP_X_CSRFTOKEN="invalid-token-1234",
            )
            self.assertEqual(bad_csrf.status_code, 403)

            # Valid CSRF token on session mutation -> succeeds
            good_csrf = csrf_client.post(
                f"/tma/api/essays/{self.topic.id}/start/",
                {},
                content_type="application/json",
                HTTP_X_CSRFTOKEN=csrf_token,
            )
            self.assertIn(good_csrf.status_code, (200, 201))

            # Bearer JWT mutation -> succeeds cleanly without CSRF error even when cookie exists
            bearer_resp = csrf_client.post(
                f"/tma/api/essays/{self.topic.id}/start/",
                {},
                content_type="application/json",
                HTTP_AUTHORIZATION=f"Bearer {access}",
            )
            self.assertIn(bearer_resp.status_code, (200, 201))

    def test_session_status_plants_csrf_cookie(self):
        client = Client(enforce_csrf_checks=True)
        resp = client.get("/api/auth/session/status/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("csrftoken", client.cookies)
