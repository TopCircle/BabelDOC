"""A bullet hangs. Continuation lines share one indent."""

from __future__ import annotations

from collections.abc import Sequence

from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.contract import (
    BlockEdges,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.outline import marked

THRESHOLD: float = 8.0


def claim(edges: BlockEdges, lines: Sequence[Sequence[float]]) -> float | None:
    """Residual from this walk."""
    return marked(edges, lines, "bullet", "any")


def fill(lines: Sequence[Sequence[float]]) -> tuple[tuple[float, ...], ...]:
    """A hanging bullet, keeping each scanned line and its top."""
    edges = []
    for line in lines:
        edge = [float(line[0]), float(line[1])]
        if len(line) >= 3:
            edge.append(float(line[2]))
        edges.append(tuple(edge))
    return tuple(edges)

