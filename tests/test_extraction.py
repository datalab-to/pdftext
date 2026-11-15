import pytest

from pdftext.extraction import paginated_plain_text_output, plain_text_output, dictionary_output
from pdftext.schema import Pages, PdfPasswordError
from pdftext.settings import settings


def test_paginated_output(pdf_path, pdf_doc):
    text = paginated_plain_text_output(pdf_path)
    assert len(text) == len(pdf_doc)
    assert "Subspace" in text[0]

def test_plain_text_output(pdf_path):
    text = plain_text_output(pdf_path)
    assert "Subspace" in text

def test_page_range(pdf_path):
    pages = [0, 1, 3]
    text = paginated_plain_text_output(pdf_path, page_range=pages)
    assert len(text) == len(pages)

def test_json_output(pdf_path, pdf_doc):
    pages: Pages = dictionary_output(pdf_path)
    assert len(pages) == len(pdf_doc)
    assert "Subspace" in pages[0]["blocks"][0]["lines"][0]["spans"][0]["text"]

def test_keep_chars(pdf_path):
    pages: Pages = dictionary_output(pdf_path, keep_chars=True)
    assert "Subspace" in pages[0]["blocks"][0]["lines"][0]["spans"][0]["text"]
    assert "bbox" in pages[0]["blocks"][0]["lines"][0]["spans"][0]["chars"][0]

def test_superscripts(pdf_path):
    pages: Pages = dictionary_output(pdf_path)
    for page in pages:
        for block in page["blocks"]:
            for line in block["lines"]:
                for span in line["spans"]:
                    if span["text"] == "∞":
                        assert span["superscript"] is True
                        return True


def test_line_joining(pdf_path2):
    pages = [11]
    text = plain_text_output(pdf_path2, page_range=pages).lower()
    assert "the axis media control viewer toolbar" in text
    assert "axismediacontrolviewertoolbar" not in text


def test_spans_have_script_flags(pdf_path):
    pages: Pages = dictionary_output(pdf_path, page_range=[0])
    for page in pages:
        for block in page["blocks"]:
            for line in block["lines"]:
                for span in line["spans"]:
                    assert isinstance(span["superscript"], bool)
                    assert isinstance(span["subscript"], bool)


def test_links_and_refs(pdf_path):
    pages: Pages = dictionary_output(pdf_path)
    assert all("refs" in page for page in pages)
    linked_spans = [
        span
        for page in pages
        for block in page["blocks"]
        for line in block["lines"]
        for span in line["spans"]
        if span["url"]
    ]
    assert linked_spans
    # link reconstruction must preserve the script flags
    for span in linked_spans:
        assert "superscript" in span
        assert "subscript" in span


def test_rotated_page(rotated_pdf_path):
    pages: Pages = dictionary_output(rotated_pdf_path, page_range=[0])
    assert pages[0]["rotation"] == 90
    text = plain_text_output(rotated_pdf_path, page_range=[0])
    assert "Subspace" in text


def test_empty_page(empty_pdf_path):
    pages: Pages = dictionary_output(empty_pdf_path)
    assert len(pages) == 1
    assert pages[0]["blocks"] == []


def test_encrypted_requires_password(encrypted_pdf_path):
    with pytest.raises(PdfPasswordError):
        plain_text_output(encrypted_pdf_path)


def test_encrypted_wrong_password(encrypted_pdf_path):
    with pytest.raises(PdfPasswordError):
        plain_text_output(encrypted_pdf_path, password="wrong")


def test_encrypted_with_password(encrypted_pdf_path):
    text = paginated_plain_text_output(encrypted_pdf_path, password="user")
    assert len(text) == 12
    assert "secret text on page 0" in text[0]


def test_encrypted_with_workers(encrypted_pdf_path, monkeypatch):
    monkeypatch.setattr(settings, "WORKER_PAGE_THRESHOLD", 1)
    text = paginated_plain_text_output(encrypted_pdf_path, password="user", workers=2)
    assert len(text) == 12
    assert "secret text on page 11" in text[11]


def test_page_range_out_of_bounds(pdf_path):
    with pytest.raises(ValueError):
        dictionary_output(pdf_path, page_range=[999])
    with pytest.raises(ValueError):
        dictionary_output(pdf_path, page_range=[-1])


def test_workers_match_serial(pdf_path, monkeypatch):
    monkeypatch.setattr(settings, "WORKER_PAGE_THRESHOLD", 1)
    serial = paginated_plain_text_output(pdf_path)
    parallel = paginated_plain_text_output(pdf_path, workers=2)
    assert serial == parallel


def test_flatten_pdf_repeated(pdf_path):
    for _ in range(3):
        pages = dictionary_output(pdf_path, page_range=[0], flatten_pdf=True)
        assert pages


def test_refs_present_with_disable_links(pdf_path):
    pages: Pages = dictionary_output(pdf_path, page_range=[0], disable_links=True)
    assert pages[0]["refs"] == []


def test_rotated_page_bbox_not_inverted(rotated_pdf_path):
    pages: Pages = dictionary_output(rotated_pdf_path, page_range=[0])
    bbox = pages[0]["bbox"]
    assert bbox[0] <= bbox[2] and bbox[1] <= bbox[3], f"inverted page bbox {bbox}"
    assert round(bbox[2] - bbox[0]) == pages[0]["width"]
    assert round(bbox[3] - bbox[1]) == pages[0]["height"]


def test_surrogate_unicode_sanitized(surrogate_pdf_path):
    import json

    pages: Pages = dictionary_output(surrogate_pdf_path, keep_chars=True)
    json.dumps(pages, ensure_ascii=False).encode("utf-8")  # must not raise
    chars = [
        c["char"]
        for b in pages[0]["blocks"]
        for l in b["lines"]
        for s in l["spans"]
        for c in s["chars"]
    ]
    assert "�" in chars and "B" in chars


def test_cjk_text(tmp_path):
    import fitz

    samples = {
        "chinese": ("china-s", "人工智能正在改变世界这是测试"),
        "japanese": ("japan", "人工知能は世界を変えていますこれはテスト"),
        "korea": ("korea", "인공지능이세상을바꾸고있습니다"),
    }
    for name, (font, text) in samples.items():
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 100), text, fontname=font)
        path = tmp_path / f"{name}.pdf"
        doc.save(str(path))
        doc.close()
        extracted = plain_text_output(str(path))
        assert text in extracted.replace(" ", ""), f"{name}: {extracted!r}"


def test_cyrillic_greek_vietnamese(tmp_path):
    import fitz

    text = "Тест Δοκιμή thử nghiệm"
    doc = fitz.open()
    page = doc.new_page()
    rc = page.insert_htmlbox(fitz.Rect(50, 50, 550, 200), f"<p>{text}</p>")
    path = tmp_path / "multi.pdf"
    doc.save(str(path))
    doc.close()
    extracted = plain_text_output(str(path))
    for word in ("Тест", "Δοκιμή", "nghiệm"):
        assert word in extracted, f"missing {word!r} in {extracted!r}"


def test_perpendicular_text_separate_lines(tmp_path):
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 400), "horizontal body text")
    page.insert_text((60, 400), "vertical label", rotate=90)
    path = tmp_path / "perp.pdf"
    doc.save(str(path))
    doc.close()

    pages: Pages = dictionary_output(str(path))
    for block in pages[0]["blocks"]:
        for line in block["lines"]:
            texts = {span["text"].strip() for span in line["spans"] if span["text"].strip()}
            assert not ({"horizontal body text", "vertical label"} <= texts), \
                "perpendicular text merged into one line"


def test_superscript_overlapping_bbox(tmp_path):
    # Tests that candidate superscripts whose bounding box slightly overlaps horizontally
    # with the previous span (x0 < bx1 < x1) are correctly split and identified as superscripts.
    stream_content = b"""BT
/F1 12 Tf
72 700 Td
(mc) Tj
0.7 0 0 0.7 87.5 706 Tm
(2) Tj
ET
"""
    raw_pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj\n"
        b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n"
        b"5 0 obj << /Length " + str(len(stream_content)).encode() + b" >> stream\n"
        + stream_content
        + b"endstream\nendobj\n"
        b"trailer << /Root 1 0 R >>"
    )

    path = tmp_path / "superscript_overlap.pdf"
    path.write_bytes(raw_pdf)

    pages: Pages = dictionary_output(str(path))
    assert len(pages) == 1
    spans = pages[0]["blocks"][0]["lines"][0]["spans"]
    assert len(spans) == 2
    assert spans[0]["text"] == "mc"
    assert spans[0]["superscript"] is False
    assert spans[1]["text"] == "2"
    assert spans[1]["superscript"] is True


def test_get_spans_superscript_overlap():
    import numpy as np
    from pdftext.pdf.chars import PageChars
    from pdftext.pdf.pages import get_spans

    fonts = [{"name": "TestFont", "flags": 0, "size": 10, "weight": 400}]
    # 'x' span followed by '2' with slight horizontal overlap (x0=109.8 < bx1=110.0, x1=115.8 > 110.0)
    boxes = np.array([
        [100.0, 100.0, 110.0, 120.0],
        [109.8, 95.0, 115.8, 107.0],
    ], dtype=np.float64)

    chars = PageChars(
        text="x2",
        codes=np.array([ord("x"), ord("2")], dtype=np.uint32),
        rotations=np.zeros(2, dtype=np.float64),
        boxes=boxes,
        font_ids=np.zeros(2, dtype=np.int32),
        fonts=fonts,
        char_indices=np.array([0, 1], dtype=np.int64),
    )

    spans = get_spans(chars)
    assert len(spans) == 2
    assert spans[0]["text"] == "x"
    assert spans[1]["text"] == "2"

    # Non-advancing character (e.g. an accent positioned on top, x1 <= bx1) should not trigger superscript break
    boxes_non_advancing = np.array([
        [100.0, 100.0, 110.0, 120.0],
        [102.0, 95.0, 108.0, 107.0],
    ], dtype=np.float64)

    chars_non_advancing = PageChars(
        text="x^",
        codes=np.array([ord("x"), ord("^")], dtype=np.uint32),
        rotations=np.zeros(2, dtype=np.float64),
        boxes=boxes_non_advancing,
        font_ids=np.zeros(2, dtype=np.int32),
        fonts=fonts,
        char_indices=np.array([0, 1], dtype=np.int64),
    )

    spans_non_advancing = get_spans(chars_non_advancing)
    assert len(spans_non_advancing) == 1
