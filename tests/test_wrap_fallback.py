"""CJK wrap→block fallback heuristics (layout align LA-1)."""

from __future__ import annotations

from babeldoc.format.pdf.document_il.utils.wrap_shape import count_typeset_baselines
from babeldoc.format.pdf.document_il.utils.wrap_shape import should_fallback_wrap_to_block
from babeldoc.format.pdf.document_il.utils.wrap_shape import wrap_line_budget


class _U:
    def __init__(self, y: float):
        self.y = y


class TestWrapLineBudget:
    def test_budget_from_shape(self):
        shape = [(0, 194), (0, 174), (0, 143), (0, 67)]
        assert wrap_line_budget(shape) == max(4 + 4, 10)  # 10
        assert wrap_line_budget([(0, 100)] * 12) == 16

    def test_budget_empty(self):
        assert wrap_line_budget(None) == 10
        assert wrap_line_budget([]) == 10


class TestShouldFallbackWrapToBlock:
    def test_fits_short_no_fallback(self):
        shape = [(0, 194), (0, 174), (0, 143), (0, 67)]
        units = [_U(500 - 14 * i) for i in range(4)]
        assert (
            should_fallback_wrap_to_block(
                wrap_shape=shape, typeset_units=units, all_units_fit=True
            )
            is False
        )

    def test_overflow_many_lines_fallback(self):
        shape = [(0, 194), (0, 174), (0, 143), (0, 67)]
        # 20 baselines >> budget 10
        units = [_U(500 - 10 * i) for i in range(20)]
        assert (
            should_fallback_wrap_to_block(
                wrap_shape=shape, typeset_units=units, all_units_fit=False
            )
            is True
        )

    def test_no_shape_no_fallback(self):
        assert (
            should_fallback_wrap_to_block(
                wrap_shape=None, typeset_units=[_U(1)], all_units_fit=False
            )
            is False
        )


class TestCountBaselines:
    def test_distinct_y(self):
        units = [_U(10), _U(10.04), _U(20), _U(20.02)]
        # rounded to 0.1 → 10.0, 10.0, 20.0, 20.0 → 2
        assert count_typeset_baselines(units) == 2
