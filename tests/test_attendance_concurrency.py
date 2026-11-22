"""Attendance: stale saves (409), finalized registers, atomic batches and a real PostgreSQL race."""

from __future__ import annotations

import threading

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Profile
from apps.attendance import services
from apps.attendance.models import AttendanceAuditLog, AttendanceRecord, AttendanceSession
from apps.courses.models import StudentGroup

User = get_user_model()


def _user(email: str, role: str = "student", **extra):
    user = User.objects.create_user(email=email, password="x-Pass-123!", role=role, **extra)
    Profile.objects.get_or_create(user=user)
    return user


def _client(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.fixture
def room(db):
    teacher = _user("att-teacher@example.test", "teacher")
    group = StudentGroup.objects.create(name="G-1", teacher=teacher)
    students = [_user(f"att-s{i}@example.test", first_name=f"S{i}") for i in range(1, 4)]
    group.students.add(*students)
    session = services.create_session(group=group, teacher=teacher, lesson_date=timezone.localdate(), actor=teacher)[0]
    return {"teacher": teacher, "group": group, "students": students, "session": session}


def url(room, action=""):
    return f"/api/v1/school/attendance/sessions/{room['session'].id}/{action}"


def mark(room, student, status, **body):
    return _client(room["teacher"]).post(url(room, "mark/"), {"student_id": student.id, "status": status, **body}, format="json")


def sheet(room):
    return _client(room["teacher"]).get(url(room)).json()


# -- revision ----------------------------------------------------------------------------------


@pytest.mark.django_db
def test_sheet_carries_a_revision_that_tracks_every_visible_change(room):
    first = sheet(room)["revision"]
    assert first and first == sheet(room)["revision"]  # stable while nothing changes
    s1 = room["students"][0]
    after_present = mark(room, s1, "present").json()["revision"]
    assert after_present != first
    after_late = mark(room, s1, "late", late_minutes=7).json()["revision"]
    assert after_late != after_present
    after_note = mark(room, s1, "late", late_minutes=7, note="bus").json()["revision"]
    assert after_note != after_late
    assert sheet(room)["revision"] == after_note


@pytest.mark.django_db
def test_identical_content_has_an_identical_revision(room):
    s1 = room["students"][0]
    a = mark(room, s1, "present").json()["revision"]
    mark(room, s1, "absent")
    b = mark(room, s1, "present").json()["revision"]
    assert a == b


# -- stale saves ---------------------------------------------------------------------------------


@pytest.mark.django_db
def test_stale_save_is_rejected_with_409_and_the_fresh_sheet_and_changes_nothing(room):
    s1, s2, s3 = room["students"]
    stale = sheet(room)["revision"]  # teacher A opens the sheet
    assert mark(room, s1, "absent").status_code == 200  # teacher B changes it meanwhile

    response = _client(room["teacher"]).post(
        url(room, "mark/"),
        {"revision": stale, "marks": [{"student_id": s2.id, "status": "present"}, {"student_id": s3.id, "status": "late"}]},
        format="json",
    )
    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "ATTENDANCE_CHANGED"
    assert body["revision"] != stale
    assert {row["student_id"]: row["status"] for row in body["roster"]}[s1.id] == "absent"  # fresh sheet returned
    # nothing from the stale batch was applied
    assert not AttendanceRecord.objects.filter(session=room["session"], student__in=[s2, s3]).exists()

    # the client re-submits against the fresh revision and succeeds
    retry = _client(room["teacher"]).post(
        url(room, "mark/"),
        {"revision": body["revision"], "marks": [{"student_id": s2.id, "status": "present"}]},
        format="json",
    )
    assert retry.status_code == 200
    assert AttendanceRecord.objects.filter(session=room["session"], student=s2, status="present").exists()


@pytest.mark.django_db
def test_if_match_header_is_honoured_and_requests_without_a_revision_still_work(room):
    s1, s2, _ = room["students"]
    stale = sheet(room)["revision"]
    mark(room, s1, "present")
    response = _client(room["teacher"]).post(
        url(room, "mark/"), {"student_id": s2.id, "status": "present"}, format="json", HTTP_IF_MATCH=f'"{stale}"'
    )
    assert response.status_code == 409 and response.json()["code"] == "ATTENDANCE_CHANGED"
    # legacy clients that send no revision are unaffected (backward compatible)
    assert mark(room, s2, "present").status_code == 200


@pytest.mark.django_db
def test_mark_all_present_and_finalize_also_reject_stale_sheets(room):
    s1, _, _ = room["students"]
    stale = sheet(room)["revision"]
    mark(room, s1, "absent")
    all_present = _client(room["teacher"]).post(url(room, "mark-all-present/"), {"revision": stale}, format="json")
    assert all_present.status_code == 409 and all_present.json()["code"] == "ATTENDANCE_CHANGED"
    assert AttendanceRecord.objects.filter(session=room["session"]).count() == 1  # nobody was silently marked present

    finalize = _client(room["teacher"]).post(url(room, "finalize/"), {"revision": stale, "mark_unmarked_as_absent": True}, format="json")
    assert finalize.status_code == 409 and finalize.json()["code"] == "ATTENDANCE_CHANGED"
    room["session"].refresh_from_db()
    assert room["session"].status == AttendanceSession.Status.DRAFT


@pytest.mark.django_db
def test_a_failing_batch_applies_nothing(room):
    s1, s2, _ = room["students"]
    response = _client(room["teacher"]).post(
        url(room, "mark/"),
        {"marks": [{"student_id": s1.id, "status": "present"}, {"student_id": s2.id, "status": "not-a-status"}]},
        format="json",
    )
    assert response.status_code == 400
    assert not AttendanceRecord.objects.filter(session=room["session"]).exists()


# -- finalized registers ---------------------------------------------------------------------------


def _finalize(room):
    for student in room["students"]:
        assert mark(room, student, "present").status_code == 200
    done = _client(room["teacher"]).post(url(room, "finalize/"), {}, format="json")
    assert done.status_code == 200, done.content
    return sheet(room)["revision"]


@pytest.mark.django_db
def test_a_finalized_register_is_not_changed_by_an_ordinary_save(room):
    _finalize(room)
    s1 = room["students"][0]
    for response in (
        mark(room, s1, "absent"),
        _client(room["teacher"]).post(url(room, "mark-all-present/"), {}, format="json"),
        _client(room["teacher"]).post("/api/v1/school/attendance/quick-mark/",
                                      {"group_id": room["group"].id, "student_id": s1.id, "status": "absent"}, format="json"),
    ):
        assert response.status_code == 409
        assert response.json()["code"] == "ATTENDANCE_FINALIZED"
    assert AttendanceRecord.objects.get(session=room["session"], student=s1).status == "present"


@pytest.mark.django_db
def test_a_correction_needs_an_explicit_flag_and_a_reason_and_is_audited(room):
    _finalize(room)
    s1 = room["students"][0]
    no_reason = mark(room, s1, "excused", correction=True)
    assert no_reason.status_code == 409 and no_reason.json()["code"] == "ATTENDANCE_FINALIZED"

    ok = mark(room, s1, "excused", correction=True, reason="Doctor's note received")
    assert ok.status_code == 200, ok.content
    assert AttendanceRecord.objects.get(session=room["session"], student=s1).status == "excused"
    log = AttendanceAuditLog.objects.filter(session=room["session"], student=s1, new_value="excused").latest("id")
    assert log.old_value == "present" and log.reason == "Doctor's note received" and log.actor == room["teacher"]
    room["session"].refresh_from_db()
    assert room["session"].status == AttendanceSession.Status.FINALIZED  # a correction does not reopen the register


@pytest.mark.django_db
def test_a_correction_still_respects_the_revision(room):
    revision = _finalize(room)
    s1, s2, _ = room["students"]
    assert mark(room, s1, "late", correction=True, reason="late bus", late_minutes=5).status_code == 200
    stale = mark(room, s2, "absent", correction=True, reason="x", revision=revision)
    assert stale.status_code == 409 and stale.json()["code"] == "ATTENDANCE_CHANGED"


@pytest.mark.django_db
def test_a_cancelled_register_and_foreign_teachers_stay_closed(room):
    other = _user("att-other@example.test", "teacher")
    assert _client(other).post(url(room, "mark/"), {"student_id": room["students"][0].id, "status": "present"}, format="json").status_code == 403
    AttendanceSession.objects.filter(pk=room["session"].pk).update(status=AttendanceSession.Status.CANCELLED)
    assert mark(room, room["students"][0], "present").status_code == 400


# -- a real race (PostgreSQL row locks) --------------------------------------------------------------


class AttendanceRaceTests(TransactionTestCase):
    """Two teachers save against the same revision at the same instant: exactly one wins."""

    def test_exactly_one_of_two_concurrent_saves_with_the_same_revision_wins(self):
        if connection.vendor != "postgresql":
            self.skipTest("row-lock race needs PostgreSQL")
        teacher = _user("race-teacher@example.test", "teacher")
        group = StudentGroup.objects.create(name="Race", teacher=teacher)
        students = [_user(f"race-s{i}@example.test") for i in range(2)]
        group.students.add(*students)
        session = services.create_session(group=group, teacher=teacher, lesson_date=timezone.localdate(), actor=teacher)[0]
        revision = services.revision(session)

        barrier = threading.Barrier(2)
        outcomes: list[str] = []
        lock = threading.Lock()

        def save(student, status):
            try:
                barrier.wait(timeout=10)
                services.mark_many(
                    AttendanceSession.objects.get(pk=session.pk),
                    [{"student_id": student.pk, "status": status}],
                    actor=teacher,
                    expected_revision=revision,
                )
                result = "ok"
            except services.StaleAttendanceError:
                result = "stale"
            finally:
                connection.close()
            with lock:
                outcomes.append(result)

        threads = [threading.Thread(target=save, args=(students[0], "present")),
                   threading.Thread(target=save, args=(students[1], "absent"))]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        assert sorted(outcomes) == ["ok", "stale"], outcomes
        assert AttendanceRecord.objects.filter(session=session).count() == 1
