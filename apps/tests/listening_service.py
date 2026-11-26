"""Server-authoritative Listening playback schedule & play-limit enforcement."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.tests.models import ExamPart, TestAttempt

LISTENING_GRACE_SECONDS = 120


def effective_play_limit(attempt: TestAttempt, part: ExamPart | None) -> int:
    """Return max permitted plays: 0 means unlimited (practice mode)."""
    study_mode = getattr(attempt, "study_mode", "") or getattr(attempt, "mode", "strict")
    if study_mode == "practice":
        return 0
    if part and part.audio_play_limit and part.audio_play_limit > 0:
        return int(part.audio_play_limit)
    exam_type = getattr(attempt.test, "exam_type", "") or ""
    if exam_type in ("ielts_academic", "ielts_general", "cefr_multilevel"):
        return 1
    return 0


def _schedule_key(part_id: int) -> str:
    return f"listening:{int(part_id)}"


@transaction.atomic
def get_or_update_listening_schedule(
    *,
    attempt_id: int,
    student: Any,
    part_id: int,
    start_play: bool = False,
    duration_seconds: float | None = None,
) -> dict[str, Any]:
    """Read or atomically advance Listening playback state for an attempt part.

    HTTP Range media requests never call with ``start_play=True``, ensuring seeks
    and metadata preloads never consume playback allowance.
    """
    attempt = TestAttempt.objects.select_related("test").select_for_update().get(
        pk=attempt_id,
        student=student,
    )
    part = ExamPart.objects.filter(pk=part_id, section__test_id=attempt.test_id).first()
    if part is None:
        raise ValueError("Listening qismi topilmadi.")

    limit = effective_play_limit(attempt, part)
    media_state = dict(attempt.media_state or {})
    key = _schedule_key(part_id)
    cur = dict(media_state.get(key) or {})
    plays_used = int(cur.get("plays_used") or 0)
    now = timezone.now()

    if start_play:
        if attempt.status != TestAttempt.Status.IN_PROGRESS:
            raise ValueError("Yakunlangan urinishda audio ishga tushirilmaydi.")
        if limit > 0 and plays_used >= limit:
            raise ValueError("Audio eshitish limiti tugadi.")
        plays_used += 1
        cur["plays_used"] = plays_used
        if not cur.get("started_at"):
            cur["started_at"] = now.isoformat()
        if duration_seconds is not None and duration_seconds > 0:
            cur["duration_seconds"] = round(float(duration_seconds), 2)
            ends_at = now + timedelta(seconds=float(duration_seconds) + LISTENING_GRACE_SECONDS)
            cur["reading_ends_at"] = ends_at.isoformat()
        cur["last_started_at"] = now.isoformat()
        cur["audio_play_limit"] = limit
        media_state[key] = cur
        attempt.media_state = media_state
        attempt.save(update_fields=["media_state"])

    remaining = max(0, limit - plays_used) if limit > 0 else None
    return {
        "attempt_id": attempt.id,
        "part_id": part.id,
        "audio_play_limit": limit,
        "plays_used": plays_used,
        "remaining_plays": remaining,
        "started_at": cur.get("started_at"),
        "reading_ends_at": cur.get("reading_ends_at"),
        "duration_seconds": cur.get("duration_seconds"),
        "grace_seconds": LISTENING_GRACE_SECONDS,
        "can_play": (limit == 0 or plays_used < limit),
        "server_time": now.isoformat(),
    }
