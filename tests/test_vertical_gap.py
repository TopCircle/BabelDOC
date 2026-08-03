"""Title→body vertical gap: CJK tall titles must not overlap body (dual layout)."""

from __future__ import annotations

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import Page
from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraphComposition
from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
from babeldoc.format.pdf.document_il.il_version_1 import VisualBbox
from babeldoc.format.pdf.document_il.utils.vertical_gap import (
    DEFAULT_MIN_GAP_PT,
    enforce_title_body_gaps,
    ink_box,
    is_display_title,
    shift_paragraph_y,
)


def _ch(u: str, x: float, y: float, *, size: float, w: float = 10.0) -> PdfCharacter:
    # PDF y-up: y is bottom of glyph, y2 top
    box = Box(x=x, y=y, x2=x + w, y2=y + size * 0.9)
    return PdfCharacter(
        char_unicode=u,
        box=box,
        visual_bbox=VisualBbox(box=Box(x=box.x, y=box.y, x2=box.x2, y2=box.y2)),
        pdf_style=PdfStyle(font_id="F", font_size=size, graphic_state=None),
        scale=1.0,
        advance=w,
    )


def _para(chars: list[PdfCharacter], *, label: str = "plain text") -> PdfParagraph:
    box = ink_box(
        PdfParagraph(
            pdf_paragraph_composition=[
                PdfParagraphComposition(pdf_character=c) for c in chars
            ]
        )
    )
    return PdfParagraph(
        box=box,
        layout_label=label,
        pdf_paragraph_composition=[
            PdfParagraphComposition(pdf_character=c) for c in chars
        ],
        unicode="".join(c.char_unicode or "" for c in chars),
    )


def test_is_display_title_by_size():
    p = _para([_ch("成", 50, 600, size=56.0)], label="plain text")
    assert is_display_title(p)


def test_shift_paragraph_y():
    p = _para([_ch("a", 100, 400, size=12.0)])
    y0 = p.pdf_paragraph_composition[0].pdf_character.box.y
    shift_paragraph_y(p, -20.0)
    assert abs(p.pdf_paragraph_composition[0].pdf_character.box.y - (y0 - 20)) < 0.01


def test_enforce_gap_shifts_overlapping_body():
    """Title ink bottom at y=580; body top at y=590 (overlap) → body shifts down."""
    # Title: large at top of page (high y)
    title_chars = [
        _ch(c, 50 + i * 40, 580, size=56.0, w=38.0) for i, c in enumerate("标题字")
    ]
    # Body starts overlapping (body.y2=590 > title.y=580)
    body_chars = [
        _ch(c, 100 + i * 12, 590 - 12, size=12.0, w=11.0)
        for i, c in enumerate("正文开始在这里足够长")
    ]
    title = _para(title_chars, label="title")
    body = _para(body_chars, label="plain text")
    page = Page(
        page_number=0,
        mediabox=Box(x=0, y=0, x2=612, y2=792),
        pdf_paragraph=[title, body],
    )

    t_ink = ink_box(title)
    b_ink_before = ink_box(body)
    assert t_ink and b_ink_before
    # Overlap or too tight
    assert b_ink_before.y2 > t_ink.y - DEFAULT_MIN_GAP_PT

    n = enforce_title_body_gaps(page, min_gap=DEFAULT_MIN_GAP_PT)
    assert n >= 1
    b_ink = ink_box(body)
    assert b_ink is not None
    # body top must be at or below title bottom - gap
    assert b_ink.y2 <= t_ink.y - DEFAULT_MIN_GAP_PT + 0.5


def test_no_shift_when_gap_already_enough():
    title = _para(
        [_ch(c, 50 + i * 40, 600, size=56.0, w=38.0) for i, c in enumerate("大标题")],
        label="title",
    )
    # body well below: title.y ≈ 600, body top y2 ≈ 500
    body = _para(
        [
            _ch(c, 100 + i * 12, 500 - 12, size=12.0, w=11.0)
            for i, c in enumerate("正文足够远")
        ],
        label="plain text",
    )
    page = Page(page_number=0, pdf_paragraph=[title, body])
    n = enforce_title_body_gaps(page, min_gap=14.0)
    assert n == 0
