"""Grant or refuse a named contour, then write its line edges.

The base strategy is already frozen. This stage is the only one that
may grant a named fill. A protected role, a closed gate, a base
conflict, or a below-confidence preserve is refused here and is not
claimed. An eligible body that no paradigm claims keeps its scanned
edges when those edges are a contour. A rectangle stays the union.
Typesetting reads the grant. It does not call claim again.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from babeldoc.format.pdf.document_il.utils.layout_plan.geometry import geometry_eligible
from babeldoc.format.pdf.document_il.utils.layout_plan.measure import measure_region
from babeldoc.format.pdf.document_il.utils.layout_plan.model import ContourLevel
from babeldoc.format.pdf.document_il.utils.layout_plan.model import LayoutFacts
from babeldoc.format.pdf.document_il.utils.layout_plan.model import LayoutPlan
from babeldoc.format.pdf.document_il.utils.layout_plan.model import LineBox
from babeldoc.format.pdf.document_il.utils.layout_plan.model import LineEdgeLink
from babeldoc.format.pdf.document_il.utils.layout_plan.model import Region
from babeldoc.format.pdf.document_il.utils.layout_plan.model import RegionDecision
from babeldoc.format.pdf.document_il.utils.layout_plan.model import SharedContour
from babeldoc.format.pdf.document_il.utils.layout_plan.model import edge_digest
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms import load_catalog
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.contract import (
    BlockEdges,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.contract import (
    Paradigm,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.contract import (
    one_direction,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.contract import pick
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.contract import (
    stand_down,
)

# The catalog objects have no version field. Grants record this stamp.
_CATALOG_VERSION = "1"
_BASE_CONFLICTS = frozenset({"list_and_shaped", "conflict_tie"})
# A region in one of these states does not join a shared contour.
_PAIR_BLOCK = frozenset({"refused", "conflict"})


def with_line_edge_links(
    facts: LayoutFacts,
    plan: LayoutPlan,
    *,
    catalog: Sequence[Paradigm] | None = None,
) -> LayoutPlan:
    """Stamp each decision, then attach edges only for a granted fill."""
    if plan.input_gate != "single_page":
        stamped = tuple(
            _stamp_refused(decision, plan.input_gate) for decision in plan.decisions
        )
        return replace(
            plan,
            decisions=stamped,
            line_edge_links=(),
            shared_contours=(),
        )
    by_region = {region.region_id: region for region in facts.regions}
    pending = [_pending(decision, by_region) for decision in plan.decisions]
    items: tuple[Paradigm, ...] = ()
    if any(reason is None for _decision, _region, reason in pending):
        items = tuple(load_catalog() if catalog is None else catalog)
    stamped_list: list[RegionDecision] = []
    links: list[LineEdgeLink] = []
    for decision, region, reason in pending:
        if reason is not None:
            stamped_list.append(_stamp_refused(decision, reason))
            continue
        chosen, link = _choice_for_region(region, decision, items)
        stamped_list.append(chosen)
        if link is not None:
            links.append(link)
    stamped = tuple(stamped_list)
    return replace(
        plan,
        decisions=stamped,
        line_edge_links=tuple(links),
        shared_contours=_shared_contours(facts, stamped, items, links),
    )


def _pending(
    decision: RegionDecision, by_region: dict[str, Region]
) -> tuple[RegionDecision, Region | None, str | None]:
    region = by_region.get(decision.region_id)
    return decision, region, _refuse_reason(decision, region)


def line_edges_on(page) -> dict[str, LineEdgeLink]:
    """Links whose frozen decision granted a fill.

    An unstamped decision, or a plan with no decisions, still exposes
    its links. A scanned frame does too. A stamped refusal, conflict,
    or recorded claim does not.
    """
    plan = getattr(page, "layout_plan", None)
    if plan is None:
        return {}
    decisions = {
        decision.region_id: decision
        for decision in (getattr(plan, "decisions", ()) or ())
    }
    found: dict[str, LineEdgeLink] = {}
    for link in getattr(plan, "line_edge_links", ()) or ():
        if not link.edges or _link_hidden(decisions.get(link.region_id)):
            continue
        found[link.region_id] = link
    return found


def _link_hidden(decision: RegionDecision | None) -> bool:
    if decision is None:
        return False
    status = decision.contour_status
    return bool(status) and status not in {"matched", "frame"}


def line_edges_for(page, paragraph) -> LineEdgeLink | None:
    """The frozen link for this paragraph, or None."""
    if page is None or paragraph is None:
        return None
    region_id = getattr(paragraph, "layout_region_id", None)
    if not region_id:
        return None
    return line_edges_on(page).get(region_id)


def line_edge_ids(page) -> set[str]:
    """Region ids the legacy pass must not move."""
    return set(line_edges_on(page))


def interval_for_line_edges(
    link: LineEdgeLink,
    line_idx: int,
    y_bottom: float | None = None,
    y_top: float | None = None,
) -> tuple[float, float] | None:
    """Left and right for the Chinese line that occupies this height.

    Sentence flow returns the outer frame and ignores the height.
    Edge flow uses the sample under the baseline. The Chinese line
    index is not an English width: the same height answers the same
    interval for every index. A band that covers samples with no
    common interval is unplaceable. Past the last sample the last
    English edge is not reused.
    """
    edges = getattr(link, "edges", None)
    if not edges:
        return (0.0, 0.0)
    if getattr(link, "flow", "edge") == "sentence":
        left = min(float(edge[0]) for edge in edges)
        right = max(float(edge[1]) for edge in edges)
        return (left, right)
    if y_bottom is None or y_top is None or not isinstance(line_idx, int):
        return None
    levels = tuple(getattr(link, "levels", ()) or ())
    if not levels:
        return None
    return _interval_on_levels(levels, float(y_bottom), float(y_top))


def _interval_on_levels(
    levels: Sequence[ContourLevel],
    y_bottom: float,
    y_top: float,
) -> tuple[float, float] | None:
    """The sample under the baseline.

    A line that also clips the next sample keeps the sample its
    baseline sits on. Crossing two samples that share no x is
    unplaceable, so the line is not given the wider of the two.
    """
    samples = sorted(levels, key=lambda item: item.top, reverse=True)
    if y_bottom > y_top:
        y_bottom, y_top = y_top, y_bottom
    pitch = _pitch([level.top for level in samples])
    slabs: list[tuple[ContourLevel, float]] = []
    for index, level in enumerate(samples):
        below = samples[index + 1].top if index + 1 < len(samples) else level.top - pitch
        if level.top >= y_bottom and below <= y_top:
            slabs.append((level, below))
    if not slabs:
        return None
    left = max(level.left for level, _below in slabs)
    right = min(level.right for level, _below in slabs)
    if right - left < 1.0:
        return None
    host = slabs[0][0]
    for level, below in slabs:
        if below <= y_bottom <= level.top:
            host = level
            break
    if host.right - host.left < 1.0:
        return None
    return (host.left, host.right)


def _pitch(tops: Sequence[float]) -> float:
    ordered = sorted(tops, reverse=True)
    steps = sorted(
        ordered[index] - ordered[index + 1]
        for index in range(len(ordered) - 1)
        if ordered[index] > ordered[index + 1]
    )
    if not steps:
        return 0.0
    return steps[len(steps) // 2]


def lower_edge_span(
    edges: Sequence[tuple[float, float]],
) -> tuple[float, float] | None:
    """X span of the lower lines.

    The union box starts at the first line. A side quote can cross that
    first line and still miss every line that sits lower. Downward growth
    uses this span, so the quote does not stop those lines.
    """
    if not edges:
        return None
    lower = edges[len(edges) // 2 :]
    return (
        min(edge[0] for edge in lower),
        max(edge[1] for edge in lower),
    )


def covers_lower_span(
    zone_x: float,
    zone_x2: float,
    left: float,
    right: float,
) -> bool:
    """True when a zone lies across the lower lines, not beside them.

    A side quote bites one edge. A zone that leaves at most 8pt of the
    span uncovered is the column itself. Downward growth keeps the
    paragraph under those lines and ignores that zone.
    """
    span = right - left
    if span <= 1.0:
        return False
    overlap = min(zone_x2, right) - max(zone_x, left)
    return overlap >= span - 8.0


def contour_span(link, y: float, line_h: float) -> tuple[float, float] | None:
    """Width across this line when the contour has samples.

    The paragraph box is the union of the contour, so it reaches a
    side quote even when the line at this height stops short of it.
    """
    levels = getattr(link, "levels", None) if link is not None else None
    if not levels:
        return None
    step = max(float(line_h), 1.0)
    return interval_for_line_edges(link, 0, float(y), float(y) + step)


def _seat_on_contour(box, link) -> None:
    """Put a box that missed its contour back on the scanned lines.

    A display band can drop the whole rectangle under a quote. The
    contour is still the scanned tops. A box that already meets those
    tops stays, including one whose top sits below the first line.
    Samples without a height do not invent one.
    """
    levels = tuple(getattr(link, "levels", ()) or ())
    if not levels:
        return
    current_top = getattr(box, "y2", None)
    current_bottom = getattr(box, "y", None)
    if current_top is None or current_bottom is None:
        return
    tops = [float(level.top) for level in levels]
    high = max(tops)
    low = min(tops)
    pitch = _pitch(tops)
    if pitch <= 0.0:
        return
    floor = low - pitch
    if float(current_bottom) < high and float(current_top) > floor:
        # Headroom above the first sample puts the opening line off the
        # contour, and the place loop then paints nothing. Edge flow
        # starts on that sample. Sentence flow keeps a taller box.
        if (
            getattr(link, "flow", "edge") != "sentence"
            and float(current_top) > high
        ):
            box.y2 = high
        return
    box.y2 = high
    box.y = floor


def raise_sentence_boxes(page) -> None:
    """Lift a sentence-flow box up to the first scanned line.

    The scale search reads the box before render and only searches
    downward afterward. A short top locks a small size. The bottom
    stays where it is, so the next paragraph is not pushed.
    """
    links = line_edges_on(page)
    if not links:
        return
    for paragraph in getattr(page, "pdf_paragraph", None) or []:
        link = links.get(getattr(paragraph, "layout_region_id", None))
        if link is None or getattr(link, "flow", "edge") != "sentence":
            continue
        box = getattr(paragraph, "box", None)
        if box is None:
            continue
        tops = [float(level.top) for level in (getattr(link, "levels", ()) or ())]
        current = getattr(box, "y2", None)
        if tops and current is not None and float(current) < max(tops):
            box.y2 = max(tops)


def assign_line_edge_boxes(page) -> None:
    """Set the paragraph box to the union of its scanned line edges.

    Call this before render. The last line still starts at its own left.
    Indent is cleared so the first line starts on the scanned edge.
    """
    links = line_edges_on(page)
    if not links:
        return
    for paragraph in getattr(page, "pdf_paragraph", None) or []:
        link = links.get(getattr(paragraph, "layout_region_id", None))
        if link is None or not link.edges:
            continue
        box = getattr(paragraph, "box", None)
        if box is None:
            continue
        box.x = min(edge[0] for edge in link.edges)
        box.x2 = max(edge[1] for edge in link.edges)
        paragraph.alignment = link.alignment
        paragraph.first_line_indent = 0
        _seat_on_contour(box, link)
    raise_sentence_boxes(page)


def link_for_lines(
    lines: Sequence[Sequence[float]],
) -> LineEdgeLink | None:
    """The fill a matched paradigm writes for these source lines.

    Plan-time helper. Typesetting does not call this. No match, a
    conflict, or a claim without a fill returns nothing.
    """
    contour = shared_contour_for(lines)
    if contour is None:
        return None
    return LineEdgeLink(
        "lines",
        contour.edges,
        contour.alignment,
        contour.flow,
        contour.levels,
    )


def shared_contour_for(
    lines: Sequence[Sequence[float]],
    catalog: Sequence[Paradigm] | None = None,
) -> SharedContour | None:
    """Freeze the fill for these source x pairs.

    Y is the same synthetic step ``link_for_lines`` used, so a contour
    stored here matches a typeset lookup of the same x pairs.
    """
    if len(lines) < 2:
        return None
    boxes = tuple(
        LineBox(float(line[0]), float(line[1]), 1000.0 - index * 15.0)
        for index, line in enumerate(lines)
    )
    region = Region(
        region_id="lines",
        page_index=0,
        source_order=0,
        role=None,
        lines=boxes,
    )
    items = tuple(load_catalog() if catalog is None else catalog)
    status, name, residual, edges, chosen = _evaluate(region, items)
    if status != "matched" or chosen is None or not edges or residual is None:
        return None
    return SharedContour(
        digest=edge_digest(lines),
        edges=edges,
        alignment=chosen.alignment,
        flow=chosen.flow,
        plugin=chosen.name,
        version=_CATALOG_VERSION,
        residual=float(residual),
        threshold=float(chosen.threshold),
        levels=_levels_for(edges, boxes),
    )


def _refuse_reason(decision: RegionDecision, region: Region | None) -> str | None:
    """Why this region must not be claimed. None means claim may run."""
    if region is None:
        return "missing_region"
    if not geometry_eligible(region):
        return "protected_role"
    if decision.fallback in _BASE_CONFLICTS:
        return decision.fallback
    if decision.base_strategy == "preserve" and _rejected_for(
        decision, "below_confidence"
    ):
        return "below_confidence"
    return None


def _rejected_for(decision: RegionDecision, reason: str) -> bool:
    return any(item.reason == reason for item in decision.rejected)


def _choice_for_region(
    region: Region | None,
    decision: RegionDecision,
    items: Sequence[Paradigm],
) -> tuple[RegionDecision, LineEdgeLink | None]:
    if region is None or not region.lines:
        return _stamp_unmatched(decision, None), None
    status, name, residual, edges, chosen = _evaluate(region, items)
    if status == "conflict":
        claims = _claims_under(region, items)
        return _stamp_conflict(decision, residual, claims), None
    if status != "matched" or chosen is None:
        link = _scanned_link(region)
        if link is not None:
            return _stamp_frame(decision), link
        return _stamp_unmatched(decision, residual), None
    if not edges:
        return _stamp_recorded(decision, name, residual, chosen.threshold), None
    link = LineEdgeLink(
        region.region_id,
        edges,
        chosen.alignment,
        chosen.flow,
        _levels_for(edges, region.lines),
    )
    return _stamp_matched(decision, chosen, residual), link


def _evaluate(
    region: Region, items: Sequence[Paradigm]
) -> tuple[str, str, float | None, tuple[tuple[float, ...], ...], Paradigm | None]:
    recorded = [
        [float(line.x0), float(line.x1), float(line.y0)] for line in region.lines
    ]
    results = stand_down(
        tuple(
            (item.name, item.claim(_edges(region), recorded), item.threshold)
            for item in items
        )
    )
    status, name, residual = pick(results)
    chosen = next((item for item in items if item.name == name), None)
    if status != "matched" or chosen is None or not callable(chosen.fill):
        return status, name, residual, (), chosen if status == "matched" else None
    raw = chosen.fill(recorded)
    if not raw:
        return status, name, residual, (), chosen
    edges = tuple(tuple(float(value) for value in edge) for edge in raw)
    return status, name, residual, edges, chosen


def _claims_under(region: Region, items: Sequence[Paradigm]) -> tuple[str, ...]:
    """Names still under their own threshold after founding stand-down."""
    recorded = [
        [float(line.x0), float(line.x1), float(line.y0)] for line in region.lines
    ]
    stood = stand_down(
        tuple(
            (item.name, item.claim(_edges(region), recorded), item.threshold)
            for item in items
        )
    )
    names = [
        name
        for name, residual, threshold in stood
        if _under(residual, threshold) and name
    ]
    return tuple(sorted(set(names)))


def _under(residual: float | None, threshold: float) -> bool:
    return residual is not None and residual < threshold


def _stamp_refused(decision: RegionDecision, reason: str) -> RegionDecision:
    return replace(
        decision,
        contour_plugin=None,
        contour_version=None,
        contour_residual=None,
        contour_threshold=None,
        contour_status="refused",
        contour_reason=reason,
        contour_claims=(),
    )


def _stamp_matched(
    decision: RegionDecision, chosen: Paradigm, residual: float | None
) -> RegionDecision:
    return replace(
        decision,
        contour_plugin=chosen.name,
        contour_version=_CATALOG_VERSION,
        contour_residual=None if residual is None else float(residual),
        contour_threshold=float(chosen.threshold),
        contour_status="matched",
        contour_reason=None,
        contour_claims=(),
    )


def _stamp_recorded(
    decision: RegionDecision,
    name: str,
    residual: float | None,
    threshold: float | None,
) -> RegionDecision:
    return replace(
        decision,
        contour_plugin=name,
        contour_version=_CATALOG_VERSION,
        contour_residual=None if residual is None else float(residual),
        contour_threshold=None if threshold is None else float(threshold),
        contour_status="recorded",
        contour_reason="no_fill",
        contour_claims=(),
    )


def _stamp_conflict(
    decision: RegionDecision, residual: float | None, claims: tuple[str, ...]
) -> RegionDecision:
    return replace(
        decision,
        contour_plugin=None,
        contour_version=None,
        contour_residual=None if residual is None else float(residual),
        contour_threshold=None,
        contour_status="conflict",
        contour_reason="contour_conflict",
        contour_claims=claims,
    )


def _stamp_unmatched(
    decision: RegionDecision, residual: float | None
) -> RegionDecision:
    return replace(
        decision,
        contour_plugin=None,
        contour_version=None,
        contour_residual=None if residual is None else float(residual),
        contour_threshold=None,
        contour_status="unmatched",
        contour_reason=None,
        contour_claims=(),
    )


def _stamp_frame(decision: RegionDecision) -> RegionDecision:
    """The scanned contour is the frame. No paradigm name is attached."""
    return replace(
        decision,
        contour_plugin=None,
        contour_version=None,
        contour_residual=None,
        contour_threshold=None,
        contour_status="frame",
        contour_reason=None,
        contour_claims=(),
    )


def _scanned_link(region: Region) -> LineEdgeLink | None:
    """Measured edges, when they are a contour and no paradigm wrote one.

    A rectangle has nothing to keep: the union is that frame. A short
    last line is not a contour. The walk is the pin's 12pt.
    """
    if len(region.lines) < 4:
        return None
    edges = tuple((float(line.x0), float(line.x1)) for line in region.lines)
    if not _contour(edges):
        return None
    return LineEdgeLink(
        region.region_id,
        edges,
        "left",
        "edge",
        _levels_for(edges, region.lines),
    )


def _contour(edges: tuple[tuple[float, float], ...]) -> bool:
    body = _without_short_tail(list(edges))
    if len(body) < 4:
        return False
    lefts = [edge[0] for edge in body]
    rights = [edge[1] for edge in body]
    left_walk = max(lefts) - min(lefts) >= 12.0 and one_direction(lefts)
    right_walk = max(rights) - min(rights) >= 12.0 and one_direction(rights)
    return left_walk or right_walk


def _without_short_tail(
    spans: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    """Drop a short last line. Same 24pt inset and 8pt wall as the pin."""
    kept = list(spans)
    dropped = 0
    while len(kept) >= 3 and dropped < 2:
        last = kept[-1]
        previous = kept[-2]
        right_inset = previous[1] - last[1]
        left_out = previous[0] - last[0]
        if right_inset >= 24.0 and left_out <= 8.0:
            kept.pop()
            dropped += 1
            continue
        break
    return kept


def _shared_contours(
    facts: LayoutFacts,
    decisions: tuple[RegionDecision, ...],
    items: Sequence[Paradigm],
    links: Sequence[LineEdgeLink],
) -> tuple[SharedContour, ...]:
    """Own grants, then a joined contour for an adjacent eligible pair."""
    by_decision = {decision.region_id: decision for decision in decisions}
    found: list[SharedContour] = []
    seen: set[str] = set()
    for link in links:
        decision = by_decision.get(link.region_id)
        region = _region(facts, link.region_id)
        if decision is None or region is None or decision.contour_status != "matched":
            continue
        if decision.contour_plugin is None or decision.contour_residual is None:
            continue
        if decision.contour_threshold is None:
            continue
        contour = _own_contour(region, link, decision)
        _keep(found, seen, contour)
    if items:
        _keep_pairs(facts, by_decision, items, found, seen)
    return tuple(found)


def _own_contour(
    region: Region, link: LineEdgeLink, decision: RegionDecision
) -> SharedContour:
    return SharedContour(
        digest=edge_digest([(line.x0, line.x1) for line in region.lines]),
        edges=link.edges,
        alignment=link.alignment,
        flow=link.flow,
        plugin=decision.contour_plugin or "",
        version=decision.contour_version or _CATALOG_VERSION,
        residual=float(decision.contour_residual or 0.0),
        threshold=float(decision.contour_threshold or 0.0),
        levels=link.levels,
    )


def _keep_pairs(
    facts: LayoutFacts,
    by_decision: dict[str, RegionDecision],
    items: Sequence[Paradigm],
    found: list[SharedContour],
    seen: set[str],
) -> None:
    by_region = {region.region_id: region for region in facts.regions}
    for region in facts.regions:
        lower = by_region.get(region.below_id) if region.below_id else None
        if lower is None or _blocks_pair(by_decision, region, lower):
            continue
        lines = [(line.x0, line.x1) for line in region.lines]
        lines.extend((line.x0, line.x1) for line in lower.lines)
        contour = shared_contour_for(lines, items)
        real = (*region.lines, *lower.lines)
        _keep(found, seen, _retarget_levels(contour, real))


def _blocks_pair(
    by_decision: dict[str, RegionDecision], upper: Region, lower: Region
) -> bool:
    return _blocked(by_decision.get(upper.region_id)) or _blocked(
        by_decision.get(lower.region_id)
    )


def _blocked(decision: RegionDecision | None) -> bool:
    if decision is None:
        return True
    return decision.contour_status in _PAIR_BLOCK


def _keep(
    found: list[SharedContour], seen: set[str], contour: SharedContour | None
) -> None:
    if contour is None or contour.digest in seen:
        return
    seen.add(contour.digest)
    found.append(contour)


def _region(facts: LayoutFacts, region_id: str) -> Region | None:
    for region in facts.regions:
        if region.region_id == region_id:
            return region
    return None


def _retarget_levels(contour: SharedContour | None, lines) -> SharedContour | None:
    """Store page y on a pair contour.

    The claim itself still runs on the synthetic step ``shared_contour_for``
    uses, so the digest stays stable. The samples typesetting reads are
    the source lines. A fill edge lines up with that source prefix. A
    short tail the fill omitted gets no sample. An edge that cannot be
    lined up keeps no page height, so a Chinese line there is unplaceable.
    """
    if contour is None:
        return None
    if not lines or len(contour.edges) > len(lines):
        return replace(contour, levels=())
    return replace(contour, levels=_levels_for(contour.edges, lines))


def _levels_for(edges, source) -> tuple[ContourLevel, ...]:
    """One sample per fill edge, using the source line's top.

    Wired fills write one edge per source line, top line first, and may
    omit a short tail. ``observed`` means the edge is that line's ink.
    ``available`` means the fill moved the ink to space it measured on
    these lines. Nothing here invents a photo edge. The label does not
    grant or refuse a paradigm.
    """
    if not edges or not source or len(edges) > len(source):
        return ()
    built: list[ContourLevel] = []
    for index, edge in enumerate(edges):
        left = float(edge[0])
        right = float(edge[1])
        sx0, sx1, top = _xy(source[index])
        kind = "observed" if left == sx0 and right == sx1 else "available"
        built.append(ContourLevel(left, right, top, kind))
    return tuple(built)


def _xy(line) -> tuple[float, float, float]:
    if hasattr(line, "x0"):
        return float(line.x0), float(line.x1), float(line.y0)
    return float(line[0]), float(line[1]), float(line[2])


def _edges(region: Region) -> BlockEdges:
    measured = measure_region(region)
    return BlockEdges(
        full_count=measured.full_count,
        left_range=measured.left_range,
        right_range=measured.right_range,
        left_monotone=measured.left_monotone,
        right_monotone=measured.right_monotone,
        marker=measured.marker,
    )
