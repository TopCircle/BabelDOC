"""Left edge straight. The right edge is wide on top and narrow below."""

from __future__ import annotations

from collections.abc import Sequence

from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.contract import (
    BlockEdges,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.outline import (
    _strip_short_tail,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.outline import (
    right_step,
)

THRESHOLD: float = 8.0


def claim(edges: BlockEdges, lines: Sequence[Sequence[float]]) -> float | None:
    """Residual from this walk."""
    return right_step(edges, lines, "upper_wide")


def fill(lines: Sequence[Sequence[float]]) -> tuple[tuple[float, ...], ...]:
    """The step, with the line height kept on each edge.

    The lower shelf is the narrow one. A short tail sits on that shelf,
    so it keeps the shelf's right edge. It does not open to the wide top.
    A Chinese line uses the edge at its height.
    """
    if not lines:
        return ()
    body = _strip_short_tail(lines)
    shelf = float(body[-1][1])
    edges = []
    for index, line in enumerate(lines):
        right = float(line[1]) if index < len(body) else shelf
        edge = [float(line[0]), right]
        if len(line) >= 3:
            edge.append(float(line[2]))
        edges.append(tuple(edge))
    return tuple(edges)
