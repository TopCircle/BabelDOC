"""Tests for pre-expanding narrow title boxes (Edging-class short headings)
and readable scale floor.
"""

from __future__ import annotations

from types import SimpleNamespace
import statistics

import pytest

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.midend.typesetting import Typesetting


class _StubTypesetting:
    """Minimal stand-in providing get_max_right_space."""

    def get_max_right_space(self, current_box, page):
        return 550.0


def _page():
    return SimpleNamespace(
        cropbox=SimpleNamespace(box=Box(x=0, y=0, x2=612, y2=792)),
        pdf_paragraph=[],
        pdf_character=[],
        pdf_figure=[],
    )


class TestReadableScaleFloor:
    def test_min_readable_scale_constant(self):
        assert Typesetting.MIN_READABLE_SCALE >= 0.5
        assert Typesetting.MIN_READABLE_SCALE < 1.0


class TestReferenceWidthCap:
    def test_caps_to_en_line_width(self):
        box = Box(x=56.0, y=100.0, x2=500.0, y2=200.0)
        ax, ax2 = Typesetting._cap_available_with_reference(
            box, 56.0, 500.0, [300.0, 280.0, 260.0], 0
        )
        assert ax == 56.0
        assert ax2 == pytest.approx(56.0 + 300.0)

    def test_extra_lines_use_median(self):
        box = Box(x=56.0, y=100.0, x2=500.0, y2=200.0)
        refs = [300.0, 280.0, 260.0]
        ax, ax2 = Typesetting._cap_available_with_reference(
            box, 56.0, 500.0, refs, line_idx=10
        )
        assert ax2 == pytest.approx(56.0 + 280.0)  # median

    def test_narrow_ref_not_skipped_when_box_is_page_wide(self):
        """Orgasms p.8: EN wrap column ~150–220pt but box ~480pt after
        dropping artistic figure zone. Must still cap to EN width."""
        box = Box(x=73.8, y=100.0, x2=556.0, y2=700.0)
        refs = [222.0, 177.0, 191.0, 224.0, 153.0, 160.0]
        # Mid-column EN width
        ax, ax2 = Typesetting._cap_available_with_reference(
            box, 73.8, 556.0, refs, line_idx=4
        )
        assert ax2 <= 73.8 + 160.0 + 1.0
        assert ax2 < 350.0  # must not spill across photo (~x=195+)
        # Extra CJK lines
        ax2b = Typesetting._cap_available_with_reference(
            box, 73.8, 556.0, refs, line_idx=50
        )[1]
        assert ax2b < 350.0
        assert ax2b == pytest.approx(73.8 + statistics.median(refs), abs=1.0)


class TestPreExpandNarrowBox:
    def test_expands_when_content_much_wider_than_box(self):
        # Original "Edging" ~49pt wide; CJK translation needs ~144pt
        box = Box(x=56.0, y=97.4, x2=105.1, y2=114.0)
        units = [SimpleNamespace(width=12.0) for _ in range(12)]
        para = SimpleNamespace(
            unicode="边缘控制（Edging）", box=None, layout_label="title"
        )

        out = Typesetting._pre_expand_narrow_box(
            _StubTypesetting(), box, para, _page(), units, apply_layout=True
        )
        assert out.x2 == 545.0
        assert out.x2 - out.x > 400
        assert para.box is out

    def test_expands_short_heading_at_lower_ratio(self):
        """Title-like CJK slightly wider than EN box should still expand."""
        box = Box(x=56.0, y=340.0, x2=258.0, y2=360.0)  # ~202pt like EN title
        # content 1.2x box → triggers short-heading 1.15 path, not body 1.5
        units = [SimpleNamespace(width=14.0) for _ in range(18)]  # 252pt
        para = SimpleNamespace(
            unicode="如何在性爱中进行凯格尔运动",
            box=None,
            layout_label="title",
        )
        out = Typesetting._pre_expand_narrow_box(
            _StubTypesetting(), box, para, _page(), units, apply_layout=True
        )
        assert out.x2 > box.x2

    def test_no_expand_when_content_fits(self):
        box = Box(x=56.0, y=97.4, x2=105.1, y2=114.0)
        units = [SimpleNamespace(width=10.0) for _ in range(3)]  # 30pt
        para = SimpleNamespace(unicode="Hi", box=None, layout_label=None)

        out = Typesetting._pre_expand_narrow_box(
            _StubTypesetting(), box, para, _page(), units, apply_layout=False
        )
        assert abs((out.x2 - out.x) - 49.1) < 0.01
        assert para.box is None

    def test_no_expand_when_blocked_on_right(self):
        class Blocked:
            def get_max_right_space(self, current_box, page):
                return current_box.x2  # no room

        box = Box(x=56.0, y=97.4, x2=105.1, y2=114.0)
        units = [SimpleNamespace(width=12.0) for _ in range(12)]
        para = SimpleNamespace(
            unicode="边缘控制（Edging）", box=None, layout_label="title"
        )

        out = Typesetting._pre_expand_narrow_box(
            Blocked(), box, para, _page(), units, apply_layout=True
        )
        assert abs((out.x2 - out.x) - 49.1) < 0.01
        assert para.box is None
