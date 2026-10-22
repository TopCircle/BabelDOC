"""Pinned right edge. The left edge runs one way for at least 18pt.

A last line that is still wide enough to count as full, but ends short
of the wall, does not open the pinned edge. The threshold stays 8pt.
A hang, and a left walk that clears the 16pt wall only once, keep the
shared range so those blocks stay where they already matched.
"""

from __future__ import annotations

from collections.abc import Sequence

from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.contract import (
    BlockEdges,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.contract import (
    one_direction,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.outline import (
    _hang_indent,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.outline import (
    _repeated_indent,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.outline import (
    _strip_short_tail,
)

THRESHOLD: float = 8.0
_FREE_EDGE = 18.0
_WALK = 16.0


def claim(edges: BlockEdges, lines: Sequence[Sequence[float]]) -> float | None:
    """Residual is the pinned edge. A short or folded free edge is not a candidate."""
    if not _candidate(edges, lines):
        return None
    if edges.right_range < THRESHOLD or _keep_shared_range(lines):
        return edges.right_range
    return _pinned_after_tail(lines)


def _candidate(edges: BlockEdges, lines: Sequence[Sequence[float]]) -> bool:
    if edges.marker != "none" or edges.full_count < 4:
        return False
    if not one_direction([float(line[0]) for line in lines]):
        return False
    return edges.left_range >= _FREE_EDGE


def _keep_shared_range(lines: Sequence[Sequence[float]]) -> bool:
    """True when remeasuring the tail would take a block another shape owns."""
    if _hang_indent(lines) is not None or _repeated_indent(lines) is not None:
        return True
    return _lines_past_wall(lines) < 2


def _lines_past_wall(lines: Sequence[Sequence[float]]) -> int:
    lefts = [float(line[0]) for line in lines]
    outer = min(lefts)
    return sum(value - outer > _WALK for value in lefts)


def _pinned_after_tail(lines: Sequence[Sequence[float]]) -> float:
    body = _strip_short_tail(lines)
    rights = [float(line[1]) for line in body]
    if not rights:
        return 0.0
    return max(rights) - min(rights)


def fill(lines: Sequence[Sequence[float]]) -> tuple[tuple[float, float], ...]:
    """Each sealed line's own left and right.

    There is no figure frame on this block. The edge is the line itself.
    """
    return tuple((float(line[0]), float(line[1])) for line in lines)
