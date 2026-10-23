"""Place list paragraphs from the frozen item chain.

Strategy comes only from ``consume_layout_plan``. Bullets and numbers
share this path. The existing hang insets wrap lines once alignment is
left. This module does not guess a paradigm, and it does not import the
legacy column reflow.
"""

from __future__ import annotations

from babeldoc.format.pdf.document_il.utils.layout_plan.model import ListLink
from babeldoc.format.pdf.document_il.utils.rect_flow_stack import BODY_PARAGRAPH_GAP
from babeldoc.format.pdf.document_il.utils.rect_flow_stack import ink_lines
from babeldoc.format.pdf.document_il.utils.rect_flow_stack import ink_span
from babeldoc.format.pdf.document_il.utils.rect_flow_stack import line_slots
from babeldoc.format.pdf.document_il.utils.rect_flow_stack import list_links_on
from babeldoc.format.pdf.document_il.utils.rect_flow_stack import pack_offsets
from babeldoc.format.pdf.document_il.utils.rect_flow_stack import shift_paragraph


def assign_list_boxes(page) -> None:
    """Set each frozen list box to the shared marker left and column right.

    Call this before render. Alignment becomes left so the existing hang
    can inset wrap lines. The box stays on the marker. ``body_left`` is
    the frozen continuation edge and is not applied again here, because
    that would indent the marker as well as the wrap.
    """
    links = list_links_on(page)
    if not links:
        return
    for paragraph in getattr(page, "pdf_paragraph", None) or []:
        link = links.get(getattr(paragraph, "layout_region_id", None))
        if link is None:
            continue
        box = getattr(paragraph, "box", None)
        if box is None:
            continue
        box.x = link.marker_left
        box.x2 = link.column_right
        paragraph.alignment = "left"
        metrics = getattr(paragraph, "reference_metrics", None)
        if metrics is None:
            continue
        stored = getattr(metrics, "per_line_widths", None) or []
        count = len(stored) if stored else int(getattr(metrics, "line_count", 0) or 0)
        width = link.column_right - link.marker_left
        metrics.per_line_widths = line_slots(width, count)


def pack_list_items(page, paragraph_gap: float | None = None) -> None:
    """After render, close the hole under a shorter list item.

    The next item's top sits one rendered line below the previous ink.
    That blank line is the list's own leading, not the 3pt body gap.
    Pass ``paragraph_gap`` to use a fixed distance instead.
    The whole item moves. Leading inside it stays as rendered.
    """
    links = list_links_on(page)
    if not links:
        return
    by_region = {}
    for paragraph in getattr(page, "pdf_paragraph", None) or []:
        region_id = getattr(paragraph, "layout_region_id", None)
        if region_id in links:
            by_region[region_id] = paragraph
    for chain in _chains(links):
        spans: list[tuple[str, float, float]] = []
        members = []
        for link in chain:
            paragraph = by_region.get(link.region_id)
            if paragraph is None:
                continue
            ink = ink_span(paragraph)
            if ink is None:
                continue
            top, bottom = ink
            spans.append((link.list_chain_id, top, bottom))
            members.append(paragraph)
        gap = paragraph_gap if paragraph_gap is not None else _blank_line(members)
        for dy, paragraph in zip(pack_offsets(spans, gap), members, strict=True):
            shift_paragraph(paragraph, dy)


def _blank_line(paragraphs) -> float:
    """Distance between consecutive list items.

    When source paragraphs are tightly packed (e.g. a directory / TOC),
    preserve the source gap so items do not expand and overlap later sections.
    Otherwise, leave one empty line between items.
    """
    source_gaps: list[float] = []
    for i in range(len(paragraphs) - 1):
        b1 = getattr(paragraphs[i], "box", None)
        b2 = getattr(paragraphs[i + 1], "box", None)
        if (
            b1 is not None
            and b2 is not None
            and b1.y is not None
            and b2.y2 is not None
        ):
            g = float(b1.y) - float(b2.y2)
            if 0.5 <= g <= 30.0:
                source_gaps.append(g)

    pitches: list[float] = []
    heights: list[float] = []
    for paragraph in paragraphs:
        lines = ink_lines(paragraph)
        tops = [top for top, _bottom in lines]
        for index in range(len(tops) - 1):
            step = tops[index] - tops[index + 1]
            if step > 0.5:
                pitches.append(step)
        for top, bottom in lines:
            height = top - bottom
            if height > 0.5:
                heights.append(height)

    median_h = heights[len(heights) // 2] if heights else 12.0
    if source_gaps:
        source_gaps.sort()
        med_source = source_gaps[len(source_gaps) // 2]
        if med_source < median_h:
            return med_source

    if pitches:
        pitches.sort()
        return pitches[len(pitches) // 2]
    if heights:
        return median_h
    return BODY_PARAGRAPH_GAP


def _chains(links: dict[str, ListLink]) -> list[list[ListLink]]:
    pointed = {link.flow_next_id for link in links.values() if link.flow_next_id}
    chains: list[list[ListLink]] = []
    seen: set[str] = set()
    for link in links.values():
        if link.region_id in pointed:
            continue
        chain: list[ListLink] = []
        cursor: ListLink | None = link
        while cursor is not None and cursor.region_id not in seen:
            seen.add(cursor.region_id)
            chain.append(cursor)
            nxt = cursor.flow_next_id
            cursor = links.get(nxt) if nxt else None
        if chain:
            chains.append(chain)
    for link in links.values():
        if link.region_id not in seen:
            chains.append([link])
    return chains
