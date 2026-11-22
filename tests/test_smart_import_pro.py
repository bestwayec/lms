"""Smart Import Pro: every supported format yields the same, unaltered questions.

Nothing is guessed: missing keys stay missing and are reported; text is kept
byte-for-byte (Uzbek apostrophes, Cyrillic, quotes).
"""

from __future__ import annotations

import io
import zipfile

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.tests import studio_service as svc
from apps.tests.import_extract import ImportError_, sniff
from apps.tests.studio_parser import parse_smart_paste
from tests import import_fixtures as fx


def _questions(result):
    return [q for b in result["blocks"] for q in b["questions"]]


def _assert_ona_tili(result, expect_q20="D"):
    qs = _questions(result)
    assert len(qs) == 20
    for q, (text, opts, ans) in zip(qs, fx.ONA_TILI):
        assert q["text"] == text  # unaltered, incl. ‘ ’ “ ”
        assert q["options"] == opts
    assert [q["answer"] for q in qs[:19]] == [a for _, _, a in fx.ONA_TILI[:19]]
    assert qs[19]["answer"] == expect_q20
    assert result["report"]["total_questions"] == 20
    assert result["report"]["missing_answers"] == 0


# --------------------------------------------------------------------------- formats


def test_docx_import_preserves_text_and_keys():
    _assert_ona_tili(svc.import_test_file(fx.docx_bytes(), "ona_tili.docx"))


def test_xlsx_import_with_uzbek_header():
    r = svc.import_test_file(fx.xlsx_bytes(), "ona_tili.xlsx")
    assert r["source"]["kind"] == "xlsx"
    _assert_ona_tili(r)


@pytest.mark.parametrize("delimiter,encoding", [(";", "utf-8-sig"), (",", "utf-8"), ("\t", "utf-8")])
def test_csv_import_delimiters(delimiter, encoding):
    _assert_ona_tili(svc.import_test_file(fx.csv_bytes(delimiter=delimiter, encoding=encoding), "t.csv"))


def test_csv_windows_1251_russian_is_not_mangled():
    items = [("Какое слово является наречием?", ["быстро", "быстрый", "быстрота", "быстрее"], "А")]
    r = svc.import_test_file(fx.csv_bytes(items, encoding="cp1251"), "ru.csv")
    q = _questions(r)[0]
    assert q["text"] == "Какое слово является наречием?" and q["options"][0] == "быстро"
    assert q["answer"] == "A"


@pytest.mark.skipif(not fx.has_unicode_font(), reason="needs DejaVuSans for a Unicode text PDF")
def test_selectable_text_pdf_import():
    r = svc.import_test_file(fx.pdf_bytes(), "ona_tili.pdf")
    assert r["source"]["kind"] == "pdf"
    qs = _questions(r)
    assert len(qs) == 20 and qs[0]["text"] == "Qaysi gapda undalma mavjud?"
    assert qs[1]["options"][1] == "Abdulla Qodiriy"
    assert [q["answer"] for q in qs] == [a for _, _, a in fx.ONA_TILI]


def test_scanned_pdf_is_refused_honestly():
    with pytest.raises(svc.StudioError) as e:
        svc.import_test_file(fx.pdf_bytes(image_only=True), "scan.pdf")
    assert e.value.code == "scanned_pdf"


def test_plain_text_upload_equals_smart_paste():
    r = svc.import_test_file(fx.smart_paste_text().encode(), "t.txt")
    _assert_ona_tili(r)


# --------------------------------------------------------------------------- safety


@pytest.mark.parametrize(
    "data,name,code",
    [
        (b"", "a.csv", "file_empty"),
        (b"%PDF-1.4 fake", "a.docx", "extension_mismatch"),
        (b"PK\x03\x04garbage", "a.docx", "file_corrupt"),
        (b"\xd0\xcf\x11\xe0legacy", "a.doc", "legacy_office_format"),
        (b"MZ\x00\x00binary", "a.exe", "unsupported_format"),
        (b"hello", "a.exe", "unsupported_format"),
    ],
)
def test_bad_files_are_rejected(data, name, code):
    with pytest.raises(ImportError_) as e:
        sniff(data, name)
    assert e.value.code == code


def test_zip_bomb_is_rejected():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("word/document.xml", b"0" * (70 * 1024 * 1024))
    with pytest.raises(ImportError_) as e:
        sniff(buf.getvalue(), "bomb.docx")
    assert e.value.code == "file_too_complex"


def test_oversized_upload_is_rejected():
    from apps.tests.import_extract import MAX_UPLOAD_BYTES

    with pytest.raises(ImportError_) as e:
        sniff(b"a" * (MAX_UPLOAD_BYTES + 1), "big.txt")
    assert e.value.code == "file_too_large"


# --------------------------------------------------------------------------- Smart Paste languages


@pytest.mark.parametrize(
    "text,expected",
    [
        ("1. Savol?\nA) bir\nB) ikki\nC) uch\nD) to‘rt\nTo‘g‘ri javob: C", "C"),
        ("1. Savol?\nA) bir\nB) ikki\nC) uch\nD) to‘rt\nToʻgʻri javob: D", "D"),
        ("1. Savol?\nA) bir\nB) ikki\nC) uch\nD) to'rt\nKalit: B", "B"),
        ("1. Savol?\nA. bir\nB. ikki\nC. uch\nD. to'rt\nANSWER: A", "A"),
        ("1. Вопрос?\nА) один\nБ) два\nВ) три\nГ) четыре\nОтвет: В", "C"),  # Russian order: В = 3rd
        ("1. Вопрос?\nА) один\nБ) два\nВ) три\nГ) четыре\nПравильный ответ: Г", "D"),
        ("1. Савол?\nА) бир\nБ) икки\nВ) уч\nГ) тўрт\nЖавоб: Б", "B"),
        ("1. Q?\nА) one\nВ) two\nС) three\nD) four\nAnswer: С", "C"),  # Cyrillic look-alikes of A B C
        ("1. Savol? A) bir B) ikki C) uch D) to'rt\nJavob: D", "D"),
        ("1. Savol?\nA) bir\nB) ikki\nC) uch\nD) to'rt\n\nJavoblar:\n1-B", "B"),
        ("1. Вопрос?\nА) один\nБ) два\nВ) три\nГ) четыре\n\nОтветы: 1-Г", "D"),
    ],
)
def test_smart_paste_answer_formats(text, expected):
    qs = _questions(parse_smart_paste(text))
    assert len(qs) == 1 and len(qs[0]["options"]) == 4
    assert qs[0]["answer"] == expected


def test_missing_key_is_never_guessed():
    r = svc.import_test_file(fx.smart_paste_text(key_style="none").encode(), "t.txt")
    assert all(q["answer"] == "" for q in _questions(r))
    assert r["report"]["missing_answers"] == 20 and r["report"]["valid_questions"] == 0


def test_key_list_after_questions():
    _assert_ona_tili(svc.import_test_file(fx.smart_paste_text(key_style="key_list").encode(), "t.txt"))


def test_report_flags_duplicates():
    text = "1. Q?\nA) x\nB) x\nC) y\nD) z\nJavob: A\n1. Q2?\nA) a\nB) b\nC) c\nD) d\nJavob: B"
    r = svc.import_test_file(text.encode(), "t.txt")
    assert r["report"]["duplicate_options"] == 1
    assert r["report"]["duplicate_numbers"] == [1]
    assert r["report"]["valid_questions"] == 1


# --------------------------------------------------------------------------- API


@pytest.mark.django_db
def test_import_endpoint_is_preview_only_and_teacher_only():
    from django.core.files.uploadedfile import SimpleUploadedFile

    from apps.tests.models import Test

    teacher = User.objects.create_user(email="si_t@example.com", password="p", role="teacher")
    student = User.objects.create_user(email="si_s@example.com", password="p", role="student")
    api = APIClient()
    url = "/api/v1/teacher/studio/import-file/"
    upload = lambda: SimpleUploadedFile("ona.docx", fx.docx_bytes())  # noqa: E731
    api.force_authenticate(student)
    assert api.post(url, {"file": upload()}, format="multipart").status_code == 403
    api.force_authenticate(teacher)
    before = Test.objects.count()
    r = api.post(url, {"file": upload()}, format="multipart")
    assert r.status_code == 200 and r.data["report"]["total_questions"] == 20
    assert Test.objects.count() == before  # nothing saved
    bad = api.post(url, {"file": SimpleUploadedFile("scan.pdf", fx.pdf_bytes(image_only=True))}, format="multipart")
    assert bad.status_code == 400 and bad.data["code"] == "scanned_pdf"
