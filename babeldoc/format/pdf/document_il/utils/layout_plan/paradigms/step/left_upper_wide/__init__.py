"""Right edge straight. The left edge is wide on top and narrow below."""

from __future__ import annotations

from collections.abc import Sequence

from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.contract import (
    BlockEdges,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.outline import (
    _strip_short_tail,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.outline import (
    left_step,
)

THRESHOLD: float = 8.0


def claim(edges: BlockEdges, lines: Sequence[Sequence[float]]) -> float | None:
    """Residual from this walk."""
    return left_step(edges, lines, "upper_wide")


def fill(lines: Sequence[Sequence[float]]) -> tuple[tuple[float, ...], ...]:
    """The step, with the line height kept on each edge.

    The lower shelf is the narrow one. A short tail sits on that shelf,
    so it keeps the shelf's left edge and opens to the right wall.
    """
    if not lines:
        return ()
    body = _strip_short_tail(lines)
    shelf = float(body[-1][0])
    outer_right = max(float(line[1]) for line in lines)
    edges = []
    for index, line in enumerate(lines):
        left = float(line[0]) if index < len(body) else shelf
        right = float(line[1]) if index < len(body) else outer_right
        edge = [left, right]
        if len(line) >= 3:
            edge.append(float(line[2]))
        edges.append(tuple(edge))
    return tuple(edges)
