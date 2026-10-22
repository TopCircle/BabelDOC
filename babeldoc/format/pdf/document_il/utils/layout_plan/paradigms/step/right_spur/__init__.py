"""Left edge straight. One line alone reaches the right edge."""

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
    return right_step(edges, lines, "spur")


def fill(lines: Sequence[Sequence[float]]) -> tuple[tuple[float, ...], ...]:
    """The one wide line keeps its right. The shelf stays narrow.

    A short tail sits on the shelf. It does not open to the spur.
    A Chinese line uses the edge at its height.
    """
    if not lines:
        return ()
    body = _strip_short_tail(lines)
    rights = [float(line[1]) for line in body]
    outer = max(rights) if rights else 0.0
    shelf_rights = [value for value in rights if value < outer - 4.0]
    shelf = max(shelf_rights) if shelf_rights else (rights[-1] if rights else 0.0)
    edges = []
    for index, line in enumerate(lines):
        right = float(line[1]) if index < len(body) else shelf
        edge = [float(line[0]), right]
        if len(line) >= 3:
            edge.append(float(line[2]))
        edges.append(tuple(edge))
    return tuple(edges)
