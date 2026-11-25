"""Data-grounded student learning insights without fabricated predictions."""

from __future__ import annotations

from typing import Any

from django.db.models import Avg, Count, Max, Q

MIN_SUBJECT_SAMPLES = 2
MIN_TREND_SAMPLES = 4


def build_student_insights(user) -> dict[str, Any]:
    """Compute truthful learning insights from a student's official records.

    - Subject strength/weakness classification requires at least 2 real attempts
      per subject (never invented from 0 or 1 attempts).
    - Improvement delta requires at least 4 completed non-preview, non-trial
      test results (latest 3 average minus prior up to 3 average).
    """
    from apps.courses.models import Homework, HomeworkSubmission, StudentGroup
    from apps.essays.models import EssaySubmission, TeacherReview
    from apps.results.models import Result

    real_results = Result.objects.filter(
        student=user,
        attempt__is_preview=False,
        attempt__trial_part_id__isnull=True,
    )

    subject_rows = list(
        real_results.values("test__subject")
        .annotate(
            attempts=Count("id"),
            passed=Count("id", filter=Q(is_passed=True)),
            avg_percentage=Avg("percentage"),
            best_percentage=Max("percentage"),
        )
        .order_by("-avg_percentage", "-attempts")
    )

    subjects: list[dict[str, Any]] = []
    for row in subject_rows:
        subj = (row.get("test__subject") or "").strip() or "general"
        attempts = int(row.get("attempts") or 0)
        passed = int(row.get("passed") or 0)
        avg_pct = round(float(row["avg_percentage"]), 1) if row.get("avg_percentage") is not None else 0.0
        best_pct = round(float(row["best_percentage"]), 1) if row.get("best_percentage") is not None else 0.0
        subjects.append(
            {
                "subject": subj,
                "attempts": attempts,
                "passed": passed,
                "pass_rate": round(passed / attempts * 100, 1) if attempts > 0 else 0.0,
                "avg_percentage": avg_pct,
                "best_percentage": best_pct,
                "eligible": attempts >= MIN_SUBJECT_SAMPLES,
            }
        )

    eligible_subjects = [s for s in subjects if s["eligible"]]
    strongest_subject = eligible_subjects[0] if eligible_subjects else None
    weakest_subject = None
    if len(eligible_subjects) >= 2:
        candidate = min(eligible_subjects, key=lambda s: (s["avg_percentage"], -s["attempts"]))
        if candidate["subject"] != strongest_subject["subject"]:
            weakest_subject = candidate
    elif len(eligible_subjects) == 1 and eligible_subjects[0]["avg_percentage"] < 60.0:
        weakest_subject = eligible_subjects[0]
        strongest_subject = None

    recent_scores = [
        float(p)
        for p in real_results.order_by("-calculated_at", "-id").values_list("percentage", flat=True)[:6]
    ]
    total_attempts = sum(s["attempts"] for s in subjects)
    improvement_trend: dict[str, Any] | None = None
    if len(recent_scores) >= MIN_TREND_SAMPLES:
        recent_avg = sum(recent_scores[:3]) / 3.0
        prior = recent_scores[3:6]
        prior_avg = sum(prior) / len(prior)
        delta = round(recent_avg - prior_avg, 1)
        direction = "up" if delta >= 2.0 else "down" if delta <= -2.0 else "steady"
        improvement_trend = {
            "recent_avg": round(recent_avg, 1),
            "prior_avg": round(prior_avg, 1),
            "delta_percentage": delta,
            "direction": direction,
            "sample_size": len(recent_scores),
        }

    assigned_hw_ids = list(
        Homework.objects.filter(
            Q(student=user) | Q(group__students=user, group__status=StudentGroup.Status.ACTIVE),
            status=Homework.Status.ACTIVE,
        )
        .values_list("id", flat=True)
        .distinct()
    )
    active_assignments = len(assigned_hw_ids)
    completed_assignments = (
        HomeworkSubmission.objects.filter(
            student=user,
            homework_id__in=assigned_hw_ids,
            is_completed=True,
        )
        .values("homework_id")
        .distinct()
        .count()
        if assigned_hw_ids
        else 0
    )
    completion_rate = (
        round(completed_assignments / active_assignments * 100, 1)
        if active_assignments > 0
        else None
    )

    essay_agg = EssaySubmission.objects.filter(student=user).aggregate(
        total=Count("id"),
        reviewed=Count(
            "id",
            filter=Q(
                status__in=[
                    EssaySubmission.Status.GRADED,
                    EssaySubmission.Status.TEACHER_REVIEWED,
                ]
            ),
        ),
        appeals_open=Count(
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

    latest_reviews = list(
        TeacherReview.objects.filter(submission__student=user)
        .select_related("submission__topic", "teacher")
        .order_by("-reviewed_at")[:3]
    )
    feedback_items = [
        {
            "submission_id": rev.submission_id,
            "topic_title": rev.submission.topic.title if rev.submission.topic_id else "",
            "final_score": float(rev.final_score),
            "converted_score": rev.submission.converted_score,
            "teacher_name": rev.teacher.get_full_name() if rev.teacher_id else "",
            "comments": (rev.teacher_comments or "")[:400],
            "has_voice_feedback": bool(rev.voice_feedback),
            "voice_duration_seconds": rev.voice_duration_seconds or 0,
            "reviewed_at": rev.reviewed_at.isoformat() if rev.reviewed_at else None,
        }
        for rev in latest_reviews
    ]

    return {
        "has_sufficient_data": bool(eligible_subjects),
        "min_subject_samples": MIN_SUBJECT_SAMPLES,
        "min_trend_samples": MIN_TREND_SAMPLES,
        "total_test_attempts": total_attempts,
        "subjects": subjects,
        "strongest_subject": strongest_subject,
        "weakest_subject": weakest_subject,
        "improvement_trend": improvement_trend,
        "assignments": {
            "active_total": active_assignments,
            "completed": completed_assignments,
            "pending": max(0, active_assignments - completed_assignments),
            "completion_rate": completion_rate,
        },
        "essays": {
            "total_submitted": int(essay_agg.get("total") or 0),
            "graded_or_reviewed": int(essay_agg.get("reviewed") or 0),
            "open_appeals": int(essay_agg.get("appeals_open") or 0),
            "recent_teacher_feedback": feedback_items,
        },
    }
