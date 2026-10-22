"""First line at the left. Later lines share an indent of at least 48pt."""

from __future__ import annotations

from collections.abc import Sequence

from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.contract import (
    BlockEdges,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.outline import hang

THRESHOLD: float = 8.0


def claim(edges: BlockEdges, lines: Sequence[Sequence[float]]) -> float | None:
    """Residual from this walk."""
    return hang(edges, lines, "deep")


def fill(lines: Sequence[Sequence[float]]) -> tuple[tuple[float, ...], ...]:
    """The deep hanging indent, with each scanned line and its top kept.

    First line starts on the outer left edge.
    Later lines share the indented left margin.
    Each line keeps its own right edge and top height.
    """
    edges = []
    for line in lines:
        edge = [float(line[0]), float(line[1])]
        if len(line) >= 3:
            edge.append(float(line[2]))
        edges.append(tuple(edge))
    return tuple(edges)
