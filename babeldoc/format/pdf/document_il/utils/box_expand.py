"""Shared box-expansion policy for typesetting.

One place for:
  * narrow figure-adjacent columns (prefer expand **down** when right blocked)
  * short headings (expand sooner; may deepen when right is blocked)
  * OCR dual-layer (expand down first into the white-fill band)

``Typesetting`` scale search and ``_pre_expand_narrow_box`` must call these
helpers so the 150pt / right-blocked / down-first policy cannot drift.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from babeldoc.format.pdf.document_il.il_version_1 import Box

# Figure-adjacent body columns (OA p7 left strip ~105pt on letter).
NARROW_COLUMN_MAX_WIDTH = 150.0

# Content-width / box-width thresholds before we attempt expansion.
RATIO_SHORT_HEADING = 1.15
RATIO_NARROW_COLUMN = 1.2
RATIO_BODY = 1.5

Axis = Literal["right", "down"]
GetMaxRight = Callable[[Box], float]
GetMaxBottom = Callable[[Box], float]


def box_width(box: Box | None) -> float:
    if box is None or box.x is None or box.x2 is None:
        return 0.0
    return float(box.x2 - box.x)


def is_narrow_column(box: Box | None) -> bool:
    w = box_width(box)
    return 0 < w < NARROW_COLUMN_MAX_WIDTH


def is_short_heading_text(text: str | None, layout_label: str | None) -> bool:
    t = (text or "").strip()
    label = (layout_label or "").lower()
    if len(t) <= 40:
        return True
    return label in ("title", "section_header") and len(t) <= 48


def content_expand_ratio_need(
    text: str | None,
    layout_label: str | None,
    box: Box | None,
) -> float:
    """Minimum content_w / box_w before pre-expand attempts."""
    if is_short_heading_text(text, layout_label):
        return RATIO_SHORT_HEADING
    if is_narrow_column(box):
        return RATIO_NARROW_COLUMN
    return RATIO_BODY


def is_right_blocked(box: Box, get_max_right: GetMaxRight, *, margin: float = 5.0) -> bool:
    """True when no meaningful free width remains to the right of *box*."""
    if box is None or box.x2 is None:
        return True
    try:
        max_x = get_max_right(box) - margin
    except Exception:
        return True
    return max_x <= box.x2 + 1


def prefer_expand_down(
    box: Box,
    *,
    ocr_mode: bool,
    get_max_right: GetMaxRight,
) -> bool:
    """Whether the first expansion axis should be down rather than right.

    True for OCR dual-layer (use white-fill height) and for narrow columns
    whose right side is blocked by a figure/exclusion zone.
    """
    if ocr_mode:
        return True
    return is_narrow_column(box) and is_right_blocked(box, get_max_right)


def expand_axis_order(*, prefer_down: bool) -> tuple[Axis, Axis]:
    """Ordered expansion attempts (at most two axes)."""
    if prefer_down:
        return ("down", "right")
    return ("right", "down")


def try_expand_right(
    box: Box,
    get_max_right: GetMaxRight,
    *,
    margin: float = 5.0,
) -> Box | None:
    """Return a wider box, or None if right is blocked / error."""
    if box is None or box.x is None or box.x2 is None:
        return None
    try:
        max_x = get_max_right(box) - margin
    except Exception:
        return None
    if max_x <= box.x2 + 1:
        return None
    return Box(x=box.x, y=box.y, x2=max_x, y2=box.y2)


def try_expand_down(
    box: Box,
    get_max_bottom: GetMaxBottom,
    *,
    margin: float = 2.0,
) -> Box | None:
    """Return a taller box (lower y), or None if bottom is blocked / error.

    PDF y grows upward: free space below means a smaller ``y``.
    """
    if box is None or box.y is None or box.y2 is None:
        return None
    try:
        min_y = get_max_bottom(box) + margin
    except Exception:
        return None
    if min_y >= box.y - 1:
        return None
    return Box(x=box.x, y=min_y, x2=box.x2, y2=box.y2)


def try_expand_axis(
    box: Box,
    axis: Axis,
    *,
    get_max_right: GetMaxRight,
    get_max_bottom: GetMaxBottom,
) -> Box | None:
    if axis == "right":
        return try_expand_right(box, get_max_right)
    return try_expand_down(box, get_max_bottom)


def try_pre_expand_for_content(
    box: Box,
    *,
    content_w: float,
    text: str | None,
    layout_label: str | None,
    get_max_right: GetMaxRight,
    get_max_bottom: GetMaxBottom,
) -> Box | None:
    """Pre-scale expand when content is clearly wider than the original box.

    Order: right first; if blocked and (narrow column or short heading), down.
    Returns the expanded box, or None when no change is possible.
    """
    if box is None:
        return None
    box_w = box_width(box)
    if box_w <= 0 or content_w <= 0:
        return None
    ratio_need = content_expand_ratio_need(text, layout_label, box)
    if content_w < box_w * ratio_need:
        return None

    right = try_expand_right(box, get_max_right)
    if right is not None:
        return right

    # Right blocked: deepen only for columns/headings that need it.
    if is_narrow_column(box) or is_short_heading_text(text, layout_label):
        return try_expand_down(box, get_max_bottom)
    return None
