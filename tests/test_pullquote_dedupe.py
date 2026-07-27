"""Pull-quote near-duplicate skip (Day6 side callout)."""

from __future__ import annotations

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import Page
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
from babeldoc.format.pdf.document_il.utils.pullquote_dedupe import (
    is_pullquote_duplicate_of_body,
)
from babeldoc.format.pdf.document_il.utils.pullquote_dedupe import normalize_for_dup


def _para(text: str, *, x: float, x2: float, y: float = 100.0) -> PdfParagraph:
    return PdfParagraph(
        box=Box(x=x, y=y, x2=x2, y2=y + 40),
        pdf_style=PdfStyle(font_id="base", font_size=12.0, graphic_state=None),
        pdf_paragraph_composition=[],
        unicode=text,
    )


def _page(*paras: PdfParagraph) -> Page:
    p = Page(
        page_number=0,
        mediabox=Box(x=0, y=0, x2=612, y2=792),
        cropbox=Box(x=0, y=0, x2=612, y2=792),
    )
    p.pdf_paragraph = list(paras)
    return p


QUOTE = (
    "Since her orgasm is essentially an intense contraction of her PC and "
    "pelvic floor muscles, strengthening them increases blood flow to the "
    "area and enables her to experience a deeper pleasure sensation and a "
    "repeated series of pulses"
)


def test_normalize_strips_punct():
    assert normalize_for_dup("Hello, World!") == "helloworld"


def test_side_callout_contained_in_body_is_duplicate():
    body = _para(
        f'"{QUOTE}," says Laura Berman, author of The Passion Prescription.',
        x=102,
        x2=360,
    )
    callout = _para(QUOTE, x=360, x2=560)  # right-side narrow band
    page = _page(body, callout)
    assert is_pullquote_duplicate_of_body(callout, page) is True
    assert is_pullquote_duplicate_of_body(body, page) is False


def test_unique_body_not_duplicate():
    a = _para("Unique paragraph about Kegels and exercise.", x=102, x2=500)
    b = _para("Something completely different about foreplay.", x=102, x2=500)
    page = _page(a, b)
    assert is_pullquote_duplicate_of_body(a, page) is False
