"""Nearest block below, and whether another block sits between the two.

Column order, list order, and the body paragraph gap share this walk.
The edge function is the only difference. A list passes its marker edge.
A column passes its left edge. Two copies of the same test drift, and a
later whole-chain shift then moves the wrong paragraph.
"""

from __future__ import annotations

from collections.abc import Callable

from babeldoc.format.pdf.document_il.utils.layout_plan.model import Region
from babeldoc.format.pdf.document_il.utils.placement_paradigm import shares_column_left


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
    """True when an obstacle on this edge sits strictly between the pair."""
    high = bottom(upper)
    low = top(lower)
    for other in obstacles:
        if not shares_column_left(edge(upper), edge(other)):
            continue
        if top(other) > low and bottom(other) < high:
            return True
    return False
