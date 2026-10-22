"""Scanned white between neighboring body paragraphs.

The rect chain does not choose these pairs. Two body blocks in one
column get the extra white past one source line step. A list keeps its
own blank line. A title, quote, or other non-body block ends the run.
A pair the column chain already points at stays on that chain. A pocket
stays on the figure, including a stair that has no figure link yet.
"""

from __future__ import annotations

import statistics
from dataclasses import replace

from babeldoc.format.pdf.document_il.utils.layout_plan.geometry import geometry_eligible
from babeldoc.format.pdf.document_il.utils.layout_plan.model import ColumnLink
from babeldoc.format.pdf.document_il.utils.layout_plan.model import LayoutFacts
from babeldoc.format.pdf.document_il.utils.layout_plan.model import LayoutPlan
from babeldoc.format.pdf.document_il.utils.layout_plan.model import ParagraphGapLink
from babeldoc.format.pdf.document_il.utils.layout_plan.model import PocketLink
from babeldoc.format.pdf.document_il.utils.layout_plan.model import Region
from babeldoc.format.pdf.document_il.utils.layout_plan.model import RegionDecision
from babeldoc.format.pdf.document_il.utils.layout_plan.neighbors import blocked
from babeldoc.format.pdf.document_il.utils.layout_plan.neighbors import left_edge
from babeldoc.format.pdf.document_il.utils.layout_plan.neighbors import next_below


def with_paragraph_gap_links(facts: LayoutFacts, plan: LayoutPlan) -> LayoutPlan:
    """Copy the plan and attach one gap per body paragraph that needs a seat."""
    return replace(
        plan,
        paragraph_gap_links=paragraph_gap_links(
            facts,
            plan.decisions,
            plan.column_links,
            plan.pocket_links,
        ),
    )


def paragraph_gap_links(
    facts: LayoutFacts,
    decisions: tuple[RegionDecision, ...],
    column_links: tuple[ColumnLink, ...],
    pocket_links: tuple[PocketLink, ...],
) -> tuple[ParagraphGapLink, ...]:
    """Extra white above each lower body that this module seats."""
    by_decision = {item.region_id: item for item in decisions}
    bodies = [
        region
        for region in facts.regions
        if region.lines and _is_body(region, by_decision)
    ]
    body_ids = {region.region_id for region in bodies}
    obstacles = [
        region
        for region in facts.regions
        if region.lines and region.region_id not in body_ids
    ]
    flow_next = {
        link.region_id: link.flow_next_id
        for link in column_links
        if link.flow_next_id
    }
    pocket_ids = _pocket_ids(decisions, pocket_links)
    rect_ids = {link.region_id for link in column_links}
    links: list[ParagraphGapLink] = []
    for region in bodies:
        below = next_below(region, bodies, left_edge)
        if below is None or blocked(region, below, obstacles, left_edge):
            continue
        if _already_seated(
            region.region_id,
            below.region_id,
            flow_next,
            pocket_ids,
            rect_ids,
        ):
            continue
        links.append(
            ParagraphGapLink(
                region_id=below.region_id,
                above_id=region.region_id,
                paragraph_gap=scanned_paragraph_gap(region.lines, below.lines),
            )
        )
    return tuple(links)


def paragraph_gap_ids(page) -> set[str]:
    """Lower region ids the legacy pass must not move."""
    plan = getattr(page, "layout_plan", None)
    if plan is None:
        return set()
    return {
        link.region_id
        for link in getattr(plan, "paragraph_gap_links", ()) or ()
    }


def scanned_paragraph_gap(upper_lines, lower_lines) -> float:
    """Extra white between two source paragraphs, past one line step.

    ``y0`` is the line top and grows upward. The step inside a paragraph
    is the line pitch. The step across the break, minus that pitch, is
    the paragraph white. A break that is only one line step adds nothing.
    Wrap width does not use this number.
    """
    pitch = _line_pitch(upper_lines) or _line_pitch(lower_lines)
    if pitch <= 0.0 or not upper_lines or not lower_lines:
        return 0.0
    upper_floor = min(float(line.y0) for line in upper_lines)
    lower_ceil = max(float(line.y0) for line in lower_lines)
    extra = (upper_floor - lower_ceil) - pitch
    if extra <= 0.5:
        return 0.0
    return float(extra)


def _is_body(region: Region, by_decision: dict[str, RegionDecision]) -> bool:
    if not geometry_eligible(region):
        return False
    return by_decision[region.region_id].base_strategy != "list"


def _pocket_ids(
    decisions: tuple[RegionDecision, ...],
    pocket_links: tuple[PocketLink, ...],
) -> set[str]:
    """Pockets, including a stair that has no figure link yet."""
    found = {link.region_id for link in pocket_links}
    found.update(
        decision.region_id
        for decision in decisions
        if decision.base_strategy == "shaped_pocket"
    )
    return found


def _already_seated(
    upper_id: str,
    lower_id: str,
    flow_next: dict[str, str],
    pocket_ids: set[str],
    rect_ids: set[str],
) -> bool:
    """True when a column link or a pocket already owns this pair.

    The column chain stores the rect successor on ``flow_next_id``.
    A pocket is not moved. A rect under a pocket stays with the pocket
    pull. A stair with no figure is still a pocket: it has the strategy
    and no link.
    """
    if flow_next.get(upper_id) == lower_id:
        return True
    if lower_id in pocket_ids:
        return True
    return upper_id in pocket_ids and lower_id in rect_ids


def _line_pitch(lines) -> float:
    ys = sorted(float(line.y0) for line in lines)
    steps = [
        ys[index + 1] - ys[index]
        for index in range(len(ys) - 1)
        if ys[index + 1] - ys[index] > 0.5
    ]
    if not steps:
        return 0.0
    return float(statistics.median(steps))
