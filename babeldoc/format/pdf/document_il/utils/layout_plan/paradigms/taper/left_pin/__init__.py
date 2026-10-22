"""Pinned left edge. The right edge runs one way for at least 18pt.

A step of 4pt or less does not set the direction. The short last line
does. A small step may oppose the counted steps when two of them
remain, none is larger than 18pt, and two lines sit more than 18pt
inside the outer edge.
"""

from __future__ import annotations

from collections.abc import Sequence

from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.contract import (
    BlockEdges,
)

THRESHOLD: float = 8.0
_FREE_EDGE = 18.0
_STEP = 4.0


def claim(edges: BlockEdges, lines: Sequence[Sequence[float]]) -> float | None:
    """Residual is the pinned edge. A short or folded free edge is not a candidate."""
    if edges.marker != "none":
        return None
    if edges.full_count < 4:
        return None
    if not _one_way([float(line[1]) for line in lines]):
        return None
    if edges.right_range < _FREE_EDGE:
        return None
    return edges.left_range


def _one_way(values: Sequence[float]) -> bool:
    """True when steps past 4pt share a direction.

    A smaller step may oppose them only when the counted steps are a
    run: two or more, none larger than the free-edge floor, and two
    lines more than that floor inside the outer edge.
    """
    if len(values) < 2:
        return False
    deltas = [values[index + 1] - values[index] for index in range(len(values) - 1)]
    counted = [delta for delta in deltas if abs(delta) > _STEP]
    if _reversed(counted):
        return False
    if not _reversed(deltas):
        return True
    outer = max(values)
    inside = sum(1 for value in values if outer - value > _FREE_EDGE)
    return (
        len(counted) >= 2
        and all(abs(delta) <= _FREE_EDGE for delta in counted)
        and inside >= 2
    )


def _reversed(deltas: Sequence[float]) -> bool:
    """True when the steps go both ways. A zero step is neither."""
    return any(delta > 0.0 for delta in deltas) and any(delta < 0.0 for delta in deltas)


def fill(lines: Sequence[Sequence[float]]) -> tuple[tuple[float, float], ...]:
    """Each sealed line's own left and right.

    There is no figure frame on this block. The edge is the line itself.
    """
    return tuple((float(line[0]), float(line[1])) for line in lines)
