"""Schema 1.0 JSON Exam Package validate, import, keyless template export & mock readiness."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from django.db import transaction

from apps.tests.models import (
    Choice,
    ExamPart,
    ExamSection,
    GapBlank,
    Question,
    QuestionGroup,
    ReadingPassage,
    Test,
)

SCHEMA_VERSION = "1.0"
MAX_PACKAGE_BYTES = 2 * 1024 * 1024  # 2 MiB hard guard
VALID_SECTIONS = {"LISTENING", "READING", "WRITING", "SPEAKING", "GENERAL"}
VALID_LAYOUTS = {"table", "notes", "summary", "flow", "passage", "map", "matching", ""}

TYPE_MAP = {
    "SINGLE": Question.QuestionType.SINGLE_CHOICE,
    "SINGLE_CHOICE": Question.QuestionType.SINGLE_CHOICE,
    "MCQ": Question.QuestionType.MULTIPLE_CHOICE,
    "MULTIPLE": Question.QuestionType.MULTIPLE_CHOICE,
    "MULTIPLE_CHOICE": Question.QuestionType.MULTIPLE_CHOICE,
    "TFNG": Question.QuestionType.TRUE_FALSE_NOT_GIVEN,
    "TRUE_FALSE_NOT_GIVEN": Question.QuestionType.TRUE_FALSE_NOT_GIVEN,
    "GAP": Question.QuestionType.INLINE_GAP_FILL,
    "GAP_FILL": Question.QuestionType.INLINE_GAP_FILL,
    "INLINE_GAP_FILL": Question.QuestionType.INLINE_GAP_FILL,
    "SHORT": Question.QuestionType.SHORT_ANSWER,
    "SHORT_ANSWER": Question.QuestionType.SHORT_ANSWER,
    "MATCHING": Question.QuestionType.MATCHING,
    "HEADING_MATCHING": Question.QuestionType.HEADING_MATCHING,
    "MAP_LABELING": Question.QuestionType.MAP_LABELING,
    "WRITTEN": Question.QuestionType.WRITTEN,
    "SPEAKING_PROMPT": Question.QuestionType.SPEAKING_PROMPT,
}


class PackageValidationError(ValueError):
    """Raised when an imported Schema 1.0 exam package fails validation."""

    def __init__(self, errors: list[dict[str, Any]]) -> None:
        self.errors = errors
        super().__init__(errors[0]["message"] if errors else "Invalid exam package")


def _package_size_bytes(payload: Any) -> int:
    try:
        return len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    except Exception:
        return MAX_PACKAGE_BYTES + 1


def _resolve_qtype(raw: Any) -> str:
    norm = str(raw or "MULTIPLE_CHOICE").strip().upper()
    return TYPE_MAP.get(norm, Question.QuestionType.SINGLE_CHOICE)


def validate_exam_package(
    payload: Any,
    *,
    allow_keyless: bool = False,
) -> dict[str, Any]:
    """Validate a Schema 1.0 JSON exam package without mutating database state."""
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    if not isinstance(payload, dict):
        return {
            "valid": False,
            "errors": [{"path": "$", "code": "invalid_json_object", "message": "Package must be a JSON object."}],
            "warnings": [],
            "summary": {"sections": 0, "parts": 0, "questions": 0, "is_keyless": False},
        }

    if _package_size_bytes(payload) > MAX_PACKAGE_BYTES:
        return {
            "valid": False,
            "errors": [{"path": "$", "code": "package_too_large", "message": "Exam JSON exceeds 2 MiB limit."}],
            "warnings": [],
            "summary": {"sections": 0, "parts": 0, "questions": 0, "is_keyless": False},
        }

    if str(payload.get("schemaVersion") or "") != SCHEMA_VERSION:
        errors.append({
            "path": "schemaVersion",
            "code": "unsupported_schema_version",
            "message": f"schemaVersion must be '{SCHEMA_VERSION}'.",
        })

    title = str(payload.get("title") or "").strip()
    if not title:
        errors.append({"path": "title", "code": "title_required", "message": "Test title is required."})

    sections = payload.get("sections")
    if not isinstance(sections, list) or not sections:
        errors.append({"path": "sections", "code": "sections_required", "message": "At least one section is required."})
        return {
            "valid": False,
            "errors": errors,
            "warnings": warnings,
            "summary": {"sections": 0, "parts": 0, "questions": 0, "is_keyless": False},
        }

    total_parts = 0
    total_questions = 0
    keyless_detected = bool(payload.get("isTemplate"))
    stimulus_texts: dict[str, str] = {}

    for si, sec in enumerate(sections):
        if not isinstance(sec, dict):
            errors.append({"path": f"sections[{si}]", "code": "invalid_section", "message": "Section must be an object."})
            continue
        code = str(sec.get("code") or "GENERAL").strip().upper()
        if code not in VALID_SECTIONS:
            warnings.append({"path": f"sections[{si}].code", "code": "non_standard_section", "message": f"Section '{code}' is non-standard."})
        parts = sec.get("parts") or []
        if not isinstance(parts, list) or not parts:
            errors.append({"path": f"sections[{si}].parts", "code": "parts_required", "message": "Each section must have parts."})
            continue
        for pi, part in enumerate(parts):
            total_parts += 1
            if not isinstance(part, dict):
                errors.append({"path": f"sections[{si}].parts[{pi}]", "code": "invalid_part", "message": "Part must be an object."})
                continue
            groups = part.get("groups") or []
            if not isinstance(groups, list) or not groups:
                errors.append({"path": f"sections[{si}].parts[{pi}].groups", "code": "groups_required", "message": "Each part must have groups."})
                continue
            for gi, grp in enumerate(groups):
                if not isinstance(grp, dict):
                    errors.append({"path": f"sections[{si}].parts[{pi}].groups[{gi}]", "code": "invalid_group", "message": "Group must be an object."})
                    continue
                layout = str(grp.get("contentLayout") or "").strip().lower()
                if layout and layout not in VALID_LAYOUTS:
                    warnings.append({"path": f"sections[{si}].parts[{pi}].groups[{gi}].contentLayout", "code": "unknown_layout", "message": f"Unknown contentLayout '{layout}'."})
                passage = grp.get("passage")
                if isinstance(passage, dict):
                    sref = str(passage.get("stimulusRef") or grp.get("stimulusRef") or "").strip()
                    p_content = str(passage.get("content") or "")
                    if sref:
                        if sref in stimulus_texts and stimulus_texts[sref] != p_content:
                            errors.append({
                                "path": f"sections[{si}].parts[{pi}].groups[{gi}].stimulusRef",
                                "code": "stimulus_ref_collision",
                                "message": f"stimulusRef '{sref}' refers to conflicting passage contents.",
                            })
                        else:
                            stimulus_texts[sref] = p_content
                questions = grp.get("questions") or []
                if not isinstance(questions, list) or not questions:
                    errors.append({"path": f"sections[{si}].parts[{pi}].groups[{gi}].questions", "code": "questions_required", "message": "Each group must contain questions."})
                    continue
                for qi, q in enumerate(questions):
                    total_questions += 1
                    if not isinstance(q, dict):
                        errors.append({"path": f"...questions[{qi}]", "code": "invalid_question", "message": "Question must be an object."})
                        continue
                    qtype = _resolve_qtype(q.get("questionType") or q.get("type"))
                    qtext = str(q.get("text") or "").strip()
                    if not qtext:
                        errors.append({"path": f"sections[{si}].parts[{pi}].groups[{gi}].questions[{qi}].text", "code": "question_text_required", "message": "Question text is required."})
                    if qtype in (Question.QuestionType.WRITTEN, Question.QuestionType.SPEAKING_PROMPT):
                        continue
                    is_gap = qtype in (Question.QuestionType.INLINE_GAP_FILL, Question.QuestionType.GAP_FILL, Question.QuestionType.SHORT_ANSWER)
                    if is_gap:
                        accepted = q.get("acceptedAnswers") or ([q.get("answer")] if q.get("answer") else [])
                        accepted = [str(a).strip() for a in accepted if str(a or "").strip()]
                        if not accepted:
                            keyless_detected = True
                            if not allow_keyless:
                                errors.append({"path": f"sections[{si}].parts[{pi}].groups[{gi}].questions[{qi}].acceptedAnswers", "code": "answer_required", "message": "Gap/short answer question requires at least one accepted answer."})
                    else:
                        options = q.get("options") or q.get("choices") or []
                        if not isinstance(options, list) or len(options) < 2:
                            errors.append({"path": f"sections[{si}].parts[{pi}].groups[{gi}].questions[{qi}].options", "code": "options_required", "message": "Choice question requires at least 2 options."})
                            continue
                        has_correct = any(isinstance(o, dict) and o.get("isCorrect") for o in options) or bool(q.get("answer") or q.get("correctAnswer"))
                        if not has_correct:
                            keyless_detected = True
                            if not allow_keyless:
                                errors.append({"path": f"sections[{si}].parts[{pi}].groups[{gi}].questions[{qi}].answer", "code": "answer_required", "message": "Answer key is required unless importing a keyless template."})

    if keyless_detected and not allow_keyless:
        warnings.append({"path": "$", "code": "keyless_template_needs_keys", "message": "Answer keys missing; cannot publish until keys are completed."})

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "summary": {
            "sections": len(sections),
            "parts": total_parts,
            "questions": total_questions,
            "is_keyless": keyless_detected,
        },
    }


@transaction.atomic
def import_exam_package(
    user: Any,
    payload: dict[str, Any],
    *,
    test: Test | None = None,
    allow_keyless: bool = False,
) -> Test:
    """Import a Schema 1.0 JSON exam package into DB as a DRAFT test."""
    validation = validate_exam_package(payload, allow_keyless=allow_keyless)
    if not validation["valid"]:
        raise PackageValidationError(validation["errors"])

    from apps.tests.mock_service import _get_or_create_mock_course

    subject = str(payload.get("subject") or "english").strip().lower()
    if subject not in {"uzbek", "english", "biology", "chemistry", "law"}:
        subject = "english"
    exam_type = str(payload.get("examType") or payload.get("exam_type") or Test.ExamType.GENERAL)
    if exam_type not in Test.ExamType.values:
        exam_type = Test.ExamType.GENERAL
    category = str(payload.get("assessmentCategory") or payload.get("assessment_category") or Test.AssessmentCategory.TOPIC_TEST)
    if category not in Test.AssessmentCategory.values:
        category = Test.AssessmentCategory.TOPIC_TEST

    is_keyless = bool(validation["summary"]["is_keyless"])
    if test is None:
        test = Test.objects.create(
            course=_get_or_create_mock_course(user),
            created_by=user,
            title=str(payload["title"]).strip()[:255],
            description=str(payload.get("description") or "").strip(),
            subject=subject,
            exam_type=exam_type,
            assessment_category=category,
            time_limit_minutes=max(0, int(payload.get("timeLimitMinutes") or payload.get("time_limit_minutes") or 0)),
            status=Test.Status.DRAFT,
            is_keyless=is_keyless,
            spec_version=str(payload.get("specVersion") or SCHEMA_VERSION)[:32],
            shuffle_choices=False,
            scoring_type=Test.ScoringType.STANDARD,
        )
    else:
        test.title = str(payload["title"]).strip()[:255]
        test.description = str(payload.get("description") or "").strip()
        test.subject = subject
        test.exam_type = exam_type
        test.assessment_category = category
        test.time_limit_minutes = max(0, int(payload.get("timeLimitMinutes") or payload.get("time_limit_minutes") or 0))
        test.status = Test.Status.DRAFT
        test.is_keyless = is_keyless
        test.content_version = int(test.content_version or 1) + 1
        test.sections.all().delete()
        test.passages.all().delete()
        test.questions.all().delete()
        test.save()

    passage_by_ref: dict[str, ReadingPassage] = {}
    q_counter = 0

    for s_idx, sec_raw in enumerate(payload.get("sections", []), start=1):
        sec_code = str(sec_raw.get("code") or "GENERAL").strip().upper()
        section = ExamSection.objects.create(
            test=test,
            code=sec_code,
            name=str(sec_raw.get("name") or sec_code.title()),
            audio_url=str(sec_raw.get("audioUrl") or sec_raw.get("audio_url") or ""),
            order=s_idx,
            duration_minutes=max(0, int(sec_raw.get("durationMinutes") or sec_raw.get("duration_minutes") or 0)),
        )
        for p_idx, part_raw in enumerate(sec_raw.get("parts", []), start=1):
            p_num_val = part_raw.get("partNumber")
            part = ExamPart.objects.create(
                section=section,
                number=str(part_raw.get("number") or p_num_val or p_idx)[:10],
                part_number=int(p_num_val) if str(p_num_val or "").isdigit() else p_idx,
                title=str(part_raw.get("title") or "")[:255],
                instructions=str(part_raw.get("instructions") or ""),
                audio_play_limit=max(0, int(part_raw.get("audioPlayLimit") or 0)),
                transcript=str(part_raw.get("transcript") or ""),
                order=p_idx,
            )
            if part_raw.get("audioUrl") and not section.audio_url:
                section.audio_url = str(part_raw["audioUrl"])
                section.save(update_fields=["audio_url"])

            for g_idx, grp_raw in enumerate(part_raw.get("groups", []), start=1):
                sref = str(grp_raw.get("stimulusRef") or "").strip()
                passage_obj = None
                p_raw = grp_raw.get("passage")
                if isinstance(p_raw, dict) and str(p_raw.get("content") or "").strip():
                    p_ref = str(p_raw.get("stimulusRef") or sref or f"__p_{s_idx}_{p_idx}_{g_idx}").strip()
                    passage_obj = passage_by_ref.get(p_ref)
                    if passage_obj is None:
                        passage_obj = ReadingPassage.objects.create(
                            test=test,
                            section=section,
                            title=str(p_raw.get("title") or grp_raw.get("title") or "")[:255],
                            content=str(p_raw.get("content") or ""),
                            stimulus_ref=p_ref if not p_ref.startswith("__p_") else "",
                            order=len(passage_by_ref) + 1,
                        )
                        passage_by_ref[p_ref] = passage_obj

                group = QuestionGroup.objects.create(
                    part=part,
                    title=str(grp_raw.get("title") or "")[:255],
                    instructions=str(grp_raw.get("instructions") or ""),
                    answer_rule=str(grp_raw.get("answerRule") or grp_raw.get("answer_rule") or "")[:120],
                    passage=passage_obj,
                    stimulus_ref=sref[:80],
                    content_layout=str(grp_raw.get("contentLayout") or "")[:32],
                    options_label=str(grp_raw.get("optionsLabel") or "")[:120],
                    each_option_once=bool(grp_raw.get("eachOptionOnce")),
                    order=g_idx,
                )

                for q_raw in grp_raw.get("questions", []):
                    q_counter += 1
                    qtype = _resolve_qtype(q_raw.get("questionType") or q_raw.get("type"))
                    pos = int(q_raw.get("position") or q_raw.get("number") or q_counter)
                    max_score_val = q_raw.get("maxScore")
                    question = Question.objects.create(
                        test=test,
                        section=section,
                        group=group,
                        reading_passage=passage_obj,
                        text=str(q_raw.get("text") or ""),
                        question_type=qtype,
                        points=max(1, int(q_raw.get("points") or 1)),
                        max_score=Decimal(str(max_score_val)) if max_score_val is not None else None,
                        evidence_text=str(q_raw.get("evidenceText") or ""),
                        audio_start_sec=float(q_raw["audioStartSec"]) if q_raw.get("audioStartSec") is not None else None,
                        cefr_level=str(q_raw.get("cefrLevel") or "")[:8],
                        skill_tags=list(q_raw.get("skillTags") or []) if isinstance(q_raw.get("skillTags"), list) else [],
                        explanation=str(q_raw.get("explanation") or ""),
                        position=pos,
                        config={"number": pos, **({"word_limit_min": q_raw.get("minWords")} if q_raw.get("minWords") else {})},
                    )
                    if qtype in (Question.QuestionType.INLINE_GAP_FILL, Question.QuestionType.GAP_FILL, Question.QuestionType.SHORT_ANSWER):
                        accepted = q_raw.get("acceptedAnswers") or ([q_raw.get("answer")] if q_raw.get("answer") else [])
                        blanks = [
                            GapBlank(question=question, position=0, answer_text=str(a).strip()[:200])
                            for a in accepted
                            if str(a or "").strip()
                        ]
                        if blanks:
                            GapBlank.objects.bulk_create(blanks)
                    else:
                        options = q_raw.get("options") or q_raw.get("choices") or []
                        ans_key = str(q_raw.get("answer") or q_raw.get("correctAnswer") or "").strip().upper()
                        rows = []
                        for oi, opt in enumerate(options, start=1):
                            if isinstance(opt, dict):
                                text = str(opt.get("text") or opt.get("label") or "")
                                is_ok = bool(opt.get("isCorrect")) or (ans_key == chr(64 + oi))
                            else:
                                text = str(opt or "")
                                is_ok = (ans_key == chr(64 + oi)) or (ans_key == text.strip().upper())
                            rows.append(Choice(question=question, text=text[:500], is_correct=is_ok, position=oi))
                        if rows:
                            Choice.objects.bulk_create(rows)

    return test


def export_exam_package(test: Test, *, template: bool = False) -> dict[str, Any]:
    """Export a Test in canonical Schema 1.0 JSON format (template=True strips answer keys)."""
    sections_out: list[dict[str, Any]] = []
    sections = test.sections.order_by("order").prefetch_related(
        "parts__groups__passage",
        "parts__groups__questions__choices",
        "parts__groups__questions__gap_blanks",
    )
    for sec in sections:
        parts_out: list[dict[str, Any]] = []
        for part in sec.parts.order_by("order"):
            groups_out: list[dict[str, Any]] = []
            for grp in part.groups.order_by("order"):
                questions_out: list[dict[str, Any]] = []
                for q in grp.questions.order_by("position"):
                    q_entry: dict[str, Any] = {
                        "number": q.config.get("number") if isinstance(q.config, dict) and q.config.get("number") else q.position,
                        "position": q.position,
                        "questionType": q.question_type,
                        "text": q.text,
                        "points": q.points,
                        **({"maxScore": float(q.max_score)} if q.max_score is not None else {}),
                        **({"evidenceText": q.evidence_text} if q.evidence_text else {}),
                        **({"audioStartSec": q.audio_start_sec} if q.audio_start_sec is not None else {}),
                        **({"cefrLevel": q.cefr_level} if q.cefr_level else {}),
                        **({"skillTags": q.skill_tags} if q.skill_tags else {}),
                        **({"explanation": q.explanation} if q.explanation and not template else {}),
                    }
                    is_gap = q.question_type in (Question.QuestionType.INLINE_GAP_FILL, Question.QuestionType.GAP_FILL, Question.QuestionType.SHORT_ANSWER)
                    if is_gap:
                        if not template:
                            q_entry["acceptedAnswers"] = [b.answer_text for b in q.gap_blanks.all()]
                    else:
                        q_entry["options"] = [
                            {
                                "text": c.text,
                                **({"isCorrect": bool(c.is_correct)} if not template else {}),
                            }
                            for c in q.choices.order_by("position")
                        ]
                    questions_out.append(q_entry)

                grp_entry: dict[str, Any] = {
                    "title": grp.title,
                    "instructions": grp.instructions,
                    **({"answerRule": grp.answer_rule} if grp.answer_rule else {}),
                    **({"stimulusRef": grp.stimulus_ref} if grp.stimulus_ref else {}),
                    **({"contentLayout": grp.content_layout} if grp.content_layout else {}),
                    "questions": questions_out,
                }
                if grp.passage:
                    grp_entry["passage"] = {
                        "title": grp.passage.title,
                        "content": grp.passage.content,
                        **({"stimulusRef": grp.passage.stimulus_ref} if grp.passage.stimulus_ref else {}),
                    }
                groups_out.append(grp_entry)

            parts_out.append({
                "number": part.number,
                "partNumber": part.part_number or part.order,
                "title": part.title,
                "instructions": part.instructions,
                "audioPlayLimit": part.audio_play_limit,
                **({"transcript": part.transcript} if part.transcript else {}),
                "groups": groups_out,
            })

        sections_out.append({
            "code": sec.code,
            "name": sec.name,
            "durationMinutes": sec.duration_minutes,
            **({"audioUrl": sec.audio_url} if sec.audio_url else {}),
            "parts": parts_out,
        })

    return {
        "schemaVersion": SCHEMA_VERSION,
        "isTemplate": template,
        "title": test.title,
        "description": test.description,
        "subject": test.subject,
        "examType": test.exam_type,
        "assessmentCategory": test.assessment_category,
        "timeLimitMinutes": test.time_limit_minutes,
        "sections": sections_out,
    }


def check_mock_publish_readiness(test: Test) -> list[dict[str, Any]]:
    """Verify full-mock and English test publish readiness (blocks incomplete mocks)."""
    issues: list[dict[str, Any]] = []
    if getattr(test, "is_keyless", False):
        issues.append({
            "block": -1,
            "number": None,
            "option": None,
            "code": "keyless_template_cannot_publish",
        })
    questions = list(test.questions.prefetch_related("choices", "gap_blanks", "matching_prompts__correct_pairs"))
    if not questions:
        issues.append({"block": -1, "number": None, "option": None, "code": "empty_test"})
        return issues

    for q in questions:
        qtype = q.question_type
        if qtype in (Question.QuestionType.WRITTEN, Question.QuestionType.SPEAKING_PROMPT):
            continue
        if qtype in (Question.QuestionType.INLINE_GAP_FILL, Question.QuestionType.GAP_FILL, Question.QuestionType.SHORT_ANSWER):
            if not q.gap_blanks.exists() and not (q.correct_text or "").strip():
                issues.append({"block": -1, "number": q.position, "option": None, "code": "missing_answer_key"})
        elif qtype in (Question.QuestionType.SINGLE_CHOICE, Question.QuestionType.MULTIPLE_CHOICE, Question.QuestionType.TRUE_FALSE_NOT_GIVEN, Question.QuestionType.HEADING_MATCHING, Question.QuestionType.MAP_LABELING):
            if not any(c.is_correct for c in q.choices.all()):
                issues.append({"block": -1, "number": q.position, "option": None, "code": "missing_answer_key"})

    if test.assessment_category == Test.AssessmentCategory.FULL_MOCK and test.subject == "english":
        listening_sec = test.sections.filter(code="LISTENING").first()
        if listening_sec:
            has_audio = bool(listening_sec.audio_url or test.audio_url or listening_sec.parts.exclude(audio="").exists())
            if not has_audio:
                issues.append({"block": -1, "number": None, "option": None, "code": "listening_audio_missing"})

    return issues
