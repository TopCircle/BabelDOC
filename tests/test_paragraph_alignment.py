"""Tests for paragraph horizontal alignment detection and typesetting shift."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter
from babeldoc.format.pdf.document_il.il_version_1 import PdfLine
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraphComposition
from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
from babeldoc.format.pdf.document_il.il_version_1 import VisualBbox
from babeldoc.format.pdf.document_il.midend.typesetting import Typesetting
from babeldoc.format.pdf.document_il.midend.typesetting import TypesettingUnit
from babeldoc.format.pdf.document_il.utils.layout_helper import detect_paragraph_alignment


def _char(x: float, x2: float, y: float = 100.0, y2: float = 112.0, ch: str = "a"):
    box = Box(x=x, y=y, x2=x2, y2=y2)
    return PdfCharacter(
        char_unicode=ch,
        box=box,
        visual_bbox=VisualBbox(box=Box(x=x, y=y, x2=x2, y2=y2)),
        pdf_style=PdfStyle(font_id="base", font_size=10.0, graphic_state=None),
    )


def _line_para(line_ranges: list[tuple[float, float]], *, label: str | None = None):
    """Build a paragraph whose compositions are one PdfLine per range."""
    compositions = []
    y = 200.0
    for x, x2 in line_ranges:
        # Put a few chars spanning the line range
        chars = [
            _char(x, x + 5, y=y, y2=y + 12, ch="A"),
            _char(x2 - 5, x2, y=y, y2=y + 12, ch="Z"),
        ]
        line = PdfLine(
            box=Box(x=x, y=y, x2=x2, y2=y + 12),
            pdf_character=chars,
        )
        compositions.append(PdfParagraphComposition(pdf_line=line))
        y -= 15.0

    para_left = min(r[0] for r in line_ranges)
    para_right = max(r[1] for r in line_ranges)
    para_bottom = y
    para_top = 200.0 + 12.0
    return PdfParagraph(
        box=Box(x=para_left, y=para_bottom, x2=para_right, y2=para_top),
        pdf_style=PdfStyle(font_id="base", font_size=10.0, graphic_state=None),
        pdf_paragraph_composition=compositions,
        unicode="test",
        layout_label=label,
    )


def _page(width: float = 612.0):
    return SimpleNamespace(
        cropbox=SimpleNamespace(box=Box(x=0, y=0, x2=width, y2=792)),
        mediabox=SimpleNamespace(box=Box(x=0, y=0, x2=width, y2=792)),
    )


class TestDetectParagraphAlignment:
    def test_multiline_center_varying_widths(self):
        # Page-centered author block: equal L/R margins, varying widths
        # Centers all at 306
        lines = [
            (78.6, 533.4),   # width 454.8, center 306
            (125.3, 486.7),  # width 361.4, center 306
            (132.7, 479.3),  # width 346.6, center 306
            (260.2, 351.8),  # width 91.6, center 306
        ]
        para = _line_para(lines)
        assert detect_paragraph_alignment(para) == "center"

    def test_multiline_left_aligned_body(self):
        # Two-column body: same left edge, full-ish equal widths
        lines = [
            (52.0, 297.0),
            (52.0, 296.5),
            (52.0, 297.2),
            (52.0, 295.0),
        ]
        para = _line_para(lines)
        assert detect_paragraph_alignment(para) == "left"

    def test_near_full_width_lines_never_center(self):
        """Even if line centers cluster, near-full-width body stays left."""
        # Centers near 300, widths still ~75%+ of para span
        lines = [
            (86.0, 520.0),
            (90.0, 510.0),
            (95.0, 505.0),
            (100.0, 490.0),
        ]
        para = _line_para(lines)
        assert detect_paragraph_alignment(para) == "left"

    def test_left_aligned_body_with_short_last_line(self):
        """Regression: full lines have lm≈rm≈0; short last line must NOT
        flip the paragraph to center (the Orgasms ebook false positive)."""
        lines = [
            (56.0, 560.0),  # full
            (56.0, 558.0),  # full
            (56.0, 555.0),  # full
            (56.0, 200.0),  # short last line, flush left
        ]
        para = _line_para(lines)
        assert detect_paragraph_alignment(para) == "left"

    def test_left_aligned_body_near_full_page(self):
        # Near-full-width left body as on the dual PDF English side
        lines = [
            (56.0, 560.0),
            (56.0, 550.0),
            (56.0, 555.0),
            (56.0, 400.0),
        ]
        para = _line_para(lines)
        assert detect_paragraph_alignment(para, _page(612)) == "left"

    def test_title_label_does_not_force_center(self):
        # Ebook section headings are often left-aligned but labeled "title"
        # by DocLayout — must stay left, not float to center of wide box.
        para = _line_para([(56.0, 490.0)], label="title")
        assert detect_paragraph_alignment(para, _page(612)) == "left"

    def test_left_aligned_section_heading_stays_left(self):
        # Short Chinese heading after translation of a left-aligned EN heading
        # with a wide original box: geometry is left-edge at page margin.
        para = _line_para([(56.0, 490.3)], label="title")  # Working Out... style
        assert detect_paragraph_alignment(para, _page(612)) == "left"

    def test_single_line_page_centered(self):
        # Single title line centered on page (L≈R page margins)
        para = _line_para([(63.9, 548.1)])  # center 306, page 612
        assert detect_paragraph_alignment(para, _page(612)) == "center"

    def test_single_line_column_not_center(self):
        # Left column body line — not page-centered
        para = _line_para([(52.0, 297.0)])
        assert detect_paragraph_alignment(para, _page(612)) == "left"

    def test_right_aligned(self):
        lines = [
            (100.0, 300.0),
            (150.0, 300.0),
            (200.0, 300.0),
        ]
        para = _line_para(lines)
        assert detect_paragraph_alignment(para) == "right"


class TestApplyLineHorizontalAlignment:
    def _unit_at(self, x: float, width: float = 10.0) -> TypesettingUnit:
        ch = _char(x, x + width)
        return TypesettingUnit(char=ch)

    def test_center_shifts_short_line(self):
        # Line placed left-to-right at x=50..80 within available 50..250
        units = [self._unit_at(50), self._unit_at(60), self._unit_at(70)]
        Typesetting._apply_line_horizontal_alignment(
            units, 0, 3, available_x=50.0, available_x2=250.0, alignment="center"
        )
        # line width = 30, avail = 200, offset = (200-30)/2 = 85 → start at 135
        assert units[0].box.x == pytest.approx(135.0, abs=0.1)
        assert units[2].box.x2 == pytest.approx(165.0, abs=0.1)

    def test_left_alignment_no_shift(self):
        units = [self._unit_at(50), self._unit_at(60)]
        Typesetting._apply_line_horizontal_alignment(
            units, 0, 2, available_x=50.0, available_x2=250.0, alignment="left"
        )
        assert units[0].box.x == pytest.approx(50.0)
        assert units[1].box.x == pytest.approx(60.0)

    def test_right_alignment(self):
        units = [self._unit_at(50), self._unit_at(60), self._unit_at(70)]
        Typesetting._apply_line_horizontal_alignment(
            units, 0, 3, available_x=50.0, available_x2=250.0, alignment="right"
        )
        # line width 30, target left = 250-30 = 220
        assert units[0].box.x == pytest.approx(220.0, abs=0.1)
        assert units[2].box.x2 == pytest.approx(250.0, abs=0.1)

    def test_full_width_line_no_shift(self):
        units = [self._unit_at(50, width=200)]
        Typesetting._apply_line_horizontal_alignment(
            units, 0, 1, available_x=50.0, available_x2=250.0, alignment="center"
        )
        assert units[0].box.x == pytest.approx(50.0)
