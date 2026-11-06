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
    _first_line_indent,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.outline import (
    _hang_indent,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.outline import (
    _repeated_indent,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.outline import (
    _spur_left,
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
    pinned = _pinned_after_tail(lines)
    if pinned >= THRESHOLD:
        return pinned
    if edges.right_range < THRESHOLD or _keep_shared_range(lines):
        return edges.right_range
    return pinned


def _candidate(edges: BlockEdges, lines: Sequence[Sequence[float]]) -> bool:
    if edges.marker != "none" or edges.full_count < 4:
        return False
    # The left spur check uses its own tail view. Continuity stays on the right.
    left_body = _strip_short_tail(lines, free_side="left")
    if _spur_left([float(line[0]) for line in left_body]):
        return False
    body = _strip_short_tail(lines)
    check_lines = body if len(body) >= 4 else lines
    if not _runs_one_way([float(line[0]) for line in check_lines]):
        return False
    if _first_line_indent(lines) is not None:
        return False
    return edges.left_range >= _FREE_EDGE


def _runs_one_way(values: Sequence[float]) -> bool:
    if len(values) < 2:
        return False
    if one_direction(values):
        return True
    deltas = [values[index + 1] - values[index] for index in range(len(values) - 1)]
    pos_sum = sum(delta for delta in deltas if delta > 0.0)
    neg_sum = sum(-delta for delta in deltas if delta < 0.0)
    if pos_sum >= _FREE_EDGE and neg_sum <= 12.0 and deltas[-1] <= 0.0:
        return True
    if neg_sum >= _FREE_EDGE and pos_sum <= 12.0 and deltas[-1] >= 0.0:
        return True
    return False


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


def fill(lines: Sequence[Sequence[float]]) -> tuple[tuple[float, ...], ...]:
    """Each sealed line's own left and right.

    There is no figure frame on this block. The edge is the line itself.
    A short tail keeps the lower shelf's left edge and outer right wall.
    """
    if not lines:
        return ()
    body = _strip_short_tail(lines)
    shelf = float(body[-1][0])
    outer_right = max(float(line[1]) for line in body)
    edges = []
    for index, line in enumerate(lines):
        left = float(line[0]) if index < len(body) else shelf
        right = float(line[1]) if index < len(body) else outer_right
        edge = [left, right]
        if len(line) >= 3:
            edge.append(float(line[2]))
        edges.append(tuple(edge))
    return tuple(edges)
