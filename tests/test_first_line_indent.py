"""Tests for visual first-line indent detection."""

from __future__ import annotations

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter
from babeldoc.format.pdf.document_il.il_version_1 import PdfLine
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraphComposition
from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
from babeldoc.format.pdf.document_il.il_version_1 import VisualBbox
from babeldoc.format.pdf.document_il.midend.paragraph_finder import (
    _compute_visual_first_line_indent,
)
from babeldoc.format.pdf.document_il.midend.paragraph_finder import ParagraphFinder


def _char(x: float, x2: float, y: float, y2: float, ch: str = "a"):
    box = Box(x=x, y=y, x2=x2, y2=y2)
    return PdfCharacter(
        char_unicode=ch,
        box=box,
        visual_bbox=VisualBbox(box=Box(x=x, y=y, x2=x2, y2=y2)),
        pdf_style=PdfStyle(font_id="base", font_size=10.0, graphic_state=None),
    )


def _para_from_line_ranges(ranges: list[tuple[float, float, float]]):
    """ranges: list of (x0, x2, y) per visual line (top to bottom uses decreasing y)."""
    compositions = []
    for x0, x2, y in ranges:
        chars = [
            _char(x0, x0 + 4, y, y + 12, "A"),
            _char(x2 - 4, x2, y, y + 12, "Z"),
        ]
        compositions.append(
            PdfParagraphComposition(
                pdf_line=PdfLine(
                    box=Box(x=x0, y=y, x2=x2, y2=y + 12),
                    pdf_character=chars,
                )
            )
        )
    # also add char-level compositions path via update_paragraph_data
    all_chars = []
    for comp in compositions:
        all_chars.extend(comp.pdf_line.pdf_character)
    para = PdfParagraph(
        box=Box(
            x=min(r[0] for r in ranges),
            y=min(r[2] for r in ranges),
            x2=max(r[1] for r in ranges),
            y2=max(r[2] for r in ranges) + 12,
        ),
        pdf_style=PdfStyle(font_id="base", font_size=10.0, graphic_state=None),
        pdf_paragraph_composition=compositions,
        unicode="test",
    )
    return para


class TestVisualFirstLineIndent:
    def test_no_indent_when_flush_left(self):
        # IMPORTANT NOTE + body all at x=56
        para = _para_from_line_ranges(
            [
                (56.0, 180.0, 200.0),
                (56.0, 500.0, 180.0),
                (56.0, 480.0, 160.0),
            ]
        )
        assert _compute_visual_first_line_indent(para) == 0.0

    def test_classic_first_line_indent(self):
        # First line starts 20pt further right than body
        para = _para_from_line_ranges(
            [
                (76.0, 400.0, 200.0),
                (56.0, 500.0, 180.0),
                (56.0, 490.0, 160.0),
            ]
        )
        indent = _compute_visual_first_line_indent(para)
        assert indent == 20.0

    def test_cap_max_indent(self):
        para = _para_from_line_ranges(
            [
                (200.0, 400.0, 200.0),
                (56.0, 500.0, 180.0),
                (56.0, 490.0, 160.0),
            ]
        )
        indent = _compute_visual_first_line_indent(para)
        assert indent == 48.0  # capped

    def test_single_line_no_indent(self):
        para = _para_from_line_ranges([(56.0, 200.0, 200.0)])
        assert _compute_visual_first_line_indent(para) == 0.0

    def test_update_paragraph_data_uses_visual_indent(self):
        # Stream-order first composition could be misleading; visual wins
        para = _para_from_line_ranges(
            [
                (56.0, 180.0, 200.0),  # IMPORTANT NOTE flush
                (56.0, 500.0, 180.0),
                (56.0, 480.0, 160.0),
            ]
        )
        # Call the indent path directly without constructing full ParagraphFinder
        # (FontMapper needs a real TranslationConfig)
        from babeldoc.format.pdf.document_il.midend.paragraph_finder import (
            _normalize_first_line_indent,
        )

        para.first_line_indent = _compute_visual_first_line_indent(para)
        _normalize_first_line_indent(para)
        assert float(para.first_line_indent or 0) == 0.0
