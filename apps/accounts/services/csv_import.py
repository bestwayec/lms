"""
CSV Import Service — Talabalarni CSV fayldan to'plamda qo'shish.

Supports:
    - CSV with columns: email, first_name, last_name, phone (optional)
    - Duplicate detection (skip existing emails)
    - Independent, unguessable initial credentials for new students
    - One-time password-setup emails (never plaintext passwords)
    - Import summary with success/error counts
"""

from __future__ import annotations

import csv
import io
import logging
import secrets
from typing import Any

from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import PasswordResetForm

logger = logging.getLogger(__name__)
User = get_user_model()


class CSVImportService:
    """
    CSV fayldan talabalarni import qilish xizmati.

    CSV format:
        email,first_name,last_name,phone
        student1@example.com,Ali,Valiyev,+998901234567
        student2@example.com,Vali,Hasanov,+998907654321
    """

    REQUIRED_COLUMNS = {"email", "first_name", "last_name"}
    OPTIONAL_COLUMNS = {"phone"}
    VALID_COLUMNS = REQUIRED_COLUMNS | OPTIONAL_COLUMNS

    @classmethod
    def import_students(
        cls,
        csv_content: str | bytes,
        created_by: Any = None,
        send_welcome: bool = True,
    ) -> dict[str, Any]:
        """
        CSV dan talabalarni import qilish.

        Args:
            csv_content: CSV faylning matn/kontenti.
            created_by: Kim tomonidan yaratilgan (teacher/admin).
            send_welcome: Welcome email yuborilsinmi?

        Returns:
            {
                "total": int,
                "created": int,
                "skipped": int,
                "errors": list[dict],
                "created_users": list[User],
            }
        """
        if isinstance(csv_content, bytes):
            csv_content = csv_content.decode("utf-8-sig")

        reader = csv.DictReader(io.StringIO(csv_content))

        # Validate columns
        if not reader.fieldnames:
            return {
                "total": 0,
                "created": 0,
                "skipped": 0,
                "errors": [{"row": 0, "error": "CSV fayl bo'sh"}],
                "created_users": [],
            }

        missing = cls.REQUIRED_COLUMNS - set(reader.fieldnames)
        if missing:
            return {
                "total": 0,
                "created": 0,
                "skipped": 0,
                "errors": [
                    {"row": 0, "error": f"Kerakli ustunlar yo'q: {', '.join(missing)}"}
                ],
                "created_users": [],
            }

        created = 0
        skipped = 0
        errors = []
        created_users = []

        for i, row in enumerate(reader, start=2):  # start=2 because row 1 is header
            try:
                email = row.get("email", "").strip().lower()
                first_name = row.get("first_name", "").strip()
                last_name = row.get("last_name", "").strip()
                phone = row.get("phone", "").strip()

                # Validate required fields
                if not email:
                    errors.append({"row": i, "error": "Email bo'sh"})
                    continue
                if not first_name:
                    errors.append({"row": i, "error": "Ism bo'sh"})
                    continue
                if not last_name:
                    errors.append({"row": i, "error": "Familiya bo'sh"})
                    continue

                # Check duplicate
                if User.objects.filter(email=email).exists():
                    skipped += 1
                    continue

                # Generate password
                password = secrets.token_urlsafe(32)

                # Create user
                user = User.objects.create_user(
                    email=email,
                    password=password,
                    first_name=first_name,
                    last_name=last_name,
                    role="student",
                )

                # Update phone in profile if provided
                if phone:
                    from apps.accounts.models import Profile

                    profile, _ = Profile.objects.get_or_create(user=user)
                    profile.phone = phone
                    profile.save(update_fields=["phone"])

                created += 1
                created_users.append(user)

                # Send welcome email
                if send_welcome:
                    try:
                        cls._send_welcome_email(user)
                    except Exception as e:
                        logger.warning("Password setup email failed for user_id=%s: %s", user.pk, e)

            except Exception as e:
                errors.append({"row": i, "error": str(e)})

        logger.info(
            "CSV import completed: total=%d, created=%d, skipped=%d, errors=%d",
            created + skipped,
            created,
            skipped,
            len(errors),
        )

        return {
            "total": created + skipped + len(errors),
            "created": created,
            "skipped": skipped,
            "errors": errors,
            "created_users": created_users,
        }

    @classmethod
    def _send_welcome_email(cls, user: Any) -> None:
        """Email a one-time password setup link, never an initial password.

        Imported accounts have an unguessable independent password and can
        activate access through the existing one-hour reset confirmation flow.
        """
        site = urlsplit(settings.SITE_URL)
        if (
            site.scheme not in ("http", "https")
            or not site.netloc
            or site.path not in ("", "/")
            or (not settings.DEBUG and site.scheme != "https")
        ):
            raise ValueError("SITE_URL must be a valid HTTPS origin in production")

        form = PasswordResetForm({"email": user.email})
        if not form.is_valid():
            raise ValueError("Imported student has no valid email for password setup")

        form.save(
            domain_override=site.netloc,
            use_https=(site.scheme == "https"),
            email_template_name="registration/password_reset_email.txt",
            subject_template_name="registration/password_reset_subject.txt",
            html_email_template_name="registration/password_reset_email.html",
            extra_email_context={"lang": getattr(user, "language", "uz")},
        )

    @classmethod
    def validate_csv(cls, csv_content: str | bytes) -> dict[str, Any]:
        """
        CSV faylni tekshirish (import qilmasdan).

        Returns:
            {"valid": bool, "errors": list, "row_count": int, "columns": list}
        """
        if isinstance(csv_content, bytes):
            csv_content = csv_content.decode("utf-8-sig")

        reader = csv.DictReader(io.StringIO(csv_content))

        if not reader.fieldnames:
            return {
                "valid": False,
                "errors": ["CSV fayl bo'sh"],
                "row_count": 0,
                "columns": [],
            }

        missing = cls.REQUIRED_COLUMNS - set(reader.fieldnames)
        if missing:
            return {
                "valid": False,
                "errors": [f"Kerakli ustunlar yo'q: {', '.join(missing)}"],
                "row_count": 0,
                "columns": list(reader.fieldnames),
            }

        rows = list(reader)
        errors = []
        for i, row in enumerate(rows, start=2):
            if not row.get("email", "").strip():
                errors.append(f"{i}-qator: Email bo'sh")
            if not row.get("first_name", "").strip():
                errors.append(f"{i}-qator: Ism bo'sh")
            if not row.get("last_name", "").strip():
                errors.append(f"{i}-qator: Familiya bo'sh")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "row_count": len(rows),
            "columns": list(reader.fieldnames),
        }
