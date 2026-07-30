"""Sort paragraph lines when stream climbs the page (bottom→top emit)."""

from __future__ import annotations

from unittest.mock import MagicMock

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter
from babeldoc.format.pdf.document_il.il_version_1 import PdfLine
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraphComposition
from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
from babeldoc.format.pdf.document_il.il_version_1 import VisualBbox
from babeldoc.format.pdf.document_il.midend.paragraph_finder import ParagraphFinder


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
    """Stream order bottom→top (y increases); reading order top-first."""
    finder = object.__new__(ParagraphFinder)
    finder.translation_config = MagicMock()
    # Stream: low y first, then higher y (climb)
    p = PdfParagraph(
        box=Box(x=100, y=100, x2=400, y2=200),
        pdf_style=PdfStyle(font_id="base", font_size=12.0, graphic_state=None),
        pdf_paragraph_composition=[
            _line("bottom line start", y=100),
            _line("middle", y=130),
            _line("top line end", y=160),
        ],
        unicode="",
        layout_label="plain text",
    )
    finder._maybe_sort_lines_visual_reading_order(p)
    tops = [c.pdf_line.box.y2 for c in p.pdf_paragraph_composition]
    assert tops == sorted(tops, reverse=True)
    first = "".join(
        ch.char_unicode for ch in p.pdf_paragraph_composition[0].pdf_line.pdf_character
    )
    assert first.startswith("top")


def test_no_sort_when_stream_already_top_down():
    finder = object.__new__(ParagraphFinder)
    finder.translation_config = MagicMock()
    p = PdfParagraph(
        box=Box(x=100, y=100, x2=400, y2=200),
        pdf_style=PdfStyle(font_id="base", font_size=12.0, graphic_state=None),
        pdf_paragraph_composition=[
            _line("top first", y=160),
            _line("middle", y=130),
            _line("bottom last", y=100),
        ],
        unicode="",
        layout_label="plain text",
    )
    before = [
        "".join(ch.char_unicode for ch in c.pdf_line.pdf_character)
        for c in p.pdf_paragraph_composition
    ]
    finder._maybe_sort_lines_visual_reading_order(p)
    after = [
        "".join(ch.char_unicode for ch in c.pdf_line.pdf_character)
        for c in p.pdf_paragraph_composition
    ]
    assert before == after
