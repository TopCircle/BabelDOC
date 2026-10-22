"""Left edge straight. The full lines' right edge folds past 48pt."""

from __future__ import annotations

from collections.abc import Sequence

from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.contract import (
    BlockEdges,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.outline import (
    _HANG_DEEP,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.outline import (
    right_rag,
)

THRESHOLD: float = 8.0
FLOW = "edge"


def claim(edges: BlockEdges, lines: Sequence[Sequence[float]]) -> float | None:
    """Residual from this walk. A shallow fold stays on rag/right_edge."""
    if edges.right_range <= _HANG_DEEP:
        return None
    return right_rag(edges, lines)


def fill(lines: Sequence[Sequence[float]]) -> tuple[tuple[float, ...], ...]:
    """Each scanned line, with its top kept.

    Chinese wraps on that line's right. The top seats the box on the
    first scanned line. The bottom of the box stays put.
    """
    edges = []
    for line in lines:
        edge = [float(line[0]), float(line[1])]
        if len(line) >= 3:
            edge.append(float(line[2]))
        edges.append(tuple(edge))
    return tuple(edges)
