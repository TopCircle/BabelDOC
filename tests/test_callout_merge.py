"""Merge stacked narrow callout lines and horizontal prefix pairs."""

from __future__ import annotations

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter
from babeldoc.format.pdf.document_il.il_version_1 import PdfLine
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraphComposition
from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
from babeldoc.format.pdf.document_il.il_version_1 import VisualBbox
from babeldoc.format.pdf.document_il.utils.callout_merge import (
    merge_stacked_narrow_callout_paragraphs,
)


def _line_para(text: str, *, x: float, y: float, w: float) -> PdfParagraph:
    chars = []
    cx = x
    for ch in text:
        box = Box(x=cx, y=y, x2=cx + 6, y2=y + 12)
        chars.append(
            PdfCharacter(
                char_unicode=ch,
                box=box,
                visual_bbox=VisualBbox(box=box),
                pdf_style=PdfStyle(font_id="b", font_size=12.0, graphic_state=None),
                scale=1.0,
                advance=6,
            )
        )
        cx += 6
    line = PdfLine(box=Box(x=x, y=y, x2=x + w, y2=y + 12), pdf_character=chars)
    return PdfParagraph(
        box=Box(x=x, y=y, x2=x + w, y2=y + 12),
        pdf_paragraph_composition=[PdfParagraphComposition(pdf_line=line)],
        unicode=text,
        layout_label="plain text",
        xobj_id=-1,
    )


def test_merge_triangle_callout_lines():
    paras = [
        _line_para("the program.", x=450, y=100, w=80),
        _line_para("plans and stick", x=420, y=120, w=110),
        _line_para("In order to work", x=320, y=200, w=180),
    ]
    n = merge_stacked_narrow_callout_paragraphs(paras)
    assert n >= 1
    assert len(paras) < 3
    assert paras[0].box.x2 - paras[0].box.x > 100
    comps = paras[0].pdf_paragraph_composition
    if len(comps) >= 2:
        y2s = [c.pdf_line.box.y2 for c in comps]
        assert y2s == sorted(y2s, reverse=True)


def test_merge_non_list_adjacent_ultra_narrow_tips():
    tip = _line_para("the program.", x=450, y=100, w=80)
    mid = _line_para("plans and stick", x=420, y=120, w=100)
    body = _line_para(
        "Wide body paragraph that must stay separate.",
        x=50,
        y=300,
        w=400,
    )
    paras = [tip, body, mid]
    n = merge_stacked_narrow_callout_paragraphs(paras)
    assert n >= 1
    assert len(paras) == 2
    texts = []
    for p in paras:
        for c in p.pdf_paragraph_composition or []:
            if c.pdf_line:
                texts.append(
                    "".join(ch.char_unicode for ch in c.pdf_line.pdf_character)
                )
    joined = " ".join(texts)
    assert "Wide body" in joined
    assert "the program." in joined
    assert "plans and stick" in joined


def test_does_not_y_merge_medium_width_across_page():
    """0.6.4.48: medium-width strips must not y-merge across a blocker."""
    a = _line_para("As they say, actions speak.", x=50, y=300, w=200)
    b = _line_para("Short quote line two here.", x=50, y=280, w=200)
    blocker = _line_para("BLOCKER wide body text xxxx", x=50, y=500, w=400)
    paras = [a, blocker, b]
    n = merge_stacked_narrow_callout_paragraphs(paras)
    assert n == 0
    assert len(paras) == 3


def test_vertical_gap_22_does_not_merge_sparse_medium_stack():
    """Regression: vertical constants stay 22pt / 220pt (not loosened for p5)."""
    # Same column, width 200, gap 25pt > 22 → list-adjacent must not merge
    upper = _line_para("As they say, actions speak louder.", x=50, y=320, w=200)
    # y2 of lower = 280+12=292; upper.y=320 → gap = 320-292 = 28 > 22
    lower = _line_para("Short second line of body text.", x=50, y=280, w=200)
    upper.box = Box(x=50, y=320, x2=250, y2=332)
    lower.box = Box(x=50, y=280, x2=250, y2=292)
    # list-adjacent in discovery order with upper first by y2
    paras = [upper, lower]
    n = merge_stacked_narrow_callout_paragraphs(paras)
    assert n == 0
    assert len(paras) == 2


def test_merge_horizontal_prefix_callout_oa_p5():
    """Left short clause + right fuller sentence → one unit."""
    left = _line_para(
        "This is the focus of a large portion of the book.",
        x=40,
        y=400,
        w=120,
    )
    right = _line_para(
        "This is the focus of a large portion of the book: learning the seven "
        "essential movements required to perform the fifty trigasmic positions "
        "which follow. Before you focus too closely on the new moves, we study "
        "the nature of female orgasm.",
        x=180,
        y=380,
        w=200,
    )
    right.box = Box(x=180, y=380, x2=380, y2=430)
    left.box = Box(x=40, y=400, x2=160, y2=425)
    paras = [left, right]
    n = merge_stacked_narrow_callout_paragraphs(paras)
    assert n >= 1
    assert len(paras) == 1
    u = paras[0].unicode or ""
    assert "learning the seven" in u or "Before you focus" in u
    assert paras[0].box.x2 - paras[0].box.x > 150


def test_horizontal_prefix_does_not_merge_unrelated():
    left = _line_para("Short left aside.", x=40, y=400, w=100)
    right = _line_para(
        "Completely different body paragraph about something else entirely.",
        x=180,
        y=390,
        w=250,
    )
    right.box = Box(x=180, y=390, x2=430, y2=420)
    paras = [left, right]
    n = merge_stacked_narrow_callout_paragraphs(paras)
    assert n == 0
    assert len(paras) == 2
