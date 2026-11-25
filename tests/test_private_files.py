"""Private uploads are served only through authenticated, object-checked views.

Covers payment receipts, subscription receipts, tuition proofs and speaking audio:
anonymous, owner, other student, unrelated teacher, center admin and platform admin,
the response hardening headers, X-Accel-Redirect mode and path-traversal refusal.
"""

from __future__ import annotations

import shutil
import tempfile
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.signals import request_finished
from django.db import close_old_connections
from django.http import Http404
from django.test import override_settings
from rest_framework.test import APIClient

from apps.core.private_files import is_private_media_name, private_file_response
from apps.payments.models import PaymentReceipt
from apps.speaking.models import SpeakingSubmission, SpeakingTopic
from apps.subscriptions.models import PaymentReceipt as SubscriptionReceipt
from apps.tuition.models import CoursePayment
from tests.conftest import LMSBaseTestCase

User = get_user_model()

# 1x1 PNG
PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7\x9a\xa0\xa0\x00\x00\x00\x00IEND\xaeB`\x82"
)


def close_quietly(response) -> None:
    """Close a streaming response without letting request_finished close the test's DB connection."""
    request_finished.disconnect(close_old_connections)
    try:
        response.close()
    finally:
        request_finished.connect(close_old_connections)


AUDIO = b"RIFF$\x00\x00\x00WAVEfmt " + b"\x00" * 24


class PrivateFileAccessTests(LMSBaseTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media = tempfile.mkdtemp(prefix="lms-private-files-")
        cls._override = override_settings(MEDIA_ROOT=cls._media)
        cls._override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._override.disable()
        shutil.rmtree(cls._media, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        self.other_student = User.objects.create_user(
            email="other-student@test.com", password="testpass123", role="student"
        )
        self.other_teacher = User.objects.create_user(
            email="other-teacher@test.com", password="testpass123", role="teacher"
        )
        self.center_admin = User.objects.create_user(
            email="center-admin@test.com", password="testpass123", role="center_admin"
        )

        self.receipt = PaymentReceipt.objects.create(
            user=self.student,
            plan="pro",
            amount=Decimal("49000"),
            receipt_image=SimpleUploadedFile("secret.png", PNG, "image/png"),
            image_hash="a" * 64,
        )
        self.sub_receipt = SubscriptionReceipt.objects.create(
            user=self.student,
            plan_type="pro",
            amount=Decimal("49000"),
            payment_system=SubscriptionReceipt.PaymentSystem.CLICK,
            transaction_id="PRIV-TX-1",
            receipt_image=SimpleUploadedFile("sub.png", PNG, "image/png"),
            receipt_hash="b" * 64,
        )
        self.payment = CoursePayment.objects.create(
            student=self.student,
            amount_uzs=Decimal("100000"),
            proof=SimpleUploadedFile("proof.png", PNG, "image/png"),
        )
        topic = SpeakingTopic.objects.create(
            title="Journey",
            subject="english",
            part=SpeakingTopic.PartChoice.PART2,
            prompt="Describe a journey.",
        )
        self.speaking = SpeakingSubmission.objects.create(
            user=self.student,
            topic=topic,
            audio_file=SimpleUploadedFile("voice.wav", AUDIO, "audio/wav"),
        )

        self.targets = {
            "payment-receipt": f"/api/v1/files/payment-receipts/{self.receipt.pk}/",
            "subscription-receipt": f"/api/v1/files/subscription-receipts/{self.sub_receipt.pk}/",
            "tuition-proof": f"/api/v1/files/tuition-proofs/{self.payment.pk}/",
            "speaking-audio": f"/api/v1/files/speaking/{self.speaking.pk}/audio/",
        }

    def get(self, user, url):
        client = APIClient()
        if user is not None:
            client.force_authenticate(user)
        return client.get(url)

    # -- who may read ---------------------------------------------------------

    def test_anonymous_is_rejected_everywhere(self):
        for name, url in self.targets.items():
            with self.subTest(name):
                self.assertIn(self.get(None, url).status_code, (401, 403))

    def test_owner_can_read_their_own_files(self):
        for name, url in self.targets.items():
            with self.subTest(name):
                response = self.get(self.student, url)
                self.assertEqual(response.status_code, 200, name)
                self.assertTrue(len(b"".join(response.streaming_content)) > 0)

    def test_unrelated_accounts_get_404_not_403(self):
        for user in (self.other_student, self.other_teacher, self.center_admin):
            for name, url in self.targets.items():
                with self.subTest(user=user.email, target=name):
                    self.assertEqual(self.get(user, url).status_code, 404)

    def test_teacher_of_the_student_gets_no_implicit_access_to_audio_or_receipts(self):
        # self.teacher teaches self.student's course in the base fixture.
        for name, url in self.targets.items():
            with self.subTest(name):
                self.assertEqual(self.get(self.teacher, url).status_code, 404)

    def test_platform_admin_can_read_everything(self):
        for name, url in self.targets.items():
            with self.subTest(name):
                response = self.get(self.admin_user, url)
                self.assertEqual(response.status_code, 200, name)

    def test_delegated_permission_unlocks_only_the_matching_file(self):
        from django.contrib.auth.models import Permission

        reviewer = User.objects.create_user(
            email="reviewer@test.com", password="testpass123", role="teacher"
        )
        reviewer.user_permissions.add(Permission.objects.get(codename="view_paymentreceipt", content_type__app_label="payments"))
        reviewer = User.objects.get(pk=reviewer.pk)  # drop the permission cache
        self.assertEqual(self.get(reviewer, self.targets["payment-receipt"]).status_code, 200)
        self.assertEqual(self.get(reviewer, self.targets["subscription-receipt"]).status_code, 404)
        self.assertEqual(self.get(reviewer, self.targets["speaking-audio"]).status_code, 404)

    def test_missing_or_unknown_objects_are_404(self):
        self.assertEqual(self.get(self.student, "/api/v1/files/payment-receipts/999999/").status_code, 404)
        no_proof = CoursePayment.objects.create(student=self.student, amount_uzs=Decimal("1"))
        self.assertEqual(self.get(self.student, f"/api/v1/files/tuition-proofs/{no_proof.pk}/").status_code, 404)

    def test_a_deleted_file_on_disk_is_404_not_500(self):
        self.receipt.receipt_image.storage.delete(self.receipt.receipt_image.name)
        self.assertEqual(self.get(self.student, self.targets["payment-receipt"]).status_code, 404)

    # -- how it is served -----------------------------------------------------

    def test_response_is_private_nosniff_and_sandboxed(self):
        response = self.get(self.student, self.targets["payment-receipt"])
        self.assertIn("no-store", response["Cache-Control"])
        self.assertIn("private", response["Cache-Control"])
        self.assertNotIn("public", response["Cache-Control"])
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertIn("sandbox", response["Content-Security-Policy"])
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertTrue(response["Content-Disposition"].startswith("inline"))
        close_quietly(response)

    def test_active_content_is_always_an_attachment(self):
        for filename in ("evil.svg", "evil.html", "evil.pdf"):
            with self.subTest(filename):
                payment = CoursePayment.objects.create(
                    student=self.student,
                    amount_uzs=Decimal("1"),
                    proof=SimpleUploadedFile(filename, b"<svg onload=alert(1)>", "image/svg+xml"),
                )
                response = private_file_response(payment.proof)
                self.assertTrue(response["Content-Disposition"].startswith("attachment"), filename)
                close_quietly(response)

    def test_accel_redirect_mode_sends_no_body(self):
        with override_settings(PRIVATE_MEDIA_ACCEL_PREFIX="/_private_media/"):
            response = self.get(self.student, self.targets["payment-receipt"])
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["X-Accel-Redirect"].startswith("/_private_media/receipts/"))
        self.assertEqual(response.content, b"")
        self.assertIn("no-store", response["Cache-Control"])

    # -- the helper cannot be abused as a generic file reader -----------------

    def test_only_private_prefixes_are_servable(self):
        self.assertTrue(is_private_media_name("receipts/2026/11/a.png"))
        self.assertTrue(is_private_media_name("speaking/audio/2026/11/a.wav"))
        self.assertTrue(is_private_media_name("essays/audio/2026/11/a.wav"))
        self.assertFalse(is_private_media_name("exams/audio/a.mp3"))
        self.assertFalse(is_private_media_name("receipts/../secrets/x"))
        self.assertFalse(is_private_media_name("../receipts/x"))
        self.assertFalse(is_private_media_name("essays/audio/../secrets/x"))
        field = type("FF", (), {"name": "avatars/me.png"})()
        with self.assertRaises(Http404):
            private_file_response(field)
        traversal = type("FF", (), {"name": "receipts/../../etc/passwd"})()
        with self.assertRaises(Http404):
            private_file_response(traversal)

    def test_nginx_configs_deny_all_private_media_prefixes(self):
        from pathlib import Path
        from apps.core.private_files import PRIVATE_MEDIA_PREFIXES

        expected_alts = "|".join(p.rstrip("/") for p in PRIVATE_MEDIA_PREFIXES)
        expected_block = f"location ~ ^/media/({expected_alts})/ {{"
        root = Path(__file__).resolve().parents[1]
        for rel, expected_count in (
            ("nginx.conf", 1),
            ("deploy/nginx/nginx-http.conf", 1),
            ("deploy/nginx/nginx-ssl.conf", 2),
            ("deploy/nginx/nginx.conf", 2),
        ):
            text = (root / rel).read_text(encoding="utf-8")
            self.assertEqual(
                text.count(expected_block),
                expected_count,
                f"{rel} must contain {expected_count} private-media deny blocks matching PRIVATE_MEDIA_PREFIXES",
            )
            self.assertGreaterEqual(text.count("location /_private_media/ {"), expected_count)

        verify_script = (root / "deploy/scripts/verify_private_media_nginx.sh").read_text(encoding="utf-8")
        self.assertIn(f"^/media/({expected_alts})/", verify_script)
        self.assertIn("/media/essays/audio/2026/11/f.wav", verify_script)
        self.assertIn("/api/classroom/essays/1/voice/", verify_script)

    # -- API output never carries a public /media/ URL ------------------------

    def test_receipt_api_exposes_only_the_authenticated_path(self):
        client = APIClient()
        client.force_authenticate(self.student)
        response = client.get("/api/v1/payments/my-receipts/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        data = response.json()["results"][0]
        self.assertEqual(data["receipt_image_url"], self.targets["payment-receipt"])
        self.assertEqual(data["receipt_image"], self.targets["payment-receipt"])
        self.assertNotIn("/media/", str(data))

    def test_speaking_serializer_exposes_only_the_authenticated_path(self):
        from apps.speaking.views import _serialize_submission

        data = _serialize_submission(self.speaking)
        self.assertEqual(data["audio_url"], self.targets["speaking-audio"])
        self.assertNotIn("/media/", str(data))

    def test_admin_receipt_preview_has_no_public_media_url(self):
        from django.contrib import admin

        model_admin = admin.site._registry[PaymentReceipt]
        for html in (model_admin.receipt_preview(self.receipt), model_admin.receipt_preview_large(self.receipt)):
            self.assertNotIn("/media/", html)
            self.assertIn(self.targets["payment-receipt"], html)
