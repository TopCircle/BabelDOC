"""Right edge straight. One line alone reaches the left edge."""

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
    return left_step(edges, lines, "spur")


def fill(lines: Sequence[Sequence[float]]) -> tuple[tuple[float, ...], ...]:
    """The one wide line keeps its left. The shelf stays indented."""
    if not lines:
        return ()
    body = _strip_short_tail(lines)
    lefts = [float(line[0]) for line in body]
    outer = min(lefts) if lefts else 0.0
    shelf_lefts = [value for value in lefts if value > outer + 4.0]
    shelf = min(shelf_lefts) if shelf_lefts else (lefts[-1] if lefts else 0.0)
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
