"""Left edge straight. The right edge is narrow on top and wide below."""

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
    return right_step(edges, lines, "lower_wide")


def fill(lines: Sequence[Sequence[float]]) -> tuple[tuple[float, ...], ...]:
    """The step, with the line height kept on each edge.

    A short tail is the sentence ending under the wide part. Its ink
    does not narrow the frame. A Chinese line uses the edge at its height.
    """
    if not lines:
        return ()
    body = _strip_short_tail(lines)
    wide = max(float(line[1]) for line in body)
    edges = []
    for index, line in enumerate(lines):
        right = float(line[1]) if index < len(body) else wide
        edge = [float(line[0]), right]
        if len(line) >= 3:
            edge.append(float(line[2]))
        edges.append(tuple(edge))
    return tuple(edges)
