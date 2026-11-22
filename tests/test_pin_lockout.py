"""A 4-digit test PIN has 10 000 values: guessing must be rate-limited per account."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.accounts.models import Profile
from apps.courses.models import Course
from apps.tests.models import Choice, Question, Test
from apps.tests.services import PIN_MAX_FAILURES_PER_TEST, PIN_MAX_FAILURES_PER_USER

User = get_user_model()
PIN = "4821"


def _user(email: str, role: str = "student"):
    user = User.objects.create_user(email=email, password="x-Pass-123!", role=role)
    Profile.objects.get_or_create(user=user)
    return user


def _api(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user)
    return client


def _pin_test(teacher, slug: str, *, code: str) -> Test:
    course = Course.objects.create(teacher=teacher, title=slug, slug=slug)
    test = Test.objects.create(
        title=f"PIN {slug}", course=course, mock_code=code, subject="uzbek",
        status=Test.Status.PUBLISHED, is_active=True, access_pin=PIN,
    )
    question = Question.objects.create(test=test, text="Q", position=1, points=1)
    for idx, letter in enumerate("AB", start=1):
        Choice.objects.create(question=question, text=letter, is_correct=letter == "A", position=idx)
    return test


@pytest.fixture(autouse=True)
def _clean_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def teacher(db):
    return _user("pin-teacher@example.test", "teacher")


@pytest.fixture
def pin_test(teacher):
    return _pin_test(teacher, "pin-a", code="PIN-A")


def start(user, test, pin):
    return _api(user).post(f"/api/tests/{test.id}/start/", {"pin": pin}, format="json")


@pytest.mark.django_db
def test_wrong_pins_lock_the_account_for_that_test_even_for_the_right_pin(pin_test):
    student = _user("guesser@example.test")
    for _ in range(PIN_MAX_FAILURES_PER_TEST):
        res = start(student, pin_test, "0000")
        assert res.status_code == 400 and res.json()["code"] == "INVALID_PIN"
    locked = start(student, pin_test, PIN)  # even the correct PIN is refused while locked
    assert locked.status_code == 429
    assert locked.json()["code"] == "PIN_LOCKED"
    assert int(locked["Retry-After"]) > 0
    assert not pin_test.attempts.filter(student=student).exists()


@pytest.mark.django_db
def test_lockout_is_per_account_not_global(pin_test):
    attacker, honest = _user("attacker@example.test"), _user("honest@example.test")
    for _ in range(PIN_MAX_FAILURES_PER_TEST + 1):
        start(attacker, pin_test, "1111")
    assert start(attacker, pin_test, PIN).status_code == 429
    assert start(honest, pin_test, PIN).status_code == 201


@pytest.mark.django_db
def test_a_correct_pin_below_the_limit_resets_the_counter(pin_test):
    student = _user("forgetful@example.test")
    for _ in range(PIN_MAX_FAILURES_PER_TEST - 1):
        assert start(student, pin_test, "9999").status_code == 400
    assert start(student, pin_test, PIN).status_code == 201
    # The per-test counter is cleared by the success, so the earlier mistakes no longer count.
    assert cache.get(f"testpin:fail:{student.id}:{pin_test.id}") is None


@pytest.mark.django_db
def test_missing_pin_is_not_counted_as_a_guess(pin_test):
    student = _user("noguess@example.test")
    for _ in range(PIN_MAX_FAILURES_PER_TEST + 2):
        res = start(student, pin_test, "")
        assert res.status_code == 400 and res.json()["code"] == "PIN_REQUIRED"
    assert start(student, pin_test, PIN).status_code == 201


@pytest.mark.django_db
def test_spreading_guesses_over_many_tests_hits_the_per_user_cap(teacher):
    student = _user("spreader@example.test")
    tests = [_pin_test(teacher, f"spread-{i}", code=f"SPR-{i}") for i in range(PIN_MAX_FAILURES_PER_USER // 2)]
    # 4 wrong guesses per test stays under the per-test limit, but not under the per-user cap.
    for test in tests:
        for _ in range(PIN_MAX_FAILURES_PER_TEST - 1):
            start(student, test, "0000")
    assert start(student, tests[0], "0000").status_code == 429
    fresh = _pin_test(teacher, "spread-fresh", code="SPR-FRESH")
    assert start(student, fresh, PIN).status_code == 429


@pytest.mark.django_db
def test_the_owner_teacher_is_never_locked_out_of_previewing_their_own_test(teacher, pin_test):
    for _ in range(PIN_MAX_FAILURES_PER_TEST + 3):
        start(teacher, pin_test, "0000")
    assert start(teacher, pin_test, PIN).status_code == 201


@pytest.mark.django_db
def test_mock_join_reports_a_wrong_pin_instead_of_returning_an_old_attempt(pin_test):
    student = _user("joiner@example.test")
    assert start(student, pin_test, PIN).status_code == 201  # now the student has an attempt
    pin_test.attempts.filter(student=student).update(status="completed")
    res = _api(student).post("/api/tests/mock/join/", {"code": "PIN-A", "pin": "0000", "auto_start": True}, format="json")
    assert res.status_code == 400, res.content
    assert "attempt_id" not in res.json()


@pytest.mark.django_db
def test_mock_join_is_locked_after_repeated_wrong_pins(pin_test):
    student = _user("joiner2@example.test")
    for _ in range(PIN_MAX_FAILURES_PER_TEST):
        _api(student).post("/api/tests/mock/join/", {"code": "PIN-A", "pin": "0000", "auto_start": True}, format="json")
    res = _api(student).post("/api/tests/mock/join/", {"code": "PIN-A", "pin": PIN, "auto_start": True}, format="json")
    assert res.status_code == 429
