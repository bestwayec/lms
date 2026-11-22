"""
Tests for Stage 3c — Teacher Workspace 3.0:
- Teacher Workspace Overview (Davomat olish, Uy vazifasi berish, Guruhlarim, Natijalar)
- Today's lessons schedule integration with AttendanceSession
- Homework creation, listing, validation, and deletion
- Review queue (pending essays) and upcoming deadlines
- Tenant scoping and role authorization guards
"""

from __future__ import annotations

from datetime import timedelta
import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.attendance.models import AttendanceRecord, AttendanceSession
from apps.courses.models import Homework, StudentGroup
from apps.courses.group_service import add_student_to_group
from apps.essays.models import EssaySubmission, EssayTopic
from apps.organizations.models import CenterBranch, LearningCenter
from apps.results.models import Result
from apps.tests.models import Test


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def teacher_a(db):
    u = User.objects.create_user(
        email="teacher_a_3c@example.com",
        password="pass",
        role="teacher",
        first_name="Teacher",
        last_name="Alpha",
    )
    return u


@pytest.fixture
def teacher_b(db):
    u = User.objects.create_user(
        email="teacher_b_3c@example.com",
        password="pass",
        role="teacher",
        first_name="Teacher",
        last_name="Beta",
    )
    return u


@pytest.fixture
def student_one(db):
    return User.objects.create_user(
        email="student_1_3c@example.com",
        password="pass",
        role="student",
        first_name="Ali",
        last_name="Valiyev",
    )


@pytest.fixture
def student_two(db):
    return User.objects.create_user(
        email="student_2_3c@example.com",
        password="pass",
        role="student",
        first_name="Zafar",
        last_name="Karimov",
    )


@pytest.fixture
def group_a(db, teacher_a, student_one, student_two):
    g = StudentGroup.objects.create(
        name="Group Alpha 3C",
        teacher=teacher_a,
    )
    add_student_to_group(group=g, student=student_one, actor=teacher_a)
    add_student_to_group(group=g, student=student_two, actor=teacher_a)
    return g


@pytest.fixture
def group_b(db, teacher_b):
    return StudentGroup.objects.create(
        name="Group Beta 3C",
        teacher=teacher_b,
    )


@pytest.mark.django_db
def test_teacher_workspace_overview_aggregations(api, teacher_a, group_a, student_one):
    """
    Teacher Workspace Overview must return the 4 primary action data streams:
    - today_lessons (integrated with AttendanceSession)
    - assignments & upcoming_deadlines
    - review_queue (pending essays)
    - attendance_today_summary
    - backward-compatible stats (groups, student_count, published_tests)
    """
    api.force_authenticate(user=teacher_a)

    # 1. Add an AttendanceSession for today
    today = timezone.localdate()
    session = AttendanceSession.objects.create(
        group=group_a,
        teacher=teacher_a,
        lesson_date=today,
        status=AttendanceSession.Status.FINALIZED,
        title="1-Dars",
    )
    AttendanceRecord.objects.create(
        session=session,
        student=student_one,
        status="present",
    )

    # 2. Add an active homework
    future_due = timezone.now() + timedelta(days=3)
    hw = Homework.objects.create(
        group=group_a,
        title="Grammar Unit 1 Homework",
        description="Solve exercises 1 to 10",
        due_date=future_due,
        created_by=teacher_a,
    )

    # 3. Add an essay pending teacher review
    topic = EssayTopic.objects.create(
        title="Modern Technology in Education",
        is_active=True,
    )
    EssaySubmission.objects.create(
        student=student_one,
        topic=topic,
        essay_text="Technology has revolutionized classroom education...",
        word_count=210,
        status=EssaySubmission.Status.PENDING_TEACHER,
    )

    resp = api.get("/api/v1/school/teacher/")
    assert resp.status_code == 200
    data = resp.json()

    # Core Action 1: Davomat olish (Today's lessons & summary)
    assert "today_lessons" in data
    assert len(data["today_lessons"]) == 1
    lesson = data["today_lessons"][0]
    assert lesson["group_id"] == group_a.id
    assert lesson["status"] == "finalized"
    assert lesson["present_count"] == 1
    assert lesson["student_count"] == 2

    assert "attendance_today_summary" in data
    assert data["attendance_today_summary"]["total_groups"] == 1
    assert data["attendance_today_summary"]["finalized_count"] == 1
    assert data["attendance_today_summary"]["draft_count"] == 0

    # Core Action 2: Uy vazifasi berish (Assignments & upcoming deadlines)
    assert "assignments" in data
    assert len(data["assignments"]) >= 1
    hw_item = [a for a in data["assignments"] if a["id"] == hw.id][0]
    assert hw_item["title"] == "Grammar Unit 1 Homework"
    assert hw_item["group_id"] == group_a.id
    assert hw_item["is_overdue"] is False

    assert "upcoming_deadlines" in data
    assert any(a["id"] == hw.id for a in data["upcoming_deadlines"])

    # Core Action 3: Guruhlarim
    assert "groups" in data
    assert len(data["groups"]) == 1
    assert data["groups"][0]["id"] == group_a.id
    assert data["student_count"] == 2

    # Core Action 4: Natijalar & Review Queue
    assert "review_queue" in data
    assert len(data["review_queue"]) == 1
    rq_item = data["review_queue"][0]
    assert rq_item["student_id"] == student_one.id
    assert rq_item["topic_title"] == "Modern Technology in Education"
    assert rq_item["word_count"] == 210
    assert data["review_queue_count"] == 1


@pytest.mark.django_db
def test_unauthorized_access_to_teacher_endpoints(api, student_one):
    """Students and unauthenticated users must be rejected from teacher endpoints."""
    # Anonymous
    resp = api.get("/api/v1/school/teacher/")
    assert resp.status_code in (401, 403)

    # Student
    api.force_authenticate(user=student_one)
    resp = api.get("/api/v1/school/teacher/")
    assert resp.status_code == 403

    resp = api.get("/api/v1/school/teacher/homeworks/")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_teacher_homework_lifecycle(api, teacher_a, teacher_b, group_a, group_b):
    """
    Verify creating, listing, and deleting homework:
    - Teacher A can create and list homework for Group A
    - Teacher A cannot create homework for Teacher B's Group B
    - Validates deadline in future
    - Teacher A can delete own homework; Teacher B cannot delete Teacher A's homework
    """
    api.force_authenticate(user=teacher_a)

    # 1. Past due date rejected
    past_due = (timezone.now() - timedelta(hours=2)).isoformat()
    resp = api.post(
        "/api/v1/school/teacher/homeworks/",
        {
            "group_id": group_a.id,
            "title": "Invalid Past Homework",
            "due_date": past_due,
        },
        format="json",
    )
    assert resp.status_code == 400
    assert "kelajakda" in resp.json()["detail"].lower()

    # 2. Creating homework for another teacher's group rejected (403)
    future_due = (timezone.now() + timedelta(days=4)).isoformat()
    resp = api.post(
        "/api/v1/school/teacher/homeworks/",
        {
            "group_id": group_b.id,
            "title": "Hacked Homework",
            "due_date": future_due,
        },
        format="json",
    )
    assert resp.status_code == 403

    # 3. Valid creation
    resp = api.post(
        "/api/v1/school/teacher/homeworks/",
        {
            "group_id": group_a.id,
            "title": "Vocabulary Unit 2 Practice",
            "due_date": future_due,
            "description": "Memorize 20 words from unit 2",
        },
        format="json",
    )
    assert resp.status_code == 201
    created_hw = resp.json()
    assert created_hw["title"] == "Vocabulary Unit 2 Practice"
    assert created_hw["group_id"] == group_a.id
    hw_id = created_hw["id"]

    # 4. Listing homeworks
    resp = api.get("/api/v1/school/teacher/homeworks/")
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert any(h["id"] == hw_id for h in results)

    # Filter by group
    resp = api.get(f"/api/v1/school/teacher/homeworks/?group_id={group_a.id}")
    assert resp.status_code == 200
    assert any(h["id"] == hw_id for h in resp.json()["results"])

    # 5. Teacher B cannot delete Teacher A's homework
    api.force_authenticate(user=teacher_b)
    del_resp = api.delete(f"/api/v1/school/teacher/homeworks/{hw_id}/")
    assert del_resp.status_code == 403

    # 6. Teacher A can delete own homework
    api.force_authenticate(user=teacher_a)
    del_resp = api.delete(f"/api/v1/school/teacher/homeworks/{hw_id}/")
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "deleted"

    # Confirm deleted
    assert not Homework.objects.filter(id=hw_id).exists()


@pytest.mark.django_db
def test_teacher_homework_with_essay_topic_integration(api, teacher_a, group_a):
    """Attaching an essay topic to homework automatically synchronizes with EssayAssignment."""
    api.force_authenticate(user=teacher_a)
    topic = EssayTopic.objects.create(title="Climate Change and Green Energy", is_active=True)

    future_due = (timezone.now() + timedelta(days=5)).isoformat()
    resp = api.post(
        "/api/v1/school/teacher/homeworks/",
        {
            "group_id": group_a.id,
            "title": "Essay Task 2 on Climate",
            "due_date": future_due,
            "essay_topic_id": topic.id,
            "description": "Write minimum 250 words",
        },
        format="json",
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["type"] == "essay"

    # Verify EssayAssignment created
    from apps.essays.models import EssayAssignment

    assert EssayAssignment.objects.filter(group=group_a, topic=topic).exists()


@pytest.mark.django_db
def test_center_admin_workspace_isolation(api, teacher_a, group_a, teacher_b, group_b):
    """
    A Learning Center admin only sees groups and sessions belonging to their center branch.
    """
    owner = User.objects.create_user(
        email="owner_3c@example.com",
        password="pass",
        role="center_admin",
    )
    center = LearningCenter.objects.create(name="Grand Academy 3C", owner=owner)
    branch = CenterBranch.objects.create(center=center, name="Main Branch 3C", branch_code="BR3C", director=owner)

    # Attach group_a to center branch
    group_a.branch = branch
    group_a.save()

    # group_b has no branch
    group_b.branch = None
    group_b.save()

    api.force_authenticate(user=owner)
    resp = api.get("/api/v1/school/teacher/")
    assert resp.status_code == 200
    data = resp.json()

    # Center admin sees group_a but NOT group_b
    group_ids = [g["id"] for g in data["groups"]]
    assert group_a.id in group_ids
    assert group_b.id not in group_ids
