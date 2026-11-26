"""Asynchronous Celery tasks for Speaking AI evaluation."""

from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=1)
def evaluate_speaking_submission_task(self, submission_id: int, transcript_only: bool = False) -> dict:
    """Evaluate a pending SpeakingSubmission asynchronously and refund quota on failure."""
    from apps.core.ai_health import AIUnavailable, record_ai_failure, record_ai_success
    from apps.payments.ai_quota import refund_feature_cap
    from .models import SpeakingSubmission
    from .services import apply_speaking_evaluation

    sub = SpeakingSubmission.objects.select_related("user", "topic").filter(pk=submission_id).first()
    if sub is None:
        return {"ok": False, "reason": "not_found"}
    if sub.status not in (SpeakingSubmission.Status.EVALUATING,):
        return {"ok": True, "status": sub.status, "skipped": True}

    try:
        apply_speaking_evaluation(sub, transcript_only=transcript_only)
        record_ai_success("speaking")
        return {"ok": True, "status": sub.status, "submission_id": sub.pk}
    except AIUnavailable as exc:
        refund_feature_cap(sub.user, "speaking")
        record_ai_failure("speaking", exc)
        sub.status = SpeakingSubmission.Status.ERROR
        sub.feedback = {**(sub.feedback or {}), "error": str(exc)}
        sub.save(update_fields=["status", "feedback"])
        return {"ok": False, "status": "error", "code": "not_graded"}
    except Exception as exc:
        refund_feature_cap(sub.user, "speaking")
        logger.exception("Async speaking evaluation failed for submission=%s: %s", submission_id, exc)
        sub.status = SpeakingSubmission.Status.ERROR
        sub.feedback = {**(sub.feedback or {}), "error": AIUnavailable.user_message}
        sub.save(update_fields=["status", "feedback"])
        return {"ok": False, "status": "error", "code": "error"}
