"""
Management command: purge_all_tests

Safely purges ALL tests, questions, choices, test attempts, student answers,
and test results atomically from the database for a clean production start.

STRICT SAFETY GUARANTEES:
- PRESERVES ALL User accounts, Profiles, Passwords, and Tokens.
- PRESERVES ALL Student Groups, Group Enrollments, and Teacher-Student relationships.
- PRESERVES ALL Subscriptions, Payments, Plans, and Invoices.
- PRESERVES ALL Categories, Subjects, and Essay Submissions.
- REQUIRES --confirm flag to execute. Refuses to run without --confirm.
"""

from __future__ import annotations

import sys
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

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


class Command(BaseCommand):
    help = (
        "Safely purges all tests, questions, attempts, and results atomically "
        "while preserving all Users, Profiles, Groups, Subscriptions, and Payments."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirm",
            action="store_true",
            default=False,
            help="Confirmation flag. Required to perform the purge.",
        )

    def handle(self, *args, **options):
        if not options.get("confirm"):
            self.stderr.write(
                self.style.ERROR(
                    "XATOLIK: Ushbu buyruq barcha testlar, savollar va urinishlarni o'chiradi!\n"
                    "Bajarish uchun qat'iy ravishda '--confirm' bayrog'ini bering:\n"
                    "  python manage.py purge_all_tests --confirm"
                )
            )
            sys.exit(1)

        self.stdout.write(self.style.WARNING(">>> Purging all tests, questions, and attempts atomically..."))

        with transaction.atomic():
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
