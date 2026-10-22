"""Seal text lines into blocks before any paradigm is named.

The cut uses the line pitch, a left-edge jump, and the column overlap.
It does not read a shape name, a sample catalog, or a plugin. A short
line stays in the block. A line-count threshold is not a cut. A short
line to the left of one line on the same row is that line's leader:
it is not a block, and its box is not an edge.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from babeldoc.format.pdf.document_il.utils.layout_plan.model import LineBox
from babeldoc.format.pdf.document_il.utils.layout_plan.model import geometry_digest
from babeldoc.format.pdf.document_il.utils.placement_paradigm import shares_column_left

# Same column overlap already used when regions are related. Not a shape test.
_COLUMN_OVERLAP = 0.35
# A step within half a point of the body pitch is still one line step.
_GAP_EXTRA = 0.5
# Lines this close in y are beside each other, not one under the other.
_BESIDE = 0.5
# How far up a pitch sample may look. Farther than this is not a line step.
_PITCH_LOOK = 48.0

OpenedBy = Literal["page", "gap", "left", "column"]


@dataclass(frozen=True, slots=True)
class SealedBlock:
    """One sealed run of lines. The id is the geometry digest only."""

    block_id: str
    lines: tuple[LineBox, ...]
    opened_by: OpenedBy
    leaders: tuple[LineBox, ...] = ()

    def to_dict(self) -> dict:
        return {
            "block_id": self.block_id,
            "opened_by": self.opened_by,
            "line_count": len(self.lines),
            "lines": [[line.x0, line.x1, line.y0] for line in self.lines],
            "leaders": [[line.x0, line.x1, line.y0] for line in self.leaders],
        }


def seal_lines(lines: Sequence[LineBox]) -> tuple[SealedBlock, ...]:
    """Group lines that share a pitch, a left edge, and a column.

    Reading order is top to bottom. A line joins the block directly
    above it when all three hold. Otherwise it opens a new block.
    """
    ordered = tuple(sorted(lines, key=lambda line: (-line.y0, line.x0, line.x1)))
    if not ordered:
        return ()
    body, leaders_of = _fold_leaders(ordered)
    pitch = _body_pitch(body)
    groups: list[list[LineBox]] = []
    reasons: list[OpenedBy] = []
    for line in body:
        host = _host(groups, line, pitch)
        if host is None:
            reasons.append(_opened_by(groups, line, pitch))
            groups.append([line])
        else:
            host.append(line)
    return tuple(
        SealedBlock(
            block_id=geometry_digest(tuple(group)),
            lines=tuple(group),
            opened_by=reason,
            leaders=tuple(
                leader for line in group for leader in leaders_of.get(line, ())
            ),
        )
        for group, reason in zip(groups, reasons, strict=True)
    )


def _body_pitch(lines: Sequence[LineBox]) -> float:
    """Median step down to the nearest line in the same column.

    The neighbor's left edge is not part of this. A hanging line sits
    one step under a wider line, and that step is the pitch. The larger
    gap before the next run stays above the median on a normal page.
    """
    gaps: list[float] = []
    for index, line in enumerate(lines):
        for above in reversed(lines[:index]):
            gap = above.y0 - line.y0
            if gap <= _BESIDE:
                continue
            if gap > _PITCH_LOOK:
                break
            if _overlap_pair(above, line):
                gaps.append(gap)
                break
    if not gaps:
        return 0.0
    return float(statistics.median(gaps))


def _host(
    groups: list[list[LineBox]], line: LineBox, pitch: float
) -> list[LineBox] | None:
    found: list[LineBox] | None = None
    best: float | None = None
    for group in groups:
        if not _joins(group, line, pitch):
            continue
        gap = _gap(group, line)
        if best is None or gap < best:
            best = gap
            found = group
    return found


def _joins(group: list[LineBox], line: LineBox, pitch: float) -> bool:
    if not _same_column(group, line):
        return False
    gap = _gap(group, line)
    if gap <= _BESIDE:
        return False
    if pitch > 0.0 and gap > pitch + _GAP_EXTRA:
        return False
    return _left_ok(group, line)


def _opened_by(
    groups: list[list[LineBox]], line: LineBox, pitch: float
) -> OpenedBy:
    if not groups:
        return "page"
    same = [group for group in groups if _same_column(group, line)]
    if not same:
        return "column"
    nearest = min(same, key=lambda group: _gap(group, line))
    gap = _gap(nearest, line)
    if gap <= _BESIDE:
        return "column"
    if pitch > 0.0 and gap > pitch + _GAP_EXTRA:
        return "gap"
    return "left"


def _left_ok(group: list[LineBox], line: LineBox) -> bool:
    """True when the line uses a left edge this block already has.

    A block that is still one line may take one step. A step to the
    right is the hanging edge. A step to the left stays only when the
    two right edges share the column tolerance. A later line must match
    an edge the block already stored.
    """
    if any(shares_column_left(item.x0, line.x0) for item in group):
        return True
    if len(group) != 1:
        return False
    if line.x0 > group[0].x0:
        return True
    return shares_column_left(group[0].x1, line.x1)


def _fold_leaders(
    lines: Sequence[LineBox],
) -> tuple[tuple[LineBox, ...], dict[LineBox, tuple[LineBox, ...]]]:
    """Drop a short left-hand line that only sits beside one other line."""
    chosen: dict[int, LineBox] = {}
    for index, line in enumerate(lines):
        host = _leader_host(line, lines)
        if host is not None:
            chosen[index] = host
    host_at = {id(lines[index]): host for index, host in chosen.items()}
    leaders: dict[LineBox, list[LineBox]] = {}
    for index, host in chosen.items():
        host = host_at.get(id(host), host)
        leaders.setdefault(host, []).append(lines[index])
    body = tuple(line for index, line in enumerate(lines) if index not in chosen)
    return body, {host: tuple(items) for host, items in leaders.items()}


def _leader_host(line: LineBox, lines: Sequence[LineBox]) -> LineBox | None:
    """The line this short box sits beside, when it has no column of its own."""
    host = _beside_host(line, lines)
    if host is None or _has_column_neighbor(line, lines):
        return None
    return host


def _beside_host(line: LineBox, lines: Sequence[LineBox]) -> LineBox | None:
    """Nearest line on this row with this box entirely to its left."""
    width = line.x1 - line.x0
    found: LineBox | None = None
    best: float | None = None
    for other in lines:
        if other is line or abs(other.y0 - line.y0) > _BESIDE:
            continue
        if line.x1 > other.x0 + _BESIDE:
            continue
        if width >= other.x1 - other.x0:
            continue
        gap = other.x0 - line.x1
        if best is None or gap < best:
            best = gap
            found = other
    return found


def _has_column_neighbor(line: LineBox, lines: Sequence[LineBox]) -> bool:
    """True when another line continues this left edge down the page.

    A full line that merely starts at the same left is not this column.
    """
    width = line.x1 - line.x0
    for other in lines:
        if other is line or abs(other.y0 - line.y0) <= _BESIDE:
            continue
        if not shares_column_left(line.x0, other.x0):
            continue
        if other.x1 - other.x0 > width * 4:
            continue
        if _overlap_pair(line, other):
            return True
    return False


def _same_column(group: list[LineBox], line: LineBox) -> bool:
    return _overlap(min(item.x0 for item in group), max(item.x1 for item in group), line.x0, line.x1)


def _overlap_pair(above: LineBox, below: LineBox) -> bool:
    return _overlap(above.x0, above.x1, below.x0, below.x1)


def _overlap(a0: float, a1: float, b0: float, b1: float) -> bool:
    overlap = min(a1, b1) - max(a0, b0)
    narrow = max(1.0, min(a1 - a0, b1 - b0))
    return overlap >= _COLUMN_OVERLAP * narrow


def _gap(group: list[LineBox], line: LineBox) -> float:
    return min(item.y0 for item in group) - line.y0
