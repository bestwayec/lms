"""English Learning Center API (Phase 01).

Provides the track-scoped English learning hub payload (IELTS Academic, IELTS
General Training, CEFR Multi-level BMB, General English) backed strictly by
real database records and user progress.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from django.db.models import Count, Q
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Profile
from apps.courses.models import Homework, HomeworkSubmission
from apps.essays.models import EssaySubmission, EssayTopic
from apps.results.models import Result
from apps.speaking.models import SpeakingSubmission, SpeakingTopic
from apps.tests.models import ExamSection, StudentAnswer, Test, TestAttempt
from apps.vocabulary.models import StudentWordMistake, VocabularyPack

STUDY_MODES = (
    {"code": "practice", "label": "Practice Mode", "timed": False},
    {"code": "timed_practice", "label": "Timed Practice", "timed": True},
    {"code": "full_mock", "label": "Full Mock Exam", "timed": True},
    {"code": "assignment", "label": "Teacher Assignment", "timed": False},
    {"code": "review", "label": "Review & Mistakes", "timed": False},
)

TRACK_CATALOG = (
    {
        "code": Profile.EnglishTrack.IELTS_ACADEMIC,
        "label": "IELTS Academic",
        "short_label": "Academic",
        "scale": "Band 1.0–9.0",
        "description": "University & academic IELTS: Listening (40), Academic Reading (40), Task 1 Data/Chart + Task 2 Essay, Speaking 1–3.",
        "exam_types": [Test.ExamType.IELTS_ACADEMIC, Test.ExamType.GENERAL],
    },
    {
        "code": Profile.EnglishTrack.IELTS_GENERAL,
        "label": "IELTS General Training",
        "short_label": "General",
        "scale": "Band 1.0–9.0",
        "description": "Work & migration IELTS: Listening (40), General Reading (stricter raw curve), Task 1 Letter + Task 2 Essay, Speaking 1–3.",
        "exam_types": [Test.ExamType.IELTS_GENERAL, Test.ExamType.IELTS_ACADEMIC, Test.ExamType.GENERAL],
    },
    {
        "code": Profile.EnglishTrack.CEFR_MULTILEVEL,
        "label": "CEFR Multi-level (BMB)",
        "short_label": "Multi-level",
        "scale": "BMB 0–75 (B1–C1)",
        "description": "Uzbekistan BMB/UZBMB Multi-level format: Listening 35Q (6 parts), Reading 35Q (5 parts), Writing 5/5/6, Speaking 1.1/1.2/2/3.",
        "exam_types": [Test.ExamType.CEFR_MULTILEVEL, Test.ExamType.GENERAL],
    },
    {
        "code": Profile.EnglishTrack.GENERAL_ENGLISH,
        "label": "General English",
        "short_label": "General EN",
        "scale": "CEFR A2–C1",
        "description": "Balanced everyday fluency across Listening, Reading, Grammar Studio, Vocabulary Pronunciation and AI Speaking.",
        "exam_types": [Test.ExamType.GENERAL, Test.ExamType.CEFR_MULTILEVEL],
    },
)

TRACK_CODES = {t["code"] for t in TRACK_CATALOG}
FINISHED_ATTEMPT_STATUSES = (
    TestAttempt.Status.COMPLETED,
    TestAttempt.Status.PENDING_GRADING,
    TestAttempt.Status.TIMEOUT,
)


def _track_exam_types(track: str) -> list[str]:
    for item in TRACK_CATALOG:
        if item["code"] == track:
            return list(item["exam_types"])
    return [Test.ExamType.IELTS_ACADEMIC, Test.ExamType.GENERAL]


def _serialize_test_card(test: Test) -> dict[str, Any]:
    sec_codes = [s.code.upper() for s in test.sections.all() if s.code]
    return {
        "id": test.id,
        "title": test.title,
        "exam_type": test.exam_type,
        "assessment_category": test.assessment_category,
        "time_limit_minutes": test.time_limit_minutes,
        "question_count": getattr(test, "counted_q", None) if getattr(test, "counted_q", None) is not None else test.total_questions,
        "difficulty": test.difficulty,
        "has_audio": bool(test.audio_url or "LISTENING" in sec_codes),
        "sections": sec_codes,
        "mock_code": test.mock_code or "",
    }


def _resume_item(user) -> dict[str, Any] | None:
    att = (
        TestAttempt.objects.filter(
            student=user,
            status=TestAttempt.Status.IN_PROGRESS,
            test__subject="english",
            is_preview=False,
        )
        .select_related("test")
        .order_by("-started_at")
        .first()
    )
    if att:
        return {
            "kind": "test",
            "id": att.id,
            "test_id": att.test_id,
            "title": att.test.title,
            "started_at": att.started_at.isoformat() if att.started_at else None,
            "route": f"/take/{att.id}",
        }
    draft_essay = (
        EssaySubmission.objects.filter(
            student=user,
            topic__subject="english",
            status=EssaySubmission.Status.DRAFT,
        )
        .select_related("topic")
        .order_by("-updated_at")
        .first()
    )
    if draft_essay:
        return {
            "kind": "essay",
            "id": draft_essay.id,
            "topic_id": draft_essay.topic_id,
            "title": draft_essay.topic.title if draft_essay.topic else draft_essay.custom_title or "English Writing",
            "updated_at": draft_essay.updated_at.isoformat() if draft_essay.updated_at else None,
            "route": f"/essays/write/{draft_essay.topic_id}" if draft_essay.topic_id else "/essays",
        }
    return None


def _build_skill_progress(user) -> dict[str, Any]:
    eng_results = list(
        Result.objects.filter(
            student=user,
            test__subject="english",
            attempt__is_preview=False,
        )
        .select_related("test", "attempt")
        .prefetch_related("section_scores")
        .order_by("-calculated_at")[:30]
    )
    listening_scores: list[float] = []
    reading_scores: list[float] = []
    for res in eng_results:
        sec_map = {s.section_code.upper(): s for s in res.section_scores.all()}
        if "LISTENING" in sec_map and float(sec_map["LISTENING"].maximum) > 0:
            listening_scores.append(
                round(float(sec_map["LISTENING"].earned) * 100.0 / float(sec_map["LISTENING"].maximum), 1)
            )
        if "READING" in sec_map and float(sec_map["READING"].maximum) > 0:
            reading_scores.append(
                round(float(sec_map["READING"].earned) * 100.0 / float(sec_map["READING"].maximum), 1)
            )

    eng_essays = EssaySubmission.objects.filter(
        student=user,
        topic__subject="english",
        status__in=(
            EssaySubmission.Status.GRADED,
            EssaySubmission.Status.AI_EVALUATED,
            EssaySubmission.Status.TEACHER_REVIEWED,
        ),
    ).order_by("-updated_at")
    latest_essay = eng_essays.first()

    eng_speaking = SpeakingSubmission.objects.filter(
        user=user,
        status=SpeakingSubmission.Status.COMPLETED,
    ).order_by("-created_at")
    latest_speaking = eng_speaking.first()

    word_total = StudentWordMistake.objects.filter(student=user).count()
    word_mastered = StudentWordMistake.objects.filter(student=user, is_mastered=True).count()

    return {
        "listening": {
            "attempts": len(listening_scores),
            "best_pct": max(listening_scores) if listening_scores else None,
            "latest_pct": listening_scores[0] if listening_scores else None,
        },
        "reading": {
            "attempts": len(reading_scores),
            "best_pct": max(reading_scores) if reading_scores else None,
            "latest_pct": reading_scores[0] if reading_scores else None,
        },
        "writing": {
            "submissions": eng_essays.count(),
            "latest_score": float(latest_essay.total_score) if latest_essay and latest_essay.total_score is not None else None,
            "latest_max": latest_essay.max_score if latest_essay else None,
        },
        "speaking": {
            "submissions": eng_speaking.count(),
            "latest_band": (
                float(latest_speaking.overall_band)
                if latest_speaking and latest_speaking.overall_band is not None
                else None
            ),
        },
        "vocabulary": {
            "reviewed": word_total,
            "mastered": word_mastered,
        },
    }


def _active_english_homework(user) -> list[dict[str, Any]]:
    group_ids = list(user.student_groups.values_list("id", flat=True))
    qs = Homework.objects.filter(status=Homework.Status.ACTIVE).filter(
        Q(student=user) | Q(group_id__in=group_ids)
    )
    items: list[dict[str, Any]] = []
    subs = {
        s.homework_id: s
        for s in HomeworkSubmission.objects.filter(student=user, homework__in=qs[:20])
    }
    for hw in qs.select_related("test", "essay_topic", "group", "vocabulary_pack").order_by("due_date", "-created_at")[:20]:
        is_english = False
        if hw.test_id and hw.test and hw.test.subject == "english":
            is_english = True
        elif hw.essay_topic_id and hw.essay_topic and hw.essay_topic.subject == "english":
            is_english = True
        elif hw.group_id and hw.group and getattr(hw.group, "subject", "") == "english":
            is_english = True
        elif hw.vocabulary_pack_id and hw.vocabulary_pack and hw.vocabulary_pack.subject == "english":
            is_english = True
        elif hw.content_type == Homework.ContentType.VOCABULARY:
            is_english = True
        if not is_english:
            continue
        sub = subs.get(hw.id)
        items.append(
            {
                "id": hw.id,
                "title": hw.title,
                "content_type": hw.content_type,
                "deadline": hw.due_date.isoformat() if hw.due_date else None,
                "status": sub.status if sub else HomeworkSubmission.Status.NOT_STARTED,
                "is_completed": bool(sub and sub.is_completed),
            }
        )
        if len(items) >= 6:
            break
    return items


class EnglishCenterView(APIView):
    """GET/PATCH /api/v1/english/center/ — English Learning Center hub & track settings."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        profile, _ = Profile.objects.get_or_create(user=request.user)
        requested_track = (request.query_params.get("track") or "").strip()
        track = requested_track if requested_track in TRACK_CODES else (profile.english_track or Profile.EnglishTrack.IELTS_ACADEMIC)
        exam_types = _track_exam_types(track)
        search_q = (request.query_params.get("q") or "").strip()

        base_tests = (
            Test.objects.filter(
                subject="english",
                is_active=True,
                status=Test.Status.PUBLISHED,
            )
            .prefetch_related("sections")
            .annotate(counted_q=Count("questions", filter=Test.counted_questions_q(), distinct=True))
            .order_by("-created_at")
        )
        if search_q:
            base_tests = base_tests.filter(Q(title__icontains=search_q) | Q(description__icontains=search_q))

        track_tests = list(base_tests.filter(exam_type__in=exam_types)[:30])
        if not track_tests:
            track_tests = list(base_tests[:30])

        listening_tests: list[dict[str, Any]] = []
        reading_tests: list[dict[str, Any]] = []
        full_mocks: list[dict[str, Any]] = []
        for test in track_tests:
            sec_codes = {s.code.upper() for s in test.sections.all() if s.code}
            is_full = test.assessment_category == Test.AssessmentCategory.FULL_MOCK or len(sec_codes) >= 2
            card = _serialize_test_card(test)
            if is_full and len(full_mocks) < 8:
                full_mocks.append(card)
            if ("LISTENING" in sec_codes or test.audio_url) and len(listening_tests) < 8:
                listening_tests.append(card)
            if ("READING" in sec_codes or (not test.audio_url and "LISTENING" not in sec_codes)) and len(reading_tests) < 8:
                reading_tests.append(card)

        writing_qs = EssayTopic.objects.filter(subject="english", is_active=True).order_by("-created_at")
        if track == Profile.EnglishTrack.CEFR_MULTILEVEL:
            preferred_writing = list(writing_qs.filter(category=EssayTopic.Category.MULTILEVEL)[:8])
            writing_topics = preferred_writing or list(writing_qs[:8])
        else:
            preferred_writing = list(
                writing_qs.filter(
                    category__in=(EssayTopic.Category.IELTS_TASK1, EssayTopic.Category.IELTS_TASK2, EssayTopic.Category.UMUMIY)
                )[:8]
            )
            writing_topics = preferred_writing or list(writing_qs[:8])

        speaking_qs = SpeakingTopic.objects.filter(subject="english", is_active=True).order_by("part", "-created_at")
        if track == Profile.EnglishTrack.CEFR_MULTILEVEL:
            preferred_spk = list(speaking_qs.filter(part=SpeakingTopic.PartChoice.MULTILEVEL)[:8])
            speaking_topics = preferred_spk or list(speaking_qs[:8])
        else:
            preferred_spk = list(speaking_qs.exclude(part=SpeakingTopic.PartChoice.MULTILEVEL)[:8])
            speaking_topics = preferred_spk or list(speaking_qs[:8])

        vocab_packs = list(
            VocabularyPack.objects.filter(subject="english")
            .filter(Q(group__isnull=True) | Q(group__students=request.user) | Q(teacher=request.user))
            .distinct()
            .order_by("-created_at")[:8]
        )

        unresolved_test_mistakes = (
            StudentAnswer.objects.filter(
                attempt__student=request.user,
                attempt__test__subject="english",
                is_correct=False,
            )
            .values("question_id")
            .distinct()
            .count()
        )
        word_mistakes_count = StudentWordMistake.objects.filter(
            student=request.user,
            is_mastered=False,
        ).count()

        recent_results = [
            {
                "result_id": r.id,
                "test_id": r.test_id,
                "title": r.test.title,
                "exam_type": r.test.exam_type,
                "percentage": float(r.percentage),
                "correct": r.correct_answers,
                "total": r.total_questions,
                "finished_at": r.calculated_at.isoformat() if r.calculated_at else None,
            }
            for r in Result.objects.filter(
                student=request.user,
                test__subject="english",
                attempt__is_preview=False,
            )
            .select_related("test")
            .order_by("-calculated_at")[:6]
        ]

        homework_items = _active_english_homework(request.user)
        from apps.vocabulary.models import GrammarCategory
        from apps.vocabulary.quiz_engine import seed_grammar_curriculum

        if GrammarCategory.objects.count() < 10:
            seed_grammar_curriculum()
        grammar_list = list(GrammarCategory.objects.order_by("sort_order", "id")[:10])

        return Response(
            {
                "track": track,
                "target_band": float(profile.target_band) if profile.target_band is not None else None,
                "target_cefr_level": profile.target_cefr_level or "",
                "tracks": list(TRACK_CATALOG),
                "study_modes": list(STUDY_MODES),
                "resume": _resume_item(request.user),
                "counts": {
                    "listening_tests": len(listening_tests),
                    "reading_tests": len(reading_tests),
                    "full_mocks": len(full_mocks),
                    "writing_topics": len(writing_topics),
                    "speaking_topics": len(speaking_topics),
                    "vocabulary_packs": len(vocab_packs),
                    "grammar_topics": len(grammar_list),
                    "pending_homework": sum(1 for h in homework_items if not h["is_completed"]),
                    "unresolved_mistakes": unresolved_test_mistakes + word_mistakes_count,
                },
                "listening_tests": listening_tests,
                "reading_tests": reading_tests,
                "full_mocks": full_mocks,
                "writing_topics": [
                    {
                        "id": t.id,
                        "title": t.title,
                        "category": t.category,
                        "rubric_type": t.rubric_type,
                        "word_limit_min": t.word_limit_min,
                        "time_limit_minutes": t.time_limit_minutes,
                    }
                    for t in writing_topics
                ],
                "speaking_topics": [
                    {
                        "id": s.id,
                        "title": s.title,
                        "part": s.part,
                        "difficulty": s.difficulty,
                        "prep_time_seconds": s.prep_time_seconds,
                        "speak_time_seconds": s.speak_time_seconds,
                    }
                    for s in speaking_topics
                ],
                "vocabulary_packs": [
                    {
                        "id": p.id,
                        "title": p.title,
                        "word_count": p.word_count,
                        "created_at": p.created_at.isoformat() if p.created_at else None,
                    }
                    for p in vocab_packs
                ],
                "grammar_topics": [
                    {
                        "slug": g.slug,
                        "title": g.title,
                        "cefr_level": g.cefr_level,
                    }
                    for g in grammar_list
                ],
                "homework": homework_items,
                "mistakes": {
                    "test_mistakes_count": unresolved_test_mistakes,
                    "vocabulary_mistakes_count": word_mistakes_count,
                    "total": unresolved_test_mistakes + word_mistakes_count,
                },
                "skill_progress": _build_skill_progress(request.user),
                "recent_results": recent_results,
            },
            status=status.HTTP_200_OK,
        )

    def patch(self, request: Request) -> Response:
        profile, _ = Profile.objects.get_or_create(user=request.user)
        data = request.data if isinstance(request.data, dict) else {}

        if "english_track" in data:
            track = str(data.get("english_track") or "").strip()
            if track not in TRACK_CODES:
                return Response(
                    {"error": "Noto'g'ri ingliz tili yo'nalishi (track)."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            profile.english_track = track

        if "target_band" in data:
            raw_band = data.get("target_band")
            if raw_band in (None, ""):
                profile.target_band = None
            else:
                try:
                    band = Decimal(str(raw_band))
                except (InvalidOperation, ValueError):
                    return Response(
                        {"error": "target_band 1.0–9.0 oralig'ida son bo'lishi kerak."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if band < Decimal("1.0") or band > Decimal("9.0"):
                    return Response(
                        {"error": "target_band 1.0–9.0 oralig'ida bo'lishi kerak."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                profile.target_band = band

        if "target_cefr_level" in data:
            lvl = str(data.get("target_cefr_level") or "").strip().upper()
            if lvl and lvl not in ("A1", "A2", "B1", "B2", "C1", "C2"):
                return Response(
                    {"error": "target_cefr_level A1–C2 oralig'ida bo'lishi kerak."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            profile.target_cefr_level = lvl

        if data.get("set_active_subject") is True:
            profile.active_subject = Profile.SubjectChoice.ENGLISH

        prefs = dict(profile.subject_study_preferences or {})
        eng = dict(prefs.get("english") or {})
        eng["track"] = profile.english_track
        eng["target_band"] = str(profile.target_band) if profile.target_band is not None else None
        eng["target_cefr_level"] = profile.target_cefr_level
        prefs["english"] = eng
        profile.subject_study_preferences = prefs
        profile.save()

        return Response(
            {
                "active_subject": profile.active_subject,
                "english_track": profile.english_track,
                "target_band": float(profile.target_band) if profile.target_band is not None else None,
                "target_cefr_level": profile.target_cefr_level,
            },
            status=status.HTTP_200_OK,
        )
