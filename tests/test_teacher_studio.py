"""Teacher Studio: Smart Paste parser, save/validate/publish, assignment,
access, media upload and item analysis against real attempts."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.courses.models import Homework, StudentGroup
from apps.tests.models import Choice, ExamPart, GapBlank, Question, Test, TestAttempt
from apps.tests import services as test_services
from apps.tests.services import SaveAnswerService, StartAttemptService, SubmitAttemptService
from apps.tests.studio_parser import gap_sentence, parse_answer_pairs, parse_smart_paste

PASTE = """Reading Passage 1
Bees are remarkable insects. They communicate through a waggle dance.

Questions 1-2
Choose the correct letter A, B or C.
1. How do bees communicate?
A) By sound
B) By dance
C) By smell
2. What colour can bees not see?
A) Blue B) Red C) Yellow

Questions 3-4
Write TRUE, FALSE or NOT GIVEN.
3. Bees live alone.
4. Bees make honey. TRUE

Questions 5-6
Match each speaker with a place.
A) In a garden
B) At home
C) In a shop
5. Speaker 1
6. Speaker 2

Complete the notes.
Bees visit [7:flowers] to collect [8:nectar|pollen].

Answer key: 1: B, 2: B, 3: F, 5: C, 6: A
"""


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------
class TestParser:
    def test_mixed_paste_becomes_typed_blocks(self):
        out = parse_smart_paste(PASTE)
        types = [b["type"] for b in out["blocks"]]
        assert types == ["mcq", "tfng", "matching", "gap"]
        mcq, tfng, matching, gap = out["blocks"]
        assert mcq["section"] == "READING"
        assert mcq["passage"].startswith("Bees are remarkable")
        assert mcq["instructions"] == "Choose the correct letter A, B or C."
        assert [q["options"] for q in mcq["questions"]] == [
            ["By sound", "By dance", "By smell"],
            ["Blue", "Red", "Yellow"],  # inline "A) B) C)" on one line
        ]
        assert [q["answer"] for q in mcq["questions"]] == ["B", "B"]
        assert tfng["options"] == ["TRUE", "FALSE", "NOT GIVEN"]
        assert [q["answer"] for q in tfng["questions"]] == ["FALSE", "TRUE"]  # key "F" + trailing label
        assert tfng["questions"][1]["text"] == "Bees make honey."
        assert matching["options"] == ["In a garden", "At home", "In a shop"]
        assert [(q["text"], q["answer"]) for q in matching["questions"]] == [("Speaker 1", "C"), ("Speaker 2", "A")]
        assert gap["instructions"] == "Complete the notes."
        assert [(q["number"], q["answer"]) for q in gap["questions"]] == [(7, "flowers"), (8, "nectar|pollen")]
        assert out["warnings"] == []

    def test_star_marks_the_correct_option(self):
        out = parse_smart_paste("1. 2+2?\nA) 3\n*B) 4\nC) 5\n\n2. Capital of France?\nA) Rome\nB) Paris *")
        (block,) = out["blocks"]
        assert [q["answer"] for q in block["questions"]] == ["B", "B"]

    def test_no_answer_is_never_guessed(self):
        out = parse_smart_paste("1. Pick one\nA) x\nB) y")
        assert out["blocks"][0]["questions"][0]["answer"] == ""

    def test_answer_key_formats(self):
        assert parse_answer_pairs("1: A, 2: bees, 3=C") == {1: "A", 2: "bees", 3: "C"}
        assert parse_answer_pairs("1-A 2-B 3-C") == {1: "A", 2: "B", 3: "C"}
        out = parse_smart_paste("1. Q one\nA) a\nB) b\n2. Q two\nA) a\nB) b\n\nJavoblar:\n1. B\n2. A\n")
        assert [q["answer"] for q in out["blocks"][0]["questions"]] == ["B", "A"]

    def test_key_for_unknown_question_is_reported(self):
        out = parse_smart_paste("1. Q\nA) a\nB) b\nAnswers: 1: A, 9: C")
        assert {"code": "key_unmatched", "number": 9} in out["warnings"]

    def test_yes_no_not_given_labels(self):
        out = parse_smart_paste("Write YES, NO or NOT GIVEN.\n1. The writer agrees.\n2. Cats fly.\nKey: 1: Y, 2: NG")
        (block,) = out["blocks"]
        assert block["type"] == "tfng"
        assert block["options"] == ["YES", "NO", "NOT GIVEN"]
        assert [q["answer"] for q in block["questions"]] == ["YES", "NOT GIVEN"]

    def test_gap_without_answer_takes_the_key(self):
        out = parse_smart_paste("The [1] is red and the [2:sky] is blue.\nAnswers: 1: apple")
        (block,) = out["blocks"]
        assert block["type"] == "gap"
        assert [(q["number"], q["answer"]) for q in block["questions"]] == [(1, "apple"), (2, "sky")]

    def test_short_answer_questions(self):
        out = parse_smart_paste("1. How many legs has a spider?\n2. Name the largest ocean.\nKey: 1: 8, 2: Pacific")
        (block,) = out["blocks"]
        assert block["type"] == "short"
        assert [q["answer"] for q in block["questions"]] == ["8", "Pacific"]

    def test_listening_heading_sets_section(self):
        out = parse_smart_paste("Listening Part 1\n1. Where is he?\nA) Home\nB) Work")
        assert out["blocks"][0]["section"] == "LISTENING"

    def test_duplicate_numbers_warned(self):
        out = parse_smart_paste("1. A?\nA) x\nB) y\n1. B?\nA) x\nB) y")
        assert {"code": "duplicate_number", "number": 1} in out["warnings"]

    def test_gap_sentence_shows_one_input(self):
        text = "Bees visit [7:flowers] to collect [8:nectar]."
        assert gap_sentence(text, 7) == "Bees visit (7) ________ to collect (8) …."
        assert gap_sentence(text, 8) == "Bees visit (7) … to collect (8) ________."

    def test_huge_input_is_capped(self):
        out = parse_smart_paste("1. Q\nA) a\nB) b\n" + "x" * 200_000)
        assert out["blocks"]


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
def _user(email: str, role: str) -> User:
    return User.objects.create_user(email=email, password="pw-12345678", role=role, first_name=email.split("@")[0])


def _client(user: User) -> APIClient:
    c = APIClient()
    c.force_authenticate(user)
    return c


def _payload(blocks=None, **extra):
    return {
        "title": "Bees",
        "subject": "english",
        "time_limit_minutes": 30,
        "blocks": blocks if blocks is not None else parse_smart_paste(PASTE)["blocks"],
        **extra,
    }


@pytest.fixture
def teacher(db):
    return _user("t@studio.test", "teacher")


@pytest.fixture
def api(teacher):
    return _client(teacher)


@pytest.mark.django_db
class TestStudioApi:
    def test_students_are_forbidden(self):
        student = _user("s@studio.test", "student")
        c = _client(student)
        assert c.post("/api/v1/teacher/studio/parse/", {"text": "1. Q"}, format="json").status_code == 403
        assert c.get("/api/v1/teacher/studio/tests/").status_code == 403

    def test_parse_endpoint(self, api):
        res = api.post("/api/v1/teacher/studio/parse/", {"text": PASTE}, format="json")
        assert res.status_code == 200
        assert len(res.data["blocks"]) == 4
        assert api.post("/api/v1/teacher/studio/parse/", {"text": " "}, format="json").data["code"] == "text_required"

    def test_create_builds_cd_structure_as_draft(self, api, teacher):
        res = api.post("/api/v1/teacher/studio/tests/", _payload(), format="json")
        assert res.status_code == 201, res.data
        test = Test.objects.get(id=res.data["test"]["id"])
        assert test.status == Test.Status.DRAFT and not test.is_active
        assert test.created_by == teacher
        assert ExamPart.objects.filter(section__test=test).count() == 4
        assert test.questions.count() == 8
        q1 = test.questions.get(config__number=1)
        assert q1.question_type == Question.QuestionType.MULTIPLE_CHOICE
        assert q1.choices.get(is_correct=True).text == "By dance"
        q3 = test.questions.get(config__number=3)
        assert q3.question_type == Question.QuestionType.TRUE_FALSE_NOT_GIVEN
        assert q3.choices.get(is_correct=True).text == "FALSE"
        q6 = test.questions.get(config__number=6)
        assert q6.question_type == Question.QuestionType.MATCHING
        assert list(q6.choices.order_by("position").values_list("text", flat=True)) == ["In a garden", "At home", "In a shop"]
        assert q6.choices.get(is_correct=True).text == "In a garden"
        q8 = test.questions.get(config__number=8)
        assert q8.question_type == Question.QuestionType.INLINE_GAP_FILL
        assert "(8) ________" in q8.text
        assert sorted(GapBlank.objects.filter(question=q8).values_list("answer_text", flat=True)) == ["nectar", "pollen"]
        # One shared passage row for the three reading blocks.
        assert test.passages.filter(content__startswith="Bees are remarkable").count() == 1
        assert res.data["issues"] == []

    def test_round_trip_keeps_blocks(self, api):
        created = api.post("/api/v1/teacher/studio/tests/", _payload(), format="json").data
        res = api.get(f"/api/v1/teacher/studio/tests/{created['test']['id']}/")
        blocks = res.data["blocks"]
        assert [b["type"] for b in blocks] == ["mcq", "tfng", "matching", "gap"]
        assert blocks[3]["gap_text"] == "Bees visit [7:flowers] to collect [8:nectar|pollen]."
        assert blocks[0]["questions"][0]["answer"] == "B"
        assert blocks[2]["options"] == ["In a garden", "At home", "In a shop"]

    def test_publish_blocked_until_problems_fixed(self, api):
        blocks = parse_smart_paste(PASTE)["blocks"]
        blocks[0]["questions"][0]["answer"] = ""
        blocks[0]["questions"][1]["options"][1] = ""
        blocks.append(
            {"type": "mcq", "section": "LISTENING", "title": "L1", "questions": [
                {"number": 9, "text": "Where?", "options": ["Home", "Work"], "answer": "A"}]}
        )
        test_id = api.post("/api/v1/teacher/studio/tests/", _payload(blocks), format="json").data["test"]["id"]
        res = api.post(f"/api/v1/teacher/studio/tests/{test_id}/publish/")
        assert res.status_code == 400 and res.data["code"] == "invalid"
        codes = {(i["code"], i["number"]) for i in res.data["issues"]}
        assert ("missing_answer", 1) in codes
        assert ("empty_option", 2) in codes
        assert ("audio_missing", None) in codes
        assert Test.objects.get(id=test_id).status == Test.Status.DRAFT

        # Fix: answer, option, upload + link audio.
        blocks[0]["questions"][0]["answer"] = "B"
        blocks[0]["questions"][1]["options"][1] = "Red"
        audio = api.post(
            "/api/v1/teacher/studio/media/",
            {"kind": "audio", "file": SimpleUploadedFile("part1.mp3", b"ID3fake", content_type="audio/mpeg")},
            format="multipart",
        )
        assert audio.status_code == 201, audio.data
        blocks[-1]["audio_path"] = audio.data["path"]
        assert api.put(f"/api/v1/teacher/studio/tests/{test_id}/", _payload(blocks), format="json").status_code == 200
        res = api.post(f"/api/v1/teacher/studio/tests/{test_id}/publish/")
        assert res.status_code == 200, res.data
        test = Test.objects.get(id=test_id)
        assert test.status == Test.Status.PUBLISHED and test.is_active and test.mock_code
        assert ExamPart.objects.get(section__test=test, section__code="LISTENING").audio.name == audio.data["path"]

    def test_validate_endpoint(self, api):
        res = api.post(
            "/api/v1/teacher/studio/validate/",
            {"blocks": [{"type": "matching", "options": ["x", ""], "questions": [{"number": 1, "text": "p", "answer": ""}]}]},
            format="json",
        )
        codes = {i["code"] for i in res.data["issues"]}
        assert {"empty_option", "missing_answer"} <= codes

    def test_media_rejects_bad_types_and_foreign_paths(self, api):
        bad = api.post(
            "/api/v1/teacher/studio/media/",
            {"kind": "image", "file": SimpleUploadedFile("x.svg", b"<svg/>", content_type="image/svg+xml")},
            format="multipart",
        )
        assert bad.status_code == 400 and bad.data["code"] == "bad_media_type"
        blocks = [{"type": "short", "section": "GENERAL", "image_path": "../../etc/passwd", "questions": []}]
        res = api.post("/api/v1/teacher/studio/tests/", _payload(blocks), format="json")
        assert res.status_code == 400 and res.data["code"] == "bad_media_path"

    def test_teacher_cannot_touch_another_teachers_test(self, api):
        test_id = api.post("/api/v1/teacher/studio/tests/", _payload(), format="json").data["test"]["id"]
        other = _client(_user("t2@studio.test", "teacher"))
        assert other.get(f"/api/v1/teacher/studio/tests/{test_id}/").status_code == 404
        assert other.post(f"/api/v1/teacher/studio/tests/{test_id}/publish/").status_code == 404
        assert other.get(f"/api/v1/teacher/studio/tests/{test_id}/analysis/").status_code == 404

    def test_rebuild_refused_once_students_answered(self, api):
        test_id = api.post("/api/v1/teacher/studio/tests/", _payload(), format="json").data["test"]["id"]
        TestAttempt.objects.create(test_id=test_id, student=_user("s1@studio.test", "student"))
        res = api.put(f"/api/v1/teacher/studio/tests/{test_id}/", _payload(), format="json")
        assert res.status_code == 409 and res.data["code"] == "has_attempts"


def _published(api) -> Test:
    test_id = api.post("/api/v1/teacher/studio/tests/", _payload(), format="json").data["test"]["id"]
    assert api.post(f"/api/v1/teacher/studio/tests/{test_id}/publish/").status_code == 200
    return Test.objects.get(id=test_id)


@pytest.mark.django_db
class TestAssignAndAnalysis:
    def test_assign_creates_homework_and_links(self, api, teacher):
        test = _published(api)
        group = StudentGroup.objects.create(teacher=teacher, name="9-A", subject="english")
        due = (timezone.now() + timedelta(days=3)).isoformat()
        res = api.post(f"/api/v1/teacher/studio/tests/{test.id}/assign/", {"group_id": group.id, "due_at": due}, format="json")
        assert res.status_code == 201, res.data
        assert res.data["tma_link"] == f"https://t.me/uz_essaygrader_bot?startapp=test_{test.id}"
        assert res.data["join_code"] == test.mock_code
        hw = Homework.objects.get(group=group, test=test)
        assert res.data["assignment"]["id"] == hw.id
        # Re-assigning updates the deadline instead of duplicating.
        later = (timezone.now() + timedelta(days=5)).isoformat()
        api.post(f"/api/v1/teacher/studio/tests/{test.id}/assign/", {"group_id": group.id, "due_at": later}, format="json")
        assert Homework.objects.filter(group=group, test=test).count() == 1

    def test_assign_validation(self, api, teacher):
        test = _published(api)
        mine = StudentGroup.objects.create(teacher=teacher, name="Mine")
        foreign = StudentGroup.objects.create(teacher=_user("t3@studio.test", "teacher"), name="Theirs")
        future = (timezone.now() + timedelta(days=1)).isoformat()
        past = (timezone.now() - timedelta(days=1)).isoformat()
        url = f"/api/v1/teacher/studio/tests/{test.id}/assign/"
        assert api.post(url, {"group_id": foreign.id, "due_at": future}, format="json").data["code"] == "group_not_found"
        assert api.post(url, {"group_id": mine.id, "due_at": past}, format="json").data["code"] == "due_in_past"
        assert api.post(url, {"group_id": mine.id, "due_at": "soon"}, format="json").data["code"] == "bad_due"
        draft_id = api.post("/api/v1/teacher/studio/tests/", _payload(), format="json").data["test"]["id"]
        res = api.post(f"/api/v1/teacher/studio/tests/{draft_id}/assign/", {"group_id": mine.id, "due_at": future}, format="json")
        assert res.data["code"] == "not_published"

    def test_second_group_members_get_access_to_students_only_test(self, api, teacher):
        test = _published(api)
        test.access_type = Test.AccessType.STUDENTS_ONLY
        test.save()
        g1 = StudentGroup.objects.create(teacher=teacher, name="G1")
        g2 = StudentGroup.objects.create(teacher=teacher, name="G2")
        s2 = _user("member2@studio.test", "student")
        g2.students.add(s2)
        outsider = _user("outsider@studio.test", "student")
        future = (timezone.now() + timedelta(days=2)).isoformat()
        for g in (g1, g2):
            api.post(f"/api/v1/teacher/studio/tests/{test.id}/assign/", {"group_id": g.id, "due_at": future}, format="json")
        test.refresh_from_db()
        assert test.assigned_group == g1
        assert StartAttemptService.execute(test_id=test.id, student=s2) is not None
        # outsider: teacher's groups do not include them
        with pytest.raises(test_services.TestAccessDeniedError):
            StartAttemptService.execute(test_id=test.id, student=outsider)

    def test_item_analysis_from_real_attempts(self, api, teacher):
        test = _published(api)
        q1 = test.questions.get(config__number=1)
        q7 = test.questions.get(config__number=7)
        right = q1.choices.get(is_correct=True)
        wrong = q1.choices.filter(is_correct=False).first()
        students = [_user(f"st{i}@studio.test", "student") for i in range(5)]
        for i, s in enumerate(students):
            att = StartAttemptService.execute(test_id=test.id, student=s)
            # Q1: only student 0 right (80% fail → flagged). Q7: all right.
            SaveAnswerService.execute(attempt_id=att.id, student=s, question_id=q1.id, choice_ids=[(right if i == 0 else wrong).id])
            SaveAnswerService.execute(attempt_id=att.id, student=s, question_id=q7.id, text_answer="Flowers")
            SubmitAttemptService.execute(attempt_id=att.id, student=s)
        # A teacher preview never counts.
        TestAttempt.objects.create(test=test, student=teacher, is_preview=True, status=TestAttempt.Status.COMPLETED)

        res = api.get(f"/api/v1/teacher/studio/tests/{test.id}/analysis/")
        assert res.status_code == 200
        assert res.data["students"] == 5
        items = {i["number"]: i for i in res.data["items"]}
        assert items[1]["correct"] == 1 and items[1]["accuracy"] == 20.0 and items[1]["flagged"] is True
        assert items[7]["accuracy"] == 100.0 and items[7]["flagged"] is False
        assert items[3]["answered"] == 0 and items[3]["flagged"] is True  # nobody answered
        assert sum(b["count"] for b in res.data["distribution"]) == 5
        assert len(res.data["matrix"]) == 5
        assert len(res.data["matrix"][0]["cells"]) == len(res.data["items"])

    def test_item_analysis_group_filter_and_empty_state(self, api, teacher):
        test = _published(api)
        group = StudentGroup.objects.create(teacher=teacher, name="Empty")
        res = api.get(f"/api/v1/teacher/studio/tests/{test.id}/analysis/?group={group.id}")
        assert res.status_code == 200
        assert res.data["students"] == 0 and res.data["average"] is None
        assert all(i["accuracy"] is None and not i["flagged"] for i in res.data["items"])

    def test_test_detail_reports_cd_engine(self, api):
        test = _published(api)
        student = _user("viewer@studio.test", "student")
        res = _client(student).get(f"/api/tests/{test.id}/")
        assert res.status_code == 200
        assert res.data["has_cd_structure"] is True

    def test_choice_keys_never_reach_students(self, api):
        test = _published(api)
        student = _user("leak@studio.test", "student")
        att = StartAttemptService.execute(test_id=test.id, student=student)
        res = _client(student).get(f"/api/tests/attempts/{att.id}/")
        assert res.status_code == 200
        body = str(res.data)
        assert "is_correct" not in body and "nectar" not in body
        assert Choice.objects.filter(question__test=test, is_correct=True).count() == 6


@pytest.mark.django_db
def test_non_studio_test_is_never_rebuilt(api, teacher):
    """A legacy/imported test opened in the Studio must not lose its questions."""
    from apps.tests.mock_service import _get_or_create_mock_course

    legacy = Test.objects.create(course=_get_or_create_mock_course(teacher), created_by=teacher, title="Old")
    q = Question.objects.create(test=legacy, text="Legacy?", question_type="single", position=1)
    res = api.put(f"/api/v1/teacher/studio/tests/{legacy.id}/", _payload(), format="json")
    assert res.status_code == 409 and res.data["code"] == "not_studio"
    assert Question.objects.filter(id=q.id).exists()
    detail = api.get(f"/api/v1/teacher/studio/tests/{legacy.id}/").data["test"]
    assert detail["is_studio"] is False and detail["editable"] is False
    listed = {t["id"]: t for t in api.get("/api/v1/teacher/studio/tests/").data}
    assert listed[legacy.id]["is_studio"] is False
