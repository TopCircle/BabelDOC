"""Place shaped pockets from the frozen figure gap.

Strategy comes only from ``consume_layout_plan``. The line width is the
gap stored on the pocket link. This module does not read English line
widths, and it does not guess which side is free.
"""

from __future__ import annotations

from babeldoc.format.pdf.document_il.utils.layout_plan.consume import (
    consume_layout_plan,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.model import PocketLink
from babeldoc.format.pdf.document_il.utils.rect_flow_stack import BODY_PARAGRAPH_GAP
from babeldoc.format.pdf.document_il.utils.rect_flow_stack import _line_break_dy
from babeldoc.format.pdf.document_il.utils.rect_flow_stack import _line_chars
from babeldoc.format.pdf.document_il.utils.rect_flow_stack import _link_chains
from babeldoc.format.pdf.document_il.utils.rect_flow_stack import _rect_links
from babeldoc.format.pdf.document_il.utils.rect_flow_stack import ink_span
from babeldoc.format.pdf.document_il.utils.rect_flow_stack import shift_paragraph
from babeldoc.format.pdf.document_il.utils.region_skip import is_chrome_paragraph

# Same horizontal overlap the column neighbor already uses.
_X_OVERLAP = 0.35
# How far below a line with no edge of its own the curve may already be rising.
_INK_LOOK = 8.0


def pocket_links_on(page) -> dict[str, PocketLink]:
    """Pocket links whose frozen strategy is still shaped_pocket."""
    plan = getattr(page, "layout_plan", None)
    if plan is None:
        return {}
    found: dict[str, PocketLink] = {}
    for link in getattr(plan, "pocket_links", ()) or ():
        seen = consume_layout_plan(plan, link.region_id)
        if seen.base_strategy != "shaped_pocket":
            continue
        found[link.region_id] = link
    return found


def pocket_for(page, paragraph) -> PocketLink | None:
    """The frozen link for this paragraph, or None."""
    if page is None or paragraph is None:
        return None
    region_id = getattr(paragraph, "layout_region_id", None)
    if not region_id:
        return None
    return pocket_links_on(page).get(region_id)


def interval_for_pocket(
    link: PocketLink,
    line_idx: int,
    y_bottom: float | None = None,
    y_top: float | None = None,
) -> tuple[float, float]:
    """``(x0, x1)`` of one Chinese line.

    With a height, the width is the figure edge that meets that line,
    held short of the ink. A line with no edge looks a short way below,
    where a rising curve starts. Further than that, the width is the
    opening, not the English line's own gap. A line past the last stored
    gap keeps the last gap.
    """
    width = _width_for(link, line_idx, y_bottom, y_top)
    if link.free_side == "left":
        return (link.pin_edge - width, link.pin_edge)
    return (link.pin_edge, link.pin_edge + width)


def _edges_near(link: PocketLink, lo: float, hi: float) -> list[float]:
    """Figure edges that meet ``[lo, hi]`` on the body side of the pin."""
    edges = [
        edge
        for bottom, top, edge in link.slices
        if top >= lo and bottom <= hi
    ]
    if link.free_side == "right":
        return [edge for edge in edges if edge > link.pin_edge + 1.0]
    return [edge for edge in edges if edge < link.pin_edge - 1.0]


def _width_for(
    link: PocketLink,
    line_idx: int,
    y_bottom: float | None,
    y_top: float | None,
) -> float:
    if (
        y_bottom is not None
        and y_top is not None
        and link.slices
        and link.opening > 1.0
    ):
        lo, hi = (y_bottom, y_top) if y_bottom <= y_top else (y_top, y_bottom)
        edges = _edges_near(link, lo, hi)
        # A line that already meets the figure uses that edge. The tighter
        # contour below it belongs to the next line. Look down only when
        # this line has no edge, where a rising curve is about to enter.
        if not edges:
            edges = _edges_near(link, lo - _INK_LOOK, lo)
        if edges:
            # The inset is the white measured on this page, stored on the link.
            gap = link.edge_gap
            if link.free_side == "right":
                return max(0.0, min(edges) - link.pin_edge - gap)
            return max(0.0, link.pin_edge - max(edges) - gap)
        return link.opening
    widths = link.line_widths
    if not widths:
        return 0.0
    idx = line_idx if 0 <= line_idx < len(widths) else len(widths) - 1
    return widths[idx]


def align_frame_line(units, frame_right: float) -> None:
    """Spread a line so its right edge meets the frame.

    The frame was already scanned. Characters were filled left to right.
    This is the align step: the pin stays, the last glyph meets the frame.
    One glyph cannot span the frame. A line already on the edge stays.
    Punctuation is a glyph, so it meets the frame and does not hang past it.
    """
    glyphs = [
        unit
        for unit in units
        if not getattr(unit, "is_space", False)
        and getattr(unit, "box", None) is not None
        and unit.box.x is not None
        and unit.box.x2 is not None
    ]
    glyphs.sort(key=lambda unit: float(unit.box.x))
    if len(glyphs) < 2:
        return
    slack = float(frame_right) - float(glyphs[-1].box.x2)
    if slack <= 0.5:
        return
    step = slack / (len(glyphs) - 1)
    ordered = sorted(
        (
            unit
            for unit in units
            if getattr(unit, "box", None) is not None and unit.box.x is not None
        ),
        key=lambda unit: float(unit.box.x),
    )
    running = 0.0
    glyph_index = 0
    for unit in ordered:
        if glyph_index < len(glyphs) and unit is glyphs[glyph_index]:
            running = glyph_index * step
            glyph_index += 1
        unit.shift_x(running)


def assign_shaped_boxes(page) -> None:
    """Set each frozen pocket box to the gap beside the figure.

    Call this before render. The pin is the frozen ``free_side``.
    ``left`` means the right edge is pinned. ``right`` means the left edge
    is pinned.
    """
    links = pocket_links_on(page)
    if not links:
        return
    for paragraph in getattr(page, "pdf_paragraph", None) or []:
        link = links.get(getattr(paragraph, "layout_region_id", None))
        if link is None or not link.line_widths:
            continue
        box = getattr(paragraph, "box", None)
        if box is None:
            continue
        widest = max(link.line_widths)
        if link.opening > widest:
            widest = link.opening
        if link.free_side == "left":
            box.x2 = link.pin_edge
            box.x = link.pin_edge - widest
            paragraph.alignment = "right"
        else:
            box.x = link.pin_edge
            box.x2 = link.pin_edge + widest
            paragraph.alignment = "left"
        paragraph.first_line_indent = 0
        metrics = getattr(paragraph, "reference_metrics", None)
        if metrics is None:
            continue
        metrics.per_line_widths = list(link.line_widths)


def pack_shaped_pockets(page, paragraph_gap: float = BODY_PARAGRAPH_GAP) -> None:
    """After render, close the space under a pocket and separate overlaps.

    A shorter pocket pulls the rect column below it up. The pull seats that
    column one rendered line step plus its scanned paragraph white under the
    pocket. A column a body-paragraph gap already seated stays there.
    ``paragraph_gap`` fills in when the scan found no extra white.
    When two bodies still share ink, the lower one moves down. A rect chain
    uses that same white. Anything else keeps the ink clearance. Chrome stays
    put. A page with no pocket is left alone.
    """
    pockets = pocket_links_on(page)
    if not pockets:
        return
    rects = _rect_links(page)
    if rects:
        _pull_rect_columns(page, pockets, rects, paragraph_gap)
    _push_overlaps_down(page, paragraph_gap)


def _pull_rect_columns(page, pockets, rects, paragraph_gap: float) -> None:
    from babeldoc.format.pdf.document_il.utils.layout_plan.paragraph_gap import (
        paragraph_gap_ids,
    )

    anchored = paragraph_gap_ids(page)
    by_region = {
        getattr(paragraph, "layout_region_id", None): paragraph
        for paragraph in getattr(page, "pdf_paragraph", None) or []
    }
    pocket_inks = []
    for region_id in pockets:
        paragraph = by_region.get(region_id)
        if paragraph is None:
            continue
        ink = ink_span(paragraph)
        if ink is not None:
            pocket_inks.append((paragraph, ink[0], ink[1]))
    pocket_inks.sort(key=lambda item: item[1])
    chains = _link_chains(rects)
    for paragraph, _top, bottom in pocket_inks:
        _pull_column_up(
            by_region,
            chains,
            pocket_inks,
            paragraph,
            bottom,
            paragraph_gap,
            anchored,
        )


def _pull_column_up(
    by_region, chains, pocket_inks, pocket, pocket_bottom, gap, anchored
) -> None:
    chosen = None
    chosen_top = None
    for chain in chains:
        head = by_region.get(chain[0].region_id)
        if head is None:
            continue
        ink = ink_span(head)
        if ink is None:
            continue
        top = ink[0]
        if top > pocket_bottom + 0.5:
            continue
        if _blocked(pocket_bottom, top, pocket_inks):
            continue
        pocket_box = _box_of(pocket_inks, pocket_bottom)
        if pocket_box is None or not _overlaps_x(pocket_box, getattr(head, "box", None)):
            continue
        if chosen_top is None or top > chosen_top:
            chosen = chain
            chosen_top = top
    if chosen is None or chosen_top is None:
        return
    # The body gap already put this chain under the paragraph above it.
    if any(link.region_id in anchored for link in chosen):
        return
    head = by_region.get(chosen[0].region_id)
    if head is None:
        return
    dy = _line_break_dy(pocket, head, _extra_above(chosen[0], gap))
    if dy <= 0.5:
        return
    for link in chosen:
        paragraph = by_region.get(link.region_id)
        if paragraph is not None:
            shift_paragraph(paragraph, dy)


def _extra_above(link, fallback: float) -> float:
    """Scanned white above this paragraph, or the caller's fallback."""
    if link.paragraph_gap > 0.0:
        return link.paragraph_gap
    return fallback


def _blocked(pocket_bottom, rect_top, pocket_inks) -> bool:
    for _paragraph, top, bottom in pocket_inks:
        if abs(bottom - pocket_bottom) <= 0.5:
            continue
        if bottom < pocket_bottom - 0.5 and top > rect_top:
            return True
    return False


def _box_of(pocket_inks, pocket_bottom):
    for paragraph, _top, bottom in pocket_inks:
        if abs(bottom - pocket_bottom) <= 0.5:
            return getattr(paragraph, "box", None)
    return None


def _overlaps_x(left, right) -> bool:
    if left is None or right is None:
        return False
    if None in (left.x, left.x2, right.x, right.x2):
        return False
    overlap = min(float(left.x2), float(right.x2)) - max(float(left.x), float(right.x))
    narrow = max(1.0, min(float(left.x2) - float(left.x), float(right.x2) - float(right.x)))
    return overlap >= _X_OVERLAP * narrow


def _push_overlaps_down(page, gap: float) -> None:
    """Move a lower body down until it clears the body above it.

    Y grows upward. A negative shift moves down. The shift is the whole
    paragraph. A move that would leave the page is skipped. A rect chain
    keeps the scanned paragraph white. Other overlaps clear by ``gap`` on
    the ink.
    """
    bodies = []
    for paragraph in getattr(page, "pdf_paragraph", None) or []:
        if is_chrome_paragraph(paragraph, page):
            continue
        if _ink_extent(paragraph) is None:
            continue
        bodies.append(paragraph)
    bodies.sort(key=lambda paragraph: _ink_extent(paragraph)[1], reverse=True)
    floor = _crop_floor(page)
    links = _rect_links(page)
    for index, upper in enumerate(bodies):
        for lower in bodies[index + 1 :]:
            if getattr(upper, "xobj_id", None) != getattr(lower, "xobj_id", None):
                continue
            _push_below(upper, lower, gap, floor, links)


def _rendered_lines(paragraph) -> list[tuple[float, float, float, float]]:
    """One ``(x, x2, y, y2)`` per rendered line."""
    raw: list[tuple[float, float, float, float]] = []
    for composition in getattr(paragraph, "pdf_paragraph_composition", None) or []:
        for char in _line_chars(composition):
            box = getattr(char, "box", None)
            if box is None or None in (box.x, box.x2, box.y, box.y2):
                continue
            raw.append((float(box.x), float(box.x2), float(box.y), float(box.y2)))
    if not raw:
        return []
    ordered = sorted(raw, key=lambda item: item[3], reverse=True)
    groups: list[list[tuple[float, float, float, float]]] = [[ordered[0]]]
    for item in ordered[1:]:
        if groups[-1][0][3] - item[3] > 1.5:
            groups.append([item])
        else:
            groups[-1].append(item)
    return [
        (
            min(item[0] for item in group),
            max(item[1] for item in group),
            min(item[2] for item in group),
            max(item[3] for item in group),
        )
        for group in groups
    ]


def _ink_lines_cross(upper, lower) -> bool:
    """True when one line of each paragraph runs through the other.

    The union reaches a side quote when another line is wider. A touch
    under 8pt stays beside the line.
    """
    for left in _rendered_lines(upper):
        for right in _rendered_lines(lower):
            overlap_x = min(left[1], right[1]) - max(left[0], right[0])
            overlap_y = min(left[3], right[3]) - max(left[2], right[2])
            if overlap_x >= 8.0 and overlap_y > 0:
                return True
    return False


def _push_below(upper, lower, gap: float, floor: float | None, links) -> None:
    above = _ink_extent(upper)
    below = _ink_extent(lower)
    if above is None or below is None:
        return
    overlap = min(above[2], below[2]) - max(above[0], below[0])
    if overlap <= 1.0:
        return
    extra = _successor_extra(upper, lower, links, gap)
    if extra is None:
        # A side quote meets this union only because a lower line steps out.
        if (
            _rendered_lines(upper)
            and _rendered_lines(lower)
            and not _ink_lines_cross(upper, lower)
        ):
            return
        lower_top = below[1]
        upper_bottom = above[3]
        if lower_top <= upper_bottom - gap:
            return
        dy = (upper_bottom - gap) - lower_top
    else:
        dy = _line_break_dy(upper, lower, extra)
    if dy >= -0.5:
        return
    if floor is not None and below[3] + dy < floor:
        return
    shift_paragraph(lower, dy)


def _successor_extra(upper, lower, links, fallback: float) -> float | None:
    """Scanned white when ``lower`` is the next rect paragraph, else nothing."""
    upper_link = links.get(getattr(upper, "layout_region_id", None))
    lower_link = links.get(getattr(lower, "layout_region_id", None))
    if upper_link is None or lower_link is None:
        return None
    if upper_link.flow_next_id != getattr(lower, "layout_region_id", None):
        return None
    return _extra_above(lower_link, fallback)


def _ink_extent(paragraph) -> tuple[float, float, float, float] | None:
    """``(x0, top, x1, bottom)`` of the glyphs, else the paragraph box."""
    xs0: list[float] = []
    xs1: list[float] = []
    tops: list[float] = []
    bottoms: list[float] = []
    for composition in getattr(paragraph, "pdf_paragraph_composition", None) or []:
        for char in _line_chars(composition):
            box = getattr(char, "box", None)
            if box is None:
                continue
            if box.x is not None and box.x2 is not None:
                xs0.append(float(box.x))
                xs1.append(float(box.x2))
            if box.y is not None and box.y2 is not None:
                tops.append(float(box.y2))
                bottoms.append(float(box.y))
    box = getattr(paragraph, "box", None)
    if not tops:
        if box is None or box.y is None or box.y2 is None:
            return None
        tops = [float(box.y2)]
        bottoms = [float(box.y)]
    if not xs0:
        if box is None or box.x is None or box.x2 is None:
            return None
        xs0 = [float(box.x)]
        xs1 = [float(box.x2)]
    return min(xs0), max(tops), max(xs1), min(bottoms)


def _crop_floor(page) -> float | None:
    for name in ("cropbox", "mediabox"):
        holder = getattr(page, name, None)
        box = getattr(holder, "box", None) if holder is not None else None
        if box is not None and box.y is not None:
            return float(box.y)
    return None
