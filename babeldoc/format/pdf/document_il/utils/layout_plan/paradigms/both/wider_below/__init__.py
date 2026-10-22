"""Both edges open downward past the wall, in more than one step. Travels stay within 48pt."""

from __future__ import annotations

from collections.abc import Sequence

from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.contract import (
    BlockEdges,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.outline import (
    wider_below,
)

THRESHOLD: float = 48.0
# Same short-line sizes the shared walk already uses. This module only
# adds a tail whose left keeps opening past that wall.
_SHORT = 24.0
_SLACK = 4.0
_WALL = 8.0


def claim(edges: BlockEdges, lines: Sequence[Sequence[float]]) -> float | None:
    """Residual from this walk. A short tail that keeps opening is not a turn."""
    return wider_below(edges, _body(lines))


def fill(lines: Sequence[Sequence[float]]) -> tuple[tuple[float, float], ...]:
    """Each full line's own left and right.

    This block has no figure frame. The edge is the line that was sealed.
    A short last line that keeps the same left walk is not an edge.
    """
    return tuple((float(line[0]), float(line[1])) for line in _body(lines))


def _body(lines: Sequence[Sequence[float]]) -> tuple[Sequence[float], ...]:
    """Drop at most two short tails whose left step stays on this walk."""
    kept = list(lines)
    dropped = 0
    while len(kept) >= 3 and dropped < 2:
        previous = kept[-2]
        last = kept[-1]
        right_inset = float(previous[1]) - float(last[1])
        left_out = float(previous[0]) - float(last[0])
        if right_inset < _SHORT or left_out <= _WALL:
            break
        if not _continues(kept[:-1], left_out):
            break
        kept.pop()
        dropped += 1
    return tuple(kept)


def _continues(body: Sequence[Sequence[float]], left_out: float) -> bool:
    """True when the tail steps out by about the same amount as the walk."""
    opened: list[float] = []
    for index in range(len(body) - 1):
        step = float(body[index][0]) - float(body[index + 1][0])
        if step > _SLACK:
            opened.append(step)
    if not opened:
        return False
    return left_out <= opened[-1] + _SLACK
