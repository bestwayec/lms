"""
AI Speaking Simulator Evaluation Service (apps/speaking/services.py).

Dual-model Architecture:
  1. Audio Stream & Transcription: fish-audio/s2.1-pro-free:free (via OpenRouter)
     with multimodal fallback.
  2. Speech Evaluation: deepseek/deepseek-r1-0528 (via OpenRouter/DeepSeek API)
     evaluating the 4 official IELTS criteria:
     - Fluency and Coherence (0.0 - 9.0)
     - Lexical Resource (0.0 - 9.0)
     - Grammatical Range and Accuracy (0.0 - 9.0)
     - Pronunciation (0.0 - 9.0)
     utilizing strict deduction scoring starting from Band 9.0 down.
"""

from __future__ import annotations

import base64
from decimal import Decimal, InvalidOperation
import json
import logging
import re
from typing import Any, Dict

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone
import httpx
from openai import OpenAI

from apps.core.ai_gateway import record_ai_usage
from apps.core.ai_health import AIUnavailable

from .audio_verify import inspect_uploaded_audio
from .models import SpeakingSubmission, SpeakingTopic

logger = logging.getLogger(__name__)

# Official UZBMB Multilevel Speaking conversion table (0.0..21.0 in 0.5 steps -> 0..75)
MULTILEVEL_SPEAKING_21_TO_75 = (
    0, 10, 11, 13, 15, 17, 19, 21, 23, 24, 26, 27, 29, 30, 32, 33, 35, 37, 38, 39, 40,
    42, 43, 45, 46, 47, 49, 50, 51, 52, 54, 56, 57, 59, 61, 63, 64, 65, 67, 69, 71, 73, 75,
)


def convert_multilevel_speaking_21_to_75(raw_total: float | Decimal) -> Decimal:
    """Convert raw Multilevel speaking total (0..21) to the 0..75 CEFR scale."""
    clamped = max(0.0, min(21.0, float(raw_total)))
    idx = int(round(clamped * 2.0))
    idx = max(0, min(len(MULTILEVEL_SPEAKING_21_TO_75) - 1, idx))
    return Decimal(str(MULTILEVEL_SPEAKING_21_TO_75[idx]))


def _round_to_half_band(score: float) -> Decimal:
    """IELTS rounding rule: round to nearest 0.5 or 0.0."""
    half = round(score * 2) / 2
    clamped = max(1.0, min(9.0, half))
    return Decimal(str(clamped))


def _get_openrouter_client(timeout: float = 60.0) -> OpenAI:
    """Build OpenAI client for OpenRouter models."""
    api_key = (
        getattr(settings, "DEEPSEEK_API_KEY", "")
        or getattr(settings, "OPENROUTER_API_KEY", "")
        or "sk-test-deepseek-key"
    ).strip()
    base_url = getattr(
        settings, "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
    ).strip()
    return OpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=httpx.Timeout(timeout, connect=10.0),
        max_retries=0,
        default_headers={
            "HTTP-Referer": getattr(
                settings, "OPENROUTER_SITE_URL", "https://grandec.uz"
            ),
            "X-Title": getattr(settings, "OPENROUTER_APP_NAME", "Grand Education LMS"),
        },
    )


def _process_audio_stream_fish_audio(audio_file, topic: SpeakingTopic) -> str | None:
    """
    Process candidate speech audio stream using fish-audio/s2.1-pro-free:free.
    Extracts high-fidelity speech transcription for IELTS examiner evaluation.
    """
    audio_model = getattr(
        settings, "AUDIO_STREAM_MODEL", "fish-audio/s2.1-pro-free:free"
    )
    api_key = (
        getattr(settings, "DEEPSEEK_API_KEY", "")
        or getattr(settings, "OPENROUTER_API_KEY", "")
    ).strip()

    if not api_key:
        return None

    try:
        audio_file.seek(0)
        raw_bytes = audio_file.read()
        audio_file.seek(0)
        b64_audio = base64.b64encode(raw_bytes).decode("utf-8")

        name = (getattr(audio_file, "name", "") or "").lower()
        ext = "wav" if name.endswith(".wav") else "mp3"

        client = _get_openrouter_client(timeout=45.0)
        response = client.chat.completions.create(
            model=audio_model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a speech audio recognition model. Transcribe the candidate's spoken speech verbatim.",
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": f"Transcribe this IELTS Speaking response for prompt: {topic.title}",
                        },
                        {
                            "type": "input_audio",
                            "input_audio": {"data": b64_audio, "format": ext},
                        },
                    ],
                },
            ],
            max_tokens=1500,
        )
        content = response.choices[0].message.content or ""
        if content.strip():
            logger.info("fish-audio transcription successful: %d chars", len(content))
            return content.strip()
    except Exception as exc:
        logger.warning(
            "fish-audio stream processing (%s), falling back to multimodal speech transcription",
            exc,
        )

    # Multimodal transcription fallback
    gemini_key = getattr(settings, "GEMINI_API_KEY", "") or getattr(
        settings, "GOOGLE_API_KEY", ""
    )
    if gemini_key:
        try:
            from google import genai

            client = genai.Client(api_key=gemini_key)
            audio_file.seek(0)
            audio_bytes = audio_file.read()
            audio_file.seek(0)

            name = (getattr(audio_file, "name", "") or "").lower()
            mime_type = "audio/wav" if name.endswith(".wav") else "audio/webm"
            res = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    genai.types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
                    "Transcribe this candidate speech recording verbatim. Return only the transcript text.",
                ],
            )
            if res.text:
                return res.text.strip()
        except Exception as e:
            logger.warning("Multimodal speech transcription fallback failed: %s", e)

    return None


def _evaluate_speech_deepseek_r1(
    transcript: str, topic: SpeakingTopic, duration_seconds: int = 60
) -> Dict[str, Any] | None:
    """
    Evaluate candidate's speech transcript using deepseek/deepseek-r1-0528.
    Applies official 4 IELTS Speaking criteria with deduction method starting from Band 9.0.
    """
    eval_model = getattr(settings, "AI_EVALUATION_MODEL", "deepseek/deepseek-r1-0528")
    api_key = (
        getattr(settings, "DEEPSEEK_API_KEY", "")
        or getattr(settings, "OPENROUTER_API_KEY", "")
    ).strip()

    if not api_key:
        return None

    bullets_str = ", ".join(topic.bullet_points) if topic.bullet_points else "None"
    system_prompt = (
        "You are a certified Senior IELTS Speaking Examiner powered by DeepSeek-R1.\n"
        "Evaluate the candidate's speech strictly according to the 4 official IELTS criteria:\n"
        "1. Fluency and Coherence (0.0 to 9.0)\n"
        "2. Lexical Resource (0.0 to 9.0)\n"
        "3. Grammatical Range and Accuracy (0.0 to 9.0)\n"
        "4. Pronunciation & Intonation (0.0 to 9.0)\n\n"
        "DEDUCTION SCORING METHOD:\n"
        "Start your evaluation from the maximum Band 9.0 for each criterion. Do NOT apply arbitrary artificial limits.\n"
        "Deduct marks for tangible flaws (hesitations, discourse repetition, lexical gaps, grammar slips, unnatural phrasing).\n"
        "Provide explicit, constructive reasons for every deduction, itemizing vocabulary upgrades and grammar corrections.\n\n"
        "Return STRICTLY valid JSON with no markdown wrapping, in this format:\n"
        "{\n"
        '  "transcript": "...",\n'
        '  "fluency_score": 7.0,\n'
        '  "lexical_score": 7.5,\n'
        '  "grammar_score": 7.0,\n'
        '  "pronunciation_score": 7.0,\n'
        '  "overall_band": 7.0,\n'
        '  "feedback": {\n'
        '    "summary": "...",\n'
        '    "fluency_feedback": "...",\n'
        '    "lexical_feedback": "...",\n'
        '    "grammar_feedback": "...",\n'
        '    "pronunciation_feedback": "...",\n'
        '    "vocabulary_suggestions": [\n'
        '      {"original": "...", "improved": "...", "explanation": "..."}\n'
        "    ],\n"
        '    "grammar_corrections": [\n'
        '      {"incorrect": "...", "corrected": "...", "rule": "..."}\n'
        "    ]\n"
        "  }\n"
        "}"
    )

    user_msg = (
        f"Candidate Speaking Task:\n"
        f"Topic: {topic.title}\n"
        f"Section: {topic.get_part_display()}\n"
        f"Prompt: {topic.prompt}\n"
        f"Cue Card Bullets: {bullets_str}\n"
        f"Duration: {duration_seconds} seconds\n\n"
        f"Candidate Speech Transcript:\n{transcript}"
    )

    try:
        client = _get_openrouter_client(timeout=60.0)
        response = client.chat.completions.create(
            model=eval_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.1,
            max_tokens=2500,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or ""
        clean_json = re.sub(
            r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.MULTILINE
        )
        data = json.loads(clean_json)
        if isinstance(data, dict) and "overall_band" in data:
            data.setdefault("transcript", transcript)
            logger.info("DeepSeek-R1 Speaking evaluation completed successfully")
            return data
    except Exception as exc:
        logger.warning("DeepSeek-R1 Speaking evaluation call failed: %s", exc)

    return None


def _parse_band(value: Any, *, allow_none: bool = False) -> Decimal | None:
    if value is None:
        if allow_none:
            return None
        raise AIUnavailable("Baholash javobida ballar yo'q yoki noto'g'ri", feature="speaking")
    if isinstance(value, bool):
        raise AIUnavailable("Baholash javobida ballar yo'q yoki noto'g'ri", feature="speaking")
    try:
        dec = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise AIUnavailable("Baholash javobida ballar yo'q yoki noto'g'ri", feature="speaking") from exc
    if not dec.is_finite() or dec < Decimal("0") or dec > Decimal("9"):
        raise AIUnavailable("Baholash javobida ball chegaradan tashqarida", feature="speaking")
    return dec


def _build_speaking_evaluation(
    audio_file,
    topic: SpeakingTopic,
    duration_seconds: int = 60,
    *,
    track: str | None = None,
    transcript_only: bool = False,
) -> dict[str, Any]:
    """Run STT + Rubric evaluation and return validated fields without mutating DB."""
    transcript = _process_audio_stream_fish_audio(audio_file, topic)
    eval_result: Dict[str, Any] | None = None
    if transcript:
        eval_result = _evaluate_speech_deepseek_r1(transcript, topic, duration_seconds)

    if not transcript:
        record_ai_usage(feature="speaking", model="stt", success=False)
        raise AIUnavailable("Nutqni matnga o'girib bo'lmadi", feature="speaking")
    if not eval_result or not isinstance(eval_result, dict):
        record_ai_usage(feature="speaking", model="deepseek-r1", success=False)
        raise AIUnavailable("Baholash javobi olinmadi", feature="speaking")

    for req_key in ("fluency_score", "lexical_score", "grammar_score", "pronunciation_score"):
        if req_key not in eval_result:
            raise AIUnavailable("Baholash javobida ballar yo'q yoki noto'g'ri", feature="speaking")

    fc = _parse_band(eval_result["fluency_score"])
    lr = _parse_band(eval_result["lexical_score"])
    gra = _parse_band(eval_result["grammar_score"])
    # Honest pronunciation policy: if evaluated strictly from transcript without acoustic
    # telemetry (explicit None or transcript_only flag without verified acoustic scoring),
    # never fabricate a pronunciation score.
    pr = _parse_band(eval_result["pronunciation_score"], allow_none=True)
    if transcript_only and not eval_result.get("acoustic_verified"):
        pr = None

    assert fc is not None and lr is not None and gra is not None
    if pr is not None:
        overall: Decimal | None = _round_to_half_band(float(fc + lr + gra + pr) / 4.0)
        partial_estimate: Decimal | None = None
    else:
        # Honest Speaking Policy: Never present a 3-criterion transcript average as a complete IELTS/Multilevel Speaking band.
        # Store the partial 3-criterion estimate separately in feedback and keep overall_band/final_score pending (None)
        # until acoustic pronunciation telemetry or qualified teacher review is provided.
        overall = None
        partial_estimate = _round_to_half_band(float(fc + lr + gra) / 3.0)

    resolved_track = track or (
        SpeakingSubmission.Track.CEFR_MULTILEVEL
        if topic.part == SpeakingTopic.PartChoice.MULTILEVEL
        else SpeakingSubmission.Track.IELTS
    )
    feedback = dict(eval_result.get("feedback") or {})
    if pr is None:
        feedback.setdefault("pronunciation_status", "not_measured_from_transcript")
        feedback.setdefault(
            "pronunciation_feedback",
            "Talaffuz faqat matn asosida taxmin qilinmadi; audio akustik baholash yoki ustoz tekshiruvi talab etiladi.",
        )
        feedback["assessment_scope"] = "partial_transcript_only"
        feedback["is_partial_estimate"] = True
        feedback["partial_band_estimate"] = float(partial_estimate) if partial_estimate is not None else None
        feedback["acoustic_fluency_verified"] = False
        feedback["requires_acoustic_or_teacher"] = True
    else:
        feedback["assessment_scope"] = "complete_4_criteria"
        feedback["is_partial_estimate"] = False
        feedback["acoustic_fluency_verified"] = True
        feedback["requires_acoustic_or_teacher"] = False

    task_scores: dict[str, Any] = {}
    final_score: Decimal | None = overall
    rubric_version = "ielts_speaking_v1"
    if resolved_track == SpeakingSubmission.Track.CEFR_MULTILEVEL:
        rubric_version = "uzbmb_multilevel_speaking_2026_v2"
        if overall is not None:
            avg_ratio = float(overall) / 9.0
            p11 = round(min(5.0, max(0.0, avg_ratio * 5.0)) * 2) / 2
            p12 = round(min(5.0, max(0.0, avg_ratio * 5.0)) * 2) / 2
            p2 = round(min(5.0, max(0.0, avg_ratio * 5.0)) * 2) / 2
            p3 = round(min(6.0, max(0.0, avg_ratio * 6.0)) * 2) / 2
            raw_21 = p11 + p12 + p2 + p3
            scaled_75 = convert_multilevel_speaking_21_to_75(raw_21)
            task_scores = {
                "1.1": p11,
                "1.2": p12,
                "2": p2,
                "3": p3,
                "raw_total": raw_21,
                "raw_max": 21,
                "scaled_75": float(scaled_75),
            }
            final_score = scaled_75
        else:
            task_scores = {
                "is_partial_estimate": True,
                "partial_band_estimate": float(partial_estimate) if partial_estimate is not None else None,
            }
            final_score = None

    record_ai_usage(feature="speaking", model=getattr(settings, "AI_EVALUATION_MODEL", "deepseek-r1"), success=True)
    return {
        "transcript": transcript,
        "fluency_score": fc,
        "lexical_score": lr,
        "grammar_score": gra,
        "pronunciation_score": pr,
        "overall_band": overall,
        "final_score": final_score,
        "track": resolved_track,
        "rubric_version": rubric_version,
        "task_scores": task_scores,
        "feedback": feedback,
    }


def apply_speaking_evaluation(sub: SpeakingSubmission, *, expected_seconds: int | None = None, transcript_only: bool = False) -> SpeakingSubmission:
    """Evaluate an already-persisted SpeakingSubmission (used by async Celery worker)."""
    from apps.accounts.gamification import record_user_activity

    evaluated = _build_speaking_evaluation(
        sub.audio_file,
        sub.topic,
        sub.duration_seconds or 60,
        track=sub.track,
        transcript_only=transcript_only,
    )
    with transaction.atomic():
        for field, val in evaluated.items():
            setattr(sub, field, val)
        sub.status = SpeakingSubmission.Status.COMPLETED
        sub.save()

    record_user_activity(sub.user, xp_amount=30, activity_type="speaking")
    try:
        from apps.notifications.tasks import broadcast_speaking_result_to_groups

        broadcast_speaking_result_to_groups(sub)
    except Exception as exc:
        logger.warning("Speaking group broadcast skipped/failed: %s", exc)
    return sub


def evaluate_speaking_submission(
    audio_file,
    topic_id: int,
    user,
    duration_seconds: int = 60,
    *,
    track: str | None = None,
    audio_meta: dict[str, Any] | None = None,
    transcript_only: bool = False,
) -> SpeakingSubmission:
    """
    Synchronous Speaking evaluation pipeline.
    Creates no DB row if STT or evaluation fails so failed AI calls never persist fake grades.
    """
    from apps.accounts.gamification import record_user_activity

    topic = SpeakingTopic.objects.filter(pk=topic_id).first()
    if not topic:
        raise ValueError(f"Speaking mavzusi topilmadi: {topic_id}")

    if audio_meta is None:
        audio_meta = inspect_uploaded_audio(audio_file)

    evaluated = _build_speaking_evaluation(
        audio_file,
        topic,
        duration_seconds,
        track=track,
        transcript_only=transcript_only,
    )

    sub = SpeakingSubmission.objects.create(
        user=user,
        topic=topic,
        audio_file=audio_file,
        duration_seconds=audio_meta.get("decoded_seconds") or duration_seconds,
        decoded_duration_ms=audio_meta.get("decoded_duration_ms"),
        audio_hash=audio_meta.get("audio_hash", ""),
        is_verified_audio=bool(audio_meta.get("is_verified_audio")),
        transcript=evaluated["transcript"],
        fluency_score=evaluated["fluency_score"],
        lexical_score=evaluated["lexical_score"],
        grammar_score=evaluated["grammar_score"],
        pronunciation_score=evaluated["pronunciation_score"],
        overall_band=evaluated["overall_band"],
        final_score=evaluated["final_score"],
        track=evaluated["track"],
        rubric_version=evaluated["rubric_version"],
        task_scores=evaluated["task_scores"],
        feedback=evaluated["feedback"],
        status=SpeakingSubmission.Status.COMPLETED,
    )

    record_user_activity(user, xp_amount=30, activity_type="speaking")
    try:
        from apps.notifications.tasks import broadcast_speaking_result_to_groups

        broadcast_speaking_result_to_groups(sub)
    except Exception as exc:
        logger.warning("Speaking group broadcast skipped/failed: %s", exc)

    return sub


def can_review_speaking_submission(user, submission: SpeakingSubmission) -> bool:
    """Strict RBAC boundary for Teacher Speaking Review (requires explicit workflow grant)."""
    from apps.accounts.access import is_platform_admin
    from apps.courses.models import StudentGroup

    if not user or not user.is_authenticated or not user.is_active:
        return False
    if is_platform_admin(user):
        return True
    if getattr(user, "role", None) != "teacher":
        return False
    if not (
        submission.teacher_review_requested
        or submission.status == SpeakingSubmission.Status.PENDING_TEACHER
        or submission.teacher_reviewed_by_id == user.pk
    ):
        return False
    return submission.user.student_groups.filter(
        teacher=user,
        status=StudentGroup.Status.ACTIVE,
    ).exists() or _is_linked_mock_teacher(user, submission)


def _is_linked_mock_teacher(user, submission: SpeakingSubmission) -> bool:
    """Allow teacher access when submission belongs to a Full Mock test owned/taught by teacher."""
    from apps.tests.models import TestAttempt

    for att in TestAttempt.objects.select_related("test", "test__course").filter(
        student=submission.user,
        media_state__speaking_submissions__isnull=False,
    )[:20]:
        mapping = (att.media_state or {}).get("speaking_submissions") or {}
        if isinstance(mapping, dict) and submission.pk in {int(v) for v in mapping.values() if str(v).isdigit()}:
            t = att.test
            if t.created_by_id == user.id or (t.course_id and t.course.teacher_id == user.id):
                return True
    return False


class TeacherSpeakingReviewService:
    @staticmethod
    @transaction.atomic
    def submit_review(
        submission: SpeakingSubmission,
        teacher,
        score: float | Decimal,
        comments: str = "",
    ) -> SpeakingSubmission:
        locked = SpeakingSubmission.objects.select_for_update().select_related("user", "topic").get(pk=submission.pk)
        if not can_review_speaking_submission(teacher, locked):
            raise PermissionDenied("Bu speaking topshirig'ini tekshirishga ruxsatingiz yo'q.")

        val = Decimal(str(score))
        if locked.track == SpeakingSubmission.Track.CEFR_MULTILEVEL:
            if val < Decimal("0") or val > Decimal("75"):
                raise ValueError("Multi-level Speaking bali 0–75 oralig'ida bo'lishi kerak.")
            effective = val.quantize(Decimal("0.1"))
        else:
            if val < Decimal("0") or val > Decimal("9") or (val * 2) % 1 != 0:
                raise ValueError("IELTS Speaking bali 0.0–9.0 oralig'ida (0.5 qadam) bo'lishi kerak.")
            effective = val.quantize(Decimal("0.1"))
            locked.overall_band = effective

        locked.teacher_reviewed_by = teacher
        locked.teacher_score = effective
        locked.final_score = effective
        locked.teacher_comments = (comments or "").strip()[:3000]
        locked.teacher_reviewed_at = timezone.now()
        locked.teacher_review_requested = False
        locked.feedback = {
            **(locked.feedback or {}),
            "assessment_scope": "teacher_finalized",
            "is_partial_estimate": False,
        }
        locked.status = SpeakingSubmission.Status.COMPLETED
        locked.save()

        _try_finalize_linked_mock_attempts(speaking_submission_id=locked.pk)
        return locked


def _extract_speaking_sub_ids(mapping: Any) -> set[int]:
    ids: set[int] = set()
    if not isinstance(mapping, dict):
        return ids
    for v in mapping.values():
        raw_id = v.get("submission_id") if isinstance(v, dict) else v
        if str(raw_id or "").isdigit():
            ids.add(int(raw_id))
    return ids


def _try_finalize_linked_mock_attempts(
    *,
    speaking_submission_id: int | None = None,
    essay_submission_id: int | None = None,
) -> None:
    """Best-effort finalization of PENDING_GRADING mock attempts when a rated section completes."""
    from apps.tests.models import ExamWrittenBridge, TestAttempt
    from apps.tests.services import SubmitAttemptService

    target_attempts: list[TestAttempt] = []
    if essay_submission_id is not None:
        att_ids = list(
            ExamWrittenBridge.objects.filter(essay_submission_id=essay_submission_id).values_list("attempt_id", flat=True)
        )
        target_attempts.extend(
            TestAttempt.objects.select_related("student").filter(
                id__in=att_ids, status=TestAttempt.Status.PENDING_GRADING
            )
        )
    if speaking_submission_id is not None:
        for att in TestAttempt.objects.select_related("student").filter(status=TestAttempt.Status.PENDING_GRADING)[:50]:
            mapping = (att.media_state or {}).get("speaking_submissions") or {}
            if speaking_submission_id in _extract_speaking_sub_ids(mapping):
                target_attempts.append(att)

    seen: set[int] = set()
    for att in target_attempts:
        if att.id in seen:
            continue
        seen.add(att.id)
        try:
            SubmitAttemptService.finalize_pending_grading(attempt_id=att.id, student=att.student)
        except ValueError:
            # Other sections (Writing or Speaking) are still pending grading.
            pass
        except Exception:
            logger.exception("Auto-finalize attempt=%s failed cleanly", att.id)
