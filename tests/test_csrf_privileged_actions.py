"""Privileged state changes must not be forgeable through a victim's session cookie."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.middleware.csrf import _get_new_csrf_string
from django.test import Client
from rest_framework_simplejwt.tokens import AccessToken

from apps.payments.models import PaymentReceipt

User = get_user_model()
PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7\x9a\xa0\xa0\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture
def receipt(db):
    student = User.objects.create_user(email="payer@example.test", password="x-Pass-123!", role="student")
    return PaymentReceipt.objects.create(
        user=student, plan="pro", amount=Decimal("15000"), image_hash="c" * 64,
        receipt_image=SimpleUploadedFile("r.png", PNG, "image/png"),
    )


@pytest.fixture
def admin(db):
    return User.objects.create_user(email="payments-admin@example.test", password="x-Pass-123!", role="admin")


def url(receipt):
    return f"/api/v1/billing/receipts/{receipt.id}/review/"


@pytest.mark.django_db
def test_session_without_csrf_token_cannot_approve_a_receipt(receipt, admin):
    client = Client(enforce_csrf_checks=True)
    client.force_login(admin)
    response = client.post(url(receipt), {"action": "approve"}, content_type="application/json")
    assert response.status_code == 403
    receipt.refresh_from_db()
    assert receipt.status == PaymentReceipt.Status.PENDING
    assert not receipt.user.has_pro_access


@pytest.mark.django_db
def test_session_with_a_valid_csrf_token_can_still_review(receipt, admin):
    client = Client(enforce_csrf_checks=True)
    client.force_login(admin)
    token = _get_new_csrf_string()
    client.cookies["csrftoken"] = token
    response = client.post(url(receipt), {"action": "reject", "note": "blurry"}, content_type="application/json",
                           HTTP_X_CSRFTOKEN=token)
    assert response.status_code == 200, response.content
    receipt.refresh_from_db()
    assert receipt.status == PaymentReceipt.Status.REJECTED


@pytest.mark.django_db
def test_bearer_token_callers_are_not_subject_to_csrf(receipt, admin):
    client = Client(enforce_csrf_checks=True)
    response = client.post(url(receipt), {"action": "reject", "note": "x"}, content_type="application/json",
                           HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(admin)}")
    assert response.status_code == 200, response.content


@pytest.mark.django_db
def test_a_student_cannot_review_even_with_a_valid_csrf_token(receipt):
    other = User.objects.create_user(email="snoop@example.test", password="x-Pass-123!", role="student")
    client = Client(enforce_csrf_checks=True)
    client.force_login(other)
    token = _get_new_csrf_string()
    client.cookies["csrftoken"] = token
    response = client.post(url(receipt), {"action": "approve"}, content_type="application/json", HTTP_X_CSRFTOKEN=token)
    assert response.status_code == 403
    receipt.refresh_from_db()
    assert receipt.status == PaymentReceipt.Status.PENDING
