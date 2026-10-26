"""Frozen reading order for rect_flow regions.

``above_id`` stays the loose 0.35 overlap. This chain does not read it.
A block joins the next rect_flow block below only when their left edges
already belong to one column. A title, quote, or any other non-rect
block in that column ends the chain.
"""

from __future__ import annotations

import statistics
from dataclasses import replace

from babeldoc.format.pdf.document_il.utils.layout_plan.model import ColumnLink
from babeldoc.format.pdf.document_il.utils.layout_plan.model import LayoutFacts
from babeldoc.format.pdf.document_il.utils.layout_plan.model import LayoutPlan
from babeldoc.format.pdf.document_il.utils.layout_plan.model import Region
from babeldoc.format.pdf.document_il.utils.layout_plan.model import RegionDecision
from babeldoc.format.pdf.document_il.utils.layout_plan.neighbors import blocked
from babeldoc.format.pdf.document_il.utils.layout_plan.neighbors import bottom
from babeldoc.format.pdf.document_il.utils.layout_plan.neighbors import left_edge
from babeldoc.format.pdf.document_il.utils.layout_plan.neighbors import next_below
from babeldoc.format.pdf.document_il.utils.layout_plan.neighbors import top
from babeldoc.format.pdf.document_il.utils.layout_plan.paragraph_gap import (
    scanned_paragraph_gap,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.pocket_chain import (
    scanned_edge_gap,
)
from babeldoc.format.pdf.document_il.utils.placement_paradigm import shares_column_left

# A side display column, same gates as a centered quote: narrow, and
# leading well above body pitch. Body text beside a photo is narrower
# than a full column but its pitch stays the body pitch.
_DISPLAY_LINES = 4
_DISPLAY_PITCH = 22.0
_DISPLAY_MIN_WIDTH = 80.0
_DISPLAY_MAX_WIDTH = 200.0


def with_column_links(facts: LayoutFacts, plan: LayoutPlan) -> LayoutPlan:
    """Copy the plan and attach one link per rect_flow region."""
    return replace(plan, column_links=column_links(facts, plan.decisions))


def column_links(
    facts: LayoutFacts, decisions: tuple[RegionDecision, ...]
) -> tuple[ColumnLink, ...]:
    by_decision = {item.region_id: item for item in decisions}
    rects = [
        region
        for region in facts.regions
        if region.lines
        and by_decision[region.region_id].base_strategy == "rect_flow"
    ]
    obstacles = [
        region
        for region in facts.regions
        if region.lines
        and by_decision[region.region_id].base_strategy != "rect_flow"
    ]
    flow_next: dict[str, str] = {}
    for region in rects:
        nearest = next_below(region, rects, left_edge)
        if nearest is None or blocked(region, nearest, obstacles, left_edge):
            continue
        flow_next[region.region_id] = nearest.region_id
    chains = _chains(rects, flow_next)
    edges = _edges(rects, chains)
    by_region = {region.region_id: region for region in rects}
    previous = {lower: upper for upper, lower in flow_next.items()}
    links: list[ColumnLink] = []
    for region in rects:
        chain_id = chains[region.region_id]
        left, chain_right = edges[chain_id]
        right = _right_before_display(region, chain_right, obstacles)
        side, slices = _figure_gap(region, facts.figures, left, chain_right)
        pin = left if side == "right" else chain_right
        above = by_region.get(previous.get(region.region_id, ""))
        if above is not None:
            gap_value = scanned_paragraph_gap(above.lines, region.lines)
        else:
            gap_value = _gap_under_pocket(region, obstacles, by_decision)
        links.append(
            ColumnLink(
                region_id=region.region_id,
                column_chain_id=chain_id,
                flow_next_id=flow_next.get(region.region_id),
                column_left=left,
                column_right=right,
                free_side=side,
                gap_slices=slices,
                edge_gap=scanned_edge_gap(region.lines, slices, side, pin),
                paragraph_gap=gap_value,
            )
        )
    return tuple(links)


def _gap_under_pocket(
    region: Region,
    obstacles: list[Region],
    by_decision: dict[str, RegionDecision],
) -> float:
    """Scanned white between a pocket and the rect column under it.

    The rect chain stops at the pocket, so this head has no rect above it.
    The pocket pull reads the number. A block between them leaves it at 0.
    """
    above = [
        other
        for other in obstacles
        if by_decision[other.region_id].base_strategy == "shaped_pocket"
        and shares_column_left(left_edge(region), left_edge(other))
        and bottom(other) >= top(region) - 0.5
    ]
    if not above:
        return 0.0
    pocket = min(above, key=bottom)
    between = [item for item in obstacles if item.region_id != pocket.region_id]
    if blocked(pocket, region, between, left_edge):
        return 0.0
    return scanned_paragraph_gap(pocket.lines, region.lines)


def _figure_gap(
    region: Region,
    figures: tuple,
    left: float,
    right: float,
) -> tuple[str, tuple[tuple[float, float, float], ...]]:
    """Figure edges beside this column, or nothing when the figure is distant.

    A flat English edge is still the column. The line width is the gap at
    that height, which may be wider than the English line. A figure further
    away than the column is wide is a different object and is not a gap.
    """
    if not figures or not region.lines:
        return "", ()
    width = right - left
    if width <= 1.0:
        return "", ()
    ys = [line.y0 for line in region.lines]
    y_lo, y_hi = min(ys), max(ys)
    min_x1 = min(line.x1 for line in region.lines)
    max_x0 = max(line.x0 for line in region.lines)
    right_edges: list[float] = []
    left_edges: list[float] = []
    for figure in figures:
        if figure.y1 < y_lo or figure.y0 > y_hi:
            continue
        # If every line in this column already extends far past the figure edge,
        # the figure is an underlay background, not an obstacle bounding the column.
        if figure.x0 > left + 1.0 and figure.x0 > min_x1 - 40.0:
            right_edges.append(figure.x0)
        if figure.x1 < right - 1.0 and figure.x1 < max_x0 + 40.0:
            left_edges.append(figure.x1)
    side = ""
    if right_edges and min(right_edges) - right <= width:
        side = "right"
    elif left_edges and left - max(left_edges) <= width:
        side = "left"
    if not side:
        return "", ()
    slices: list[tuple[float, float, float]] = []
    for figure in figures:
        if side == "right" and figure.x0 > left + 1.0:
            slices.append((figure.y0, figure.y1, figure.x0))
        elif side == "left" and figure.x1 < right - 1.0:
            slices.append((figure.y0, figure.y1, figure.x1))
    return side, tuple(slices)


def _chains(rects: list[Region], flow_next: dict[str, str]) -> dict[str, str]:
    pointed = set(flow_next.values())
    chains: dict[str, str] = {}
    for region in rects:
        if region.region_id in pointed:
            continue
        cursor: str | None = region.region_id
        seen: set[str] = set()
        while cursor and cursor not in seen:
            seen.add(cursor)
            chains[cursor] = region.region_id
            cursor = flow_next.get(cursor)
    for region in rects:
        chains.setdefault(region.region_id, region.region_id)
    return chains


def _edges(
    rects: list[Region], chains: dict[str, str]
) -> dict[str, tuple[float, float]]:
    grouped: dict[str, list[Region]] = {}
    for region in rects:
        grouped.setdefault(chains[region.region_id], []).append(region)
    return {
        chain_id: (
            min(left_edge(region) for region in members),
            max(_right(region) for region in members),
        )
        for chain_id, members in grouped.items()
    }


def _right_before_display(
    region: Region, chain_right: float, obstacles: list[Region]
) -> float:
    """This member's own right when a side display bites the chain width.

    The chain right is the widest member. A quote beside one member sits
    inside that width, and that member's ink already stopped before it.
    Ink that crosses the quote stops at the quote's left. A short member
    with no display beside it keeps the chain right.
    """
    bite = _display_left(region, chain_right, obstacles)
    if bite is None:
        return chain_right
    own = _right(region)
    if own < bite:
        return min(chain_right, own)
    return min(chain_right, bite)


def _display_left(
    region: Region, chain_right: float, obstacles: list[Region]
) -> float | None:
    """Left edge of a display obstacle on this member's right."""
    y_lo = bottom(region)
    y_hi = top(region)
    own_left = left_edge(region)
    found: list[float] = []
    for other in obstacles:
        if not _is_side_display(other):
            continue
        if bottom(other) > y_hi or top(other) < y_lo:
            continue
        other_left = left_edge(other)
        if other_left <= own_left + 1.0 or other_left >= chain_right - 0.5:
            continue
        found.append(other_left)
    if not found:
        return None
    return min(found)


def _is_side_display(region: Region) -> bool:
    """Narrow column whose leading is display, not body."""
    lines = region.lines
    if len(lines) < _DISPLAY_LINES:
        return False
    width = max(line.x1 for line in lines) - min(line.x0 for line in lines)
    if not _DISPLAY_MIN_WIDTH <= width <= _DISPLAY_MAX_WIDTH:
        return False
    ys = sorted(float(line.y0) for line in lines)
    steps = [ys[index + 1] - ys[index] for index in range(len(ys) - 1)]
    if not steps:
        return False
    return float(statistics.median(steps)) >= _DISPLAY_PITCH


def _right(region: Region) -> float:
    return max(line.x1 for line in region.lines)
