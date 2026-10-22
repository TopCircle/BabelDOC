"""Frozen gaps for shaped pockets that sit beside a figure.

The taper test still decides the strategy. A stair with no figure keeps
that label and gets no link, so placement does not invent a width from
the English lines. ``free_side`` is read once here and stored on the link.
"""

from __future__ import annotations

import statistics
from dataclasses import replace

from babeldoc.format.pdf.document_il.utils.layout_plan.geometry import free_side
from babeldoc.format.pdf.document_il.utils.layout_plan.model import FigureBox
from babeldoc.format.pdf.document_il.utils.layout_plan.model import LayoutFacts
from babeldoc.format.pdf.document_il.utils.layout_plan.model import LayoutPlan
from babeldoc.format.pdf.document_il.utils.layout_plan.model import PocketLink
from babeldoc.format.pdf.document_il.utils.layout_plan.model import Region
from babeldoc.format.pdf.document_il.utils.layout_plan.model import RegionDecision


def with_pocket_links(facts: LayoutFacts, plan: LayoutPlan) -> LayoutPlan:
    """Copy the plan and attach one link per pocket that meets a figure."""
    return replace(plan, pocket_links=pocket_links(facts, plan.decisions))


def pocket_links(
    facts: LayoutFacts, decisions: tuple[RegionDecision, ...]
) -> tuple[PocketLink, ...]:
    by_decision = {item.region_id: item for item in decisions}
    found: list[PocketLink] = []
    for region in facts.regions:
        decision = by_decision.get(region.region_id)
        if decision is None or decision.base_strategy != "shaped_pocket":
            continue
        if not region.lines:
            continue
        side = free_side(region)
        if side not in {"left", "right"}:
            continue
        widths, pin, opening = _gaps(region, facts.figures, side)
        if widths is None or pin is None or opening is None:
            continue
        slices = _slices(facts.figures, side)
        found.append(
            PocketLink(
                region_id=region.region_id,
                free_side=side,
                pin_edge=pin,
                line_widths=widths,
                opening=opening,
                slices=slices,
                edge_gap=scanned_edge_gap(region.lines, slices, side, pin),
            )
        )
    return tuple(found)


def _gaps(
    region: Region, figures: tuple[FigureBox, ...], side: str
) -> tuple[tuple[float, ...] | None, float | None, float | None]:
    """Gaps from the pinned edge to the figure, top line first.

    A line with no figure at its height uses the block's outer span, which
    is one edge, not that English line's own width. No link is returned
    when no line actually meets a figure. The third value is that outer span.
    """
    ordered = sorted(region.lines, key=lambda line: line.y0, reverse=True)
    if side == "right":
        pin = min(line.x0 for line in ordered)
        opening = max(line.x1 for line in ordered) - pin
    else:
        pin = max(line.x1 for line in ordered)
        opening = pin - min(line.x0 for line in ordered)
    if opening <= 1.0:
        return None, None, None
    beside = False
    widths: list[float] = []
    for line in ordered:
        gap = _gap_at(line.y0, figures, side, pin)
        if gap is None:
            gap = opening
        else:
            beside = True
        if gap <= 1.0:
            return None, None, None
        widths.append(gap)
    if not beside:
        return None, None, None
    return tuple(widths), pin, opening


def _slices(
    figures: tuple[FigureBox, ...], side: str
) -> tuple[tuple[float, float, float], ...]:
    """``(bottom, top, edge)`` for each figure. Y grows upward."""
    found: list[tuple[float, float, float]] = []
    for figure in figures:
        edge = figure.x0 if side == "right" else figure.x1
        found.append((figure.y0, figure.y1, edge))
    return tuple(found)


def scanned_edge_gap(lines, slices, side: str, pin: float) -> float:
    """White the original text left before the figure.

    The paragraph's last line is short on purpose, so it is not the edge.
    The number is the median of the other lines that still leave white.
    A line that already crosses the figure does not invent a gutter.
    """
    if not lines or not slices or side not in {"left", "right"}:
        return 0.0
    ordered = sorted(lines, key=lambda line: float(line.y0))
    body = ordered[1:] if len(ordered) > 1 else ordered
    gaps = _positive_gaps(body, slices, side, pin)
    if not gaps:
        gaps = _positive_gaps(ordered, slices, side, pin)
    if not gaps:
        return 0.0
    return float(statistics.median(gaps))


def _positive_gaps(lines, slices, side: str, pin: float) -> list[float]:
    found: list[float] = []
    for line in lines:
        edge = _slice_edge_at(float(line.y0), slices, side, pin)
        if edge is None:
            continue
        gap = (edge - float(line.x1)) if side == "right" else (float(line.x0) - edge)
        if gap > 0:
            found.append(gap)
    return found


def _slice_edge_at(y: float, slices, side: str, pin: float) -> float | None:
    if side == "right":
        edges = [
            edge
            for bottom, top, edge in slices
            if bottom <= y <= top and edge > pin + 1.0
        ]
        return min(edges) if edges else None
    edges = [
        edge
        for bottom, top, edge in slices
        if bottom <= y <= top and edge < pin - 1.0
    ]
    return max(edges) if edges else None


def _gap_at(
    y: float, figures: tuple[FigureBox, ...], side: str, pin: float
) -> float | None:
    if side == "right":
        edges = [
            figure.x0
            for figure in figures
            if figure.y0 <= y <= figure.y1 and figure.x0 > pin + 1.0
        ]
        if not edges:
            return None
        return min(edges) - pin
    edges = [
        figure.x1
        for figure in figures
        if figure.y0 <= y <= figure.y1 and figure.x1 < pin - 1.0
    ]
    if not edges:
        return None
    return pin - max(edges)
