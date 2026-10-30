"""Tests for decorative and body underline detection and removal in paragraphs."""

from __future__ import annotations

from unittest.mock import MagicMock

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import Page
from babeldoc.format.pdf.document_il.il_version_1 import PdfCurve
from babeldoc.format.pdf.document_il.il_version_1 import PdfLine
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraphComposition
from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
from babeldoc.format.pdf.document_il.midend.styles_and_formulas import StylesAndFormulas
from babeldoc.format.pdf.document_il.midend.styles_and_formulas import (
    _curve_within_paragraph_vertical_bounds,
)
from babeldoc.format.pdf.document_il.midend.styles_and_formulas import (
    _is_thin_horizontal_line,
)
from babeldoc.format.pdf.translation_config import TranslationConfig


class TestUnderlineGeometry:
    def test_thin_horizontal_line_detection(self):
        # Zero-height vector line
        assert _is_thin_horizontal_line(Box(x=36.0, y=225.0, x2=321.0, y2=225.0))
        # Thin rectangle (0.5pt - 1.5pt)
        assert _is_thin_horizontal_line(Box(x=36.0, y=224.5, x2=321.0, y2=225.5))
        # Bold decorative underline stroke up to 3.0pt
        assert _is_thin_horizontal_line(Box(x=36.0, y=223.5, x2=321.0, y2=226.5))
        # Square or tall box is not a line
        assert not _is_thin_horizontal_line(Box(x=36.0, y=200.0, x2=100.0, y2=240.0))
        # Dot/tiny noise (width < 3.0)
        assert not _is_thin_horizontal_line(Box(x=36.0, y=225.0, x2=38.0, y2=225.0))

    def test_standard_body_underline_vertical_bounds(self):
        # In Document IL (PDF coordinates), y=0 is at bottom, so visual bottom of line is y=100.0,
        # and visual top of line is y2=112.0.
        para_box = Box(x=36.0, y=100.0, x2=300.0, y2=112.0)
        para_entries = [(para_box, 12.0)]

        # Underline 2pt below bottom of line (lower y: 100 - 2 = 98)
        curve_ok = Box(x=36.0, y=98.0, x2=280.0, y2=98.0)
        assert _curve_within_paragraph_vertical_bounds(curve_ok, para_entries)

        # Underline 4pt below bottom (lower y: 100 - 4 = 96, 12 * 0.35 = 4.2 max bottom margin)
        curve_4pt = Box(x=36.0, y=96.0, x2=280.0, y2=96.0)
        assert _curve_within_paragraph_vertical_bounds(curve_4pt, para_entries)

        # Far below paragraph (e.g. 15pt below: 100 - 15 = 85) -> False
        curve_far = Box(x=36.0, y=85.0, x2=280.0, y2=85.0)
        assert not _curve_within_paragraph_vertical_bounds(curve_far, para_entries)

        # Top divider rule above heading (higher y: 112 + 5 = 117) -> protected by conservative top margin
        curve_above = Box(x=36.0, y=117.0, x2=300.0, y2=117.0)
        assert not _curve_within_paragraph_vertical_bounds(curve_above, para_entries)

    def test_large_heading_underline_vertical_bounds(self):
        # Explosive Ejaculation Stimulation page 10 heading: 21pt font
        # In PDF coordinates: text bbox y=571.70..592.70, underline at y=567.0 (4.70pt below text bottom)
        heading_box = Box(x=36.0, y=571.70, x2=326.0, y2=592.70)
        para_entries = [(heading_box, 21.0)]

        underline = Box(x=36.0, y=567.0, x2=321.0, y2=567.0)
        assert _curve_within_paragraph_vertical_bounds(underline, para_entries)

    def test_page_wide_rule_not_mistaken_for_underline(self):
        # Paragraph is 150pt wide in column 1 (x=36..186)
        para_box = Box(x=36.0, y=200.0, x2=186.0, y2=220.0)
        para_entries = [(para_box, 14.0)]

        # Divider rule that spans across the whole page (x=20..580, width 560pt)
        page_divider = Box(x=20.0, y=198.0, x2=580.0, y2=198.0)
        assert not _curve_within_paragraph_vertical_bounds(page_divider, para_entries)


class TestRemoveNonFormulaLinesIntegration:
    def test_heading_underline_removed_from_page(self):
        config = TranslationConfig(
            input_file="dummy.pdf",
            translator=MagicMock(),
            lang_in="en",
            lang_out="zh-CN",
            doc_layout_model=MagicMock(),
            remove_non_formula_lines=True,
        )
        sf = StylesAndFormulas(config)

        heading_style = PdfStyle(font_id="H1", font_size=21.0, graphic_state=None)
        line = PdfLine(
            box=Box(x=36.0, y=571.70, x2=326.0, y2=592.70),
        )
        comp = PdfParagraphComposition(pdf_line=line)
        para = PdfParagraph(
            box=Box(x=36.0, y=571.70, x2=326.0, y2=592.70),
            pdf_style=heading_style,
            pdf_paragraph_composition=[comp],
            unicode="Wet & Wild – The ONE trick",
        )

        underline_curve = PdfCurve(
            box=Box(x=36.0, y=567.0, x2=321.0, y2=567.0),
            graphic_state=None,
            pdf_path=[],
            fill_background=False,
            stroke_path=True,
        )
        unrelated_curve = PdfCurve(
            box=Box(x=36.0, y=200.0, x2=321.0, y2=200.0),
            graphic_state=None,
            pdf_path=[],
            fill_background=False,
            stroke_path=True,
        )

        page = Page(
            page_number=0,
            pdf_paragraph=[para],
            pdf_curve=[underline_curve, unrelated_curve],
        )

        sf.remove_non_formula_lines_from_paragraphs(page)

        # Underline curve was recognized and removed; unrelated curve remains
        assert underline_curve not in page.pdf_curve
        assert unrelated_curve in page.pdf_curve
        assert len(page.pdf_curve) == 1
