"""PR-06: multi-interval estimate + place across figure pockets."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
from babeldoc.format.pdf.document_il.il_version_1 import VisualBbox
from babeldoc.format.pdf.document_il.midend.exclusion_zone import ExclusionZone
from babeldoc.format.pdf.document_il.midend.exclusion_zone import ExclusionZoneIndex
from babeldoc.format.pdf.document_il.midend.exclusion_zone import ZONE_FIGURE
from babeldoc.format.pdf.document_il.midend.typesetting import Typesetting
from babeldoc.format.pdf.document_il.midend.typesetting import TypesettingUnit
from babeldoc.format.pdf.translation_config import TranslationConfig
from babeldoc.translator.fixed_map_translator import FixedMapTranslator


def _style(size: float = 10.0) -> PdfStyle:
    return PdfStyle(font_id="base", font_size=size, graphic_state=None)


def _unit(ch: str = "中", width: float = 10.0, height: float = 12.0) -> TypesettingUnit:
    box = Box(x=0, y=0, x2=width, y2=height)
    char = PdfCharacter(
        char_unicode=ch,
        box=box,
        visual_bbox=VisualBbox(box=Box(x=0, y=0, x2=width, y2=height)),
        pdf_style=_style(),
    )
    return TypesettingUnit(char=char)


def _typesetting() -> Typesetting:
    cfg = TranslationConfig(
        translator=FixedMapTranslator(),
        input_file="multi_interval.pdf",
        lang_in="en",
        lang_out="zh-CN",
        doc_layout_model=MagicMock(),
        auto_extract_glossary=False,
    )
    return Typesetting(cfg)


def _para(box: Box) -> PdfParagraph:
    return PdfParagraph(
        box=box,
        pdf_style=_style(),
        pdf_paragraph_composition=[],
        unicode="测试",
    )


def _mid_figure_index() -> ExclusionZoneIndex:
    # Page [0, 612]; figure [150, 350] → left 150 + right 262
    zone = ExclusionZone(
        box=Box(x=150, y=100, x2=350, y2=400),
        kind=ZONE_FIGURE,
        priority=20,
    )
    return ExclusionZoneIndex([zone])


class TestQueryAndEstimate:
    def test_query_returns_both_pockets(self):
        ts = _typesetting()
        ts._current_zone_index = _mid_figure_index()
        box = Box(x=0, y=100, x2=612, y2=400)
        intervals = ts._query_line_intervals(200, 220, box)
        assert intervals == [(0, 150), (350, 612)]

    def test_estimate_uses_sum_not_left_only(self):
        """DP capacity = sum of pockets (150+262), not left-prefer 150."""
        ts = _typesetting()
        ts._current_zone_index = _mid_figure_index()
        box = Box(x=0, y=100, x2=612, y2=400)
        units = [_unit() for _ in range(8)]
        widths = ts._estimate_line_widths(
            units, box, scale=1.0, avg_height=12.0, line_skip=1.05
        )
        assert widths
        # First band intersects the figure
        assert widths[0] == pytest.approx(150 + 262)

    def test_estimate_caps_with_reference_width(self):
        ts = _typesetting()
        ts._current_zone_index = _mid_figure_index()
        box = Box(x=0, y=100, x2=612, y2=400)
        units = [_unit() for _ in range(8)]
        widths = ts._estimate_line_widths(
            units,
            box,
            scale=1.0,
            avg_height=12.0,
            line_skip=1.05,
            reference_widths=[140.0, 140.0],
        )
        assert widths[0] == pytest.approx(140.0)  # min(ref, sum)

    def test_no_zone_full_width(self):
        ts = _typesetting()
        ts._current_zone_index = ExclusionZoneIndex([])
        box = Box(x=0, y=100, x2=500, y2=400)
        widths = ts._estimate_line_widths(
            [_unit()], box, scale=1.0, avg_height=12.0, line_skip=1.05
        )
        assert widths[0] == pytest.approx(500.0)


class TestPlaceAcrossIntervals:
    def test_greedy_jumps_to_right_pocket(self):
        """Units wider than left residual continue in the right residual."""
        ts = _typesetting()
        ts._current_zone_index = _mid_figure_index()
        # Left pocket 150pt; 16×10pt chars = 160 → must use right pocket
        units = [_unit(ch="字", width=10.0) for _ in range(20)]
        box = Box(x=0, y=100, x2=612, y2=400)
        para = _para(box)

        placed, all_fit = ts._layout_typesetting_units(
            units,
            box,
            scale=1.0,
            line_skip=1.05,
            paragraph=para,
            use_english_line_break=False,
            break_points=None,
            reference_widths=None,
        )
        assert placed
        xs = [u.box.x for u in placed if not u.is_space]
        # At least one glyph lands in the right pocket (x >= 350)
        assert any(x >= 350.0 - 0.1 for x in xs), f"no right-pocket glyph: {xs[:25]}"
        # And some still on the left
        assert any(x < 150.0 for x in xs)

    def test_left_figure_single_pocket_still_works(self):
        zone = ExclusionZone(
            box=Box(x=0, y=100, x2=200, y2=400),
            kind=ZONE_FIGURE,
            priority=20,
        )
        ts = _typesetting()
        ts._current_zone_index = ExclusionZoneIndex([zone])
        units = [_unit(width=10.0) for _ in range(10)]
        box = Box(x=0, y=100, x2=612, y2=400)
        para = _para(box)
        placed, _ = ts._layout_typesetting_units(
            units,
            box,
            scale=1.0,
            line_skip=1.05,
            paragraph=para,
            use_english_line_break=False,
            break_points=None,
        )
        assert placed
        # Body starts at figure right edge
        assert min(u.box.x for u in placed) >= 200.0 - 0.1

    def test_cap_leftmost_only(self):
        intervals = [(0.0, 200.0), (400.0, 600.0)]
        box = Box(x=0, y=0, x2=600, y2=100)
        capped = Typesetting._cap_leftmost_interval_with_reference(
            box,
            intervals,
            reference_widths=[120.0],
            line_idx=0,
            alignment="left",
        )
        assert capped[0][0] == pytest.approx(0.0)
        assert capped[0][1] == pytest.approx(120.0)
        assert capped[1] == (400.0, 600.0)

    def test_try_advance_interval(self):
        intervals = [(0.0, 50.0), (100.0, 200.0)]
        # Doesn't fit in first residual at x=40
        result = Typesetting._try_advance_interval_for_unit(
            unit_width=20.0,
            intervals=intervals,
            interval_idx=0,
            current_x=40.0,
            available_x2=50.0,
        )
        assert result == (1, 100.0, 200.0, 100.0)

        # Already fits — no advance
        assert (
            Typesetting._try_advance_interval_for_unit(
                10.0, intervals, 0, 0.0, 50.0
            )
            is None
        )

    def test_empty_line_keeps_left_when_unit_fits(self):
        """English lookahead must not snap an empty line onto the right pocket.

        Regression: need_break with empty current_line_heights used to assign
        intervals[-1], parking the first glyph mid/right of a figure.
        """
        ts = _typesetting()
        ts._current_zone_index = _mid_figure_index()
        # Short units that fit the left residual; enable EN break lookahead
        units = [_unit(ch="a", width=8.0) for _ in range(12)]
        box = Box(x=0, y=100, x2=612, y2=400)
        para = _para(box)
        placed, _ = ts._layout_typesetting_units(
            units,
            box,
            scale=1.0,
            line_skip=1.05,
            paragraph=para,
            use_english_line_break=True,
            break_points=None,
            reference_widths=None,
        )
        assert placed
        first_x = placed[0].box.x
        assert first_x < 150.0, f"first glyph should be left residual, got x={first_x}"
