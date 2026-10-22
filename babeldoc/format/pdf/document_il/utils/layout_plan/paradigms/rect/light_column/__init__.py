"""Both edges stay within 16pt, aside from one short line.

A right edge that steps in once and comes back keeps each line's own
right. Anything shallower, or more than one dip, still shares the wall.
A left edge that walks one way by more than 4pt keeps each earlier
line's own left. A fold, and a drift of 4pt or less, still share it.
The last line stays on the outer edge.
"""

from __future__ import annotations

from collections.abc import Sequence

from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.contract import (
    BlockEdges,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.outline import (
    light_column,
)

THRESHOLD: float = 16.0
_WALL = 16.0
_BOWL = 8.0
_SLACK = 4.0


def claim(edges: BlockEdges, lines: Sequence[Sequence[float]]) -> float | None:
    """Residual from this walk."""
    return light_column(edges, lines)


def fill(lines: Sequence[Sequence[float]]) -> tuple[tuple[float, float], ...]:
    """Lines inside the wall share the outer edge.

    A right edge that steps in once and comes back keeps each line's own
    right. A line more than 16pt off either wall keeps its own edge,
    unless it is the last line. A one-way left walk keeps each earlier
    line's own left. There is no figure frame on this block.
    """
    if not lines:
        return ()
    outer_left = min(float(line[0]) for line in lines)
    outer_right = max(float(line[1]) for line in lines)
    last = len(lines) - 1
    right_dip = _one_dip(
        [outer_right - float(line[1]) for line in lines[:last]],
    )
    own_left = _one_way_left(lines)
    pairs: list[tuple[float, float]] = []
    for index, line in enumerate(lines):
        pairs.append(
            _pair(
                line,
                index,
                last,
                outer_left,
                outer_right,
                right_dip,
                own_left,
            ),
        )
    return tuple(pairs)


def _pair(line, index, last, outer_left, outer_right, right_dip, own_left):
    left = float(line[0])
    right = float(line[1])
    if index == last:
        return (outer_left, outer_right)
    if right_dip:
        return (_kept_left(left, outer_left, own_left), right)
    if _off_either_wall(left, right, outer_left, outer_right):
        return (left, right)
    if own_left:
        return (left, outer_right)
    return (outer_left, outer_right)


def _kept_left(left: float, outer_left: float, own_left: bool) -> float:
    if left - outer_left > _WALL or own_left:
        return left
    return outer_left


def _off_either_wall(left, right, outer_left, outer_right) -> bool:
    return left - outer_left > _WALL or outer_right - right > _WALL


def _one_way_left(lines: Sequence[Sequence[float]]) -> bool:
    """True when the left edge walks, and steps over 4pt do not reverse."""
    lefts = [float(line[0]) for line in lines]
    if max(lefts) - min(lefts) <= _SLACK:
        return False
    signs = _left_signs(lefts)
    return not (any(sign > 0 for sign in signs) and any(sign < 0 for sign in signs))


def _left_signs(lefts: Sequence[float]) -> list[int]:
    signs: list[int] = []
    for index in range(len(lefts) - 1):
        delta = lefts[index + 1] - lefts[index]
        if abs(delta) <= _SLACK:
            continue
        signs.append(1 if delta > 0.0 else -1)
    return signs


def _one_dip(insets: Sequence[float]) -> bool:
    """The right edge steps in once, holds, and comes back inside the wall."""
    if len(insets) < 3:
        return False
    depth = max(insets)
    if depth < _BOWL or depth > _WALL:
        return False
    runs = _deep_runs(insets, depth - _SLACK)
    if len(runs) != 1:
        return False
    start, stop = runs[0]
    held = stop - start >= 2
    came_back = start > 0 and stop < len(insets)
    return held and came_back


def _deep_runs(insets: Sequence[float], floor: float) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for index, inset in enumerate(insets):
        if inset >= floor:
            if start is None:
                start = index
            continue
        if start is not None:
            runs.append((start, index))
            start = None
    if start is not None:
        runs.append((start, len(insets)))
    return runs
