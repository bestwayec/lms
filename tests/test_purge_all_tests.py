from decimal import Decimal
import io
import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.courses.models import Course
from apps.groups.models import GroupEnrollment, StudentGroup
from apps.payments.models import PaymentReceipt, SubscriptionPlan, UserSubscription
from apps.results.models import Result
from apps.tests.models import Choice, Question, Test, TestAttempt

User = get_user_model()


@pytest.mark.django_db
def test_purge_all_tests_without_confirm_fails():
    out = io.StringIO()
    err = io.StringIO()
    with pytest.raises((CommandError, SystemExit)):
        call_command("purge_all_tests", stdout=out, stderr=err)


@pytest.mark.django_db
def test_purge_all_tests_with_confirm_preserves_users_and_groups():
    user = User.objects.create_user(
        email="teacher_preserve@example.com",
        password="Password123!",
        first_name="PreservedTeacher",
        role="teacher",
    )
    student = User.objects.create_user(
        email="student_preserve@example.com",
        password="Password123!",
        first_name="PreservedStudent",
        role="student",
    )

    group = StudentGroup.objects.create(name="Biology Group 1", teacher=user)
    GroupEnrollment.objects.create(group=group, student=student)

    plan, _ = SubscriptionPlan.objects.get_or_create(
        plan_type=SubscriptionPlan.PlanType.PRO,
        defaults={"name": "Pro Plan", "price_monthly": Decimal("60000")},
    )
    sub = UserSubscription.objects.create(user=student, plan=plan)
    receipt = PaymentReceipt.objects.create(
        user=student,
        amount=Decimal("60000"),
        plan="pro",
    )

    course = Course.objects.create(teacher=user, title="Biology Course", slug="biology-course")
    test_obj = Test.objects.create(course=course, title="Biology 101", subject="biology")
    q = Question.objects.create(test=test_obj, text="Mitochondria function?")
    Choice.objects.create(question=q, text="Powerhouse of the cell", is_correct=True)

    attempt = TestAttempt.objects.create(test=test_obj, student=student)
    Result.objects.create(
        test=test_obj,
        course=course,
        student=student,
        attempt=attempt,
        total_questions=1,
        correct_answers=1,
        wrong_answers=0,
        unanswered=0,
        score=Decimal("100.00"),
        max_score=Decimal("100.00"),
        percentage=Decimal("100.00"),
        is_passed=True,
    )

    # Sanity check
    assert Test.objects.count() == 1
    assert Question.objects.count() == 1
    assert Choice.objects.count() == 1
    assert TestAttempt.objects.count() == 1
    assert Result.objects.count() == 1
    assert StudentGroup.objects.count() == 1
    assert GroupEnrollment.objects.count() == 1

    out = io.StringIO()
    call_command("purge_all_tests", "--confirm", stdout=out)
    output = out.getvalue()

    assert "Xavfsiz tozalash muvaffaqiyatli yakunlandi" in output
    assert "Barcha Foydalanuvchilar, Guruhlar, Obunalar va To'lovlar 100% saqlab qolindi!" in output

    # Check purged
    assert Test.objects.count() == 0
    assert Question.objects.count() == 0
    assert Choice.objects.count() == 0
    assert TestAttempt.objects.count() == 0
    assert Result.objects.count() == 0

    # Check preserved
    assert User.objects.filter(email="teacher_preserve@example.com").exists()
    assert User.objects.filter(email="student_preserve@example.com").exists()
    assert StudentGroup.objects.filter(id=group.id).exists()
    assert GroupEnrollment.objects.filter(group=group, student=student).exists()
    assert UserSubscription.objects.filter(id=sub.id).exists()
    assert PaymentReceipt.objects.filter(id=receipt.id).exists()
