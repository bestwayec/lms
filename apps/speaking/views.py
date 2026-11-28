"""
Speaking app views (apps/speaking/views.py).

Endpoints:
    GET  /api/v1/speaking/topics/            — List active IELTS/Multi-level topics
    GET  /api/v1/speaking/topics/<id>/       — Topic detail with Cue Card bullets
    POST /api/v1/speaking/submit/            — Upload audio, get instant 4-criteria AI evaluation
    GET  /api/v1/speaking/submissions/<id>/  — Detailed score card & feedback
    GET  /api/v1/speaking/my-submissions/    — User history
"""

from __future__ import annotations

import logging
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from rest_framework import permissions, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts.access import is_platform_admin
from apps.core.ai_health import AIUnavailable, record_ai_failure, record_ai_success
from apps.payments.ai_quota import consume_feature_cap, refund_feature_cap

from .audio_verify import InvalidSpeakingAudio, inspect_uploaded_audio
from .models import SpeakingSubmission, SpeakingTopic
from .services import (
    TeacherSpeakingReviewService,
    can_review_speaking_submission,
    evaluate_speaking_submission,
)

logger = logging.getLogger(__name__)


def _serialize_topic(topic: SpeakingTopic) -> dict:
    return {
        "id": topic.id,
        "title": topic.title,
        "subject": topic.subject,
        "part": topic.part,
        "part_label": topic.get_part_display(),
        "prompt": topic.prompt,
        "bullet_points": topic.bullet_points,
        "follow_up_questions": topic.follow_up_questions,
        "prep_time_seconds": topic.prep_time_seconds,
        "speak_time_seconds": topic.speak_time_seconds,
        "difficulty": topic.difficulty,
        "difficulty_label": topic.get_difficulty_display(),
    }


def _audio_path(sub: SpeakingSubmission) -> str | None:
    """Authenticated download path; the recording is never exposed as a /media/ URL."""
    if not sub.audio_file:
        return None
    from apps.webapi.views_private_files import speaking_audio_path

    return speaking_audio_path(sub.pk)


def _serialize_submission(sub: SpeakingSubmission) -> dict:
    fb = sub.feedback or {}
    return {
        "id": sub.id,
        "topic_id": sub.topic_id,
        "topic_title": sub.topic.title if sub.topic else "",
        "part": sub.topic.part if sub.topic else "",
        "part_label": sub.topic.get_part_display() if sub.topic else "",
        "track": getattr(sub, "track", "ielts"),
        "rubric_version": getattr(sub, "rubric_version", "ielts_speaking_v1"),
        "audio_url": _audio_path(sub),
        "duration_seconds": sub.duration_seconds,
        "decoded_duration_ms": getattr(sub, "decoded_duration_ms", None),
        "audio_hash": getattr(sub, "audio_hash", ""),
        "is_verified_audio": bool(getattr(sub, "is_verified_audio", False)),
        "transcript": sub.transcript,
        "fluency_score": float(sub.fluency_score) if sub.fluency_score is not None else None,
        "lexical_score": float(sub.lexical_score) if sub.lexical_score is not None else None,
        "grammar_score": float(sub.grammar_score) if sub.grammar_score is not None else None,
        "pronunciation_score": float(sub.pronunciation_score) if sub.pronunciation_score is not None else None,
        "overall_band": float(sub.overall_band) if sub.overall_band is not None else None,
        "final_score": float(sub.final_score) if getattr(sub, "final_score", None) is not None else (float(sub.overall_band) if sub.overall_band is not None else None),
        "is_partial_estimate": bool(fb.get("is_partial_estimate", sub.overall_band is None and sub.final_score is None and sub.fluency_score is not None)),
        "partial_band_estimate": fb.get("partial_band_estimate"),
        "assessment_scope": fb.get("assessment_scope") or ("teacher_finalized" if getattr(sub, "teacher_reviewed_at", None) else "complete_4_criteria"),
        "task_scores": getattr(sub, "task_scores", {}) or {},
        "feedback": fb,
        "teacher_review_requested": bool(getattr(sub, "teacher_review_requested", False)),
        "teacher_score": float(sub.teacher_score) if getattr(sub, "teacher_score", None) is not None else None,
        "teacher_comments": getattr(sub, "teacher_comments", ""),
        "teacher_reviewed_at": sub.teacher_reviewed_at.isoformat() if getattr(sub, "teacher_reviewed_at", None) else None,
        "status": sub.status,
        "created_at": sub.created_at.isoformat(),
    }


class SpeakingTopicsListView(APIView):
    """GET /api/v1/speaking/topics/"""

    permission_classes = [permissions.AllowAny]

    def get(self, request: Request) -> Response:
        qs = SpeakingTopic.objects.filter(is_active=True)
        part = request.query_params.get("part", "").strip()
        if part:
            qs = qs.filter(part=part)

        # Seed standard IELTS speaking topics if empty
        if not qs.exists() and not SpeakingTopic.objects.exists():
            _seed_default_speaking_topics()
            qs = SpeakingTopic.objects.filter(is_active=True)
            if part:
                qs = qs.filter(part=part)

        data = [_serialize_topic(t) for t in qs]
        return Response(
            {"count": len(data), "results": data}, status=status.HTTP_200_OK
        )


class SpeakingTopicDetailView(APIView):
    """GET /api/v1/speaking/topics/<id>/"""

    permission_classes = [permissions.AllowAny]

    def get(self, request: Request, pk: int) -> Response:
        topic = SpeakingTopic.objects.filter(pk=pk, is_active=True).first()
        if not topic:
            return Response(
                {"error": "Speaking mavzusi topilmadi."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(_serialize_topic(topic), status=status.HTTP_200_OK)


class SpeakingSubmitView(APIView):
    """
    POST /api/v1/speaking/submit/
    Multipart form-data: `audio`, `topic_id`, optional `duration_seconds`.
    """

    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "speaking-submit"

    #: Largest accepted recording and the clip lengths we grade.
    MAX_AUDIO_BYTES = 25 * 1024 * 1024
    MIN_SECONDS = 5
    MAX_SECONDS = 15 * 60

    def post(self, request: Request) -> Response:
        audio_file = request.FILES.get("audio")
        if not audio_file:
            return Response(
                {"ok": False, "error": "Ovoz yozuvi (audio) yuklanmadi."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        content_type = str(getattr(audio_file, "content_type", "") or "").lower()
        if not (content_type.startswith("audio/") or content_type in ("video/webm", "application/octet-stream")):
            return Response(
                {"ok": False, "code": "not_audio", "error": "Faqat audio fayl yuklash mumkin."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if audio_file.size > self.MAX_AUDIO_BYTES:
            return Response(
                {"ok": False, "code": "file_too_large", "error": "Audio fayl juda katta (25 MB gacha)."},
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )

        topic_id_raw = request.data.get("topic_id")
        if not topic_id_raw or not str(topic_id_raw).isdigit():
            return Response(
                {"ok": False, "error": "Mavzu ID si (topic_id) ko'rsatilmadi."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        topic_id = int(topic_id_raw)

        duration_raw = request.data.get("duration_seconds", "60")
        duration = int(duration_raw) if str(duration_raw).isdigit() else 60
        duration = max(self.MIN_SECONDS, min(duration, self.MAX_SECONDS))

        expected_raw = request.data.get("expected_seconds")
        expected_seconds = int(expected_raw) if str(expected_raw or "").isdigit() else None
        strict_decode = str(request.data.get("strict_decode", "")).lower() in ("1", "true")
        transcript_only = str(request.data.get("transcript_only", "")).lower() in ("1", "true")
        track_raw = str(request.data.get("track", "") or "").strip().lower()
        track = track_raw if track_raw in ("ielts", "cefr_multilevel") else None

        try:
            audio_meta = inspect_uploaded_audio(
                audio_file,
                expected_seconds=expected_seconds,
                strict_decode=strict_decode,
            )
        except InvalidSpeakingAudio as exc:
            return Response(
                {"ok": False, "code": exc.code, "error": exc.message},
                status=status.HTTP_400_BAD_REQUEST,
            )

        allowed, limit = consume_feature_cap(request.user, "speaking")
        if not allowed:
            return Response(
                {"ok": False, "code": "daily_limit", "limit": limit, "upgrade_url": "/pricing",
                 "error": "Bugungi Speaking limitingiz tugadi."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        async_mode = str(request.data.get("async") or request.data.get("async_mode") or "").lower() in ("1", "true")
        if async_mode:
            topic = SpeakingTopic.objects.filter(pk=topic_id).first()
            if not topic:
                refund_feature_cap(request.user, "speaking")
                return Response(
                    {"ok": False, "error": "Speaking mavzusi topilmadi."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            resolved_track = track or (
                SpeakingSubmission.Track.CEFR_MULTILEVEL
                if topic.part == SpeakingTopic.PartChoice.MULTILEVEL
                else SpeakingSubmission.Track.IELTS
            )
            sub = SpeakingSubmission.objects.create(
                user=request.user,
                topic=topic,
                audio_file=audio_file,
                duration_seconds=audio_meta.get("decoded_seconds") or duration,
                decoded_duration_ms=audio_meta.get("decoded_duration_ms"),
                audio_hash=audio_meta.get("audio_hash", ""),
                is_verified_audio=bool(audio_meta.get("is_verified_audio")),
                track=resolved_track,
                rubric_version=(
                    "uzbmb_multilevel_speaking_2026_v2"
                    if resolved_track == SpeakingSubmission.Track.CEFR_MULTILEVEL
                    else "ielts_speaking_v1"
                ),
                status=SpeakingSubmission.Status.EVALUATING,
            )
            from .tasks import evaluate_speaking_submission_task

            evaluate_speaking_submission_task.delay(sub.pk, transcript_only=transcript_only)
            sub.refresh_from_db()
            return Response(
                {"ok": True, "async": True, "submission": _serialize_submission(sub)},
                status=status.HTTP_202_ACCEPTED,
            )

        try:
            sub = evaluate_speaking_submission(
                audio_file=audio_file,
                topic_id=topic_id,
                user=request.user,
                duration_seconds=duration,
                track=track,
                audio_meta=audio_meta,
                transcript_only=transcript_only,
            )
            record_ai_success("speaking")
            return Response(
                {"ok": True, "submission": _serialize_submission(sub)},
                status=status.HTTP_201_CREATED,
            )
        except AIUnavailable as exc:
            # Not graded: no band, no transcript, no XP, and today's call is returned.
            refund_feature_cap(request.user, "speaking")
            record_ai_failure("speaking", exc)
            logger.warning("Speaking not graded: %s", exc)
            return Response(
                {"ok": False, "code": "not_graded", "error": AIUnavailable.user_message},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except Exception as e:
            refund_feature_cap(request.user, "speaking")
            logger.exception("Speaking evaluation failed: %s", e)
            return Response(
                {"ok": False, "code": "not_graded", "error": AIUnavailable.user_message},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class SpeakingSubmissionDetailView(APIView):
    """GET /api/v1/speaking/submissions/<id>/"""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request, pk: int) -> Response:
        sub = SpeakingSubmission.objects.filter(pk=pk, user=request.user).first()
        if not sub:
            is_admin = (
                getattr(request.user, "role", None) == "admin" or request.user.is_superuser
            )
            if is_admin:
                sub = SpeakingSubmission.objects.filter(pk=pk).first()
            elif getattr(request.user, "role", None) == "teacher":
                sub = (
                    SpeakingSubmission.objects.filter(
                        pk=pk, user__student_groups__teacher=request.user
                    )
                    .distinct()
                    .first()
                )

        if not sub:
            return Response(
                {"error": "Topshiriq topilmadi."}, status=status.HTTP_404_NOT_FOUND
            )

        return Response(_serialize_submission(sub), status=status.HTTP_200_OK)


class MySpeakingSubmissionsView(APIView):
    """GET /api/v1/speaking/my-submissions/"""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request) -> Response:
        subs = (
            SpeakingSubmission.objects.filter(user=request.user)
            .select_related("topic")
            .order_by("-created_at")[:20]
        )
        data = [_serialize_submission(s) for s in subs]
        return Response(
            {"count": len(data), "results": data}, status=status.HTTP_200_OK
        )


class SpeakingRequestTeacherReviewView(APIView):
    """POST /api/v1/speaking/submissions/<id>/request-review/"""

    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [JSONParser]

    def post(self, request: Request, pk: int) -> Response:
        sub = SpeakingSubmission.objects.filter(pk=pk, user=request.user).select_related("topic").first()
        if not sub:
            return Response({"error": "Topshiriq topilmadi."}, status=status.HTTP_404_NOT_FOUND)
        if sub.status == SpeakingSubmission.Status.EVALUATING:
            return Response(
                {"error": "AI baholash yakunlanishini kuting."},
                status=status.HTTP_409_CONFLICT,
            )
        sub.teacher_review_requested = True
        if sub.teacher_reviewed_at is None:
            sub.status = SpeakingSubmission.Status.PENDING_TEACHER
        sub.save(update_fields=["teacher_review_requested", "status"])
        return Response({"ok": True, "submission": _serialize_submission(sub)}, status=status.HTTP_200_OK)


class TeacherSpeakingQueueView(APIView):
    """GET /api/v1/speaking/teacher/queue/"""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request) -> Response:
        if not (
            getattr(request.user, "role", None) == "teacher" or is_platform_admin(request.user)
        ):
            raise PermissionDenied("Faqat o'qituvchilar va adminlar uchun.")

        qs = SpeakingSubmission.objects.select_related("user", "topic").filter(
            Q(teacher_review_requested=True) | Q(status=SpeakingSubmission.Status.PENDING_TEACHER)
        )
        if not is_platform_admin(request.user):
            qs = qs.filter(user__student_groups__teacher=request.user).distinct()

        pending = qs.filter(teacher_reviewed_at__isnull=True).order_by("-created_at")[:50]
        reviewed = qs.filter(teacher_reviewed_at__isnull=False).order_by("-teacher_reviewed_at")[:20]

        def _card(s: SpeakingSubmission) -> dict:
            d = _serialize_submission(s)
            d["student_name"] = s.user.get_full_name() or s.user.email
            d["student_email"] = s.user.email
            return d

        return Response(
            {
                "pending": [_card(s) for s in pending],
                "reviewed": [_card(s) for s in reviewed],
            },
            status=status.HTTP_200_OK,
        )


class TeacherSpeakingReviewView(APIView):
    """POST /api/v1/speaking/teacher/<id>/review/"""

    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [JSONParser]

    def post(self, request: Request, pk: int) -> Response:
        sub = SpeakingSubmission.objects.select_related("user", "topic").filter(pk=pk).first()
        if not sub:
            return Response({"error": "Topshiriq topilmadi."}, status=status.HTTP_404_NOT_FOUND)
        if not can_review_speaking_submission(request.user, sub):
            raise PermissionDenied("Bu speaking topshirig'ini tekshirishga ruxsatingiz yo'q.")

        raw_score = request.data.get("score")
        if raw_score is None or isinstance(raw_score, bool):
            return Response({"detail": "score majburiy."}, status=status.HTTP_400_BAD_REQUEST)
        comments = str(request.data.get("comments") or request.data.get("teacher_comments") or "")
        try:
            updated = TeacherSpeakingReviewService.submit_review(
                sub, request.user, score=raw_score, comments=comments
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"ok": True, "submission": _serialize_submission(updated)}, status=status.HTTP_200_OK)


def _seed_default_speaking_topics():
    """Initial seed topics for IELTS Part 1, Part 2 (Cue Card), and Part 3."""
    SpeakingTopic.objects.get_or_create(
        title="Hometown & Daily Life",
        part=SpeakingTopic.PartChoice.PART1,
        defaults={
            "prompt": "Let's talk about your hometown. Where is it located? What do you like most about living there? Would you like to live there in the future?",
            "bullet_points": [
                "Where your hometown is located",
                "What its best features are",
                "How it has changed recently",
            ],
            "prep_time_seconds": 15,
            "speak_time_seconds": 60,
            "difficulty": SpeakingTopic.Difficulty.EASY,
        },
    )
    SpeakingTopic.objects.get_or_create(
        title="Describe an Influential Book You Have Read",
        part=SpeakingTopic.PartChoice.PART2,
        defaults={
            "prompt": "Describe a book that has had a powerful influence on your thinking or life choices.",
            "bullet_points": [
                "What the book is and who wrote it",
                "What the main message or story is",
                "When and why you read it",
                "Explain why it had such a strong impact on you",
            ],
            "prep_time_seconds": 60,
            "speak_time_seconds": 120,
            "difficulty": SpeakingTopic.Difficulty.MEDIUM,
        },
    )
    SpeakingTopic.objects.get_or_create(
        title="Describe an Important Decision You Made",
        part=SpeakingTopic.PartChoice.PART2,
        defaults={
            "prompt": "Describe an important choice or life decision you made in the past few years.",
            "bullet_points": [
                "What the decision was",
                "When you had to make it",
                "How you felt while deciding",
                "Explain whether it turned out to be the right decision",
            ],
            "prep_time_seconds": 60,
            "speak_time_seconds": 120,
            "difficulty": SpeakingTopic.Difficulty.MEDIUM,
        },
    )
    SpeakingTopic.objects.get_or_create(
        title="Artificial Intelligence & Future Education",
        part=SpeakingTopic.PartChoice.PART3,
        defaults={
            "prompt": "How do you think emerging AI tools will reshape traditional classroom learning over the next decade? Can AI ever replace empathetic human educators?",
            "follow_up_questions": [
                "Do teachers still remain essential in the age of generative AI?",
                "How can schools ensure digital literacy for underprivileged students?",
            ],
            "prep_time_seconds": 15,
            "speak_time_seconds": 90,
            "difficulty": SpeakingTopic.Difficulty.HARD,
        },
    )
