"""LayoutIntent → LineIntervalPlan → Typesetting consumption chain.

Architecture: ``docs/line-interval-architecture.md``.

Typesetting must break lines only via ``LineIntervalPlan.intervals_at``.
Intent fields that do not change intervals are not deliverables.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from babeldoc.format.pdf.document_il import il_version_1
from babeldoc.format.pdf.document_il.utils.layout_intent import LayoutIntentRole
from babeldoc.format.pdf.document_il.utils.layout_intent import WrapMode
from babeldoc.format.pdf.document_il.utils.wrap_shape import get_active_wrap
from babeldoc.format.pdf.document_il.utils.wrap_shape import resolve_wrap_shape

Box = il_version_1.Box
PdfParagraph = il_version_1.PdfParagraph

# Cap helper signature used by non-wrap path (owned by Typesetting today).
CapFn = Callable[
    [Box, float, float, list[float] | None, int],
    tuple[float, float],
]


class LayoutAttempt(str, Enum):
    """Overflow chain: rebuild plan, do not recurse wrap/drop flags forever."""

    PRIMARY = "primary"
    FULL_MEASURE = "full_measure"


def _left_quote_owns_residual(
    zone_index: Any,
    residual_x1: float,
    *,
    y_bottom: float | None = None,
    y_top: float | None = None,
) -> bool:
    """True when a quote zone's right edge is this residual's left edge.

    OA p91: red bar design ~54–211, body residual starts at ~211. B4b
    carved that pocket on purpose; the Orgasms p.21 box.x snap must not
    undo it. Figure zones do not match — p.21 still snaps.
    """
    if zone_index is None:
        return False
    zones = getattr(zone_index, "zones", None) or []
    for zone in zones:
        if getattr(zone, "kind", None) != "quote":
            continue
        zb = getattr(zone, "box", None)
        if zb is None or zb.x2 is None:
            continue
        if (
            y_bottom is not None
            and y_top is not None
            and zb.y is not None
            and zb.y2 is not None
            and (zb.y2 < y_bottom or zb.y > y_top)
        ):
            continue
        # Residual starts at or just past the quote (padding slack).
        if zb.x2 <= residual_x1 + 2.0 and residual_x1 - zb.x2 <= 40.0:
            return True
    return False


def infer_wrap_mode_from_line_boxes(
    lines: list[tuple[float, float]],
) -> WrapMode:
    """Infer pin side from EN line boxes ``(x, x2)``.

    RIGHT_FIXED: right edge pinned (spread ≤4pt), left steps (≥12pt) — p19.
    LEFT_FIXED: left edge pinned, right steps — p82.
    Ambiguous → NONE (do not force pin).
    """
    if len(lines) < 2:
        return WrapMode.NONE
    xs = [float(x) for x, _ in lines]
    x2s = [float(x2) for _, x2 in lines]
    left_spread = max(xs) - min(xs)
    right_spread = max(x2s) - min(x2s)
    if right_spread <= 4.0 and left_spread >= 12.0:
        return WrapMode.RIGHT_FIXED
    if left_spread <= 4.0 and right_spread >= 12.0:
        return WrapMode.LEFT_FIXED
    return WrapMode.NONE


def infer_wrap_mode_beside_photo(
    design_box: Box,
    photo_boxes: list | None,
) -> WrapMode | None:
    """Pin side from a y-overlapping photo: right of text -> LEFT_FIXED.

    Width-only wrap_shape synth and ambiguous line-box spreads used to
    default to RIGHT_FIXED, which right-aligned OA p33 leftovers into the
    model. None when no photo sits beside the column.
    """
    if design_box is None or not photo_boxes:
        return None
    if design_box.x is None or design_box.x2 is None:
        return None
    text_cx = (float(design_box.x) + float(design_box.x2)) / 2.0
    dy1 = float(design_box.y) if design_box.y is not None else None
    dy2 = float(design_box.y2) if design_box.y2 is not None else None
    for photo in photo_boxes:
        if photo is None or photo.x is None or photo.x2 is None:
            continue
        if (
            dy1 is not None
            and dy2 is not None
            and photo.y is not None
            and photo.y2 is not None
        ):
            if float(photo.y2) < dy1 or float(photo.y) > dy2:
                continue
        photo_cx = (float(photo.x) + float(photo.x2)) / 2.0
        if photo_cx > text_cx + 20.0:
            return WrapMode.LEFT_FIXED
        if photo_cx < text_cx - 20.0:
            return WrapMode.RIGHT_FIXED
    return None


def shape_entry(
    wrap_shape: list[tuple[float, float]],
    line_idx: int,
) -> tuple[float, float]:
    """``(left_offset, width)`` for line_idx; past end reuses last."""
    if not wrap_shape:
        return 0.0, 0.0
    idx = 0 if line_idx < 0 else line_idx
    if idx >= len(wrap_shape):
        return wrap_shape[-1]
    return wrap_shape[idx]


def wrap_interval(
    design_box: Box,
    wrap_shape: list[tuple[float, float]],
    line_idx: int,
    wrap_mode: WrapMode,
    *,
    layout_box: Box | None = None,
) -> tuple[float, float]:
    """Single wrap pocket for one line under LEFT_FIXED or RIGHT_FIXED.

    Always clamps into ``intersect(design_box, layout_box)`` and never lets
    requested width push the free edge past the pin (prevents x→page-edge
    drift when width > available).
    """
    if design_box is None:
        raise TypeError("wrap_interval requires design_box")
    if wrap_mode is WrapMode.NONE:
        raise ValueError("wrap_interval requires LEFT_FIXED or RIGHT_FIXED")

    # Intersection of design + layout (layout may expand; pin still from design)
    lo_x = float(design_box.x)
    lo_x2 = float(design_box.x2)
    if layout_box is not None and layout_box.x is not None:
        lo_x = max(lo_x, float(layout_box.x))
        lo_x2 = min(lo_x2, float(layout_box.x2))
    if lo_x2 <= lo_x:
        lo_x, lo_x2 = float(design_box.x), float(design_box.x2)

    if not wrap_shape:
        return lo_x, lo_x2

    _off, width = shape_entry(wrap_shape, line_idx)
    width = float(width)
    if width < 8.0:
        width = 8.0
    avail = lo_x2 - lo_x
    if width > avail:
        width = avail

    if wrap_mode is WrapMode.RIGHT_FIXED:
        x2 = lo_x2
        x1 = x2 - width
    else:  # LEFT_FIXED
        x1 = lo_x
        x2 = x1 + width

    # Final clamp (numerical safety)
    x1 = max(lo_x, min(x1, lo_x2))
    x2 = max(x1, min(x2, lo_x2))
    return x1, x2


def typeset_wrap_line_legacy(
    design_box: Box,
    wrap_shape: list[tuple[float, float]],
    line_idx: int,
) -> tuple[float, float]:
    """Backward-compatible right-pin (pre-clamp behavior for tests).

    Prefer ``wrap_interval(..., WrapMode.RIGHT_FIXED)`` for new code.
    Legacy path did not clamp width to design; only pin math.
    """
    if design_box is None:
        raise TypeError("typeset_wrap_line requires a design_box")
    if not wrap_shape:
        return float(design_box.x), float(design_box.x2)
    _off, width = shape_entry(wrap_shape, line_idx)
    width = float(width)
    if width < 8.0:
        width = 8.0
    right = float(design_box.x2)
    return right - width, right


@dataclass(slots=True)
class LineIntervalPlan:
    """Resolved line geometry for one paragraph + one LayoutAttempt."""

    attempt: LayoutAttempt
    design_box: Box
    layout_box: Box
    wrap_mode: WrapMode
    wrap_shape: list[tuple[float, float]] | None
    wrap_active: bool
    zone_index: Any
    reference_widths: list[float] | None
    alignment: str | None
    cap_available: CapFn | None

    def intervals_at(
        self,
        y_bottom: float,
        y_top: float,
        *,
        line_idx: int,
    ) -> list[tuple[float, float]]:
        """Canonical API: pockets ``[(x1, x2), ...]`` for this y-band / line."""
        box = self.layout_box
        if box is None or box.x is None or box.x2 is None:
            return [(0.0, 0.0)]

        if self.attempt is LayoutAttempt.FULL_MEASURE:
            return [(float(box.x), float(box.x2))]

        # PRIMARY: wrap pin when active
        if self.wrap_active and self.wrap_shape and self.wrap_mode is not WrapMode.NONE:
            mode = self.wrap_mode
            pocket = wrap_interval(
                self.design_box,
                self.wrap_shape,
                line_idx,
                mode,
                layout_box=box,
            )
            return [pocket]

        # PRIMARY: zone residual + optional reference cap
        intervals = self._zone_intervals(y_bottom, y_top, box)
        return self._cap_leftmost(
            box, intervals, line_idx, y_bottom=y_bottom, y_top=y_top
        )

    def _zone_intervals(
        self,
        y_bottom: float,
        y_top: float,
        box: Box,
    ) -> list[tuple[float, float]]:
        zone_index = self.zone_index
        if zone_index and getattr(zone_index, "zones", None) and y_top > y_bottom:
            intervals = zone_index.get_intervals_at(y_bottom, y_top, box.x, box.x2)
            if intervals:
                return list(intervals)
        return [(float(box.x), float(box.x2))]

    def _cap_leftmost(
        self,
        box: Box,
        intervals: list[tuple[float, float]],
        line_idx: int,
        *,
        y_bottom: float | None = None,
        y_top: float | None = None,
    ) -> list[tuple[float, float]]:
        if not intervals:
            return [(float(box.x), float(box.x2))]
        if not self.reference_widths or self.cap_available is None:
            return intervals
        ix1, ix2 = intervals[0]
        # A left quote already carved this residual (OA p91). The p.21
        # snap-back uses box.x (full-measure leftover ~102) and would
        # paint CJK back over the red bar. Pretend the paragraph starts
        # at the residual so cap keeps the wrap pocket.
        cap_box = box
        if _left_quote_owns_residual(
            self.zone_index, ix1, y_bottom=y_bottom, y_top=y_top
        ):
            cap_box = Box(x=ix1, y=box.y, x2=box.x2, y2=box.y2)
        cx1, cx2 = self.cap_available(
            cap_box,
            ix1,
            ix2,
            self.reference_widths,
            line_idx,
        )
        if (cx1, cx2) == (ix1, ix2):
            return intervals
        return [(cx1, cx2), *intervals[1:]]


def effective_wrap_mode(
    paragraph: PdfParagraph | None,
    *,
    shape_present: bool,
) -> WrapMode:
    """Mode from intent, with legacy default RIGHT_FIXED when shape but no mode."""
    intent = getattr(paragraph, "layout_intent", None) if paragraph else None
    mode = getattr(intent, "wrap_mode", None) if intent is not None else None
    if mode is None or mode is WrapMode.NONE:
        # Pre-C1 intents / synth shapes: historical consumer was right-pin only.
        if shape_present:
            return WrapMode.RIGHT_FIXED
        return WrapMode.NONE
    return mode


def resolve_line_interval_plan(
    paragraph: PdfParagraph | None,
    layout_box: Box,
    *,
    attempt: LayoutAttempt = LayoutAttempt.PRIMARY,
    wrap_enabled: bool = True,
    zone_index: Any = None,
    reference_widths: list[float] | None = None,
    alignment: str | None = None,
    cap_available: CapFn | None = None,
) -> LineIntervalPlan:
    """Build plan for one paragraph attempt.

    FULL_MEASURE ignores wrap and figure carving (full layout_box width).
    PRIMARY uses wrap pin when active, else zones + reference cap.
    """
    active = get_active_wrap(
        paragraph,
        enabled=wrap_enabled and attempt is LayoutAttempt.PRIMARY,
        layout_box=layout_box,
    )
    shape = resolve_wrap_shape(paragraph) if paragraph is not None else None
    if active is not None:
        design, shape = active
        wrap_active = True
    else:
        design = layout_box
        intent = getattr(paragraph, "layout_intent", None) if paragraph else None
        if intent is not None and getattr(intent, "design_box", None) is not None:
            design = intent.design_box
        wrap_active = False
        shape = shape if wrap_enabled and attempt is LayoutAttempt.PRIMARY else None

    mode = effective_wrap_mode(paragraph, shape_present=bool(shape) and wrap_active)
    if not wrap_active:
        mode = WrapMode.NONE

    return LineIntervalPlan(
        attempt=attempt,
        design_box=design,
        layout_box=layout_box,
        wrap_mode=mode,
        wrap_shape=list(shape) if shape else None,
        wrap_active=wrap_active and mode is not WrapMode.NONE,
        zone_index=zone_index if attempt is LayoutAttempt.PRIMARY else None,
        reference_widths=(
            reference_widths if attempt is LayoutAttempt.PRIMARY else None
        ),
        alignment=alignment,
        cap_available=cap_available,
    )


def attempt_chain_for_paragraph(
    paragraph: PdfParagraph | None,
    *,
    is_cjk: bool,
) -> list[LayoutAttempt]:
    """Overflow attempts: PRIMARY then FULL_MEASURE for CJK float-wrap body."""
    if not is_cjk:
        return [LayoutAttempt.PRIMARY]
    shape = resolve_wrap_shape(paragraph) if paragraph is not None else None
    intent = getattr(paragraph, "layout_intent", None) if paragraph else None
    role = getattr(intent, "role", None) if intent is not None else None
    from babeldoc.format.pdf.document_il.utils.layout_intent import LayoutIntentRole

    # Side callout / pull-quote must stay in their design column. FULL_MEASURE
    # widens a 157pt left gutter to ~440pt (OA p91 red bar → overlaps body).
    if role in (LayoutIntentRole.CALLOUT, LayoutIntentRole.PULL_QUOTE):
        return [LayoutAttempt.PRIMARY]
    if shape or role is LayoutIntentRole.WRAP_COLUMN:
        return [LayoutAttempt.PRIMARY, LayoutAttempt.FULL_MEASURE]
    # Thin residual bodies also get FULL_MEASURE as second chance (CJK)
    return [LayoutAttempt.PRIMARY, LayoutAttempt.FULL_MEASURE]


def allows_full_measure_escalation(
    paragraph: PdfParagraph | None,
    *,
    is_cjk: bool,
) -> bool:
    """True when CJK overflow may drop figure zones / widen to body measure.

    CALLOUT / PULL_QUOTE must stay in their design column (OA p91 red bar,
    OA p59 wrap misread as quote). Inner typesetting retries used to ignore
    ``attempt_chain_for_paragraph`` and FULL_MEASURE into the photo.
    WRAP_COLUMN still escalates via wrap-budget, not this gate.
    """
    return LayoutAttempt.FULL_MEASURE in attempt_chain_for_paragraph(
        paragraph, is_cjk=is_cjk
    )


def flags_to_attempt(
    *,
    wrap_enabled: bool,
    drop_figure_zones: bool,
) -> LayoutAttempt:
    """Map legacy kwargs to attempt (migration bridge)."""
    if drop_figure_zones and not wrap_enabled:
        return LayoutAttempt.FULL_MEASURE
    return LayoutAttempt.PRIMARY


def full_measure_layout_box(
    paragraph: PdfParagraph | None,
    layout_box: Box | None,
    page: Any = None,
    *,
    min_body_width: float = 400.0,
) -> Box | None:
    """Widen/snaps ``paragraph.box`` for FULL_MEASURE so intervals are true body measure.

    C3 (docs/line-interval-architecture.md): FULL_MEASURE must change
    ``layout_box`` width, not only drop figure zones. OA p82.65 still showed
    x≈5 w≈285 walls because the layout box stayed the residual strip.
    """
    if layout_box is None or layout_box.x is None or layout_box.x2 is None:
        return None
    intent = getattr(paragraph, "layout_intent", None) if paragraph else None
    design = getattr(intent, "design_box", None) if intent is not None else None
    if design is None or design.x is None:
        design = layout_box

    page_left = 0.0
    page_right = 612.0
    if page is not None:
        crop = getattr(getattr(page, "cropbox", None), "box", None)
        if crop is not None and crop.x is not None and crop.x2 is not None:
            page_left = float(crop.x)
            page_right = float(crop.x2)

    # Left: prefer design.x; if design was residual-snapped near page edge, use
    # a normal body margin (~56–102pt band).
    dx = float(design.x)
    if dx < page_left + 30.0:
        left = page_left + 56.0
    else:
        left = dx

    design_w = max(0.0, float(design.x2) - float(design.x))
    page_w = max(1.0, page_right - page_left)
    role = getattr(intent, "role", None) if intent is not None else None
    wrap_mode = getattr(intent, "wrap_mode", None) if intent is not None else None
    # Figure-wrap columns must not grow into the photo.
    # RIGHT_FIXED (p19 photo on the left) already stays at design_w.
    # LEFT_FIXED figure wrap (p33/p59 photo on the right, layout_box is
    # the wrap column itself or the wrap_shape tapers) also stays.
    # LEFT_FIXED residual strips (p82.65 layout x~5 vs design x~102)
    # still need the body-measure widen.
    stay_in_design = False
    if role is LayoutIntentRole.WRAP_COLUMN:
        if wrap_mode is WrapMode.RIGHT_FIXED:
            stay_in_design = True
        elif wrap_mode is WrapMode.LEFT_FIXED:
            same_column = (
                abs(float(layout_box.x) - float(design.x)) < 12.0
                and abs(float(layout_box.x2) - float(design.x2)) < 12.0
            )
            shape = getattr(intent, "wrap_shape", None) or []
            widths = [float(w) for _off, w in shape]
            from babeldoc.format.pdf.document_il.utils.figure_wrap import (
                is_figure_wrap_taper,
            )

            stay_in_design = same_column or is_figure_wrap_taper(widths)
    if stay_in_design:
        target_w = design_w
    else:
        target_w = max(design_w, min_body_width, min(460.0, page_w * 0.72))
    right = min(page_right - 16.0, left + target_w)
    if right <= left + 50.0:
        right = min(page_right - 16.0, left + min_body_width)

    return Box(
        x=left,
        y=float(layout_box.y) if layout_box.y is not None else 0.0,
        x2=right,
        y2=float(layout_box.y2) if layout_box.y2 is not None else 0.0,
    )


def layout_box_is_thin_vs_full_measure(
    layout_box: Box | None,
    full_box: Box | None,
    *,
    ratio: float = 0.65,
) -> bool:
    """True when current box is much narrower than FULL_MEASURE target."""
    if layout_box is None or full_box is None:
        return False
    lw = float(layout_box.x2) - float(layout_box.x)
    fw = float(full_box.x2) - float(full_box.x)
    if fw <= 1.0:
        return False
    return lw < fw * ratio
