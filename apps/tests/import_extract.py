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
    "pptx": "pptx",
    "txt": "text",
    "csv": "csv",
    "tsv": "csv",
    "xlsx": "xlsx",
    "docx": "docx",
    "pdf": "pdf",
}

W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
A_NS = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
P_NS = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
R_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PKG_REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"
MAX_SLIDES = 200


def _safe_xml(raw: bytes):
    """Parse one OOXML part. OOXML never uses a DTD: a DOCTYPE/ENTITY means a
    crafted file (entity expansion, external entities) and is refused."""
    head = raw[:4096].upper()
    if b"<!DOCTYPE" in head or b"<!ENTITY" in raw.upper():
        raise ImportError_("file_corrupt")
    try:
        return ET.fromstring(raw)
    except ET.ParseError:
        raise ImportError_("file_corrupt") from None


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
    slide_lines: list[int] | None = None


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
    if "ppt/presentation.xml" in names:
        return "pptx"
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
    root = _safe_xml(xml)
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


def _ppt_paragraphs(node) -> list[str]:
    out = []
    for p in node.iter(f"{A_NS}p"):
        parts = []
        for el in p.iter():
            if el.tag == f"{A_NS}t":
                parts.append(el.text or "")
            elif el.tag == f"{A_NS}br":
                parts.append("\n")
        text = "".join(parts)
        if text.strip():
            out.append(text)
    return out


def _slide_order(zf: zipfile.ZipFile) -> list[str]:
    """Slide part names in presentation order (sldIdLst → relationships)."""
    pres = _safe_xml(zf.read("ppt/presentation.xml"))
    rels = _safe_xml(zf.read("ppt/_rels/presentation.xml.rels"))
    targets = {r.get("Id"): r.get("Target", "") for r in rels.iter(f"{PKG_REL_NS}Relationship")}
    order = []
    lst = pres.find(f"{P_NS}sldIdLst")
    for sld in (lst if lst is not None else []):
        target = targets.get(sld.get(f"{R_NS}id"), "")
        if target:
            order.append("ppt/" + target.lstrip("/").removeprefix("ppt/"))
    return order[:MAX_SLIDES]


def _notes_for(zf: zipfile.ZipFile, slide_part: str) -> list[str]:
    rel_part = slide_part.replace("slides/", "slides/_rels/") + ".rels"
    if rel_part not in zf.namelist():
        return []
    for r in _safe_xml(zf.read(rel_part)).iter(f"{PKG_REL_NS}Relationship"):
        if r.get("Type", "").endswith("/notesSlide"):
            target = r.get("Target", "")
            name = "ppt/notesSlides/" + target.rsplit("/", 1)[-1]
            if name in zf.namelist():
                return _ppt_paragraphs(_safe_xml(zf.read(name)))
    return []


def extract_pptx(data: bytes) -> Extracted:
    """Slides in order: text boxes, tables, answer lines from speaker notes.

    Returns the text with a per-line slide map in ``out.slide_lines`` so the
    caller can tell which slide each question came from. Image-only slides
    produce a warning (no OCR) instead of being silently skipped.
    """
    from apps.tests.studio_parser import KEY_HEADER_RE, KEY_LINE_RE, SINGLE_ANSWER_RE

    out = Extracted(kind="pptx")
    lines: list[str] = []
    line_slide: list[int] = []
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        order = _slide_order(zf)
        if not order:
            raise ImportError_("file_empty")
        for number, part in enumerate(order, start=1):
            if part not in zf.namelist():
                continue
            root = _safe_xml(zf.read(part))
            slide_lines: list[str] = []
            has_picture = any(True for _ in root.iter(f"{P_NS}pic"))
            for sp in root.iter(f"{P_NS}sp"):
                slide_lines.extend(_ppt_paragraphs(sp))
            for frame in root.iter(f"{P_NS}graphicFrame"):
                rows = []
                for tr in frame.iter(f"{A_NS}tr"):
                    cells = [" ".join(_ppt_paragraphs(tc)).strip() for tc in tr.iter(f"{A_NS}tc")]
                    if any(cells):
                        rows.append(cells)
                slide_lines.extend(_table_as_questions(rows))
            # Speaker notes: only answer-key lines ("Javob: B", "1-B", "Kalitlar: …");
            # free commentary would pollute question text.
            for note in _notes_for(zf, part):
                stripped = note.strip()
                if SINGLE_ANSWER_RE.match(stripped) or KEY_HEADER_RE.match(stripped) or KEY_LINE_RE.match(stripped):
                    slide_lines.append(stripped)
            if not slide_lines and has_picture:
                out.warnings.append({"code": "pptx_image_only_slide", "slide": number})
            for line in slide_lines:
                lines.append(line)
                line_slide.append(number)
            lines.append("")
            line_slide.append(number)
    out.text = "\n".join(lines)
    out.slide_lines = line_slide
    if not out.text.strip() and not out.rows:
        raise ImportError_("pptx_no_text")
    return out


_HEAD_Q = ("savol", "question", "вопрос", "savollar")
_HEAD_ANS = ("javob", "answer", "ответ", "kalit", "to'g'ri javob", "to‘g‘ri javob")


def _table_as_questions(rows: list[list[str]]) -> list[str]:
    """A slide table with a Savol/A/B/C/D(/Javob) header → numbered question lines.

    Other tables are kept as plain lines. The answer column is used only when
    present; nothing is inferred.
    """
    if len(rows) < 2:
        return [" ".join(c for c in r if c) for r in rows]
    head = [c.strip().lower().rstrip(":.)") for c in rows[0]]
    if not head or head[0] not in _HEAD_Q:
        return [" ".join(c for c in r if c) for r in rows]
    opt_cols = [i for i, h in enumerate(head) if len(h) == 1 and h.upper() in "ABCDEАБВГД"]
    ans_col = next((i for i, h in enumerate(head) if h in _HEAD_ANS), None)
    out: list[str] = []
    for n, row in enumerate(rows[1:], start=1):
        q = row[0].strip()
        if not q:
            continue
        if not re.match(r"^\s*\d{1,3}\s*[.)]\s", q):
            q = f"{n}. {q}"
        out.append(q)
        for j, col in enumerate(opt_cols):
            if col < len(row) and row[col].strip():
                out.append(f"{'ABCDE'[j]}) {row[col].strip()}")
        if ans_col is not None and ans_col < len(row) and row[ans_col].strip():
            out.append(f"Javob: {row[ans_col].strip()}")
    return out


def slide_map(text: str, slide_lines: list[int], numbers: list[int]) -> dict[int, int]:
    """Question number → slide, from where its "N." line occurs (first match in order)."""
    import re as _re

    result: dict[int, int] = {}
    pending = list(numbers)
    for line, slide in zip(text.split("\n"), slide_lines):
        m = _re.match(r"^\s*(?:Q(?:uestion)?\s*)?(\d{1,3})\s*[.)]\s+\S", line, _re.IGNORECASE)
        if m and pending and int(m.group(1)) == pending[0]:
            result[pending.pop(0)] = slide
    return result


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
    if kind == "pptx":
        return extract_pptx(data)
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
    invalid = sum(1 for w in warnings if w.get("code") not in ("docx_auto_numbering", "pptx_image_only_slide"))
    return {
        "total_questions": total,
        "valid_questions": valid,
        "missing_answers": missing,
        "duplicate_options": duplicate_options,
        "too_few_options": too_few,
        "duplicate_numbers": duplicates,
        "warnings_count": invalid,
    }
