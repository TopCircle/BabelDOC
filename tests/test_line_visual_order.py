"""Sort paragraph lines when stream climbs the page (bottom→top emit)."""

from __future__ import annotations

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter
from babeldoc.format.pdf.document_il.il_version_1 import PdfLine
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraphComposition
from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
from babeldoc.format.pdf.document_il.il_version_1 import VisualBbox
from babeldoc.format.pdf.document_il.utils.stream_order import (
    sort_line_compositions_if_stream_climbs,
)


def _ch(text: str, x: float, y: float = 100.0, w: float = 8.0) -> PdfCharacter:
    box = Box(x=x, y=y, x2=x + w, y2=y + 12)
    return PdfCharacter(
        pdf_character_id=None,
        char_unicode=text,
        box=box,
        visual_bbox=VisualBbox(box=box),
        pdf_style=PdfStyle(font_id="base", font_size=12.0, graphic_state=None),
        scale=1.0,
        advance=w,
        vertical=False,
        xobj_id=None,
    )


def _line(text: str, *, y: float, x: float = 100.0) -> PdfParagraphComposition:
    chars = [_ch(c, x + i * 8, y=y) for i, c in enumerate(text)]
    line = PdfLine(
        box=Box(x=x, y=y, x2=x + 8 * len(text), y2=y + 12),
        pdf_character=chars,
    )
    return PdfParagraphComposition(pdf_line=line)


def test_sorts_when_stream_climbs_page():
    comps = [
        _line("bottom line start", y=100),
        _line("middle", y=130),
        _line("top line end", y=160),
    ]
    sorted_c = sort_line_compositions_if_stream_climbs(comps)
    assert sorted_c is not None
    tops = [c.pdf_line.box.y2 for c in sorted_c]
    assert tops == sorted(tops, reverse=True)
    first = "".join(ch.char_unicode for ch in sorted_c[0].pdf_line.pdf_character)
    assert first.startswith("top")


def test_no_sort_when_stream_already_top_down():
    comps = [
        _line("top first", y=160),
        _line("middle", y=130),
        _line("bottom last", y=100),
    ]
    assert sort_line_compositions_if_stream_climbs(comps) is None


def test_no_sort_when_mixed_non_line_composition():
    """Formula/non-line interleave → no-op (do not dump non-lines to end)."""
    comps = [
        _line("a", y=100),
        PdfParagraphComposition(pdf_character=_ch("x", 0)),
        _line("b", y=140),
    ]
    assert sort_line_compositions_if_stream_climbs(comps) is None


def test_multiline_stream_climb_reorders_callout_body():
    """OA TAKING CHARGE: paint bottom line first → MT must see top line first."""
    from babeldoc.format.pdf.document_il.utils.stream_order import (
        maybe_reorder_multiline_stream_climb,
        is_multiline_stream_climbing,
    )

    # Stream order: tip (low y) first, then climb (PDF y-up)
    lines_bottom_first = [
        ("the program.", 100.0),
        ("plans and stick", 115.0),
        ("the work make", 130.0),
        ("man who is prepared", 145.0),
        ("intimacy await", 160.0),
        ("Mind-blowing orgasms", 175.0),
        ("start directing flow", 190.0),
        ("you will need to take", 205.0),
        ("In order to work through", 220.0),
    ]
    chars: list = []
    for text, y in lines_bottom_first:
        for i, c in enumerate(text):
            chars.append(_ch(c, 300 + i * 6, y=y))
    assert is_multiline_stream_climbing(chars)
    # Narrow width (~200pt) allows reorder
    ordered = maybe_reorder_multiline_stream_climb(chars, para_width=200.0)
    assert ordered is not chars
    head = "".join(c.char_unicode for c in ordered[: len("In order")])
    assert head.startswith("In order")
    # Wide body must not reorder
    assert maybe_reorder_multiline_stream_climb(chars, para_width=400.0) is chars
