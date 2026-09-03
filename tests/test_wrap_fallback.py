"""CJK wrap→block fallback heuristics (layout align LA-1).

Pure helpers live in wrap_shape; typesetting wires a single parameterized
retry (wrap_enabled=False) — no instance disable flag.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.midend.typesetting import Typesetting
from babeldoc.format.pdf.document_il.utils.layout_intent import LayoutIntent
from babeldoc.format.pdf.document_il.utils.layout_intent import LayoutIntentRole
from babeldoc.format.pdf.document_il.utils.layout_intent import WrapMode
from babeldoc.format.pdf.document_il.utils.wrap_shape import count_typeset_baselines
from babeldoc.format.pdf.document_il.utils.wrap_shape import residual_line_budget
from babeldoc.format.pdf.document_il.utils.wrap_shape import should_fallback_residual_to_block
from babeldoc.format.pdf.document_il.utils.wrap_shape import should_fallback_wrap_to_block
from babeldoc.format.pdf.document_il.utils.wrap_shape import wrap_line_budget
from babeldoc.format.pdf.translation_config import TranslationConfig


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

    def test_translation_growth_beyond_one_extra_line_fallback(self):
        shape = [(0, 194), (0, 174), (0, 143), (0, 67)]
        units = [_U(500 - 10 * i) for i in range(6)]
        assert (
            should_fallback_wrap_to_block(
                wrap_shape=shape, typeset_units=units, all_units_fit=True
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


class TestResidualLineBudget:
    def test_near_full_width_uncapped(self):
        assert residual_line_budget(400, 460) >= 1000

    def test_oa_p82_strip(self):
        # ~189pt residual / ~460pt para → budget around 10
        b = residual_line_budget(189, 460)
        assert 6 <= b <= 14

    def test_narrower_fewer_lines(self):
        assert residual_line_budget(80, 460) < residual_line_budget(189, 460)


class TestShouldFallbackResidualToBlock:
    def test_short_caption_kept(self):
        units = [_U(500 - 14 * i) for i in range(4)]
        assert (
            should_fallback_residual_to_block(
                residual_width=189,
                para_width=460,
                typeset_units=units,
                all_units_fit=True,
            )
            is False
        )

    def test_dense_wall_fallback(self):
        # OA p82: ~14+ lines in ~189pt strip
        units = [_U(700 - 14 * i) for i in range(16)]
        assert (
            should_fallback_residual_to_block(
                residual_width=189,
                para_width=460,
                typeset_units=units,
                all_units_fit=False,
            )
            is True
        )

    def test_full_width_no_fallback(self):
        units = [_U(500 - 10 * i) for i in range(20)]
        assert (
            should_fallback_residual_to_block(
                residual_width=450,
                para_width=460,
                typeset_units=units,
                all_units_fit=False,
            )
            is False
        )

    def test_none_residual_no_fallback(self):
        assert (
            should_fallback_residual_to_block(
                residual_width=None,
                para_width=460,
                typeset_units=[_U(1)] * 20,
                all_units_fit=False,
            )
            is False
        )


def _cjk_typesetting() -> Typesetting:
    cfg = TranslationConfig(
        translator=MagicMock(),
        input_file="dummy.pdf",
        lang_in="en",
        lang_out="zh-CN",
        doc_layout_model=MagicMock(),
    )
    return Typesetting(cfg)


def _wrap_paragraph() -> PdfParagraph:
    design = Box(x=56, y=100, x2=400, y2=500)
    shape = [(0.0, 194.0), (0.0, 174.0), (0.0, 143.0), (0.0, 67.0)]
    para = PdfParagraph(
        box=design,
        pdf_paragraph_composition=[],
        unicode="测试绕排段落",
    )
    para.layout_intent = LayoutIntent(
        role=LayoutIntentRole.WRAP_COLUMN,
        design_box=design,
        top_inset=0.0,
        bottom_inset=0.0,
        wrap_shape=shape,
    )
    return para


class TestActiveWrapParameterized:
    """wrap_enabled is call-scoped on Typesetting, not a sticky disable flag."""

    def test_wrap_enabled_true_resolves_pin(self):
        ts = _cjk_typesetting()
        para = _wrap_paragraph()
        ts._wrap_enabled = True
        active = ts._active_wrap(para, para.box)
        assert active is not None
        design, shape = active
        assert design.x2 == 400
        assert len(shape) == 4

    def test_wrap_enabled_false_disables_pin(self):
        ts = _cjk_typesetting()
        para = _wrap_paragraph()
        ts._wrap_enabled = False
        assert ts._active_wrap(para, para.box) is None

    def test_no_disable_wrap_instance_flag(self):
        ts = _cjk_typesetting()
        assert not hasattr(ts, "_disable_wrap_for_paragraph")
        assert not hasattr(ts, "_drop_all_figures_for_paragraph")
        assert getattr(ts, "_wrap_enabled", "missing") is None


class TestCjkAbandonNarrowColumn:
    """OA S8: callout / left-of-photo wrap must not FULL_MEASURE into the figure."""

    def test_pull_quote_never_abandons(self):
        ts = _cjk_typesetting()
        design = Box(x=101.87, y=228.59, x2=341.48, y2=393.24)
        para = PdfParagraph(box=design, pdf_paragraph_composition=[], unicode="是为更喜欢特技")
        para.layout_intent = LayoutIntent(
            role=LayoutIntentRole.PULL_QUOTE,
            design_box=design,
            top_inset=0.0,
            bottom_inset=0.0,
        )
        units = [_U(380 - 14 * i) for i in range(8)]
        assert (
            ts._cjk_should_abandon_narrow_column(
                para,
                design,
                units,
                all_units_fit=True,
                wrap_enabled=True,
                drop_figure_zones=False,
            )
            is False
        )

    def test_callout_never_abandons(self):
        ts = _cjk_typesetting()
        design = Box(x=54.18, y=376.0, x2=211.64, y2=451.0)
        para = PdfParagraph(box=design, pdf_paragraph_composition=[], unicode="红条")
        para.layout_intent = LayoutIntent(
            role=LayoutIntentRole.CALLOUT,
            design_box=design,
            top_inset=0.0,
            bottom_inset=0.0,
        )
        units = [_U(440 - 14 * i) for i in range(6)]
        assert (
            ts._cjk_should_abandon_narrow_column(
                para,
                design,
                units,
                all_units_fit=True,
                wrap_enabled=True,
                drop_figure_zones=False,
            )
            is False
        )

    def test_left_fixed_wrap_fits_does_not_c3(self):
        """Pin wrap that fits its shape must not C3-widen into the photo."""
        ts = _cjk_typesetting()
        design = Box(x=101.87, y=228.59, x2=341.48, y2=393.24)
        shape = [
            (0.0, 231.8),
            (0.7, 238.1),
            (0.1, 240.6),
            (1.0, 230.7),
            (0.4, 223.4),
            (0.3, 220.4),
            (0.3, 218.5),
        ]
        para = PdfParagraph(box=design, pdf_paragraph_composition=[], unicode="绕图")
        para.layout_intent = LayoutIntent(
            role=LayoutIntentRole.WRAP_COLUMN,
            design_box=design,
            top_inset=0.0,
            bottom_inset=0.0,
            wrap_shape=shape,
            wrap_mode=WrapMode.LEFT_FIXED,
        )
        units = [_U(380 - 14 * i) for i in range(7)]
        assert (
            ts._cjk_should_abandon_narrow_column(
                para,
                design,
                units,
                all_units_fit=True,
                wrap_enabled=True,
                drop_figure_zones=False,
            )
            is False
        )

    def test_wrap_over_budget_still_abandons(self):
        ts = _cjk_typesetting()
        para = _wrap_paragraph()
        units = [_U(500 - 10 * i) for i in range(20)]
        assert (
            ts._cjk_should_abandon_narrow_column(
                para,
                para.box,
                units,
                all_units_fit=False,
                wrap_enabled=True,
                drop_figure_zones=False,
            )
            is True
        )
