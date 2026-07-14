"""Tests for pre-expanding narrow title boxes (Edging-class short headings)
and readable scale floor.
"""

from __future__ import annotations

from types import SimpleNamespace

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


class TestPreExpandNarrowBox:
    def test_expands_when_content_much_wider_than_box(self):
        # Original "Edging" ~49pt wide; CJK translation needs ~144pt
        box = Box(x=56.0, y=97.4, x2=105.1, y2=114.0)
        units = [SimpleNamespace(width=12.0) for _ in range(12)]
        para = SimpleNamespace(unicode="边缘控制（Edging）", box=None)

        out = Typesetting._pre_expand_narrow_box(
            _StubTypesetting(), box, para, _page(), units, apply_layout=True
        )
        assert out.x2 == 545.0
        assert out.x2 - out.x > 400
        assert para.box is out

    def test_no_expand_when_content_fits(self):
        box = Box(x=56.0, y=97.4, x2=105.1, y2=114.0)
        units = [SimpleNamespace(width=10.0) for _ in range(3)]  # 30pt
        para = SimpleNamespace(unicode="Hi", box=None)

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
        para = SimpleNamespace(unicode="边缘控制（Edging）", box=None)

        out = Typesetting._pre_expand_narrow_box(
            Blocked(), box, para, _page(), units, apply_layout=True
        )
        assert abs((out.x2 - out.x) - 49.1) < 0.01
        assert para.box is None
