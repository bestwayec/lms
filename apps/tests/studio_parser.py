"""Teacher Studio — Smart Paste / Quick Import parser.

Turns text a teacher pastes (a passage, numbered questions, an answer key)
into editor *blocks*. One block = one question group of a single type:

    mcq       numbered questions, each with its own ``A) B) C)`` options
    tfng      True/False/Not Given (or Yes/No/Not Given) statements
    matching  numbered prompts sharing one ``A) B) C)`` option list
    gap       a text with inline gaps ``[1:answer]`` (``[1:bee|bees]`` = alternatives)
    short     numbered questions answered with a word or number

The parser is pure (no database access) so the editor can call it on every
paste and the tests can pin its behaviour. It never guesses an answer: a
question without a marked answer (``*B)``), a key entry (``1: B``) or a gap
answer stays unanswered and publish validation reports it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
MAX_TEXT_CHARS = 60_000

BLOCK_TYPES = ("mcq", "tfng", "matching", "gap", "short")
SECTIONS = ("GENERAL", "READING", "LISTENING")

TF_LABELS = ["TRUE", "FALSE", "NOT GIVEN"]
YN_LABELS = ["YES", "NO", "NOT GIVEN"]

QUESTION_RE = re.compile(r"^\s*(?:Q(?:uestion)?\s*)?(\d{1,3})\s*[.)]\s+(\S.*)$", re.IGNORECASE)
OPTION_RE = re.compile(r"^\s*(\*)?\s*\(?([A-Ha-h])\s*[.)]\s+(.+?)\s*(\*)?\s*$")
INLINE_OPTION_RE = re.compile(r"(?:^|\s)(\*)?\(?([A-H])[.)]\s+")
GAP_RE = re.compile(r"\[(\d{1,3})(?:\s*:\s*([^\]]*))?\]")
KEY_HEADER_RE = re.compile(
    r"^\s*(?:answer\s*keys?|answers?|keys?|javoblar|javob\s*kaliti|kalitlar|kalit|"
    r"to'g'ri\s+javoblar|ответы|ключи?|ключ\s+ответов)\s*[:\-–—]?\s*(.*)$",
    re.IGNORECASE,
)
# "1: A, 2: bees" / "3=C"  (colon/equals: never a question line)
KEY_LINE_RE = re.compile(r"^\s*\d{1,3}\s*[:=]\s*\S")
KEY_PAIR_RE = re.compile(
    r"(\d{1,3})\s*[:=.)\-–]\s*(.+?)(?=\s*[,;]\s*\d{1,3}\s*[:=.)\-–]|\s+\d{1,3}\s*[:=.)\-–]\s*\S|\s*[,;]?\s*$)"
)
TFNG_RE = re.compile(
    r"\b(TRUE\s*/?\s*,?\s*FALSE\s*/?\s*,?\s*(?:OR\s+)?NOT\s+GIVEN|T\s*/\s*F\s*/\s*NG)\b", re.IGNORECASE
)
YNNG_RE = re.compile(r"\b(YES\s*/?\s*,?\s*NO\s*/?\s*,?\s*(?:OR\s+)?NOT\s+GIVEN|Y\s*/\s*N\s*/\s*NG)\b", re.IGNORECASE)
HEADING_RE = re.compile(
    r"^\s*(?:#+\s*)?(questions?\s+\d{1,3}\s*(?:[-–—]|to)\s*\d{1,3}|part\s+\d+|section\s+\d+|"
    r"(?:reading\s+)?passage(?:\s+\d+)?|reading(?:\s+part)?(?:\s+\d+)?|listening(?:\s+part)?(?:\s+\d+)?|"
    r"matn|text)\b\s*[:.]?\s*(.*)$",
    re.IGNORECASE,
)
INSTRUCTION_RE = re.compile(
    r"^\s*(choose|write|match|complete|read|listen|answer|label|look|decide|do the following|"
    r"which|tanlang|javob|moslang|to'ldiring|o'qing|tinglang|выберите|ответьте|заполните|прочитайте)\b",
    re.IGNORECASE,
)


def normalize_tf(value: str, labels: list[str]) -> str:
    """Map T/F/NG, Y/N/NG and spelled-out labels onto ``labels``; '' if unknown."""
    v = re.sub(r"[\s_.\-]+", " ", str(value or "")).strip().upper()
    if v in ("T", "TRUE", "Y", "YES", "TO'G'RI", "ВЕРНО", "ДА"):
        return labels[0]
    if v in ("F", "FALSE", "N", "NO", "NOTO'G'RI", "НЕВЕРНО", "НЕТ"):
        return labels[1]
    if v in ("NG", "NOT GIVEN", "N G", "NI", "NO INFORMATION", "NOT STATED", "БЕЗ ИНФОРМАЦИИ"):
        return labels[2]
    return ""


def normalize_letter(value: str, option_count: int) -> str:
    v = str(value or "").strip().strip(".)").upper()
    if len(v) == 1 and v in LETTERS[: max(option_count, 0)]:
        return v
    return ""


def parse_answer_pairs(text: str) -> dict[int, str]:
    """``"1: A, 2: bees 3-C"`` → ``{1: "A", 2: "bees", 3: "C"}``."""
    out: dict[int, str] = {}
    for m in KEY_PAIR_RE.finditer(text):
        num = int(m.group(1))
        ans = m.group(2).strip().strip(",;").strip()
        if ans:
            out[num] = ans
    return out


def split_inline_options(text: str) -> tuple[str, list[tuple[str, str, bool]]]:
    """``"Q? A) x B) y *C) z"`` → (``"Q?"``, [(A, x, False), …, (C, z, True)]).

    Only when the letters run A, B, C… in order; otherwise the text is kept.
    """
    matches = list(INLINE_OPTION_RE.finditer(text))
    if len(matches) < 2:
        return text, []
    letters = [m.group(2) for m in matches]
    if letters != list(LETTERS[: len(letters)]):
        return text, []
    head = text[: matches[0].start()].strip()
    opts = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[m.end() : end].strip()
        star = bool(m.group(1)) or body.endswith("*")
        opts.append((m.group(2), body.rstrip("*").strip(), star))
    return head, opts


@dataclass
class _Block:
    section: str
    title: str = ""
    instructions: list[str] = field(default_factory=list)
    passage: list[str] = field(default_factory=list)
    options: list[str] = field(default_factory=list)
    questions: list[dict[str, Any]] = field(default_factory=list)
    tf_labels: list[str] | None = None

    def empty(self) -> bool:
        return not (self.questions or self.passage or self.options)


def _gap_questions(gap_text: str) -> list[dict[str, Any]]:
    """One question per ``[n:answer]`` marker, in text order."""
    out = []
    for m in GAP_RE.finditer(gap_text):
        out.append({"number": int(m.group(1)), "text": "", "options": [], "answer": (m.group(2) or "").strip()})
    return out


def gap_sentence(gap_text: str, number: int) -> str:
    """The sentence/line holding gap ``number``: that gap as ``(n) ________``,
    every other gap as ``(m) …`` (so students see one input per question)."""
    for line in gap_text.splitlines():
        if not any(int(m.group(1)) == number for m in GAP_RE.finditer(line)):
            continue
        pieces = re.split(r"(?<=[.!?])\s+", line.strip()) if len(line) > 200 else [line.strip()]
        for piece in pieces:
            if any(int(m.group(1)) == number for m in GAP_RE.finditer(piece)):

                def repl(m: re.Match[str]) -> str:
                    n = int(m.group(1))
                    return f"({n}) ________" if n == number else f"({n}) …"

                return GAP_RE.sub(repl, piece)
    return f"({number}) ________"


def gap_context(gap_text: str) -> str:
    """Lines of a gap text that hold no gap (headings, labels) — shown as context."""
    return "\n".join(line for line in gap_text.splitlines() if line.strip() and not GAP_RE.search(line)).strip()


def _finalize(block: _Block) -> list[dict[str, Any]]:
    """Decide the block type; a passage with gaps becomes its own gap block."""
    out: list[dict[str, Any]] = []
    passage = "\n".join(block.passage).strip()
    instructions = "\n".join(block.instructions).strip()
    if passage and GAP_RE.search(passage):
        out.append(
            {
                "type": "gap",
                "section": block.section,
                "title": block.title,
                "instructions": instructions,
                "passage": "",
                "gap_text": passage,
                "options": [],
                "questions": _gap_questions(passage),
            }
        )
        passage, instructions = "", ""
        if not block.questions:
            return out

    questions = block.questions
    options = list(block.options)
    # Matching written as statements first, then the shared option list.
    if (
        not options
        and block.tf_labels is None
        and len(questions) >= 2
        and questions[-1]["options"]
        and not any(q["options"] for q in questions[:-1])
    ):
        options = [text for _, text, _ in questions[-1]["options"]]
        questions[-1]["options"] = []

    if not questions:
        if passage or instructions or options:
            out.append(
                {
                    "type": "matching" if options else "mcq",
                    "section": block.section,
                    "title": block.title,
                    "instructions": instructions,
                    "passage": passage,
                    "gap_text": "",
                    "options": options,
                    "questions": [],
                }
            )
        return out

    if block.tf_labels is not None and not any(q["options"] for q in questions):
        btype = "tfng"
        options = list(block.tf_labels)
    elif options and not any(q["options"] for q in questions):
        btype = "matching"
    elif any(q["options"] for q in questions):
        btype = "mcq"
    else:
        btype = "short"

    norm_questions = []
    for q in questions:
        opts = q["options"]
        answer = q.get("answer", "")
        if btype == "mcq":
            star = next((letter for letter, _, s in opts if s), "")
            answer = answer or star
            answer = normalize_letter(answer, len(opts))
        elif btype == "matching":
            answer = normalize_letter(answer, len(options))
        elif btype == "tfng":
            answer = normalize_tf(answer, options)
        norm_questions.append(
            {
                "number": q["number"],
                "text": q["text"].strip(),
                "options": [text for _, text, _ in opts] if btype == "mcq" else [],
                "answer": answer,
            }
        )
    out.append(
        {
            "type": btype,
            "section": block.section,
            "title": block.title,
            "instructions": instructions,
            "passage": passage,
            "gap_text": "",
            "options": options if btype in ("matching", "tfng") else [],
            "questions": norm_questions,
        }
    )
    return out


def apply_answer_key(blocks: list[dict[str, Any]], key: dict[int, str]) -> list[int]:
    """Fill unanswered questions from ``key``. Returns key numbers that matched nothing."""
    used: set[int] = set()
    for block in blocks:
        for q in block["questions"]:
            raw = key.get(q["number"])
            if raw is None:
                continue
            used.add(q["number"])
            if q.get("answer"):
                continue
            if block["type"] == "mcq":
                q["answer"] = normalize_letter(raw, len(q["options"]))
            elif block["type"] == "matching":
                q["answer"] = normalize_letter(raw, len(block["options"]))
            elif block["type"] == "tfng":
                q["answer"] = normalize_tf(raw, block["options"] or TF_LABELS)
            else:
                q["answer"] = raw.strip()
    return sorted(set(key) - used)


def parse_smart_paste(text: str, default_section: str = "GENERAL") -> dict[str, Any]:
    """Parse pasted text into ``{"blocks": [...], "answer_key": {...}, "warnings": [...]}``."""
    text = (text or "")[:MAX_TEXT_CHARS].replace("\r\n", "\n").replace("\r", "\n")
    section = default_section if default_section in SECTIONS else "GENERAL"
    blocks: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    key: dict[int, str] = {}
    cur = _Block(section=section)
    key_mode = False
    last_q: dict[str, Any] | None = None
    after_options = False  # a plain line after options opens the next block

    def flush(keep_passage: bool = False, final: bool = False) -> None:
        nonlocal cur, last_q, after_options
        has_gaps = bool(GAP_RE.search("\n".join(cur.passage)))
        passage_only = not cur.questions and not cur.options and not has_gaps
        inherited = cur.passage if (keep_passage or passage_only) and not has_gaps else []
        if not passage_only or (final and cur.passage):
            blocks.extend(_finalize(cur))
        cur = _Block(section=section, passage=list(inherited))
        last_q = None
        after_options = False

    for lineno, raw_line in enumerate(text.split("\n"), start=1):
        line = raw_line.strip()
        if not line:
            continue

        header = KEY_HEADER_RE.match(line)
        if header and (header.group(1) == "" or parse_answer_pairs(header.group(1)) or len(line) < 40):
            key_mode = True
            key.update(parse_answer_pairs(header.group(1)))
            continue
        if key_mode:
            pairs = parse_answer_pairs(line)
            if pairs:
                key.update(pairs)
                continue
            key_mode = False
        if KEY_LINE_RE.match(line) and not QUESTION_RE.match(line):
            pairs = parse_answer_pairs(line)
            if pairs:
                key.update(pairs)
                continue

        heading = HEADING_RE.match(line)
        if heading and len(line) <= 80 and not QUESTION_RE.match(line):
            word = heading.group(1).lower()
            keep = word.startswith("question")
            flush(keep_passage=keep)
            if word.startswith("listening"):
                section = "LISTENING"
                cur.section = section
            elif word.startswith(("reading", "passage")):
                section = "READING"
                cur.section = section
            cur.title = (heading.group(2) or "").strip() or line.strip("#: ").strip()
            if TFNG_RE.search(line):
                cur.tf_labels = list(TF_LABELS)
            elif YNNG_RE.search(line):
                cur.tf_labels = list(YN_LABELS)
            continue

        tf_hit = TFNG_RE.search(line) or YNNG_RE.search(line)
        if tf_hit and not QUESTION_RE.match(line):
            if cur.questions:
                flush(keep_passage=True)
            cur.tf_labels = list(TF_LABELS if TFNG_RE.search(line) else YN_LABELS)
            cur.instructions.append(line)
            continue

        q = QUESTION_RE.match(line)
        if q:
            number = int(q.group(1))
            body = q.group(2).strip()
            if cur.tf_labels is not None:
                # "1. Bees can see red. FALSE" — a trailing label is the answer.
                m = re.search(r"\s+(TRUE|FALSE|NOT GIVEN|YES|NO|T|F|NG|Y|N)\s*$", body)
                answer = ""
                if m and len(body) > len(m.group(0)) + 3:
                    answer = m.group(1)
                    body = body[: m.start()].strip()
                last_q = {"number": number, "text": body, "options": [], "answer": answer}
            else:
                head, inline = split_inline_options(body)
                last_q = {"number": number, "text": head, "options": inline, "answer": ""}
            cur.questions.append(last_q)
            after_options = bool(last_q["options"])
            continue

        if cur.tf_labels is None and last_q is not None and not last_q["options"]:
            head, inline = split_inline_options(line)
            if not head and inline:
                last_q["options"].extend(inline)
                after_options = True
                continue

        opt = OPTION_RE.match(line)
        if opt and cur.tf_labels is None:
            letter = opt.group(2).upper()
            star = bool(opt.group(1) or opt.group(4))
            body = opt.group(3).strip()
            if last_q is not None:
                expected = LETTERS[len(last_q["options"])] if len(last_q["options"]) < len(LETTERS) else ""
                if letter == expected:
                    last_q["options"].append((letter, body, star))
                    after_options = True
                    continue
            if not cur.questions:
                expected = LETTERS[len(cur.options)] if len(cur.options) < len(LETTERS) else ""
                if letter == expected:
                    cur.options.append(body)
                    continue
            warnings.append({"code": "option_out_of_order", "line": lineno})
            continue

        # Plain text.
        if (
            last_q is not None
            and not last_q["options"]
            and not after_options
            and cur.tf_labels is None
            and not re.search(r"[?.!:]$", last_q["text"])
            and not INSTRUCTION_RE.match(line)
            and not GAP_RE.search(line)
        ):
            last_q["text"] = f"{last_q['text']}\n{line}".strip()
            continue
        if cur.questions:
            flush()
        if INSTRUCTION_RE.match(line) and len(line) <= 200 and not GAP_RE.search(line):
            cur.instructions.append(line)
        else:
            cur.passage.append(line)

    flush(final=True)

    blocks = [b for b in blocks if b["questions"] or b["passage"] or b["gap_text"]]
    unmatched = apply_answer_key(blocks, key)
    for num in unmatched:
        warnings.append({"code": "key_unmatched", "number": num})

    seen: set[int] = set()
    for block in blocks:
        for qd in block["questions"]:
            if qd["number"] in seen:
                warnings.append({"code": "duplicate_number", "number": qd["number"]})
            seen.add(qd["number"])

    return {"blocks": blocks, "answer_key": {str(k): v for k, v in sorted(key.items())}, "warnings": warnings}
