"""Release-safety regression tests for NEXT 8.0 schema compatibility and invite-code concurrency."""

from __future__ import annotations

import json
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection
from django.utils import timezone

from apps.accounts.models import Profile
from apps.courses.models import Course, StudentGroup
from apps.essays.models import EssayTopic
from apps.speaking.models import SpeakingSubmission, SpeakingTopic
from apps.tests.models import (
    ExamPart,
    ExamSection,
    Question,
    QuestionGroup,
    ReadingPassage,
    StudentAnswer,
    Test,
    TestAttempt,
)

User = get_user_model()

NEXT_8_DEFAULTED_COLUMNS: dict[str, set[str]] = {
    "accounts_profile": {"english_track", "target_cefr_level"},
    "essays_essaytopic": {"task_subtype", "stimulus_data"},
    "speaking_speakingsubmission": {
        "audio_hash",
        "is_verified_audio",
        "track",
        "rubric_version",
        "task_scores",
        "teacher_review_requested",
        "teacher_comments",
    },
    "tests_test": {"content_version", "is_keyless", "spec_version"},
    "tests_examsection": {"stimulus_ref"},
    "tests_readingpassage": {"stimulus_ref"},
    "tests_exampart": {"audio_play_limit", "transcript", "stimulus_ref"},
    "tests_questiongroup": {"stimulus_ref", "content_layout"},
    "tests_question": {"evidence_text", "cefr_level", "skill_tags"},
    "tests_testattempt": {
        "study_mode",
        "session_token",
        "last_revision",
        "content_version",
        "spec_version",
        "section_deadlines",
        "media_state",
    },
    "tests_studentanswer": {"revision", "annotations"},
}


@pytest.mark.django_db(transaction=True)
class TestStudentGroupInviteCodeCollisionSafety:
    """Verify unique invite_code generation handles collisions and concurrent inserts."""

    def test_save_retries_pre_save_hex_collision(self) -> None:
        teacher = User.objects.create_user(
            email="t_invite_seq@example.com",
            password="pass",
            role="teacher",
        )
        with patch("secrets.token_hex", side_effect=["AABB", "AABB", "CCDD"]):
            g1 = StudentGroup.objects.create(teacher=teacher, name="Seq G1", subject="english")
            g2 = StudentGroup.objects.create(teacher=teacher, name="Seq G2", subject="english")

        assert g1.invite_code == "ENG-AABB"
        assert g2.invite_code == "ENG-CCDD"
        assert g1.invite_code != g2.invite_code

    def test_save_recovers_from_db_unique_race_via_savepoint_retry(self) -> None:
        teacher = User.objects.create_user(
            email="t_invite_race@example.com",
            password="pass",
            role="teacher",
        )
        existing = StudentGroup.objects.create(
            teacher=teacher,
            name="Existing",
            subject="english",
            invite_code="ENG-RACE1",
        )
        assert existing.invite_code == "ENG-RACE1"

        original_exists = StudentGroup.objects.filter
        fake_miss_done = {"missed": False}

        def tricked_filter(*args, **kwargs):
            qs = original_exists(*args, **kwargs)
            if not fake_miss_done["missed"] and kwargs.get("invite_code") == "ENG-RACE1":
                fake_miss_done["missed"] = True
                return StudentGroup.objects.none()
            return qs

        with (
            patch("secrets.token_hex", side_effect=["RACE1", "SAFE99"]),
            patch.object(StudentGroup.objects, "filter", side_effect=tricked_filter),
        ):
            raced = StudentGroup.objects.create(teacher=teacher, name="Raced Group", subject="english")

        assert raced.pk is not None
        assert raced.invite_code == "ENG-SAFE99"
        assert raced.invite_code != existing.invite_code

    def test_explicit_duplicate_invite_code_still_raises_integrity_error(self) -> None:
        teacher = User.objects.create_user(
            email="t_invite_explicit@example.com",
            password="pass",
            role="teacher",
        )
        StudentGroup.objects.create(
            teacher=teacher,
            name="Explicit 1",
            subject="english",
            invite_code="ENG-FIXED",
        )
        with pytest.raises(IntegrityError):
            StudentGroup.objects.create(
                teacher=teacher,
                name="Explicit 2",
                subject="english",
                invite_code="ENG-FIXED",
            )

    @unittest.skipUnless(
        connection.vendor == "postgresql",
        "Concurrent multi-connection unique insert stress runs against PostgreSQL.",
    )
    def test_concurrent_postgresql_group_creation_under_high_collision_pressure(self) -> None:
        teacher = User.objects.create_user(
            email="t_invite_pg_conc@example.com",
            password="pass",
            role="teacher",
        )
        workers = 6
        barrier = threading.Barrier(workers)

        def create_group(idx: int) -> str:
            from django.db import connections

            try:
                barrier.wait(timeout=10)
                grp = StudentGroup.objects.create(
                    teacher=teacher,
                    name=f"Concurrent-{idx}",
                    subject="english",
                )
                return grp.invite_code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=workers) as pool:
            codes = list(pool.map(create_group, range(workers)))

        assert len(codes) == workers
        assert len(set(codes)) == workers


@pytest.mark.django_db
class TestBackwardCompatibleDatabaseDefaults:
    """Verify NEXT 8.0 non-nullable columns carry SQL DEFAULTs for v2.12.0 INSERT compatibility."""

    def test_sql_defaults_exist_for_all_new_non_nullable_columns(self) -> None:
        with connection.cursor() as cursor:
            for table, columns in NEXT_8_DEFAULTED_COLUMNS.items():
                if connection.vendor == "postgresql":
                    cursor.execute(
                        """
                        SELECT column_name, column_default, is_nullable
                        FROM information_schema.columns
                        WHERE table_schema = 'public' AND table_name = %s
                        """,
                        [table],
                    )
                    col_meta = {
                        row[0]: {"default": row[1], "nullable": row[2]}
                        for row in cursor.fetchall()
                    }
                    for col in columns:
                        assert col in col_meta, f"Missing column {table}.{col}"
                        assert col_meta[col]["default"] is not None, (
                            f"PostgreSQL {table}.{col} lacks SQL DEFAULT after DROP DEFAULT fix check"
                        )
                else:
                    cursor.execute(f'PRAGMA table_info("{table}")')
                    col_meta = {row[1]: {"default": row[4]} for row in cursor.fetchall()}
                    for col in columns:
                        assert col in col_meta, f"Missing column {table}.{col}"
                        assert col_meta[col]["default"] is not None, (
                            f"SQLite {table}.{col} lacks SQL DEFAULT"
                        )

    def test_v2_12_raw_sql_inserts_omitting_all_next8_columns_succeed(self) -> None:
        now = timezone.now()
        empty_json = json.dumps({})
        student = User.objects.create_user(
            email="legacy_v212@example.com",
            password="pass",
            role="student",
        )
        # User create auto-created Profile via signal; remove to test raw v2.12 INSERT on accounts_profile
        Profile.objects.filter(user=student).delete()

        teacher = User.objects.create_user(
            email="legacy_v212_t@example.com",
            password="pass",
            role="teacher",
        )
        course = Course.objects.create(title="Legacy Course", slug="legacy-course", teacher=teacher)
        speaking_topic = SpeakingTopic.objects.create(
            title="Legacy Speaking Topic",
            part=SpeakingTopic.PartChoice.PART1,
            prompt="Describe your hobby.",
        )

        with connection.cursor() as cursor:
            # 1. accounts_profile (omits english_track, target_cefr_level, target_band)
            cursor.execute(
                """
                INSERT INTO accounts_profile (
                    user_id, phone, bio, plan, active_subject, subject_study_preferences,
                    exam_target, target_timeline_months, target_grade, onboarding_completed,
                    referral_source, main_goal, target_exam, sub_subject, level,
                    daily_goal_minutes, reminder_slot, daily_plan_summary,
                    current_streak, longest_streak, streak_freeze_count,
                    xp_points, weekly_xp, weekly_league, leaderboard_opt_in,
                    leaderboard_pseudonym, streak_opt_in, center_name
                ) VALUES (
                    %s, '', '', 'free', 'english', %s,
                    'ielts', 3, '', false,
                    '', '', '', '', '',
                    20, '09:00', %s,
                    0, 0, 0,
                    0, 0, 'bronze', false,
                    '', true, ''
                )
                """,
                [student.id, empty_json, empty_json],
            )

            # 2. tests_test (omits content_version, is_keyless, spec_version)
            cursor.execute(
                """
                INSERT INTO tests_test (
                    scoring_type, exam_type, assessment_category, subject, title, description,
                    course_id, time_limit_minutes, max_attempts, pass_percentage, difficulty,
                    status, is_active, show_results_immediately, shuffle_questions, shuffle_choices,
                    audio_url, is_strict_mode, strict_anti_cheat, access_type, audience_mode,
                    auto_archive_on_completion, access_pin, created_at, updated_at
                ) VALUES (
                    'band_9', 'ielts', 'mock', 'english', 'Legacy v2.12 Test', '',
                    %s, 60, 0, 60, 'medium',
                    'published', true, true, false, false,
                    '', false, false, 'free', 'both',
                    false, '', %s, %s
                )
                """,
                [course.id, now, now],
            )
            test_id = Test.objects.get(title="Legacy v2.12 Test").id

            # 3. tests_examsection (omits stimulus_ref)
            cursor.execute(
                """
                INSERT INTO tests_examsection (
                    test_id, name, code, audio_url, "order", duration_minutes, weight
                ) VALUES (%s, 'Reading', 'reading', '', 1, 60, 1.0)
                """,
                [test_id],
            )
            section_id = ExamSection.objects.get(test_id=test_id, code="reading").id

            # 4. tests_readingpassage (omits stimulus_ref)
            cursor.execute(
                """
                INSERT INTO tests_readingpassage (
                    test_id, title, content, audio_url, source, "order"
                ) VALUES (%s, 'Legacy Passage', 'Passage body', '', '', 1)
                """,
                [test_id],
            )

            # 5. tests_exampart (omits part_number, audio_play_limit, transcript, stimulus_ref)
            cursor.execute(
                """
                INSERT INTO tests_exampart (
                    section_id, number, title, instructions, audio, "order"
                ) VALUES (%s, 1, 'Part 1', '', '', 1)
                """,
                [section_id],
            )
            part_id = ExamPart.objects.get(section_id=section_id, title="Part 1").id

            # 6. tests_questiongroup (omits stimulus_ref, content_layout)
            cursor.execute(
                """
                INSERT INTO tests_questiongroup (
                    part_id, title, instructions, answer_rule, image, options_label, each_option_once, "order"
                ) VALUES (%s, 'Group 1', '', '', '', '', false, 1)
                """,
                [part_id],
            )

            # 7. tests_question (omits evidence_text, audio_start_sec, cefr_level, skill_tags)
            cursor.execute(
                """
                INSERT INTO tests_question (
                    test_id, passage, text, question_type, correct_text, points,
                    explanation, evidence, explanation_status, needs_review,
                    total_attempts, correct_attempts, current_rasch_weight, difficulty_logit,
                    position, config
                ) VALUES (
                    %s, '', 'Legacy Q1', 'mcq', 'A', 1,
                    '', '', 'verified', false,
                    0, 0, 1.0, 0.0,
                    1, %s
                )
                """,
                [test_id, empty_json],
            )
            question_id = Question.objects.get(test_id=test_id, text="Legacy Q1").id

            # 8. tests_testattempt (omits study_mode, session_token, last_revision, content_version, spec_version, section_deadlines, media_state)
            cursor.execute(
                """
                INSERT INTO tests_testattempt (
                    test_id, student_id, status, started_at, score, percentage, is_passed,
                    violation_count, cheating_detected, violation_logs, is_preview, access_source,
                    is_classroom_entitlement, mode, raw_score, cefr_level, rasch_score, rasch_grade,
                    rasch_mode, section_scores, teacher_comment, teacher_overridden
                ) VALUES (
                    %s, %s, 'in_progress', %s, 0, 0, false,
                    0, false, %s, false, 'self',
                    false, 'strict', 0, '', 0, '',
                    'legacy', %s, '', false
                )
                """,
                [test_id, student.id, now, empty_json, empty_json],
            )
            attempt_id = TestAttempt.objects.get(test_id=test_id, student=student).id

            # 9. tests_studentanswer (omits revision, annotations)
            cursor.execute(
                """
                INSERT INTO tests_studentanswer (
                    attempt_id, question_id, text_answer, written_text, written_word_count,
                    ai_feedback, answered_at
                ) VALUES (%s, %s, 'A', '', 0, %s, %s)
                """,
                [attempt_id, question_id, empty_json, now],
            )

            # 10. essays_essaytopic (omits task_subtype, stimulus_image, stimulus_data)
            cursor.execute(
                """
                INSERT INTO essays_essaytopic (
                    subject, rubric_type, title, description, category,
                    word_limit_min, word_limit_max, time_limit_minutes, sample_outline,
                    grammar_strictness, national_cert_scale, password, is_active, created_at
                ) VALUES (
                    'english', 'bmb_12', 'Legacy Essay Topic', 'Write well.', 'general',
                    200, 350, 40, '',
                    5, false, '', true, %s
                )
                """,
                [now],
            )

            # 11. speaking_speakingsubmission (omits audio_hash, is_verified_audio, track, rubric_version, task_scores, teacher_review_requested, teacher_comments, etc.)
            cursor.execute(
                """
                INSERT INTO speaking_speakingsubmission (
                    user_id, topic_id, duration_seconds, transcript, feedback, status, created_at
                ) VALUES (%s, %s, 45, 'Hello examiner', %s, 'pending', %s)
                """,
                [student.id, speaking_topic.id, empty_json, now],
            )

        # Read every inserted row back via Django ORM to verify clean default hydration
        assert Profile.objects.get(user=student).english_track == "ielts_academic"
        assert Test.objects.get(id=test_id).content_version == 1
        assert ExamSection.objects.get(id=section_id).stimulus_ref == ""
        assert ReadingPassage.objects.get(test_id=test_id).stimulus_ref == ""
        assert ExamPart.objects.get(id=part_id).audio_play_limit == 0
        assert QuestionGroup.objects.get(part_id=part_id).content_layout == ""
        assert Question.objects.get(id=question_id).skill_tags == []
        attempt = TestAttempt.objects.get(id=attempt_id)
        assert attempt.study_mode == "strict"
        assert attempt.section_deadlines == {}
        assert StudentAnswer.objects.get(attempt_id=attempt_id, question_id=question_id).annotations == {}
        assert EssayTopic.objects.get(title="Legacy Essay Topic").stimulus_data == {}
        sub = SpeakingSubmission.objects.get(user=student, topic=speaking_topic)
        assert sub.track == "ielts"
        assert sub.rubric_version == "ielts_speaking_v1"
        assert sub.task_scores == {}
