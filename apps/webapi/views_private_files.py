"""Authenticated downloads for private uploads.

Receipts, tuition proofs and speaking recordings used to be reachable by URL under the
public ``/media/`` mapping. They are now only served here, after an object-level check.
Callers who are not allowed to see a file get **404**, never 403, so the existence of
somebody else's receipt cannot be probed.
"""

from __future__ import annotations

from django.http import Http404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from apps.accounts.access import has_platform_permission, is_platform_admin
from apps.core.private_files import private_file_response
from apps.payments.models import PaymentReceipt
from apps.speaking.models import SpeakingSubmission
from apps.subscriptions.models import PaymentReceipt as SubscriptionReceipt
from apps.tuition.models import CoursePayment
from apps.tuition.permissions import can_view_invoice, can_view_tuition

RECEIPT_REVIEW_PERMISSION = "payments.view_paymentreceipt"
SUBSCRIPTION_RECEIPT_REVIEW_PERMISSION = "subscriptions.view_paymentreceipt"


def payment_receipt_path(receipt_id: int) -> str:
    return f"/api/v1/files/payment-receipts/{int(receipt_id)}/"


def subscription_receipt_path(receipt_id: int) -> str:
    return f"/api/v1/files/subscription-receipts/{int(receipt_id)}/"


def tuition_proof_path(payment_id: int) -> str:
    return f"/api/v1/files/tuition-proofs/{int(payment_id)}/"


def speaking_audio_path(submission_id: int) -> str:
    return f"/api/v1/files/speaking/{int(submission_id)}/audio/"


def _can_read_receipt(user, receipt: PaymentReceipt) -> bool:
    return receipt.user_id == user.pk or has_platform_permission(user, RECEIPT_REVIEW_PERMISSION)


def _can_read_proof(user, payment: CoursePayment) -> bool:
    if payment.student_id == user.pk:
        return True
    if payment.invoice_id and payment.invoice is not None:
        return can_view_invoice(user, payment.invoice)
    return can_view_tuition(user)


def _can_read_speaking(user, submission: SpeakingSubmission) -> bool:
    # Recordings are personal data. Owner and platform admins only; a teacher or center
    # admin gets no implicit access (grant it explicitly if a review workflow needs it).
    return submission.user_id == user.pk or is_platform_admin(user)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def payment_receipt_file_view(request, receipt_id: int):
    receipt = PaymentReceipt.objects.filter(pk=receipt_id).first()
    if receipt is None or not _can_read_receipt(request.user, receipt):
        raise Http404
    return private_file_response(receipt.receipt_image, download_name=f"receipt-{receipt.pk}")


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def tuition_proof_file_view(request, payment_id: int):
    payment = CoursePayment.objects.select_related("invoice").filter(pk=payment_id).first()
    if payment is None or not payment.proof or not _can_read_proof(request.user, payment):
        raise Http404
    return private_file_response(payment.proof, download_name=f"proof-{payment.pk}")


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def speaking_audio_file_view(request, submission_id: int):
    submission = SpeakingSubmission.objects.filter(pk=submission_id).first()
    if (
        submission is None
        or not submission.audio_file
        or not _can_read_speaking(request.user, submission)
    ):
        raise Http404
    return private_file_response(submission.audio_file, download_name=f"speaking-{submission.pk}")


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def subscription_receipt_file_view(request, receipt_id: int):
    receipt = SubscriptionReceipt.objects.filter(pk=receipt_id).first()
    if receipt is None or not (
        receipt.user_id == request.user.pk
        or has_platform_permission(request.user, SUBSCRIPTION_RECEIPT_REVIEW_PERMISSION)
    ):
        raise Http404
    return private_file_response(receipt.receipt_image, download_name=f"receipt-{receipt.pk}")
