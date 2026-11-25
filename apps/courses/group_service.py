"""
Ustozlar va Repetitorlar Kabineti — Guruh Tahlili, Monitoring va Excel/PDF Eksport Xizmati.
"""

from __future__ import annotations

import io
import logging
from datetime import datetime
from typing import Any

from django.db import transaction
from django.db.models import Avg, Count, Max, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce

from apps.accounts.models import User
from apps.courses.models import StudentGroup
from apps.essays.models import EssaySubmission
from apps.results.models import Result
from apps.tests.bmb_grading import calculate_bmb_grade

logger = logging.getLogger(__name__)


def _possible_pro_ids(student_ids: list[int]) -> set[int]:
    """Students who *could* hold a paid tier: an active override, sponsorship or an
    unexpired subscription row. A superset; callers confirm with has_pro_access."""
    from django.db.models import Q
    from django.utils import timezone

    from apps.payments.models import SubscriptionOverride, TeacherSponsorship, UserSubscription

    if not student_ids:
        return set()
    now = timezone.now()
    live = Q(expires_at__isnull=True) | Q(expires_at__gt=now)
    subs = UserSubscription.objects.filter(user_id__in=student_ids).filter(live).order_by().values_list("user_id", flat=True)
    overrides = SubscriptionOverride.objects.filter(user_id__in=student_ids, is_active=True).order_by().values_list(
        "user_id", flat=True
    )
    sponsored = (
        TeacherSponsorship.objects.filter(student_id__in=student_ids, is_active=True, approved_at__isnull=False)
        .filter(live)
        .order_by()
        .values_list("student_id", flat=True)
    )
    return set(subs.union(overrides, sponsored))  # one query


def get_group_full_analytics(group: StudentGroup) -> dict[str, Any]:
    """
    Guruh bo'yicha to'liq jonli monitoring:
      - Har bir o'quvchining test va esse statistikasi
      - Rasmiy BMB darajalari (A+, A, B+, B, C+, C, Fail)
      - Guruh reytingi va taqsimoti
    """
    # Hammasi DB darajasida agregatsiya qilinadi (bo'yicha 4 ta toza so'rov):
    # o'quvchilar (+ oxirgi natija subquery), test agregati, esse agregati, to'lovlar.
    latest_result = Result.objects.filter(student=OuterRef("pk")).order_by(
        "-calculated_at"
    )
    students = list(
        group.students.filter(is_active=True)
        .annotate(
            latest_score=Subquery(latest_result.values("score")[:1]),
            latest_max_score=Subquery(latest_result.values("max_score")[:1]),
            latest_percentage=Subquery(latest_result.values("percentage")[:1]),
        )
        .order_by("first_name", "last_name")
    )
    student_ids = [s.id for s in students]
    if not student_ids:
        empty_bmb = {"A+": 0, "A": 0, "B+": 0, "B": 0, "C+": 0, "C": 0, "Fail": 0}
        return {
            "group_id": group.id,
            "group_name": group.name,
            "invite_code": group.invite_code or f"GR-{group.id}",
            "teacher_name": group.teacher.get_full_name() or group.teacher.email,
            "total_students": 0,
            "group_avg_percentage": 0.0,
            "group_bmb_grade": "—",
            "bmb_distribution": empty_bmb,
            "summary": {
                "total_tests_taken": 0,
                "total_essays_submitted": 0,
                "average_test_score": 0.0,
                "average_test_percentage": 0.0,
                "average_essay_score": 0.0,
                "bmb_distribution": empty_bmb,
            },
            "students": [],
        }

    # Test natijalari: o'quvchi bo'yicha son, o'rtacha foiz, oxirgi sana
    result_stats: dict[int, dict[str, Any]] = {
        row["student_id"]: row
        for row in Result.objects.filter(student_id__in=student_ids)
        .order_by()
        .values("student_id")
        .annotate(
            tests=Count("id"),
            avg_pct=Avg("percentage"),
            last_at=Max("calculated_at"),
        )
    }

    # Esse natijalari: qoralamalar hisobga olinmaydi; ball = final_score yoki total_score
    essay_stats: dict[int, dict[str, Any]] = {
        row["student_id"]: row
        for row in EssaySubmission.objects.filter(student_id__in=student_ids)
        .exclude(status=EssaySubmission.Status.DRAFT)
        .order_by()
        .values("student_id")
        .annotate(
            essays=Count("id"),
            last_at=Max("updated_at"),
            avg_score=Avg(
                Coalesce("final_score", "total_score"),
                filter=Q(total_score__isnull=False),
            ),
        )
    }

    # Kurs to'lovlari (Tuition Billing): har bir o'quvchining eng so'nggi to'lovi
    from apps.accounts.models import Profile
    from apps.tuition.models import StudentTuition

    profile_streaks: dict[int, int] = {
        p.user_id: p.current_streak
        for p in Profile.objects.filter(user_id__in=student_ids).only("user_id", "current_streak")
    }

    tuition_status: dict[int, str] = {}
    for sid, tuit_status in (
        StudentTuition.objects.filter(group=group, student_id__in=student_ids)
        .order_by("-due_date")
        .values_list("student_id", "status")
    ):
        tuition_status.setdefault(sid, tuit_status)

    roster = []
    bmb_counts = {"A+": 0, "A": 0, "B+": 0, "B": 0, "C+": 0, "C": 0, "Fail": 0}
    all_pcts: list[float] = []

    pro_candidates = _possible_pro_ids(student_ids)

    for s in students:
        r_stat = result_stats.get(s.id)
        e_stat = essay_stats.get(s.id)

        tests_count = r_stat["tests"] if r_stat else 0
        avg_test_pct = (
            round(float(r_stat["avg_pct"]), 1) if r_stat and r_stat["avg_pct"] is not None else 0.0
        )
        if tests_count > 0:
            all_pcts.append(avg_test_pct)

        has_latest = s.latest_score is not None
        latest_score_str = (
            f"{s.latest_score:.2f}/{s.latest_max_score:.2f}" if has_latest else "—"
        )
        latest_pct = float(s.latest_percentage) if s.latest_percentage is not None else 0.0

        # BMB darajasi
        bmb_info = calculate_bmb_grade(avg_test_pct if tests_count > 0 else 0.0)
        grade = bmb_info["grade"]
        if tests_count > 0 and grade in bmb_counts:
            bmb_counts[grade] += 1

        # Esse ballari
        essays_count = e_stat["essays"] if e_stat else 0
        avg_essay_score = (
            round(float(e_stat["avg_score"]), 1)
            if e_stat and e_stat["avg_score"] is not None
            else 0.0
        )

        dates = []
        if r_stat and r_stat["last_at"]:
            dates.append(r_stat["last_at"])
        if e_stat and e_stat["last_at"]:
            dates.append(e_stat["last_at"])
        last_active = max(dates).strftime("%d.%m.%Y %H:%M") if dates else None
        s_tuition = tuition_status.get(s.id)

        # Exact entitlement check only for the few who could be PRO (constant queries otherwise).
        has_pro_real = s.id in pro_candidates and bool(getattr(s, "has_pro_access", False))
        roster.append(
            {
                "student_id": s.id,
                "student_name": s.get_full_name() or s.email,
                "full_name": s.get_full_name() or s.email,
                "email": s.email,
                "streak": profile_streaks.get(s.id, 0),
                "streak_days": profile_streaks.get(s.id, 0),
                "has_pro": has_pro_real,
                "pro_status_label": "⭐ PRO (Faol)" if has_pro_real else "Guruh a'zosi (Classroom)",
                "tests_count": tests_count,
                "tests_taken": tests_count,
                "avg_test_percentage": avg_test_pct,
                "avg_test_pct": avg_test_pct,
                "latest_test_score": latest_score_str,
                "latest_test_pct": latest_pct,
                "latest_test_grade": grade if tests_count > 0 else "—",
                "essays_count": essays_count,
                "essays_written": essays_count,
                "avg_essay_score": avg_essay_score,
                "bmb_grade": grade if tests_count > 0 else "—",
                "bmb_title": bmb_info["title"]
                if tests_count > 0
                else "Test topshirmagan",
                "badge_class": bmb_info["badge_class"] if tests_count > 0 else "badge",
                "tuition_status": s_tuition or "pending",
                "tuition_label": (
                    "To'langan"
                    if s_tuition == "paid"
                    else "Muddati o'tgan" if s_tuition == "overdue" else "Kutilmoqda"
                ),
                "last_active": last_active or "Faollik yo'q",
            }
        )

    # Sort roster by avg_test_pct descending
    roster.sort(key=lambda x: x["avg_test_pct"], reverse=True)
    for idx, item in enumerate(roster, start=1):
        item["rank"] = idx

    group_avg_pct = round(sum(all_pcts) / len(all_pcts), 1) if all_pcts else 0.0
    group_bmb = calculate_bmb_grade(group_avg_pct)["grade"] if all_pcts else "—"

    return {
        "group_id": group.id,
        "group_name": group.name,
        "invite_code": group.invite_code or f"GR-{group.id}",
        "teacher_name": group.teacher.get_full_name() or group.teacher.email,
        "total_students": len(students),
        "group_avg_percentage": group_avg_pct,
        "group_bmb_grade": group_bmb,
        "bmb_distribution": bmb_counts,
        "summary": {
            "total_tests_taken": sum(r["tests_taken"] for r in roster),
            "total_essays_submitted": sum(r["essays_written"] for r in roster),
            "average_test_score": group_avg_pct,
            "average_test_percentage": group_avg_pct,
            "average_essay_score": round(
                sum(r["avg_essay_score"] for r in roster) / len(roster), 1
            )
            if roster
            else 0.0,
            "bmb_distribution": bmb_counts,
        },
        "students": roster,
    }


get_group_analytics = get_group_full_analytics


def _invalidate_tma_cache_on_commit() -> None:
    try:
        from apps.telegram_app.views import invalidate_tma_tests_cache

        transaction.on_commit(invalidate_tma_tests_cache)
    except Exception:
        pass


def find_group_by_token_or_code(token_or_code: str) -> StudentGroup | None:
    """Finds a StudentGroup by invite_token or invite_code."""
    if not token_or_code:
        return None
    raw = token_or_code.strip()
    clean_code = raw.removeprefix("#").upper()
    return (
        StudentGroup.objects.filter(invite_token=raw).first()
        or StudentGroup.objects.filter(invite_code__iexact=clean_code).first()
        or StudentGroup.objects.filter(invite_code__iexact=f"#{clean_code}").first()
    )


def add_student_to_group(
    group: StudentGroup,
    student: User,
    actor: User | None = None,
    reason: str = "",
    metadata: dict[str, Any] | None = None,
) -> tuple[bool, Any]:
    """
    O'quvchini guruhga qo'shadi, a'zolik tarixini yozadi va kross-markaz xavfsizligini tekshiradi.

    - Atomik tranzaksiya va guruh qatorini qulflash (select_for_update) orqali
      konkurrent qo'shilishda duplicate membership oldi olinadi.
    - Takroriy chaqiriq idempotent: agar o'quvchi allaqachon guruhda bo'lsa, (False, history) qaytaradi.
    - Kross-markaz tekshiruvi: filial/markazga tegishli guruhga boshqa markaz talabasi
      qo'shila olmaydi (ValueError ko'tariladi).
    - Obuna yoki pullik tarif o'zgarmaydi.
    """
    from decimal import Decimal
    from django.utils import timezone
    from apps.courses.models import GroupEnrollment, GroupMembershipHistory

    with transaction.atomic():
        # Lock group row to prevent race conditions during concurrent enrollments
        locked_group = StudentGroup.objects.select_for_update().get(id=group.id)

        if locked_group.status == StudentGroup.Status.ARCHIVED:
            raise ValueError("Ushbu guruh arxivlangan. Unga o'quvchi qo'shib bo'lmaydi.")

        # Cross-center tenant validation
        if locked_group.branch_id:
            target_center_id = locked_group.branch.center_id
            if student.learning_center_id and student.learning_center_id != target_center_id:
                raise ValueError("Talaba boshqa o'quv markaziga biriktirilgan.")
            if student.branch_id:
                branch_center_id = getattr(student.branch, "center_id", None)
                if branch_center_id and branch_center_id != target_center_id:
                    raise ValueError("Talaba boshqa o'quv markaziga biriktirilgan.")

        # Check if already a member
        if locked_group.students.filter(id=student.id).exists():
            existing_history = GroupMembershipHistory.objects.filter(
                group=locked_group, student=student, removed_at__isnull=True
            ).first()
            return False, existing_history

        # Check group capacity
        max_cap = getattr(locked_group, "max_students", 50) or 50
        current_count = locked_group.students.count()
        if current_count >= max_cap:
            raise ValueError(f"Guruh to'lgan. Maksimal sig'im: {max_cap} ta o'quvchi.")

        # Add to M2M
        locked_group.students.add(student)

        # Update student's branch/learning_center if not set
        update_fields: list[str] = []
        branch = locked_group.branch
        if branch is not None:
            if not student.branch_id:
                student.branch = branch
                update_fields.append("branch")
            if branch.center_id and not student.learning_center_id:
                student.learning_center_id = branch.center_id
                update_fields.append("learning_center")
        if update_fields:
            student.save(update_fields=update_fields)

        # Ensure/activate GroupEnrollment (Truthful billing state: do not fabricate past payments)
        today = timezone.localdate()
        enrollment, created = GroupEnrollment.objects.get_or_create(
            group=locked_group,
            student=student,
            defaults={
                "monthly_fee": Decimal(str(locked_group.monthly_fee or 400000)),
                "billing_cycle_day": 10,
                "last_payment_date": None,
                "next_payment_due": today + timezone.timedelta(days=7),
                "payment_status": GroupEnrollment.PaymentStatus.DUE_SOON,
                "is_active": True,
            },
        )
        if not created and not enrollment.is_active:
            enrollment.is_active = True
            enrollment.save(update_fields=["is_active", "updated_at"])

        # Record GroupMembershipHistory
        was_previously_member = GroupMembershipHistory.objects.filter(
            group=locked_group, student=student
        ).exists()
        action = (
            GroupMembershipHistory.Action.REJOINED
            if was_previously_member
            else GroupMembershipHistory.Action.JOINED
        )
        now = timezone.now()
        history = GroupMembershipHistory.objects.create(
            group=locked_group,
            student=student,
            action=action,
            joined_at=now,
            removed_at=None,
            actor=actor,
            reason=reason or ("rejoined" if was_previously_member else "joined"),
            metadata=metadata or {},
        )

        _invalidate_tma_cache_on_commit()
        return True, history


def remove_student_from_group(
    group: StudentGroup,
    student: User,
    actor: User | None = None,
    reason: str = "",
    metadata: dict[str, Any] | None = None,
) -> bool:
    """
    O'quvchini guruhdan chiqaradi va a'zolik tarixiga yozadi.

    XAVFSIZLIK VA MA'LUMOT BUTUNLIGI:
    - Talabaning test natijalari (Result), urinishlari (TestAttempt),
      yuborgan esselari (EssaySubmission), davomati (AttendanceRecord)
      va hisobotlari HECH QACHON O'CHIRILMAYDI.
    - Faqat guruh a'zoligi to'xtatiladi:
      `group.students.remove(student)` va `GroupEnrollment.is_active = False`.
    - Tarixda `removed_at` belgilanadi va REMOVED harakat auditi yoziladi.
    """
    from django.utils import timezone
    from apps.courses.models import GroupEnrollment, GroupMembershipHistory

    with transaction.atomic():
        locked_group = StudentGroup.objects.select_for_update().get(id=group.id)

        if not locked_group.students.filter(id=student.id).exists():
            return False

        # Remove from M2M
        locked_group.students.remove(student)

        # Deactivate GroupEnrollment
        GroupEnrollment.objects.filter(group=locked_group, student=student).update(
            is_active=False
        )

        # Update open history records
        now = timezone.now()
        open_records = list(
            GroupMembershipHistory.objects.filter(
                group=locked_group, student=student, removed_at__isnull=True
            )
        )
        for rec in open_records:
            rec.removed_at = now
            rec.save(update_fields=["removed_at"])

        # Write REMOVED audit entry
        joined_at = open_records[0].joined_at if open_records else now
        GroupMembershipHistory.objects.create(
            group=locked_group,
            student=student,
            action=GroupMembershipHistory.Action.REMOVED,
            joined_at=joined_at,
            removed_at=now,
            actor=actor,
            reason=reason or "manual_remove",
            metadata=metadata or {},
        )

        _invalidate_tma_cache_on_commit()
        return True


def get_group_membership_history(group: StudentGroup):
    """Guruh a'zoligi tarixi ro'yxati (eng so'nggi harakatlar yuqorida)."""
    from apps.courses.models import GroupMembershipHistory

    return GroupMembershipHistory.objects.filter(group=group).select_related(
        "student", "actor"
    ).order_by("-created_at", "-id")


def _attach_student_to_group(
    student: User,
    group: StudentGroup,
    actor: User | None = None,
    reason: str = "invite",
) -> bool:
    """
    O'quvchini guruhga biriktiradi va bo'sh filial/markaz maydonlarini to'ldiradi.

    XAVFSIZLIK: guruhga qo'shilish HECH QANDAY pullik tarif (PRO/PREMIUM) bermaydi.
    Taklif kodi/havolasi ommaviy tarqatilishi mumkin, shuning uchun tarif faqat
    ``apps.payments.subscriptions.grant_subscription`` (admin / tasdiqlangan to'lov /
    ustoz kvotasi) orqali, audit bilan beriladi (qarang: tests/test_free_pro_leak.py).

    Returns True agar o'quvchi yangi qo'shilgan bo'lsa, False agar allaqachon a'zo edi.
    """
    success, _ = add_student_to_group(
        group=group,
        student=student,
        actor=actor or student,
        reason=reason,
    )
    return success


def join_group_by_token(student: User, token_or_code: str) -> tuple[str, StudentGroup]:
    """
    Joins student to group using invite token or code.
    Returns:
      ("ALREADY_MEMBER", group) if student is already in the group
      ("SUCCESS", group) on successful addition (no subscription change).
    Raises ValueError if group is not found.
    """
    group = find_group_by_token_or_code(token_or_code)
    if not group:
        raise ValueError(f"'{token_or_code}' bo'yicha guruh topilmadi.")

    if not _attach_student_to_group(student, group):
        return ("ALREADY_MEMBER", group)

    logger.info("Student %s joined group %s via token", student.id, group.id)
    return ("SUCCESS", group)


def join_group_by_invite_code(student: User, invite_code: str) -> StudentGroup:
    """O'quvchini taklif kodi orqali guruhga qo'shadi (obuna o'zgarmaydi)."""
    group = find_group_by_token_or_code(invite_code)
    if not group:
        raise ValueError(f"'{invite_code}' kodi bo'yicha guruh topilmadi.")

    if _attach_student_to_group(student, group):
        logger.info("Student %s joined group %s via code", student.id, group.id)

    return group


def build_group_extended_analytics(
    group: StudentGroup, student_ids: list[int] | None = None
) -> dict[str, Any]:
    """Compute assignment completion, weak tests, pending queues and 12-criterion essay averages."""
    from django.utils import timezone

    from apps.courses.models import GroupJoinRequest, Homework, HomeworkSubmission
    from apps.essays.models import EssayCriterionScore, EssaySubmission
    from apps.results.models import Result

    if student_ids is None:
        student_ids = list(group.students.values_list("id", flat=True))

    now = timezone.now()
    active_hw = list(
        Homework.objects.filter(group=group, status=Homework.Status.ACTIVE).values(
            "id", "due_date"
        )
    )
    active_ids = [h["id"] for h in active_hw]
    total_students = len(student_ids)
    expected_submissions = len(active_ids) * total_students

    completed_submissions = 0
    overdue_count = 0
    if active_ids and student_ids:
        completed_pairs = set(
            HomeworkSubmission.objects.filter(
                homework_id__in=active_ids,
                student_id__in=student_ids,
                is_completed=True,
            ).values_list("homework_id", "student_id")
        )
        completed_submissions = len(completed_pairs)
        for hw in active_hw:
            if hw["due_date"] and hw["due_date"] < now:
                done_for_hw = sum(1 for hw_id, _ in completed_pairs if hw_id == hw["id"])
                overdue_count += max(0, total_students - done_for_hw)

    completion_rate = (
        round(completed_submissions / expected_submissions * 100, 1)
        if expected_submissions > 0
        else None
    )

    weak_tests: list[dict[str, Any]] = []
    criterion_averages: list[dict[str, Any]] = []
    pending_reviews_count = 0
    pending_appeals_count = 0

    if student_ids:
        weak_rows = (
            Result.objects.filter(
                student_id__in=student_ids,
                attempt__is_preview=False,
                attempt__trial_part_id__isnull=True,
            )
            .values("test_id", "test__title")
            .annotate(
                attempts=Count("id"),
                passed=Count("id", filter=Q(is_passed=True)),
                avg_percentage=Avg("percentage"),
            )
            .filter(attempts__gte=2)
            .order_by("avg_percentage", "-attempts")[:5]
        )
        weak_tests = [
            {
                "test_id": r["test_id"],
                "test_title": r["test__title"] or "",
                "attempts": int(r["attempts"] or 0),
                "passed": int(r["passed"] or 0),
                "avg_percentage": round(float(r["avg_percentage"] or 0), 1),
            }
            for r in weak_rows
        ]

        essay_qs = EssaySubmission.objects.filter(
            Q(student_id__in=student_ids) | Q(assignment__group=group)
        ).distinct()
        essay_counts = essay_qs.aggregate(
            pending_reviews=Count(
                "id", filter=Q(status=EssaySubmission.Status.PENDING_TEACHER)
            ),
            pending_appeals=Count(
                "id",
                filter=Q(
                    appeal_status__in=[
                        EssaySubmission.AppealStatus.SUBMITTED,
                        EssaySubmission.AppealStatus.AWAITING_REVIEWER,
                        EssaySubmission.AppealStatus.UNDER_REVIEW,
                    ]
                ),
            ),
        )
        pending_reviews_count = int(essay_counts.get("pending_reviews") or 0)
        pending_appeals_count = int(essay_counts.get("pending_appeals") or 0)

        crit_rows = (
            EssayCriterionScore.objects.filter(submission__in=essay_qs)
            .values("criterion_id", "name")
            .annotate(avg_score=Avg("score"), samples=Count("id"))
            .order_by("avg_score", "criterion_id")[:12]
        )
        criterion_averages = [
            {
                "criterion_id": int(r["criterion_id"]),
                "name": r["name"],
                "avg_score": round(float(r["avg_score"] or 0), 2),
                "samples": int(r["samples"] or 0),
            }
            for r in crit_rows
        ]

    pending_join_requests_count = GroupJoinRequest.objects.filter(
        group=group, status=GroupJoinRequest.Status.PENDING
    ).count()

    return {
        "assignments_summary": {
            "active_assignments": len(active_ids),
            "completed_submissions": completed_submissions,
            "expected_submissions": expected_submissions,
            "completion_rate": completion_rate,
            "overdue_count": overdue_count,
        },
        "weak_tests": weak_tests,
        "essay_insights": {
            "pending_reviews_count": pending_reviews_count,
            "pending_appeals_count": pending_appeals_count,
            "pending_join_requests_count": pending_join_requests_count,
            "criterion_averages": criterion_averages,
        },
    }


def export_group_to_excel(group: StudentGroup) -> bytes:
    """Guruh monitoringini zamonaviy Excel (.xlsx) fayliga eksport qiladi."""
    import openpyxl
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    from apps.core.spreadsheet import safe_cell

    analytics = get_group_full_analytics(group)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Guruh Monitoringi"
    ws.views.sheetView[0].showGridLines = True

    # Ranglar
    HEADER_BG = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
    ROW_ALT_BG = PatternFill(
        start_color="F8FAFC", end_color="F8FAFC", fill_type="solid"
    )
    SUMMARY_BG = PatternFill(
        start_color="E2E8F0", end_color="E2E8F0", fill_type="solid"
    )

    FONT_TITLE = Font(name="Calibri", size=16, bold=True, color="0F172A")
    FONT_SUBTITLE = Font(name="Calibri", size=11, italic=True, color="475569")
    FONT_HEADER = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    FONT_REGULAR = Font(name="Calibri", size=11, color="1E293B")
    FONT_BOLD = Font(name="Calibri", size=11, bold=True, color="0F172A")

    THIN_BORDER = Border(
        left=Side(style="thin", color="CBD5E1"),
        right=Side(style="thin", color="CBD5E1"),
        top=Side(style="thin", color="CBD5E1"),
        bottom=Side(style="thin", color="CBD5E1"),
    )

    # 1. Sarlavha
    ws.merge_cells("A1:I1")
    ws["A1"] = f"GRAND EDUCATION — {group.name.upper()} GURUHI HISOBOTI"
    ws["A1"].font = FONT_TITLE
    ws["A1"].alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[1].height = 30

    # 2. Qo'shimcha ma'lumotlar
    ws["A2"] = (
        f"Ustoz: {analytics['teacher_name']}  |  Guruh kodi: {analytics['invite_code']}  |  Sana: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    )
    ws["A2"].font = FONT_SUBTITLE
    ws.merge_cells("A2:I2")
    ws.row_dimensions[2].height = 20

    # Bo'sh qator
    ws.row_dimensions[3].height = 10

    # 3. Ustunlar sarlavhasi
    headers = [
        "№",
        "O'quvchi F.I.Sh.",
        "Email / Login",
        "Tarif",
        "Testlar soni",
        "O'rtacha ko'rsatkich (%)",
        "BMB Sertifikat Darajasi",
        "Esselar soni",
        "O'rtacha esse bali",
        "To'lov holati",
        "Oxirgi faollik",
    ]

    ws.row_dimensions[4].height = 26
    for col_idx, header in enumerate(headers, start=1):
        cell = ws.cell(row=4, column=col_idx, value=header)
        cell.fill = HEADER_BG
        cell.font = FONT_HEADER
        cell.alignment = Alignment(
            horizontal="center", vertical="center", wrap_text=True
        )
        cell.border = THIN_BORDER

    # 4. Ma'lumotlar qatorlari
    current_row = 5
    for item in analytics["students"]:
        ws.row_dimensions[current_row].height = 22
        is_even = current_row % 2 == 0
        row_fill = ROW_ALT_BG if is_even else None

        row_data = [
            item["rank"],
            item["full_name"],
            item["email"],
            item.get("pro_status_label", "⭐ PRO (Faol)"),
            item["tests_taken"],
            f"{item['avg_test_pct']}%",
            item["bmb_grade"],
            item["essays_written"],
            f"{item['avg_essay_score']} ball",
            item.get("tuition_label", "Kutilmoqda"),
            item["last_active"],
        ]

        for col_idx, val in enumerate(row_data, start=1):
            cell = ws.cell(row=current_row, column=col_idx, value=safe_cell(val))
            cell.font = FONT_REGULAR
            cell.border = THIN_BORDER
            if row_fill:
                cell.fill = row_fill

            # Formatlash
            if col_idx in (1, 4, 5, 7, 8, 10):
                cell.alignment = Alignment(horizontal="center", vertical="center")
            elif col_idx in (6, 9):
                cell.alignment = Alignment(horizontal="right", vertical="center")
                cell.font = FONT_BOLD
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")

        current_row += 1

    # 5. Jami qatori
    ws.row_dimensions[current_row].height = 24
    summary_cells = [
        ("A", "B", "JAMI O'QUVCHILAR:"),
        ("C", "D", f"{analytics['total_students']} nafar"),
        ("E", "F", f"O'rtacha guruh bali: {analytics['group_avg_percentage']}%"),
        ("G", "G", f"BMB: {analytics['group_bmb_grade']}"),
        (
            "H",
            "J",
            f"A+: {analytics['bmb_distribution']['A+']} | A: {analytics['bmb_distribution']['A']} | B+: {analytics['bmb_distribution']['B+']} | B: {analytics['bmb_distribution']['B']}",
        ),
    ]
    for start_c, end_c, val in summary_cells:
        if start_c != end_c:
            ws.merge_cells(f"{start_c}{current_row}:{end_c}{current_row}")
        c = ws[f"{start_c}{current_row}"]
        c.value = safe_cell(val)
        c.font = FONT_BOLD
        c.fill = SUMMARY_BG
        c.alignment = Alignment(horizontal="center", vertical="center")

    for col in range(1, 11):
        ws.cell(row=current_row, column=col).border = THIN_BORDER

    # Ustun kengliklarini avtomatik sozlash
    for col in ws.columns:
        max_len = max(len(str(cell.value or "")) for cell in col)
        col_letter = get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = max(max_len + 4, 12)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def export_group_to_pdf(group: StudentGroup) -> bytes:
    """Guruh hisobotini chiroyli PDF formatida yaratadi (ReportLab)."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    analytics = get_group_full_analytics(group)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4),
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#0F172A"),
    )
    meta_style = ParagraphStyle(
        "DocMeta",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#475569"),
    )
    th_style = ParagraphStyle(
        "TH",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=11,
        textColor=colors.white,
        alignment=1,  # center
    )
    td_style = ParagraphStyle(
        "TD",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#1E293B"),
    )
    td_bold = ParagraphStyle(
        "TDBold",
        parent=td_style,
        fontName="Helvetica-Bold",
        alignment=1,
    )

    story = []

    # Sarlavha
    story.append(
        Paragraph(
            f"GRAND EDUCATION — {group.name.upper()} GURUHI HISOBOTI", title_style
        )
    )
    story.append(Spacer(1, 4))
    meta_text = (
        f"<b>Ustoz:</b> {analytics['teacher_name']} &nbsp;&nbsp;|&nbsp;&nbsp; "
        f"<b>Guruh kodi:</b> {analytics['invite_code']} &nbsp;&nbsp;|&nbsp;&nbsp; "
        f"<b>Jami o'quvchilar:</b> {analytics['total_students']} nafar &nbsp;&nbsp;|&nbsp;&nbsp; "
        f"<b>O'rtacha ball:</b> {analytics['group_avg_percentage']}% ({analytics['group_bmb_grade']}) &nbsp;&nbsp;|&nbsp;&nbsp; "
        f"<b>Sana:</b> {datetime.now().strftime('%d.%m.%Y')}"
    )
    story.append(Paragraph(meta_text, meta_style))
    story.append(Spacer(1, 14))

    # BMB darajalar taqsimot paneli
    bmb = analytics["bmb_distribution"]
    bmb_summary = (
        f"<b>BMB Sertifikat Darajalari Taqsimoti:</b> &nbsp;&nbsp;"
        f"<b>A+ (Maksimal):</b> {bmb['A+']} nafar &nbsp;&nbsp;|&nbsp;&nbsp; "
        f"<b>A:</b> {bmb['A']} &nbsp;&nbsp;|&nbsp;&nbsp; "
        f"<b>B+:</b> {bmb['B+']} &nbsp;&nbsp;|&nbsp;&nbsp; "
        f"<b>B:</b> {bmb['B']} &nbsp;&nbsp;|&nbsp;&nbsp; "
        f"<b>C+:</b> {bmb['C+']} &nbsp;&nbsp;|&nbsp;&nbsp; "
        f"<b>C:</b> {bmb['C']} &nbsp;&nbsp;|&nbsp;&nbsp; "
        f"<b>Yetarli emas:</b> {bmb['Fail']}"
    )
    story.append(Paragraph(bmb_summary, meta_style))
    story.append(Spacer(1, 10))

    # Jadval
    table_data = [
        [
            Paragraph("№", th_style),
            Paragraph("O'quvchi F.I.Sh.", th_style),
            Paragraph("Email", th_style),
            Paragraph("Testlar", th_style),
            Paragraph("O'rtacha %", th_style),
            Paragraph("BMB Daraja", th_style),
            Paragraph("Esselar", th_style),
            Paragraph("Esse bali", th_style),
            Paragraph("Oxirgi faollik", th_style),
        ]
    ]

    for item in analytics["students"]:
        table_data.append(
            [
                Paragraph(str(item["rank"]), td_bold),
                Paragraph(item["full_name"], td_style),
                Paragraph(item["email"], td_style),
                Paragraph(str(item["tests_taken"]), td_bold),
                Paragraph(f"{item['avg_test_pct']}%", td_bold),
                Paragraph(item["bmb_grade"], td_bold),
                Paragraph(str(item["essays_written"]), td_bold),
                Paragraph(f"{item['avg_essay_score']}", td_bold),
                Paragraph(item["last_active"], td_style),
            ]
        )

    col_widths = [
        1.2 * cm,
        5.5 * cm,
        4.5 * cm,
        1.8 * cm,
        2.4 * cm,
        2.6 * cm,
        1.8 * cm,
        2.2 * cm,
        4.0 * cm,
    ]
    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [colors.white, colors.HexColor("#F8FAFC")],
                ),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )

    story.append(t)
    doc.build(story)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Group Lifecycle, Archiving & Safe Deletion Audit (GRANDEC NEXT 8.0)
# ---------------------------------------------------------------------------


def get_group_dependencies(group: StudentGroup) -> dict[str, Any]:
    """
    Audits all dependencies of a StudentGroup across academic history,
    attendance, homeworks, essays, test attempts, and memberships.
    """
    from apps.courses.models import HomeworkSubmission
    from apps.tests.models import TestAttempt

    students_count = group.students.count()
    homeworks_count = group.homeworks.count()
    submissions_count = HomeworkSubmission.objects.filter(homework__group=group).count()
    attendance_sessions_count = group.attendance_sessions.count()
    essay_assignments_count = group.essay_assignments.count()
    test_attempts_count = TestAttempt.objects.filter(classroom_group=group).count()
    invitations_count = group.invitations.count()
    join_requests_count = group.join_requests.count()

    has_academic_history = bool(
        homeworks_count > 0
        or submissions_count > 0
        or attendance_sessions_count > 0
        or essay_assignments_count > 0
        or test_attempts_count > 0
    )
    can_safely_delete = not has_academic_history and students_count == 0

    dependencies_dict = {
        "students_count": students_count,
        "homeworks_count": homeworks_count,
        "submissions_count": submissions_count,
        "homework_submissions_count": submissions_count,
        "attendance_sessions_count": attendance_sessions_count,
        "essay_assignments_count": essay_assignments_count,
        "test_attempts_count": test_attempts_count,
        "invitations_count": invitations_count,
        "join_requests_count": join_requests_count,
    }

    return {
        "group_id": group.id,
        "group_name": group.name,
        "status": group.status,
        "is_active": group.is_active,
        "can_safely_delete": can_safely_delete,
        "can_delete": can_safely_delete,
        "has_academic_history": has_academic_history,
        "recommendation": "delete" if can_safely_delete else "archive",
        "dependencies": dependencies_dict,
        **dependencies_dict,
    }


def archive_group(group: StudentGroup, actor: Any) -> StudentGroup:
    """
    Safely archives a StudentGroup.
    Revokes all active invitations, marks status as ARCHIVED, preserving
    all academic records, attendance, submissions, essays, and attempts.
    """
    from django.core.exceptions import PermissionDenied
    from apps.accounts.access import is_platform_admin

    if actor is None or not getattr(actor, "is_authenticated", False):
        raise PermissionDenied("Foydalanuvchi tizimga kirmagan.")
    if not (is_platform_admin(actor) or getattr(actor, "is_superuser", False) or group.teacher_id == actor.id):
        raise PermissionDenied("Guruhni arxivlash huquqiga ega emassiz.")

    with transaction.atomic():
        locked_group = StudentGroup.objects.select_for_update().get(id=group.id)
        locked_group.status = StudentGroup.Status.ARCHIVED
        locked_group.save(update_fields=["status", "updated_at"])

        # Revoke all active invitations for this group
        locked_group.invitations.filter(is_revoked=False).update(is_revoked=True)
        _invalidate_tma_cache_on_commit()

    logger.info("Group %d (%s) archived by user %s", group.id, group.name, getattr(actor, "id", None))
    return locked_group


def restore_group(group: StudentGroup, actor: Any) -> StudentGroup:
    """Restores an archived StudentGroup back to ACTIVE status."""
    from django.core.exceptions import PermissionDenied
    from apps.accounts.access import is_platform_admin

    if actor is None or not getattr(actor, "is_authenticated", False):
        raise PermissionDenied("Foydalanuvchi tizimga kirmagan.")
    if not (is_platform_admin(actor) or getattr(actor, "is_superuser", False) or group.teacher_id == actor.id):
        raise PermissionDenied("Guruhni qayta faollashtirish huquqiga ega emassiz.")

    with transaction.atomic():
        locked_group = StudentGroup.objects.select_for_update().get(id=group.id)
        locked_group.status = StudentGroup.Status.ACTIVE
        locked_group.save(update_fields=["status", "updated_at"])
        _invalidate_tma_cache_on_commit()

    logger.info("Group %d (%s) restored by user %s", group.id, group.name, getattr(actor, "id", None))
    return locked_group


def delete_group_safely(group: StudentGroup, actor: Any) -> bool:
    """
    Attempts to permanently delete an empty StudentGroup without academic history.
    Raises ValidationError if the group has students, homeworks, submissions,
    attendance, or essay assignments.
    """
    from django.core.exceptions import PermissionDenied, ValidationError
    from apps.accounts.access import is_platform_admin

    if actor is None or not getattr(actor, "is_authenticated", False):
        raise PermissionDenied("Foydalanuvchi tizimga kirmagan.")
    if not (is_platform_admin(actor) or getattr(actor, "is_superuser", False) or group.teacher_id == actor.id):
        raise PermissionDenied("Guruhni o'chirish huquqiga ega emassiz.")

    deps = get_group_dependencies(group)
    if not deps["can_safely_delete"]:
        history_details = []
        if deps["students_count"]:
            history_details.append(f"{deps['students_count']} nafar o'quvchi")
        if deps["homeworks_count"]:
            history_details.append(f"{deps['homeworks_count']} ta vazifa")
        if deps["attendance_sessions_count"]:
            history_details.append(f"{deps['attendance_sessions_count']} ta davomat darsi")
        if deps["essay_assignments_count"]:
            history_details.append(f"{deps['essay_assignments_count']} ta esse topshirig'i")
        if deps["test_attempts_count"]:
            history_details.append(f"{deps['test_attempts_count']} ta test urinishi")

        details_str = ", ".join(history_details)
        raise ValidationError(
            f"Guruhda mavjud ma'lumotlar bor ({details_str}). "
            f"Akademik tarix daxlsizligi uchun ushbu guruhni o'chirish taqiqlanadi. "
            f"O'rniga guruhni arxivlang."
        )

    with transaction.atomic():
        group_name = group.name
        group_id = group.id
        group.delete()

    logger.info("Empty group %d (%s) deleted by user %s", group_id, group_name, getattr(actor, "id", None))
    return True


def transfer_group_teacher(group: StudentGroup, new_teacher: User, actor: Any) -> StudentGroup:
    """
    Transfers responsibility of an authorized group to a new teacher.
    Validates permissions, active status and teacher role.
    """
    from django.core.exceptions import PermissionDenied, ValidationError
    from apps.accounts.access import is_platform_admin

    if actor is None or not getattr(actor, "is_authenticated", False):
        raise PermissionDenied("Foydalanuvchi tizimga kirmagan.")
    if not (is_platform_admin(actor) or getattr(actor, "is_superuser", False) or group.teacher_id == actor.id):
        raise PermissionDenied("Guruh o'qituvchisini o'zgartirish huquqiga ega emassiz.")

    if not new_teacher or not new_teacher.is_active:
        raise ValidationError("Yangi tayinlanayotgan o'qituvchi topilmadi yoki hisob faol emas.")

    if getattr(new_teacher, "role", "") != "teacher" and not getattr(new_teacher, "is_teacher", False) and not getattr(new_teacher, "is_staff", False):
        raise ValidationError("Faqat tasdiqlangan o'qituvchiga guruh mas'uliyatini o'tkazish mumkin.")

    # Cross-center tenant check
    if group.branch_id and getattr(group.branch, "center_id", None):
        target_center_id = group.branch.center_id
        if new_teacher.learning_center_id and new_teacher.learning_center_id != target_center_id:
            raise ValidationError("Yangi o'qituvchi boshqa o'quv markaziga biriktirilgan.")
        if new_teacher.branch_id and getattr(new_teacher.branch, "center_id", None) != target_center_id:
            raise ValidationError("Yangi o'qituvchi boshqa o'quv markaziga biriktirilgan.")

    with transaction.atomic():
        locked_group = StudentGroup.objects.select_for_update().get(id=group.id)
        old_teacher_id = locked_group.teacher_id
        locked_group.teacher = new_teacher
        locked_group.save(update_fields=["teacher", "updated_at"])

        # Re-route pending essay reviews for this group's assignments from old teacher to new teacher
        try:
            from apps.essays.models import EssaySubmission
            EssaySubmission.objects.filter(
                assignment__group=locked_group,
                status=EssaySubmission.Status.PENDING_TEACHER,
                assigned_reviewer_id=old_teacher_id,
            ).update(assigned_reviewer=new_teacher)
        except Exception:
            pass

    logger.info(
        "Group %d (%s) teacher transferred from %s to %s by user %s",
        group.id,
        group.name,
        old_teacher_id,
        new_teacher.id,
        getattr(actor, "id", None),
    )
    return locked_group

