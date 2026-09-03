"""OA: mid-page plain decorative reverse reorders via single stream_order policy."""

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
from babeldoc.format.pdf.document_il.utils.layout_helper import get_char_unicode_string
from babeldoc.format.pdf.document_il.utils.stream_order import (
    maybe_reorder_reversed_stream,
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


def test_maybe_reorder_plain_mid_page_decorative_reverse():
    letters = list("Who haS orgaSMS?")
    xs = list(range(100, 100 + 10 * len(letters), 10))
    stream = [_ch(ch, x) for ch, x in zip(reversed(letters), reversed(xs), strict=False)]
    ordered = maybe_reorder_reversed_stream(
        stream, layout_label="plain text", in_page_top_band=False
    )
    assert ordered is not stream
    assert "".join(c.char_unicode for c in ordered) == "Who haS orgaSMS?"


def test_update_paragraph_reorders_mid_page_who_has():
    letters = list("Who haS orgaSMS?")
    xs = list(range(100, 100 + 10 * len(letters), 10))
    stream = [_ch(ch, x, y=400) for ch, x in zip(reversed(letters), reversed(xs), strict=False)]
    line = PdfLine(
        box=Box(x=100, y=400, x2=260, y2=412),
        pdf_character=stream,
    )
    para = PdfParagraph(
        box=Box(x=100, y=400, x2=260, y2=412),
        pdf_style=PdfStyle(font_id="base", font_size=12.0, graphic_state=None),
        pdf_paragraph_composition=[PdfParagraphComposition(pdf_line=line)],
        unicode="",
        layout_label="plain text",
    )
    finder = object.__new__(ParagraphFinder)
    finder.translation_config = MagicMock()
    finder._current_page = None
    finder.paragraph_in_title_top_band = lambda page, p: False  # type: ignore
    finder.update_paragraph_data(para, update_unicode=True, page=None)
    text = para.unicode or get_char_unicode_string(
        para.pdf_paragraph_composition[0].pdf_line.pdf_character
    )
    alnum = "".join(c.lower() for c in text if c.isalnum())
    assert alnum.startswith("who")
    assert "smsrgao" not in alnum
