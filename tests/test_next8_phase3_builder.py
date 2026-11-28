"""Phase 03 tests — Schema 1.0 JSON Exam Builder, Keyless Templates & Publish Readiness."""

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.tests.models import Question, ReadingPassage, Test
from apps.tests.package_service import export_exam_package, validate_exam_package

User = get_user_model()


def _sample_schema_v1(*, keyless: bool = False, include_audio: bool = True) -> dict:
    listening_section = {
        "code": "LISTENING",
        "name": "Listening",
        "durationMinutes": 30,
        **({"audioUrl": "https://cdn.example.com/audio/l1.mp3"} if include_audio else {}),
        "parts": [
            {
                "number": "1",
                "partNumber": 1,
                "title": "Part 1 Notes",
                "audioPlayLimit": 1,
                "transcript": "Welcome to library registration.",
                "groups": [
                    {
                        "title": "Note Completion",
                        "stimulusRef": "lis_part1_notes",
                        "contentLayout": "notes",
                        "questions": [
                            {
                                "number": 1,
                                "questionType": "INLINE_GAP_FILL",
                                "text": "Student surname: [1]",
                                "points": 1,
                                "audioStartSec": 12.5,
                                "cefrLevel": "B2",
                                "skillTags": ["detail", "spelling"],
                                **({"acceptedAnswers": ["Karimov"]} if not keyless else {}),
                            }
                        ],
                    }
                ],
            }
        ],
    }
    reading_section = {
        "code": "READING",
        "name": "Reading",
        "durationMinutes": 60,
        "parts": [
            {
                "number": "1",
                "partNumber": 1,
                "title": "Urban Trees",
                "groups": [
                    {
                        "title": "True False Not Given",
                        "stimulusRef": "read_p1_trees",
                        "contentLayout": "passage",
                        "passage": {
                            "title": "Urban Canopy",
                            "stimulusRef": "read_p1_trees",
                            "content": "Cities plant trees to cool urban heat islands.",
                        },
                        "questions": [
                            {
                                "number": 2,
                                "questionType": "TRUE_FALSE_NOT_GIVEN",
                                "text": "Trees reduce urban heat.",
                                "points": 1,
                                "evidenceText": "Cities plant trees to cool urban heat islands.",
                                "cefrLevel": "B2",
                                "skillTags": ["scanning"],
                                "options": [
                                    {"text": "TRUE", **({"isCorrect": True} if not keyless else {})},
                                    {"text": "FALSE", **({"isCorrect": False} if not keyless else {})},
                                    {"text": "NOT GIVEN", **({"isCorrect": False} if not keyless else {})},
                                ],
                            }
                        ],
                    }
                ],
            }
        ],
    }
    return {
        "schemaVersion": "1.0",
        "isTemplate": keyless,
        "title": "IELTS Academic Package Test",
        "description": "Full diagnostic package",
        "subject": "english",
        "examType": "ielts_academic",
        "assessmentCategory": "full_mock",
        "timeLimitMinutes": 90,
        "sections": [listening_section, reading_section],
    }


def test_validate_exam_package_rejects_bad_schema_and_stimulus_collision():
    bad_ver = _sample_schema_v1()
    bad_ver["schemaVersion"] = "2.0"
    res = validate_exam_package(bad_ver)
    assert res["valid"] is False
    assert any(e["code"] == "unsupported_schema_version" for e in res["errors"])

    collision = _sample_schema_v1()
    collision["sections"][1]["parts"][0]["groups"].append(
        {
            "title": "Conflict",
            "stimulusRef": "read_p1_trees",
            "passage": {"stimulusRef": "read_p1_trees", "content": "Completely different text"},
            "questions": [
                {
                    "number": 3,
                    "questionType": "MULTIPLE_CHOICE",
                    "text": "Pick one",
                    "options": [{"text": "A", "isCorrect": True}, {"text": "B"}],
                }
            ],
        }
    )
    col_res = validate_exam_package(collision)
    assert col_res["valid"] is False
    assert any(e["code"] == "stimulus_ref_collision" for e in col_res["errors"])


@pytest.mark.django_db
def test_builder_package_import_roundtrip_and_keyless_publish_gate():
    teacher = User.objects.create_user(
        email="builder_teacher@example.com",
        password="StrongPassword123!",
        role="teacher",
    )
    client = APIClient()
    client.force_authenticate(user=teacher)

    # 1. Keyless template import succeeds as DRAFT with is_keyless=True
    tpl_pkg = _sample_schema_v1(keyless=True)
    imp_tpl = client.post("/api/v1/teacher/studio/package/import/?template=1", tpl_pkg, format="json")
    assert imp_tpl.status_code == 201
    tpl_id = imp_tpl.data["test"]["id"]
    tpl_obj = Test.objects.get(id=tpl_id)
    assert tpl_obj.is_keyless is True

    # Readiness & publish must block keyless template
    ready_tpl = client.get(f"/api/v1/teacher/studio/tests/{tpl_id}/readiness/")
    assert ready_tpl.status_code == 200
    assert ready_tpl.data["ready"] is False
    assert any(i["code"] == "keyless_template_cannot_publish" for i in ready_tpl.data["issues"])
    pub_tpl = client.post(f"/api/v1/teacher/studio/tests/{tpl_id}/publish/")
    assert pub_tpl.status_code == 400

    # 2. Incomplete full mock (missing Listening audio) blocked by readiness
    no_audio_pkg = _sample_schema_v1(keyless=False, include_audio=False)
    imp_no_audio = client.post("/api/v1/teacher/studio/package/import/", no_audio_pkg, format="json")
    assert imp_no_audio.status_code == 201
    na_id = imp_no_audio.data["test"]["id"]
    ready_na = client.get(f"/api/v1/teacher/studio/tests/{na_id}/readiness/")
    assert ready_na.data["ready"] is False
    assert any(i["code"] == "listening_audio_missing" for i in ready_na.data["issues"])

    # 3. Complete valid package imports, exports roundtrip & keyless template strips all keys
    full_pkg = _sample_schema_v1(keyless=False, include_audio=True)
    imp_full = client.post("/api/v1/teacher/studio/package/import/", full_pkg, format="json")
    assert imp_full.status_code == 201
    full_id = imp_full.data["test"]["id"]
    test_obj = Test.objects.get(id=full_id)

    assert ReadingPassage.objects.filter(test=test_obj, stimulus_ref="read_p1_trees").exists()
    q1 = Question.objects.get(test=test_obj, position=1)
    assert q1.audio_start_sec == 12.5
    assert q1.cefr_level == "B2"
    assert q1.skill_tags == ["detail", "spelling"]

    ready_full = client.get(f"/api/v1/teacher/studio/tests/{full_id}/readiness/")
    assert ready_full.status_code == 200
    assert ready_full.data["ready"] is True

    exp_full = client.get(f"/api/v1/teacher/studio/tests/{full_id}/package/")
    assert exp_full.status_code == 200
    assert exp_full.data["schemaVersion"] == "1.0"
    assert exp_full.data["sections"][0]["parts"][0]["audioPlayLimit"] == 1
    assert exp_full.data["sections"][0]["parts"][0]["groups"][0]["questions"][0]["acceptedAnswers"] == ["Karimov"]

    exp_tpl = client.get(f"/api/v1/teacher/studio/tests/{full_id}/package/?template=1")
    assert exp_tpl.status_code == 200
    assert exp_tpl.data["isTemplate"] is True
    q_lis = exp_tpl.data["sections"][0]["parts"][0]["groups"][0]["questions"][0]
    assert "acceptedAnswers" not in q_lis
    q_read_opts = exp_tpl.data["sections"][1]["parts"][0]["groups"][0]["questions"][0]["options"]
    assert all("isCorrect" not in opt for opt in q_read_opts)

    # 4. Valid imported package publishes & assigns to a group with student visibility
    from apps.courses.models import StudentGroup

    student = User.objects.create_user(email="pkg_assigned_s@example.com", password="StrongPassword123!", role="student")
    group = StudentGroup.objects.create(teacher=teacher, name="Package Cohort", subject="english")
    group.students.add(student)
    pub_full = client.post(f"/api/v1/teacher/studio/tests/{full_id}/publish/")
    assert pub_full.status_code == 200
    assert pub_full.data["test"]["status"] == "published"

    assign_res = client.post(
        f"/api/v1/teacher/studio/tests/{full_id}/assign/",
        {"group_id": group.id, "due_at": "2027-01-15T12:00:00Z", "max_attempts": 2},
        format="json",
    )
    assert assign_res.status_code == 201
    s_client = APIClient()
    s_client.force_authenticate(user=student)
    list_res = s_client.get("/api/tests/")
    assert list_res.status_code == 200
    rows = list_res.data.get("results", list_res.data)
    assert any(item["id"] == full_id for item in rows)
