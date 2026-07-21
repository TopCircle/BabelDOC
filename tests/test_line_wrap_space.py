"""Line-wrap word boundaries must not glue words (All Tied Up intro).

PDF often encodes a trailing space at EOL; process_paragraph_spacing strips it.
get_char_unicode_string / add_space_dummy_chars must still insert a space when
the next char jumps back to the left margin (distance << 0).
"""

from __future__ import annotations

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter
from babeldoc.format.pdf.document_il.il_version_1 import PdfLine
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraphComposition
from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
from babeldoc.format.pdf.document_il.il_version_1 import VisualBbox
from babeldoc.format.pdf.document_il.utils.layout_helper import (
    _add_space_dummy_chars_to_list,
)
from babeldoc.format.pdf.document_il.utils.layout_helper import add_space_dummy_chars
from babeldoc.format.pdf.document_il.utils.layout_helper import get_char_unicode_string
from babeldoc.format.pdf.document_il.utils.layout_helper import get_paragraph_unicode


def _ch(
    u: str,
    x: float,
    y: float = 100.0,
    w: float = 6.0,
    h: float = 12.0,
    *,
    cid: int = 1,
) -> PdfCharacter:
    # pdf_character_id must be set: Layout.is_newline ignores formula-height
    # chars when id is None (formular_height_ignore_char).
    box = Box(x=x, y=y, x2=x + w, y2=y + h)
    return PdfCharacter(
        char_unicode=u,
        box=box,
        visual_bbox=VisualBbox(box=box),
        pdf_style=PdfStyle(font_id="f0", font_size=12.0),
        scale=1.0,
        advance=w,
        pdf_character_id=cid,
    )


class TestGetCharUnicodeStringLineWrap:
    def test_atu_intro_wraps_insert_spaces(self):
        # Line 1 ends at x≈376 "Is", line 2 starts x=56 "it" (y lower).
        # Without fix: "Isit"
        chars = [
            _ch("I", 370, y=646),
            _ch("s", 376, y=646),
            _ch("i", 56, y=630),
            _ch("t", 62, y=630),
        ]
        assert get_char_unicode_string(chars) == "Is it"

    def test_of_grey_wrap(self):
        chars = [
            _ch("o", 340, y=614),
            _ch("f", 346, y=614),
            _ch("G", 56, y=598),
            _ch("r", 62, y=598),
        ]
        assert get_char_unicode_string(chars) == "of Gr"

    def test_question_or_wrap(self):
        # ages? | Or
        chars = [
            _ch("?", 370, y=630, w=5),
            _ch("O", 56, y=614),
            _ch("r", 62, y=614),
        ]
        assert get_char_unicode_string(chars) == "? Or"

    def test_same_line_no_false_space_on_overlap(self):
        # Adjacent letters same baseline, normal tight kerning (distance ~0.5 < 0.5*w)
        chars = [
            _ch("T", 10, y=100, w=6),
            _ch("h", 15.5, y=100, w=6),  # distance 15.5-16 = -0.5 → no gap space
        ]
        # negative distance same line: not newline (same y), no space
        assert get_char_unicode_string(chars) == "Th"

    def test_cjk_wrap_no_space(self):
        chars = [
            _ch("中", 300, y=200, w=12),
            _ch("文", 56, y=180, w=12),
        ]
        assert get_char_unicode_string(chars) == "中文"

    def test_explicit_space_not_doubled(self):
        chars = [
            _ch("s", 370, y=646),
            _ch(" ", 376, y=646, w=3),
            _ch("i", 56, y=630),
        ]
        assert get_char_unicode_string(chars) == "s i"


class TestAddSpaceDummyCharsLineWrap:
    def test_flat_list_inserts_dummy_at_wrap(self):
        chars = [
            _ch("s", 376, y=646),
            _ch("i", 56, y=630),
        ]
        _add_space_dummy_chars_to_list(chars)
        assert [c.char_unicode for c in chars] == ["s", " ", "i"]

    def test_inter_line_compositions(self):
        line1 = PdfLine(pdf_character=[_ch("s", 376, y=646)])
        line2 = PdfLine(pdf_character=[_ch("i", 56, y=630)])
        para = PdfParagraph(
            pdf_paragraph_composition=[
                PdfParagraphComposition(pdf_line=line1),
                PdfParagraphComposition(pdf_line=line2),
            ]
        )
        add_space_dummy_chars(para)
        assert line1.pdf_character[-1].char_unicode == " "
        assert get_paragraph_unicode(para) == "s i"
