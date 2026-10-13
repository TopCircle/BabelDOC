"""Both edges stay within one point.

Fewer than two full lines is not a candidate.
"""

from __future__ import annotations

from collections.abc import Sequence

from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.contract import (
    BlockEdges,
)

THRESHOLD: float = 1.0


def claim(
    edges: BlockEdges,
    lines: Sequence[Sequence[float]],  # noqa: ARG001
) -> float | None:
    """Residual is the wider edge range. Coordinates are not read."""
    if edges.marker != "none":
        return None
    if edges.full_count < 2:
        return None
    return max(edges.left_range, edges.right_range)
