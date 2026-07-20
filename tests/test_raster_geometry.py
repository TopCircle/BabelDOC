"""Unit tests for raster pixel-budget helpers (v0.6.4 follow-up)."""

from __future__ import annotations

import math

from babeldoc.format.pdf.document_il.utils.raster_geometry import (
    DEFAULT_MAX_PIXELS,
    RasterGeometry,
    _pixel_dimensions,
    max_dpi_within_pixel_budget,
)


class TestPixelDimensions:
    def test_ceil_edges(self):
        # 100pt at 72dpi → 100px; 100pt at 144dpi → 200px
        assert _pixel_dimensions(100.0, 50.0, 72) == (100, 50)
        w, h = _pixel_dimensions(100.0, 50.0, 144)
        assert w == 200
        assert h == 100

    def test_minimum_one_pixel(self):
        assert _pixel_dimensions(0.001, 0.001, 1) == (1, 1)


class TestMaxDpiWithinBudget:
    def test_respects_requested_cap(self):
        dpi = max_dpi_within_pixel_budget(612.0, 792.0, 72, DEFAULT_MAX_PIXELS)
        assert dpi == 72

    def test_reduces_for_huge_page_box(self):
        # 50_000 x 50_000 pt at 72dpi would be ~12.5e9 px — must clamp hard
        dpi = max_dpi_within_pixel_budget(50_000.0, 50_000.0, 72, DEFAULT_MAX_PIXELS)
        assert 1 <= dpi < 72
        w, h = _pixel_dimensions(50_000.0, 50_000.0, dpi)
        assert w * h <= DEFAULT_MAX_PIXELS

    def test_monotonic_higher_budget_allows_higher_dpi(self):
        tiny = max_dpi_within_pixel_budget(2000.0, 2000.0, 150, 100_000)
        bigger = max_dpi_within_pixel_budget(2000.0, 2000.0, 150, 5_000_000)
        assert bigger >= tiny

    def test_formula_matches_binary_search_edge(self):
        # At the chosen dpi, product fits; at dpi+1 (if still under requested) may not
        w_pt, h_pt, req, budget = 1000.0, 1000.0, 300, 1_000_000
        dpi = max_dpi_within_pixel_budget(w_pt, h_pt, req, budget)
        pw, ph = _pixel_dimensions(w_pt, h_pt, dpi)
        assert pw * ph <= budget
        if dpi < req:
            pw2, ph2 = _pixel_dimensions(w_pt, h_pt, dpi + 1)
            assert pw2 * ph2 > budget


class TestRasterGeometryScale:
    def test_pt_px_roundtrip(self):
        import numpy as np

        img = np.zeros((200, 100, 3), dtype=np.uint8)
        # 100px wide, 50pt page → 2 px/pt
        g = RasterGeometry(
            image=img,
            requested_dpi=144,
            render_dpi=144,
            pixel_width=100,
            pixel_height=200,
            page_width_pt=50.0,
            page_height_pt=100.0,
        )
        assert g.x_scale == 2.0
        assert g.y_scale == 2.0
        assert g.pt_len_to_px(10.0, "x") == 20.0
        assert g.px_len_to_pt(20.0, "x") == 10.0
        assert math.isclose(g.px_len_to_pt(g.pt_len_to_px(7.5, "y"), "y"), 7.5)
