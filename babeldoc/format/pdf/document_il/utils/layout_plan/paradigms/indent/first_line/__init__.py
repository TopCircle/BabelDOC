"""First line indented. Remaining lines share a straight left margin."""

from __future__ import annotations

from collections.abc import Sequence

from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.contract import (
    BlockEdges,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.outline import (
    first_line_indent,
)

THRESHOLD: float = 8.0


def claim(edges: BlockEdges, lines: Sequence[Sequence[float]]) -> float | None:
    """Residual from this walk."""
    return first_line_indent(edges, lines)


def fill(lines: Sequence[Sequence[float]]) -> tuple[tuple[float, ...], ...]:
    """First line starts indented. Later lines share the straight outer margin."""
    if not lines:
        return ()
    if len(lines) < 2:
        return tuple(tuple(float(v) for v in line[:3]) for line in lines)
    outer_right = max(float(line[1]) for line in lines)
    last = len(lines) - 1
    edges = []
    for index, line in enumerate(lines):
        x0 = float(line[0])
        x1 = (
            outer_right
            if (index == last or outer_right - float(line[1]) <= 16.0)
            else float(line[1])
        )
        edge = [x0, x1]
        if len(line) >= 3:
            edge.append(float(line[2]))
        edges.append(tuple(edge))
    return tuple(edges)
