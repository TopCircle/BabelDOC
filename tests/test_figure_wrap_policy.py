"""Figure-wrap policy: single entry point, debug-stub predicate, pre-expand.

Covers review blockers B1/B2/B5 for OA p19 TAKING CHARGE (figure-wrap taper
columns must not be pull-quotes, must not pre-expand, must keep per-line
reference widths; layout-label stubs must be excluded by content signals,
not xobj_id).
"""

from __future__ import annotations

from babeldoc.format.pdf.document_il import il_version_1
from babeldoc.format.pdf.document_il.midend.typesetting import Typesetting
from babeldoc.format.pdf.document_il.utils.figure_wrap import is_figure_wrap_paragraph
from babeldoc.format.pdf.document_il.utils.figure_wrap import body_line_widths
from babeldoc.format.pdf.document_il.utils.figure_wrap import taper_prefix_widths
from babeldoc.format.pdf.document_il.utils.figure_wrap import is_figure_wrap_taper
from babeldoc.format.pdf.document_il.utils.region_skip import is_layout_debug_stub


class TestIsFigureWrapTaper:
    def test_taper_true_oa_p19(self):
        assert is_figure_wrap_taper([194, 174, 143, 67]) is True

    def test_one_short_last_line_false(self):
        assert is_figure_wrap_taper([467, 467, 258]) is False

    def test_flat_narrow_column_false(self):
        assert is_figure_wrap_taper([180, 180, 175, 100]) is False

    def test_edge_cases_false(self):
        assert is_figure_wrap_taper(None) is False
        assert is_figure_wrap_taper([]) is False
        assert is_figure_wrap_taper([194, 174]) is False

    def test_midcap_prefix_stripped_oa_p19(self):
        """OA p19 TAKING CHARGE midcaps (~3–42pt) must not kill body taper."""
        polluted = [
            7.1, 16.6, 2.7, 22.4, 8.2, 41.4,
            258.6, 249.6, 231.6, 197.6, 177.6, 146.7, 122.6, 103.6, 63.7,
            10.2,
        ]
        assert body_line_widths(polluted) == [
            258.6, 249.6, 231.6, 197.6, 177.6, 146.7, 122.6, 103.6, 63.7,
        ]
        assert is_figure_wrap_taper(polluted) is True

    def test_full_en_p19_body_taper(self):
        body = [258.6, 249.6, 231.6, 197.6, 177.6, 146.7, 122.6, 103.6, 63.7]
        assert is_figure_wrap_taper(body) is True

    def test_noisy_tail_prefix_oa_p19(self):
        """Fallback-clustered tail 51.6→99.6 must not kill the body cone."""
        noisy = [254.6, 246.0, 228.3, 193.6, 174.1, 142.6, 51.6, 99.6, 63.0]
        assert taper_prefix_widths(noisy) == [
            254.6, 246.0, 228.3, 193.6, 174.1, 142.6, 51.6,
        ]
        assert is_figure_wrap_taper(noisy) is True
        assert is_figure_wrap_paragraph(
            TestFigureWrapParagraph._para(widths=noisy)
        ) is True


class TestIsLayoutDebugStub:
    @staticmethod
    def _stub(unicode_: str):
        p = il_version_1.PdfParagraph(xobj_id=-1, unicode=unicode_)
        p.pdf_paragraph_composition = [
            il_version_1.PdfParagraphComposition(
                pdf_same_style_unicode_characters=(
                    il_version_1.PdfSameStyleUnicodeCharacters(
                        unicode=unicode_,
                        debug_info=True,
                    )
                )
            )
        ]
        return p

    @staticmethod
    def _real(unicode_: str = "real body text"):
        p = il_version_1.PdfParagraph(xobj_id=-1, unicode=unicode_)
        p.pdf_paragraph_composition = [
            il_version_1.PdfParagraphComposition(
                pdf_same_style_unicode_characters=(
                    il_version_1.PdfSameStyleUnicodeCharacters(
                        unicode=unicode_,
                        debug_info=False,
                    )
                )
            )
        ]
        return p

    def test_debug_stub_by_unicode(self):
        for u in ("fallback_line", "title", "plain text", "abandon"):
            assert is_layout_debug_stub(self._stub(u)) is True
        glued = self._real("fallback_linefallback_linefallback_line")
        glued.unicode = "fallback_linefallback_linefallback_line"
        assert is_layout_debug_stub(glued) is True

    def test_debug_stub_by_debug_composition(self):
        p = self._stub("not a class name")
        assert is_layout_debug_stub(p) is True

    def test_real_xobj_id_minus1_not_stub(self):
        """xobj_id == -1 alone must NOT mark a real paragraph as a stub."""
        assert is_layout_debug_stub(self._real()) is False
        assert is_layout_debug_stub(self._real("Chapter 3")) is False


class TestFigureWrapParagraph:
    @staticmethod
    def _para(widths=None, lines=None):
        p = il_version_1.PdfParagraph()
        if widths:
            avg = sum(widths) / len(widths)
            p.reference_metrics = il_version_1.ReferenceMetrics(
                line_count=len(widths),
                avg_line_width=avg,
                last_line_width=widths[-1],
                last_line_ratio=widths[-1] / avg,
                font_size=12.0,
                per_line_widths=list(widths),
            )
        if lines:
            p.pdf_paragraph_composition = [
                il_version_1.PdfParagraphComposition(
                    pdf_line=il_version_1.PdfLine(
                        box=il_version_1.Box(x=x, y=0, x2=x2, y2=10)
                    )
                )
                for x, x2 in lines
            ]
        return p

    def test_taper_via_reference_metrics(self):
        assert is_figure_wrap_paragraph(self._para(widths=[194, 174, 143, 67])) is True
        assert is_figure_wrap_paragraph(self._para(widths=[467, 467, 258])) is False

    def test_taper_via_polluted_midcap_widths(self):
        polluted = [
            7.1, 16.6, 2.7, 22.4, 8.2, 41.4,
            258.6, 249.6, 231.6, 197.6, 177.6, 146.7, 122.6, 103.6, 63.7,
        ]
        assert is_figure_wrap_paragraph(self._para(widths=polluted)) is True

    def test_line_box_fallback(self):
        taper_lines = [(375.9, 569.5), (395.5, 569.5), (426.9, 569.5)]
        assert is_figure_wrap_paragraph(self._para(lines=taper_lines)) is True
        aligned = [(100.0, 500.0), (100.0, 500.0)]
        assert is_figure_wrap_paragraph(self._para(lines=aligned)) is False

    def test_left_fixed_oa_p59_photo_on_right(self):
        """OA p59 wrap body: left edge pinned at ~102, right edge steps in."""
        lines = [
            (101.87, 333.64),
            (102.53, 340.67),
            (102.00, 342.65),
            (102.91, 333.62),
            (102.28, 325.63),
            (102.22, 322.61),
            (102.13, 320.65),
        ]
        assert is_figure_wrap_paragraph(self._para(lines=lines)) is True
        # Flat body column (both edges pinned) is not a wrap.
        flat = [(102.0, 340.0), (102.0, 340.0), (102.0, 338.0)]
        assert is_figure_wrap_paragraph(self._para(lines=flat)) is False


class TestUniformCjkReferenceWidths:
    def test_keeps_taper(self):
        out = Typesetting._uniform_cjk_reference_widths([194.0, 174.0, 143.0, 67.0])
        assert out == [194.0, 174.0, 143.0, 67.0]

    def test_collapses_short_last_line(self):
        assert Typesetting._uniform_cjk_reference_widths([467.0, 467.0, 258.0]) == [467.0]

    def test_collapses_flat_narrow_column(self):
        assert Typesetting._uniform_cjk_reference_widths([180.0, 180.0, 175.0, 100.0]) == [180.0]


class TestPreExpandSkipsFigureWrap:
    def test_taper_para_returns_original_box(self):
        ts = Typesetting.__new__(Typesetting)
        box = il_version_1.Box(x=375.9, y=234.9, x2=569.5, y2=284.9)
        para = TestFigureWrapParagraph._para(widths=[194, 174, 143, 67])
        page = il_version_1.Page(page_number=0)
        out = ts._pre_expand_narrow_box(box, para, page, [object()], apply_layout=True)
        assert out is box

    def test_non_taper_para_not_short_circuited(self):
        """Without a taper signature the helper falls through (needs content)."""
        ts = Typesetting.__new__(Typesetting)
        box = il_version_1.Box(x=375.9, y=234.9, x2=569.5, y2=284.9)
        para = TestFigureWrapParagraph._para(widths=[467, 467, 258])
        page = il_version_1.Page(page_number=0)
        out = ts._pre_expand_narrow_box(box, para, page, [object()], apply_layout=True)
        assert out is box  # content_w unknown for [object()]; must not crash

    def test_wrap_column_intent_skips_without_taper_metrics(self):
        """P2: WRAP_COLUMN / wrap_shape disables pre-expand even if no taper rm."""
        from babeldoc.format.pdf.document_il.utils.layout_intent import LayoutIntent
        from babeldoc.format.pdf.document_il.utils.layout_intent import LayoutIntentRole

        ts = Typesetting.__new__(Typesetting)
        box = il_version_1.Box(x=375.9, y=234.9, x2=569.5, y2=284.9)
        para = TestFigureWrapParagraph._para(widths=[467, 467, 258])
        para.layout_intent = LayoutIntent(
            role=LayoutIntentRole.WRAP_COLUMN,
            design_box=il_version_1.Box(x=375.9, y=234.9, x2=569.5, y2=284.9),
            top_inset=0.0,
            bottom_inset=0.0,
            wrap_shape=[(0.0, 193.6), (19.6, 174.0)],
        )
        page = il_version_1.Page(page_number=0)
        out = ts._pre_expand_narrow_box(box, para, page, [object()], apply_layout=True)
        assert out is box


class TestTypesetWrapLine:
    """Layout-First P2: pure wrap_shape API + typesetting wire."""

    def test_wrap_line_pins_right_edge(self):
        from babeldoc.format.pdf.document_il.utils.wrap_shape import typeset_wrap_line

        design = il_version_1.Box(x=375.9, y=234.9, x2=569.5, y2=284.9)
        shape = [(4.0, 194.0), (20.0, 174.0), (50.0, 143.0), (126.0, 67.0)]
        for i in range(len(shape)):
            _left, right = typeset_wrap_line(design, shape, i)
            assert right == 569.5

    def test_wrap_line_left_steps_not_mirror(self):
        from babeldoc.format.pdf.document_il.utils.wrap_shape import typeset_wrap_line

        design = il_version_1.Box(x=375.9, y=234.9, x2=569.5, y2=284.9)
        shape = [(4.0, 194.0), (20.0, 174.0), (50.0, 143.0), (126.0, 67.0)]
        lefts = []
        for i, (_off, width) in enumerate(shape):
            left, right = typeset_wrap_line(design, shape, i)
            assert left == right - width
            lefts.append(left)
        assert lefts[0] < lefts[1] < lefts[2] < lefts[3]
        rights = [typeset_wrap_line(design, shape, i)[1] for i in range(len(shape))]
        assert len(set(rights)) == 1

    def test_wrap_line_extra_idx_reuses_last_width(self):
        from babeldoc.format.pdf.document_il.utils.wrap_shape import typeset_wrap_line

        design = il_version_1.Box(x=100.0, y=0.0, x2=300.0, y2=50.0)
        shape = [(0.0, 200.0), (40.0, 160.0)]
        left, right = typeset_wrap_line(design, shape, 5)
        assert right == 300.0
        assert left == 300.0 - 160.0

    def test_wrap_line_rejects_none_design_box(self):
        import pytest
        from babeldoc.format.pdf.document_il.utils.wrap_shape import typeset_wrap_line

        with pytest.raises(TypeError):
            typeset_wrap_line(None, [(0.0, 100.0)], 0)  # type: ignore[arg-type]

    def test_role_only_synthesizes_shape_from_widths(self):
        """WRAP_COLUMN + wrap_shape=None still pins via reference widths."""
        from babeldoc.format.pdf.document_il.utils.layout_intent import LayoutIntent
        from babeldoc.format.pdf.document_il.utils.layout_intent import LayoutIntentRole
        from babeldoc.format.pdf.document_il.utils.wrap_shape import get_active_wrap
        from babeldoc.format.pdf.document_il.utils.wrap_shape import resolve_wrap_shape
        from babeldoc.format.pdf.document_il.utils.wrap_shape import typeset_wrap_line

        design = il_version_1.Box(x=375.9, y=234.9, x2=569.5, y2=284.9)
        para = TestFigureWrapParagraph._para(widths=[194, 174, 143, 67])
        para.layout_intent = LayoutIntent(
            role=LayoutIntentRole.WRAP_COLUMN,
            design_box=design,
            top_inset=0.0,
            bottom_inset=0.0,
            wrap_shape=None,
        )
        shape = resolve_wrap_shape(para)
        assert shape == [(0.0, 194.0), (0.0, 174.0), (0.0, 143.0), (0.0, 67.0)]
        active = get_active_wrap(para, enabled=True)
        assert active is not None
        left, right = typeset_wrap_line(active[0], active[1], 2)
        assert right == 569.5
        assert left == 569.5 - 143.0

    def test_resolve_shape_without_intent_via_figure_wrap(self):
        """Extract skip: taper metrics alone still yield a pin shape."""
        from babeldoc.format.pdf.document_il.utils.wrap_shape import resolve_wrap_shape

        para = TestFigureWrapParagraph._para(widths=[194, 174, 143, 67])
        assert para.layout_intent is None
        assert resolve_wrap_shape(para) == [
            (0.0, 194.0),
            (0.0, 174.0),
            (0.0, 143.0),
            (0.0, 67.0),
        ]

    def test_right_align_flush_short_line_to_pin(self):
        """Underfilled wrap lines must end at available_x2 (design right)."""

        class _U:
            def __init__(self):
                self.box = il_version_1.Box(x=315.0, y=100.0, x2=447.0, y2=112.0)

            def shift_x(self, dx: float) -> None:
                self.box.x += dx
                self.box.x2 += dx

        unit = _U()
        # Envelope [314, 573]; short ink 132pt placed LTR → flush right after align.
        Typesetting._apply_line_horizontal_alignment(
            [unit], 0, 1, 314.0, 572.6, "right"
        )
        assert abs(unit.box.x2 - 572.6) < 0.05
        assert abs(unit.box.x - (572.6 - 132.0)) < 0.05

    def test_replace_matrix_no_wrap_shape_unchanged(self):
        """Without wrap_shape, resolve falls through to zone + reference cap."""
        ts = Typesetting.__new__(Typesetting)
        ts._current_zone_index = None
        box = il_version_1.Box(x=100.0, y=0.0, x2=400.0, y2=50.0)
        para = il_version_1.PdfParagraph()  # no layout_intent
        intervals = ts._resolve_line_intervals(
            10.0,
            20.0,
            box,
            paragraph=para,
            line_idx=0,
            reference_widths=[150.0, 150.0],
            alignment="left",
        )
        assert intervals == [(100.0, 250.0)]

    def test_replace_matrix_wrap_shape_overrides_reference_cap(self):
        from babeldoc.format.pdf.document_il.utils.layout_intent import LayoutIntent
        from babeldoc.format.pdf.document_il.utils.layout_intent import LayoutIntentRole

        ts = Typesetting.__new__(Typesetting)
        ts._current_zone_index = None
        design = il_version_1.Box(x=375.9, y=234.9, x2=569.5, y2=284.9)
        para = il_version_1.PdfParagraph()
        para.layout_intent = LayoutIntent(
            role=LayoutIntentRole.WRAP_COLUMN,
            design_box=design,
            top_inset=0.0,
            bottom_inset=0.0,
            wrap_shape=[(4.0, 194.0), (20.0, 174.0)],
        )
        box = il_version_1.Box(x=0.0, y=0.0, x2=600.0, y2=300.0)
        intervals = ts._resolve_line_intervals(
            250.0,
            270.0,
            box,
            paragraph=para,
            line_idx=1,
            reference_widths=[500.0, 500.0],
            alignment="left",
        )
        assert len(intervals) == 1
        left, right = intervals[0]
        assert right == 569.5
        assert left == 569.5 - 174.0

    def test_replace_matrix_role_only_no_shape_still_pins(self):
        from babeldoc.format.pdf.document_il.utils.layout_intent import LayoutIntent
        from babeldoc.format.pdf.document_il.utils.layout_intent import LayoutIntentRole

        ts = Typesetting.__new__(Typesetting)
        ts._current_zone_index = None
        design = il_version_1.Box(x=375.9, y=234.9, x2=569.5, y2=284.9)
        para = TestFigureWrapParagraph._para(widths=[194, 174, 143, 67])
        para.layout_intent = LayoutIntent(
            role=LayoutIntentRole.WRAP_COLUMN,
            design_box=design,
            top_inset=0.0,
            bottom_inset=0.0,
            wrap_shape=None,
        )
        box = il_version_1.Box(x=0.0, y=0.0, x2=600.0, y2=300.0)
        intervals = ts._resolve_line_intervals(
            250.0,
            270.0,
            box,
            paragraph=para,
            line_idx=3,
            reference_widths=[500.0],
            alignment="left",
        )
        assert intervals == [(569.5 - 67.0, 569.5)]

    def test_flag_off_ignores_wrap_shape(self):
        from types import SimpleNamespace

        from babeldoc.format.pdf.document_il.utils.layout_intent import LayoutIntent
        from babeldoc.format.pdf.document_il.utils.layout_intent import LayoutIntentRole

        ts = Typesetting.__new__(Typesetting)
        ts.translation_config = SimpleNamespace(enable_layout_intent_wrap=False)
        ts._current_zone_index = None
        design = il_version_1.Box(x=375.9, y=234.9, x2=569.5, y2=284.9)
        para = il_version_1.PdfParagraph()
        para.layout_intent = LayoutIntent(
            role=LayoutIntentRole.WRAP_COLUMN,
            design_box=design,
            top_inset=0.0,
            bottom_inset=0.0,
            wrap_shape=[(4.0, 194.0)],
        )
        box = il_version_1.Box(x=100.0, y=0.0, x2=400.0, y2=50.0)
        intervals = ts._resolve_line_intervals(
            10.0,
            20.0,
            box,
            paragraph=para,
            line_idx=0,
            reference_widths=[150.0],
            alignment="left",
        )
        assert intervals == [(100.0, 250.0)]

    def test_should_skip_pre_expand_single_predicate(self):
        from babeldoc.format.pdf.document_il.utils.layout_intent import LayoutIntent
        from babeldoc.format.pdf.document_il.utils.layout_intent import LayoutIntentRole
        from babeldoc.format.pdf.document_il.utils.wrap_shape import (
            should_skip_pre_expand_for_wrap,
        )

        taper = TestFigureWrapParagraph._para(widths=[194, 174, 143, 67])
        assert should_skip_pre_expand_for_wrap(taper, wrap_enabled=False) is True
        body = TestFigureWrapParagraph._para(widths=[467, 467, 258])
        assert should_skip_pre_expand_for_wrap(body, wrap_enabled=True) is False
        body.layout_intent = LayoutIntent(
            role=LayoutIntentRole.WRAP_COLUMN,
            design_box=il_version_1.Box(x=0, y=0, x2=100, y2=10),
            top_inset=0.0,
            bottom_inset=0.0,
            wrap_shape=[(0.0, 80.0)],
        )
        assert should_skip_pre_expand_for_wrap(body, wrap_enabled=True) is True


class TestLayoutDebugStubPatterns:
    def test_add_debug_information_labels(self):
        for u in ("paragraph[z44NW]-[title]", "pagenumber: 19"):
            p = TestIsLayoutDebugStub._stub(u)
            assert is_layout_debug_stub(p) is True


class TestSanitizeCjkWrapShape:
    """CJK orphan protection: degenerate wrap pockets must not strand a
    single/double-character line (acceptance V3)."""

    def test_oa_p19_sliver_replaced_by_next_valid(self):
        from babeldoc.format.pdf.document_il.utils.wrap_shape import (
            sanitize_wrap_shape_for_cjk,
        )

        # Real OA p19 WRAP_COLUMN shape: entry 2 is a ~1pt sliver that forced
        # "的" onto its own line; entry 9 is another sliver.
        shape = [
            (9.528, 133.728),
            (0.0, 193.56),
            (57.252, 0.972),
            (31.704, 155.556),
            (19.56, 174.06),
            (72.156, 114.54),
            (51.012, 142.608),
            (128.376, 58.86),
            (140.664, 52.932),
            (126.48, 1.38),
        ]
        out = sanitize_wrap_shape_for_cjk(shape)
        assert out is not None
        assert len(out) == len(shape)
        # Sliver at idx 2 borrows the next valid width (idx 3: 155.556).
        assert out[2] == (57.252, 155.556)
        # Last sliver borrows the previous valid width (idx 8: 52.932).
        assert out[9] == (126.48, 52.932)
        # All pockets now usable for ≥2 CJK chars.
        assert all(w >= 24.0 for _off, w in out)

    def test_idempotent(self):
        from babeldoc.format.pdf.document_il.utils.wrap_shape import (
            sanitize_wrap_shape_for_cjk,
        )

        shape = [(0.0, 193.6), (19.6, 174.0), (50.0, 143.0), (126.0, 67.0)]
        once = sanitize_wrap_shape_for_cjk(shape)
        twice = sanitize_wrap_shape_for_cjk(once)
        assert once == twice

    def test_clean_shape_unchanged(self):
        from babeldoc.format.pdf.document_il.utils.wrap_shape import (
            sanitize_wrap_shape_for_cjk,
        )

        shape = [(0.0, 193.6), (19.6, 174.0), (50.0, 143.0), (126.0, 67.0)]
        assert sanitize_wrap_shape_for_cjk(shape) is shape

    def test_all_degenerate_falls_back_to_floor(self):
        from babeldoc.format.pdf.document_il.utils.wrap_shape import (
            sanitize_wrap_shape_for_cjk,
        )

        out = sanitize_wrap_shape_for_cjk([(0.0, 1.0), (5.0, 2.0)])
        assert out is not None
        assert all(w >= 24.0 for _off, w in out)

    def test_none_and_empty(self):
        from babeldoc.format.pdf.document_il.utils.wrap_shape import (
            sanitize_wrap_shape_for_cjk,
        )

        assert sanitize_wrap_shape_for_cjk(None) is None
        assert sanitize_wrap_shape_for_cjk([]) == []

    def test_oa_p19_relative_sliver_42pt_replaced(self):
        """Current p19 dump: 42pt pocket is >24pt floor but still a shred line."""
        from babeldoc.format.pdf.document_il.utils.wrap_shape import (
            sanitize_wrap_shape_for_cjk,
        )

        shape = [
            (58.8, 84.4),
            (0.0, 193.6),
            (57.3, 42.4),
            (37.9, 137.0),
            (19.6, 174.1),
            (72.2, 106.6),
            (51.0, 142.6),
        ]
        out = sanitize_wrap_shape_for_cjk(shape)
        assert out is not None
        assert out[2][1] >= 100.0
        assert out[1][1] == 193.6


class TestCjkWrapShapeSanitizeWiring:
    """CJK consumption path must sanitize before interval planning (p19)."""

    def test_resolve_line_intervals_uses_sanitized_shape(self):
        from babeldoc.format.pdf.document_il.midend.typesetting import Typesetting
        from babeldoc.format.pdf.document_il.utils.layout_intent import LayoutIntent
        from babeldoc.format.pdf.document_il.utils.layout_intent import LayoutIntentRole
        from babeldoc.format.pdf.document_il.utils.layout_intent import WrapMode

        ts = Typesetting.__new__(Typesetting)
        ts.is_cjk = True
        ts._wrap_enabled = True
        ts._layout_drop_figure_zones = False
        ts._layout_attempt = None
        ts._current_zone_index = None
        ts.translation_config = None
        design = il_version_1.Box(x=375.912, y=234.95, x2=569.532, y2=284.95)
        para = TestFigureWrapParagraph._para(widths=[194, 174, 143, 67])
        para.box = il_version_1.Box(x=375.912, y=234.95, x2=596.0, y2=284.95)
        para.layout_intent = LayoutIntent(
            role=LayoutIntentRole.WRAP_COLUMN,
            design_box=design,
            top_inset=0.0,
            bottom_inset=0.0,
            wrap_shape=[
                (9.528, 133.728),
                (0.0, 193.56),
                (57.252, 0.972),
                (31.704, 155.556),
            ],
            wrap_mode=WrapMode.RIGHT_FIXED,
        )
        page = il_version_1.Page(page_number=18)
        intervals = ts._resolve_line_intervals(
            241.7,
            258.0,
            para.box,
            paragraph=para,
            line_idx=2,
            reference_widths=None,
        )
        # The sliver (would have been an 8pt pocket) is replaced by the next
        # valid width (155.556) — pocket must be wide enough for ≥2 CJK chars.
        assert len(intervals) == 1
        x1, x2 = intervals[0]
        assert x2 - x1 >= 24.0
        # Non-mutating: the intent's shape stays the raw extractor output.
        assert para.layout_intent.wrap_shape[2][1] == 0.972
