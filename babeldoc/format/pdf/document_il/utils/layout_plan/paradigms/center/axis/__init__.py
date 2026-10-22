"""A narrow display column folded around one axis.

A step of 4pt or less does not count as a fold. The fill keeps each
scanned line. The line ends on that right. This module does not call
another claim.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence

from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.contract import (
    BlockEdges,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.contract import (
    one_direction,
)

THRESHOLD: float = 24.0
ALIGNMENT = "right"

_MIN_LINES = 4
_PITCH = 22.0
_MIN_WIDTH = 80.0
_MAX_WIDTH = 200.0
_EDGE = 8.0
_MISS = 16.0
_LEG = 24.0
_SLACK = 4.0


def claim(edges: BlockEdges, lines: Sequence[Sequence[float]]) -> float | None:
    """How far line centers sit from the block's median center."""
    if not _display_column(edges, lines):
        return None
    if _opens_down(lines):
        return None
    return _axis_span(lines)


def fill(lines: Sequence[Sequence[float]]) -> tuple[tuple[float, ...], ...]:
    """Keep each scanned line. The line ends on that right.

    The width stays the English line, so the Chinese line is not opened
    to the outermost left. The third number is that line's height.
    """
    if not lines or any(len(line) < 2 for line in lines):
        return tuple(tuple(float(value) for value in line[:3]) for line in lines)
    placed = []
    for line in lines:
        edge = [float(line[0]), float(line[1])]
        if len(line) >= 3:
            edge.append(float(line[2]))
        placed.append(tuple(edge))
    return tuple(placed)


def _display_column(edges: BlockEdges, lines: Sequence[Sequence[float]]) -> bool:
    """Narrow display column whose two edges both leave the wall."""
    if edges.marker != "none" or len(lines) < _MIN_LINES:
        return False
    if edges.full_count < _MIN_LINES:
        return False
    if edges.left_range <= _EDGE or edges.right_range <= _EDGE:
        return False
    pitch = _pitch(lines)
    if pitch is None or pitch < _PITCH:
        return False
    lefts, rights = _sides(lines)
    width = max(rights) - min(lefts)
    if not _MIN_WIDTH <= width <= _MAX_WIDTH:
        return False
    return _off_a_wall(lefts, rights)


def _opens_down(lines: Sequence[Sequence[float]]) -> bool:
    """True when both edges keep opening downward by at least 24pt.

    That trapezoid belongs to the walk that already owns it. A fold on
    either edge is this axis.
    """
    lefts, rights = _sides(lines)
    lefts = _held(lefts)
    rights = _held(rights)
    if not one_direction(lefts) or not one_direction(rights):
        return False
    return lefts[0] - lefts[-1] >= _LEG and rights[-1] - rights[0] >= _LEG


def _axis_span(lines: Sequence[Sequence[float]]) -> float:
    centers = [(float(line[0]) + float(line[1])) / 2.0 for line in lines]
    mid = statistics.median(centers)
    return max(abs(center - mid) for center in centers)


def _pitch(lines: Sequence[Sequence[float]]) -> float | None:
    if any(len(line) < 3 for line in lines):
        return None
    ys = sorted(float(line[2]) for line in lines)
    steps = [ys[index + 1] - ys[index] for index in range(len(ys) - 1)]
    if not steps:
        return None
    return float(statistics.median(steps))


def _off_a_wall(lefts: Sequence[float], rights: Sequence[float]) -> bool:
    """At least two lines clear one outer wall by more than 16pt."""
    left_outer = min(lefts)
    right_outer = max(rights)
    left_miss = sum(value - left_outer > _MISS for value in lefts)
    right_miss = sum(right_outer - value > _MISS for value in rights)
    return left_miss >= 2 or right_miss >= 2


def _held(values: Sequence[float]) -> list[float]:
    """A step of 4pt or less stays on the previous edge."""
    if len(values) == 0:
        return []
    held = [float(values[0])]
    for value in values[1:]:
        value = float(value)
        if abs(value - held[-1]) <= _SLACK:
            held.append(held[-1])
        else:
            held.append(value)
    return held


def _sides(lines: Sequence[Sequence[float]]) -> tuple[list[float], list[float]]:
    return (
        [float(line[0]) for line in lines],
        [float(line[1]) for line in lines],
    )
