"""Pinned left edge. The right edge must run one way."""

from __future__ import annotations

from collections.abc import Sequence

from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.contract import (
    BlockEdges,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.contract import (
    one_direction,
)

THRESHOLD: float = 8.0


def claim(edges: BlockEdges, lines: Sequence[Sequence[float]]) -> float | None:
    """Residual of a left pin, or ``None`` when this module is not a candidate."""
    if edges.marker != "none":
        return None
    if edges.full_count < 4 or not one_direction([line[1] for line in lines]):
        return None
    return (
        edges.left_range
        + max(0.0, 18.0 - edges.right_range)
        + max(0.0, 0.70 - edges.right_monotone) * 18.0
    )
