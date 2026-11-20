"""Regression tests: imported students must never receive shared/plaintext credentials."""

import re

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.accounts.services.csv_import import CSVImportService
from apps.organizations.models import LearningCenter

User = get_user_model()

IMPORT_URL = "/api/v1/enterprise/students/bulk-import/"
SETUP_LINK_RE = re.compile(
    r"https://grandec\\.uz/password-reset/confirm/([^/\\s]+)/([^/\\s]+)/"
)


@override_settings(
    SITE_URL="https://grandec.uz",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class EnterpriseImportCredentialTests(TestCase):
    def setUp(self):
        self.director = User.objects.create_user(
            email="director-import@example.com",
            password="DirectorSafePass123!",
            role=User.Role.CENTER_ADMIN,
        )
        self.center = LearningCenter.objects.create(
            owner=self.director, name="Import Security Center", student_seat_limit=20
        )
        self.director.learning_center = self.center
        self.director.save(update_fields=["learning_center"])
        self.client = APIClient()
        self.client.force_authenticate(user=self.director)

    def test_unique_passwords_and_one_time_setup_emails(self):
        payload = {
            "students": [
                {"first_name": "Ali", "email": "ali-import@example.com"},
                {"first_name": "Vali", "email": "vali-import@example.com"},
            ]
        }
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            response = self.client.post(IMPORT_URL, payload, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["imported"], 2)
        self.assertEqual(response.json()["manual_setup_required"], 0)
        self.assertNotIn("Standart parol", response.json()["message"])
        self.assertEqual(len(callbacks), 2)

        students = list(
            User.objects.filter(email__in=["ali-import@example.com", "vali-import@example.com"])
            .order_by("email")
        )
        self.assertEqual(len(students), 2)
        self.assertNotEqual(students[0].password, students[1].password)
        for student in students:
            self.assertTrue(student.has_usable_password())
            self.assertFalse(student.check_password("Grand2026!"))
            self.assertFalse(student.check_password(""))
            self.assertEqual(student.learning_center_id, self.center.pk)

        self.assertEqual(len(mail.outbox), 2)
        for message in mail.outbox:
            self.assertRegex(message.body, SETUP_LINK_RE)
            self.assertNotIn("Grand2026!", message.body)

    def test_setup_email_token_works_with_existing_password_confirm_api(self):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                IMPORT_URL,
                {"students": [{"first_name": "Sara", "email": "sara-import@example.com"}]},
                format="json",
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        match = SETUP_LINK_RE.search(mail.outbox[0].body)
        self.assertIsNotNone(match)
        uid, token = match.groups()

        new_password = "NewUniqueSafePassword2026!"
        confirm = self.client.post(
            "/api/auth/password-reset/confirm/",
            {
                "uid": uid,
                "token": token,
                "new_password1": new_password,
                "new_password2": new_password,
            },
            format="json",
        )
        self.assertEqual(confirm.status_code, 200)
        student = User.objects.get(email="sara-import@example.com")
        self.assertTrue(student.check_password(new_password))
        self.assertFalse(student.check_password("Grand2026!"))

    def test_missing_email_needs_manual_setup_without_shared_password(self):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                IMPORT_URL,
                {"students": [{"first_name": "No Email", "phone": "+998901112233"}]},
                format="json",
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["manual_setup_required"], 1)
        student = User.objects.get(email="student_998901112233@grandec.uz")
        self.assertTrue(student.has_usable_password())
        self.assertFalse(student.check_password("Grand2026!"))
        self.assertEqual(len(mail.outbox), 0)

    def test_import_cannot_attach_existing_unassigned_account(self):
        existing = User.objects.create_user(
            email="existing-student@example.com",
            password="ExistingAccount2026!",
            role=User.Role.STUDENT,
        )
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                IMPORT_URL,
                {"students": [{"first_name": "Claimed", "email": existing.email}]},
                format="json",
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["imported"], 0)
        self.assertEqual(response.json()["skipped"], 1)
        existing.refresh_from_db()
        self.assertIsNone(existing.learning_center_id)
        self.assertTrue(existing.check_password("ExistingAccount2026!"))
        self.assertEqual(len(mail.outbox), 0)

    def test_teacher_cannot_import_even_if_linked_to_center(self):
        teacher = User.objects.create_user(
            email="teacher-import@example.com",
            password="TeacherSafePass123!",
            role=User.Role.TEACHER,
            learning_center=self.center,
        )
        self.client.force_authenticate(user=teacher)
        response = self.client.post(
            IMPORT_URL,
            {"students": [{"first_name": "X", "email": "blocked@example.com"}]},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(User.objects.filter(email="blocked@example.com").exists())


@override_settings(
    SITE_URL="https://grandec.uz",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class LegacyCsvImportCredentialTests(TestCase):
    def test_legacy_csv_import_sends_setup_link_not_password(self):
        result = CSVImportService.import_students(
            "email,first_name,last_name\\nlegacy-import@example.com,Test,Student\\n",
            send_welcome=True,
        )
        self.assertEqual(result["created"], 1)
        student = User.objects.get(email="legacy-import@example.com")
        self.assertTrue(student.has_usable_password())
        self.assertFalse(student.check_password("Grand2026!"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertRegex(mail.outbox[0].body, SETUP_LINK_RE)
        self.assertNotIn("password:", mail.outbox[0].body.lower())
        self.assertNotIn("Grand2026!", mail.outbox[0].body)
