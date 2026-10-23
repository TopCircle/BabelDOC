"""Nearest block below, and whether another block sits between the two.

Column order, list order, and the body paragraph gap share this walk.
The edge function chooses the column. A list passes its marker edge.
A column passes its left edge. Ink that crosses the upper block counts
as between them too. Two copies of the same test drift, and a later
whole-chain shift then moves the wrong paragraph.
"""

from __future__ import annotations

from collections.abc import Callable

from babeldoc.format.pdf.document_il.utils.layout_plan.model import Region
from babeldoc.format.pdf.document_il.utils.placement_paradigm import shares_column_left

_CROSS = 8.0


def left_edge(region: Region) -> float:
    return min(line.x0 for line in region.lines)


def top(region: Region) -> float:
    return max(line.y0 for line in region.lines)


def bottom(region: Region) -> float:
    return min(line.y0 for line in region.lines)


def next_below(
    region: Region,
    candidates: list[Region],
    edge: Callable[[Region], float],
) -> Region | None:
    """The closest candidate at or below ``region`` on the same edge."""
    floor = bottom(region)
    below = [
        other
        for other in candidates
        if other.region_id != region.region_id
        and shares_column_left(edge(region), edge(other))
        and top(other) <= floor
    ]
    if not below:
        return None
    return max(below, key=top)


def blocked(
    upper: Region,
    lower: Region,
    obstacles: list[Region],
    edge: Callable[[Region], float],
) -> bool:
    """True when an obstacle sits strictly between the pair.

    The same edge counts. Ink that crosses the upper block by at least
    8pt counts too, so an outdented title is not skipped.
    """
    high = bottom(upper)
    low = top(lower)
    for other in obstacles:
        if top(other) <= low or bottom(other) >= high:
            continue
        if shares_column_left(edge(upper), edge(other)):
            return True
        if _cross(upper, other) >= _CROSS:
            return True
    return False


def _cross(upper: Region, other: Region) -> float:
    left = max(left_edge(upper), left_edge(other))
    right = min(_right_edge(upper), _right_edge(other))
    return right - left


def _right_edge(region: Region) -> float:
    return max(line.x1 for line in region.lines)
