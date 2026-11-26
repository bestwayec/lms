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
        "is_estimate": True,
        "estimate_version": IELTS_ESTIMATE_VERSION,
        "sections": [
            {"code": "LISTENING", "duration_minutes": 30, "parts": 4, "questions": 40, "scale": "band_9"},
            {"code": "READING", "duration_minutes": 60, "parts": 3, "questions": 40, "scale": "band_9", "table": "academic_reading"},
            {"code": "WRITING", "duration_minutes": 60, "parts": 2, "tasks": ["task1_academic", "task2"], "scale": "band_9"},
            {"code": "SPEAKING", "duration_minutes": 14, "parts": 3, "tasks": ["part1", "part2", "part3"], "scale": "band_9"},
        ],
    },
    "ielts_general": {
        "spec_version": "IELTS_GENERAL_V1",
        "title": "IELTS General Training Full Mock",
        "is_estimate": True,
        "estimate_version": IELTS_ESTIMATE_VERSION,
        "sections": [
            {"code": "LISTENING", "duration_minutes": 30, "parts": 4, "questions": 40, "scale": "band_9"},
            {"code": "READING", "duration_minutes": 60, "parts": 3, "questions": 40, "scale": "band_9", "table": "general_reading"},
            {"code": "WRITING", "duration_minutes": 60, "parts": 2, "tasks": ["task1_general_letter", "task2"], "scale": "band_9"},
            {"code": "SPEAKING", "duration_minutes": 14, "parts": 3, "tasks": ["part1", "part2", "part3"], "scale": "band_9"},
        ],
    },
    "cefr_multilevel": {
        "spec_version": MULTILEVEL_SPEC_V2,
        "title": "CEFR Multi-level (UZBMB 2026 v2)",
        "is_estimate": True,
        "scale_max": 75,
        "levels": {"B1": [38, 50], "B2": [51, 64], "C1": [65, 75]},
        "sections": [
            {"code": "LISTENING", "duration_minutes": 45, "parts": 6, "questions": 35, "scale": "cefr_75"},
            {"code": "READING", "duration_minutes": 60, "parts": 5, "questions": 35, "scale": "cefr_75"},
            {"code": "WRITING", "duration_minutes": 60, "parts": 3, "weights": [5, 5, 6], "raw_max": 16, "scale": "cefr_75"},
            {"code": "SPEAKING", "duration_minutes": 30, "parts": 4, "weights": [5, 5, 5, 6], "raw_max": 21, "scale": "cefr_75"},
        ],
    },
}


def get_blueprint(exam_type: str | None = None) -> dict[str, Any]:
    if exam_type and exam_type in BLUEPRINTS:
        return BLUEPRINTS[exam_type]
    return {"blueprints": BLUEPRINTS}


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
    clamped = max(1.0, min(9.0, round(val * 2.0) / 2.0))
    return Decimal(f"{clamped:.1f}")


def score_ielts_sections(
    question_scores: Iterable[Any],
    *,
    exam_type: str = "ielts_academic",
    section_names: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Compute section-level IELTS bands keeping Academic vs General Reading separate,
    and holding overall_band=None when any Written/Speaking section is pending grading.
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
        int_part = math.floor(avg)
        frac = avg - int_part
        rounded = float(int_part) if frac < 0.25 else (float(int_part) + 0.5 if frac < 0.75 else float(int_part) + 1.0)
        overall_band = Decimal(f"{max(1.0, min(9.0, rounded)):.1f}")

    cefr = ielts_band_to_cefr(overall_band) if overall_band is not None else ""
    return {
        "scale": "ielts",
        "exam_type": exam_type,
        "estimate_version": IELTS_ESTIMATE_VERSION,
        "is_estimate": True,
        "grading_status": "pending_grading" if overall_band is None else "graded",
        "overall_band": overall_band,
        "cefr_level": cefr,
        "sections": sections,
    }
