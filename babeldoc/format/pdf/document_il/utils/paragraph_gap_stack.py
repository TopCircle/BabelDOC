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
from babeldoc.format.pdf.document_il.utils.rect_flow_stack import shift_paragraph


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
