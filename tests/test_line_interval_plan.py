"""LineIntervalPlan: LayoutIntent → intervals consumption chain (C0/C1)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.midend.typesetting import Typesetting
from babeldoc.format.pdf.document_il.utils.layout_intent import LayoutIntent
from babeldoc.format.pdf.document_il.utils.layout_intent import LayoutIntentRole
from babeldoc.format.pdf.document_il.utils.layout_intent import WrapMode
from babeldoc.format.pdf.document_il.utils.line_interval_plan import LayoutAttempt
from babeldoc.format.pdf.document_il.utils.line_interval_plan import (
    _left_quote_owns_residual,
)
from babeldoc.format.pdf.document_il.utils.line_interval_plan import (
    allows_full_measure_escalation,
)
from babeldoc.format.pdf.document_il.utils.line_interval_plan import (
    attempt_chain_for_paragraph,
)
from babeldoc.format.pdf.document_il.utils.line_interval_plan import (
    full_measure_layout_box,
)
from babeldoc.format.pdf.document_il.utils.line_interval_plan import (
    infer_wrap_mode_beside_photo,
)
from babeldoc.format.pdf.document_il.utils.line_interval_plan import (
    infer_wrap_mode_from_line_boxes,
)
from babeldoc.format.pdf.document_il.utils.line_interval_plan import (
    layout_box_is_thin_vs_full_measure,
)
from babeldoc.format.pdf.document_il.utils.line_interval_plan import (
    resolve_line_interval_plan,
)
from babeldoc.format.pdf.document_il.utils.line_interval_plan import wrap_interval


class TestInferWrapMode:
    def test_right_fixed_p19_style(self):
        # left steps right, right edge pinned
        lines = [(100, 300), (120, 300), (150, 300), (200, 300)]
        assert infer_wrap_mode_from_line_boxes(lines) is WrapMode.RIGHT_FIXED

    def test_left_fixed_p82_style(self):
        # left pinned at 102, right steps in
        lines = [(102, 427), (102, 370), (102, 320), (102, 155)]
        assert infer_wrap_mode_from_line_boxes(lines) is WrapMode.LEFT_FIXED

    def test_ambiguous_none(self):
        lines = [(100, 200), (110, 210)]
        assert infer_wrap_mode_from_line_boxes(lines) is WrapMode.NONE

    def test_photo_on_right_is_left_fixed(self):
        design = Box(x=102, y=400, x2=400, y2=700)
        photo = Box(x=380, y=200, x2=580, y2=720)
        assert infer_wrap_mode_beside_photo(design, [photo]) is WrapMode.LEFT_FIXED

    def test_photo_on_left_is_right_fixed(self):
        design = Box(x=220, y=400, x2=520, y2=700)
        photo = Box(x=40, y=200, x2=200, y2=720)
        assert infer_wrap_mode_beside_photo(design, [photo]) is WrapMode.RIGHT_FIXED

    def test_no_photo_returns_none(self):
        design = Box(x=102, y=400, x2=400, y2=700)
        assert infer_wrap_mode_beside_photo(design, []) is None
        assert infer_wrap_mode_beside_photo(design, None) is None


class TestWrapInterval:
    def test_right_fixed(self):
        design = Box(x=100, y=0, x2=400, y2=100)
        shape = [(0.0, 200.0), (0.0, 150.0)]
        x1, x2 = wrap_interval(design, shape, 0, WrapMode.RIGHT_FIXED)
        assert x2 == 400
        assert abs(x1 - 200) < 1e-6

    def test_left_fixed_p82(self):
        design = Box(x=102, y=0, x2=427, y2=100)
        shape = [(0.0, 325.0), (0.0, 189.0)]
        x1, x2 = wrap_interval(design, shape, 0, WrapMode.LEFT_FIXED)
        assert abs(x1 - 102) < 1e-6
        assert abs(x2 - (102 + 325)) < 1e-6
        x1b, x2b = wrap_interval(design, shape, 1, WrapMode.LEFT_FIXED)
        assert abs(x1b - 102) < 1e-6
        assert abs(x2b - (102 + 189)) < 1e-6

    def test_clamp_prevents_negative_drift(self):
        design = Box(x=102, y=0, x2=200, y2=100)
        # width larger than design → clamp, do not push x1 below 102
        shape = [(0.0, 500.0)]
        x1, x2 = wrap_interval(design, shape, 0, WrapMode.LEFT_FIXED)
        assert x1 >= 102 - 1e-6
        assert x2 <= 200 + 1e-6
        assert x1 < x2


class TestResolvePlan:
    def _para_left_fixed(self):
        design = Box(x=102, y=100, x2=427, y2=500)
        shape = [(0.0, 325.0), (0.0, 267.0), (0.0, 189.0)]
        para = PdfParagraph(box=design, pdf_paragraph_composition=[], unicode="x")
        para.layout_intent = LayoutIntent(
            role=LayoutIntentRole.WRAP_COLUMN,
            design_box=design,
            top_inset=0.0,
            bottom_inset=0.0,
            wrap_shape=shape,
            wrap_mode=WrapMode.LEFT_FIXED,
        )
        return para, design

    def test_primary_left_fixed_intervals(self):
        para, design = self._para_left_fixed()
        plan = resolve_line_interval_plan(
            para,
            design,
            attempt=LayoutAttempt.PRIMARY,
            wrap_enabled=True,
        )
        assert plan.wrap_mode is WrapMode.LEFT_FIXED
        pockets = plan.intervals_at(400, 412, line_idx=0)
        assert len(pockets) == 1
        x1, x2 = pockets[0]
        assert abs(x1 - 102) < 1e-6
        assert abs(x2 - 427) < 1e-6  # 102+325

    def test_full_measure_full_box(self):
        para, design = self._para_left_fixed()
        plan = resolve_line_interval_plan(
            para,
            design,
            attempt=LayoutAttempt.FULL_MEASURE,
            wrap_enabled=False,
        )
        pockets = plan.intervals_at(400, 412, line_idx=0)
        assert pockets == [(102.0, 427.0)]


class TestFullMeasureBoxC3:
    def test_widens_residual_strip(self):
        # p82.65 style: residual wall box x=5 w=285
        residual = Box(x=5, y=400, x2=290, y2=700)
        design = Box(x=102, y=400, x2=427, y2=700)
        para = PdfParagraph(box=residual, pdf_paragraph_composition=[], unicode="x")
        para.layout_intent = LayoutIntent(
            role=LayoutIntentRole.WRAP_COLUMN,
            design_box=design,
            top_inset=0.0,
            bottom_inset=0.0,
            wrap_shape=[(0.0, 200.0)],
            wrap_mode=WrapMode.LEFT_FIXED,
        )
        page = type(
            "P",
            (),
            {"cropbox": type("C", (), {"box": Box(x=0, y=0, x2=612, y2=792)})()},
        )()
        wide = full_measure_layout_box(para, residual, page)
        assert wide is not None
        assert wide.x >= 56 - 1e-6  # snapped off x=5
        assert (wide.x2 - wide.x) >= 400 - 1e-6
        assert layout_box_is_thin_vs_full_measure(residual, wide) is True

    def test_right_fixed_wrap_column_stays_in_design(self):
        """OA p33: FULL_MEASURE must not grow a right-pin wrap into the photo."""
        design = Box(x=102.18, y=453.4, x2=443.63, y2=497.9)
        para = PdfParagraph(box=design, pdf_paragraph_composition=[], unicode="x")
        para.layout_intent = LayoutIntent(
            role=LayoutIntentRole.WRAP_COLUMN,
            design_box=design,
            top_inset=0.0,
            bottom_inset=0.0,
            wrap_shape=[(0.0, 338.0), (0.8, 327.5), (0.0, 127.7)],
            wrap_mode=WrapMode.RIGHT_FIXED,
        )
        page = type(
            "P",
            (),
            {"cropbox": type("C", (), {"box": Box(x=0, y=0, x2=612, y2=792)})()},
        )()
        out = full_measure_layout_box(para, design, page)
        assert out is not None
        assert out.x2 <= 443.63 + 1e-6
        assert out.x >= 102.18 - 1e-6

    def test_left_fixed_wrap_column_stays_in_design(self):
        """OA p33/p59: FULL_MEASURE must not grow a left-pin wrap into the photo."""
        design = Box(x=102.18, y=453.4, x2=443.63, y2=497.9)
        para = PdfParagraph(box=design, pdf_paragraph_composition=[], unicode="x")
        para.layout_intent = LayoutIntent(
            role=LayoutIntentRole.WRAP_COLUMN,
            design_box=design,
            top_inset=0.0,
            bottom_inset=0.0,
            wrap_shape=[(0.0, 338.0), (0.8, 327.5), (0.0, 127.7)],
            wrap_mode=WrapMode.LEFT_FIXED,
        )
        page = type(
            "P",
            (),
            {"cropbox": type("C", (), {"box": Box(x=0, y=0, x2=612, y2=792)})()},
        )()
        out = full_measure_layout_box(para, design, page)
        assert out is not None
        assert out.x2 <= 443.63 + 1e-6
        assert out.x >= 102.18 - 1e-6
        assert (out.x2 - out.x) <= (443.63 - 102.18) + 1e-6


class TestAttemptChainCallout:
    def _para(self, role: LayoutIntentRole, design: Box) -> PdfParagraph:
        para = PdfParagraph(box=design, pdf_paragraph_composition=[], unicode="x")
        para.layout_intent = LayoutIntent(
            role=role,
            design_box=design,
            top_inset=0.0,
            bottom_inset=0.0,
        )
        return para

    def test_cjk_callout_stays_primary(self):
        """OA p91 red bar must not FULL_MEASURE into the body column."""
        bar = self._para(
            LayoutIntentRole.CALLOUT,
            Box(x=54.18, y=375.99, x2=211.635, y2=450.99),
        )
        assert attempt_chain_for_paragraph(bar, is_cjk=True) == [LayoutAttempt.PRIMARY]

    def test_cjk_pull_quote_stays_primary(self):
        quote = self._para(
            LayoutIntentRole.PULL_QUOTE,
            Box(x=361, y=360, x2=552, y2=440),
        )
        assert attempt_chain_for_paragraph(quote, is_cjk=True) == [
            LayoutAttempt.PRIMARY
        ]

    def test_cjk_wrap_column_still_escalates(self):
        wrap = self._para(
            LayoutIntentRole.WRAP_COLUMN,
            Box(x=102, y=400, x2=427, y2=700),
        )
        wrap.layout_intent.wrap_shape = [(0.0, 200.0)]
        assert LayoutAttempt.FULL_MEASURE in attempt_chain_for_paragraph(
            wrap, is_cjk=True
        )
        assert allows_full_measure_escalation(wrap, is_cjk=True) is True

    def test_cjk_callout_disallows_full_measure_escalation(self):
        bar = self._para(
            LayoutIntentRole.CALLOUT,
            Box(x=54.18, y=375.99, x2=211.635, y2=450.99),
        )
        assert allows_full_measure_escalation(bar, is_cjk=True) is False

    def test_cjk_pull_quote_disallows_full_measure_escalation(self):
        """OA p59 wrap-beside-photo was PULL_QUOTE; must not overlay the figure."""
        quote = self._para(
            LayoutIntentRole.PULL_QUOTE,
            Box(x=101.87, y=228.59, x2=341.48, y2=393.24),
        )
        assert allows_full_measure_escalation(quote, is_cjk=True) is False


class TestQuoteResidualCap:
    """OA p91: left quote residual must stay left-aligned, not snap to box.x."""

    def _quote_index(self, *, kind: str = "quote"):
        zone = SimpleNamespace(
            kind=kind,
            box=Box(x=54.18, y=376.0, x2=211.635, y2=451.0),
        )
        return SimpleNamespace(zones=[zone])

    def test_quote_owns_residual_left(self):
        idx = self._quote_index()
        assert _left_quote_owns_residual(idx, 211.635, y_bottom=390.0, y_top=405.0)
        assert _left_quote_owns_residual(idx, 220.0, y_bottom=390.0, y_top=405.0)
        # Different y-band (above the bar) does not own the residual.
        assert not _left_quote_owns_residual(idx, 211.635, y_bottom=200.0, y_top=220.0)

    def test_figure_zone_does_not_own_residual(self):
        idx = self._quote_index(kind="figure")
        assert not _left_quote_owns_residual(idx, 330.0, y_bottom=400.0, y_top=420.0)

    def test_cap_does_not_snap_over_left_quote(self):
        """Residual [211, 572] + EN wrap width ~323 stays in the pocket.

        Without the quote guard, left-align snap walks back to box.x=102
        and CJK overpaints the red bar (undoes B4b).
        """
        box = Box(x=102.18, y=339.0, x2=572.57, y2=459.0)
        refs = [317.28, 325.60, 323.28, 322.73, 323.06, 323.14, 238.27]
        para = PdfParagraph(box=box, pdf_paragraph_composition=[], unicode="x")
        plan = resolve_line_interval_plan(
            para,
            box,
            attempt=LayoutAttempt.PRIMARY,
            wrap_enabled=True,
            zone_index=self._quote_index(),
            reference_widths=refs,
            alignment="left",
            cap_available=lambda b, ax, ax2, r, li: (
                Typesetting._cap_available_with_reference(
                    b, ax, ax2, r, li, alignment="left"
                )
            ),
        )
        x1, x2 = plan._cap_leftmost(
            box,
            [(211.635, 572.57)],
            1,
            y_bottom=390.0,
            y_top=405.0,
        )[0]
        assert x1 == pytest.approx(211.635, abs=0.1)
        assert x1 > 180.0  # must not snap to box.x=102
        assert x2 == pytest.approx(211.635 + 325.60, abs=1.0)
        assert x2 < 560.0  # capped; not the full 572 residual

    def test_figure_residual_still_snaps_to_box(self):
        """Orgasms p.21: figure (not quote) mid-photo shove still snaps."""
        box = Box(x=110.0, y=100.0, x2=550.0, y2=700.0)
        refs = [200.0, 210.0, 190.0]
        para = PdfParagraph(box=box, pdf_paragraph_composition=[], unicode="x")
        plan = resolve_line_interval_plan(
            para,
            box,
            attempt=LayoutAttempt.PRIMARY,
            wrap_enabled=True,
            zone_index=self._quote_index(kind="figure"),
            reference_widths=refs,
            alignment="left",
            cap_available=lambda b, ax, ax2, r, li: (
                Typesetting._cap_available_with_reference(
                    b, ax, ax2, r, li, alignment="left"
                )
            ),
        )
        x1, x2 = plan._cap_leftmost(
            box,
            [(330.0, 520.0)],
            0,
            y_bottom=400.0,
            y_top=420.0,
        )[0]
        assert x1 == pytest.approx(110.0)
        assert x2 == pytest.approx(310.0)
