"""
Daily Blitz (60-second express quiz) API views.

Allows students to complete a 60-second 5-question blitz daily for +25 XP
and to advance or maintain their streak flame (🔥 N kun).
"""

from __future__ import annotations

import random
from typing import Any

from django.contrib.auth import get_user_model
from django.db.models import Q
from rest_framework import permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response

from apps.accounts.gamification import record_user_activity, get_user_streak_info
from apps.accounts.models import Profile
from apps.tests.models import Choice, Question, Test

User = get_user_model()

# Curated fallback questions for each subject when DB is fresh/purged
FALLBACK_BLITZ_QUESTIONS: dict[str, list[dict[str, Any]]] = {
    "uzbek": [
        {
            "id": -101,
            "text": "Qaysi qatorda tutuq belgisi (') so'z ma'nosini farqlash uchun xizmat qilgan?",
            "choices": [
                {"id": -1, "text": "a'lo — alo", "is_correct": False},
                {"id": -2, "text": "sur'at — surat", "is_correct": True},
                {"id": -3, "text": "ta'lim — talim", "is_correct": False},
                {"id": -4, "text": "ma'no — mano", "is_correct": False},
            ],
            "explanation": "Sur'at (tezlik) va surat (rasm) so'zlarida tutuq belgisi ma'no farqlaydi.",
        },
        {
            "id": -102,
            "text": "O'zbek tilida nechta unli fonema mavjud?",
            "choices": [
                {"id": -5, "text": "5 ta", "is_correct": False},
                {"id": -6, "text": "6 ta (a, o, i, u, o', e)", "is_correct": True},
                {"id": -7, "text": "8 ta", "is_correct": False},
                {"id": -8, "text": "10 ta", "is_correct": False},
            ],
            "explanation": "Hozirgi o'zbek adabiy tilida 6 ta unli fonema mavjud.",
        },
        {
            "id": -103,
            "text": "Alisher Navoiyning 'Xamsa' asariga kirmaydigan dostonni toping.",
            "choices": [
                {"id": -9, "text": "Hayrat ul-abror", "is_correct": False},
                {"id": -10, "text": "Farhod va Shirin", "is_correct": False},
                {"id": -11, "text": "Lison ut-tayr", "is_correct": True},
                {"id": -12, "text": "Sab'ai sayyor", "is_correct": False},
            ],
            "explanation": "Lison ut-tayr 'Xamsa' tarkibiga kirmaydi, alohida falsafiy doston hisoblanadi.",
        },
        {
            "id": -104,
            "text": "Qaysi so'z yasovchi qo'shimcha yangi so'z hosil qiladi?",
            "choices": [
                {"id": -13, "text": "-chi (ishchi)", "is_correct": True},
                {"id": -14, "text": "-lar (kitoblar)", "is_correct": False},
                {"id": -15, "text": "-ga (uyga)", "is_correct": False},
                {"id": -16, "text": "-roq (kattaroq)", "is_correct": False},
            ],
            "explanation": "-chi qo'shimchasi yangi mustaqil ma'noli ot yasaydi.",
        },
        {
            "id": -105,
            "text": "'Xazonrezgi' so'zining ma'nosi qaysi javobda to'g'ri izohlangan?",
            "choices": [
                {"id": -17, "text": "Bahor faslidagi lola ochilishi", "is_correct": False},
                {"id": -18, "text": "Kuzda barglarning to'kilish mavsumi", "is_correct": True},
                {"id": -19, "text": "Qishdagi qor bo'roni", "is_correct": False},
                {"id": -20, "text": "Yozdagi qurg'oqchilik", "is_correct": False},
            ],
            "explanation": "Xazonrezgi — yaproqlarning sarg'ayib to'kilish payti, xazon fasli.",
        },
    ],
    "biology": [
        {
            "id": -201,
            "text": "Hujayraning energetik stansiyasi qaysi organoid hisoblanadi?",
            "choices": [
                {"id": -21, "text": "Ribosoma", "is_correct": False},
                {"id": -22, "text": "Mitoxondriya", "is_correct": True},
                {"id": -23, "text": "Goldji majmuasi", "is_correct": False},
                {"id": -24, "text": "Lizosoma", "is_correct": False},
            ],
            "explanation": "Mitoxondriya ATF sintez qilib, hujayrani energiya bilan ta'minlaydi.",
        },
        {
            "id": -202,
            "text": "Odam organizmida qon hosil bo'lish jarayoni qayerda kechadi?",
            "choices": [
                {"id": -25, "text": "Qizil ilikda", "is_correct": True},
                {"id": -26, "text": "Jigarda", "is_correct": False},
                {"id": -27, "text": "Taloshda", "is_correct": False},
                {"id": -28, "text": "Buyrakda", "is_correct": False},
            ],
            "explanation": "Qizil suyak iligi barcha shaklli elementlarni sintezlaydi.",
        },
        {
            "id": -203,
            "text": "Fotosintez jarayonida ajralib chiqadigan kislorod manbasi nima?",
            "choices": [
                {"id": -29, "text": "Karbonat angidrid (CO2)", "is_correct": False},
                {"id": -30, "text": "Suv (H2O fotolizi)", "is_correct": True},
                {"id": -31, "text": "Glyukoza", "is_correct": False},
                {"id": -32, "text": "Xlorofill", "is_correct": False},
            ],
            "explanation": "Kislorod yorug'lik bosqichida suv fotolizidan hosil bo'ladi.",
        },
        {
            "id": -204,
            "text": "DNK molekulasida adenin (A) ga komplementar nukleotid qaysi?",
            "choices": [
                {"id": -33, "text": "Timin (T)", "is_correct": True},
                {"id": -34, "text": "Urasil (U)", "is_correct": False},
                {"id": -35, "text": "Guanin (G)", "is_correct": False},
                {"id": -36, "text": "Sitozin (S)", "is_correct": False},
            ],
            "explanation": "DNKda A=T ikki vodorod bog'i orqali bog'lanadi.",
        },
        {
            "id": -205,
            "text": "Gidra qaysi tip vakili hisoblanadi?",
            "choices": [
                {"id": -37, "text": "Bir hujayralilar", "is_correct": False},
                {"id": -38, "text": "Bo'shliqichlilar (Ichakbo'shliqlilar)", "is_correct": True},
                {"id": -39, "text": "Yassi chuvalchanglar", "is_correct": False},
                {"id": -40, "text": "Bo'g'imoyoqlilar", "is_correct": False},
            ],
            "explanation": "Chuchuk suv gidrasi ichakbo'shliqlilar tipiga mansub.",
        },
    ],
    "chemistry": [
        {
            "id": -301,
            "text": "Davriy sistemada eng kuchli elektromanfiylikka ega element qaysi?",
            "choices": [
                {"id": -41, "text": "Kislorod (O)", "is_correct": False},
                {"id": -42, "text": "Ftor (F)", "is_correct": True},
                {"id": -43, "text": "Xlor (Cl)", "is_correct": False},
                {"id": -44, "text": "Azot (N)", "is_correct": False},
            ],
            "explanation": "Ftor eng yuqori nisbiy elektromanfiylikka (4.0) ega.",
        },
        {
            "id": -302,
            "text": "Suv molekulasidagi (H2O) kimyoviy bog'lanish turi qanday?",
            "choices": [
                {"id": -45, "text": "Qutbli kovalent", "is_correct": True},
                {"id": -46, "text": "Qutbsiz kovalent", "is_correct": False},
                {"id": -47, "text": "Ionli bog'", "is_correct": False},
                {"id": -48, "text": "Metall bog'", "is_correct": False},
            ],
            "explanation": "H va O orasidagi bog' turli elektromanfiylikli metallmaslar o'rtasida bo'lgani uchun qutbli kovalentdir.",
        },
        {
            "id": -303,
            "text": "Normal sharoitda 1 mol har qanday gaz qancha hajm egallaydi?",
            "choices": [
                {"id": -49, "text": "11.2 litr", "is_correct": False},
                {"id": -50, "text": "22.4 litr", "is_correct": True},
                {"id": -51, "text": "44.8 litr", "is_correct": False},
                {"id": -52, "text": "1.0 litr", "is_correct": False},
            ],
            "explanation": "Avogadro qonuniga ko'ra n.sh.da 1 mol gaz 22.4 l hajmni egallaydi.",
        },
        {
            "id": -304,
            "text": "Marmarning asosiy kimyoviy tarkibi nima?",
            "choices": [
                {"id": -53, "text": "Kalsiy karbonat (CaCO3)", "is_correct": True},
                {"id": -54, "text": "Kalsiy sulfat (CaSO4)", "is_correct": False},
                {"id": -55, "text": "Kaliy gidroksid (KOH)", "is_correct": False},
                {"id": -56, "text": "Kremniy oksidi (SiO2)", "is_correct": False},
            ],
            "explanation": "Ohaktosh, bo'r va marmar CaCO3 dan iborat.",
        },
        {
            "id": -305,
            "text": "Lakmus qog'ozi kislotali muhitda qanday rangga kiradi?",
            "choices": [
                {"id": -57, "text": "Ko'k", "is_correct": False},
                {"id": -58, "text": "Qizil", "is_correct": True},
                {"id": -59, "text": "Sariq", "is_correct": False},
                {"id": -60, "text": "Binafsha", "is_correct": False},
            ],
            "explanation": "Lakmus kislotada qizil, ishqorda ko'k bo'ladi.",
        },
    ],
    "law": [
        {
            "id": -401,
            "text": "O'zbekiston Respublikasi Konstitutsiyasiga ko'ra, davlat hokimiyatining yagona manbai kim?",
            "choices": [
                {"id": -61, "text": "Xalq", "is_correct": True},
                {"id": -62, "text": "Prezident", "is_correct": False},
                {"id": -63, "text": "Oliy Majlis", "is_correct": False},
                {"id": -64, "text": "Sudlar", "is_correct": False},
            ],
            "explanation": "Konstitutsiyaning 7-moddasiga binoan, xalq davlat hokimiyatining birdan-bir manbaidir.",
        },
        {
            "id": -402,
            "text": "O'zbekiston Respublikasi qonun chiqaruvchi oliy organi qaysi?",
            "choices": [
                {"id": -65, "text": "Oliy Majlis", "is_correct": True},
                {"id": -66, "text": "Vazirlar Mahkamasi", "is_correct": False},
                {"id": -67, "text": "Bosh Prokuratura", "is_correct": False},
                {"id": -68, "text": "Konstitutsiyaviy Sud", "is_correct": False},
            ],
            "explanation": "O'zbekiston Respublikasining Oliy Majlisi oliy davlat vakillik organi bo'lib, qonun chiqaruvchi hokimiyatni amalga oshiradi.",
        },
        {
            "id": -403,
            "text": "Fuqarolik huquqiy layoqat qachon vujudga keladi?",
            "choices": [
                {"id": -69, "text": "Inson tug'ilgan paytdan boshlab", "is_correct": True},
                {"id": -70, "text": "14 yoshga to'lganda", "is_correct": False},
                {"id": -71, "text": "16 yoshga to'lganda", "is_correct": False},
                {"id": -72, "text": "18 yoshga to'lganda", "is_correct": False},
            ],
            "explanation": "Fuqarolik huquq layoqati inson tug'ilgan paytda vujudga keladi va uning vafoti bilan tugaydi.",
        },
        {
            "id": -404,
            "text": "Mehnat shartnomasi tuzishga umumiy qoidaga ko'ra necha yoshdan yo'l qo'yiladi?",
            "choices": [
                {"id": -73, "text": "16 yoshdan", "is_correct": True},
                {"id": -74, "text": "18 yoshdan", "is_correct": False},
                {"id": -75, "text": "15 yoshdan", "is_correct": False},
                {"id": -76, "text": "21 yoshdan", "is_correct": False},
            ],
            "explanation": "Yangi Mehnat kodeksiga binoan ishga qabul qilishga 16 yoshdan yo'l qo'yiladi.",
        },
        {
            "id": -405,
            "text": "Aybsizlik prezumpsiyasi qaysi huquq sohasining fundamental prinsipi hisoblanadi?",
            "choices": [
                {"id": -77, "text": "Jinoyat-protsessual huquqi", "is_correct": True},
                {"id": -78, "text": "Mulk huquqi", "is_correct": False},
                {"id": -79, "text": "Meros huquqi", "is_correct": False},
                {"id": -80, "text": "Mehnat huquqi", "is_correct": False},
            ],
            "explanation": "Shaxsning aybi qonunda belgilangan tartibda isbotlanmaguncha u aybsiz hisoblanadi.",
        },
    ],
    "english": [
        {
            "id": -501,
            "text": "Choose the correct sentence in the Present Perfect Continuous tense:",
            "choices": [
                {"id": -81, "text": "She has been working here for three years.", "is_correct": True},
                {"id": -82, "text": "She has worked here yesterday.", "is_correct": False},
                {"id": -83, "text": "She is working here since morning.", "is_correct": False},
                {"id": -84, "text": "She was been working here.", "is_correct": False},
            ],
            "explanation": "'Has been + V-ing' expresses an action that started in the past and continues into the present.",
        },
        {
            "id": -502,
            "text": "Which word is an antonym for 'METICULOUS'?",
            "choices": [
                {"id": -85, "text": "Careless", "is_correct": True},
                {"id": -86, "text": "Accurate", "is_correct": False},
                {"id": -87, "text": "Thorough", "is_correct": False},
                {"id": -88, "text": "Precise", "is_correct": False},
            ],
            "explanation": "'Meticulous' means very careful and precise; its antonym is 'careless'.",
        },
        {
            "id": -503,
            "text": "If I _____ his phone number, I would have called him yesterday.",
            "choices": [
                {"id": -89, "text": "had known", "is_correct": True},
                {"id": -90, "text": "knew", "is_correct": False},
                {"id": -91, "text": "have known", "is_correct": False},
                {"id": -92, "text": "know", "is_correct": False},
            ],
            "explanation": "Third conditional structure: If + past perfect, would have + past participle.",
        },
        {
            "id": -504,
            "text": "What does the idiom 'once in a blue moon' mean?",
            "choices": [
                {"id": -93, "text": "Very rarely", "is_correct": True},
                {"id": -94, "text": "Every night", "is_correct": False},
                {"id": -95, "text": "During the winter", "is_correct": False},
                {"id": -96, "text": "Very frequently", "is_correct": False},
            ],
            "explanation": "'Once in a blue moon' describes an event that happens extremely infrequently.",
        },
        {
            "id": -505,
            "text": "Neither the teacher nor the students _____ in the room.",
            "choices": [
                {"id": -97, "text": "were", "is_correct": True},
                {"id": -98, "text": "was", "is_correct": False},
                {"id": -99, "text": "is", "is_correct": False},
                {"id": -100, "text": "are being", "is_correct": False},
            ],
            "explanation": "With 'neither... nor', the verb agrees with the closer subject ('the students' -> plural 'were').",
        },
    ],
}


class DailyBlitzView(APIView):
    """
    GET: Retrieve 5 fast blitz questions (60s timer).
    POST: Submit answers, compute score, and increment daily streak flame (+25 XP).
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        subject = (request.query_params.get("subject") or "uzbek").strip().lower()
        if subject not in FALLBACK_BLITZ_QUESTIONS:
            subject = "uzbek"

        # Attempt to sample 5 random single choice questions from DB
        db_questions = list(
            Question.objects.filter(
                test__subject=subject,
                question_type=Question.QuestionType.SINGLE_CHOICE,
            )
            .prefetch_related("choices")
            .filter(choices__isnull=False)
            .distinct()[:25]
        )

        formatted_questions = []
        if len(db_questions) >= 5:
            sampled = random.sample(db_questions, 5)
            for q in sampled:
                choices = [
                    {"id": c.id, "text": c.text}
                    for c in q.choices.all()
                ]
                formatted_questions.append(
                    {
                        "id": q.id,
                        "text": q.text,
                        "choices": choices,
                        "subject": subject,
                    }
                )
        else:
            # Use curated fallback express questions
            pool = FALLBACK_BLITZ_QUESTIONS.get(subject, FALLBACK_BLITZ_QUESTIONS["uzbek"])
            for q in pool:
                formatted_questions.append(
                    {
                        "id": q["id"],
                        "text": q["text"],
                        "choices": [
                            {"id": c["id"], "text": c["text"]}
                            for c in q["choices"]
                        ],
                        "subject": subject,
                    }
                )

        profile, _ = Profile.objects.get_or_create(user=request.user)
        streak_info = get_user_streak_info(request.user)

        return Response(
            {
                "subject": subject,
                "duration_seconds": 60,
                "total_questions": len(formatted_questions),
                "xp_reward": 25,
                "current_streak": streak_info.get("current_streak", profile.current_streak),
                "questions": formatted_questions,
            }
        )

    def post(self, request, *args, **kwargs):
        data = request.data or {}
        subject = (data.get("subject") or "uzbek").strip().lower()
        answers = data.get("answers") or {}  # { "<question_id>": <choice_id> }

        correct_count = 0
        total_count = 5
        details = []

        fallback_pool = FALLBACK_BLITZ_QUESTIONS.get(subject, FALLBACK_BLITZ_QUESTIONS["uzbek"])
        fallback_map = {str(q["id"]): q for q in fallback_pool}

        for q_id_str, choice_id in answers.items():
            try:
                q_id = int(q_id_str)
            except (ValueError, TypeError):
                continue

            if q_id < 0:
                # Curated fallback question
                fq = fallback_map.get(str(q_id))
                if not fq:
                    continue
                correct_c = next((c for c in fq["choices"] if c.get("is_correct")), None)
                is_correct = bool(correct_c and str(correct_c["id"]) == str(choice_id))
                if is_correct:
                    correct_count += 1
                details.append(
                    {
                        "question_id": q_id,
                        "question_text": fq["text"],
                        "is_correct": is_correct,
                        "user_choice_id": choice_id,
                        "correct_choice_id": correct_c["id"] if correct_c else None,
                        "explanation": fq.get("explanation", ""),
                    }
                )
            else:
                # Database question
                question = Question.objects.filter(id=q_id).first()
                if not question:
                    continue
                correct_choice = question.choices.filter(is_correct=True).first()
                is_correct = bool(correct_choice and str(correct_choice.id) == str(choice_id))
                if is_correct:
                    correct_count += 1
                details.append(
                    {
                        "question_id": q_id,
                        "question_text": question.text,
                        "is_correct": is_correct,
                        "user_choice_id": choice_id,
                        "correct_choice_id": correct_choice.id if correct_choice else None,
                        "explanation": question.explanation or "",
                    }
                )

        # Record activity and award +25 XP & increment/maintain daily streak flame
        streak_res = record_user_activity(request.user, xp_amount=25, activity_type="blitz")
        profile, _ = Profile.objects.get_or_create(user=request.user)

        return Response(
            {
                "ok": True,
                "score": correct_count,
                "total": total_count,
                "percentage": round((correct_count / max(1, total_count)) * 100, 1),
                "xp_earned": 25,
                "current_streak": profile.current_streak,
                "streak_days": profile.current_streak,
                "streak_incremented": streak_res.get("streak_incremented", False),
                "details": details,
            },
            status=status.HTTP_200_OK,
        )
