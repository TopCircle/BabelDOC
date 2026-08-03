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


def test_merge_non_list_adjacent_stack():
    """B3: merge by visual y even when a wide body splits the list."""
    tip = _line_para("the program.", x=450, y=100, w=80)
    mid = _line_para("plans and stick", x=420, y=120, w=110)
    top = _line_para("In order to work", x=320, y=140, w=180)
    body = _line_para(
        "Wide body paragraph that must stay separate.",
        x=50,
        y=300,
        w=400,
    )
    # Stream order: tip, body, mid, top — list-adjacent merge would miss stack
    paras = [tip, body, mid, top]
    n = merge_stacked_narrow_callout_paragraphs(paras)
    assert n >= 2
    assert len(paras) == 2
    # body preserved; callout is the other
    texts = []
    for p in paras:
        for c in p.pdf_paragraph_composition or []:
            if c.pdf_line:
                texts.append(
                    "".join(ch.char_unicode for ch in c.pdf_line.pdf_character)
                )
    joined = " ".join(texts)
    assert "Wide body" in joined
    assert "In order to work" in joined
    assert "the program." in joined