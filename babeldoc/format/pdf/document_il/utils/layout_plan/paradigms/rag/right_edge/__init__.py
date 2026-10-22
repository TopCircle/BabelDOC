"""Left edge straight. The right edge folds, and the full lines stay shallow."""

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


def claim(edges: BlockEdges, lines: Sequence[Sequence[float]]) -> float | None:
    """Residual from this walk. A fold past 48pt is the deep module."""
    if edges.right_range > _HANG_DEEP:
        return None
    return right_rag(edges, lines)


def fill(lines: Sequence[Sequence[float]]) -> tuple[tuple[float, float], ...]:
    """Each scanned line. Chinese wraps on that line's width."""
    return tuple((float(line[0]), float(line[1])) for line in lines)
