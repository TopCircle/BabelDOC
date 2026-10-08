"""Choose a placement paradigm from role and source line geometry.

The mark is a label. It does not move glyphs. Confirmed tapers stay on
the paragraph's existing pin; this module does not call
``is_figure_wrap_taper``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from babeldoc.format.pdf.document_il.utils.layout_intent import LayoutIntentRole
from babeldoc.format.pdf.document_il.utils.layout_intent import WrapMode

_FULL_WIDTH_RATIO = 0.60
_MIN_TAPER_LINES = 4
_MAX_PINNED_RANGE = 18.0
_MIN_LEFT_RANGE = 24.0
# Left-pin free edge. Not the 24pt bar used when the right edge is pinned.
_MIN_RIGHT_FREE_RANGE = 18.0
_STABLE_LEFT_RANGE = 8.0
_EDGE_BUCKET_PT = 6.0
_MAX_STEP_BACK = 6.0
_MIN_MONOTONE = 0.70

_KEEP_ROLES = frozenset(
    {
        LayoutIntentRole.CHROME,
        LayoutIntentRole.TITLE,
        LayoutIntentRole.PULL_QUOTE,
        LayoutIntentRole.CALLOUT,
        LayoutIntentRole.LIST,
        LayoutIntentRole.SECTION_HEADER,
        LayoutIntentRole.FIGURE_CAPTION,
        LayoutIntentRole.DROPCAP,
        LayoutIntentRole.FORMULA,
    }
)
_PINNED_MODES = frozenset({WrapMode.LEFT_FIXED, WrapMode.RIGHT_FIXED})
_RECT_CONFIDENCE = {
    "shape_not_taper": 0.85,
    "taper_too_short": 0.8,
    "stable_column": 0.9,
    "not_taper": 0.8,
}


class PlacementParadigm(str, Enum):
    """How a translated paragraph should sit in its source region."""

    RECT_REFLOW = "rect_reflow"
    SHAPED_POCKET = "shaped_pocket"
    KEEP_CURRENT = "keep_current"


@dataclass(slots=True)
class ParadigmMark:
    """Classifier output. ``reason`` is a stable string for eval logs."""

    paradigm: PlacementParadigm
    confidence: float
    reason: str


@dataclass(slots=True)
class _LineFeatures:
    full_count: int
    left_range: float
    right_range: float
    distinct_lefts: int
    distinct_rights: int
    left_monotone: float
    right_monotone: float


def select_paradigm(
    role: LayoutIntentRole,
    wrap_mode: WrapMode | None,
    line_boxes: list[tuple[float, float, float]],
) -> ParadigmMark:
    """Label one paragraph.

    Args:
        role: Existing layout role. Kept roles are never reshaped.
        wrap_mode: Current pin, or ``None`` when the paragraph has none.
        line_boxes: Source lines as ``(x0, x1, y0)``. ``y0`` grows upward.

    Returns:
        The paradigm mark. Low confidence is only the empty-line case.
    """
    if role in _KEEP_ROLES:
        return ParadigmMark(PlacementParadigm.KEEP_CURRENT, 0.9, "keep_role")
    if not line_boxes:
        return ParadigmMark(PlacementParadigm.RECT_REFLOW, 0.4, "no_lines")
    return _mark_from_geometry(wrap_mode, line_boxes)


def _mark_from_geometry(
    wrap_mode: WrapMode | None,
    line_boxes: list[tuple[float, float, float]],
) -> ParadigmMark:
    features = _line_features(line_boxes)
    if _is_taper(features):
        return ParadigmMark(PlacementParadigm.SHAPED_POCKET, 0.9, "taper")
    reason = _rect_reason(wrap_mode, features)
    return ParadigmMark(
        PlacementParadigm.RECT_REFLOW,
        _RECT_CONFIDENCE[reason],
        reason,
    )


def _rect_reason(wrap_mode: WrapMode | None, features: _LineFeatures) -> str:
    """Pinned modes that failed the taper test stay rectangles.

    That check is ahead of ``stable_column`` and ``taper_too_short`` so a
    flat column already marked ``RIGHT_FIXED`` is not treated as a taper
    that was merely too short.
    """
    if wrap_mode in _PINNED_MODES:
        return "shape_not_taper"
    if _is_too_short(features):
        return "taper_too_short"
    if features.full_count and features.left_range <= _STABLE_LEFT_RANGE:
        return "stable_column"
    return "not_taper"


def _is_taper(features: _LineFeatures) -> bool:
    return _is_right_pin_taper(features) or _is_left_pin_taper(features)


def _is_right_pin_taper(features: _LineFeatures) -> bool:
    """Photo on the left: right edge pinned, left edge steps in."""
    return (
        features.full_count >= _MIN_TAPER_LINES
        and features.right_range <= _MAX_PINNED_RANGE
        and features.left_monotone >= _MIN_MONOTONE
        and features.left_range >= _MIN_LEFT_RANGE
        and features.distinct_lefts >= _MIN_TAPER_LINES
    )


def _is_left_pin_taper(features: _LineFeatures) -> bool:
    """Photo on the right: left edge pinned, right edge steps."""
    return (
        features.full_count >= _MIN_TAPER_LINES
        and features.left_range <= _MAX_PINNED_RANGE
        and features.right_monotone >= _MIN_MONOTONE
        and features.right_range >= _MIN_RIGHT_FREE_RANGE
        and features.distinct_rights >= _MIN_TAPER_LINES
    )


def _is_too_short(features: _LineFeatures) -> bool:
    if not 0 < features.full_count < _MIN_TAPER_LINES:
        return False
    right_pin = (
        features.right_range <= _MAX_PINNED_RANGE
        and features.left_monotone >= _MIN_MONOTONE
        and features.left_range >= _MIN_LEFT_RANGE
    )
    left_pin = (
        features.left_range <= _MAX_PINNED_RANGE
        and features.right_monotone >= _MIN_MONOTONE
        and features.right_range >= _MIN_RIGHT_FREE_RANGE
    )
    return right_pin or left_pin


def _line_features(
    line_boxes: list[tuple[float, float, float]],
) -> _LineFeatures:
    full = _full_lines_top_down(line_boxes)
    lefts = [box[0] for box in full]
    rights = [box[1] for box in full]
    return _LineFeatures(
        full_count=len(full),
        left_range=_span(lefts),
        right_range=_span(rights),
        distinct_lefts=_distinct_edges(lefts),
        distinct_rights=_distinct_edges(rights),
        left_monotone=_monotone_share(lefts, outward="left"),
        right_monotone=_monotone_share(rights, outward="right"),
    )


def _full_lines_top_down(
    line_boxes: list[tuple[float, float, float]],
) -> list[tuple[float, float, float]]:
    """Keep lines at least 60% of the peak width, top of the page first.

    IL y grows upward, so the first visual line is the larger y. A
    downward sort would read a left-stepping taper as a step-back.
    """
    widths = [x1 - x0 for x0, x1, _y in line_boxes]
    peak = max(widths) if widths else 0.0
    full = [
        (x0, x1, y)
        for (x0, x1, y), width in zip(line_boxes, widths, strict=True)
        if peak > 0 and width >= _FULL_WIDTH_RATIO * peak
    ]
    full.sort(key=lambda box: box[2], reverse=True)
    return full


def _span(values: list[float]) -> float:
    if not values:
        return 0.0
    return max(values) - min(values)


def _distinct_edges(values: list[float]) -> int:
    return len({round(value / _EDGE_BUCKET_PT) for value in values})


def _monotone_share(values: list[float], *, outward: str) -> float:
    """Share of successive edges that do not jump outward by more than 6pt.

    A free left edge steps back when it jumps left. A free right edge steps
    back when it jumps right. Reading order is top of the page first.
    """
    if len(values) < 2:
        return 1.0
    deltas = [values[index + 1] - values[index] for index in range(len(values) - 1)]
    if outward == "right":
        held = sum(1 for delta in deltas if delta <= _MAX_STEP_BACK)
    else:
        held = sum(1 for delta in deltas if delta >= -_MAX_STEP_BACK)
    return held / len(deltas)
