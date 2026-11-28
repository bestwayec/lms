"""Phase 01 tests — English Learning Center, track persistence & score targets."""

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.accounts.models import Profile
from apps.courses.models import Course, StudentGroup
from apps.essays.models import EssayTopic
from apps.speaking.models import SpeakingTopic
from apps.tests.models import ExamSection, Question, StudentAnswer, Test, TestAttempt
from apps.vocabulary.models import VocabularyPack

User = get_user_model()


@pytest.mark.django_db
def test_profile_english_track_and_targets_via_auth_me():
    user = User.objects.create_user(
        email="eng_student@example.com",
        password="StrongPassword123!",
        first_name="Ali",
        last_name="Valiyev",
        role="student",
    )
    client = APIClient()
    client.force_authenticate(user=user)

    res = client.get("/api/auth/me/")
    assert res.status_code == 200
    assert res.data["english_track"] == "ielts_academic"
    assert res.data["target_band"] is None
    assert res.data["target_cefr_level"] == ""

    patch_res = client.patch(
        "/api/auth/me/",
        {
            "active_subject": "english",
            "english_track": "cefr_multilevel",
            "target_band": "7.5",
            "target_cefr_level": "c1",
        },
        format="json",
    )
    assert patch_res.status_code == 200
    assert patch_res.data["english_track"] == "cefr_multilevel"
    assert str(patch_res.data["target_band"]) == "7.5"
    assert patch_res.data["target_cefr_level"] == "C1"

    profile = Profile.objects.get(user=user)
    assert profile.active_subject == "english"
    assert profile.english_track == "cefr_multilevel"
    assert float(profile.target_band) == 7.5
    assert profile.target_cefr_level == "C1"
    assert profile.subject_study_preferences["english"]["track"] == "cefr_multilevel"


@pytest.mark.django_db
def test_profile_english_track_validation_rejects_invalid_values():
    user = User.objects.create_user(
        email="eng_val@example.com",
        password="StrongPassword123!",
        role="student",
    )
    client = APIClient()
    client.force_authenticate(user=user)

    assert client.patch("/api/auth/me/", {"english_track": "invalid_track"}, format="json").status_code == 400
    assert client.patch("/api/auth/me/", {"target_band": "9.5"}, format="json").status_code == 400
    assert client.patch("/api/auth/me/", {"target_cefr_level": "Z9"}, format="json").status_code == 400


@pytest.mark.django_db
def test_english_center_requires_auth_and_separates_subjects_and_tracks():
    anon = APIClient()
    assert anon.get("/api/v1/english/center/").status_code == 401

    teacher = User.objects.create_user(
        email="eng_teacher@example.com",
        password="StrongPassword123!",
        role="teacher",
    )
    student = User.objects.create_user(
        email="eng_learner@example.com",
        password="StrongPassword123!",
        role="student",
    )
    course = Course.objects.create(title="English Mastery", teacher=teacher)
    group = StudentGroup.objects.create(name="IELTS Group A", teacher=teacher, subject="english")
    group.students.add(student)

    # Uzbek test that MUST NOT leak into English Center
    uzbek_test = Test.objects.create(
        title="Ona tili Milliy Sertifikat",
        subject="uzbek",
        exam_type=Test.ExamType.NATIONAL_CERT,
        course=course,
        status=Test.Status.PUBLISHED,
    )
    # IELTS Listening & Reading test
    ielts_test = Test.objects.create(
        title="IELTS Academic Practice 1",
        subject="english",
        exam_type=Test.ExamType.IELTS_ACADEMIC,
        assessment_category=Test.AssessmentCategory.FULL_MOCK,
        course=course,
        status=Test.Status.PUBLISHED,
        time_limit_minutes=60,
    )
    sec_l = ExamSection.objects.create(test=ielts_test, name="Listening", code="LISTENING", order=1)
    sec_r = ExamSection.objects.create(test=ielts_test, name="Reading", code="READING", order=2)
    q1 = Question.objects.create(test=ielts_test, section=sec_l, text="L Q1", question_type=Question.QuestionType.GAP_FILL, position=1)
    Question.objects.create(test=ielts_test, section=sec_r, text="R Q1", question_type=Question.QuestionType.SINGLE_CHOICE, position=2)

    # CEFR Multilevel test
    cefr_test = Test.objects.create(
        title="BMB Multilevel Reading Mock",
        subject="english",
        exam_type=Test.ExamType.CEFR_MULTILEVEL,
        course=course,
        status=Test.Status.PUBLISHED,
    )
    sec_cefr_r = ExamSection.objects.create(test=cefr_test, name="Reading", code="READING", order=1)
    Question.objects.create(test=cefr_test, section=sec_cefr_r, text="CEFR Q1", question_type=Question.QuestionType.SINGLE_CHOICE, position=1)

    EssayTopic.objects.create(
        title="Global Warming Solutions",
        description="Write 250+ words",
        subject="english",
        category=EssayTopic.Category.IELTS_TASK2,
        rubric_type=EssayTopic.RubricType.IELTS_TASK2,
        word_limit_min=250,
    )
    EssayTopic.objects.create(
        title="Ona tili insho",
        description="Uzbek essay",
        subject="uzbek",
        category=EssayTopic.Category.ONA_TILI,
    )
    SpeakingTopic.objects.create(
        title="Describe a memorable trip",
        subject="english",
        part=SpeakingTopic.PartChoice.PART2,
        prompt="Talk about a trip",
    )
    VocabularyPack.objects.create(
        teacher=teacher,
        group=group,
        title="Academic Verbs",
        subject="english",
        raw_words_text="analyze - tahlil qilmoq",
        word_count=1,
    )

    # Active in-progress attempt + one wrong answer for mistakes count
    att = TestAttempt.objects.create(student=student, test=ielts_test, status=TestAttempt.Status.IN_PROGRESS)
    StudentAnswer.objects.create(attempt=att, question=q1, is_correct=False, text_answer="wrong")

    client = APIClient()
    client.force_authenticate(user=student)

    res = client.get("/api/v1/english/center/")
    assert res.status_code == 200
    payload = res.data
    assert payload["track"] == "ielts_academic"
    assert len(payload["tracks"]) == 4
    assert len(payload["study_modes"]) == 5
    assert payload["resume"]["route"] == f"/take/{att.id}"
    all_returned_ids = {
        t["id"]
        for t in (payload["listening_tests"] + payload["reading_tests"] + payload["full_mocks"])
    }
    assert uzbek_test.id not in all_returned_ids
    assert ielts_test.id in all_returned_ids
    assert len(payload["writing_topics"]) == 1
    assert payload["writing_topics"][0]["title"] == "Global Warming Solutions"
    assert len(payload["speaking_topics"]) == 1
    assert len(payload["vocabulary_packs"]) == 1
    assert payload["mistakes"]["test_mistakes_count"] == 1
    # Zero fabricated stats
    assert payload["skill_progress"]["listening"]["best_pct"] is None
    assert payload["skill_progress"]["speaking"]["latest_band"] is None

    # Switch track via PATCH
    patch = client.patch(
        "/api/v1/english/center/",
        {"english_track": "cefr_multilevel", "target_cefr_level": "B2", "set_active_subject": True},
        format="json",
    )
    assert patch.status_code == 200
    assert patch.data["english_track"] == "cefr_multilevel"
    assert patch.data["target_cefr_level"] == "B2"
    assert patch.data["active_subject"] == "english"

    res_cefr = client.get("/api/v1/english/center/")
    assert res_cefr.status_code == 200
    assert res_cefr.data["track"] == "cefr_multilevel"
    assert any(t["id"] == cefr_test.id for t in res_cefr.data["reading_tests"])
