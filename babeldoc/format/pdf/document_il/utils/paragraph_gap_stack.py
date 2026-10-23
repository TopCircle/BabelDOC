"""Seat body paragraphs that the rect chain does not own.

The distance is the rendered line step plus the scanned extra white.
A rect column under one of these paragraphs moves as a whole, so the
gap inside that column stays the one ``pack_rect_flow`` already set.
"""

from __future__ import annotations

from babeldoc.format.pdf.document_il.utils.layout_plan.model import ParagraphGapLink
from babeldoc.format.pdf.document_il.utils.rect_flow_stack import BODY_PARAGRAPH_GAP
from babeldoc.format.pdf.document_il.utils.rect_flow_stack import _line_break_dy
from babeldoc.format.pdf.document_il.utils.rect_flow_stack import _rect_links
from babeldoc.format.pdf.document_il.utils.rect_flow_stack import ink_lines
from babeldoc.format.pdf.document_il.utils.rect_flow_stack import shift_paragraph


def seat_dropped_headings(page, drops: dict) -> None:
    """A one-line heading keeps its gap when the column under it drops.

    The heading was set on the source line. The column moved down, so
    the same shift puts the heading back on that gap. A line that was
    not sitting on the column stays. A wide bar stays.
    """
    if not drops:
        return
    paragraphs = list(getattr(page, "pdf_paragraph", None) or [])
    moved: set[int] = set()
    for paragraph in paragraphs:
        delta = float(drops.get(id(paragraph), 0.0) or 0.0)
        if delta < 8.0:
            continue
        body = _first_line_span(paragraph)
        if body is None:
            continue
        body_top, body_left, body_right = body
        heading = _heading_on_column(
            paragraphs, paragraph, body_top, body_left, body_right, delta
        )
        if heading is None or id(heading) in moved:
            continue
        shift_paragraph(heading, -delta)
        moved.add(id(heading))


def _first_line_span(paragraph) -> tuple[float, float, float] | None:
    lines = ink_lines(paragraph)
    if not lines:
        return None
    top = lines[0][0]
    xs: list[float] = []
    x2s: list[float] = []
    for composition in getattr(paragraph, "pdf_paragraph_composition", None) or []:
        for char in _chars(composition):
            box = getattr(char, "box", None)
            if box is None or box.y2 is None or box.x is None or box.x2 is None:
                continue
            if abs(float(box.y2) - top) > 4.0:
                continue
            xs.append(float(box.x))
            x2s.append(float(box.x2))
    if not xs:
        return None
    return top, min(xs), max(x2s)


def _chars(composition) -> list:
    from babeldoc.format.pdf.document_il.utils.rect_flow_stack import _line_chars

    return _line_chars(composition)


def _heading_on_column(paragraphs, body, body_top, body_left, body_right, delta):
    best = None
    best_gap = None
    for other in paragraphs:
        if other is body:
            continue
        lines = ink_lines(other)
        if len(lines) != 1:
            continue
        span = _first_line_span(other)
        if span is None:
            continue
        _top, left, right = span
        bottom = lines[0][1]
        if bottom < body_top:
            continue
        gap = bottom - body_top
        if gap > delta + 48.0:
            continue
        if right > body_right + 12.0 or left < body_left - 40.0:
            continue
        if best_gap is None or gap < best_gap:
            best = other
            best_gap = gap
    return best


def pack_body_paragraphs(page) -> None:
    """After render, seat each linked body under the paragraph above it."""
    links = _gap_links(page)
    if not links:
        return
    by_region = {
        getattr(paragraph, "layout_region_id", None): paragraph
        for paragraph in getattr(page, "pdf_paragraph", None) or []
    }
    rects = _rect_links(page)
    for link in _chain_order(links):
        _seat(link, by_region, rects)


def _gap_links(page) -> tuple[ParagraphGapLink, ...]:
    plan = getattr(page, "layout_plan", None)
    if plan is None:
        return ()
    return tuple(getattr(plan, "paragraph_gap_links", ()) or ())


def _seat(link: ParagraphGapLink, by_region, rects) -> None:
    upper = by_region.get(link.above_id)
    lower = by_region.get(link.region_id)
    if upper is None or lower is None:
        return
    extra = link.paragraph_gap if link.paragraph_gap > 0.0 else BODY_PARAGRAPH_GAP
    dy = _line_break_dy(upper, lower, extra)
    _shift_target(link.region_id, lower, dy, by_region, rects)


def _shift_target(region_id, lower, dy, by_region, rects) -> None:
    rect = rects.get(region_id)
    if rect is None:
        shift_paragraph(lower, dy)
        return
    chain_id = rect.column_chain_id
    for other_id, item in rects.items():
        if item.column_chain_id != chain_id:
            continue
        paragraph = by_region.get(other_id)
        if paragraph is not None:
            shift_paragraph(paragraph, dy)


def _chain_order(links: tuple[ParagraphGapLink, ...]) -> list[ParagraphGapLink]:
    """Seat the upper pair before a paragraph that hangs under it."""
    by_above: dict[str, list[ParagraphGapLink]] = {}
    for link in links:
        by_above.setdefault(link.above_id, []).append(link)
    lowers = {link.region_id for link in links}
    ordered: list[ParagraphGapLink] = []
    seen: set[str] = set()
    pending = [link for link in links if link.above_id not in lowers]
    while pending:
        link = pending.pop(0)
        if link.region_id in seen:
            continue
        seen.add(link.region_id)
        ordered.append(link)
        pending.extend(by_above.get(link.region_id, ()))
    ordered.extend(link for link in links if link.region_id not in seen)
    return ordered
