"""Merge stacked narrow callout lines into one paragraph."""

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
    # Bottom tip first in list (as stream may emit); boxes stacked
    paras = [
        _line_para("the program.", x=450, y=100, w=80),
        _line_para("plans and stick", x=420, y=120, w=110),
        _line_para("In order to work", x=320, y=200, w=180),
    ]
    # Ensure vertical stack upper has higher y2
    n = merge_stacked_narrow_callout_paragraphs(paras)
    assert n >= 1
    assert len(paras) < 3
    # Union should be relatively wide
    assert paras[0].box.x2 - paras[0].box.x > 100
    # Compositions top-first after merge
    comps = paras[0].pdf_paragraph_composition
    if len(comps) >= 2:
        y2s = [c.pdf_line.box.y2 for c in comps]
        assert y2s == sorted(y2s, reverse=True)


def test_merge_non_list_adjacent_ultra_narrow_tips():
    """Y-pass merges ultra-narrow tips even when a wide body splits the list."""
    tip = _line_para("the program.", x=450, y=100, w=80)
    mid = _line_para("plans and stick", x=420, y=120, w=100)
    body = _line_para(
        "Wide body paragraph that must stay separate.",
        x=50,
        y=300,
        w=400,
    )
    # tip/mid not list-adjacent; both ultra-narrow ≤120
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
    """0.6.4.48 regression: width≤220 y-sort merged unrelated short paras."""
    a = _line_para("As they say, actions speak.", x=50, y=300, w=200)
    b = _line_para("Short quote line two here.", x=50, y=280, w=200)
    blocker = _line_para("BLOCKER wide body text xxxx", x=50, y=500, w=400)
    # Not list-adjacent; medium width → y-pass must not merge
    paras = [a, blocker, b]
    n = merge_stacked_narrow_callout_paragraphs(paras)
    assert n == 0
    assert len(paras) == 3
