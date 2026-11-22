from __future__ import annotations

from datetime import timedelta
import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.courses.models import Homework, StudentGroup
from apps.tests import studio_service as svc
from apps.tests.models import Test, TestAttempt
from apps.tests.studio_parser import parse_smart_paste


def _user(email: str, role: str) -> User:
    try:
        return User.objects.get(email=email)
    except User.DoesNotExist:
        return User.objects.create_user(
            email=email,
            password="pw-12345678",
            role=role,
            first_name=email.split("@")[0],
        )


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def teacher():
    return _user("builder_teacher@test.com", "teacher")


@pytest.fixture
def other_teacher():
    return _user("other_teacher@test.com", "teacher")


@pytest.fixture
def student():
    return _user("builder_student@test.com", "student")


@pytest.mark.django_db
class TestTestBuilder3Backend:
    def test_smart_paste_parses_single_answer_line(self):
        text = """
Q1. What is the capital of Uzbekistan?
A) Samarkand
B) Tashkent
C) Bukhara
D) Khiva
ANSWER: B

2. Python is a programming language.
A) True
B) False
Javob: A
"""
        res = parse_smart_paste(text)
        assert len(res["blocks"]) == 1
        qs = res["blocks"][0]["questions"]
        assert len(qs) == 2
        assert qs[0]["answer"] == "B"
        assert qs[1]["answer"] == "A"

    def test_duplicate_option_detection_in_validation(self):
        blocks = [
            {
                "type": "mcq",
                "section": "GENERAL",
                "title": "Duplicate Options Test",
                "instructions": "",
                "passage": "",
                "gap_text": "",
                "audio_path": "",
                "image_path": "",
                "options": [],
                "questions": [
                    {
                        "number": 1,
                        "text": "Choose something",
                        "options": ["Apple", "Apple", "Banana"],
                        "answer": "A",
                    }
                ],
            }
        ]
        issues = svc.validate_blocks(svc.normalize_blocks(blocks))
        assert any(i["code"] == "duplicate_option" and i["number"] == 1 for i in issues)

    def test_csv_file_import_parsing(self):
        csv_data = """question,choice_a,choice_b,choice_c,choice_d,correct,points,explanation
"2 + 2 = ?","3","4","5","6","B","2","Basic addition"
"Capital of France?","London","Paris","Berlin","Madrid","B","1","Geography"
"""
        res = svc.parse_csv_test_file(csv_data)
        assert res["questions_count"] == 2
        assert res["detected_answers"] == 2
        assert len(res["warnings"]) == 0
        q1 = res["blocks"][0]["questions"][0]
        assert q1["text"] == "2 + 2 = ?"
        assert q1["answer"] == "B"
        assert q1["points"] == 2
        assert q1["explanation"] == "Basic addition"

    def test_csv_file_import_missing_answer_warning(self):
        csv_data = """question,choice_a,choice_b,choice_c,choice_d,correct
"Unanswered question","Option 1","Option 2","Option 3","Option 4",""
"""
        res = svc.parse_csv_test_file(csv_data)
        assert res["questions_count"] == 1
        assert res["detected_answers"] == 0
        assert any(w["code"] == "missing_or_invalid_answer" for w in res["warnings"])

    def test_create_test_persists_points_and_explanation(self, api, teacher):
        api.force_authenticate(user=teacher)
        payload = {
            "title": "Physics Quiz",
            "subject": "uzbek",
            "time_limit_minutes": 20,
            "blocks": [
                {
                    "type": "mcq",
                    "section": "GENERAL",
                    "title": "Part 1",
                    "instructions": "",
                    "passage": "",
                    "gap_text": "",
                    "options": [],
                    "questions": [
                        {
                            "number": 1,
                            "text": "Newton's first law?",
                            "options": ["Inertia", "Force", "Gravity", "Energy"],
                            "answer": "A",
                            "points": 3,
                            "explanation": "Law of inertia",
                        }
                    ],
                }
            ],
        }
        res = api.post("/api/v1/teacher/studio/tests/", payload, format="json")
        assert res.status_code == 201
        test_id = res.data["test"]["id"]
        detail = api.get(f"/api/v1/teacher/studio/tests/{test_id}/").data
        q = detail["blocks"][0]["questions"][0]
        assert q["points"] == 3
        assert q["explanation"] == "Law of inertia"

    def test_duplicate_test_creates_draft_copy(self, api, teacher, other_teacher):
        api.force_authenticate(user=teacher)
        payload = {
            "title": "Original Test",
            "subject": "biology",
            "time_limit_minutes": 45,
            "blocks": [
                {
                    "type": "mcq",
                    "section": "GENERAL",
                    "title": "Cells",
                    "instructions": "",
                    "passage": "",
                    "gap_text": "",
                    "options": [],
                    "questions": [
                        {"number": 1, "text": "What is mitochondria?", "options": ["Powerhouse", "Wall", "Nucleus"], "answer": "A"}
                    ],
                }
            ],
        }
        res = api.post("/api/v1/teacher/studio/tests/", payload, format="json")
        orig_id = res.data["test"]["id"]

        # Duplicate by creator
        dup_res = api.post(f"/api/v1/teacher/studio/tests/{orig_id}/duplicate/")
        assert dup_res.status_code == 201
        dup_data = dup_res.data
        assert "Original Test (Nusxa)" in dup_data["test"]["title"]
        assert dup_data["test"]["status"] == Test.Status.DRAFT
        assert dup_data["test"]["id"] != orig_id
        assert len(dup_data["blocks"][0]["questions"]) == 1

        # Other teacher cannot duplicate private test
        api.force_authenticate(user=other_teacher)
        assert api.post(f"/api/v1/teacher/studio/tests/{orig_id}/duplicate/").status_code == 404

    def test_delete_draft_test_and_conflict_on_attempts(self, api, teacher, student):
        api.force_authenticate(user=teacher)
        payload = {
            "title": "Draft to delete",
            "subject": "chemistry",
            "time_limit_minutes": 15,
            "blocks": [
                {
                    "type": "mcq",
                    "section": "GENERAL",
                    "title": "Atoms",
                    "instructions": "",
                    "passage": "",
                    "gap_text": "",
                    "options": [],
                    "questions": [
                        {"number": 1, "text": "H2O?", "options": ["Water", "Acid"], "answer": "A"}
                    ],
                }
            ],
        }
        res = api.post("/api/v1/teacher/studio/tests/", payload, format="json")
        test_id = res.data["test"]["id"]

        # Delete works when there are no attempts
        del_res = api.delete(f"/api/v1/teacher/studio/tests/{test_id}/")
        assert del_res.status_code == 200
        assert not Test.objects.filter(id=test_id).exists()

        # If test has attempts, deletion is rejected with 409 Conflict
        res2 = api.post("/api/v1/teacher/studio/tests/", payload, format="json")
        test_id2 = res2.data["test"]["id"]
        test2 = Test.objects.get(id=test_id2)
        TestAttempt.objects.create(
            test=test2,
            student=student,
            is_preview=False,
            status=TestAttempt.Status.COMPLETED,
            percentage=85.0,
        )
        del_res2 = api.delete(f"/api/v1/teacher/studio/tests/{test_id2}/")
        assert del_res2.status_code == 409
        assert del_res2.data["code"] == "has_attempts"
        assert Test.objects.filter(id=test_id2).exists()

    def test_export_questions_csv_with_formula_sanitization(self, api, teacher):
        api.force_authenticate(user=teacher)
        payload = {
            "title": "Formula Test",
            "subject": "uzbek",
            "time_limit_minutes": 25,
            "blocks": [
                {
                    "type": "mcq",
                    "section": "GENERAL",
                    "title": "=SUM(1,2)",
                    "instructions": "",
                    "passage": "",
                    "gap_text": "",
                    "options": [],
                    "questions": [
                        {
                            "number": 1,
                            "text": "@danger command",
                            "options": ["+calc", "-alert", "normal"],
                            "answer": "C",
                        }
                    ],
                }
            ],
        }
        res = api.post("/api/v1/teacher/studio/tests/", payload, format="json")
        test_id = res.data["test"]["id"]

        export_res = api.get(f"/api/v1/teacher/studio/tests/{test_id}/export/")
        assert export_res.status_code == 200
        assert export_res["Content-Type"].startswith("text/csv")
        content = export_res.content.decode("utf-8")
        # Formula indicators must be prepended with single quote
        assert "'=SUM(1,2)" in content or "'@danger" in content or "'+calc" in content

    def test_test_bank_filters_by_search_status_subject(self, api, teacher):
        api.force_authenticate(user=teacher)
        # Create published english test
        t1_res = api.post("/api/v1/teacher/studio/tests/", {
            "title": "English Advanced",
            "subject": "english",
            "time_limit_minutes": 30,
            "blocks": [{"type": "mcq", "section": "GENERAL", "title": "B1", "instructions": "", "passage": "", "gap_text": "", "options": [], "questions": [{"number": 1, "text": "Q", "options": ["A", "B"], "answer": "A"}]}],
        }, format="json")
        api.post(f"/api/v1/teacher/studio/tests/{t1_res.data['test']['id']}/publish/")

        # Create draft uzbek test
        api.post("/api/v1/teacher/studio/tests/", {
            "title": "Ona tili grammatika",
            "subject": "uzbek",
            "time_limit_minutes": 20,
            "blocks": [{"type": "mcq", "section": "GENERAL", "title": "B1", "instructions": "", "passage": "", "gap_text": "", "options": [], "questions": [{"number": 1, "text": "Q", "options": ["A", "B"], "answer": "A"}]}],
        }, format="json")

        # Filter by search
        search_res = api.get("/api/v1/teacher/studio/tests/?q=Advanced").data
        assert len(search_res) == 1
        assert search_res[0]["title"] == "English Advanced"

        # Filter by status
        published_res = api.get("/api/v1/teacher/studio/tests/?status=published").data
        assert any(t["title"] == "English Advanced" for t in published_res)
        assert not any(t["title"] == "Ona tili grammatika" for t in published_res)

        # Filter by subject
        uzbek_res = api.get("/api/v1/teacher/studio/tests/?subject=uzbek").data
        assert any(t["title"] == "Ona tili grammatika" for t in uzbek_res)
        assert not any(t["title"] == "English Advanced" for t in uzbek_res)

    def test_item_analysis_pending_review_distinction(self, api, teacher, student):
        api.force_authenticate(user=teacher)
        p_res = api.post("/api/v1/teacher/studio/tests/", {
            "title": "Analysis Test",
            "subject": "uzbek",
            "time_limit_minutes": 30,
            "blocks": [{"type": "mcq", "section": "GENERAL", "title": "B1", "instructions": "", "passage": "", "gap_text": "", "options": [], "questions": [{"number": 1, "text": "Q", "options": ["A", "B"], "answer": "A"}]}],
        }, format="json")
        test_id = p_res.data["test"]["id"]
        api.post(f"/api/v1/teacher/studio/tests/{test_id}/publish/")
        test = Test.objects.get(id=test_id)

        # Student 1: completed with score 0.0 (GRADED numeric zero)
        TestAttempt.objects.create(
            test=test,
            student=student,
            is_preview=False,
            status=TestAttempt.Status.COMPLETED,
            percentage=0.0,
        )
        # Student 2: pending grading
        student2 = _user("student2@test.com", "student")
        TestAttempt.objects.create(
            test=test,
            student=student2,
            is_preview=False,
            status=TestAttempt.Status.PENDING_GRADING,
            percentage=0.0,
        )

        analysis = svc.item_analysis(test)
        assert analysis["students"] == 2
        assert analysis["pending_review_count"] == 1
        # In student matrix:
        m_s1 = next(r for r in analysis["matrix"] if r["student"] == student.get_full_name() or r["student"] == student.username or r["student"] == student.email)
        m_s2 = next(r for r in analysis["matrix"] if r["student"] == student2.get_full_name() or r["student"] == student2.username or r["student"] == student2.email)
        assert m_s1["percentage"] == 0.0
        assert m_s1["is_pending"] is False
        assert m_s2["percentage"] is None
        assert m_s2["is_pending"] is True
