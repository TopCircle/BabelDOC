"""A tall en-dash belongs to the list item on its right."""

from __future__ import annotations

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter
from babeldoc.format.pdf.document_il.il_version_1 import PdfLine
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraphComposition
from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
from babeldoc.format.pdf.document_il.il_version_1 import VisualBbox
from babeldoc.format.pdf.document_il.utils.dash_bullet_join import join_dash_bullets


def _char(ch: str, x: float, y: float, x2: float, y2: float, size: float) -> PdfCharacter:
    box = Box(x=x, y=y, x2=x2, y2=y2)
    return PdfCharacter(
        char_unicode=ch,
        box=box,
        visual_bbox=VisualBbox(box=Box(x=x, y=y, x2=x2, y2=y2)),
        pdf_style=PdfStyle(font_id="F", font_size=size),
    )


def _line(text: str, x: float, y: float, *, size: float = 12.0, width: float = 8.0):
    chars = []
    cx = x
    for ch in text:
        chars.append(_char(ch, cx, y, cx + width, y + size, size))
        cx += width
    return PdfParagraphComposition(
        pdf_line=PdfLine(
            box=Box(x=x, y=y, x2=cx, y2=y + size),
            pdf_character=chars,
        )
    )


def _para(*comps: PdfParagraphComposition) -> PdfParagraph:
    return PdfParagraph(pdf_paragraph_composition=list(comps))


def _text(paragraph: PdfParagraph) -> str:
    parts = []
    for comp in paragraph.pdf_paragraph_composition or []:
        line = comp.pdf_line
        if line is None:
            continue
        parts.append("".join(char.char_unicode or "" for char in line.pdf_character))
    return "".join(parts)


def test_a_lone_dash_joins_the_item_on_its_right():
    dash = _para(_line("\u2013", 141.0, 161.0, size=30.0, width=15.0))
    item = _para(_line("While she's wearing", 162.0, 167.8))
    paras = [dash, item]
    assert join_dash_bullets(paras) == 1
    assert paras == [item]
    assert _text(item).startswith("\u2013")
    assert "While" in _text(item)


def test_a_heading_gives_its_trailing_dash_to_the_item():
    heading = _para(
        _line("1. Beginner", 102.0, 191.5),
        _line("\u2013", 141.0, 161.0, size=30.0, width=15.0),
    )
    item = _para(_line("While she's wearing", 162.0, 167.8))
    paras = [heading, item]
    assert join_dash_bullets(paras) == 1
    assert heading in paras
    assert "\u2013" not in _text(heading)
    assert _text(heading).startswith("1. Beginner")
    assert _text(item).startswith("\u2013")


def test_a_hyphenated_word_stays_split():
    stem = _para(_line("stimula-", 72.0, 200.0))
    tail = _para(_line("tion feels", 72.0, 182.0))
    paras = [stem, tail]
    assert join_dash_bullets(paras) == 0
    assert len(paras) == 2


def test_a_joined_dash_does_not_set_the_item_left():
    dash = _para(_line("\u2013", 141.0, 161.0, size=30.0, width=15.0))
    item = _para(_line("While she's wearing", 162.0, 167.8))
    paras = [dash, item]
    assert join_dash_bullets(paras) == 1
    from babeldoc.format.pdf.document_il.midend.paragraph_finder import (
        _chars_for_left_edge,
    )

    chars = []
    for comp in item.pdf_paragraph_composition:
        chars.extend(comp.pdf_line.pdf_character)
    assert min(char.box.x for char in chars) == 141.0
    assert min(char.box.x for char in _chars_for_left_edge(chars)) == 162.0
    only = _para(_line("\u2013", 141.0, 161.0, size=30.0, width=15.0))
    lone = only.pdf_paragraph_composition[0].pdf_line.pdf_character
    assert min(char.box.x for char in _chars_for_left_edge(lone)) == 141.0


def test_a_joined_dash_is_not_its_own_contour_line():
    dash = _para(_line("\u2013", 141.0, 161.0, size=30.0, width=15.0))
    item = _para(_line("While she's wearing", 162.0, 167.8))
    paras = [dash, item]
    assert join_dash_bullets(paras) == 1
    from babeldoc.format.pdf.document_il.utils.rect_flow_stack import _lines_of

    lines = _lines_of(item)
    assert len(lines) == 1
    assert lines[0].x0 == 162.0
    # Styles folds the words off the line box. The dash must still not
    # come back as a 15pt line.
    item.pdf_paragraph_composition[1].pdf_line.box = None
    folded = _lines_of(item)
    assert [line.x0 for line in folded] == [162.0]


def test_a_one_point_dash_still_joins_the_line_it_marks():
    """The stored box is a sliver on the centerline. The glyph is 30pt."""
    dash = _para(_line("\u2013", 141.0, 176.0, size=30.0, width=15.0))
    dash.pdf_paragraph_composition[0].pdf_line.box.y2 = 177.0
    dash.pdf_paragraph_composition[0].pdf_line.pdf_character[0].box.y2 = 177.0
    dash.pdf_paragraph_composition[0].pdf_line.pdf_character[0].visual_bbox.box.y2 = 177.0
    heading = _para(_line("1. Beginner", 102.0, 192.0))
    item = _para(_line("While she's wearing", 162.0, 168.0))
    paras = [heading, dash, item]
    assert join_dash_bullets(paras) == 1
    assert dash not in paras
    assert "\u2013" not in _text(heading)
    assert _text(item).startswith("\u2013")


def test_a_dash_far_from_the_item_stays():
    dash = _para(_line("\u2013", 141.0, 400.0, size=30.0, width=15.0))
    item = _para(_line("While she's wearing", 162.0, 167.8))
    paras = [dash, item]
    assert join_dash_bullets(paras) == 0
    assert len(paras) == 2
