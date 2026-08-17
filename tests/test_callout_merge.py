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


def test_right_pinned_wrap_lines_merge_above_220():
    """OA p19 TAKING CHARGE: wrap rows are 228–255pt, right edge pinned ~570.

    The 220pt callout cap must stay (p5 regression). Wrap-column rows need a
    separate right-pin merge so CJK can reflow as one WRAP_COLUMN.
    """
    rows = [
        _line_para("To complete the exercises in this book,", x=315.0, y=420, w=255.0),
        _line_para("you will need to take charge of your sex life and", x=323.0, y=400, w=246.0),
        _line_para("start directing your", x=341.5, y=380, w=228.0),
        _line_para("relationship. Mind-blowing orgasms await.", x=376.0, y=360, w=194.0),
    ]
    for p, x, y in zip(
        rows,
        (315.0, 323.0, 341.5, 376.0),
        (420.0, 400.0, 380.0, 360.0),
        strict=True,
    ):
        p.box = Box(x=x, y=y, x2=570.0, y2=y + 14)
    n = merge_stacked_narrow_callout_paragraphs(rows)
    assert n >= 2
    assert len(rows) == 1
    from babeldoc.format.pdf.document_il.utils.layout_helper import (
        get_paragraph_unicode,
    )

    u = get_paragraph_unicode(rows[0]) or ""
    assert "exercises" in u
    assert "orgasms" in u
    assert abs(rows[0].box.x2 - 570.0) < 0.1
    assert abs(rows[0].box.x - 315.0) < 0.1


def test_right_pinned_keeps_merging_after_union_exceeds_280():
    """After the first absorb the host box is the wrap column (~290pt)."""
    rows = [
        _line_para("line one of the wrap column text xx", x=315.0, y=420, w=255.0),
        _line_para("line two wrap column text here xxx", x=323.0, y=400, w=247.0),
        _line_para("line three wrap column text xxxxx", x=341.5, y=380, w=228.5),
        _line_para("line four wrap column text xx", x=376.0, y=360, w=194.0),
        _line_para("line five shorter wrap tail", x=401.5, y=340, w=168.5),
    ]
    for p, x, y in zip(
        rows,
        (315.0, 323.0, 341.5, 376.0, 401.5),
        (420.0, 400.0, 380.0, 360.0, 340.0),
        strict=True,
    ):
        p.box = Box(x=x, y=y, x2=570.0, y2=y + 14)
    n = merge_stacked_narrow_callout_paragraphs(rows)
    assert n >= 3
    assert len(rows) == 1
    assert abs(rows[0].box.x - 315.0) < 0.1
    assert abs(rows[0].box.x2 - 570.0) < 0.1


def test_right_pinned_absorbs_next_line_into_multirow_wrap_host():
    """OA p19: existing wrap cluster (one tall composition) + the line above."""
    host = _line_para(
        "relationship. Mindblowing orgasms await the prepared man.",
        x=375.9,
        y=198.0,
        w=193.6,
    )
    host.box = Box(x=375.9, y=197.9, x2=569.5, y2=284.9)
    above = _line_para(
        "start directing the flow of development in your",
        x=341.5,
        y=287.9,
        w=228.3,
    )
    above.box = Box(x=341.5, y=287.9, x2=569.9, y2=299.9)
    paras = [above, host]
    n = merge_stacked_narrow_callout_paragraphs(paras)
    assert n >= 1
    assert len(paras) == 1
    assert paras[0].box.x <= 341.5 + 0.1
    assert paras[0].box.x2 >= 569.5 - 0.1


def test_debug_stub_does_not_block_right_pinned_wrap_merge():
    """OA p19: fallback_line stub sits in the 3pt gap between wrap rows."""
    host = _line_para("relationship. Mindblowing orgasms await.", x=375.9, y=198.0, w=193.6)
    host.box = Box(x=375.9, y=197.9, x2=569.5, y2=284.9)
    above = _line_para("start directing the flow of development", x=341.5, y=287.9, w=228.3)
    above.box = Box(x=341.5, y=287.9, x2=569.9, y2=299.9)
    stub = _line_para("fallback_line", x=447.7, y=284.9, w=71.5)
    stub.box = Box(x=447.7, y=284.9, x2=519.2, y2=289.9)
    stub.unicode = "fallback_line"
    paras = [above, stub, host]
    n = merge_stacked_narrow_callout_paragraphs(paras)
    assert n >= 1
    from babeldoc.format.pdf.document_il.utils.layout_helper import (
        get_paragraph_unicode,
    )

    joined = " ".join(get_paragraph_unicode(p) or "" for p in paras)
    assert "relationship" in joined
    assert "directing" in joined
    assert len([p for p in paras if (p.unicode or "") != "fallback_line"]) == 1


def test_right_pinned_does_not_merge_unpinned_body():
    """Full-measure body (x2 not pinned together) must not join a wrap stack."""
    wrap = _line_para("start directing your", x=341.5, y=380, w=228.0)
    wrap.box = Box(x=341.5, y=380, x2=570.0, y2=394)
    body = _line_para(
        "If you want a little extra spice in the bedroom you have to take charge.",
        x=102.0,
        y=350,
        w=470.0,
    )
    body.box = Box(x=102.0, y=350, x2=572.0, y2=380)
    paras = [wrap, body]
    n = merge_stacked_narrow_callout_paragraphs(paras)
    assert n == 0
    assert len(paras) == 2
