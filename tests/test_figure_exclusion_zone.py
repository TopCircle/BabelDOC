"""Tests for figure exclusion zones and polygon scanline support.

Tests cover:
- _collect_figure_zones() from PdfFigure and PdfForm
- polygon_scanline_blocked_intervals() for convex and concave polygons
- _subtract_blocked_from_range() for interval arithmetic
- ExclusionZoneIndex with polygon zones
"""

from __future__ import annotations

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import Page
from babeldoc.format.pdf.document_il.il_version_1 import PdfFigure
from babeldoc.format.pdf.document_il.il_version_1 import PdfForm
from babeldoc.format.pdf.document_il.il_version_1 import PdfFormSubtype
from babeldoc.format.pdf.document_il.midend.exclusion_zone import ExclusionZone
from babeldoc.format.pdf.document_il.midend.exclusion_zone import ExclusionZoneBuilder
from babeldoc.format.pdf.document_il.midend.exclusion_zone import ExclusionZoneIndex
from babeldoc.format.pdf.document_il.midend.exclusion_zone import MIN_USABLE_LINE_WIDTH_PT
from babeldoc.format.pdf.document_il.midend.exclusion_zone import ZONE_FIGURE
from babeldoc.format.pdf.document_il.midend.exclusion_zone import _collect_figure_zones
from babeldoc.format.pdf.document_il.midend.exclusion_zone import _max_horizontal_residual
from babeldoc.format.pdf.document_il.midend.exclusion_zone import (
    _subtract_blocked_from_range,
)
from babeldoc.format.pdf.document_il.midend.exclusion_zone import min_usable_line_width
from babeldoc.format.pdf.document_il.midend.exclusion_zone import (
    polygon_scanline_blocked_intervals,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_page(
    width: float = 612.0,
    height: float = 792.0,
    figures: list[PdfFigure] | None = None,
    forms: list[PdfForm] | None = None,
) -> Page:
    page = Page(page_number=1)
    page.cropbox = type("CropBox", (), {"box": Box(x=0, y=0, x2=width, y2=height)})()
    page.pdf_figure = figures or []
    page.pdf_form = forms or []
    page.pdf_paragraph = []
    return page


def _make_figure(x: float, y: float, x2: float, y2: float) -> PdfFigure:
    fig = PdfFigure()
    fig.box = Box(x=x, y=y, x2=x2, y2=y2)
    return fig


def _make_form(
    x: float, y: float, x2: float, y2: float, form_type: str = "image"
) -> PdfForm:
    form = PdfForm()
    form.box = Box(x=x, y=y, x2=x2, y2=y2)
    form.form_type = form_type
    form.xobj_id = 1
    form.render_order = 0
    form.ctm = [1, 0, 0, 1, 0, 0]
    form.pdf_form_subtype = PdfFormSubtype()
    return form


# ---------------------------------------------------------------------------
# polygon_scanline_blocked_intervals tests
# ---------------------------------------------------------------------------


class TestPolygonScanline:
    """Test polygon scanline intersection algorithm."""

    def test_rectangle(self):
        """Rectangle polygon produces correct blocked interval."""
        # Rectangle from (100, 100) to (300, 300)
        polygon = ((100, 100), (300, 100), (300, 300), (100, 300))

        # Scanline through the middle
        intervals = polygon_scanline_blocked_intervals(200, polygon)
        assert len(intervals) == 1
        assert abs(intervals[0][0] - 100) < 0.01
        assert abs(intervals[0][1] - 300) < 0.01

    def test_rectangle_below(self):
        """Scanline below polygon returns empty."""
        polygon = ((100, 100), (300, 100), (300, 300), (100, 300))
        intervals = polygon_scanline_blocked_intervals(50, polygon)
        assert intervals == []

    def test_rectangle_above(self):
        """Scanline above polygon returns empty."""
        polygon = ((100, 100), (300, 100), (300, 300), (100, 300))
        intervals = polygon_scanline_blocked_intervals(350, polygon)
        assert intervals == []

    def test_triangle(self):
        """Triangle produces narrowing blocked interval."""
        # Triangle: base at y=100 from x=100 to x=300, apex at (200, 300)
        polygon = ((100, 100), (300, 100), (200, 300))

        # At y=150 (1/4 up), width should be ~75% of base
        intervals = polygon_scanline_blocked_intervals(150, polygon)
        assert len(intervals) == 1
        # At y=150: t = (150-100)/(300-100) = 0.25
        # left edge: 100 + 0.25 * (200-100) = 125
        # right edge: 300 + 0.25 * (200-300) = 275
        assert abs(intervals[0][0] - 125) < 0.01
        assert abs(intervals[0][1] - 275) < 0.01

    def test_triangle_apex(self):
        """At triangle apex, blocked interval is very narrow."""
        polygon = ((100, 100), (300, 100), (200, 300))
        # At y=290 (near apex), interval should be narrow
        intervals = polygon_scanline_blocked_intervals(290, polygon)
        assert len(intervals) == 1
        width = intervals[0][1] - intervals[0][0]
        assert width < 30  # Should be narrow

    def test_empty_polygon(self):
        """Empty polygon returns empty list."""
        assert polygon_scanline_blocked_intervals(100, ()) == []
        assert polygon_scanline_blocked_intervals(100, ((100, 100),)) == []
        assert polygon_scanline_blocked_intervals(100, ((100, 100), (200, 200))) == []

    def test_vertex_on_scanline(self):
        """Vertex exactly on scanline doesn't produce degenerate interval."""
        # Diamond: (200, 100), (300, 200), (200, 300), (100, 200)
        polygon = ((200, 100), (300, 200), (200, 300), (100, 200))

        # Scanline at y=200 (passes through two vertices)
        intervals = polygon_scanline_blocked_intervals(200, polygon)
        # Should produce one interval from 100 to 300
        assert len(intervals) == 1
        assert abs(intervals[0][0] - 100) < 0.01
        assert abs(intervals[0][1] - 300) < 0.01

    def test_l_shape(self):
        """L-shaped polygon (concave) can produce multiple intervals."""
        # L-shape: outer rectangle with a notch cut from top-right
        # Vertices: (100,100) → (300,100) → (300,200) → (200,200) → (200,300) → (100,300)
        polygon = (
            (100, 100), (300, 100), (300, 200),
            (200, 200), (200, 300), (100, 300),
        )

        # At y=250 (in the vertical arm), interval should be [100, 200]
        intervals = polygon_scanline_blocked_intervals(250, polygon)
        assert len(intervals) == 1
        assert abs(intervals[0][0] - 100) < 0.01
        assert abs(intervals[0][1] - 200) < 0.01

    def test_horizontal_edge_skipped(self):
        """Horizontal edges are properly handled."""
        # Rectangle with explicit horizontal edges
        polygon = ((100, 100), (300, 100), (300, 200), (100, 200))

        # Scanline at y=100 (bottom edge) — should include the interior
        intervals = polygon_scanline_blocked_intervals(100, polygon)
        assert len(intervals) == 1

        # Scanline at y=200 (top edge) — vertex-on-scanline guard skips
        intervals = polygon_scanline_blocked_intervals(200, polygon)
        # At y=200, top edge is skipped, so no intersections → empty
        assert intervals == []


# ---------------------------------------------------------------------------
# _subtract_blocked_from_range tests
# ---------------------------------------------------------------------------


class TestSubtractBlocked:
    """Test blocked interval subtraction from available range."""

    def test_no_blocked(self):
        """No blocked intervals returns original range."""
        assert _subtract_blocked_from_range(0, 100, []) == (0, 100)

    def test_blocked_in_middle(self):
        """Blocked in middle returns wider side."""
        # [0, 100] with blocked [30, 50] → [(0, 30), (50, 100)] → (50, 100)
        result = _subtract_blocked_from_range(0, 100, [(30, 50)])
        assert result == (50, 100)

    def test_blocked_on_right(self):
        """Blocked on right shrinks range."""
        # [0, 100] with blocked [70, 100] → [(0, 70)]
        result = _subtract_blocked_from_range(0, 100, [(70, 100)])
        assert result == (0, 70)

    def test_blocked_on_left(self):
        """Blocked on left shrinks range."""
        # [0, 100] with blocked [0, 30] → [(30, 100)]
        result = _subtract_blocked_from_range(0, 100, [(0, 30)])
        assert result == (30, 100)

    def test_fully_blocked(self):
        """Fully blocked returns zero-width range."""
        result = _subtract_blocked_from_range(0, 100, [(0, 100)])
        assert result == (0, 0)

    def test_multiple_blocked_picks_widest(self):
        """Multiple blocked intervals picks the widest remaining."""
        # [0, 100] with blocked [10, 30], [60, 80]
        # → [(0, 10), (30, 60), (80, 100)] → (30, 60) width=30
        result = _subtract_blocked_from_range(0, 100, [(10, 30), (60, 80)])
        assert result == (30, 60)

    def test_overlapping_blocked_merged(self):
        """Overlapping blocked intervals are merged."""
        # [0, 100] with blocked [20, 50], [40, 70] → merged [20, 70]
        # → [(0, 20), (70, 100)] → (70, 100) width=30
        result = _subtract_blocked_from_range(0, 100, [(20, 50), (40, 70)])
        assert result == (70, 100)


# ---------------------------------------------------------------------------
# ExclusionZoneIndex with polygon zones
# ---------------------------------------------------------------------------


class TestPolygonExclusionZoneIndex:
    """Test ExclusionZoneIndex with polygon zones."""

    def test_rectangular_zone_unchanged(self):
        """Rectangular zones still work correctly."""
        zone = ExclusionZone(
            box=Box(x=300, y=0, x2=400, y2=792),
            kind=ZONE_FIGURE,
        )
        index = ExclusionZoneIndex([zone])
        x, x2 = index.get_available_x_range(0, 20, 0, 612)
        # Should keep left side (0, 300) since it's wider than right (400, 612)
        assert abs(x - 0) < 0.01
        assert abs(x2 - 300) < 0.01

    def test_polygon_zone_triangle(self):
        """Polygon zone with triangle shape blocks correctly."""
        # Triangle in the right portion of the page
        polygon = ((300, 0), (600, 0), (450, 400))
        zone = ExclusionZone(
            box=Box(x=300, y=0, x2=600, y2=400),
            kind=ZONE_FIGURE,
            polygon=polygon,
        )
        index = ExclusionZoneIndex([zone])

        # At y=100 (near base), triangle covers [337.5, 562.5]
        # Available: [0, 337.5] vs [562.5, 612] → [0, 337.5] is wider
        x, x2 = index.get_available_x_range(90, 110, 0, 612)
        assert abs(x - 0) < 1.0
        assert abs(x2 - 337.5) < 1.0

    def test_polygon_zone_narrow_at_apex(self):
        """Near triangle apex, more space becomes available."""
        polygon = ((300, 0), (600, 0), (450, 400))
        zone = ExclusionZone(
            box=Box(x=300, y=0, x2=600, y2=400),
            kind=ZONE_FIGURE,
            polygon=polygon,
        )
        index = ExclusionZoneIndex([zone])

        # At y=350 (near apex), triangle covers ~[412, 487]
        # Available: [0, 412] vs [487, 612] → [0, 412] is wider
        x, x2 = index.get_available_x_range(340, 360, 0, 612)
        # Width should be > 400 (much more than at base)
        assert (x2 - x) > 400

    def test_mixed_rectangular_and_polygon(self):
        """Index handles mix of rectangular and polygon zones."""
        rect_zone = ExclusionZone(
            box=Box(x=0, y=0, x2=100, y2=792),
            kind=ZONE_FIGURE,
        )
        polygon = ((300, 0), (500, 0), (500, 400), (300, 400))
        poly_zone = ExclusionZone(
            box=Box(x=300, y=0, x2=500, y2=400),
            kind=ZONE_FIGURE,
            polygon=polygon,
        )
        index = ExclusionZoneIndex([rect_zone, poly_zone])

        # Rectangular zone blocks [0, 100], polygon blocks [300, 500]
        # Available: [100, 300] vs [500, 612] → [100, 300] is wider
        x, x2 = index.get_available_x_range(100, 120, 0, 612)
        assert abs(x - 100) < 0.01
        assert abs(x2 - 300) < 0.01


# ---------------------------------------------------------------------------
# _collect_figure_zones tests
# ---------------------------------------------------------------------------


class TestCollectFigureZones:
    """Test figure zone collection from page elements."""

    def test_empty_page(self):
        """Empty page produces no figure zones."""
        page = _make_page()
        zones = _collect_figure_zones(page)
        assert zones == []

    def test_pdf_figure(self):
        """PdfFigure objects become figure zones."""
        fig = _make_figure(100, 100, 300, 300)
        page = _make_page(figures=[fig])
        zones = _collect_figure_zones(page)
        assert len(zones) == 1
        assert zones[0].kind == ZONE_FIGURE
        assert zones[0].priority == 20

    def test_pdf_form_image(self):
        """PdfForm with form_type='image' becomes figure zone."""
        form = _make_form(100, 100, 300, 300)
        page = _make_page(forms=[form])
        zones = _collect_figure_zones(page)
        assert len(zones) == 1
        assert zones[0].kind == ZONE_FIGURE

    def test_pdf_form_non_image_ignored(self):
        """PdfForm with form_type='form' is ignored."""
        form = _make_form(100, 100, 300, 300, form_type="form")
        page = _make_page(forms=[form])
        zones = _collect_figure_zones(page)
        assert zones == []

    def test_deduplication(self):
        """Overlapping figure and form at same position are deduplicated."""
        fig = _make_figure(100, 100, 300, 300)
        form = _make_form(100, 100, 300, 300)
        page = _make_page(figures=[fig], forms=[form])
        zones = _collect_figure_zones(page)
        assert len(zones) == 1  # Deduplicated

    def test_padding_applied(self):
        """Figure zones have adaptive padding applied."""
        fig = _make_figure(100, 100, 300, 300)
        page = _make_page(figures=[fig])
        zones = _collect_figure_zones(page)
        assert len(zones) == 1
        box = zones[0].box
        # Box should be larger than original figure (padding added)
        assert box.x < 100
        assert box.y < 100
        assert box.x2 > 300
        assert box.y2 > 300

    def test_multiple_figures(self):
        """Multiple figures produce multiple zones."""
        fig1 = _make_figure(100, 100, 200, 200)
        fig2 = _make_figure(400, 400, 500, 500)
        page = _make_page(figures=[fig1, fig2])
        zones = _collect_figure_zones(page)
        assert len(zones) == 2


# ---------------------------------------------------------------------------
# filter_for_paragraph — drop false-positive figure zones over body text
# ---------------------------------------------------------------------------


class TestFilterForParagraph:
    """Figure zones that spill over body paragraphs must not crush scale."""

    def test_drops_figure_covering_body(self):
        """Needle residual under body → drop so layout uses full width."""
        # Body with a figure that leaves only a ~20pt strip (scale-crush case)
        body = Box(x=56, y=320, x2=554, y2=430)
        fig_zone = ExclusionZone(
            box=Box(x=56, y=320, x2=530, y2=430),
            kind=ZONE_FIGURE,
        )
        index = ExclusionZoneIndex([fig_zone])
        filtered = index.filter_for_paragraph(body)
        assert len(filtered.zones) == 0
        x1f, x2f = filtered.get_available_x_range(350, 370, body.x, body.x2)
        assert x1f == body.x and x2f == body.x2

    def test_drops_artistic_side_image_when_para_extends_into_figure(self):
        """Orgasms p.3/8/13: EN lines run past figure.x into the photo bbox.

        Hard-keeping the zone forces a uniform rectangular strip; drop so
        original reference_widths can recreate the freeform taper.
        """
        # Para AABB reaches ~x=560 while figure starts ~231 (EN lines ~250-400 wide)
        body = Box(x=56, y=100, x2=420, y2=700)
        fig_zone = ExclusionZone(
            box=Box(x=231, y=98.9, x2=613.1, y2=793.0),
            kind=ZONE_FIGURE,
        )
        assert body.x2 > fig_zone.box.x
        index = ExclusionZoneIndex([fig_zone])
        filtered = index.filter_for_paragraph(body)
        assert len(filtered.zones) == 0
        x1, x2 = filtered.get_available_x_range(200, 220, body.x, body.x2)
        assert x1 == body.x and x2 == body.x2

    def test_keeps_side_figure_beside_body(self):
        """Real float: figure on the right, body column on the left — keep zone."""
        body = Box(x=56, y=300, x2=300, y2=500)
        fig_zone = ExclusionZone(
            box=Box(x=320, y=300, x2=560, y2=500),
            kind=ZONE_FIGURE,
        )
        index = ExclusionZoneIndex([fig_zone])
        filtered = index.filter_for_paragraph(body)
        assert len(filtered.zones) == 1

    def test_always_keeps_quote_zones(self):
        """Pull-quote zones are kept even when overlapping a wide box."""
        from babeldoc.format.pdf.document_il.midend.exclusion_zone import ZONE_QUOTE

        body = Box(x=56, y=300, x2=564, y2=500)
        quote_zone = ExclusionZone(
            box=Box(x=340, y=320, x2=560, y2=450),
            kind=ZONE_QUOTE,
        )
        index = ExclusionZoneIndex([quote_zone])
        filtered = index.filter_for_paragraph(body)
        assert len(filtered.zones) == 1
        assert filtered.zones[0].kind == ZONE_QUOTE

    def test_no_zones_returns_self(self):
        index = ExclusionZoneIndex([])
        body = Box(x=56, y=300, x2=564, y2=500)
        assert index.filter_for_paragraph(body) is index

    def test_drops_figure_leaving_needle_residual(self):
        """Orgasms p.10-style: figure leaves only ~25pt strip on the right."""
        body = Box(x=56, y=100, x2=560, y2=200)
        # Almost full-width figure inside body y-range, residual right ~20pt
        fig_zone = ExclusionZone(
            box=Box(x=56, y=100, x2=540, y2=200),
            kind=ZONE_FIGURE,
        )
        residual = _max_horizontal_residual(body, fig_zone.box)
        assert residual < MIN_USABLE_LINE_WIDTH_PT

        index = ExclusionZoneIndex([fig_zone])
        # Without residual rule this would force a ~20pt column
        x1, x2 = index.get_available_x_range(120, 140, body.x, body.x2)
        # Line-level fallback OR residual filter must yield usable width
        filtered = index.filter_for_paragraph(body)
        assert len(filtered.zones) == 0
        x1f, x2f = filtered.get_available_x_range(120, 140, body.x, body.x2)
        assert x1f == body.x and x2f == body.x2
        assert (x2f - x1f) > 400

    def test_keeps_side_column_residual_wide_enough(self):
        """p.21-style: full-height side figure, body column ~200pt — keep zone."""
        # Body is already the left column next to a right image
        body = Box(x=56, y=100, x2=330, y2=700)
        fig_zone = ExclusionZone(
            box=Box(x=340, y=100, x2=600, y2=700),
            kind=ZONE_FIGURE,
        )
        # No horizontal overlap with body → residual = full body width
        residual = _max_horizontal_residual(body, fig_zone.box)
        assert residual > 200

        index = ExclusionZoneIndex([fig_zone])
        filtered = index.filter_for_paragraph(body)
        assert len(filtered.zones) == 1

    def test_keeps_right_float_beside_body_column(self):
        """Real wrap: body column left, figure right — little/no box overlap.

        Full-width body + large right figure would exceed max_coverage (p7 rule);
        production body boxes for wrap sit *beside* the float, not under it.
        """
        body = Box(x=56, y=300, x2=300, y2=500)
        fig_zone = ExclusionZone(
            box=Box(x=320, y=300, x2=560, y2=500),
            kind=ZONE_FIGURE,
        )
        residual = _max_horizontal_residual(body, fig_zone.box)
        assert residual >= 200

        index = ExclusionZoneIndex([fig_zone])
        filtered = index.filter_for_paragraph(body)
        assert len(filtered.zones) == 1

    def test_get_available_falls_back_when_strip_too_narrow(self):
        """Line-level safety net: narrow residual returns full default width."""
        body_x, body_x2 = 56.0, 560.0
        fig_zone = ExclusionZone(
            box=Box(x=56, y=100, x2=540, y2=200),
            kind=ZONE_FIGURE,
        )
        index = ExclusionZoneIndex([fig_zone])
        x1, x2 = index.get_available_x_range(
            120, 140, body_x, body_x2, min_width=MIN_USABLE_LINE_WIDTH_PT
        )
        assert x1 == body_x and x2 == body_x2

    def test_drop_all_figures_flag(self):
        body = Box(x=56, y=300, x2=560, y2=500)
        fig_zone = ExclusionZone(
            box=Box(x=400, y=300, x2=550, y2=450),
            kind=ZONE_FIGURE,
        )
        index = ExclusionZoneIndex([fig_zone])
        filtered = index.filter_for_paragraph(body, drop_all_figures=True)
        assert len(filtered.zones) == 0

    def test_min_usable_line_width_scales_with_para(self):
        assert min_usable_line_width(None) == MIN_USABLE_LINE_WIDTH_PT
        # 15% of 500 = 75 > 28
        assert min_usable_line_width(500) == 75.0
        # 15% of 100 = 15 < 28 → floor
        assert min_usable_line_width(100) == MIN_USABLE_LINE_WIDTH_PT


# ---------------------------------------------------------------------------
# ExclusionZoneBuilder integration
# ---------------------------------------------------------------------------


class TestExclusionZoneBuilder:
    """Test that ExclusionZoneBuilder includes figure zones."""

    def test_builder_includes_figures(self):
        """Builder should include figure zones alongside quote zones."""
        fig = _make_figure(400, 100, 550, 300)
        page = _make_page(figures=[fig])
        zones = ExclusionZoneBuilder.build(page)
        figure_zones = [z for z in zones if z.kind == ZONE_FIGURE]
        assert len(figure_zones) == 1
