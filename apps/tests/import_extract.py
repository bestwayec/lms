"""Smart Import Pro — turn an uploaded test file into editor blocks.

Formats: plain text / Smart Paste, CSV (``,`` ``;`` or tab; UTF-8 or
Windows-1251), XLSX, DOCX and *selectable-text* PDF. The real format is
decided from the file's bytes, not its name; the extension must agree.

Safety: size cap, ZIP entry/expansion caps (zip-bomb), DOCX/XLSX parsed
with the standard XML parser on a fixed set of package parts (external
entities are not resolved by ``xml.etree``), PDFs read text only (no
JavaScript, no forms). Nothing is sent to any external service.

Honesty: the extracted text is handed to the same parsers the editor uses
(``parse_smart_paste`` / the tabular parser). They never invent an answer;
missing keys are reported. A PDF without a text layer (a scan) is refused
with ``scanned_pdf`` — OCR is not configured, so the teacher is told to
paste the text or upload the source document instead.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from dataclasses import dataclass, field
from typing import Any
from xml.etree import ElementTree as ET

MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_ZIP_ENTRIES = 2000
MAX_ZIP_EXPANDED_BYTES = 60 * 1024 * 1024
MAX_PDF_PAGES = 60
MAX_SHEET_ROWS = 2000
MIN_TEXT_CHARS_PER_PAGE = 25

EXT_KIND = {
    "txt": "text",
    "csv": "csv",
    "tsv": "csv",
    "xlsx": "xlsx",
    "docx": "docx",
    "pdf": "pdf",
}

W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class ImportError_(ValueError):
    """Machine-readable import failure; ``code`` is translated by the UI."""

    def __init__(self, code: str, **extra: Any):
        super().__init__(code)
        self.code = code
        self.extra = extra


@dataclass
class Extracted:
    kind: str
    text: str = ""
    rows: list[list[str]] | None = None
    warnings: list[dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Sniffing
# ---------------------------------------------------------------------------


def _zip_kind(data: bytes) -> str:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise ImportError_("file_corrupt") from None
    infos = zf.infolist()
    if len(infos) > MAX_ZIP_ENTRIES or sum(i.file_size for i in infos) > MAX_ZIP_EXPANDED_BYTES:
        raise ImportError_("file_too_complex")
    names = {i.filename for i in infos}
    if "word/document.xml" in names:
        return "docx"
    if "xl/workbook.xml" in names:
        return "xlsx"
    raise ImportError_("unsupported_format")


def sniff(data: bytes, filename: str = "") -> str:
    """Return the real kind of ``data``; the extension, when given, must agree."""
    if not data:
        raise ImportError_("file_empty")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ImportError_("file_too_large", limit_mb=MAX_UPLOAD_BYTES // (1024 * 1024))
    if data.startswith(b"%PDF-"):
        kind = "pdf"
    elif data.startswith(b"PK\x03\x04"):
        kind = _zip_kind(data)
    elif data.startswith((b"\xd0\xcf\x11\xe0",)):  # legacy .doc / .xls (OLE2)
        raise ImportError_("legacy_office_format")
    elif b"\x00" in data[:4096]:
        raise ImportError_("unsupported_format")
    else:
        kind = "text"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext:
        expected = EXT_KIND.get(ext)
        if expected is None:
            raise ImportError_("unsupported_format")
        if expected == "csv" and kind == "text":
            kind = "csv"
        elif expected != kind and not (expected == "text" and kind == "text"):
            raise ImportError_("extension_mismatch")
    return kind


def decode_text(data: bytes) -> str:
    """UTF-8 (with/without BOM), UTF-16 with BOM, else Windows-1251 (uz/ru Excel exports)."""
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1251", errors="replace")


# ---------------------------------------------------------------------------
# Extractors
# ---------------------------------------------------------------------------


def _csv_rows(text: str) -> list[list[str]]:
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ";" if sample.count(";") > sample.count(",") else ","
    return [row for row in csv.reader(io.StringIO(text), delimiter=delimiter)]


def _docx_paragraph_text(p: ET.Element) -> str:
    parts: list[str] = []
    for node in p.iter():
        tag = node.tag
        if tag == f"{W_NS}t":
            parts.append(node.text or "")
        elif tag == f"{W_NS}tab":
            parts.append("\t")
        elif tag in (f"{W_NS}br", f"{W_NS}cr"):
            parts.append("\n")
    return "".join(parts)


def extract_docx(data: bytes) -> Extracted:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        with zf.open("word/document.xml") as fh:
            xml = fh.read(MAX_ZIP_EXPANDED_BYTES)
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        raise ImportError_("file_corrupt") from None
    body = root.find(f"{W_NS}body")
    if body is None:
        raise ImportError_("file_empty")
    lines: list[str] = []
    table_rows: list[list[str]] = []
    out = Extracted(kind="docx")
    numbered_auto = 0
    for child in body:
        if child.tag == f"{W_NS}p":
            text = _docx_paragraph_text(child)
            # Word auto-numbering ("1." drawn by the list style) is not in the text.
            if child.find(f"{W_NS}pPr/{W_NS}numPr") is not None and text.strip():
                numbered_auto += 1
            lines.append(text)
        elif child.tag == f"{W_NS}tbl":
            for tr in child.iter(f"{W_NS}tr"):
                cells = [
                    "\n".join(_docx_paragraph_text(p) for p in tc.iter(f"{W_NS}p")).strip()
                    for tc in tr.iter(f"{W_NS}tc")
                ]
                if any(cells):
                    table_rows.append(cells)
            lines.append("")
    if numbered_auto:
        out.warnings.append({"code": "docx_auto_numbering", "count": numbered_auto})
    out.text = "\n".join(lines)
    if table_rows and _looks_tabular(table_rows):
        out.rows = table_rows
    elif table_rows:
        out.text += "\n" + "\n".join(" ".join(c for c in r if c) for r in table_rows)
    if not out.text.strip() and not out.rows:
        raise ImportError_("file_empty")
    return out


def extract_xlsx(data: bytes) -> Extracted:
    from openpyxl import load_workbook

    try:
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception:
        raise ImportError_("file_corrupt") from None
    try:
        ws = wb.worksheets[0]
        rows: list[list[str]] = []
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i >= MAX_SHEET_ROWS:
                break
            cells = ["" if v is None else str(v).strip() for v in row]
            if any(cells):
                rows.append(cells)
    finally:
        wb.close()
    if not rows:
        raise ImportError_("file_empty")
    return Extracted(kind="xlsx", rows=rows)


def extract_pdf(data: bytes) -> Extracted:
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise ImportError_("pdf_encrypted")
        pages = reader.pages
        if len(pages) > MAX_PDF_PAGES:
            raise ImportError_("pdf_too_many_pages", limit=MAX_PDF_PAGES)
        texts = [(p.extract_text() or "") for p in pages]
    except ImportError_:
        raise
    except Exception:
        raise ImportError_("file_corrupt") from None
    chars = sum(len(t.strip()) for t in texts)
    if not pages or chars < MIN_TEXT_CHARS_PER_PAGE * len(pages):
        raise ImportError_("scanned_pdf")
    return Extracted(kind="pdf", text="\n".join(texts))


def _looks_tabular(rows: list[list[str]]) -> bool:
    if len(rows) < 2:
        return False
    head = [re.sub(r"\s+", "_", c.strip().lower()) for c in rows[0]]
    return any(h in ("question", "savol", "вопрос", "savollar", "text") for h in head) or (
        len(rows[0]) >= 5 and sum(1 for r in rows if len(r) >= 5) >= len(rows) * 0.8
    )


def extract(data: bytes, filename: str = "") -> Extracted:
    kind = sniff(data, filename)
    if kind == "pdf":
        return extract_pdf(data)
    if kind == "docx":
        return extract_docx(data)
    if kind == "xlsx":
        return extract_xlsx(data)
    text = decode_text(data)
    if kind == "csv":
        return Extracted(kind="csv", rows=_csv_rows(text))
    return Extracted(kind="text", text=text)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def build_report(blocks: list[dict[str, Any]], warnings: list[dict[str, Any]]) -> dict[str, Any]:
    """What the teacher must review before saving. Counts only; nothing is fixed silently."""
    total = missing = duplicate_options = too_few = valid = 0
    for block in blocks:
        for q in block.get("questions", []):
            total += 1
            no_answer = not str(q.get("answer") or "").strip()
            opts = [str(o).strip().lower() for o in (q.get("options") or []) if str(o).strip()]
            dup = len(opts) != len(set(opts))
            few = block.get("type") == "mcq" and len(opts) < 2
            missing += no_answer
            duplicate_options += dup
            too_few += few
            valid += not (no_answer or dup or few)
    numbers = [q.get("number") for b in blocks for q in b.get("questions", [])]
    duplicates = sorted({n for n in numbers if numbers.count(n) > 1})
    invalid = sum(1 for w in warnings if w.get("code") not in ("docx_auto_numbering",))
    return {
        "total_questions": total,
        "valid_questions": valid,
        "missing_answers": missing,
        "duplicate_options": duplicate_options,
        "too_few_options": too_few,
        "duplicate_numbers": duplicates,
        "warnings_count": invalid,
    }
