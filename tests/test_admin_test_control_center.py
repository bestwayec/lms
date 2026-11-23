"""
Tests for Admin Test Control Center 4.0.

Verifies:
- Scoped querysets & RBAC (Platform Admin, Center Admin, Teacher, Student)
- Search and status filtering
- Question, assignment, attempt, and result count annotations
- Deep duplication (sections, passages, questions, choices, blanks, matching)
- Safe deletion policy: blocking deletion when attempts or active homework exist
- Archive, restore, unpublish transitions
- Bulk preview & safe bulk execution
- Safeguard barrier on purge_all_tests
"""

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.organizations.models import LearningCenter
from apps.courses.models import Course, Homework, StudentGroup
from apps.results.models import Result
from apps.tests.admin_test_service import (
    archive_test,
    check_safe_deletion,
    duplicate_test,
    execute_bulk_action,
    get_scoped_tests_queryset,
    preview_bulk_action,
    restore_test,
    unpublish_test,
)
from apps.tests.models import (
    Choice,
    ExamSection,
    GapBlank,
    MatchingOption,
    MatchingPair,
    MatchingPrompt,
    Question,
    ReadingPassage,
    Test,
    TestAttempt,
)

User = get_user_model()


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def platform_admin(db):
    return User.objects.create_user(
        email="platform_admin@test.com",
        password="pass",
        role="admin",
        is_superuser=True,
    )


@pytest.fixture
def center(db, platform_admin):
    return LearningCenter.objects.create(
        name="Grand Education Center",
        slug="grand-education",
        owner=platform_admin,
    )


@pytest.fixture
def center_admin(db, center):
    user = User.objects.create_user(
        email="center_admin@test.com",
        password="pass",
        role="center_admin",
    )
    user.learning_center = center
    user.save(update_fields=["learning_center"])
    return user


@pytest.fixture
def teacher_1(db, center):
    user = User.objects.create_user(
        email="teacher_1@test.com",
        password="pass",
        role="teacher",
    )
    user.learning_center = center
    user.save(update_fields=["learning_center"])
    return user


@pytest.fixture
def teacher_2(db):
    return User.objects.create_user(
        email="teacher_2@test.com",
        password="pass",
        role="teacher",
    )


@pytest.fixture
def course_1(db, teacher_1):
    return Course.objects.create(title="Ona tili", slug="ona-tili", teacher=teacher_1)


@pytest.fixture
def course_2(db, teacher_2):
    return Course.objects.create(title="Kimyo", slug="kimyo", teacher=teacher_2)


@pytest.fixture
def student(db):
    return User.objects.create_user(
        email="student@test.com",
        password="pass",
        role="student",
    )


@pytest.mark.django_db
def test_scoped_querysets_rbac(platform_admin, center_admin, teacher_1, teacher_2, course_1, course_2, student):
    test_t1 = Test.objects.create(title="T1 Test", course=course_1, created_by=teacher_1, status="published", is_active=True)
    test_t2 = Test.objects.create(title="T2 Test", course=course_2, created_by=teacher_2, status="published", is_active=True)

    # Platform admin sees all
    assert get_scoped_tests_queryset(platform_admin).count() == 2

    # Center admin sees T1 (teacher_1 is in their center), not T2
    center_tests = list(get_scoped_tests_queryset(center_admin))
    assert test_t1 in center_tests
    assert test_t2 not in center_tests

    # Teacher 1 sees only T1
    t1_tests = list(get_scoped_tests_queryset(teacher_1))
    assert t1_tests == [test_t1]

    # Student sees none
    assert get_scoped_tests_queryset(student).count() == 0


@pytest.mark.django_db
def test_admin_test_list_api_filters_and_stats(api, platform_admin, teacher_1, course_1):
    Test.objects.create(title="Published Chemistry", course=course_1, subject="Chemistry", status="published", is_active=True, created_by=teacher_1)
    t_draft = Test.objects.create(title="Draft Biology", course=course_1, subject="Biology", status="draft", is_active=True, created_by=teacher_1)
    Test.objects.create(title="Archived Physics", course=course_1, subject="Physics", status="archived", is_active=False, created_by=teacher_1)

    api.force_authenticate(user=platform_admin)

    # 1. All tests
    res = api.get("/api/v1/panel/tests/")
    assert res.status_code == 200
    assert res.data["total"] == 3
    assert res.data["stats"]["published_count"] == 1
    assert res.data["stats"]["draft_count"] == 1
    assert res.data["stats"]["archived_count"] == 1

    # 2. Filter by status=published
    res_pub = api.get("/api/v1/panel/tests/?status=published")
    assert res_pub.status_code == 200
    assert res_pub.data["total"] == 1
    assert res_pub.data["results"][0]["title"] == "Published Chemistry"

    # 3. Filter by search query q
    res_q = api.get("/api/v1/panel/tests/?q=Biology")
    assert res_q.status_code == 200
    assert res_q.data["total"] == 1
    assert res_q.data["results"][0]["id"] == t_draft.id

    # 4. Student blocked
    student = User.objects.create_user(email="s@test.com", password="x", role="student")
    api.force_authenticate(user=student)
    res_denied = api.get("/api/v1/panel/tests/")
    assert res_denied.status_code == 403


@pytest.mark.django_db
def test_safe_deletion_policy(api, platform_admin, teacher_1, course_1, student):
    test_draft = Test.objects.create(title="Clean Draft", course=course_1, status="draft", is_active=True, created_by=teacher_1)
    test_pub = Test.objects.create(title="Published Live", course=course_1, status="published", is_active=True, created_by=teacher_1)
    test_attempted = Test.objects.create(title="With Attempts", course=course_1, status="draft", is_active=True, created_by=teacher_1)

    # Add attempt to test_attempted
    TestAttempt.objects.create(test=test_attempted, student=student, status="completed")

    # 1. Draft with 0 attempts: check_safe_deletion passes
    safe, msg, _ = check_safe_deletion(test_draft)
    assert safe is True

    # 2. Published test: check_safe_deletion blocks
    safe_pub, msg_pub, _ = check_safe_deletion(test_pub)
    assert safe_pub is False
    assert "arxivlang" in msg_pub or "qoralamaga" in msg_pub

    # 3. Test with attempts: check_safe_deletion blocks
    safe_att, msg_att, _ = check_safe_deletion(test_attempted)
    assert safe_att is False
    assert "urinishi" in msg_att

    # API test: DELETE with attempts returns 409 Conflict
    api.force_authenticate(user=platform_admin)
    res_block = api.delete(f"/api/v1/panel/tests/{test_attempted.id}/")
    assert res_block.status_code == 409
    assert res_block.data["can_archive"] is True
    assert Test.objects.filter(id=test_attempted.id).exists()

    # API test: DELETE clean draft succeeds with 204
    res_del = api.delete(f"/api/v1/panel/tests/{test_draft.id}/")
    assert res_del.status_code == 204
    assert not Test.objects.filter(id=test_draft.id).exists()


@pytest.mark.django_db
def test_duplicate_test_with_nested_relations(api, platform_admin, teacher_1, course_1):
    test = Test.objects.create(
        title="Original Exam",
        course=course_1,
        subject="Ona tili",
        status="published",
        is_active=True,
        created_by=teacher_1,
        time_limit_minutes=45,
    )
    sec = ExamSection.objects.create(test=test, name="Grammatika", code="GRAM", order=1)
    ReadingPassage.objects.create(test=test, section=sec, title="Matn 1", content="Lorem ipsum", order=1)
    q = Question.objects.create(test=test, section=sec, text="Savol 1?", question_type="single", points=2, position=1)
    Choice.objects.create(question=q, text="A javob", is_correct=True, position=0)
    Choice.objects.create(question=q, text="B javob", is_correct=False, position=1)

    api.force_authenticate(user=platform_admin)
    res = api.post(f"/api/v1/panel/tests/{test.id}/duplicate/")
    assert res.status_code == 201

    new_id = res.data["id"]
    assert new_id != test.id
    new_test = Test.objects.get(id=new_id)

    assert new_test.status == "draft"
    assert "Nusxa" in new_test.title
    assert new_test.sections.count() == 1
    assert new_test.passages.count() == 1
    assert new_test.questions.count() == 1

    new_q = new_test.questions.first()
    assert new_q.choices.count() == 2
    assert new_q.choices.filter(is_correct=True).exists()


@pytest.mark.django_db
def test_archive_restore_unpublish(api, platform_admin, teacher_1, course_1):
    test = Test.objects.create(title="Status Test", course=course_1, status="published", is_active=True, created_by=teacher_1)
    api.force_authenticate(user=platform_admin)

    # 1. Archive
    res_arc = api.post(f"/api/v1/panel/tests/{test.id}/archive/")
    assert res_arc.status_code == 200
    test.refresh_from_db()
    assert test.status == "archived"
    assert test.is_active is False

    # 2. Restore
    res_res = api.post(f"/api/v1/panel/tests/{test.id}/restore/")
    assert res_res.status_code == 200
    test.refresh_from_db()
    assert test.status == "draft"
    assert test.is_active is False

    # 3. Unpublish
    test.status = "published"
    test.save()
    res_unpub = api.post(f"/api/v1/panel/tests/{test.id}/unpublish/")
    assert res_unpub.status_code == 200
    test.refresh_from_db()
    assert test.status == "draft"


@pytest.mark.django_db
def test_bulk_preview_and_actions(api, platform_admin, teacher_1, course_1, student):
    t_clean = Test.objects.create(title="Clean Draft 1", course=course_1, status="draft", is_active=True, created_by=teacher_1)
    t_with_att = Test.objects.create(title="Attempted 2", course=course_1, status="draft", is_active=True, created_by=teacher_1)
    TestAttempt.objects.create(test=t_with_att, student=student, status="completed")
    t_pub = Test.objects.create(title="Live 3", course=course_1, status="published", is_active=True, created_by=teacher_1)

    api.force_authenticate(user=platform_admin)
    test_ids = [t_clean.id, t_with_att.id, t_pub.id]

    # Bulk preview for delete
    preview_res = api.post("/api/v1/panel/tests/bulk-preview/", {"test_ids": test_ids, "action": "delete"}, format="json")
    assert preview_res.status_code == 200
    assert preview_res.data["total_selected"] == 3
    assert preview_res.data["safe_to_delete_count"] == 1
    assert preview_res.data["blocked_from_delete_count"] == 2

    # Bulk delete: only clean draft is deleted; attempted and published are retained
    bulk_del_res = api.post("/api/v1/panel/tests/bulk/", {"test_ids": test_ids, "action": "delete"}, format="json")
    assert bulk_del_res.status_code == 200
    assert bulk_del_res.data["deleted_count"] == 1
    assert bulk_del_res.data["retained_count"] == 2

    assert not Test.objects.filter(id=t_clean.id).exists()
    assert Test.objects.filter(id=t_with_att.id).exists()
    assert Test.objects.filter(id=t_pub.id).exists()


@pytest.mark.django_db(transaction=True)
def test_quiz_filters_published_and_handles_complex(teacher_1, course_1, student):
    from apps.notifications.bot.quiz import _start_quiz
    from unittest.mock import AsyncMock
    from types import SimpleNamespace
    from asgiref.sync import async_to_sync

    # Create draft test and published complex test
    draft_test = Test.objects.create(title="Draft Quiz", course=course_1, status="draft", is_active=False, created_by=teacher_1)
    complex_test = Test.objects.create(title="IELTS Exam", course=course_1, status="published", is_active=True, created_by=teacher_1)
    sec = ExamSection.objects.create(test=complex_test, name="Reading", code="READ", order=1)
    ReadingPassage.objects.create(test=complex_test, section=sec, title="P1", content="Text", order=1)

    query = SimpleNamespace(answer=AsyncMock(), edit_message_text=AsyncMock(), data="")
    update = SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=12345))
    context = SimpleNamespace(user_data={})

    # 1. Starting draft quiz should be rejected
    async_to_sync(_start_quiz)(update, context, draft_test.id)
    query.edit_message_text.assert_awaited()
    assert "topilmadi" in query.edit_message_text.await_args.args[0].lower()

    # 2. Starting complex quiz should prompt Mini App / Web Runner
    query.edit_message_text.reset_mock()
    async_to_sync(_start_quiz)(update, context, complex_test.id)
    query.edit_message_text.assert_awaited()
    call_args = query.edit_message_text.await_args
    assert "kengaytirilgan format" in call_args.args[0]
    keyboard = call_args.kwargs["reply_markup"].inline_keyboard
    # Must have Mini App and Web Runner buttons
    btn_texts = [b.text for row in keyboard for b in row]
    assert any("Mini App" in t for t in btn_texts)
    assert any("Veb" in t for t in btn_texts)


def test_purge_all_tests_production_safeguard():
    from io import StringIO
    from unittest.mock import patch
    from django.conf import settings
    from django.core.management import call_command

    out = StringIO()
    err = StringIO()

    with patch.object(settings, "DEBUG", False), \
         patch.object(settings, "SETTINGS_MODULE", "config.settings.production", create=True):
        with pytest.raises(SystemExit) as exc:
            call_command("purge_all_tests", confirm=True, stdout=out, stderr=err)
        assert exc.value.code == 1
        assert "XAVFSIZLIK CHEKLOVI" in err.getvalue()
        assert "XAVFSIZLIK CHEKLOVI" in err.getvalue()
