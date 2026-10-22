"""Frozen reading order for list regions.

``above_id`` stays the loose 0.35 overlap. This chain does not read it.
A bullet and a number join when their marker edges already belong to one
column. One line is enough. A title, quote, body, or any other non-list
block on that marker edge ends the chain. A list in another column does not.
"""

from __future__ import annotations

from dataclasses import replace

from babeldoc.format.pdf.document_il.utils.layout_plan.model import LayoutFacts
from babeldoc.format.pdf.document_il.utils.layout_plan.model import LayoutPlan
from babeldoc.format.pdf.document_il.utils.layout_plan.model import ListLink
from babeldoc.format.pdf.document_il.utils.layout_plan.model import Region
from babeldoc.format.pdf.document_il.utils.layout_plan.model import RegionDecision
from babeldoc.format.pdf.document_il.utils.layout_plan.neighbors import blocked
from babeldoc.format.pdf.document_il.utils.layout_plan.neighbors import next_below
from babeldoc.format.pdf.document_il.utils.placement_paradigm import shares_column_left


def with_list_links(facts: LayoutFacts, plan: LayoutPlan) -> LayoutPlan:
    """Copy the plan and attach one link per list region."""
    return replace(plan, list_links=list_links(facts, plan.decisions))


def list_links(
    facts: LayoutFacts, decisions: tuple[RegionDecision, ...]
) -> tuple[ListLink, ...]:
    by_decision = {item.region_id: item for item in decisions}
    items = [
        region
        for region in facts.regions
        if region.lines and by_decision[region.region_id].base_strategy == "list"
    ]
    obstacles = [
        region
        for region in facts.regions
        if region.lines and by_decision[region.region_id].base_strategy != "list"
    ]
    flow_next: dict[str, str] = {}
    for region in items:
        nearest = next_below(region, items, _marker_left)
        if nearest is None or blocked(region, nearest, obstacles, _marker_left):
            continue
        flow_next[region.region_id] = nearest.region_id
    chains = _chains(items, flow_next)
    edges = _edges(items, chains)
    links: list[ListLink] = []
    for region in items:
        chain_id = chains[region.region_id]
        marker, right = edges[chain_id]
        links.append(
            ListLink(
                region_id=region.region_id,
                list_chain_id=chain_id,
                flow_next_id=flow_next.get(region.region_id),
                marker_left=marker,
                column_right=right,
                body_left=_body_left(region),
            )
        )
    return tuple(links)


def _chains(items: list[Region], flow_next: dict[str, str]) -> dict[str, str]:
    pointed = set(flow_next.values())
    chains: dict[str, str] = {}
    for region in items:
        if region.region_id in pointed:
            continue
        cursor: str | None = region.region_id
        seen: set[str] = set()
        while cursor and cursor not in seen:
            seen.add(cursor)
            chains[cursor] = region.region_id
            cursor = flow_next.get(cursor)
    for region in items:
        chains.setdefault(region.region_id, region.region_id)
    return chains


def _edges(
    items: list[Region], chains: dict[str, str]
) -> dict[str, tuple[float, float]]:
    grouped: dict[str, list[Region]] = {}
    for region in items:
        grouped.setdefault(chains[region.region_id], []).append(region)
    return {
        chain_id: (
            min(_marker_left(region) for region in members),
            max(_right(region) for region in members),
        )
        for chain_id, members in grouped.items()
    }


def _marker_left(region: Region) -> float:
    return min(line.x0 for line in region.lines)


def _body_left(region: Region) -> float:
    """Continuation edge. Lines on the marker edge do not count.

    The tolerance is the same column-left check the chain uses. This does
    not choose a strategy and does not invent a second hang width.
    """
    marker = _marker_left(region)
    hung = [
        line.x0
        for line in region.lines
        if not shares_column_left(line.x0, marker)
    ]
    if not hung:
        return marker
    return min(hung)


def _right(region: Region) -> float:
    return max(line.x1 for line in region.lines)
