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
# Ultra-narrow callout strip (OA p8 ~80pt) — expand sooner under expand mode.
ULTRA_NARROW_COLUMN_MAX_WIDTH = 100.0
# Design callout column after line-merge (OA TAKING CHARGE ~180–220pt).
CALLOUT_COLUMN_MAX_WIDTH = 230.0
# Left-gutter red bar (OA p91 ~157pt). Wider left-edge strips (~200pt body)
# must still be allowed to right-expand.
LEFT_GUTTER_BAR_MAX_WIDTH = 180.0

# Content-width / box-width thresholds before we attempt expansion.
RATIO_SHORT_HEADING = 1.15
RATIO_NARROW_COLUMN = 1.2
RATIO_ULTRA_NARROW = 1.05  # PR-D: almost any CJK overflow triggers expand
RATIO_BODY = 1.5

Axis = Literal["right", "down", "left"]
GetMaxRight = Callable[[Box], float]
GetMaxBottom = Callable[[Box], float]
GetMaxLeft = Callable[[Box], float]


def box_width(box: Box | None) -> float:
    if box is None or box.x is None or box.x2 is None:
        return 0.0
    return float(box.x2 - box.x)


def is_narrow_column(box: Box | None) -> bool:
    w = box_width(box)
    return 0 < w < NARROW_COLUMN_MAX_WIDTH


def is_ultra_narrow_column(box: Box | None) -> bool:
    """Tighter than :func:`is_narrow_column` (OA p8 callout ~80pt)."""
    w = box_width(box)
    return 0 < w < ULTRA_NARROW_COLUMN_MAX_WIDTH


def is_callout_column(box: Box | None) -> bool:
    """Merged inverted-triangle / side callout column (wider tip, still narrow)."""
    w = box_width(box)
    return 0 < w < CALLOUT_COLUMN_MAX_WIDTH


def is_left_gutter_bar(box: Box | None) -> bool:
    """OA p91 left-gutter red bar (x≈54, width ≲180pt)."""
    if box is None or box.x is None:
        return False
    return float(box.x) < 80.0 and 0.0 < box_width(box) < LEFT_GUTTER_BAR_MAX_WIDTH


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
    if is_ultra_narrow_column(box):
        return RATIO_ULTRA_NARROW
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

    True for OCR dual-layer (use white-fill height), ultra-narrow callouts,
    and for narrow columns whose right side is blocked by a figure/exclusion.
    """
    if ocr_mode:
        return True
    # Ultra-narrow right strips almost always sit against a figure — prefer
    # down even if a few points remain to the right (PR-D).
    if is_ultra_narrow_column(box):
        return True
    # Left-gutter callout: wrap-column ink looks free on the right (OA p91).
    if is_left_gutter_bar(box):
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


# Hard cap: callouts sit on figures; unlimited left expand crosses the page
# into the body column (OA p19 dual 0.6.4.48 regression).
_MAX_LEFT_EXPAND_PT = 100.0


def try_expand_left(
    box: Box,
    get_max_left: GetMaxLeft,
    *,
    margin: float = 5.0,
    need_width: float | None = None,
    max_expand: float = _MAX_LEFT_EXPAND_PT,
) -> Box | None:
    """Extend box left for CJK reflow — only as far as content needs, capped.

    Unlimited expand to ``get_max_left`` (often the page margin) pulls right-side
    callouts across photos into the body column and wrecks dual layout.
    """
    if box is None or box.x is None or box.x2 is None:
        return None
    cur_w = box_width(box)
    if cur_w <= 0:
        return None
    # Only expand when content is wider than the box (or need_width given).
    if need_width is None or need_width <= cur_w + 1.0:
        return None
    try:
        min_x_free = get_max_left(box) + margin
    except Exception:
        return None
    desired_x = float(box.x2) - float(need_width)
    min_x_cap = float(box.x) - float(max_expand)
    # Rightmost of the lower bounds = least aggressive left edge we may use.
    new_x = max(min_x_free, min_x_cap, desired_x)
    if new_x >= float(box.x) - 1.0:
        return None
    return Box(x=new_x, y=box.y, x2=box.x2, y2=box.y2)


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
    get_max_left: GetMaxLeft | None = None,
) -> Box | None:
    """Pre-scale expand when content is clearly wider than the original box.

    Order: right first; if blocked and (narrow column or short heading), down.
    Callout columns: left (into body) then down then right.
    Returns the expanded box, or None when no change is possible.
    """
    if box is None:
        return None
    box_w = box_width(box)
    if box_w <= 0 or content_w <= 0:
        return None
    ratio_need = content_expand_ratio_need(text, layout_label, box)
    # Right-side design callouts (tip / merged triangle): left then down.
    # Do NOT treat every width<230 box as a callout — short body/subheads would
    # force full-page left expand and destroy dual layout.
    right_blocked = is_right_blocked(box, get_max_right)
    left_gutter_bar = is_left_gutter_bar(box)
    force_callout = is_ultra_narrow_column(box) or (
        is_callout_column(box) and right_blocked
    )
    # Even callouts: no expand when content already fits the box.
    if content_w <= box_w + 1.0:
        return None
    if not force_callout and not left_gutter_bar and content_w < box_w * ratio_need:
        return None

    # OA p91 left-gutter red bar (x≈54): body wrap ink at x≈246 looks like free
    # right space, so right_blocked is false and the general path would widen
    # the bar into the wrap pocket while exclusion still tracks design_box.
    # Deepen only — never right-expand into the wrap column.
    if left_gutter_bar:
        return try_expand_down(box, get_max_bottom)

    # Ultra-narrow / right-blocked callout column: modest left, then right, down.
    if force_callout:
        left = (
            try_expand_left(box, get_max_left, need_width=content_w)
            if get_max_left is not None
            else None
        )
        work = left if left is not None else box
        right = try_expand_right(work, get_max_right)
        if right is not None:
            return right
        down = try_expand_down(work, get_max_bottom)
        if down is not None:
            return down
        return left  # may be None

    right = try_expand_right(box, get_max_right)
    if right is not None:
        return right

    # Right blocked: deepen only for columns/headings that need it.
    if is_narrow_column(box) or is_short_heading_text(text, layout_label):
        return try_expand_down(box, get_max_bottom)
    return None
