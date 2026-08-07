"""LineIntervalPlan: LayoutIntent → intervals consumption chain (C0/C1)."""

from __future__ import annotations

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.utils.layout_intent import LayoutIntent
from babeldoc.format.pdf.document_il.utils.layout_intent import LayoutIntentRole
from babeldoc.format.pdf.document_il.utils.layout_intent import WrapMode
from babeldoc.format.pdf.document_il.utils.line_interval_plan import LayoutAttempt
from babeldoc.format.pdf.document_il.utils.line_interval_plan import (
    infer_wrap_mode_from_line_boxes,
)
from babeldoc.format.pdf.document_il.utils.line_interval_plan import resolve_line_interval_plan
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
