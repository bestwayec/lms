"""Regression tests for the homework authorization / grading-integrity audit.

Each test pins a defect confirmed in the Stage 4 code (PR #139) and fails on
that code:

* P0 direct ``submit`` created a HomeworkSubmission for any authenticated user;
* P0 grader exceptions / missing Result / missing attempt were stored as
  GRADED with score 0;
* P1 the list endpoint (GET) wrote rows and linked an older Result of the same
  test to a new homework;
* P1 start/save/submit ignored start_date, due_date, cancellation, the
  homework time limit and attempt limits; autosave after finish reported ok;
* P1 idempotency keys were global across teachers; any vocabulary pack,
  essay topic or lesson could be attached; assigning a test mutated it.
"""

from __future__ import annotations

import threading
from datetime import timedelta
from unittest import mock

import pytest
from django.db import connection
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.courses.group_service import remove_student_from_group
from apps.courses.homework_service import (
    HomeworkConflict,
    create_unified_homework,
    derive_submission_status,
    get_student_homework_list,
    start_student_homework,
    submit_student_homework,
)
from apps.courses.models import Course, Homework, HomeworkSubmission, Lesson, Module, StudentGroup
from apps.essays.models import EssayTopic
from apps.results.models import Result
from apps.tests.models import Choice, Question, StudentAnswer, Test, TestAttempt
from apps.tests.services import SaveAnswerService, StartAttemptService, SubmitAttemptService
from apps.tests.studio_service import student_has_assignment
from apps.vocabulary.models import VocabularyPack

BASE = "/api/v1/school/student/homeworks"


def _user(email, role="student", **kw):
    return User.objects.create_user(email=email, password="pass", role=role, first_name="F", last_name="L", **kw)


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def teacher(db):
    return _user("hi_teacher@example.com", role="teacher")


@pytest.fixture
def other_teacher(db):
    return _user("hi_teacher2@example.com", role="teacher")


@pytest.fixture
def student(db):
    return _user("hi_student@example.com")


@pytest.fixture
def outsider(db):
    return _user("hi_outsider@example.com")


@pytest.fixture
def group(teacher, student):
    g = StudentGroup.objects.create(name="HI group", teacher=teacher)
    g.students.add(student)
    return g


@pytest.fixture
def other_group(other_teacher, outsider):
    g = StudentGroup.objects.create(name="Other center group", teacher=other_teacher)
    g.students.add(outsider)
    return g


@pytest.fixture
def test_obj(teacher):
    course = Course.objects.create(teacher=teacher, title="HI course", slug="hi-course")
    t = Test.objects.create(
        course=course,
        title="HI quiz",
        created_by=teacher,
        status=Test.Status.PUBLISHED,
        access_type=Test.AccessType.STUDENTS_ONLY,
        subject="mathematics",
        time_limit_minutes=30,
        max_attempts=0,
    )
    for pos in (1, 2):
        q = Question.objects.create(test=t, position=pos, text=f"Q{pos}", points=1)
        Choice.objects.create(question=q, text="right", is_correct=True, position=1)
        Choice.objects.create(question=q, text="wrong", is_correct=False, position=2)
    return t


def _hw(teacher, group, test=None, **kw):
    kw.setdefault("due_date", timezone.now() + timedelta(days=2))
    hw, _ = create_unified_homework(teacher, title="HW", group_id=group.id, test_id=test.id if test else None, **kw)
    return hw


def _answer(attempt, student, correct: bool):
    for q in attempt.test.questions.all():
        choice = q.choices.get(is_correct=correct)
        SaveAnswerService.execute(attempt.id, q.id, choice_ids=[choice.id], student=student)


# --------------------------------------------------------------------------- P0 authorization


@pytest.mark.django_db
@pytest.mark.parametrize("action", ["start", "save", "submit"])
def test_unrelated_student_cannot_write_and_no_row_is_created(api, teacher, group, test_obj, outsider, action):
    hw = _hw(teacher, group, test_obj)
    api.force_authenticate(outsider)
    resp = api.post(f"{BASE}/{hw.id}/{action}/", {"answers": {"x": 1}}, format="json")
    assert resp.status_code == 404
    assert not HomeworkSubmission.objects.filter(homework=hw).exists()


@pytest.mark.django_db
@pytest.mark.parametrize("suffix", ["", "result/"])
def test_unrelated_users_cannot_read(api, teacher, group, test_obj, outsider, other_teacher, suffix):
    hw = _hw(teacher, group, test_obj)
    for user in (outsider, other_teacher):
        api.force_authenticate(user)
        assert api.get(f"{BASE}/{hw.id}/{suffix}").status_code == 404
    api.force_authenticate(outsider)
    assert all(item["id"] != hw.id for item in api.get(f"{BASE}/").data["results"])


@pytest.mark.django_db
def test_other_center_student_cannot_submit_individual_homework(api, teacher, group, student, outsider, other_group):
    hw, _ = create_unified_homework(
        teacher, title="Solo", student_id=student.id, content_type="custom",
        due_date=timezone.now() + timedelta(days=1),
    )
    api.force_authenticate(outsider)
    assert api.post(f"{BASE}/{hw.id}/submit/", {"answers": {"text": "x"}}, format="json").status_code == 404
    assert not HomeworkSubmission.objects.filter(homework=hw).exists()


@pytest.mark.django_db
def test_teacher_cannot_assign_individual_homework_to_foreign_student(teacher, group, outsider, other_group):
    with pytest.raises(PermissionError):
        create_unified_homework(
            teacher, title="x", student_id=outsider.id, content_type="custom",
            due_date=timezone.now() + timedelta(days=1),
        )


@pytest.mark.django_db
def test_direct_submit_without_start_is_rejected(api, teacher, group, student):
    hw, _ = create_unified_homework(
        teacher, title="Custom", group_id=group.id, content_type="custom",
        due_date=timezone.now() + timedelta(days=1),
    )
    api.force_authenticate(student)
    resp = api.post(f"{BASE}/{hw.id}/submit/", {"answers": {"text": "hello"}}, format="json")
    assert resp.status_code == 409 and resp.data["code"] == "not_started"
    assert not HomeworkSubmission.objects.filter(homework=hw).exists()


@pytest.mark.django_db
def test_removed_student_keeps_history_but_cannot_write(api, teacher, group, student, test_obj):
    hw = _hw(teacher, group, test_obj, max_attempts=3)
    start = start_student_homework(student, hw.id)
    attempt = TestAttempt.objects.get(id=start["attempt_id"])
    _answer(attempt, student, correct=True)
    assert submit_student_homework(student, hw.id)["status"] == "graded"

    remove_student_from_group(group, student, actor=teacher)

    api.force_authenticate(student)
    result = api.get(f"{BASE}/{hw.id}/result/")
    assert result.status_code == 200 and result.data["percentage"] == 100.0
    listed = {i["id"]: i for i in api.get(f"{BASE}/").data["results"]}
    assert listed[hw.id]["can_start"] is False and listed[hw.id]["is_current_recipient"] is False
    assert api.post(f"{BASE}/{hw.id}/start/").status_code == 404
    # The teacher still sees the preserved submission.
    assert HomeworkSubmission.objects.get(homework=hw, student=student).status == "graded"


# --------------------------------------------------------------------------- P0 grading integrity


@pytest.mark.django_db
def test_grader_exception_is_grading_failed_not_zero_and_retry_grades(teacher, group, student, test_obj):
    hw = _hw(teacher, group, test_obj)
    attempt_id = start_student_homework(student, hw.id)["attempt_id"]
    attempt = TestAttempt.objects.get(id=attempt_id)
    _answer(attempt, student, correct=True)

    with mock.patch.object(SubmitAttemptService, "execute", side_effect=RuntimeError("grader down")):
        out = submit_student_homework(student, hw.id)
    assert out["status"] == "grading_failed" and out["ok"] is False
    assert out["score"] is None and out["percentage"] is None
    sub = HomeworkSubmission.objects.get(homework=hw, student=student)
    assert sub.score is None and sub.percentage is None
    # Answers preserved, attempt still open for the retry.
    assert StudentAnswer.objects.filter(attempt_id=attempt_id).count() == 2
    assert TestAttempt.objects.get(id=attempt_id).status == TestAttempt.Status.IN_PROGRESS
    assert derive_submission_status(hw, sub)[0] == "grading_failed"

    retry = submit_student_homework(student, hw.id)
    assert retry["status"] == "graded" and retry["percentage"] == 100.0
    assert Result.objects.filter(attempt_id=attempt_id).count() == 1


@pytest.mark.django_db
def test_missing_official_result_is_grading_failed(teacher, group, student, test_obj):
    hw = _hw(teacher, group, test_obj)
    attempt_id = start_student_homework(student, hw.id)["attempt_id"]

    def finish_without_result(aid, user):
        TestAttempt.objects.filter(id=aid).update(status=TestAttempt.Status.COMPLETED, completed_at=timezone.now())

    with mock.patch.object(SubmitAttemptService, "execute", side_effect=finish_without_result):
        out = submit_student_homework(student, hw.id)
    assert out["status"] == "grading_failed"
    assert out["score"] is None
    sub = HomeworkSubmission.objects.get(homework=hw, student=student)
    assert sub.status == "grading_failed" and sub.score is None and sub.grading_error
    assert not Result.objects.filter(attempt_id=attempt_id).exists()


@pytest.mark.django_db
def test_genuine_zero_is_graded(teacher, group, student, test_obj):
    hw = _hw(teacher, group, test_obj)
    attempt = TestAttempt.objects.get(id=start_student_homework(student, hw.id)["attempt_id"])
    _answer(attempt, student, correct=False)
    out = submit_student_homework(student, hw.id)
    assert out["status"] == "graded"
    assert out["score"] == 0.0 and out["percentage"] == 0.0
    assert Result.objects.get(attempt=attempt).score == 0


@pytest.mark.django_db
def test_duplicate_finish_is_idempotent(teacher, group, student, test_obj):
    hw = _hw(teacher, group, test_obj)
    attempt = TestAttempt.objects.get(id=start_student_homework(student, hw.id)["attempt_id"])
    _answer(attempt, student, correct=True)
    first = submit_student_homework(student, hw.id)
    second = submit_student_homework(student, hw.id)
    assert first["status"] == second["status"] == "graded"
    assert first["percentage"] == second["percentage"] == 100.0
    assert Result.objects.filter(attempt=attempt).count() == 1


@pytest.mark.django_db
def test_finish_in_official_runner_is_recorded_via_linked_attempt(teacher, group, student, test_obj):
    """The real journey: start homework → TakeTest submits the attempt → homework shows the Result."""
    hw = _hw(teacher, group, test_obj)
    attempt = TestAttempt.objects.get(id=start_student_homework(student, hw.id)["attempt_id"])
    _answer(attempt, student, correct=True)
    SubmitAttemptService.execute(attempt.id, student)  # what the runner does
    item = next(i for i in get_student_homework_list(student) if i["id"] == hw.id)
    assert item["status"] == "graded" and item["percentage"] == 100.0


@pytest.mark.django_db
def test_legacy_fabricated_zero_is_not_shown_as_grade(teacher, group, student, test_obj):
    hw = _hw(teacher, group, test_obj)
    sub = HomeworkSubmission.objects.create(
        homework=hw, student=student, status="graded", is_completed=True,
        score=0, percentage=0.0, attempts_count=1, completed_at=timezone.now(),
    )
    status, score, _ = derive_submission_status(hw, sub)
    assert status == "grading_failed" and score is None


# --------------------------------------------------------------------------- P1 GET safety / stale links


@pytest.mark.django_db
def test_list_does_not_write_or_link_an_older_result(api, teacher, group, student, test_obj):
    # Student practised the same test before the homework existed.
    old = StartAttemptService.execute(test_id=test_obj.id, student=student)
    _answer(old, student, correct=True)
    SubmitAttemptService.execute(old.id, student)
    TestAttempt.objects.filter(id=old.id).update(started_at=timezone.now() - timedelta(days=3))
    assert Result.objects.filter(student=student, test=test_obj).exists()

    hw = _hw(teacher, group, test_obj)
    api.force_authenticate(student)
    item = next(i for i in api.get(f"{BASE}/").data["results"] if i["id"] == hw.id)
    assert item["status"] == "not_started" and item["score"] is None
    assert api.get(f"{BASE}/{hw.id}/").status_code == 200
    assert not HomeworkSubmission.objects.filter(homework=hw).exists()


@pytest.mark.django_db
def test_legacy_stale_linked_row_is_ignored(teacher, group, student, test_obj):
    old = StartAttemptService.execute(test_id=test_obj.id, student=student)
    _answer(old, student, correct=True)
    SubmitAttemptService.execute(old.id, student)
    TestAttempt.objects.filter(id=old.id).update(started_at=timezone.now() - timedelta(days=3))
    hw = _hw(teacher, group, test_obj)
    result = Result.objects.get(attempt=old)
    HomeworkSubmission.objects.create(  # what the old GET fallback wrote
        homework=hw, student=student, status="graded", is_completed=True, result=result,
        score=result.score, percentage=float(result.percentage), completed_at=result.calculated_at,
    )
    item = next(i for i in get_student_homework_list(student) if i["id"] == hw.id)
    assert item["status"] == "not_started" and item["can_start"] is True


# --------------------------------------------------------------------------- P1 window / timer / attempts


@pytest.mark.django_db
def test_not_yet_open_and_expired_and_cancelled(api, teacher, group, student, test_obj):
    api.force_authenticate(student)
    future = _hw(teacher, group, test_obj, start_date=timezone.now() + timedelta(hours=1))
    resp = api.post(f"{BASE}/{future.id}/start/")
    assert resp.status_code == 409 and resp.data["code"] == "not_open"

    expired = _hw(teacher, group, test_obj)
    Homework.objects.filter(id=expired.id).update(due_date=timezone.now() - timedelta(minutes=1))
    resp = api.post(f"{BASE}/{expired.id}/start/")
    assert resp.status_code == 409 and resp.data["code"] == "deadline_passed"

    custom, _ = create_unified_homework(
        teacher, title="c", group_id=group.id, content_type="custom", due_date=timezone.now() + timedelta(days=1)
    )
    assert api.post(f"{BASE}/{custom.id}/start/").status_code == 200
    from apps.courses.homework_service import cancel_teacher_homework

    cancel_teacher_homework(teacher, custom.id)
    for action in ("start", "save", "submit"):
        resp = api.post(f"{BASE}/{custom.id}/{action}/", {"answers": {"text": "x"}}, format="json")
        assert resp.status_code == 409, action
    assert api.get(f"{BASE}/{custom.id}/").data["status"] == "cancelled"


@pytest.mark.django_db
def test_no_autosave_after_finish_and_custom_time_limit(api, teacher, group, student):
    hw, _ = create_unified_homework(
        teacher, title="c", group_id=group.id, content_type="custom", time_limit=10,
        due_date=timezone.now() + timedelta(days=1),
    )
    api.force_authenticate(student)
    assert api.post(f"{BASE}/{hw.id}/start/").status_code == 200
    assert api.post(f"{BASE}/{hw.id}/save/", {"answers": {"text": "draft"}}, format="json").status_code == 200

    HomeworkSubmission.objects.filter(homework=hw).update(started_at=timezone.now() - timedelta(minutes=11))
    late = api.post(f"{BASE}/{hw.id}/save/", {"answers": {"text": "late"}}, format="json")
    assert late.status_code == 409 and late.data["code"] == "time_expired"
    assert HomeworkSubmission.objects.get(homework=hw).answers_payload == {"text": "draft"}

    HomeworkSubmission.objects.filter(homework=hw).update(started_at=timezone.now())
    done = api.post(f"{BASE}/{hw.id}/submit/", {"answers": {"text": "final"}}, format="json")
    assert done.status_code == 200 and done.data["status"] == "awaiting_review" and done.data["score"] is None
    after = api.post(f"{BASE}/{hw.id}/save/", {"answers": {"text": "overwrite"}}, format="json")
    assert after.status_code == 409 and after.data["code"] == "already_completed"
    assert HomeworkSubmission.objects.get(homework=hw).answers_payload == {"text": "final"}


@pytest.mark.django_db
def test_max_attempts_enforced_and_retake_resets_submission(teacher, group, student, test_obj):
    hw = _hw(teacher, group, test_obj, max_attempts=2)
    a1 = TestAttempt.objects.get(id=start_student_homework(student, hw.id)["attempt_id"])
    _answer(a1, student, correct=False)
    assert submit_student_homework(student, hw.id)["percentage"] == 0.0

    a2_id = start_student_homework(student, hw.id)["attempt_id"]
    assert a2_id != a1.id
    sub = HomeworkSubmission.objects.get(homework=hw, student=student)
    assert sub.is_completed is False and sub.score is None and sub.attempts_count == 2
    _answer(TestAttempt.objects.get(id=a2_id), student, correct=True)
    assert submit_student_homework(student, hw.id)["percentage"] == 100.0

    with pytest.raises(HomeworkConflict) as exc:
        start_student_homework(student, hw.id)
    assert exc.value.code == "attempts_exhausted"


@pytest.mark.django_db
def test_resume_does_not_consume_an_attempt(teacher, group, student, test_obj):
    hw = _hw(teacher, group, test_obj, max_attempts=1)
    first = start_student_homework(student, hw.id)
    again = start_student_homework(student, hw.id)
    assert first["attempt_id"] == again["attempt_id"]
    assert HomeworkSubmission.objects.get(homework=hw).attempts_count == 1


@pytest.mark.django_db
def test_expired_official_attempt_is_finalised_with_saved_answers(teacher, group, student, test_obj):
    hw = _hw(teacher, group, test_obj, max_attempts=1)
    attempt = TestAttempt.objects.get(id=start_student_homework(student, hw.id)["attempt_id"])
    _answer(attempt, student, correct=True)
    Homework.objects.filter(id=hw.id).update(created_at=timezone.now() - timedelta(hours=1))
    TestAttempt.objects.filter(id=attempt.id).update(started_at=timezone.now() - timedelta(minutes=31))
    out = start_student_homework(student, hw.id)  # resume after the timer ran out
    assert out["status"] == "graded" and out["percentage"] == 100.0
    assert TestAttempt.objects.get(id=attempt.id).status == TestAttempt.Status.TIMEOUT


# --------------------------------------------------------------------------- P1 creation authorization


@pytest.mark.django_db
def test_idempotency_key_is_isolated_per_teacher(teacher, other_teacher, group, other_group):
    due = timezone.now() + timedelta(days=1)
    a, created_a = create_unified_homework(
        teacher, title="A", group_id=group.id, content_type="custom", due_date=due, idempotency_key="k1"
    )
    b, created_b = create_unified_homework(
        other_teacher, title="B", group_id=other_group.id, content_type="custom", due_date=due, idempotency_key="k1"
    )
    assert created_a and created_b and a.id != b.id and b.group_id == other_group.id


@pytest.mark.django_db
def test_foreign_vocabulary_essay_and_lesson_are_rejected(teacher, other_teacher, group, other_group):
    due = timezone.now() + timedelta(days=1)
    pack = VocabularyPack.objects.create(teacher=other_teacher, title="P", raw_words_text="a")
    topic = EssayTopic.objects.create(title="T", created_by=other_teacher)
    course = Course.objects.create(teacher=other_teacher, title="C2", slug="hi-c2")
    module = Module.objects.create(course=course, title="M")
    lesson = Lesson.objects.create(module=module, title="L")
    with pytest.raises(PermissionError):
        create_unified_homework(teacher, title="v", group_id=group.id, vocabulary_pack_id=pack.id, due_date=due)
    with pytest.raises(PermissionError):
        create_unified_homework(teacher, title="e", group_id=group.id, essay_topic_id=topic.id, due_date=due)
    with pytest.raises(PermissionError):
        create_unified_homework(teacher, title="l", group_id=group.id, lesson_id=lesson.id, due_date=due)
    assert not Homework.objects.filter(group=group).exists()
    own = VocabularyPack.objects.create(teacher=teacher, title="mine", raw_words_text="a")
    hw, _ = create_unified_homework(teacher, title="v", group_id=group.id, vocabulary_pack_id=own.id, due_date=due)
    assert hw.vocabulary_pack_id == own.id


@pytest.mark.django_db
def test_assigning_does_not_mutate_shared_test(teacher, group, test_obj):
    _hw(teacher, group, test_obj)
    test_obj.refresh_from_db()
    assert test_obj.assigned_group_id is None


@pytest.mark.django_db
def test_cancelled_homework_does_not_grant_test_access(teacher, group, student, test_obj):
    hw = _hw(teacher, group, test_obj)
    assert student_has_assignment(student, test_obj)
    from apps.courses.homework_service import cancel_teacher_homework

    cancel_teacher_homework(teacher, hw.id)
    assert not student_has_assignment(student, test_obj)


@pytest.mark.django_db
def test_teacher_grades_custom_work_zero_is_valid_and_foreign_teacher_404(api, teacher, other_teacher, group, student):
    hw, _ = create_unified_homework(
        teacher, title="c", group_id=group.id, content_type="custom", due_date=timezone.now() + timedelta(days=1)
    )
    start_student_homework(student, hw.id)
    submit_student_homework(student, hw.id, {"text": "answer"})
    sub = HomeworkSubmission.objects.get(homework=hw)
    url = f"/api/v1/school/teacher/homework-submissions/{sub.id}/grade/"
    api.force_authenticate(other_teacher)
    assert api.post(url, {"score": 5, "max_score": 10}, format="json").status_code == 404
    api.force_authenticate(teacher)
    resp = api.post(url, {"score": 0, "max_score": 10, "feedback": "redo"}, format="json")
    assert resp.status_code == 200 and resp.data["status"] == "graded" and resp.data["score"] == 0.0
    api.force_authenticate(student)
    res = api.get(f"{BASE}/{hw.id}/result/").data
    assert res["status"] == "graded" and res["score"] == 0.0 and res["feedback"] == "redo"


# --------------------------------------------------------------------------- concurrency (PostgreSQL)


@pytest.mark.django_db(transaction=True)
@pytest.mark.skipif(connection.vendor != "postgresql", reason="row locks need PostgreSQL")
def test_concurrent_autosave_and_finish_never_overwrites_final_answers(teacher, group, student):
    hw, _ = create_unified_homework(
        teacher, title="c", group_id=group.id, content_type="custom", due_date=timezone.now() + timedelta(days=1)
    )
    start_student_homework(student, hw.id)
    barrier = threading.Barrier(2)
    outcomes: dict[str, str] = {}

    def do(name, fn):
        from django.db import connection as conn

        try:
            barrier.wait()
            fn()
            outcomes[name] = "ok"
        except HomeworkConflict as exc:
            outcomes[name] = exc.code
        finally:
            conn.close()

    from apps.courses.homework_service import save_student_homework_progress

    t1 = threading.Thread(target=do, args=("submit", lambda: submit_student_homework(student, hw.id, {"text": "final"})))
    t2 = threading.Thread(target=do, args=("save", lambda: save_student_homework_progress(student, hw.id, {"text": "late"})))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    sub = HomeworkSubmission.objects.get(homework=hw)
    assert outcomes["submit"] == "ok"
    assert sub.is_completed
    if outcomes["save"] == "ok":  # save won the lock first; submit then wrote the final payload
        assert sub.answers_payload == {"text": "final"}
    else:
        assert outcomes["save"] == "already_completed"
        assert sub.answers_payload == {"text": "final"}


# --------------------------------------------------------------------------- teacher progress


@pytest.mark.django_db
def test_teacher_roster_uses_authoritative_status(api, teacher, other_teacher, group, student, test_obj):
    peer = _user("hi_peer@example.com")
    group.students.add(peer)
    # peer practised before the homework: must NOT count as a completion
    old = StartAttemptService.execute(test_id=test_obj.id, student=peer)
    SubmitAttemptService.execute(old.id, peer)
    TestAttempt.objects.filter(id=old.id).update(started_at=timezone.now() - timedelta(days=2))

    hw = _hw(teacher, group, test_obj)
    attempt = TestAttempt.objects.get(id=start_student_homework(student, hw.id)["attempt_id"])
    _answer(attempt, student, correct=False)
    submit_student_homework(student, hw.id)
    remove_student_from_group(group, student, actor=teacher)

    api.force_authenticate(teacher)
    data = api.get(f"/api/v1/school/teacher/homeworks/{hw.id}/roster/").data
    rows = {r["student_id"]: r for r in data["students"]}
    assert rows[student.id]["status"] == "graded" and rows[student.id]["score"] == 0.0
    assert rows[student.id]["is_current_member"] is False
    assert rows[peer.id]["status"] == "not_started"
    assert data["summary"]["submitted"] == 1 and data["summary"]["total_students"] == 1

    overview = api.get("/api/v1/school/teacher/").data
    card = next(a for a in overview["assignments"] if a["id"] == hw.id)
    assert card["submissions_count"] == 1 and card["graded_count"] == 1

    api.force_authenticate(other_teacher)
    assert api.get(f"/api/v1/school/teacher/homeworks/{hw.id}/roster/").status_code == 404


@pytest.mark.django_db
def test_assigned_test_cannot_be_rebuilt_under_live_homework(teacher, group, test_obj):
    from apps.tests import studio_service as svc

    Question.objects.filter(test=test_obj).update(config={"studio_type": "single"})
    hw = _hw(teacher, group, test_obj)
    payload = {"title": "changed", "subject": "uzbek", "blocks": []}
    with pytest.raises(svc.StudioConflict) as exc:
        svc.save_test(teacher, payload, test=test_obj)
    assert exc.value.code == "has_assignments"
    test_obj.refresh_from_db()
    assert test_obj.status == Test.Status.PUBLISHED and test_obj.questions.count() == 2
    from apps.courses.homework_service import cancel_teacher_homework

    cancel_teacher_homework(teacher, hw.id)
    assert not svc.has_live_assignments(test_obj)
