"""Teacher Studio — save, validate, publish, assign and analyse tests.

Editor blocks map onto the existing CD-format models, no new tables:

    block            → ExamPart + QuestionGroup (one each), inside an ExamSection
    block.passage    → ReadingPassage (shared when several blocks use the same text)
    block.audio_path → ExamPart.audio      block.image_path → QuestionGroup.image
    mcq / matching   → Question(MULTIPLE_CHOICE / MATCHING) + Choice rows
    tfng             → Question(TRUE_FALSE_NOT_GIVEN) + 3 Choice rows
    gap / short      → Question(INLINE_GAP_FILL) + GapBlank rows (one per accepted answer)

Studio tests therefore run on the same CD exam engine (and the same scoring)
as the imported mocks. Assignment reuses ``courses.Homework``.
"""

from __future__ import annotations

import re
import secrets
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from django.conf import settings
from django.core.files.storage import default_storage
from django.db import transaction
from django.utils import timezone

from apps.accounts.access import is_platform_admin
from apps.tests.models import (
    Choice,
    ExamPart,
    ExamSection,
    GapBlank,
    Question,
    QuestionGroup,
    ReadingPassage,
    StudentAnswer,
    Test,
    TestAttempt,
)
from apps.tests.studio_parser import (
    BLOCK_TYPES,
    LETTERS,
    SECTIONS,
    TF_LABELS,
    YN_LABELS,
    GAP_RE,
    gap_context,
    gap_sentence,
    normalize_letter,
    normalize_tf,
)

MAX_BLOCKS = 60
MAX_QUESTIONS = 300
MAX_OPTIONS = 12
AUDIO_EXTS = {".mp3", ".m4a", ".wav", ".ogg"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}  # no SVG: it can carry scripts
MAX_AUDIO_BYTES = 40 * 1024 * 1024
MAX_IMAGE_BYTES = 5 * 1024 * 1024
AUDIO_PREFIX = "exams/audio/"
IMAGE_PREFIX = "exams/images/"
STUDIO_SUBJECTS = {"uzbek", "english", "biology", "chemistry", "law"}
SECTION_NAMES = {"GENERAL": "Test", "READING": "Reading", "LISTENING": "Listening"}
FLAG_FAIL_RATE = 60.0  # item flagged when more than this % of students failed it
TYPE_TO_QTYPE = {
    "mcq": Question.QuestionType.MULTIPLE_CHOICE,
    "tfng": Question.QuestionType.TRUE_FALSE_NOT_GIVEN,
    "matching": Question.QuestionType.MATCHING,
    "gap": Question.QuestionType.INLINE_GAP_FILL,
    "short": Question.QuestionType.INLINE_GAP_FILL,
}


class StudioError(ValueError):
    """Bad input. ``code`` is machine-readable; the UI translates it."""

    def __init__(self, code: str, message: str = "", **extra: Any) -> None:
        super().__init__(message or code)
        self.code = code
        self.extra = extra


class StudioConflict(StudioError):
    """The test can no longer be rebuilt (students already answered it)."""


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------
def is_teacher(user) -> bool:
    return bool(
        user
        and user.is_authenticated
        and user.is_active
        and (getattr(user, "role", None) == "teacher" or is_platform_admin(user))
    )


def owns_test(user, test: Test) -> bool:
    if is_platform_admin(user):
        return True
    if test.created_by_id == user.id:
        return True
    course = getattr(test, "course", None)
    return bool(course and course.teacher_id == user.id)


def teacher_tests(user):
    qs = Test.objects.all()
    if not is_platform_admin(user):
        qs = qs.filter(created_by=user)
    return qs


def real_attempts(test: Test):
    """Attempts that count: finished, not teacher previews."""
    return TestAttempt.objects.filter(
        test=test,
        is_preview=False,
        status__in=[TestAttempt.Status.COMPLETED, TestAttempt.Status.TIMEOUT, TestAttempt.Status.PENDING_GRADING],
    )


# ---------------------------------------------------------------------------
# Block normalisation
# ---------------------------------------------------------------------------
def _s(value: Any, limit: int = 5000) -> str:
    return str(value if value is not None else "").replace("\r\n", "\n").strip()[:limit]


def _media_path(value: Any, prefix: str) -> str:
    path = _s(value, 300).lstrip("/")
    if not path:
        return ""
    if ".." in path or "\\" in path or not path.startswith(prefix):
        raise StudioError("bad_media_path")
    if not default_storage.exists(path):
        raise StudioError("media_not_found")
    return path


def normalize_blocks(raw_blocks: Any) -> list[dict[str, Any]]:
    """Clean editor blocks. Gap questions are always re-derived from the gap text."""
    if not isinstance(raw_blocks, list):
        raise StudioError("blocks_required")
    if len(raw_blocks) > MAX_BLOCKS:
        raise StudioError("too_many_blocks")
    blocks: list[dict[str, Any]] = []
    total_questions = 0
    for raw in raw_blocks:
        if not isinstance(raw, dict):
            raise StudioError("bad_block")
        btype = raw.get("type")
        if btype not in BLOCK_TYPES:
            raise StudioError("bad_block_type")
        section = raw.get("section") if raw.get("section") in SECTIONS else "GENERAL"
        raw_qs = raw.get("questions") if isinstance(raw.get("questions"), list) else []
        block = {
            "type": btype,
            "section": section,
            "title": _s(raw.get("title"), 255),
            "instructions": _s(raw.get("instructions"), 3000),
            "passage": _s(raw.get("passage"), 30000),
            "gap_text": _s(raw.get("gap_text"), 30000),
            "audio_path": _media_path(raw.get("audio_path"), AUDIO_PREFIX),
            "image_path": _media_path(raw.get("image_path"), IMAGE_PREFIX),
            "options": [_s(o, 500) for o in (raw.get("options") or [])][:MAX_OPTIONS]
            if isinstance(raw.get("options"), list)
            else [],
            "questions": [],
        }
        if btype == "tfng":
            block["options"] = list(YN_LABELS if block["options"][:1] == ["YES"] else TF_LABELS)
        if btype == "gap":
            by_number = {}
            for q in raw_qs:
                if isinstance(q, dict):
                    try:
                        by_number[int(q.get("number"))] = _s(q.get("answer"), 500)
                    except (TypeError, ValueError):
                        continue
            for m in GAP_RE.finditer(block["gap_text"]):
                num = int(m.group(1))
                block["questions"].append(
                    {
                        "number": num,
                        "text": gap_sentence(block["gap_text"], num),
                        "options": [],
                        "answer": by_number.get(num) or _s(m.group(2), 500),
                    }
                )
        else:
            for q in raw_qs:
                if not isinstance(q, dict):
                    raise StudioError("bad_question")
                try:
                    number = int(q.get("number"))
                except (TypeError, ValueError):
                    raise StudioError("bad_question_number") from None
                if not 1 <= number <= 999:
                    raise StudioError("bad_question_number")
                opts = q.get("options") if btype == "mcq" and isinstance(q.get("options"), list) else []
                block["questions"].append(
                    {
                        "number": number,
                        "text": _s(q.get("text"), 3000),
                        "options": [_s(o, 500) for o in opts][:MAX_OPTIONS],
                        "answer": _s(q.get("answer"), 500),
                    }
                )
        total_questions += len(block["questions"])
        blocks.append(block)
    if total_questions > MAX_QUESTIONS:
        raise StudioError("too_many_questions")
    return blocks


def _answers(value: str) -> list[str]:
    return [a.strip() for a in value.split("|") if a.strip()]


def validate_blocks(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every problem that must be fixed before publishing, one entry each.

    ``{"block": i, "number": n | None, "option": k | None, "code": ...}``
    """
    issues: list[dict[str, Any]] = []

    def add(block: int, code: str, number: int | None = None, option: int | None = None) -> None:
        issues.append({"block": block, "number": number, "option": option, "code": code})

    if not blocks:
        add(-1, "no_blocks")
    seen: dict[int, int] = {}
    for bi, b in enumerate(blocks):
        if not b["questions"]:
            add(bi, "gap_no_markers" if b["type"] == "gap" else "no_questions")
        if b["section"] == "LISTENING" and not b["audio_path"]:
            add(bi, "audio_missing")
        if b["type"] == "matching":
            if len(b["options"]) < 2:
                add(bi, "too_few_options")
            for oi, opt in enumerate(b["options"]):
                if not opt:
                    add(bi, "empty_option", option=oi)
        for q in b["questions"]:
            n = q["number"]
            if n in seen:
                add(bi, "duplicate_number", n)
            seen[n] = bi
            if b["type"] not in ("gap",) and not q["text"]:
                add(bi, "empty_question", n)
            if b["type"] == "mcq":
                if len(q["options"]) < 2:
                    add(bi, "too_few_options", n)
                for oi, opt in enumerate(q["options"]):
                    if not opt:
                        add(bi, "empty_option", n, oi)
                if not normalize_letter(q["answer"], len(q["options"])):
                    add(bi, "missing_answer", n)
            elif b["type"] == "matching":
                if not normalize_letter(q["answer"], len(b["options"])):
                    add(bi, "missing_answer", n)
            elif b["type"] == "tfng":
                if not normalize_tf(q["answer"], b["options"]):
                    add(bi, "missing_answer", n)
            elif not _answers(q["answer"]):
                add(bi, "missing_answer", n)
    return issues


# ---------------------------------------------------------------------------
# Save / load
# ---------------------------------------------------------------------------
@dataclass
class TestMeta:
    title: str
    subject: str
    time_limit_minutes: int
    description: str


def _meta(payload: dict[str, Any]) -> TestMeta:
    title = _s(payload.get("title"), 255)
    if not title:
        raise StudioError("title_required")
    subject = _s(payload.get("subject"), 20).lower() or "uzbek"
    if subject not in STUDIO_SUBJECTS:
        raise StudioError("bad_subject")
    try:
        minutes = int(payload.get("time_limit_minutes") or 0)
    except (TypeError, ValueError):
        raise StudioError("bad_time_limit") from None
    if not 0 <= minutes <= 600:
        raise StudioError("bad_time_limit")
    return TestMeta(title, subject, minutes, _s(payload.get("description"), 2000))


def is_studio_test(test: Test) -> bool:
    """Every question was written by the Studio (an empty test counts too)."""
    return not test.questions.exclude(config__has_key="studio_type").exists()


def has_real_answers(test: Test) -> bool:
    return TestAttempt.objects.filter(test=test, is_preview=False).exists()


def _clear_content(test: Test) -> None:
    # Preview attempts only (checked by the caller): their answers go with the questions.
    TestAttempt.objects.filter(test=test, is_preview=True).delete()
    test.questions.all().delete()
    test.passages.all().delete()
    test.sections.all().delete()  # cascades parts and groups


def _build_content(test: Test, blocks: list[dict[str, Any]]) -> None:
    sections: dict[str, ExamSection] = {}
    part_counter: dict[str, int] = defaultdict(int)
    passages: dict[str, ReadingPassage] = {}
    order = {code: i for i, code in enumerate(SECTIONS, start=1)}

    for bi, b in enumerate(blocks, start=1):
        code = b["section"]
        section = sections.get(code)
        if section is None:
            section = ExamSection.objects.create(
                test=test, code=code, name=SECTION_NAMES[code], order=order[code]
            )
            sections[code] = section
        part_counter[code] += 1
        part = ExamPart.objects.create(
            section=section,
            number=str(part_counter[code]),
            title=b["title"],
            order=bi,
        )
        if b["audio_path"]:
            part.audio.name = b["audio_path"]
            part.save(update_fields=["audio"])

        passage_text = b["passage"]
        if b["type"] == "gap":
            passage_text = "\n\n".join(p for p in (b["passage"], gap_context(b["gap_text"])) if p)
        passage = None
        if passage_text:
            passage = passages.get(passage_text)
            if passage is None:
                passage = ReadingPassage.objects.create(
                    test=test, section=section, title=b["title"], content=passage_text, order=bi
                )
                passages[passage_text] = passage

        group = QuestionGroup.objects.create(
            part=part,
            title=b["title"],
            instructions=b["instructions"],
            passage=passage,
            # The exam screen lists shared matching options only under a label.
            options_label=f"A–{LETTERS[len(b['options']) - 1]}" if b["type"] == "matching" and b["options"] else "",
            each_option_once=False,
            order=1,
        )
        if b["image_path"]:
            group.image.name = b["image_path"]
            group.save(update_fields=["image"])

        for qi, q in enumerate(b["questions"]):
            config: dict[str, Any] = {"number": q["number"], "studio_type": b["type"]}
            if b["type"] == "gap" and qi == 0:
                # Answers stripped: Question.config is sent to students as-is.
                config["studio_gap_text"] = GAP_RE.sub(lambda m: f"[{m.group(1)}]", b["gap_text"])
            question = Question.objects.create(
                test=test,
                section=section,
                group=group,
                reading_passage=passage,
                text=q["text"],
                question_type=TYPE_TO_QTYPE[b["type"]],
                points=1,
                position=section.order * 1000 + q["number"],
                config=config,
            )
            if b["type"] == "mcq":
                correct = normalize_letter(q["answer"], len(q["options"]))
                _choices(question, q["options"], LETTERS.index(correct) if correct else -1)
            elif b["type"] == "matching":
                correct = normalize_letter(q["answer"], len(b["options"]))
                _choices(question, b["options"], LETTERS.index(correct) if correct else -1)
            elif b["type"] == "tfng":
                label = normalize_tf(q["answer"], b["options"])
                _choices(question, b["options"], b["options"].index(label) if label else -1)
            else:
                GapBlank.objects.bulk_create(
                    GapBlank(question=question, position=0, answer_text=a[:200]) for a in _answers(q["answer"])
                )


def _choices(question: Question, options: list[str], correct_index: int) -> None:
    seen: set[str] = set()
    rows = []
    for i, text in enumerate(options):
        # Choice(question, text) is unique: a repeated (or empty) option keeps its
        # slot via trailing spaces, which load_blocks strips again. Empty options
        # only exist in drafts: publish validation rejects them.
        label = text
        while label in seen:
            label = f"{label} "
        seen.add(label)
        rows.append(Choice(question=question, text=label[:500], is_correct=i == correct_index, position=i + 1))
    Choice.objects.bulk_create(rows)


@transaction.atomic
def save_test(user, payload: dict[str, Any], test: Test | None = None) -> Test:
    """Create or rebuild a Studio test as a DRAFT (publish is a separate step)."""
    meta = _meta(payload)
    blocks = normalize_blocks(payload.get("blocks"))
    if test is not None:
        test = Test.objects.select_for_update().get(pk=test.pk)
        if not is_studio_test(test):
            # Legacy / imported tests hold types the Studio cannot rebuild.
            raise StudioConflict("not_studio")
        if has_real_answers(test):
            raise StudioConflict("has_attempts")
        _clear_content(test)
        test.title = meta.title
        test.subject = meta.subject
        test.time_limit_minutes = meta.time_limit_minutes
        test.description = meta.description
        test.status = Test.Status.DRAFT
        test.save()
    else:
        from apps.tests.mock_service import _get_or_create_mock_course

        test = Test.objects.create(
            course=_get_or_create_mock_course(user),
            created_by=user,
            title=meta.title,
            subject=meta.subject,
            exam_type=Test.ExamType.GENERAL,
            scoring_type=Test.ScoringType.STANDARD,
            time_limit_minutes=meta.time_limit_minutes,
            description=meta.description,
            max_attempts=1,
            shuffle_choices=False,
            status=Test.Status.DRAFT,
        )
    _build_content(test, blocks)
    return test


@transaction.atomic
def publish_test(test: Test) -> tuple[bool, list[dict[str, Any]]]:
    """Publish when the saved content validates; otherwise return the issues."""
    test = Test.objects.select_for_update().get(pk=test.pk)
    issues = validate_blocks(load_blocks(test))
    if issues:
        return False, issues
    if not test.mock_code:
        from apps.tests.mock_service import generate_unique_mock_code

        test.mock_code = generate_unique_mock_code()
    test.status = Test.Status.PUBLISHED
    test.save()
    return True, []


def _media_url(field) -> str:
    try:
        return field.url if field else ""
    except ValueError:
        return ""


def load_blocks(test: Test) -> list[dict[str, Any]]:
    """Rebuild editor blocks from the saved CD structure (inverse of ``_build_content``)."""
    blocks: list[dict[str, Any]] = []
    questions = (
        test.questions.select_related("group", "reading_passage")
        .prefetch_related("choices", "gap_blanks")
        .order_by("position")
    )
    by_group: dict[int | None, list[Question]] = defaultdict(list)
    for q in questions:
        by_group[q.group_id].append(q)

    parts = (
        ExamPart.objects.filter(section__test=test)
        .select_related("section")
        .prefetch_related("groups__passage")
        .order_by("order", "id")
    )
    for part in parts:
        for group in part.groups.all():
            qs = by_group.get(group.id, [])
            btype = next((q.config.get("studio_type") for q in qs if q.config.get("studio_type")), None)
            if btype is None:
                btype = _infer_type(qs)
            block: dict[str, Any] = {
                "type": btype,
                "section": part.section.code if part.section.code in SECTIONS else "GENERAL",
                "title": group.title or part.title,
                "instructions": group.instructions,
                "passage": "",
                "gap_text": "",
                "audio_path": part.audio.name if part.audio else "",
                "audio_url": _media_url(part.audio),
                "image_path": group.image.name if group.image else "",
                "image_url": _media_url(group.image),
                "options": [],
                "questions": [],
            }
            passage = group.passage.content if group.passage else ""
            if btype == "gap":
                stored = next((q.config.get("studio_gap_text") for q in qs if q.config.get("studio_gap_text")), "")
                if stored:
                    # The stored template has bare "[n]" markers (config reaches
                    # students); the accepted answers come back from GapBlank.
                    alts_by_number = {
                        q.config.get("number"): "|".join(g.answer_text for g in q.gap_blanks.all()) for q in qs
                    }

                    def _fill(m: re.Match[str]) -> str:
                        alts = alts_by_number.get(int(m.group(1)), "")
                        return f"[{m.group(1)}:{alts}]" if alts else f"[{m.group(1)}]"

                    block["gap_text"] = GAP_RE.sub(_fill, stored)
                    ctx = gap_context(stored)
                    block["passage"] = passage[: len(passage) - len(ctx)].strip() if ctx and passage.endswith(ctx) else passage
                else:  # gap group not made in the Studio: one line per gap
                    lines = [passage] if passage else []
                    for q in qs:
                        num = q.config.get("number")
                        alts = "|".join(g.answer_text for g in q.gap_blanks.all())
                        lines.append(re.sub(r"\(\d+\)\s*_{2,}", f"[{num}:{alts}]", q.text, count=1))
                    block["gap_text"] = "\n".join(lines)
            else:
                block["passage"] = passage
            for q in qs:
                choices = sorted(q.choices.all(), key=lambda c: c.position)
                num = q.config.get("number") or q.position
                answer = ""
                if btype in ("mcq", "matching"):
                    idx = next((i for i, c in enumerate(choices) if c.is_correct), -1)
                    answer = LETTERS[idx] if idx >= 0 else ""
                elif btype == "tfng":
                    answer = next((c.text for c in choices if c.is_correct), "")
                else:
                    answer = "|".join(g.answer_text for g in q.gap_blanks.all())
                if btype in ("matching", "tfng") and not block["options"]:
                    block["options"] = [c.text.strip() for c in choices]
                block["questions"].append(
                    {
                        "number": num,
                        "text": q.text,
                        "options": [c.text.strip() for c in choices] if btype == "mcq" else [],
                        "answer": answer,
                    }
                )
            if btype == "gap":
                block["questions"] = normalize_blocks([{**block, "audio_path": "", "image_path": ""}])[0][
                    "questions"
                ]
            blocks.append(block)
    return blocks


def _infer_type(qs: list[Question]) -> str:
    qtypes = {q.question_type for q in qs}
    if Question.QuestionType.TRUE_FALSE_NOT_GIVEN in qtypes:
        return "tfng"
    if qtypes & {Question.QuestionType.MATCHING, Question.QuestionType.MAP_LABELING, Question.QuestionType.HEADING_MATCHING}:
        return "matching"
    if qtypes & {Question.QuestionType.INLINE_GAP_FILL, Question.QuestionType.GAP_FILL}:
        return "gap"
    return "mcq"


def summarize_test(test: Test) -> dict[str, Any]:
    return {
        "id": test.id,
        "title": test.title,
        "subject": test.subject,
        "status": test.status,
        "time_limit_minutes": test.time_limit_minutes,
        "mock_code": test.mock_code or "",
        "access_pin": test.access_pin or "",
        "description": test.description,
        "editable": is_studio_test(test) and not has_real_answers(test),
        "is_studio": is_studio_test(test),
        "updated_at": test.updated_at.isoformat() if test.updated_at else None,
    }


# ---------------------------------------------------------------------------
# Media
# ---------------------------------------------------------------------------
def store_media(upload, kind: str) -> dict[str, str]:
    import os

    name = getattr(upload, "name", "") or ""
    ext = os.path.splitext(name)[1].lower()
    if kind == "audio":
        allowed, limit, prefix = AUDIO_EXTS, MAX_AUDIO_BYTES, AUDIO_PREFIX
    elif kind == "image":
        allowed, limit, prefix = IMAGE_EXTS, MAX_IMAGE_BYTES, IMAGE_PREFIX
    else:
        raise StudioError("bad_media_kind")
    if ext not in allowed:
        raise StudioError("bad_media_type")
    if (getattr(upload, "size", 0) or 0) > limit:
        raise StudioError("media_too_large")
    path = default_storage.save(f"{prefix}studio/{secrets.token_hex(12)}{ext}", upload)
    return {"path": path, "url": default_storage.url(path)}


# ---------------------------------------------------------------------------
# Assignment (courses.Homework)
# ---------------------------------------------------------------------------
def teacher_groups(user):
    from apps.courses.models import StudentGroup

    if is_platform_admin(user):
        return StudentGroup.objects.all()
    return StudentGroup.objects.filter(teacher=user)


def bot_username() -> str:
    return getattr(settings, "TELEGRAM_BOT_NAME", "") or "uz_essaygrader_bot"


def share_links(test: Test) -> dict[str, str]:
    return {
        "join_code": test.mock_code or "",
        "access_pin": test.access_pin or "",
        "tma_link": f"https://t.me/{bot_username()}?startapp=test_{test.id}",
        "web_path": f"/tests/{test.id}",
    }


def _parse_due(value: Any) -> datetime:
    raw = _s(value, 40)
    if not raw:
        raise StudioError("due_required")
    try:
        due = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        raise StudioError("bad_due") from None
    if timezone.is_naive(due):
        due = timezone.make_aware(due, timezone.get_current_timezone())
    if due <= timezone.now():
        raise StudioError("due_in_past")
    return due


@transaction.atomic
def assign_test(user, test: Test, group_id: Any, due_at: Any) -> dict[str, Any]:
    from apps.courses.models import Homework

    if test.status != Test.Status.PUBLISHED:
        raise StudioError("not_published")
    from apps.courses.models import StudentGroup

    try:
        group = teacher_groups(user).get(id=int(group_id))
    except (TypeError, ValueError, StudentGroup.DoesNotExist):
        raise StudioError("group_not_found") from None
    due = _parse_due(due_at)
    homework, _created = Homework.objects.update_or_create(
        group=group,
        test=test,
        defaults={"title": test.title[:200], "due_date": due, "created_by": user},
    )
    update_fields = []
    if test.assigned_group_id is None:
        test.assigned_group = group
        update_fields.append("assigned_group")
    if not test.mock_code:
        from apps.tests.mock_service import generate_unique_mock_code

        test.mock_code = generate_unique_mock_code()
        update_fields.append("mock_code")
    if update_fields:
        test.save(update_fields=update_fields)
    return {"assignment": assignment_payload(homework), **share_links(test)}


def assignment_payload(hw) -> dict[str, Any]:
    return {
        "id": hw.id,
        "group_id": hw.group_id,
        "group_name": hw.group.name,
        "student_count": hw.group.students.count(),
        "due_at": hw.due_date.isoformat(),
    }


def assignments_for(test: Test) -> list[dict[str, Any]]:
    from apps.courses.models import Homework

    return [
        assignment_payload(hw)
        for hw in Homework.objects.filter(test=test).select_related("group").order_by("due_date")
    ]


def student_has_assignment(student, test: Test) -> bool:
    """A student in any group the test is assigned to (Homework) may take it."""
    from apps.courses.models import Homework

    return Homework.objects.filter(test=test, group__students=student).exists()


# ---------------------------------------------------------------------------
# Item analysis (real attempts only)
# ---------------------------------------------------------------------------
def item_analysis(test: Test, group=None) -> dict[str, Any]:
    """Per-question accuracy over each student's latest finished attempt."""
    attempts = real_attempts(test).select_related("student").order_by("student_id", "-started_at")
    if group is not None:
        attempts = attempts.filter(student__in=group.students.all())
    latest: dict[int, TestAttempt] = {}
    for att in attempts:
        latest.setdefault(att.student_id, att)
    attempt_list = list(latest.values())
    n = len(attempt_list)

    questions = list(
        test.questions.exclude(question_type__in=["SPEAKING_PROMPT", "written"]).order_by("position")
    )
    correct_map: dict[tuple[int, int], bool | None] = {}
    for ans in StudentAnswer.objects.filter(attempt__in=attempt_list).only("attempt_id", "question_id", "is_correct"):
        correct_map[(ans.attempt_id, ans.question_id)] = ans.is_correct

    items = []
    for idx, q in enumerate(questions, start=1):
        correct = sum(1 for a in attempt_list if correct_map.get((a.id, q.id)) is True)
        answered = sum(1 for a in attempt_list if (a.id, q.id) in correct_map)
        accuracy = round(correct / n * 100, 1) if n else None
        items.append(
            {
                "question_id": q.id,
                "number": q.config.get("number") or idx,
                "text": q.text[:160],
                "question_type": q.question_type,
                "correct": correct,
                "answered": answered,
                "total": n,
                "accuracy": accuracy,
                "flagged": bool(n) and accuracy is not None and (100 - accuracy) > FLAG_FAIL_RATE,
            }
        )

    percentages = [float(a.percentage) for a in attempt_list]
    buckets = [0] * 10
    for p in percentages:
        buckets[min(int(p // 10), 9)] += 1

    rows = []
    for a in sorted(attempt_list, key=lambda x: (-float(x.percentage), x.student_id))[:200]:
        student = a.student
        rows.append(
            {
                "attempt_id": a.id,
                "student": student.get_full_name() or getattr(student, "username", "") or student.email,
                "percentage": float(a.percentage),
                "cells": [
                    (None if (a.id, q.id) not in correct_map else bool(correct_map[(a.id, q.id)]))
                    for q in questions
                ],
            }
        )

    return {
        "test_id": test.id,
        "title": test.title,
        "students": n,
        "flag_threshold": FLAG_FAIL_RATE,
        "average": round(statistics.fmean(percentages), 1) if percentages else None,
        "median": round(statistics.median(percentages), 1) if percentages else None,
        "distribution": [{"from": i * 10, "to": i * 10 + 10, "count": c} for i, c in enumerate(buckets)],
        "items": items,
        "matrix": rows,
    }
