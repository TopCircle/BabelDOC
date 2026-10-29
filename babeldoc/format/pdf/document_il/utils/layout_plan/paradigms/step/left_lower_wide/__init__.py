"""Right edge straight. The left edge is narrow on top and wide below."""

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
    return left_step(edges, lines, "lower_wide")


def fill(lines: Sequence[Sequence[float]]) -> tuple[tuple[float, ...], ...]:
    """The step, with the line height kept on each edge.

    A short tail is the sentence ending under the wide part. It keeps
    the wide part's left margin and opens to the right wall.
    """
    if not lines:
        return ()
    body = _strip_short_tail(lines)
    wide_left = min(float(line[0]) for line in body)
    outer_right = max(float(line[1]) for line in lines)
    edges = []
    for index, line in enumerate(lines):
        left = float(line[0]) if index < len(body) else wide_left
        right = float(line[1]) if index < len(body) else outer_right
        edge = [left, right]
        if len(line) >= 3:
            edge.append(float(line[2]))
        edges.append(tuple(edge))
    return tuple(edges)
