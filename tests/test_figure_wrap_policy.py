"""Figure-wrap policy: single entry point, debug-stub predicate, pre-expand.

Covers review blockers B1/B2/B5 for OA p19 TAKING CHARGE (figure-wrap taper
columns must not be pull-quotes, must not pre-expand, must keep per-line
reference widths; layout-label stubs must be excluded by content signals,
not xobj_id).
"""

from __future__ import annotations

from babeldoc.format.pdf.document_il import il_version_1
from babeldoc.format.pdf.document_il.midend.typesetting import Typesetting
from babeldoc.format.pdf.document_il.utils.figure_wrap import (
    is_figure_wrap_paragraph,
    is_figure_wrap_taper,
)
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

    def test_line_box_fallback(self):
        taper_lines = [(375.9, 569.5), (395.5, 569.5), (426.9, 569.5)]
        assert is_figure_wrap_paragraph(self._para(lines=taper_lines)) is True
        aligned = [(100.0, 500.0), (100.0, 500.0)]
        assert is_figure_wrap_paragraph(self._para(lines=aligned)) is False


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
    """Layout-First P2: right pin + left-edge step (not mirror taper)."""

    DESIGN = None  # filled in tests via Box

    def test_wrap_line_pins_right_edge(self):
        design = il_version_1.Box(x=375.9, y=234.9, x2=569.5, y2=284.9)
        # OA p19-style: left steps in, right stays pinned near page margin.
        shape = [(4.0, 194.0), (20.0, 174.0), (50.0, 143.0), (126.0, 67.0)]
        for i in range(len(shape)):
            _left, right = Typesetting._typeset_wrap_line(design, shape, i)
            assert right == 569.5

    def test_wrap_line_left_steps_not_mirror(self):
        design = il_version_1.Box(x=375.9, y=234.9, x2=569.5, y2=284.9)
        shape = [(4.0, 194.0), (20.0, 174.0), (50.0, 143.0), (126.0, 67.0)]
        lefts = []
        for i, (_off, width) in enumerate(shape):
            left, right = Typesetting._typeset_wrap_line(design, shape, i)
            assert left == right - width
            lefts.append(left)
        # Left edge steps right as width shrinks — not fixed-left mirror taper.
        assert lefts[0] < lefts[1] < lefts[2] < lefts[3]
        # Mirror would keep left at design.x and shrink right; we never do that.
        rights = [
            Typesetting._typeset_wrap_line(design, shape, i)[1]
            for i in range(len(shape))
        ]
        assert len(set(rights)) == 1

    def test_wrap_line_extra_idx_reuses_last_width(self):
        design = il_version_1.Box(x=100.0, y=0.0, x2=300.0, y2=50.0)
        shape = [(0.0, 200.0), (40.0, 160.0)]
        left, right = Typesetting._typeset_wrap_line(design, shape, 5)
        assert right == 300.0
        assert left == 300.0 - 160.0

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
        # Cap from available start: width 150 from box.x → (100, 250)
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
        # Even with a large box and large reference widths, wrap path wins.
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


class TestLayoutDebugStubPatterns:
    def test_add_debug_information_labels(self):
        for u in ("paragraph[z44NW]-[title]", "pagenumber: 19"):
            p = TestIsLayoutDebugStub._stub(u)
            assert is_layout_debug_stub(p) is True
