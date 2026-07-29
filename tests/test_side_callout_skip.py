"""Side-callout MT skip (pull-quote duplicate + ultra-narrow strip)."""

from __future__ import annotations

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import Page
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
from babeldoc.format.pdf.document_il.utils.side_callout_skip import (
    is_pullquote_duplicate_of_body,
)
from babeldoc.format.pdf.document_il.utils.side_callout_skip import (
    is_ultra_narrow_side_callout,
)
from babeldoc.format.pdf.document_il.utils.side_callout_skip import normalize_for_dup
from babeldoc.format.pdf.document_il.utils.side_callout_skip import (
    should_skip_side_callout_mt,
)


def _para(
    text: str,
    *,
    x: float,
    x2: float,
    y: float = 100.0,
    y2: float | None = None,
    layout_label: str | None = None,
) -> PdfParagraph:
    top = y2 if y2 is not None else y + 40
    p = PdfParagraph(
        box=Box(x=x, y=y, x2=x2, y2=top),
        pdf_style=PdfStyle(font_id="base", font_size=12.0, graphic_state=None),
        pdf_paragraph_composition=[],
        unicode=text,
    )
    if layout_label is not None:
        p.layout_label = layout_label
    return p


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
    assert should_skip_side_callout_mt(callout, page) is True


def test_unique_body_not_duplicate():
    a = _para("Unique paragraph about Kegels and exercise.", x=102, x2=500)
    b = _para("Something completely different about foreplay.", x=102, x2=500)
    page = _page(a, b)
    assert is_pullquote_duplicate_of_body(a, page) is False


def test_ultra_narrow_tall_callout_skipped():
    """OA p8 red strip ~80×120 at x≈429 on letter — keep EN, do not tower ZH."""
    callout = _para(
        "The best way for you to learn the clit-stimulating techniques "
        "that work best for her is going to be by watching her pleasure herself!",
        x=429,
        x2=509,
        y=361,
        y2=481,
        layout_label="plain text",
    )
    page = _page(callout)
    assert is_ultra_narrow_side_callout(callout, page) is True
    assert should_skip_side_callout_mt(callout, page) is True


def test_left_column_body_not_ultra_narrow_callout():
    """OA p7 left column ~105pt at x≈102 — body beside photo, still translate."""
    body = _para(
        "Women like different things, the same as some men enjoy hard touch "
        "and some soft, some like a little anal play,",
        x=102,
        x2=207,
        y=78,
        y2=168,
        layout_label="plain text",
    )
    page = _page(body)
    assert is_ultra_narrow_side_callout(body, page) is False
    assert should_skip_side_callout_mt(body, page) is False


def test_right_half_narrow_width_alone_still_needs_height():
    """width_ratio < 0.18 on right half but short height is not a tall strip."""
    short = _para(
        "Short callout text that is long enough in chars but not tall enough.",
        x=430,
        x2=500,
        y=400,
        y2=420,  # h=20, w=70 → h/w < 0.9
        layout_label="plain text",
    )
    page = _page(short)
    assert is_ultra_narrow_side_callout(short, page) is False


def test_title_not_ultra_narrow_even_if_narrow_box():
    title = _para(
        "WHO HAS ORGASMS?",
        x=430,
        x2=510,
        y=300,
        y2=420,
        layout_label="title",
    )
    page = _page(title)
    assert is_ultra_narrow_side_callout(title, page) is False


def test_compat_reexport_from_pullquote_dedupe():
    """Older imports via pullquote_dedupe still resolve."""
    from babeldoc.format.pdf.document_il.utils import pullquote_dedupe as pq

    callout = _para(
        "The best way for you to learn the clit-stimulating techniques "
        "that work best for her is going to be by watching her pleasure herself!",
        x=429,
        x2=509,
        y=361,
        y2=481,
    )
    page = _page(callout)
    assert pq.is_ultra_narrow_side_callout(callout, page) is True
    assert pq.should_skip_side_callout_mt(callout, page) is True
