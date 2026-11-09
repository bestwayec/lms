"""
Management command: purge_all_tests

Safely purges tests, questions, choices, test attempts, student answers,
and test results atomically from the database for a clean start.

STRICT SAFETY GUARANTEES:
- PRESERVES ALL User accounts, Profiles, Passwords, and Tokens.
- PRESERVES ALL Student Groups, Group Enrollments, and Teacher-Student relationships.
- PRESERVES ALL Subscriptions, Payments, Plans, and Invoices.
- PRESERVES ALL Categories, Subjects, and Essay Submissions.
- REQUIRES --confirm flag to execute. Refuses to run without --confirm.
- Supports --dry-run to preview candidate objects safely.
- Supports --demo-only flag to selectively purge only demo/seeded mocks.
"""

from __future__ import annotations

import sys
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q

from apps.tests.models import (
    Test,
    ExamSection,
    ReadingPassage,
    Question,
    Choice,
    TestAttempt,
    StudentAnswer,
    GapBlank,
    GapResponse,
    MatchingPrompt,
    MatchingOption,
    MatchingPair,
    MatchingResponse,
    ExamWrittenBridge,
    AttemptSectionProgress,
    ExamScoringProfile,
)
from apps.results.models import Result, ResultSectionScore


DEMO_EXACT_CODES = [
    "MOCK-LAW-01",
    "MOCK-CHEM-01",
    "MOCK-BIO-01",
    "MOCK-SHUKUROV",
    "MOCK-BMB04",
    "#MOCK-LAW-01",
    "#MOCK-CHEM-01",
    "#MOCK-BIO-01",
    "#MOCK-SHUKUROV",
    "#MOCK-BMB04",
]

DEMO_CODE_PREFIXES = [
    "DEMO-",
    "SEEDED-",
    "TEST-DEMO-",
    "#DEMO-",
    "#SEEDED-",
]


class Command(BaseCommand):
    help = (
        "Safely purges tests, questions, attempts, and results atomically "
        "while strictly preserving all Users, Profiles, Groups, Subscriptions, and Payments."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirm",
            action="store_true",
            default=False,
            help="Confirmation flag. Required to perform the purge.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Preview matching tests without deleting anything.",
        )
        parser.add_argument(
            "--demo-only",
            action="store_true",
            default=False,
            help="Only purge tests matching demo mock codes or prefixes.",
        )

    def handle(self, *args, **options):
        dry_run = options.get("dry_run", False)
        confirm = options.get("confirm", False)
        demo_only = options.get("demo_only", False)

        if not confirm and not dry_run:
            self.stderr.write(
                self.style.ERROR(
                    "XATOLIK: Ushbu buyruq testlar, savollar va urinishlarni o'chiradi!\n"
                    "Bajarish uchun qat'iy ravishda '--confirm' bayrog'ini bering:\n"
                    "  python manage.py purge_all_tests --confirm\n"
                    "Ko'rish uchun '--dry-run' bayrog'idan foydalanishingiz mumkin."
                )
            )
            sys.exit(1)

        if demo_only:
            q_filter = Q(mock_code__in=DEMO_EXACT_CODES)
            for prefix in DEMO_CODE_PREFIXES:
                q_filter |= Q(mock_code__startswith=prefix)
            q_filter |= Q(title__istartswith="[DEMO]") | Q(title__istartswith="[SEEDED]")
            tests_qs = Test.objects.filter(q_filter)
        else:
            tests_qs = Test.objects.all()

        test_ids = list(tests_qs.values_list("id", flat=True))
        test_count = len(test_ids)

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"[DRY-RUN] Tozalash uchun tanlangan testlar: {test_count} ta "
                    f"({'faqat demo' if demo_only else 'barcha testlar'}).\n"
                    "Hech qanday ma'lumot o'chirilmadi."
                )
            )
            return

        self.stdout.write(self.style.WARNING(">>> Purging tests, questions, and attempts atomically..."))

        with transaction.atomic():
            if demo_only:
                # 1. Purge results and answers for demo tests
                del_result_sections, _ = ResultSectionScore.objects.filter(result__test_id__in=test_ids).delete()
                del_results, _ = Result.objects.filter(test_id__in=test_ids).delete()
                del_gap_responses, _ = GapResponse.objects.filter(attempt__test_id__in=test_ids).delete()
                del_matching_responses, _ = MatchingResponse.objects.filter(attempt__test_id__in=test_ids).delete()
                del_answers, _ = StudentAnswer.objects.filter(attempt__test_id__in=test_ids).delete()
                del_progress, _ = AttemptSectionProgress.objects.filter(attempt__test_id__in=test_ids).delete()
                del_written, _ = ExamWrittenBridge.objects.filter(attempt__test_id__in=test_ids).delete()
                del_attempts, _ = TestAttempt.objects.filter(test_id__in=test_ids).delete()
                del_matching_pairs, _ = MatchingPair.objects.filter(prompt__question__test_id__in=test_ids).delete()
                del_matching_options, _ = MatchingOption.objects.filter(question__test_id__in=test_ids).delete()
                del_matching_prompts, _ = MatchingPrompt.objects.filter(question__test_id__in=test_ids).delete()
                del_blanks, _ = GapBlank.objects.filter(question__test_id__in=test_ids).delete()
                del_choices, _ = Choice.objects.filter(question__test_id__in=test_ids).delete()
                del_questions, _ = Question.objects.filter(test_id__in=test_ids).delete()
                del_passages, _ = ReadingPassage.objects.filter(test_id__in=test_ids).delete()
                del_sections, _ = ExamSection.objects.filter(test_id__in=test_ids).delete()
                del_profiles, _ = ExamScoringProfile.objects.filter(test_id__in=test_ids).delete()
                del_tests, _ = tests_qs.delete()
            else:
                # 1. Purge results section scores and results
                del_result_sections, _ = ResultSectionScore.objects.all().delete()
                del_results, _ = Result.objects.all().delete()

                # 2. Purge student answers and detail responses
                del_gap_responses, _ = GapResponse.objects.all().delete()
                del_matching_responses, _ = MatchingResponse.objects.all().delete()
                del_answers, _ = StudentAnswer.objects.all().delete()

                # 3. Purge attempt section progresses, written bridges, and attempts
                del_progress, _ = AttemptSectionProgress.objects.all().delete()
                del_written, _ = ExamWrittenBridge.objects.all().delete()
                del_attempts, _ = TestAttempt.objects.all().delete()

                # 4. Purge choices, prompts, blanks, and questions
                del_matching_pairs, _ = MatchingPair.objects.all().delete()
                del_matching_options, _ = MatchingOption.objects.all().delete()
                del_matching_prompts, _ = MatchingPrompt.objects.all().delete()
                del_blanks, _ = GapBlank.objects.all().delete()
                del_choices, _ = Choice.objects.all().delete()
                del_questions, _ = Question.objects.all().delete()

                # 5. Purge passages, sections, scoring profiles, and tests
                del_passages, _ = ReadingPassage.objects.all().delete()
                del_sections, _ = ExamSection.objects.all().delete()
                del_profiles, _ = ExamScoringProfile.objects.all().delete()
                del_tests, _ = Test.objects.all().delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"✅ Xavfsiz tozalash muvaffaqiyatli yakunlandi:\n"
                f" - {del_tests} ta Test o'chirildi\n"
                f" - {del_questions} ta Savol o'chirildi\n"
                f" - {del_choices} ta Variant o'chirildi\n"
                f" - {del_attempts} ta Urinish o'chirildi\n"
                f" - {del_results} ta Natija o'chirildi\n"
                f"🔒 Barcha Foydalanuvchilar, Guruhlar, Obunalar va To'lovlar 100% saqlab qolindi!"
            )
        )
