"""Spreadsheet-injection ("CSV/formula injection") protection for exports.

A cell whose text starts with ``=``, ``+``, ``-``, ``@`` (or a tab / carriage return) is
interpreted as a formula by Excel, LibreOffice and Google Sheets. Exports contain text that
people other than the reader control (a student's registered name, a test title, a center
name), so ``=HYPERLINK(...)`` or ``=cmd|...`` would run on a teacher's machine. Every text
value written to a spreadsheet or CSV goes through :func:`safe_cell`.

Numbers, ``Decimal``, dates and ``None`` are passed through untouched; only ``str`` is changed.
"""

from __future__ import annotations

from typing import Any

FORMULA_TRIGGERS = ("=", "+", "-", "@", "\t", "\r", "\n")


def safe_cell(value: Any) -> Any:
    """Return *value*, with a leading apostrophe for text that a spreadsheet would evaluate."""
    if isinstance(value, str) and value.startswith(FORMULA_TRIGGERS):
        return "'" + value
    return value


def safe_row(values) -> list[Any]:
    return [safe_cell(v) for v in values]
