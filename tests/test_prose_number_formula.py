"""Prose numbers must not become formula placeholders for DeepLX (ATU intro)."""

from __future__ import annotations

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter
from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
from babeldoc.format.pdf.document_il.il_version_1 import VisualBbox
from babeldoc.format.pdf.document_il.midend.styles_and_formulas import StylesAndFormulas


def _ch(u: str, *, x: float = 0.0) -> PdfCharacter:
    box = Box(x=x, y=0, x2=x + 6, y2=12)
    return PdfCharacter(
        char_unicode=u,
        box=box,
        visual_bbox=VisualBbox(box=Box(x=x, y=0, x2=x + 6, y2=12)),
        pdf_style=PdfStyle(font_id="base", font_size=12.0, graphic_state=None),
    )


class TestProseNumberRun:
    def test_fifty_shades(self):
        chars = [_ch(c, x=i * 6) for i, c in enumerate("50 Shades")]
        assert StylesAndFormulas._is_prose_number_run(chars, 0)
        assert StylesAndFormulas._is_prose_number_run(chars, 1)  # '0' still in run

    def test_percent_not_prose(self):
        chars = [_ch(c, x=i * 6) for i, c in enumerate("21%")]
        assert not StylesAndFormulas._is_prose_number_run(chars, 0)

    def test_trailing_digit_alone(self):
        chars = [_ch(c, x=i * 6) for i, c in enumerate("x=50")]
        # start at '5'
        assert not StylesAndFormulas._is_prose_number_run(chars, 2)

    def test_ordinal(self):
        chars = [_ch(c, x=i * 6) for i, c in enumerate("4th")]
        assert StylesAndFormulas._is_prose_number_run(chars, 0)
