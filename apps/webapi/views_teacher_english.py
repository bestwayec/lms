"""Teacher English Workspace, Unified Grading Inbox, Separated Analytics & Safe Exports."""

from __future__ import annotations

import csv
import io
from typing import Any

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import HttpResponse
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.access import is_platform_admin
from apps.core.spreadsheet import safe_row
from apps.courses.models import StudentGroup
from apps.essays.models import EssaySubmission, TeacherReview
from apps.essays.services import detect_submission_rubric
from apps.results.pdf_generator import generate_english_analytics_pdf
from apps.speaking.models import SpeakingSubmission
from apps.tests.models import Test, TestAttempt

User = get_user_model()


def _require_teacher_or_admin(user) -> None:
    if not (
        user.is_authenticated
        and user.is_active
        and (getattr(user, "role", None) in ("teacher", "center_admin") or is_platform_admin(user) or user.is_superuser)
    ):
        raise PermissionDenied("Faqat ustozlar va adminlar uchun.")


def _scoped_student_ids(user, group_id: int | None = None) -> tuple[list[int], list[dict[str, Any]]]:
    groups_qs = StudentGroup.objects.filter(status=StudentGroup.Status.ACTIVE)
    if not is_platform_admin(user) and not user.is_superuser:
        groups_qs = groups_qs.filter(teacher=user)
    groups = list(groups_qs.order_by("name").values("id", "name", "subject"))

    if group_id is not None:
        groups_qs = groups_qs.filter(id=group_id)

    student_ids = list(
        groups_qs.values_list("students__id", flat=True).distinct()
    )
    student_ids = [sid for sid in student_ids if sid is not None]
    return student_ids, groups


def build_teacher_english_workspace(user, *, group_id: int | None = None) -> dict[str, Any]:
    student_ids, groups = _scoped_student_ids(user, group_id=group_id)
    is_admin = is_platform_admin(user) or user.is_superuser

    # 1. Pending English Essays
    essays_qs = EssaySubmission.objects.select_related("student", "topic").filter(
        Q(topic__subject="english") | Q(max_score__in=(9, 16, 75))
    )
    if not is_admin:
        essays_qs = essays_qs.filter(Q(student_id__in=student_ids) | Q(assigned_reviewer=user))
    pending_essays_qs = essays_qs.filter(status=EssaySubmission.Status.PENDING_TEACHER).order_by("-submitted_at")[:30]

    pending_writing = []
    for e in pending_essays_qs:
        scale, disp_max = detect_submission_rubric(e)
        pending_writing.append(
            {
                "id": e.id,
                "student": e.student.get_full_name() or e.student.email,
                "topic": e.topic.title if e.topic else "English Writing",
                "scale": scale,
                "score": float(e.total_score or 0),
                "max_score": disp_max,
                "submitted_at": e.submitted_at.isoformat() if e.submitted_at else None,
            }
        )

    # 2. Pending English Speaking Reviews
    spk_qs = SpeakingSubmission.objects.select_related("user", "topic").filter(
        Q(teacher_review_requested=True) | Q(status=SpeakingSubmission.Status.PENDING_TEACHER)
    )
    if not is_admin:
        spk_qs = spk_qs.filter(user_id__in=student_ids)
    pending_speaking = [
        {
            "id": s.id,
            "student": s.user.get_full_name() or s.user.email,
            "topic": s.topic.title if s.topic else "Speaking",
            "track": s.track,
            "ai_band": float(s.overall_band) if s.overall_band is not None else None,
            "created_at": s.created_at.isoformat(),
        }
        for s in spk_qs.filter(teacher_reviewed_at__isnull=True).order_by("-created_at")[:30]
    ]

    # 3. Pending English Mocks
    attempts_qs = TestAttempt.objects.select_related("student", "test").filter(
        test__exam_type__in=(Test.ExamType.IELTS_ACADEMIC, Test.ExamType.IELTS_GENERAL, Test.ExamType.CEFR_MULTILEVEL),
        is_preview=False,
    )
    if not is_admin:
        attempts_qs = attempts_qs.filter(Q(student_id__in=student_ids) | Q(test__created_by=user))
    pending_mocks = []
    from apps.tests.models import ExamWrittenBridge

    for a in attempts_qs.filter(status=TestAttempt.Status.PENDING_GRADING).order_by("-completed_at")[:30]:
        bridges = list(
            ExamWrittenBridge.objects.select_related("essay_submission")
            .filter(attempt=a, essay_submission__isnull=False)
            .values_list("essay_submission_id", "essay_submission__status", "essay_submission__final_score")
        )
        spk_meta = (a.media_state or {}).get("speaking_submissions") or {}
        spk_ids = [
            int(v["submission_id"]) if isinstance(v, dict) and str(v.get("submission_id", "")).isdigit() else int(v)
            for v in spk_meta.values()
            if (isinstance(v, dict) and str(v.get("submission_id", "")).isdigit()) or str(v or "").isdigit()
        ]
        spk_items = (
            list(
                SpeakingSubmission.objects.filter(pk__in=spk_ids).values(
                    "id", "status", "track", "final_score", "overall_band"
                )
            )
            if spk_ids
            else []
        )
        pending_mocks.append(
            {
                "attempt_id": a.id,
                "test_id": a.test_id,
                "student": a.student.get_full_name() or a.student.email,
                "test_title": a.test.title,
                "exam_type": a.test.exam_type,
                "completed_at": a.completed_at.isoformat() if a.completed_at else None,
                "writing_items": [
                    {"id": sid, "status": st, "final_score": float(fs) if fs is not None else None}
                    for sid, st, fs in bridges
                ],
                "speaking_items": [
                    {
                        "id": sp["id"],
                        "status": sp["status"],
                        "track": sp["track"],
                        "final_score": float(sp["final_score"]) if sp["final_score"] is not None else None,
                    }
                    for sp in spk_items
                ],
            }
        )

    # 4. Separated Analytics (NEVER average IELTS Band 0..9 with CEFR Multilevel 0..75!)
    ielts_attempts = [a for a in attempts_qs if a.test.exam_type in (Test.ExamType.IELTS_ACADEMIC, Test.ExamType.IELTS_GENERAL)]
    ielts_bands = [float(a.band_score) for a in ielts_attempts if a.band_score is not None]

    ielts_essays_scored = [
        float(e.total_score)
        for e in essays_qs.exclude(status=EssaySubmission.Status.DRAFT)
        if detect_submission_rubric(e)[0] == "ielts" and e.total_score is not None
    ]
    ielts_speaking_scored = [
        float(s.final_score if s.final_score is not None else s.overall_band)
        for s in SpeakingSubmission.objects.filter(
            user_id__in=student_ids if not is_admin else SpeakingSubmission.objects.values_list("user_id", flat=True),
            track=SpeakingSubmission.Track.IELTS,
            status=SpeakingSubmission.Status.COMPLETED,
        )
        if (s.final_score is not None or s.overall_band is not None)
    ]

    ielts_analytics = {
        "scale": "band_9",
        "attempts_count": len(ielts_attempts),
        "avg_band": round(sum(ielts_bands) / len(ielts_bands), 2) if ielts_bands else None,
        "writing_avg_band": round(sum(ielts_essays_scored) / len(ielts_essays_scored), 2) if ielts_essays_scored else None,
        "speaking_avg_band": round(sum(ielts_speaking_scored) / len(ielts_speaking_scored), 2) if ielts_speaking_scored else None,
    }

    ml_attempts = [a for a in attempts_qs if a.test.exam_type == Test.ExamType.CEFR_MULTILEVEL]
    ml_scores_75: list[float] = []
    ml_levels = {"B1": 0, "B2": 0, "C1": 0, "BELOW_B1": 0}
    for a in ml_attempts:
        lvl = str(a.cefr_level or "").upper()
        if lvl in ml_levels:
            ml_levels[lvl] += 1
        sec = a.section_scores if isinstance(a.section_scores, dict) else {}
        vals = [float(v["score"]) for v in sec.values() if isinstance(v, dict) and isinstance(v.get("score"), (int, float))]
        if vals:
            ml_scores_75.append(round(sum(vals) / len(vals), 1))

    ml_analytics = {
        "scale": "cefr_75",
        "attempts_count": len(ml_attempts),
        "avg_score_75": round(sum(ml_scores_75) / len(ml_scores_75), 1) if ml_scores_75 else None,
        "level_distribution": ml_levels,
    }

    # 5. Audited Teacher Overrides Log
    override_audit: list[dict[str, Any]] = []
    for a in attempts_qs.filter(teacher_overridden=True).order_by("-completed_at")[:15]:
        override_audit.append(
            {
                "kind": "mock_attempt",
                "id": a.id,
                "student": a.student.get_full_name() or a.student.email,
                "title": a.test.title,
                "score": float(a.band_score) if a.band_score is not None else float(a.score or 0),
                "teacher": a.graded_by.get_full_name() or a.graded_by.email if a.graded_by else "",
                "comment": a.teacher_comment,
            }
        )
    rev_qs = TeacherReview.objects.select_related("submission", "submission__student", "submission__topic", "teacher")
    if not is_admin:
        rev_qs = rev_qs.filter(Q(teacher=user) | Q(submission__student_id__in=student_ids))
    for rev in rev_qs.order_by("-reviewed_at")[:15]:
        scale, _ = detect_submission_rubric(rev.submission)
        if scale in ("ielts", "multilevel"):
            override_audit.append(
                {
                    "kind": "essay_review",
                    "id": rev.submission_id,
                    "student": rev.submission.student.get_full_name() or rev.submission.student.email,
                    "title": rev.submission.topic.title if rev.submission.topic else "English Writing",
                    "score": float(rev.final_score),
                    "teacher": rev.teacher.get_full_name() or rev.teacher.email,
                    "comment": rev.teacher_comments,
                }
            )

    # 6. Export rows
    export_rows: list[dict[str, Any]] = []
    for a in ielts_attempts[:100]:
        export_rows.append(
            {
                "student": a.student.get_full_name() or a.student.email,
                "scale": "IELTS (/9)",
                "title": a.test.title,
                "score_label": f"Band {float(a.band_score):.1f}" if a.band_score is not None else "Pending",
                "status": a.status,
            }
        )
    for a in ml_attempts[:100]:
        export_rows.append(
            {
                "student": a.student.get_full_name() or a.student.email,
                "scale": "Multi-level (/75)",
                "title": a.test.title,
                "score_label": a.cefr_level or "Pending",
                "status": a.status,
            }
        )

    return {
        "groups": groups,
        "inbox": {
            "writing": pending_writing,
            "speaking": pending_speaking,
            "mocks": pending_mocks,
        },
        "ielts_analytics": ielts_analytics,
        "multilevel_analytics": ml_analytics,
        "override_audit": override_audit,
        "export_rows": export_rows,
    }


class TeacherEnglishWorkspaceView(APIView):
    """GET /api/v1/english/teacher/workspace/"""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        _require_teacher_or_admin(request.user)
        raw_gid = request.query_params.get("group_id")
        group_id = int(raw_gid) if raw_gid and raw_gid.isdigit() else None
        payload = build_teacher_english_workspace(request.user, group_id=group_id)
        return Response(payload, status=status.HTTP_200_OK)


class TeacherEnglishExportView(APIView):
    """GET /api/v1/english/teacher/export/?export_format=csv|pdf"""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> HttpResponse:
        _require_teacher_or_admin(request.user)
        fmt = (
            request.query_params.get("export_format")
            or request.query_params.get("format")
            or "csv"
        ).strip().lower()
        raw_gid = request.query_params.get("group_id")
        group_id = int(raw_gid) if raw_gid and raw_gid.isdigit() else None
        ws = build_teacher_english_workspace(request.user, group_id=group_id)
        rows = ws["export_rows"]

        if fmt == "pdf":
            pdf_bytes = generate_english_analytics_pdf(
                rows,
                teacher_name=request.user.get_full_name() or request.user.email,
                ielts_summary=ws["ielts_analytics"],
                multilevel_summary=ws["multilevel_analytics"],
            )
            resp = HttpResponse(pdf_bytes, content_type="application/pdf")
            resp["Content-Disposition"] = 'attachment; filename="english-analytics.pdf"'
            return resp

        if fmt == "xlsx":
            import openpyxl

            wb = openpyxl.Workbook()
            ws_sheet = wb.active
            ws_sheet.title = "English Analytics"
            ws_sheet.append(["Student", "Scale", "Title", "Score", "Status"])
            for r in rows:
                ws_sheet.append(safe_row([r["student"], r["scale"], r["title"], r["score_label"], r["status"]]))
            buf = io.BytesIO()
            wb.save(buf)
            resp = HttpResponse(
                buf.getvalue(),
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            resp["Content-Disposition"] = 'attachment; filename="english-analytics.xlsx"'
            return resp

        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(["Student", "Scale", "Title", "Score", "Status"])
        for r in rows:
            writer.writerow(
                safe_row([r["student"], r["scale"], r["title"], r["score_label"], r["status"]])
            )
        resp = HttpResponse(out.getvalue().encode("utf-8"), content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = 'attachment; filename="english-analytics.csv"'
        return resp
