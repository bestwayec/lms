"""Cross-teacher / cross-center / cross-student isolation, probed endpoint by endpoint.

The victim owns a center, a group with one student, a draft test, a group-only test, an
attempt, a result and an attendance register. Four unrelated actors (anonymous, another
student, another teacher, another center's admin) must never be able to read any of it.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Profile
from apps.attendance.models import AttendanceSession
from apps.courses.models import Course, StudentGroup
from apps.organizations.models import CenterBranch, LearningCenter
from apps.results.models import Result
from apps.tests.models import Choice, Question, Test, TestAttempt

User = get_user_model()


def _user(email: str, role: str, **extra):
    user = User.objects.create_user(email=email, password="x-Pass-123!", role=role, **extra)
    Profile.objects.get_or_create(user=user)
    return user


def _client(user=None) -> APIClient:
    client = APIClient()
    if user is not None:
        client.force_authenticate(user)
    return client


@pytest.fixture
def world(db):
    owner_a = _user("owner-a@example.test", "center_admin")
    owner_b = _user("owner-b@example.test", "center_admin")
    center_a = LearningCenter.objects.create(name="Center A", owner=owner_a)
    center_b = LearningCenter.objects.create(name="Center B", owner=owner_b)
    branch_a = CenterBranch.objects.create(name="Branch A", center=center_a, director=owner_a)
    branch_b = CenterBranch.objects.create(name="Branch B", center=center_b, director=owner_b)
    for user, center, branch in ((owner_a, center_a, branch_a), (owner_b, center_b, branch_b)):
        user.learning_center, user.branch = center, branch
        user.save(update_fields=["learning_center", "branch"])

    teacher_a = _user("teacher-a@example.test", "teacher", learning_center=center_a, branch=branch_a)
    student_a = _user("student-a@example.test", "student", learning_center=center_a, branch=branch_a)
    teacher_b = _user("teacher-b@example.test", "teacher", learning_center=center_b, branch=branch_b)
    student_b = _user("student-b@example.test", "student", learning_center=center_b, branch=branch_b)

    group_a = StudentGroup.objects.create(name="A-1", teacher=teacher_a, branch=branch_a)
    group_a.students.add(student_a)
    group_b = StudentGroup.objects.create(name="B-1", teacher=teacher_b, branch=branch_b)
    group_b.students.add(student_b)

    course_a = Course.objects.create(teacher=teacher_a, title="Course A", slug="course-a")
    draft = Test.objects.create(title="Draft A", course=course_a, subject="uzbek", status=Test.Status.DRAFT)
    group_test = Test.objects.create(
        title="Group-only A", course=course_a, subject="uzbek", status=Test.Status.PUBLISHED, is_active=True,
        access_type=Test.AccessType.STUDENTS_ONLY, assigned_group=group_a,
    )
    for test in (draft, group_test):
        question = Question.objects.create(test=test, text="Secret question", position=1, points=1)
        Choice.objects.create(question=question, text="Right", is_correct=True, position=1)
        Choice.objects.create(question=question, text="Wrong", is_correct=False, position=2)

    attempt = TestAttempt.objects.create(test=group_test, student=student_a, status=TestAttempt.Status.COMPLETED,
                                         completed_at=timezone.now())
    result = Result.objects.create(
        attempt=attempt, student=student_a, test=group_test, course=course_a, total_questions=1,
        correct_answers=1, wrong_answers=0, score=Decimal("1"), max_score=Decimal("1"), percentage=Decimal("100"),
        is_passed=True, time_taken_seconds=60,
    )
    session = AttendanceSession.objects.create(group=group_a, teacher=teacher_a, lesson_date=timezone.localdate())

    from datetime import timedelta

    from apps.courses.models import Homework, HomeworkSubmission

    homework = Homework.objects.create(
        group=group_a, title="HW A", content_type=Homework.ContentType.CUSTOM, created_by=teacher_a,
        due_date=timezone.now() + timedelta(days=2),
    )
    submission = HomeworkSubmission.objects.create(
        homework=homework, student=student_a, status=HomeworkSubmission.Status.AWAITING_REVIEW,
        is_completed=True, answers_payload={"text": "A's answer"}, attempts_count=1, completed_at=timezone.now(),
    )

    return {
        "ids": dict(draft=draft.id, group_test=group_test.id, attempt=attempt.id, result=result.id,
                    group=group_a.id, student=student_a.id, session=session.id,
                    homework=homework.id, submission=submission.id),
        "actors": {
            "anonymous": None,
            "other_student": student_b,
            "other_teacher": teacher_b,
            "other_center_admin": owner_b,
        },
        "owner_a": owner_a, "teacher_a": teacher_a, "student_a": student_a,
    }


# (name, url template). Every one is a GET of something that belongs to the victim.
READ_ENDPOINTS = [
    ("draft test detail", "/api/tests/{draft}/"),
    ("draft test detail (v1)", "/api/v1/tests/{draft}/"),
    ("group test detail", "/api/tests/{group_test}/"),
    ("group test gradebook", "/api/tests/{group_test}/gradebook/"),
    ("group test analytics", "/api/tests/{group_test}/analytics/"),
    ("group test item analysis", "/api/tests/{group_test}/item-analysis/"),
    ("teacher test analytics", "/api/tests/teacher/tests/{group_test}/analytics/"),
    ("attempt", "/api/tests/attempts/{attempt}/"),
    ("attempt details", "/api/tests/attempts/{attempt}/details/"),
    ("teacher attempt details", "/api/tests/teacher/attempts/{attempt}/details/"),
    ("result detail", "/api/results/{result}/detail/"),
    ("result pdf", "/api/results/{result}/pdf/"),
    ("result diagnostics", "/api/tests/results/{result}/diagnostics/"),
    ("group detail", "/api/v1/school/groups/{group}/"),
    ("group members", "/api/v1/school/groups/{group}/members/"),
    ("group analytics", "/api/v1/school/groups/{group}/analytics/"),
    ("group excel export", "/api/v1/school/groups/{group}/export/excel/"),
    ("group pdf export", "/api/v1/school/groups/{group}/export/pdf/"),
    ("group student view", "/api/v1/school/groups/{group}/student-view/"),
    ("group finance summary", "/api/v1/courses/groups/{group}/finance-summary/"),
    ("attendance session", "/api/v1/school/attendance/sessions/{session}/"),
    ("student attendance", "/api/v1/school/attendance/students/{student}/"),
    ("student tuition", "/api/v1/school/tuition/students/{student}/"),
    # Added for the multi-center audit (Teacher Workspace / Homework / admin panel)
    ("group history", "/api/v1/school/groups/{group}/history/"),
    ("group member results", "/api/v1/school/groups/{group}/members/{student}/results/"),
    ("group monthly report pdf", "/api/v1/school/groups/{group}/export/monthly-report-pdf/"),
    ("homework roster", "/api/v1/school/teacher/homeworks/{homework}/roster/"),
    ("homework live tablo", "/api/v1/school/teacher/homeworks/{homework}/live/"),
    ("student homework detail", "/api/v1/school/student/homeworks/{homework}/"),
    ("student homework result", "/api/v1/school/student/homeworks/{homework}/result/"),
    ("panel test detail", "/api/v1/panel/tests/{draft}/"),
    ("panel test questions", "/api/v1/panel/tests/{draft}/questions/"),
    ("studio test detail", "/api/v1/teacher/studio/tests/{draft}/"),
    ("studio test analysis", "/api/v1/teacher/studio/tests/{group_test}/analysis/"),
]


def _leaks(world, actor_name):
    user = world["actors"][actor_name]
    leaks = []
    for label, template in READ_ENDPOINTS:
        url = template.format(**world["ids"])
        response = _client(user).get(url)
        if response.status_code < 300:
            leaks.append(f"{label}: {url} -> {response.status_code}")
    return leaks


@pytest.mark.django_db
@pytest.mark.parametrize("actor", ["anonymous", "other_student", "other_teacher", "other_center_admin"])
def test_unrelated_actors_read_nothing_of_the_victim(world, actor):
    assert _leaks(world, actor) == []


@pytest.mark.django_db
def test_the_owning_teacher_and_student_still_have_their_access(world):
    """Guards against 'fixing' isolation by denying everyone."""
    ids = world["ids"]
    teacher, student = _client(world["teacher_a"]), _client(world["student_a"])
    assert teacher.get(f"/api/v1/school/groups/{ids['group']}/").status_code == 200
    assert teacher.get(f"/api/tests/{ids['draft']}/").status_code == 200
    assert student.get(f"/api/results/{ids['result']}/detail/").status_code == 200


# -- test visibility: catalogue, detail content, group assignment ---------------------------


def _titles(response) -> list[str]:
    body = response.json()
    items = body["results"] if isinstance(body, dict) and "results" in body else body
    return [item["title"] for item in items]


@pytest.mark.django_db
def test_group_only_test_is_hidden_from_non_members_and_visible_to_members(world):
    ids = world["ids"]
    url = f"/api/tests/{ids['group_test']}/"
    assert _client(None).get(url).status_code == 404
    assert _client(world["actors"]["other_student"]).get(url).status_code == 404
    assert "Group-only A" not in _titles(_client(None).get("/api/tests/"))
    assert "Group-only A" not in _titles(_client(world["actors"]["other_student"]).get("/api/tests/"))
    member = _client(world["student_a"])
    assert member.get(url).status_code == 200
    assert "Group-only A" in _titles(member.get("/api/tests/"))


@pytest.mark.django_db
def test_detail_never_returns_exam_content_to_students_or_guests(world):
    public = Test.objects.create(title="Public", course=Course.objects.get(slug="course-a"), subject="uzbek",
                                 status=Test.Status.PUBLISHED, is_active=True, access_pin="4821")
    question = Question.objects.create(test=public, text="Public secret question", position=1, points=1)
    Choice.objects.create(question=question, text="Right", is_correct=True, position=1)
    for client in (_client(None), _client(world["actors"]["other_student"]), _client(world["student_a"])):
        response = client.get(f"/api/tests/{public.id}/")
        assert response.status_code == 200
        body = response.json()
        assert body["questions"] == [] and body["passages"] == []
        assert "Public secret question" not in response.content.decode()
        assert body["total_questions"] == 1  # the catalogue facts are still there
    # the author still gets the content
    assert _client(world["teacher_a"]).get(f"/api/tests/{public.id}/").json()["questions"]


@pytest.mark.django_db
def test_draft_is_invisible_to_students_and_other_teachers_but_not_to_its_author(world):
    url = f"/api/tests/{world['ids']['draft']}/"
    for actor in ("other_student", "other_teacher"):
        assert _client(world["actors"][actor]).get(url).status_code == 404
    assert _client(world["student_a"]).get(url).status_code == 404
    assert _client(world["teacher_a"]).get(url).status_code == 200


@pytest.mark.django_db
def test_catalogue_question_counts_are_not_multiplied_by_the_visibility_rule(world):
    """The rule uses subqueries; a join here would double the Count() annotation per group/homework."""
    from apps.courses.models import Homework

    test = Test.objects.get(pk=world["ids"]["group_test"])
    other_group = StudentGroup.objects.create(name="A-2", teacher=world["teacher_a"])
    other_group.students.add(world["student_a"])
    for group in (test.assigned_group, other_group):
        Homework.objects.create(group=group, test=test, title="HW", due_date=timezone.now() + timezone.timedelta(days=1))
    response = _client(world["student_a"]).get("/api/tests/")
    rows = [t for t in (response.json()["results"] if isinstance(response.json(), dict) else response.json())
            if t["title"] == "Group-only A"]
    assert len(rows) == 1
    assert rows[0]["total_questions"] == 1


@pytest.mark.django_db
def test_teacher_of_an_assigned_group_gets_access_and_an_unrelated_teacher_gets_403_not_500(world):
    """Regression: the gradebook referenced a non-existent `group_assignments` relation (HTTP 500)."""
    from apps.courses.models import Homework

    test = Test.objects.get(pk=world["ids"]["group_test"])
    helper = _user("helper-teacher@example.test", "teacher")
    helper_group = StudentGroup.objects.create(name="H-1", teacher=helper)
    Homework.objects.create(group=helper_group, test=test, title="HW", due_date=timezone.now() + timezone.timedelta(days=1))
    url = f"/api/tests/{test.id}/gradebook/"
    assert _client(helper).get(url).status_code == 200
    assert _client(helper).get(f"/api/tests/{test.id}/").json()["questions"]  # assigned teacher sees content
    assert _client(world["actors"]["other_teacher"]).get(url).status_code == 403
    assert _client(world["actors"]["other_student"]).get(url).status_code == 403


# -- mutations: nothing the victim owns may be changed by an unrelated actor ----------------------

WRITE_ENDPOINTS = [
    ("attendance mark", "post", "/api/v1/school/attendance/sessions/{session}/mark/",
     {"student_id": "{student}", "status": "absent"}),
    ("attendance mark all present", "post", "/api/v1/school/attendance/sessions/{session}/mark-all-present/", {}),
    ("attendance finalize", "post", "/api/v1/school/attendance/sessions/{session}/finalize/", {"confirm_unmarked": True}),
    ("update attempt score", "post", "/api/tests/attempts/{attempt}/update-score/", {"score": 0}),
    ("update attempt score (teacher)", "post", "/api/tests/teacher/attempts/{attempt}/update-score/", {"score": 0}),
    ("group record payment", "post", "/api/v1/courses/groups/{group}/record-payment/",
     {"student_id": "{student}", "amount": 1}),
    ("group payment reminders", "post", "/api/v1/courses/groups/{group}/send-payment-reminders/", {}),
    ("group broadcast vedomost", "post", "/api/v1/school/groups/{group}/broadcast-vedomost/", {}),
    ("studio publish", "post", "/api/v1/teacher/studio/tests/{draft}/publish/", {}),
    ("studio assign", "post", "/api/v1/teacher/studio/tests/{draft}/assign/", {"group_ids": ["{group}"]}),
    ("generate retest", "post", "/api/tests/attempts/{attempt}/generate-retest/", {}),
    ("panel question edit", "patch", "/api/v1/panel/tests/{draft}/", {"title": "pwned"}),
    ("panel status change", "post", "/api/v1/panel/tests/{draft}/status/", {"status": "published"}),
    ("homework cancel", "delete", "/api/v1/school/teacher/homeworks/{homework}/", {}),
    ("homework grade", "post", "/api/v1/school/teacher/homework-submissions/{submission}/grade/",
     {"score": 0, "max_score": 10}),
    ("homework submit as non-recipient", "post", "/api/v1/school/student/homeworks/{homework}/submit/",
     {"answers": {"text": "x"}}),
    ("group members add", "post", "/api/v1/school/groups/{group}/members/", {"add": ["{student}"]}),
    ("panel archive", "post", "/api/v1/panel/tests/{draft}/archive/", {}),
    ("panel duplicate", "post", "/api/v1/panel/tests/{draft}/duplicate/", {}),
]


def _fill(value, ids):
    if isinstance(value, str):
        return int(ids[value[1:-1]]) if value.startswith("{") and value.endswith("}") else value
    if isinstance(value, list):
        return [_fill(v, ids) for v in value]
    if isinstance(value, dict):
        return {k: _fill(v, ids) for k, v in value.items()}
    return value


def _snapshot(world):
    from apps.attendance.models import AttendanceRecord

    ids = world["ids"]
    draft = Test.objects.get(pk=ids["draft"])
    return {
        "draft": (draft.title, draft.status, draft.is_active, draft.assigned_group_id),
        "records": list(AttendanceRecord.objects.filter(session_id=ids["session"]).values_list("student_id", "status")),
        "session": AttendanceSession.objects.values_list("status", flat=True).get(pk=ids["session"]),
        "attempt": TestAttempt.objects.values_list("score", "status").get(pk=ids["attempt"]),
        "result": Result.objects.values_list("score", "percentage").get(pk=ids["result"]),
        "attempts": TestAttempt.objects.count(),
        "homework": __import__("apps.courses.models", fromlist=["Homework"]).Homework.objects.values_list(
            "status", flat=True).get(pk=ids["homework"]),
        "submissions": list(__import__("apps.courses.models", fromlist=["HomeworkSubmission"]).HomeworkSubmission.objects
                            .order_by("id").values_list("id", "status", "score")),
        "tests": Test.objects.count(),
    }


@pytest.mark.django_db
@pytest.mark.parametrize("actor", ["anonymous", "other_student", "other_teacher", "other_center_admin"])
def test_unrelated_actors_change_nothing_of_the_victim(world, actor):
    before = _snapshot(world)
    user = world["actors"][actor]
    accepted = []
    for label, method, template, body in WRITE_ENDPOINTS:
        url = template.format(**world["ids"])
        response = getattr(_client(user), method)(url, _fill(body, world["ids"]), format="json")
        if response.status_code < 300:
            accepted.append(f"{label}: {method.upper()} {url} -> {response.status_code}")
    assert accepted == []
    assert _snapshot(world) == before


@pytest.mark.django_db
def test_every_probed_url_is_a_real_api_route_not_the_spa_catch_all(world):
    """A mistyped path would 'pass' the isolation tests for the wrong reason (404 / SPA shell)."""
    from django.urls import resolve

    ids = world["ids"]
    urls = [t.format(**ids) for _, t in READ_ENDPOINTS] + [t.format(**ids) for _, _, t, _ in WRITE_ENDPOINTS]
    for url in urls:
        match = resolve(url)
        assert "core.spa" not in match.func.__module__ and "serve_spa" not in match.func.__name__, url


@pytest.mark.django_db
def test_the_owner_can_use_the_write_endpoints_the_probe_attacks(world):
    """Positive control: the probe's request shapes are accepted from a legitimate actor."""
    ids = world["ids"]
    owner = _client(world["teacher_a"])
    mark = owner.post(f"/api/v1/school/attendance/sessions/{ids['session']}/mark/",
                      {"student_id": ids["student"], "status": "late", "late_minutes": 5}, format="json")
    assert mark.status_code == 200, mark.content
    assert owner.post(f"/api/v1/school/attendance/sessions/{ids['session']}/mark-all-present/", {}, format="json").status_code == 200


@pytest.mark.django_db
def test_own_center_admin_sees_own_center_data(world):
    """Positive control for the center cabinet: Center A's admin reads Center A's records."""
    ids = world["ids"]
    admin = _client(world["owner_a"])
    for url in (
        f"/api/v1/school/groups/{ids['group']}/",
        f"/api/v1/school/groups/{ids['group']}/analytics/",
        f"/api/v1/school/teacher/homeworks/{ids['homework']}/roster/",
        f"/api/v1/school/attendance/sessions/{ids['session']}/",
    ):
        assert admin.get(url).status_code == 200, url
