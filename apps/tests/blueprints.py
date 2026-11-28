"""Canonical IELTS Academic/General & UZBMB Multi-level Exam Blueprints and Scoring Tables."""

from __future__ import annotations

import math
import re
import unicodedata
from decimal import Decimal
from typing import Any, Iterable

from apps.tests.score_converter import calculate_overall_ielts_band, ielts_band_to_cefr

IELTS_ESTIMATE_VERSION = "IELTS_PRACTICE_ESTIMATE_V1"
MULTILEVEL_SPEC_V2 = "UZBMB_MULTILEVEL_EN_2026_V2"
SPEC_CHECKED_ON = "2026-11-27"

SOURCES: dict[str, dict[str, str]] = {
    "ielts-format": {
        "title": "IELTS Academic & General test format (Listening 30m, Reading 60m, Writing 60m, Speaking 11-14m)",
        "url": "https://ielts.org/take-a-test/test-types/ielts-academic-test",
    },
    "ielts-scoring": {
        "title": "IELTS scoring in detail (Task 2 weighted twice Task 1; overall mean rounded to nearest 0.5)",
        "url": "https://ielts.org/take-a-test/your-results/ielts-scoring-in-detail",
    },
    "idp-computer-delivered": {
        "title": "IDP: How computer-delivered IELTS works (1 Listening play + 2-minute check window)",
        "url": "https://ielts.idp.com/canada/prepare/article-how-computer-delivered-ielts-works",
    },
    "uzbmb-format": {
        "title": "UZBMB Multilevel test format (Listening 45m / 35Q / 2 plays, Reading 60m / 35Q)",
        "url": "https://uzbmb.uz/page/test_sinovlari_formati",
    },
    "uzbmb-criteria-2023": {
        "title": "UZBMB Ko'p darajali baholash mezonlari (B1 >= 38, B2 >= 51, C1 >= 65 on 0-75 scale)",
        "url": "https://uzbmb.uz/upload/file/pdf/Multilevel-bm.pdf",
    },
    "uzbmb-writing-2025": {
        "title": "UZBMB Multilevel Writing new format (Task 1.1=5, Task 1.2=5, Task 2=6 -> 16 raw, 60 min)",
        "url": "https://api-portal.gov.uz/uploads/165/2025/10/13/99dfbb36-0f1d-2c70-8a4e-e1382a5f255b_media_.pdf",
    },
    "uzbmb-speaking-format": {
        "title": "UZBMB Multilevel Speaking new format (~15 min live pace; per-part prep/response timings)",
        "url": "https://uzbmb.uz/upload/file/pdf/phone/Speaking_format.pdf",
    },
    "uzbmb-speaking-criteria": {
        "title": "UZBMB Rating scale for Multilevel speaking exams (Parts 1.1=5, 1.2=5, 2=5, 3=6 -> 21 raw)",
        "url": "https://uzbmb.uz/upload/file/pdf/phone/yangi_format_eng.pdf",
    },
}

# Separate 40-question raw -> Band tables (BESTWAY mock_scoring.py parity)
IELTS_LISTENING_40: tuple[tuple[int, float], ...] = (
    (39, 9.0), (37, 8.5), (35, 8.0), (32, 7.5), (30, 7.0),
    (26, 6.5), (23, 6.0), (18, 5.5), (16, 5.0), (13, 4.5),
    (11, 4.0), (6, 3.5), (4, 3.0), (2, 2.5), (1, 2.0), (0, 1.0),
)

IELTS_ACADEMIC_READING_40: tuple[tuple[int, float], ...] = (
    (39, 9.0), (37, 8.5), (35, 8.0), (33, 7.5), (30, 7.0),
    (27, 6.5), (23, 6.0), (19, 5.5), (15, 5.0), (13, 4.5),
    (10, 4.0), (6, 3.5), (4, 3.0), (2, 2.5), (1, 2.0), (0, 1.0),
)

IELTS_GENERAL_READING_40: tuple[tuple[int, float], ...] = (
    (40, 9.0), (39, 8.5), (37, 8.0), (36, 7.5), (34, 7.0),
    (32, 6.5), (30, 6.0), (27, 5.5), (23, 5.0), (19, 4.5),
    (15, 4.0), (12, 3.5), (9, 3.0), (6, 2.5), (3, 2.0), (0, 1.0),
)

# Half-point lookup tables (index = round_half(raw) * 2) from BESTWAY mock_scoring.py
UZBMB_MULTILEVEL_WRITING_16_TO_75: tuple[int, ...] = (
    0, 10, 14, 17, 21, 25, 28, 31, 33, 35, 37, 38, 40, 41, 43, 45, 47,
    48, 50, 51, 53, 55, 57, 59, 61, 62, 63, 64, 65, 67, 69, 72, 75,
)

UZBMB_MULTILEVEL_SPEAKING_21_TO_75: tuple[int, ...] = (
    0, 10, 11, 13, 15, 17, 19, 21, 23, 24, 26, 27, 29, 30, 32, 33, 35,
    37, 38, 39, 40, 42, 43, 45, 46, 47, 49, 50, 51, 52, 54, 56, 57, 59,
    61, 63, 64, 65, 67, 69, 71, 73, 75,
)

BLUEPRINTS: dict[str, dict[str, Any]] = {
    "ielts_academic": {
        "spec_version": "IELTS_ACADEMIC_V1",
        "title": "IELTS Academic Full Mock",
        "checked_on": SPEC_CHECKED_ON,
        "is_official": False,
        "is_estimate": True,
        "estimate_version": IELTS_ESTIMATE_VERSION,
        "sources": ["ielts-format", "ielts-scoring", "idp-computer-delivered"],
        "sections": [
            {
                "code": "LISTENING",
                "duration_minutes": 30,
                "duration_approximate": True,
                "audio_plays": 1,
                "preview_seconds": 30,
                "review_seconds": 120,
                "parts": 4,
                "questions": 40,
                "scale": "band_9",
            },
            {
                "code": "READING",
                "duration_minutes": 60,
                "duration_approximate": False,
                "parts": 3,
                "questions": 40,
                "scale": "band_9",
                "table": "academic_reading",
            },
            {
                "code": "WRITING",
                "duration_minutes": 60,
                "duration_approximate": False,
                "parts": 2,
                "tasks": ["task1_academic", "task2"],
                "weights": [1, 2],
                "min_words": [150, 250],
                "scale": "band_9",
                "weighting_rule": "Task 2 carries twice the weight of Task 1: (Task1 + 2*Task2) / 3",
            },
            {
                "code": "SPEAKING",
                "duration_minutes": 14,
                "duration_min_minutes": 11,
                "duration_approximate": True,
                "parts": 3,
                "tasks": ["part1", "part2", "part3"],
                "part_timings": [
                    {"part": "part1", "min_seconds": 240, "max_seconds": 300},
                    {"part": "part2", "prep_seconds": 60, "response_seconds": 120, "min_seconds": 180, "max_seconds": 240},
                    {"part": "part3", "min_seconds": 240, "max_seconds": 300},
                ],
                "scale": "band_9",
            },
        ],
        "unverified": [
            {
                "field": "listening.preview_seconds",
                "note": "Platform choice (30s pre-read); official recordings embed spoken reading pauses.",
            },
            {
                "field": "scale.raw_to_band",
                "note": "ielts.org publishes indicative raw thresholds for Bands 4.0-8.0; sub-4.0 rows and half-band boundaries are practice estimates.",
            },
        ],
    },
    "ielts_general": {
        "spec_version": "IELTS_GENERAL_V1",
        "title": "IELTS General Training Full Mock",
        "checked_on": SPEC_CHECKED_ON,
        "is_official": False,
        "is_estimate": True,
        "estimate_version": IELTS_ESTIMATE_VERSION,
        "sources": ["ielts-format", "ielts-scoring", "idp-computer-delivered"],
        "sections": [
            {
                "code": "LISTENING",
                "duration_minutes": 30,
                "duration_approximate": True,
                "audio_plays": 1,
                "preview_seconds": 30,
                "review_seconds": 120,
                "parts": 4,
                "questions": 40,
                "scale": "band_9",
            },
            {
                "code": "READING",
                "duration_minutes": 60,
                "duration_approximate": False,
                "parts": 3,
                "questions": 40,
                "scale": "band_9",
                "table": "general_reading",
            },
            {
                "code": "WRITING",
                "duration_minutes": 60,
                "duration_approximate": False,
                "parts": 2,
                "tasks": ["task1_general_letter", "task2"],
                "weights": [1, 2],
                "min_words": [150, 250],
                "scale": "band_9",
                "weighting_rule": "Task 2 carries twice the weight of Task 1: (Task1 + 2*Task2) / 3",
            },
            {
                "code": "SPEAKING",
                "duration_minutes": 14,
                "duration_min_minutes": 11,
                "duration_approximate": True,
                "parts": 3,
                "tasks": ["part1", "part2", "part3"],
                "part_timings": [
                    {"part": "part1", "min_seconds": 240, "max_seconds": 300},
                    {"part": "part2", "prep_seconds": 60, "response_seconds": 120, "min_seconds": 180, "max_seconds": 240},
                    {"part": "part3", "min_seconds": 240, "max_seconds": 300},
                ],
                "scale": "band_9",
            },
        ],
        "unverified": [
            {
                "field": "listening.preview_seconds",
                "note": "Platform choice (30s pre-read); official recordings embed spoken reading pauses.",
            },
            {
                "field": "scale.raw_to_band",
                "note": "ielts.org publishes indicative raw thresholds for General Reading Bands 4.0-7.0; intermediate boundaries are practice estimates.",
            },
        ],
    },
    "cefr_multilevel": {
        "spec_version": MULTILEVEL_SPEC_V2,
        "title": "CEFR Multi-level (UZBMB 2026 v2)",
        "checked_on": SPEC_CHECKED_ON,
        "is_official": False,
        "is_estimate": True,
        "scale_max": 75,
        "levels": {"B1": [38, 50], "B2": [51, 64], "C1": [65, 75]},
        "sources": ["uzbmb-format", "uzbmb-criteria-2023", "uzbmb-writing-2025", "uzbmb-speaking-format", "uzbmb-speaking-criteria"],
        "sections": [
            {
                "code": "LISTENING",
                "duration_minutes": 45,
                "duration_approximate": False,
                "audio_plays": 2,
                "preview_seconds_min": 15,
                "preview_seconds_max": 30,
                "parts": 6,
                "questions": 35,
                "scale": "cefr_75",
            },
            {
                "code": "READING",
                "duration_minutes": 60,
                "duration_approximate": False,
                "parts": 5,
                "questions": 35,
                "scale": "cefr_75",
            },
            {
                "code": "WRITING",
                "duration_minutes": 60,
                "duration_approximate": False,
                "parts": 3,
                "tasks": ["1.1", "1.2", "2"],
                "weights": [5, 5, 6],
                "word_limits": [[50, 50], [120, 150], [180, 200]],
                "raw_max": 16,
                "scale": "cefr_75",
            },
            {
                "code": "SPEAKING",
                "duration_minutes": 30,
                "official_expected_minutes": 15,
                "duration_approximate": True,
                "duration_note": "Official UZBMB rules specify per-task prep/response windows (~15 min live pace); 30 min is the generous session/mic-buffer cap.",
                "parts": 4,
                "tasks": ["1.1", "1.2", "2", "3"],
                "weights": [5, 5, 5, 6],
                "raw_max": 21,
                "part_timings": [
                    {"part": "1.1", "questions": 3, "prep_seconds": [0, 0, 0], "response_seconds": [30, 30, 30], "raw_max": 5},
                    {"part": "1.2", "questions": 3, "prep_seconds": [0, 0, 0], "response_seconds": [45, 30, 30], "raw_max": 5},
                    {"part": "2", "questions": 1, "prep_seconds": [60], "response_seconds": [120], "raw_max": 5},
                    {"part": "3", "questions": 1, "prep_seconds": [60], "response_seconds": [120], "raw_max": 6},
                ],
                "scale": "cefr_75",
            },
        ],
        "unverified": [
            {
                "field": "speaking.duration_minutes",
                "note": "UZBMB documents define per-question timings (~15 min total speech/prep) without a rigid 30-min section clock; 30 min is BESTWAY/GRANDEC's generous session cap.",
            },
            {
                "field": "scale.objective_and_speaking",
                "note": "Official UZBMB Listening/Reading use an item-level Rasch model and unpublished 21->75 Speaking conversion parameters; anchor/lookup tables are practice estimates.",
            },
        ],
    },
}


def get_blueprint(exam_type: str | None = None) -> dict[str, Any]:
    if exam_type and exam_type in BLUEPRINTS:
        return {**BLUEPRINTS[exam_type], "sources_detail": SOURCES}
    return {"checked_on": SPEC_CHECKED_ON, "sources": SOURCES, "blueprints": BLUEPRINTS}


def _lookup_table(table: tuple[tuple[int, float], ...], raw: int | float | Decimal, total: int = 40) -> Decimal:
    val = float(raw)
    if total > 0 and total != 40:
        val = (val / total) * 40.0
    raw_int = max(0, min(40, int(math.floor(val + 0.5))))
    for threshold, band in table:
        if raw_int >= threshold:
            return Decimal(f"{band:.1f}")
    return Decimal("1.0")


def raw_to_ielts_listening_band(raw: int | float | Decimal, total: int = 40) -> Decimal:
    return _lookup_table(IELTS_LISTENING_40, raw, total=total)


def raw_to_ielts_reading_band(
    raw: int | float | Decimal,
    total: int = 40,
    exam_type: str = "ielts_academic",
) -> Decimal:
    table = IELTS_GENERAL_READING_40 if str(exam_type or "").lower() == "ielts_general" else IELTS_ACADEMIC_READING_40
    return _lookup_table(table, raw, total=total)


def convert_multilevel_writing_16_to_75(raw_total: float | Decimal) -> Decimal:
    clamped = max(0.0, min(16.0, float(raw_total)))
    idx = max(0, min(len(UZBMB_MULTILEVEL_WRITING_16_TO_75) - 1, int(round(clamped * 2.0))))
    return Decimal(str(UZBMB_MULTILEVEL_WRITING_16_TO_75[idx]))


def convert_multilevel_speaking_21_to_75(raw_total: float | Decimal) -> Decimal:
    clamped = max(0.0, min(21.0, float(raw_total)))
    idx = max(0, min(len(UZBMB_MULTILEVEL_SPEAKING_21_TO_75) - 1, int(round(clamped * 2.0))))
    return Decimal(str(UZBMB_MULTILEVEL_SPEAKING_21_TO_75[idx]))


def respects_word_limit_rule(value: str, rule: str) -> bool:
    """Validate ONE_WORD / ONE_WORD_AND_OR_NUMBER responses cleanly."""
    normalized = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(value or "")).strip())
    if not normalized:
        return False
    tokens = [t for t in normalized.split(" ") if t]
    numeric = sum(bool(re.fullmatch(r"[+-]?[0-9]+(?:[.,:/-][0-9]+)*%?", t)) for t in tokens)

    def _is_word(tok: str) -> bool:
        parts = re.split(r"[-'\u2019]", tok)
        return all(part and all(unicodedata.category(c).startswith("L") for c in part) for part in parts)

    words = sum(_is_word(t) for t in tokens)
    if numeric + words != len(tokens):
        return False
    if rule == "ONE_WORD":
        return len(tokens) == 1 and words == 1
    if rule == "ONE_WORD_AND_OR_NUMBER":
        return bool(tokens) and words <= 1 and numeric <= 1
    return True


def _round_half_band(val: float) -> Decimal:
    int_part = math.floor(val)
    frac = val - int_part
    rounded = float(int_part) if frac < 0.25 else (float(int_part) + 0.5 if frac < 0.75 else float(int_part) + 1.0)
    clamped = max(1.0, min(9.0, rounded))
    return Decimal(f"{clamped:.1f}")


def _writing_band_from_items(items: list[Any], earned: Decimal, maximum: Decimal) -> Decimal:
    """Apply official IELTS Writing weighting: Task 2 carries twice the weight of Task 1."""
    if len(items) == 2:
        t1_item, t2_item = items[0], items[1]
        t1_max = float(getattr(t1_item, "maximum", 0) or 0)
        t2_max = float(getattr(t2_item, "maximum", 0) or 0)
        if t1_max > 0 and t2_max > 0:
            t1_band = (float(getattr(t1_item, "earned", 0)) / t1_max) * 9.0
            t2_band = (float(getattr(t2_item, "earned", 0)) / t2_max) * 9.0
            return _round_half_band((t1_band + 2.0 * t2_band) / 3.0)
    return _round_half_band(float(earned / maximum) * 9.0) if maximum > 0 else Decimal("0.0")


def score_ielts_sections(
    question_scores: Iterable[Any],
    *,
    exam_type: str = "ielts_academic",
    section_names: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Compute section-level IELTS bands keeping Academic vs General Reading separate,
    weighting Writing Task 2 twice Task 1, and holding overall_band=None when any
    Written/Speaking section is pending grading.
    """
    section_names = section_names or {}
    by_code: dict[str, list[Any]] = {}
    for q in question_scores:
        code = (getattr(q, "section_code", "") or "").upper()
        if not code:
            code = "WRITING" if getattr(q, "kind", "") == "written" else "GENERAL"
        by_code.setdefault(code, []).append(q)

    sections: dict[str, dict[str, Any]] = {}
    has_pending = False

    for code, items in by_code.items():
        if code in ("LISTENING", "READING", "GENERAL"):
            correct = sum(1 for q in items if q.is_correct is True)
            total = len(items)
            if code == "LISTENING":
                band = raw_to_ielts_listening_band(correct, total=total)
            else:
                band = raw_to_ielts_reading_band(correct, total=total, exam_type=exam_type)
            sections[code] = {
                "code": code,
                "name": section_names.get(code) or code.title(),
                "status": "scored",
                "earned": correct,
                "maximum": total,
                "band": float(band),
            }
        else:
            # Rated skill section (WRITING / SPEAKING)
            pending_items = any(q.is_correct is None and q.answered for q in items) or any(
                getattr(q, "kind", "") == "written" and q.is_correct is None for q in items
            )
            earned = sum((Decimal(str(q.earned)) for q in items), Decimal("0"))
            maximum = sum((Decimal(str(q.maximum)) for q in items), Decimal("0"))
            if pending_items or not any(q.answered for q in items):
                has_pending = True
                sections[code] = {
                    "code": code,
                    "name": section_names.get(code) or code.title(),
                    "status": "pending",
                    "earned": float(earned),
                    "maximum": float(maximum),
                    "band": None,
                }
            else:
                if code == "WRITING":
                    band = _writing_band_from_items(items, earned, maximum)
                else:
                    band = _round_half_band(float(earned / maximum) * 9.0) if maximum > 0 else Decimal("0.0")
                sections[code] = {
                    "code": code,
                    "name": section_names.get(code) or code.title(),
                    "status": "scored",
                    "earned": float(earned),
                    "maximum": float(maximum),
                    "band": float(band),
                }

    skill_bands = [
        sections[c]["band"]
        for c in ("LISTENING", "READING", "WRITING", "SPEAKING")
        if c in sections and sections[c]["status"] == "scored" and sections[c]["band"] is not None
    ]
    is_full_mock = len(sections) >= 4 or any(c in sections for c in ("WRITING", "SPEAKING"))

    overall_band: Decimal | None = None
    if has_pending:
        overall_band = None
    elif all(c in sections for c in ("LISTENING", "READING", "WRITING", "SPEAKING")) and len(skill_bands) == 4:
        overall_band = calculate_overall_ielts_band(
            sections["LISTENING"]["band"],
            sections["READING"]["band"],
            sections["WRITING"]["band"],
            sections["SPEAKING"]["band"],
        )
    elif not is_full_mock and len(sections) == 1:
        only = next(iter(sections.values()))
        if only["band"] is not None:
            overall_band = Decimal(f"{float(only['band']):.1f}")
    elif not has_pending and skill_bands:
        avg = sum(skill_bands) / len(skill_bands)
        overall_band = _round_half_band(avg)

    cefr = ielts_band_to_cefr(overall_band) if overall_band is not None else ""
    return {
        "scale": "ielts",
        "exam_type": exam_type,
        "estimate_version": IELTS_ESTIMATE_VERSION,
        "is_estimate": True,
        "is_official": False,
        "grading_status": "pending_grading" if overall_band is None else "graded",
        "overall_band": overall_band,
        "cefr_level": cefr,
        "sections": sections,
    }
