from __future__ import annotations

import random
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from apps.core.ai_health import AIUnavailable, record_ai_failure, record_ai_success
from apps.courses.models import StudentGroup, Homework
from apps.payments.ai_quota import consume_feature_cap, refund_feature_cap
from .models import VocabularyPack, StudentWordMistake
from .serializers import VocabularyPackSerializer
from .services.vocab_generator import (
    clean_word_list,
    generate_exercises_with_ai,
    create_vocabulary_pack,
)


def _is_teacher_or_admin(user) -> bool:
    return bool(
        getattr(user, "is_superuser", False)
        or getattr(user, "role", "") in ("teacher", "admin", "center_admin")
    )


class _AiToolsThrottle(ScopedRateThrottle):
    scope = "ai-tools"


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([_AiToolsThrottle])
def generate_vocabulary_view(request):
    """
    Ustoz tomonidan 50-60 ta so'zdan 4 xil formatli mashq generatsiya qilish.

    Teachers and admins only (it spends a paid AI call), capped per day, and
    an AI failure returns 503 with nothing saved: no exercises are made up.
    """
    if not _is_teacher_or_admin(request.user):
        return Response({"error": "Faqat ustozlar uchun."}, status=status.HTTP_403_FORBIDDEN)
    raw_text = request.data.get("raw_text", "").strip()
    title = request.data.get("title", "Ingliz tili Lug'at Mashqi").strip()
    group_id = request.data.get("group_id")
    save_to_db = request.data.get("save", True)

    words = clean_word_list(raw_text)
    if not words:
        return Response(
            {"error": "Kamida 1 ta so'z kiritilishi shart."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    group = None
    if group_id:
        group = get_object_or_404(StudentGroup, id=group_id)
        if group.teacher_id != request.user.id and not request.user.is_superuser:
            return Response({"error": "Bu guruh sizniki emas."}, status=status.HTTP_403_FORBIDDEN)

    allowed, limit = consume_feature_cap(request.user, "vocab")
    if not allowed:
        return Response(
            {"error": "Bugungi limit tugadi.", "code": "daily_limit", "limit": limit},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    try:
        if save_to_db:
            pack = create_vocabulary_pack(
                raw_text=raw_text,
                title=title,
                teacher=request.user,
                group=group,
            )
            record_ai_success("vocab")
            return Response(
                VocabularyPackSerializer(pack).data, status=status.HTTP_201_CREATED
            )
        exercises = generate_exercises_with_ai(words)
        record_ai_success("vocab")
        return Response(
            {
                "title": title,
                "word_count": len(words),
                "exercises_data": exercises,
            }
        )
    except AIUnavailable as exc:
        refund_feature_cap(request.user, "vocab")
        record_ai_failure("vocab", exc)
        return Response(
            {"error": "Mashqlarni yaratib bo'lmadi. Birozdan so'ng qayta urinib ko'ring.", "code": "ai_unavailable"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def vocabulary_packs_list_view(request):
    """Mavjud lug'at to'plamlari ro'yxati."""
    user = request.user
    if user.is_teacher or user.is_superuser:
        qs = VocabularyPack.objects.filter(teacher=user)
    else:
        # Student: uning guruhlaridagi to'plamlar
        user_groups = user.student_groups.all()
        qs = VocabularyPack.objects.filter(group__in=user_groups)

    serializer = VocabularyPackSerializer(qs[:50], many=True)
    return Response(serializer.data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def assign_vocabulary_homework_view(request):
    """Lug'at to'plamini guruhga vazifa (Homework) qilib biriktirish."""
    pack_id = request.data.get("pack_id")
    group_id = request.data.get("group_id")
    due_days = int(request.data.get("due_days", 3))

    pack = get_object_or_404(VocabularyPack, id=pack_id)
    group = get_object_or_404(StudentGroup, id=group_id)
    if pack.teacher_id != request.user.id and not request.user.is_superuser:
        return Response({"error": "Bu to'plam sizniki emas."}, status=403)

    if group.teacher != request.user and not request.user.is_superuser:
        return Response(
            {"error": "Faqat guruh ustozi vazifa biriktira oladi."}, status=403
        )

    deadline = timezone.now() + timezone.timedelta(days=due_days)

    homework = Homework.objects.create(
        group=group,
        title=f"Lug'at: {pack.title}",
        description=f"4 ta mashq formatini to'liq bajaring ({pack.word_count} so'z).",
        due_date=deadline,
        created_by=request.user,
    )
    pack.group = group
    pack.save(update_fields=["group"])

    return Response(
        {
            "status": "success",
            "message": f"Lug'at to'plami '{group.name}' guruhiga muvaffaqiyatli biriktirildi.",
            "homework_id": homework.id,
            "due_date": deadline.strftime("%Y-%m-%d %H:%M"),
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def spaced_repetition_quiz_view(request):
    """
    O'quvchining Ebbinghaus bo'yicha adashgan 5 ta so'zidan iborat mini-viktorina.
    """
    student = request.user
    mistakes = list(
        StudentWordMistake.objects.filter(student=student, is_mastered=False).order_by(
            "-mistake_count", "next_review_at"
        )[:10]
    )

    if not mistakes:
        # Default starter words if student has no recorded mistakes
        sample_words = [
            ("resilient", "bardoshli, chidamli"),
            ("persistent", "qat'iyatli, sobitqadam"),
            ("meticulous", "o'ta ehtiyotkor, sinchkov"),
            ("lucid", "aniq, tushunarli"),
            ("empathy", "hamdardlik"),
        ]
        questions = []
        for idx, (w, m) in enumerate(sample_words):
            distractors = ["dangasa", "qo'pol", "shoshqaloq", "noto'g'ri fikr"]
            opts = [m] + random.sample(distractors, 3)
            random.shuffle(opts)
            questions.append(
                {
                    "id": idx + 1,
                    "word": w,
                    "question": f"'{w}' so'zining to'g'ri o'zbekcha tarjimasi qaysi?",
                    "options": opts,
                    "correct_answer": m,
                    "streak": 0,
                }
            )
        return Response(
            {
                "status": "sample",
                "message": "Hozircha xatolar yo'q. Mashg'ulot uchun namunaviy viktorina:",
                "questions": questions,
            }
        )

    selected = random.sample(mistakes, min(5, len(mistakes)))
    questions = []
    for item in selected:
        meaning = item.translation_uz or item.definition or "To'g'ri tarjima"
        distractors = [
            "tezkor qaror",
            "qoniqarsiz natija",
            "noma'lum xulosa",
            "qarama-qarshi holat",
        ]
        opts = [meaning] + random.sample(distractors, 3)
        random.shuffle(opts)
        questions.append(
            {
                "id": item.id,
                "word": item.word,
                "question": f"'{item.word}' so'zining ma'nosi qaysi?",
                "options": opts,
                "correct_answer": meaning,
                "streak": item.consecutive_correct_streak,
                "mistake_count": item.mistake_count,
            }
        )

    return Response(
        {
            "status": "active",
            "total_active_mistakes": len(mistakes),
            "questions": questions,
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def spaced_repetition_submit_view(request):
    """
    O'quvchining so'z viktorinasidagi javobini qayd etish.
    3 marta to'g'ri topsa 'is_mastered = True' bo'ladi.
    """
    word = request.data.get("word", "").strip()
    is_correct = bool(request.data.get("is_correct", False))
    translation_uz = request.data.get("translation_uz", "")
    definition = request.data.get("definition", "")

    if not word:
        return Response({"error": "So'z ko'rsatilishi shart."}, status=400)

    mistake, _ = StudentWordMistake.objects.get_or_create(
        student=request.user,
        word=word.lower(),
        defaults={"translation_uz": translation_uz, "definition": definition},
    )
    if translation_uz and not mistake.translation_uz:
        mistake.translation_uz = translation_uz
    if definition and not mistake.definition:
        mistake.definition = definition

    newly_mastered = mistake.record_attempt(is_correct)

    return Response(
        {
            "status": "success",
            "word": mistake.word,
            "is_correct": is_correct,
            "streak": mistake.consecutive_correct_streak,
            "is_mastered": mistake.is_mastered,
            "newly_mastered": newly_mastered,
            "message": (
                "🎉 Tabriklaymiz! Siz ushbu so'zni to'liq yod oldingiz!"
                if newly_mastered
                else f"Natija qayd etildi. Joriy to'g'ri seriya: {mistake.consecutive_correct_streak}/3"
            ),
        }
    )


def _student_vocab_entries(user) -> list[dict]:
    """Assemble groundable vocabulary items from StudentWordMistake + assigned packs."""
    from .models import VocabularyPack

    entries: list[dict] = []
    seen: set[str] = set()
    for m in StudentWordMistake.objects.filter(student=user).order_by("is_mastered", "-mistake_count")[:30]:
        key = m.word.strip().lower()
        if key and key not in seen:
            seen.add(key)
            entries.append(
                {
                    "id": m.id,
                    "word": m.word,
                    "meaning": m.translation_uz or m.definition or m.word,
                    "context_sentence": m.definition if m.word.lower() in (m.definition or "").lower() else "",
                    "synonyms": [],
                    "streak": m.consecutive_correct_streak,
                    "is_mastered": m.is_mastered,
                }
            )

    packs = VocabularyPack.objects.filter(group__students=user).order_by("-created_at")[:5]
    for p in packs:
        ex = p.exercises_data if isinstance(p.exercises_data, dict) else {}
        for item in (ex.get("format_3_eng_uzb") or []):
            w = str(item.get("word") or "").strip()
            ans = str(item.get("correct_answer") or "").strip()
            if w and ans and w.lower() not in seen:
                seen.add(w.lower())
                entries.append(
                    {
                        "id": len(entries) + 1000,
                        "word": w,
                        "meaning": ans,
                        "context_sentence": "",
                        "synonyms": [],
                        "streak": 0,
                        "is_mastered": False,
                    }
                )
    return entries


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def student_vocab_deck_view(request):
    """GET /api/v1/vocabulary/deck/ — Flashcards & Spaced Repetition queue for student."""
    mistakes = StudentWordMistake.objects.filter(student=request.user).order_by("is_mastered", "next_review_at")
    due_count = mistakes.filter(is_mastered=False).count()
    mastered_count = mistakes.filter(is_mastered=True).count()
    cards = [
        {
            "id": m.id,
            "word": m.word,
            "meaning": m.translation_uz or m.definition or "",
            "definition": m.definition,
            "streak": m.consecutive_correct_streak,
            "mistake_count": m.mistake_count,
            "is_mastered": m.is_mastered,
        }
        for m in mistakes[:50]
    ]
    return Response(
        {
            "due_count": due_count,
            "mastered_count": mastered_count,
            "cards": cards,
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def student_vocab_quiz_view(request):
    """GET /api/v1/vocabulary/student-quiz/ — Answer-safe Vocabulary Exam 3.0 quiz (never leaks key)."""
    from .quiz_engine import build_answer_safe_vocab_questions

    entries = _student_vocab_entries(request.user)
    if not entries:
        return Response({"status": "empty", "questions": []})

    questions = build_answer_safe_vocab_questions(entries, user_id=request.user.id, seed=request.user.id or 1)[:10]
    return Response({"status": "active", "questions": questions})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def student_vocab_submit_view(request):
    """POST /api/v1/vocabulary/student-quiz/submit/ — Grade typed/selected vocab answer server-side."""
    from .quiz_engine import _canon

    word = str(request.data.get("word") or request.data.get("prompt_word") or "").strip()
    given = str(request.data.get("answer") or "").strip()
    q_type = str(request.data.get("type") or "listen_choose").strip()
    mistake_id = request.data.get("id")

    mistake = None
    if mistake_id:
        mistake = StudentWordMistake.objects.filter(id=mistake_id, student=request.user).first()
    if not mistake and word:
        mistake = StudentWordMistake.objects.filter(student=request.user, word__iexact=word).first()

    entries = _student_vocab_entries(request.user)
    matched = next((e for e in entries if (mistake_id and e.get("id") == mistake_id) or (word and _canon(e["word"]) == _canon(word))), None)
    if not matched and not mistake:
        return Response({"error": "So'z topilmadi."}, status=status.HTTP_404_NOT_FOUND)

    target_word = mistake.word if mistake else matched["word"]
    target_meaning = (mistake.translation_uz or mistake.definition) if mistake else matched["meaning"]

    expected = target_word if q_type in ("listen_type", "fill_blank") else target_meaning
    is_correct = bool(given) and _canon(given) == _canon(expected)

    if mistake:
        newly_mastered = mistake.record_attempt(is_correct)
        streak = mistake.consecutive_correct_streak
        is_mastered = mistake.is_mastered
    else:
        obj, _ = StudentWordMistake.objects.get_or_create(
            student=request.user,
            word=target_word.lower(),
            defaults={"translation_uz": target_meaning},
        )
        newly_mastered = obj.record_attempt(is_correct)
        streak = obj.consecutive_correct_streak
        is_mastered = obj.is_mastered

    return Response(
        {
            "ok": True,
            "is_correct": is_correct,
            "correct_answer": expected,
            "streak": streak,
            "is_mastered": is_mastered,
            "newly_mastered": newly_mastered,
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def grammar_topics_view(request):
    """GET /api/v1/vocabulary/grammar/topics/ — 10 core English grammar topics + mistake recommendations."""
    from .models import GrammarAttempt, GrammarCategory
    from .quiz_engine import recommend_grammar_for_student, seed_grammar_curriculum

    if GrammarCategory.objects.count() < 10:
        seed_grammar_curriculum()

    categories = GrammarCategory.objects.prefetch_related("exercises").order_by("sort_order", "id")
    topics_data = []
    for cat in categories:
        attempts = GrammarAttempt.objects.filter(student=request.user, category=cat)
        total = attempts.count()
        correct = attempts.filter(is_correct=True).count()
        topics_data.append(
            {
                "slug": cat.slug,
                "title": cat.title,
                "cefr_level": cat.cefr_level,
                "description": cat.description,
                "formula": cat.formula,
                "example_correct": cat.example_correct,
                "example_incorrect": cat.example_incorrect,
                "exercise_count": cat.exercises.count(),
                "attempts": total,
                "correct": correct,
                "accuracy_pct": round((correct * 100.0) / total, 1) if total > 0 else None,
            }
        )

    recommended = recommend_grammar_for_student(request.user)
    return Response({"topics": topics_data, "recommended": recommended})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def grammar_topic_detail_view(request, slug: str):
    """GET /api/v1/vocabulary/grammar/topics/<slug>/ — Rule sheet + answer-free exercises."""
    from .models import GrammarCategory
    from .quiz_engine import seed_grammar_curriculum

    if GrammarCategory.objects.count() < 10:
        seed_grammar_curriculum()

    cat = get_object_or_404(GrammarCategory.objects.prefetch_related("exercises"), slug=slug)
    exercises = [
        {
            "id": ex.id,
            "prompt": ex.prompt,
            "options": ex.options,
            "cefr_level": ex.cefr_level,
        }
        for ex in cat.exercises.all().order_by("sort_order", "id")
    ]
    return Response(
        {
            "slug": cat.slug,
            "title": cat.title,
            "cefr_level": cat.cefr_level,
            "description": cat.description,
            "formula": cat.formula,
            "example_correct": cat.example_correct,
            "example_incorrect": cat.example_incorrect,
            "exercises": exercises,
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def grammar_attempt_submit_view(request):
    """POST /api/v1/vocabulary/grammar/submit/ — Grade a grammar exercise answer cleanly."""
    from .models import GrammarAttempt, GrammarExercise
    from .quiz_engine import _canon

    ex_id = request.data.get("exercise_id")
    answer = str(request.data.get("answer") or "").strip()
    ex = GrammarExercise.objects.select_related("category").filter(id=ex_id).first()
    if not ex:
        return Response({"error": "Mashq topilmadi."}, status=status.HTTP_404_NOT_FOUND)

    is_correct = _canon(answer) == _canon(ex.correct_answer)
    GrammarAttempt.objects.create(
        student=request.user,
        category=ex.category,
        exercise=ex,
        selected_answer=answer[:255],
        is_correct=is_correct,
        source_tag=str(request.data.get("source_tag") or "grammar_studio")[:40],
    )
    return Response(
        {
            "ok": True,
            "is_correct": is_correct,
            "correct_answer": ex.correct_answer,
            "explanation": ex.explanation,
        }
    )
