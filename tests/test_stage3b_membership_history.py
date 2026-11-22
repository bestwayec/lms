"""Stage 3b — Group membership history and student search authorization tests."""

import threading
import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.attendance.models import AttendanceRecord, AttendanceSession
from apps.courses.models import Course, GroupEnrollment, GroupMembershipHistory, StudentGroup
from apps.courses.group_service import add_student_to_group, remove_student_from_group
from apps.essays.models import EssaySubmission
from apps.organizations.models import CenterBranch, LearningCenter
from apps.results.models import Result
from apps.tests.models import Test, TestAttempt


@pytest.mark.django_db
def test_authorized_teacher_can_manage_members_and_view_history():
    teacher = User.objects.create_user(email="stage3b-teacher@example.test", role="teacher", first_name="Toshmat")
    branch = CenterBranch.objects.create(name="Toshkent Filial", branch_code="TSH01", director=teacher)
    student = User.objects.create_user(
        email="stage3b-student@example.test", role="student", branch=branch, first_name="Ali", last_name="Valiyev"
    )
    group = StudentGroup.objects.create(name="Fizika 101", teacher=teacher, branch=branch)

    client = APIClient()
    client.force_authenticate(teacher)

    # 1. Search student in branch
    search_resp = client.get("/api/v1/school/students/", {"q": "Ali", "group_id": group.pk})
    assert search_resp.status_code == 200
    assert len(search_resp.data) == 1
    item = search_resp.data[0]
    assert item["id"] == student.pk
    assert item["email"] == student.email
    # Sensitive fields must not leak
    assert "has_pro" not in item
    assert "tests_count" not in item
    assert "essays_count" not in item

    # 2. Add student to group
    add_resp = client.post(f"/api/v1/school/groups/{group.pk}/members/", {"add": [student.pk]}, format="json")
    assert add_resp.status_code == 200
    assert group.students.filter(pk=student.pk).exists()

    # 3. Verify GroupMembershipHistory record
    histories = GroupMembershipHistory.objects.filter(group=group, student=student)
    assert histories.count() == 1
    hist = histories.first()
    assert hist.action == GroupMembershipHistory.Action.JOINED
    assert hist.actor == teacher
    assert hist.removed_at is None
    assert hist.reason == "manual_add"

    # 4. Verify History API endpoint
    hist_resp = client.get(f"/api/v1/school/groups/{group.pk}/history/")
    assert hist_resp.status_code == 200
    assert len(hist_resp.data) == 1
    assert hist_resp.data[0]["student_id"] == student.pk
    assert hist_resp.data[0]["action"] == "joined"
    assert hist_resp.data[0]["actor_id"] == teacher.pk


@pytest.mark.django_db
def test_unauthorized_teacher_cannot_access_or_modify_other_group():
    teacher_a = User.objects.create_user(email="teacher-a@example.test", role="teacher")
    teacher_b = User.objects.create_user(email="teacher-b@example.test", role="teacher")
    student = User.objects.create_user(email="student-a@example.test", role="student")
    group_a = StudentGroup.objects.create(name="Group A", teacher=teacher_a)
    group_a.students.add(student)

    client = APIClient()
    client.force_authenticate(teacher_b)

    # Accessing other teacher's group returns 404
    assert client.get(f"/api/v1/school/groups/{group_a.pk}/").status_code == 404
    assert client.post(f"/api/v1/school/groups/{group_a.pk}/members/", {"remove": [student.pk]}, format="json").status_code == 404
    assert client.get(f"/api/v1/school/groups/{group_a.pk}/history/").status_code == 404
    assert client.get(f"/api/v1/school/groups/{group_a.pk}/members/{student.pk}/results/").status_code == 404


@pytest.mark.django_db
def test_cross_center_student_search_and_enrollment_isolation():
    owner_1 = User.objects.create_user(email="owner1@example.test", role="admin")
    center_1 = LearningCenter.objects.create(name="Center 1", owner=owner_1)
    branch_1 = CenterBranch.objects.create(name="Branch 1", center=center_1, branch_code="C1B1")
    teacher_1 = User.objects.create_user(email="teacher1@example.test", role="teacher", branch=branch_1, learning_center=center_1)
    student_1 = User.objects.create_user(email="student1@example.test", role="student", branch=branch_1, learning_center=center_1, first_name="Kamron")
    group_1 = StudentGroup.objects.create(name="Group 1", teacher=teacher_1, branch=branch_1)

    owner_2 = User.objects.create_user(email="owner2@example.test", role="admin")
    center_2 = LearningCenter.objects.create(name="Center 2", owner=owner_2)
    branch_2 = CenterBranch.objects.create(name="Branch 2", center=center_2, branch_code="C2B2")
    teacher_2 = User.objects.create_user(email="teacher2@example.test", role="teacher", branch=branch_2, learning_center=center_2)
    student_2 = User.objects.create_user(email="student2@example.test", role="student", branch=branch_2, learning_center=center_2, first_name="Kamron")
    StudentGroup.objects.create(name="Group 2", teacher=teacher_2, branch=branch_2)

    client = APIClient()
    client.force_authenticate(teacher_1)

    # Search: Teacher 1 searching for 'Kamron' must only see student_1, NEVER student_2
    search_resp = client.get("/api/v1/school/students/", {"q": "Kamron", "group_id": group_1.pk})
    assert search_resp.status_code == 200
    returned_ids = [row["id"] for row in search_resp.data]
    assert student_1.pk in returned_ids
    assert student_2.pk not in returned_ids

    # Direct Add: Teacher 1 attempting to add student_2 (from Center 2) by ID must be REJECTED (400)
    add_resp = client.post(f"/api/v1/school/groups/{group_1.pk}/members/", {"add": [student_2.pk]}, format="json")
    assert add_resp.status_code == 400
    assert not group_1.students.filter(pk=student_2.pk).exists()

    # Invite Code: Student 2 attempting to join Group 1 via invite code must be REJECTED (400)
    client.force_authenticate(student_2)
    join_resp = client.post("/api/v1/school/groups/join/", {"invite_code": group_1.invite_code}, format="json")
    assert join_resp.status_code == 400
    assert "boshqa o'quv markaziga" in join_resp.data.get("error", "")
    assert not group_1.students.filter(pk=student_2.pk).exists()


@pytest.mark.django_db
def test_independent_tutor_workflow():
    tutor = User.objects.create_user(email="tutor@example.test", role="teacher")
    group = StudentGroup.objects.create(name="Private English", teacher=tutor)
    unaffiliated_student = User.objects.create_user(email="unaffiliated@example.test", role="student", first_name="Bobur")

    client = APIClient()
    client.force_authenticate(tutor)

    # 1. Tutor searching before student joins returns empty (avoid platform student harvesting)
    search_resp = client.get("/api/v1/school/students/", {"q": "Bobur", "group_id": group.pk})
    assert search_resp.status_code == 200
    assert search_resp.data == []

    # 2. Direct add by ID is rejected because student is not yet eligible/connected
    add_resp = client.post(f"/api/v1/school/groups/{group.pk}/members/", {"add": [unaffiliated_student.pk]}, format="json")
    assert add_resp.status_code == 400

    # 3. Student joins via invite token (authorized workflow)
    client.force_authenticate(unaffiliated_student)
    token_url = f"/api/v1/school/groups/join/{group.invite_token}/"
    join_resp = client.post(token_url, format="json")
    assert join_resp.status_code == 200
    assert join_resp.data.get("status") == "SUCCESS"
    assert group.students.filter(pk=unaffiliated_student.pk).exists()

    # 4. Now tutor can search and see them in subsequent group management
    client.force_authenticate(tutor)
    search_after = client.get("/api/v1/school/students/", {"q": "Bobur", "group_id": group.pk})
    assert search_after.status_code == 200
    assert len(search_after.data) == 1
    assert search_after.data[0]["id"] == unaffiliated_student.pk


@pytest.mark.django_db
def test_repeated_enrollment_is_idempotent():
    teacher = User.objects.create_user(email="idempotent-teacher@example.test", role="teacher")
    student = User.objects.create_user(email="idempotent-student@example.test", role="student")
    group = StudentGroup.objects.create(name="Math", teacher=teacher)

    client = APIClient()
    client.force_authenticate(teacher)

    # Add once via service
    added, hist1 = add_student_to_group(group, student, actor=teacher, reason="first_add")
    assert added is True
    assert group.students.count() == 1

    # Add again via service (idempotent)
    added_again, hist2 = add_student_to_group(group, student, actor=teacher, reason="second_add")
    assert added_again is False
    assert group.students.count() == 1
    assert hist2.pk == hist1.pk

    # Join again via token view returns ALREADY_MEMBER
    client.force_authenticate(student)
    join_resp = client.post(f"/api/v1/school/groups/join/{group.invite_token}/", format="json")
    assert join_resp.status_code == 200
    assert join_resp.data.get("status") == "ALREADY_MEMBER"
    assert group.students.count() == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_enrollment_thread_safety():
    from django.db import connection

    if connection.vendor != "postgresql":
        pytest.skip("Row-level lock concurrency test requires PostgreSQL")

    teacher = User.objects.create_user(email="concurrent-teacher@example.test", role="teacher")
    student = User.objects.create_user(email="concurrent-student@example.test", role="student")
    group = StudentGroup.objects.create(name="Concurrency Group", teacher=teacher)

    results = []
    errors = []

    def worker():
        try:
            success, hist = add_student_to_group(group, student, actor=teacher, reason="concurrent")
            results.append(success)
        except Exception as exc:
            errors.append(exc)

    t1 = threading.Thread(target=worker)
    t2 = threading.Thread(target=worker)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert errors == []
    assert len(results) == 2
    # Exactly one thread performed the addition; the other saw the existing membership idempotently
    assert sorted(results) == [False, True]
    assert group.students.filter(pk=student.pk).count() == 1
    assert GroupMembershipHistory.objects.filter(group=group, student=student, removed_at__isnull=True).count() == 1


@pytest.mark.django_db
def test_membership_removal_and_historical_data_preservation():
    teacher = User.objects.create_user(email="history-teacher@example.test", role="teacher")
    student = User.objects.create_user(email="history-student@example.test", role="student")
    group = StudentGroup.objects.create(name="History Preservation Group", teacher=teacher)
    group.students.add(student)
    GroupMembershipHistory.objects.create(group=group, student=student, action=GroupMembershipHistory.Action.JOINED, actor=teacher)

    # 1. Historical artifacts created while in group
    course = Course.objects.create(title="History Course", slug="history-course", teacher=teacher)
    test = Test.objects.create(title="Group Exam", course=course, assigned_group=group)
    attempt = TestAttempt.objects.create(test=test, student=student, status=TestAttempt.Status.COMPLETED)
    result = Result.objects.create(
        attempt=attempt, student=student, test=test, course=course,
        total_questions=10, correct_answers=9, wrong_answers=1, score=9.0, max_score=10.0, percentage=90.0,
        grading_status="graded", is_passed=True,
    )
    essay = EssaySubmission.objects.create(student=student, essay_text="Historical essay", status=EssaySubmission.Status.GRADED)
    session = AttendanceSession.objects.create(group=group, teacher=teacher, lesson_date="2026-11-20")
    record = AttendanceRecord.objects.create(session=session, student=student, status=AttendanceRecord.Status.PRESENT)

    # 2. Teacher removes student from group via API
    client = APIClient()
    client.force_authenticate(teacher)
    remove_resp = client.post(f"/api/v1/school/groups/{group.pk}/members/", {"remove": [student.pk]}, format="json")
    assert remove_resp.status_code == 200

    # 3. Student is no longer in group
    assert not group.students.filter(pk=student.pk).exists()

    # 4. User account remains active and intact
    assert User.objects.filter(pk=student.pk).exists()

    # 5. ALL historical records are 100% PRESERVED
    assert TestAttempt.objects.filter(pk=attempt.pk).exists()
    assert Result.objects.filter(pk=result.pk).exists()
    assert EssaySubmission.objects.filter(pk=essay.pk).exists()
    assert AttendanceRecord.objects.filter(pk=record.pk).exists()
    assert AttendanceSession.objects.filter(pk=session.pk).exists()

    # 6. GroupMembershipHistory properly audited
    history_entries = GroupMembershipHistory.objects.filter(group=group, student=student).order_by("created_at")
    assert history_entries.count() == 2
    joined_entry = history_entries.first()
    assert joined_entry.action == "joined"
    assert joined_entry.removed_at is not None  # Closed

    removed_entry = history_entries.last()
    assert removed_entry.action == "removed"
    assert removed_entry.actor == teacher
    assert removed_entry.reason == "manual_remove"


@pytest.mark.django_db
def test_rejoining_group_records_rejoined_action():
    teacher = User.objects.create_user(email="rejoin-teacher@example.test", role="teacher")
    student = User.objects.create_user(email="rejoin-student@example.test", role="student")
    group = StudentGroup.objects.create(name="Rejoin Group", teacher=teacher)

    # Join
    add_student_to_group(group, student, actor=teacher)
    # Remove
    remove_student_from_group(group, student, actor=teacher)
    # Rejoin
    added, hist = add_student_to_group(group, student, actor=teacher, reason="second_chance")

    assert added is True
    assert hist.action == GroupMembershipHistory.Action.REJOINED
    assert hist.reason == "second_chance"
    assert hist.removed_at is None
    assert group.students.filter(pk=student.pk).exists()


@pytest.mark.django_db
def test_invalid_and_nonexistent_ids():
    teacher = User.objects.create_user(email="validation-teacher@example.test", role="teacher")
    student = User.objects.create_user(email="validation-student@example.test", role="student")
    group = StudentGroup.objects.create(name="Validation Group", teacher=teacher)
    group.students.add(student)

    client = APIClient()
    client.force_authenticate(teacher)
    url = f"/api/v1/school/groups/{group.pk}/members/"

    # Negative integer ID
    assert client.post(url, {"add": [-1]}, format="json").status_code == 400
    # String ID
    assert client.post(url, {"add": ["invalid"]}, format="json").status_code == 400
    # Non-list
    assert client.post(url, {"add": 123}, format="json").status_code == 400
    # Add and remove same student simultaneously
    assert client.post(url, {"add": [student.pk], "remove": [student.pk]}, format="json").status_code == 400
    # Removing non-member
    assert client.post(url, {"remove": [999999]}, format="json").status_code == 400

    # Unauthenticated
    unauth_client = APIClient()
    assert unauth_client.get(f"/api/v1/school/groups/{group.pk}/members/").status_code in (401, 403, 405)

    # Student cannot call teacher student search
    client.force_authenticate(student)
    assert client.get("/api/v1/school/students/", {"q": "val"}).status_code == 403
