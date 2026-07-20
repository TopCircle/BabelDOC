"""Page rasterization with explicit pixel geometry.

This module owns page-size-to-raster-size calculations and the RGB raster
metadata shared by layout / scanned-file consumers.  It intentionally does
not perform coordinate-origin changes, y-axis flips, clipping, or padding.

Which entry point to use
------------------------
- ``with_pixel_budget`` — cap **total pixels** (default 12e6). Use for scan
  detection and RPC paths that can OOM on absurd page boxes.
- ``with_target_long_edge`` — only downscale when the default long edge would
  exceed ``2 * target_px``. Use for local YOLO-style layout (fixed imgsz).

Prefer these over raw ``page.get_pixmap(dpi=…)`` for any layout pipeline.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Literal

import numpy as np
import pymupdf

logger = logging.getLogger(__name__)

DEFAULT_MAX_PIXELS = 12_000_000
Axis = Literal["x", "y"]


@dataclass(frozen=True)
class RasterGeometry:
    """RGB raster and its scale relative to the rendered PDF page view.

    The page origin is deliberately not represented here.  Callers keep
    their existing origin, y-axis, clipping, and padding behavior.  The
    normal page path is expected to have a zero-origin rect after
    ``fix_media_box``; a non-zero origin is logged but does not stop the
    render.
    """

    image: np.ndarray
    requested_dpi: int
    render_dpi: int
    pixel_width: int
    pixel_height: int
    page_width_pt: float
    page_height_pt: float

    @property
    def x_scale(self) -> float:
        """Return rendered pixels per PDF point on the x axis."""

        return self.pixel_width / self.page_width_pt

    @property
    def y_scale(self) -> float:
        """Return rendered pixels per PDF point on the y axis."""

        return self.pixel_height / self.page_height_pt

    def pt_len_to_px(self, length: float, axis: Axis = "x") -> float:
        """Convert a point-space length to raster pixels by axis."""

        return length * self._scale(axis)

    def px_len_to_pt(self, length: float, axis: Axis = "x") -> float:
        """Convert a raster-pixel length to PDF points by axis."""

        return length / self._scale(axis)

    def _scale(self, axis: Axis) -> float:
        if axis == "x":
            return self.x_scale
        if axis == "y":
            return self.y_scale
        raise ValueError(f"unsupported raster axis: {axis!r}")

    def render_at_dpi(
        self,
        page: pymupdf.Page,
        *,
        normalize_rotation: bool,
    ) -> np.ndarray:
        """Render the page again at this geometry's DPI.

        Used by DetectScannedFile so before/after SSIM shares the same DPI.
        """

        image, _rect = _render_rgb(page, self.render_dpi, normalize_rotation)
        return image


def _positive_int(value: int, name: str) -> int:
    value = int(value)
    if value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _pixel_dimensions(
    page_width_pt: float, page_height_pt: float, dpi: int
) -> tuple[int, int]:
    """Return contract pixel dimensions using independent edge ceils."""

    return (
        max(1, math.ceil(page_width_pt * dpi / 72)),
        max(1, math.ceil(page_height_pt * dpi / 72)),
    )


def max_dpi_within_pixel_budget(
    page_width_pt: float,
    page_height_pt: float,
    requested_dpi: int,
    max_pixels: int,
) -> int:
    """Highest integer DPI in ``[1, requested_dpi]`` with product of ceil dims ≤ budget.

    Pure math (no render). Callers that only need a safe DPI (e.g. legacy
    ``get_no_rotation_img``) can use this without building a RasterGeometry.
    """

    requested_dpi = _positive_int(requested_dpi, "requested_dpi")
    max_pixels = _positive_int(max_pixels, "max_pixels")
    if page_width_pt <= 0 or page_height_pt <= 0:
        return 1

    lo, hi = 1, requested_dpi
    best = 1
    while lo <= hi:
        mid = (lo + hi) // 2
        w, h = _pixel_dimensions(page_width_pt, page_height_pt, mid)
        if w * h <= max_pixels:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return best


@contextmanager
def _page_view_rect(
    page: pymupdf.Page, *, normalize_rotation: bool
) -> Iterator[pymupdf.Rect]:
    """Yield the render-view rect, optionally with rotation forced to 0."""

    original_rotation = page.rotation
    try:
        if normalize_rotation:
            page.set_rotation(0)
        rect = page.rect
        if rect.x0 != 0 or rect.y0 != 0:
            logger.warning(
                "Raster page rect has non-zero origin: (%.3f, %.3f)",
                rect.x0,
                rect.y0,
            )
        yield rect
    finally:
        if normalize_rotation:
            page.set_rotation(original_rotation)


def _render_rgb(
    page: pymupdf.Page,
    dpi: int,
    normalize_rotation: bool,
) -> tuple[np.ndarray, pymupdf.Rect]:
    """Render one page as RGB and restore a temporarily normalized rotation."""

    with _page_view_rect(page, normalize_rotation=normalize_rotation) as rect:
        pix = page.get_pixmap(dpi=dpi)
        channels = getattr(pix, "n", 3)
        if channels != 3:
            raise ValueError(f"expected an RGB pixmap, got {channels} channels")
        samples = np.frombuffer(pix.samples, dtype=np.uint8)
        expected_size = pix.width * pix.height * 3
        if samples.size != expected_size:
            raise ValueError(
                "RGB pixmap sample size does not match its dimensions: "
                f"{samples.size} != {expected_size}"
            )
        image = samples.reshape(pix.height, pix.width, 3)
        return image, rect


def _make_geometry(
    page: pymupdf.Page,
    requested_dpi: int,
    render_dpi: int,
    *,
    normalize_rotation: bool,
) -> RasterGeometry:
    image, rect = _render_rgb(page, render_dpi, normalize_rotation)
    return RasterGeometry(
        image=image,
        requested_dpi=requested_dpi,
        render_dpi=render_dpi,
        pixel_width=image.shape[1],
        pixel_height=image.shape[0],
        page_width_pt=float(rect.width),
        page_height_pt=float(rect.height),
    )


def with_pixel_budget(
    page: pymupdf.Page,
    requested_dpi: int,
    max_pixels: int = DEFAULT_MAX_PIXELS,
    *,
    normalize_rotation: bool,
) -> RasterGeometry:
    """Render a page at the highest DPI that meets the pixel budget.

    DPI is chosen by binary search on the ceil dimension formula (no render),
    then verified with at most one render.  If MuPDF's pixmap is still over
    budget (rare rounding), a second binary search over actual renders uses
    ``O(log requested_dpi)`` attempts instead of stepping DPI by 1.
    """

    requested_dpi = _positive_int(requested_dpi, "requested_dpi")
    max_pixels = _positive_int(max_pixels, "max_pixels")

    with _page_view_rect(page, normalize_rotation=normalize_rotation) as rect:
        width_pt = float(rect.width)
        height_pt = float(rect.height)

    render_dpi = max_dpi_within_pixel_budget(
        width_pt, height_pt, requested_dpi, max_pixels
    )
    geometry = _make_geometry(
        page,
        requested_dpi,
        render_dpi,
        normalize_rotation=normalize_rotation,
    )
    if geometry.pixel_width * geometry.pixel_height <= max_pixels:
        return geometry
    if render_dpi == 1:
        return geometry

    # MuPDF produced more pixels than the ceil estimate — binary search actuals.
    lo, hi = 1, render_dpi - 1
    best = geometry  # keep last over-budget render only if even dpi=1 overflows
    while lo <= hi:
        mid = (lo + hi) // 2
        candidate = _make_geometry(
            page,
            requested_dpi,
            mid,
            normalize_rotation=normalize_rotation,
        )
        if candidate.pixel_width * candidate.pixel_height <= max_pixels:
            best = candidate
            lo = mid + 1
        else:
            hi = mid - 1
            if mid == 1:
                best = candidate
    return best


def with_target_long_edge(
    page: pymupdf.Page,
    default_dpi: int,
    target_px: int,
    *,
    normalize_rotation: bool,
) -> RasterGeometry:
    """Render at ``default_dpi`` unless the long edge would exceed ``2 * target_px``."""

    default_dpi = _positive_int(default_dpi, "default_dpi")
    target_px = _positive_int(target_px, "target_px")

    with _page_view_rect(page, normalize_rotation=normalize_rotation) as rect:
        long_edge_pt = max(float(rect.width), float(rect.height))

    default_long_edge_px = long_edge_pt * default_dpi / 72
    if default_long_edge_px > 2 * target_px:
        render_dpi = max(1, math.floor(target_px * 72 / long_edge_pt))
    else:
        render_dpi = default_dpi
    return _make_geometry(
        page,
        default_dpi,
        render_dpi,
        normalize_rotation=normalize_rotation,
    )
