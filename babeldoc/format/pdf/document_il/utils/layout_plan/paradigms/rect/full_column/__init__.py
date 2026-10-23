"""Both edges stay within one point.

Fewer than two full lines is not a candidate.
"""

from __future__ import annotations

from collections.abc import Sequence

from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.contract import (
    BlockEdges,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.outline import _coord
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.outline import (
    _step_kind,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.outline import (
    _strip_short_tail,
)

THRESHOLD: float = 1.0


def claim(
    edges: BlockEdges,
    lines: Sequence[Sequence[float]],
) -> float | None:
    """Residual is the wider edge range.

    Full lines can look flat when the lines beside a figure were left
    out of that range. A step that remains after the short tail is not
    this column.
    """
    if edges.marker != "none":
        return None
    if edges.full_count < 2:
        return None
    if _step_kind(_coord(_strip_short_tail(lines), 1)) is not None:
        return None
    return max(edges.left_range, edges.right_range)


def fill(lines: Sequence[Sequence[float]]) -> tuple[tuple[float, ...], ...]:
    """A straight column, keeping each scanned line and its top.

    Every line keeps its scanned left and right edges, and its top
    height when present.
    """
    edges = []
    for line in lines:
        edge = [float(line[0]), float(line[1])]
        if len(line) >= 3:
            edge.append(float(line[2]))
        edges.append(tuple(edge))
    return tuple(edges)
