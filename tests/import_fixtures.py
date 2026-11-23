"""Build realistic import files (DOCX/XLSX/PDF/CSV) for Smart Import tests.

Pure test helpers — authored sample content only, no real student data.
Also runnable: ``python -m tests.import_fixtures <dir>`` writes the files
the real-browser E2E uploads.
"""

from __future__ import annotations

import io
import os
import sys
import zipfile
from xml.sax.saxutils import escape

# 20 Ona tili questions. Q20 carries a deliberately WRONG key ("D"; the right
# answer is "A") so the E2E can prove a teacher corrects keys before publishing.
ONA_TILI = [
    ("Qaysi gapda undalma mavjud?", ["Bahor keldi.", "Do‘stim, kel!", "U o‘qidi.", "Kitob stolda."], "B"),
    ("“O‘tkan kunlar” romani muallifi kim?", ["Cho‘lpon", "Abdulla Qodiriy", "Oybek", "G‘afur G‘ulom"], "B"),
    ("Ot so‘z turkumi nimani bildiradi?", ["belgi", "predmet", "harakat", "miqdor"], "B"),
    ("Fe’l nimani bildiradi?", ["harakat", "predmet", "belgi", "miqdor"], "A"),
    ("O‘zbek alifbosida nechta unli bor?", ["5", "6", "7", "8"], "B"),
    ("Qaysi so‘z sifat?", ["chiroyli", "yugurmoq", "kitob", "tez-tez"], "A"),
    ("Qaysi qatorda olmosh berilgan?", ["men, sen, u", "bir, ikki", "katta, kichik", "bordi, keldi"], "A"),
    ("“Kecha va kunduz” asari muallifi?", ["Oybek", "Cho‘lpon", "Hamza", "Qodiriy"], "B"),
    ("Tinish belgisi qaysi?", ["vergul", "harf", "bo‘g‘in", "tovush"], "A"),
    ("Qaysi so‘zda tutuq belgisi to‘g‘ri yozilgan?", ["ma’no", "mano", "ma‘no", "ma-no"], "A"),
    ("Sintaksis nimani o‘rganadi?", ["gap va so‘z birikmasini", "tovushlarni", "so‘z yasalishini", "imloni"], "A"),
    ("Qaysi gap so‘roq gap?", ["Kel.", "Keldingmi?", "Qanday go‘zal!", "U keldi."], "B"),
    ("Leksikologiya nimani o‘rganadi?", ["so‘z boyligini", "gap tuzilishini", "tovushlarni", "tinish belgilarini"], "A"),
    ("Qaysi so‘z ko‘chma ma’noda?", ["oltin qo‘l", "oltin uzuk", "temir eshik", "yog‘och stol"], "A"),
    ("“Alpomish” qanday asar?", ["doston", "roman", "hikoya", "she’r"], "A"),
    ("Morfologiya bo‘limi?", ["so‘z turkumlari", "gap bo‘laklari", "uslublar", "imlo"], "A"),
    ("Qaysi so‘z ravish?", ["tez", "tezlik", "tezkor", "tezlamoq"], "A"),
    ("Uslubiyat nimani o‘rganadi?", ["nutq uslublarini", "tovushlarni", "so‘z tarkibini", "gap turlarini"], "A"),
    ("Qaysi gapda ega bor?", ["Bola kitob o‘qidi.", "Yomg‘ir!", "Qorong‘i.", "Sovuq."], "A"),
    ("Fonetika nimani o‘rganadi?", ["tovushlarni", "so‘zlarni", "gaplarni", "matnni"], "D"),
]


def smart_paste_text(items=ONA_TILI, key_style: str = "javob") -> str:
    lines = []
    for i, (q, opts, ans) in enumerate(items, start=1):
        lines.append(f"{i}. {q}")
        lines.extend(f"{'ABCD'[j]}) {o}" for j, o in enumerate(opts))
        if key_style == "javob":
            lines.append(f"Javob: {ans}")
        lines.append("")
    if key_style == "key_list":
        lines.append("Kalitlar:")
        lines.extend(f"{i}-{ans}" for i, (_, _, ans) in enumerate(items, start=1))
    return "\n".join(lines)


def csv_bytes(items=ONA_TILI, delimiter: str = ";", encoding: str = "utf-8-sig") -> bytes:
    import csv

    buf = io.StringIO()
    w = csv.writer(buf, delimiter=delimiter)
    w.writerow(["№", "Savol", "A", "B", "C", "D", "Javob", "Ball"])
    for i, (q, opts, ans) in enumerate(items, start=1):
        w.writerow([i, q, *opts, ans, 1])
    return buf.getvalue().encode(encoding)


def xlsx_bytes(items=ONA_TILI) -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["Savol", "A", "B", "C", "D", "To‘g‘ri javob", "Izoh"])
    for q, opts, ans in items:
        ws.append([q, *opts, ans, ""])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _docx_para(text: str, numbered: bool = False) -> str:
    num = '<w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr>' if numbered else ""
    return f'<w:p>{num}<w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>'


def docx_bytes(text: str | None = None, items=ONA_TILI) -> bytes:
    """A minimal but real WordprocessingML package (opens in Word/LibreOffice)."""
    body_text = text if text is not None else smart_paste_text(items)
    paras = "".join(_docx_para(line) for line in body_text.split("\n"))
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{paras}<w:sectPr/></w:body></w:document>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/></Relationships>'
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", document)
    return buf.getvalue()


FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def pdf_bytes(text: str | None = None, items=ONA_TILI, image_only: bool = False) -> bytes:
    """Selectable-text PDF (needs a Unicode TTF), or an image-only page (a 'scan')."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    if image_only:
        c.rect(50, 500, 300, 200, fill=1)
        c.showPage()
        c.save()
        return buf.getvalue()
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    pdfmetrics.registerFont(TTFont("DejaVu", FONT))
    c.setFont("DejaVu", 10)
    y = 800
    for line in (text if text is not None else smart_paste_text(items)).split("\n"):
        if y < 50:
            c.showPage()
            c.setFont("DejaVu", 10)
            y = 800
        c.drawString(40, y, line)
        y -= 14
    c.showPage()
    c.save()
    return buf.getvalue()


def has_unicode_font() -> bool:
    return os.path.exists(FONT)


def pptx_bytes(items=ONA_TILI, *, image_only_slide: bool = True) -> bytes:
    """A real PowerPoint deck (python-pptx, test-only dependency).

    Layout teachers actually use:
    * slide 1: title;
    * one slide per question for Q1–Q8 (text box, options A–D); Q1's answer is
      only in the speaker notes ("Javob: B"), Q2's notes hold commentary that
      must NOT leak into the question;
    * Q9 spread over two slides (question text, then its options);
    * a slide with a table of Q10–Q12 (Savol | A | B | C | D);
    * an image-only slide (when ``image_only_slide``);
    * a final answer-key slide ("Kalitlar: 2-B, 3-B, …").
    """
    from pptx import Presentation
    from pptx.util import Inches

    prs = Presentation()
    blank = prs.slide_layouts[6]
    title = prs.slides.add_slide(prs.slide_layouts[0])
    title.shapes.title.text = "Ona tili — 12 savol"

    def box(slide, text, top=1.0):
        tb = slide.shapes.add_textbox(Inches(0.5), Inches(top), Inches(9), Inches(5))
        tf = tb.text_frame
        lines = text.split("\n")
        tf.text = lines[0]
        for line in lines[1:]:
            tf.add_paragraph().text = line
        return tb

    for i, (q, opts, _ans) in enumerate(items[:8], start=1):
        s = prs.slides.add_slide(blank)
        box(s, "\n".join([f"{i}. {q}"] + [f"{'ABCD'[j]}) {o}" for j, o in enumerate(opts)]))
        if i == 1:
            s.notes_slide.notes_text_frame.text = f"Javob: {items[0][2]}"
        if i == 2:
            s.notes_slide.notes_text_frame.text = "Bu savolni darsda tushuntiring, A variant ham muhokama qilinadi."
    q9, o9, _ = items[8]
    box(prs.slides.add_slide(blank), f"9. {q9}")
    box(prs.slides.add_slide(blank), "\n".join(f"{'ABCD'[j]}) {o}" for j, o in enumerate(o9)))

    s = prs.slides.add_slide(blank)
    table = s.shapes.add_table(4, 5, Inches(0.3), Inches(0.5), Inches(9.4), Inches(3)).table
    for c, h in enumerate(["Savol", "A", "B", "C", "D"]):
        table.cell(0, c).text = h
    for r, (q, opts, _ans) in enumerate(items[9:12], start=1):
        table.cell(r, 0).text = f"{9 + r}. {q}"
        for c, o in enumerate(opts, start=1):
            table.cell(r, c).text = o

    if image_only_slide:
        img = prs.slides.add_slide(blank)
        png = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
            b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        img.shapes.add_picture(io.BytesIO(png), Inches(1), Inches(1), Inches(3), Inches(3))

    key = prs.slides.add_slide(blank)
    box(key, "Kalitlar:\n" + "\n".join(f"{i}-{ans}" for i, (_, _, ans) in enumerate(items[:9], start=1) if i > 1))
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


if __name__ == "__main__":  # pragma: no cover - E2E helper
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    files = {
        "ona_tili_20.docx": docx_bytes(),
        "ona_tili_20.xlsx": xlsx_bytes(),
        "ona_tili_20.csv": csv_bytes(),
        "ona_tili_20.txt": smart_paste_text().encode("utf-8"),
        "ona_tili_12.pptx": pptx_bytes(),
    }
    if has_unicode_font():
        files["ona_tili_20.pdf"] = pdf_bytes()
    for name, data in files.items():
        with open(os.path.join(out, name), "wb") as fh:
            fh.write(data)
    print("\n".join(sorted(files)))
