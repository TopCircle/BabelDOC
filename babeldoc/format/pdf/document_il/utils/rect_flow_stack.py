"""Place rect_flow paragraphs from the frozen column chain.

Strategy comes only from ``consume_layout_plan``. This module does not
guess a paradigm from role or geometry, and it does not import the
legacy column reflow.

After the plan is frozen, control is:

1. Read the plan. Do not claim, and do not rewrite a decision.
2. For one legacy call, hide planned paragraphs and remember their
   boxes on that page object. The legacy call may move only the
   paragraphs it is given, and it can see those boxes as obstacles.
3. Restore the planned paragraphs and drop the note, including when
   the call raises.
4. A later check reads the same plan. It does not pick another paradigm
   or open the frozen contour.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path

from babeldoc.format.pdf.document_il.utils.layout_plan.compose import build_plan
from babeldoc.format.pdf.document_il.utils.layout_plan.consume import (
    consume_layout_plan,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.corpus import file_fingerprint
from babeldoc.format.pdf.document_il.utils.layout_plan.facts import SourceBlock
from babeldoc.format.pdf.document_il.utils.layout_plan.facts import build_facts
from babeldoc.format.pdf.document_il.utils.layout_plan.gates import input_gate
from babeldoc.format.pdf.document_il.utils.layout_plan.log import emit
from babeldoc.format.pdf.document_il.utils.layout_plan.marker import marker_from_glyph
from babeldoc.format.pdf.document_il.utils.layout_plan.model import ColumnLink
from babeldoc.format.pdf.document_il.utils.layout_plan.model import FigureBox
from babeldoc.format.pdf.document_il.utils.layout_plan.model import LineBox
from babeldoc.format.pdf.document_il.utils.layout_plan.model import ListLink
from babeldoc.format.pdf.document_il.utils.list_marker_repair import LIST_MARKER_RE
from babeldoc.format.pdf.document_il.utils.region_skip import is_chrome_paragraph

logger = logging.getLogger(__name__)

# Ordinary paragraph gap already used when render separates body blocks
# (3pt once a paragraph is at least 36pt tall). Not a classifier cutoff.
BODY_PARAGRAPH_GAP = 3.0

# A bullet formula sits a few points off the CJK baseline. Real line steps
# are the leading, much larger than this. Not a book measurement.
_SAME_LINE_TOP = 4.0

_LABEL_ROLES = frozenset(
    {
        "title",
        "pull_quote",
        "callout",
        "chrome",
        "figure_caption",
        "dropcap",
        "section_header",
        "formula",
        "list",
    }
)


def line_slots(column_width: float, line_count: int) -> list[float]:
    """Every line uses the column measure.

    The English last-line width is not replayed. The existing left-aligned
    breaker then keeps only the paragraph's last line short.
    """
    count = line_count if line_count > 0 else 1
    return [float(column_width)] * count


def pack_offsets(
    spans: list[tuple[str, float, float]],
    gap: float,
) -> list[float]:
    """Y shift for each ``(chain_id, top, bottom)``. Y grows upward.

    The first span of a chain stays put. The next top becomes the previous
    bottom minus ``gap``. A new chain is not pulled across the break.
    Lists use this. Paragraph breaks use ``pack_rect_flow``.
    """
    offsets: list[float] = []
    cursor_chain: str | None = None
    cursor_bottom: float | None = None
    for chain_id, top, bottom in spans:
        if cursor_chain != chain_id or cursor_bottom is None:
            offsets.append(0.0)
            cursor_chain = chain_id
            cursor_bottom = bottom
            continue
        dy = (cursor_bottom - gap) - top
        offsets.append(dy)
        cursor_bottom = bottom + dy
    return offsets


def assign_rect_flow_boxes(page) -> None:
    """Set each frozen rect_flow box to the column's shared left and right.

    Call this before render. Line widths become the column measure so a
    straight column does not replay each English line.
    """
    links = _rect_links(page)
    if not links:
        return
    for paragraph in getattr(page, "pdf_paragraph", None) or []:
        link = links.get(getattr(paragraph, "layout_region_id", None))
        if link is None:
            continue
        box = getattr(paragraph, "box", None)
        if box is None:
            continue
        box.x = link.column_left
        box.x2 = link.column_right
        span = _gap_span(link)
        if link.free_side == "right":
            box.x2 = max(float(box.x2), link.column_left + span)
        elif link.free_side == "left":
            box.x = min(float(box.x), link.column_right - span)
        paragraph.alignment = "left"
        metrics = getattr(paragraph, "reference_metrics", None)
        if metrics is None:
            continue
        stored = getattr(metrics, "per_line_widths", None) or []
        count = len(stored) if stored else int(getattr(metrics, "line_count", 0) or 0)
        width = link.column_right - link.column_left
        metrics.per_line_widths = line_slots(width, count)


def pack_rect_flow(page, paragraph_gap: float | None = None) -> None:
    """After render, seat the next paragraph under the one above.

    The seat is one rendered line step plus the white scanned between those
    two source paragraphs. Pass ``paragraph_gap`` to replace that white for
    every pair. The whole paragraph moves. Leading inside it stays as
    rendered. Wrap width is not this distance.
    """
    links = _rect_links(page)
    if not links:
        return
    by_region = {}
    for paragraph in getattr(page, "pdf_paragraph", None) or []:
        region_id = getattr(paragraph, "layout_region_id", None)
        if region_id in links:
            by_region[region_id] = paragraph
    for chain in _link_chains(links):
        cursor_chain: str | None = None
        cursor_paragraph = None
        for link in chain:
            paragraph = by_region.get(link.region_id)
            if paragraph is None or _ink(paragraph) is None:
                continue
            if cursor_paragraph is None or link.column_chain_id != cursor_chain:
                dy = 0.0
            else:
                dy = _line_break_dy(
                    cursor_paragraph,
                    paragraph,
                    _break_gap(link, paragraph_gap),
                )
            _shift(paragraph, dy)
            cursor_chain = link.column_chain_id
            cursor_paragraph = paragraph


def _break_gap(link: ColumnLink, override: float | None) -> float:
    """Scanned white above this paragraph, or the caller's one distance."""
    if override is not None:
        return override
    if link.paragraph_gap > 0.0:
        return link.paragraph_gap
    return BODY_PARAGRAPH_GAP


def _line_break_dy(upper, lower, extra: float) -> float:
    """Shift that puts one line step, plus ``extra``, between paragraphs.

    The step is the one already used inside the paragraph. ``extra`` is the
    scanned white, or the caller's replacement for it. The whole lower
    paragraph moves together.
    """
    upper_lines = ink_lines(upper)
    lower_lines = ink_lines(lower)
    if not upper_lines or not lower_lines:
        return 0.0
    pitch = _rendered_pitch(upper_lines) or _rendered_pitch(lower_lines)
    lower_top = lower_lines[0][0]
    if pitch <= 0.0:
        upper_bottom = min(bottom for _top, bottom in upper_lines)
        return (upper_bottom - extra) - lower_top
    return (upper_lines[-1][0] - (pitch + extra)) - lower_top


def _rendered_pitch(lines) -> float:
    tops = [top for top, _bottom in lines]
    steps = [
        tops[index] - tops[index + 1]
        for index in range(len(tops) - 1)
        if tops[index] - tops[index + 1] > 0.5
    ]
    if not steps:
        return 0.0
    steps.sort()
    return steps[len(steps) // 2]


def shift_paragraph(paragraph, dy: float) -> None:
    """Move one paragraph and its glyphs. Leading inside it stays put."""
    _shift(paragraph, dy)


def ink_span(paragraph) -> tuple[float, float] | None:
    """Top and bottom of rendered glyphs, else the paragraph box."""
    return _ink(paragraph)


def ink_lines(paragraph) -> list[tuple[float, float]]:
    """Each rendered line as ``(top, bottom)``, highest line first.

    A marker glyph a few points off the text baseline stays on that line.
    Y grows upward.
    """
    raw: list[tuple[float, float]] = []
    for composition in getattr(paragraph, "pdf_paragraph_composition", None) or []:
        for char in _line_chars(composition):
            box = getattr(char, "box", None)
            if box is None or box.y is None or box.y2 is None:
                continue
            raw.append((float(box.y2), float(box.y)))
    if not raw:
        box = getattr(paragraph, "box", None)
        if box is None or box.y is None or box.y2 is None:
            return []
        return [(float(box.y2), float(box.y))]
    raw.sort(key=lambda item: item[0], reverse=True)
    lines: list[tuple[float, float]] = []
    for top, bottom in raw:
        if lines and abs(lines[-1][0] - top) <= _SAME_LINE_TOP:
            prev_top, prev_bottom = lines[-1]
            lines[-1] = (max(prev_top, top), min(prev_bottom, bottom))
            continue
        lines.append((top, bottom))
    return lines


def run_legacy_column_flow(page, flow: Callable) -> None:
    """Run ``flow`` on paragraphs the frozen plan did not mark.

    Rect and list pages still hand the unmarked paragraphs through. A page
    with pocket links hands ``flow`` nothing, so close and settle cannot
    move the text that sits beside the figure. With no such plan, ``flow``
    sees the page unchanged. Mark and yield are not this function.
    """
    if not _planned_ids(page):
        flow(getattr(page, "pdf_paragraph", None))
        return
    with guard_rect_flow_paragraphs(page):
        flow(page.pdf_paragraph)


@contextmanager
def guard_rect_flow_paragraphs(page):
    """Hide planned paragraphs from one legacy list pass.

    A pocket page hides every paragraph. The hidden boxes stay on this
    page until the call ends. Failures restore the page list and do not
    raise, so the legacy pass still sees every paragraph.
    """
    state = _hold(page)
    try:
        yield page
    finally:
        if state is not None:
            _restore(page, state)


def attach_layout_plans(docs, pdf_path=None, log_path=None) -> bool:
    """Freeze one plan per page before the legacy joiner runs.

    ``pdf_path`` lets a photo contribute its ink edge instead of the image
    rectangle. ``log_path`` records each block's scan and match. Returns
    False after clearing a partial attach. The caller then keeps the old
    prepare path.
    """
    if log_path is not None:
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        Path(log_path).write_text("", encoding="utf-8")
    pages = list(getattr(docs, "page", None) or [])
    fingerprint, scope = _document_identity(pdf_path)
    doc = _open_figure_pdf(pdf_path)
    try:
        for page in pages:
            _attach_page(page, doc, log_path, fingerprint, scope)
    except Exception:
        logger.warning("layout plan attach failed", exc_info=True)
        for page in pages:
            _clear_plan(page)
        return False
    finally:
        if doc is not None:
            doc.close()
    return True


def _document_identity(pdf_path) -> tuple[str | None, str]:
    """Hash the file when it exists. Otherwise the page id stays unscoped.

    A missing file does not get a made-up document id. Region ids from
    that attach are not comparable with another document.
    """
    if pdf_path and Path(pdf_path).is_file():
        return file_fingerprint(Path(pdf_path)), "document"
    return None, "unscoped"


def _attach_page(
    page,
    doc=None,
    log_path=None,
    fingerprint: str | None = None,
    identity_scope: str = "unscoped",
) -> None:
    indexed = []
    for paragraph in getattr(page, "pdf_paragraph", None) or []:
        if getattr(paragraph, "box", None) is None:
            paragraph.layout_region_id = None
            continue
        indexed.append(paragraph)
    page_index = int(getattr(page, "page_number", None) or 0)
    width, height = _page_size(page)
    texts = [_source_text(paragraph) for paragraph in indexed]
    gate, health = input_gate(width, texts)
    figures = _figures_of(page, width, height, doc)
    blocks = []
    for paragraph in indexed:
        on_photo = _on_photo(paragraph)
        lines = _lines_of(paragraph)
        # The tile's white is not skin. A column in that white is not a caption.
        if on_photo and _on_the_sheet(paragraph, figures):
            on_photo = False
        blocks.append(
            SourceBlock(
                lines=lines,
                role=_role_of(paragraph),
                text_on_photo=on_photo,
                source_text=_source_text(paragraph),
                marker=_marker_of(paragraph),
            )
        )
    if fingerprint:
        source_fingerprint = fingerprint
        scope = identity_scope
    else:
        source_fingerprint = f"unscoped:{page_index}:il"
        scope = "unscoped"
    facts = build_facts(
        source_fingerprint=source_fingerprint,
        page_index=page_index,
        page_width=width,
        page_height=height,
        input_gate=gate,
        text_health=health,
        blocks=blocks,
        figures=figures,
        identity_scope=scope,
    )
    page.layout_plan = build_plan(facts)
    emit(facts, page.layout_plan, log_path, console=True)
    if len(indexed) != len(facts.regions):
        raise RuntimeError("layout region count drifted")
    for paragraph, region in zip(indexed, facts.regions, strict=True):
        paragraph.layout_region_id = region.region_id
        paragraph.source_line_edges = tuple(
            (float(line.x0), float(line.x1)) for line in region.lines
        )


def _clear_plan(page) -> None:
    page.layout_plan = None
    for paragraph in getattr(page, "pdf_paragraph", None) or []:
        paragraph.layout_region_id = None
        paragraph.source_line_edges = None


def _planned_ids(page) -> set[str]:
    """Rect, list, figure-pocket, and line-edge ids the legacy pass must not move."""
    from babeldoc.format.pdf.document_il.utils.layout_plan.line_edges import (
        line_edge_ids,
    )
    from babeldoc.format.pdf.document_il.utils.layout_plan.paragraph_gap import (
        paragraph_gap_ids,
    )
    from babeldoc.format.pdf.document_il.utils.shaped_pocket_stack import (
        pocket_links_on,
    )

    return (
        set(_rect_links(page))
        | set(list_links_on(page))
        | set(pocket_links_on(page))
        | line_edge_ids(page)
        | paragraph_gap_ids(page)
    )


def _figures_of(page, width: float, height: float, doc=None) -> tuple[FigureBox, ...]:
    """Image and figure boxes, y-up. A box that fills the page is not a wrap figure.

    Photos on these pages are image forms. A short image sitting inside a
    text line is the line painted again, not a figure. A tall photo
    contributes the ink inside the rectangle. The white margin of that
    photo is not an edge. Neither box is written back onto the page.
    """
    found: list[FigureBox] = []
    for figure in getattr(page, "pdf_figure", None) or []:
        _append_figure(found, getattr(figure, "box", None), width, height)
    for form in getattr(page, "pdf_form", None) or []:
        if getattr(form, "form_type", None) != "image":
            continue
        box = getattr(form, "box", None)
        if _replays_a_text_line(box, page):
            continue
        ink = _photo_ink(form, doc)
        if ink is None:
            _append_figure(found, box, width, height)
            continue
        for band in ink:
            _append_figure(found, band, width, height)
    return tuple(found)


def _open_figure_pdf(pdf_path):
    if not pdf_path:
        return None
    try:
        import pymupdf

        return pymupdf.open(pdf_path)
    except Exception:
        logger.warning("figure ink pdf open failed", exc_info=True)
        return None


# A letter painted as an image is about one line tall. A photo tile is taller.
_LINE_IMAGE_HEIGHT = 18.0
# Shadow and hair. Neutral gray above this stays the sheet.
_INK_LO = 160
# Warm skin, including pale skin a flat darkness cutoff drops.
# Neutral JPEG near-white (251,251,251) and gray (247,247,247) are not skin.
_SKIN_WARMTH = 12
_INK_BAND = 8.0


def _replays_a_text_line(box, page) -> bool:
    """True when this short image starts inside a paragraph, like a letter strip.

    The strip may run past the paragraph's right edge. A figure that stands
    to the left of the text does not start inside it, so it stays a figure.
    """
    if box is None or None in (box.x, box.y, box.x2, box.y2):
        return False
    if abs(float(box.y2) - float(box.y)) > _LINE_IMAGE_HEIGHT:
        return False
    top = max(float(box.y), float(box.y2))
    bottom = min(float(box.y), float(box.y2))
    for paragraph in getattr(page, "pdf_paragraph", None) or []:
        other = getattr(paragraph, "box", None)
        if other is None or None in (other.x, other.y, other.x2, other.y2):
            continue
        if top < float(other.y) or bottom > float(other.y2):
            continue
        if float(box.x) >= float(other.x) - 1.0:
            return True
    return False


def _photo_ink(form, doc) -> list[FigureBox] | None:
    """Ink bands of a tall photo, or None when the rectangle must be kept.

    An empty list means the image has no ink. Y grows upward. Row 0 of the
    pixmap is the top of the image.
    """
    box = getattr(form, "box", None)
    if doc is None or box is None or None in (box.x, box.y, box.x2, box.y2):
        return None
    if abs(float(box.y2) - float(box.y)) <= _LINE_IMAGE_HEIGHT:
        return None
    subtype = getattr(form, "pdf_form_subtype", None)
    xobj = getattr(subtype, "pdf_xobj_form", None) if subtype is not None else None
    xref = getattr(xobj, "xref_id", None) if xobj is not None else None
    if not xref:
        return None
    try:
        import pymupdf

        pix = pymupdf.Pixmap(doc, int(xref))
        if pix.colorspace is None or pix.colorspace.n != 3 or pix.alpha:
            pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
    except Exception:
        return None
    width_px, height_px = pix.width, pix.height
    if width_px < 2 or height_px < 2:
        return None
    x0, x1 = float(box.x), float(box.x2)
    y0, y1 = float(box.y), float(box.y2)
    if x1 < x0:
        x0, x1 = x1, x0
    if y1 < y0:
        y0, y1 = y1, y0
    span_y = y1 - y0
    if span_y <= 1.0:
        return None
    bands: list[FigureBox] = []
    row = 0
    row_step = max(1, round(height_px * (_INK_BAND / span_y)))
    while row < height_px:
        next_row = min(height_px, row + row_step)
        page_top = y1 - (row / height_px) * span_y
        page_bottom = y1 - (next_row / height_px) * span_y
        left, right = _ink_span(pix, row, next_row - 1)
        if left is not None and right is not None:
            bands.append(
                FigureBox(
                    x0 + left / width_px * (x1 - x0),
                    page_bottom,
                    x0 + (right + 1) / width_px * (x1 - x0),
                    page_top,
                )
            )
        row = next_row
    return bands


def _ink_span(pix, row: int, end: int) -> tuple[int | None, int | None]:
    """Leftmost and rightmost ink on every row of the band, inclusive.

    Two sample rows miss a contour that enters between them. The line
    then crosses that contour.
    """
    left = None
    right = None
    last = min(pix.height - 1, max(row, end))
    first = max(0, min(row, last))
    for sample in range(first, last + 1):
        found = None
        for col in range(pix.width):
            if _pixel_is_ink(pix, col, sample):
                found = col
                break
        if found is None:
            continue
        left = found if left is None else min(left, found)
        for col in range(pix.width - 1, found - 1, -1):
            if _pixel_is_ink(pix, col, sample):
                right = col if right is None else max(right, col)
                break
    return left, right


def _channels_are_ink(red: int, green: int, blue: int) -> bool:
    """True for skin, shadow, or hair. Near-white and gray are the sheet."""
    darkest = min(red, green, blue)
    if darkest < _INK_LO:
        return True
    return (
        red - blue >= _SKIN_WARMTH
        and blue < 248
        and darkest < 250
    )


def _pixel_is_ink(pix, col: int, row: int) -> bool:
    pixel = pix.pixel(col, row)
    if len(pixel) < 3:
        return pixel[0] < _INK_LO
    return _channels_are_ink(pixel[0], pixel[1], pixel[2])


def _append_figure(found: list[FigureBox], box, width: float, height: float) -> None:
    if box is None:
        return
    if hasattr(box, "x0"):
        raw = (box.x0, box.y0, box.x1, box.y1)
    else:
        raw = (getattr(box, "x", None), getattr(box, "y", None), getattr(box, "x2", None), getattr(box, "y2", None))
    if None in raw:
        return
    x0, y0, x1, y1 = (float(item) for item in raw)
    if y1 < y0:
        y0, y1 = y1, y0
    if x1 < x0:
        x0, x1 = x1, x0
    if x1 - x0 <= 1.0 or y1 - y0 <= 1.0:
        return
    if x0 <= 2.0 and y0 <= 2.0 and x1 >= width - 2.0 and y1 >= height - 2.0:
        return
    found.append(FigureBox(x0, y0, x1, y1))


def column_gap_for(page, paragraph):
    """The figure gap for one rect column, or None when nothing sits beside it.

    The strategy stays rect_flow. Typesetting reads this the same way it
    reads a pocket: the width is the figure edge at that line.
    """
    if page is None or paragraph is None:
        return None
    region_id = getattr(paragraph, "layout_region_id", None)
    link = _rect_links(page).get(region_id)
    return _pocket_from_column(link)


def figure_gap_tops(page) -> dict[str, float]:
    """Box top of each rect column that has a figure gap, by region id.

    A straight column with no slices is absent. The map is for one call.
    """
    links = _rect_links(page)
    tops: dict[str, float] = {}
    if not links:
        return tops
    for paragraph in getattr(page, "pdf_paragraph", None) or []:
        region_id = getattr(paragraph, "layout_region_id", None)
        link = links.get(region_id)
        if region_id is None or link is None or not link.gap_slices:
            continue
        box = getattr(paragraph, "box", None)
        if box is None or box.y2 is None:
            continue
        tops[region_id] = float(box.y2)
    return tops


def moved_figure_gap_paragraphs(page, tops: dict[str, float]) -> list:
    """Gap columns whose box top moved since ``tops`` was taken.

    An unmoved gap column stays out. A column that was never in ``tops``
    has no slices and stays out.
    """
    if not tops:
        return []
    found = []
    for paragraph in getattr(page, "pdf_paragraph", None) or []:
        region_id = getattr(paragraph, "layout_region_id", None)
        if region_id not in tops:
            continue
        box = getattr(paragraph, "box", None)
        if box is None or box.y2 is None:
            continue
        if abs(float(box.y2) - tops[region_id]) > 0.5:
            found.append(paragraph)
    return found


def _pocket_from_column(link: ColumnLink):
    from babeldoc.format.pdf.document_il.utils.layout_plan.model import PocketLink

    if link is None or not link.gap_slices:
        return None
    if link.free_side not in {"left", "right"}:
        return None
    opening = link.column_right - link.column_left
    pin = link.column_left if link.free_side == "right" else link.column_right
    return PocketLink(
        region_id=link.region_id,
        free_side=link.free_side,
        pin_edge=pin,
        line_widths=(opening,),
        opening=opening,
        slices=link.gap_slices,
        edge_gap=link.edge_gap,
    )


def _gap_span(link: ColumnLink) -> float:
    """Widest line this column's figure gap can hold."""
    pocket = _pocket_from_column(link)
    if pocket is None:
        return link.column_right - link.column_left
    from babeldoc.format.pdf.document_il.utils.shaped_pocket_stack import (
        interval_for_pocket,
    )

    widths = [pocket.opening]
    for bottom, top, _edge in link.gap_slices:
        x0, x1 = interval_for_pocket(pocket, 0, bottom, top)
        widths.append(x1 - x0)
    return max(widths)


def _rect_links(page) -> dict[str, ColumnLink]:
    plan = getattr(page, "layout_plan", None)
    if plan is None:
        return {}
    found: dict[str, ColumnLink] = {}
    for link in getattr(plan, "column_links", ()) or ():
        seen = consume_layout_plan(plan, link.region_id)
        if seen.base_strategy != "rect_flow":
            continue
        found[link.region_id] = link
    return found


def list_links_on(page) -> dict[str, ListLink]:
    """List links whose frozen strategy is still list."""
    plan = getattr(page, "layout_plan", None)
    if plan is None:
        return {}
    found: dict[str, ListLink] = {}
    for link in getattr(plan, "list_links", ()) or ():
        seen = consume_layout_plan(plan, link.region_id)
        if seen.base_strategy != "list":
            continue
        found[link.region_id] = link
    return found


def _link_chains(links: dict[str, ColumnLink]) -> list[list[ColumnLink]]:
    pointed = {link.flow_next_id for link in links.values() if link.flow_next_id}
    chains: list[list[ColumnLink]] = []
    seen: set[str] = set()
    for link in links.values():
        if link.region_id in pointed:
            continue
        chain: list[ColumnLink] = []
        cursor: ColumnLink | None = link
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


def note_held_spans(page, paragraphs) -> None:
    """Remember boxes the legacy pass will not see. Replaces any older note.

    The note is a field on this page. Close reads it so a rise cannot
    cross ink that pass cannot see. Another page does not carry it.
    """
    if page is None:
        return
    spans = []
    for paragraph in paragraphs or []:
        box = getattr(paragraph, "box", None)
        if box is None or None in (box.x, box.y, box.x2, box.y2):
            continue
        spans.append((float(box.y), float(box.y2), float(box.x), float(box.x2)))
    page.layout_held_spans = tuple(spans) if spans else None


def clear_held_spans(page) -> None:
    """Drop this page's note. Another page object does not carry it."""
    if page is None:
        return
    page.layout_held_spans = None


def held_column_spans(page) -> tuple[tuple[float, float, float, float], ...]:
    """Boxes hidden from the current legacy pass. Empty when nothing is held."""
    if page is None:
        return ()
    return tuple(getattr(page, "layout_held_spans", None) or ())


def _hold(page) -> dict | None:
    original: list | None = None
    swapped = False
    clear_held_spans(page)
    try:
        original = list(getattr(page, "pdf_paragraph", None) or [])
        planned = _planned_ids(page)
        if not planned:
            return None
        from babeldoc.format.pdf.document_il.utils.shaped_pocket_stack import (
            pocket_links_on,
        )

        # Close and settle still move an unmarked paragraph. On a pocket
        # page that leftover is the line beside the figure, so hold it too.
        freeze_rest = bool(pocket_links_on(page))
        held_at: dict[int, object] = {}
        rest = []
        for index, paragraph in enumerate(original):
            region_id = getattr(paragraph, "layout_region_id", None)
            if freeze_rest or region_id in planned:
                held_at[index] = paragraph
            else:
                rest.append(paragraph)
        if not held_at:
            return None
        page.pdf_paragraph = rest
        swapped = True
        note_held_spans(page, list(held_at.values()))
        return {"length": len(original), "held_at": held_at}
    except Exception:
        logger.warning("planned paragraph hold failed", exc_info=True)
        clear_held_spans(page)
        if swapped and original is not None:
            page.pdf_paragraph = original
        return None


def _restore(page, state: dict) -> None:
    try:
        flowed = list(getattr(page, "pdf_paragraph", None) or [])
        rebuilt = []
        cursor = 0
        held_at = state["held_at"]
        for index in range(state["length"]):
            held = held_at.get(index)
            if held is not None:
                rebuilt.append(held)
                continue
            if cursor < len(flowed):
                rebuilt.append(flowed[cursor])
                cursor += 1
        if cursor < len(flowed):
            rebuilt.extend(flowed[cursor:])
        page.pdf_paragraph = rebuilt
    finally:
        clear_held_spans(page)


def _role_of(paragraph) -> str | None:
    role = _labeled_role(paragraph)
    # Styles stores a leading bullet as a formula, and intent then marks the
    # whole item formula. The list plugin never sees that item. Drop only
    # this tag so the existing marker rule can run.
    if role == "formula" and _opens_as_list(paragraph):
        return None
    lines = _lines_of(paragraph)
    # A multi-line narrative/dialogue/bibliography block is a body column,
    # never a standalone math equation or short decorative pull-quote / callout.
    if role == "formula" and len(lines) >= 2:
        return None
    if role in ("pull_quote", "callout") and len(lines) >= 4:
        return None
    return role


def _labeled_role(paragraph) -> str | None:
    intent = getattr(paragraph, "layout_intent", None)
    role = getattr(intent, "role", None) if intent is not None else None
    if role is not None:
        value = getattr(role, "value", role)
        if isinstance(value, str) and value:
            return value
    label = getattr(paragraph, "layout_label", None)
    if isinstance(label, str) and label in _LABEL_ROLES:
        return label
    return None


def _opens_as_list(paragraph) -> bool:
    marker = _marker_of(paragraph)
    if marker is not None and marker.is_bullet:
        return True
    text = _source_text(paragraph).replace("\xa0", " ").replace("\u2009", " ").lstrip()
    return bool(LIST_MARKER_RE.match(text))


def _on_photo(paragraph) -> bool:
    intent = getattr(paragraph, "layout_intent", None)
    return bool(getattr(intent, "text_on_photo", False)) if intent is not None else False


# Glyphs hang about one em below the line top. The next line is not this one.
_GLYPH_DEPTH = 12.0


def _on_the_sheet(paragraph, figures) -> bool:
    """True when the photo flag is the tile's white, and skin cuts the box.

    A caption whose line meets the skin stays on the photo. A list and
    chrome stay as they were. A figure that only sits beside the box
    does not count.
    """
    if not figures or _opens_as_list(paragraph) or is_chrome_paragraph(paragraph):
        return False
    lines = _lines_of(paragraph)
    box = getattr(paragraph, "box", None)
    if len(lines) < 2 or box is None or None in (box.x, box.y, box.x2, box.y2):
        return False
    if _line_meets_skin(lines, figures):
        return False
    return _skin_cuts_box(box, figures)


def _line_meets_skin(lines, figures) -> bool:
    for line in lines:
        bottom = line.y0 - _GLYPH_DEPTH
        for figure in figures:
            if figure.y1 < bottom or figure.y0 > line.y0:
                continue
            if figure.x0 < line.x1 - 1.0 and figure.x1 > line.x0 + 1.0:
                return True
    return False


def _skin_cuts_box(box, figures) -> bool:
    top = max(float(box.y), float(box.y2))
    bottom = min(float(box.y), float(box.y2))
    left = float(box.x)
    right = float(box.x2)
    for figure in figures:
        if figure.y1 < bottom or figure.y0 > top:
            continue
        if left + 1.0 < figure.x0 < right - 1.0:
            return True
        if left + 1.0 < figure.x1 < right - 1.0:
            return True
    return False


def _source_text(paragraph) -> str:
    return getattr(paragraph, "unicode", None) or ""


def _lines_of(paragraph) -> tuple[LineBox, ...]:
    """Source lines for the plan.

    A pure run of line boxes is those boxes. Styles later folds every line
    of one face into a single run, and the paragraph box is then one
    rectangle. The characters still sit on the source lines, so the plan
    reads those lines. The Chinese measure is not taken from them.
    """
    compositions = getattr(paragraph, "pdf_paragraph_composition", None) or []
    # A 30pt en-dash is the bullet, not a 15pt-wide first line. Counting
    # it makes the item a hang and the Chinese sentence does not fit.
    body = [comp for comp in compositions if not _is_dash_bullet_line(comp)]
    if body:
        compositions = body
    line_boxes: list[LineBox] = []
    folded = False
    for composition in compositions:
        line = getattr(composition, "pdf_line", None)
        box = getattr(line, "box", None) if line is not None else None
        if box is not None and None not in (box.x, box.x2, box.y2):
            line_boxes.append(LineBox(float(box.x), float(box.x2), float(box.y2)))
            continue
        if _line_chars(composition):
            folded = True
    if line_boxes and not folded:
        return tuple(line_boxes)
    recovered = _lines_from_characters(paragraph)
    if recovered:
        return recovered
    if line_boxes:
        return tuple(line_boxes)
    box = getattr(paragraph, "box", None)
    if box is None or box.x is None or box.x2 is None or box.y2 is None:
        return ()
    return (LineBox(float(box.x), float(box.x2), float(box.y2)),)


def _lines_from_characters(paragraph) -> tuple[LineBox, ...]:
    """One box per source line, top first. A marker a few points off stays."""
    chars = []
    for composition in getattr(paragraph, "pdf_paragraph_composition", None) or []:
        for char in _line_chars(composition):
            box = getattr(char, "box", None)
            if box is None or None in (box.x, box.x2, box.y2):
                continue
            chars.append(char)
    if not chars:
        return ()
    chars.sort(key=lambda char: float(char.box.y2), reverse=True)
    groups: list[list] = [[chars[0]]]
    for char in chars[1:]:
        if abs(float(groups[-1][0].box.y2) - float(char.box.y2)) <= _SAME_LINE_TOP:
            groups[-1].append(char)
            continue
        groups.append([char])
    found: list[LineBox] = []
    for group in groups:
        text = "".join(
            getattr(char, "char_unicode", None) or "" for char in group
        ).strip()
        # The bullet dash is its own glyph. It is not the item's first line.
        if text in _DASH_BULLET_LINE and len(groups) > 1:
            continue
        x0 = min(float(char.box.x) for char in group)
        x1 = max(float(char.box.x2) for char in group)
        if x1 - x0 <= 0.0:
            continue
        top = max(float(char.box.y2) for char in group)
        found.append(LineBox(x0, x1, top))
    return tuple(found)


def _marker_of(paragraph):
    for composition in getattr(paragraph, "pdf_paragraph_composition", None) or []:
        chars = _line_chars(composition)
        if not chars:
            continue
        text = "".join(getattr(char, "char_unicode", None) or "" for char in chars)
        style = getattr(chars[0], "pdf_style", None)
        font = getattr(style, "font_id", None) if style is not None else None
        evidence = marker_from_glyph(text, font)
        if text.strip() or evidence.is_bullet:
            return evidence
    return None


# En dash, em dash, figure dash, minus. A line of only these is a bullet.
_DASH_BULLET_LINE = frozenset("\u2013\u2014\u2012\u2212")


def _is_dash_bullet_line(composition) -> bool:
    chars = _line_chars(composition)
    if not chars:
        return False
    text = "".join(getattr(char, "char_unicode", None) or "" for char in chars).strip()
    return text in _DASH_BULLET_LINE


def _line_chars(composition) -> list:
    line = getattr(composition, "pdf_line", None)
    if line is not None and getattr(line, "pdf_character", None):
        return list(line.pdf_character)
    character = getattr(composition, "pdf_character", None)
    if character is not None:
        return [character]
    same = getattr(composition, "pdf_same_style_characters", None)
    if same is not None and getattr(same, "pdf_character", None):
        return list(same.pdf_character)
    formula = getattr(composition, "pdf_formula", None)
    if formula is not None and getattr(formula, "pdf_character", None):
        return list(formula.pdf_character)
    return []


def _ink(paragraph) -> tuple[float, float] | None:
    tops: list[float] = []
    bottoms: list[float] = []
    for composition in getattr(paragraph, "pdf_paragraph_composition", None) or []:
        for char in _line_chars(composition):
            box = getattr(char, "box", None)
            if box is None or box.y is None or box.y2 is None:
                continue
            tops.append(float(box.y2))
            bottoms.append(float(box.y))
    if tops:
        return max(tops), min(bottoms)
    box = getattr(paragraph, "box", None)
    if box is None or box.y is None or box.y2 is None:
        return None
    return float(box.y2), float(box.y)


def _shift(paragraph, dy: float) -> None:
    if dy == 0:
        return
    _shift_box(getattr(paragraph, "box", None), dy)
    for composition in getattr(paragraph, "pdf_paragraph_composition", None) or []:
        line = getattr(composition, "pdf_line", None)
        if line is not None:
            _shift_box(getattr(line, "box", None), dy)
            for char in getattr(line, "pdf_character", None) or []:
                _shift_box(getattr(char, "box", None), dy)
        formula = getattr(composition, "pdf_formula", None)
        if formula is not None:
            _shift_box(getattr(formula, "box", None), dy)
            for char in getattr(formula, "pdf_character", None) or []:
                _shift_box(getattr(char, "box", None), dy)
        character = getattr(composition, "pdf_character", None)
        if character is not None:
            _shift_box(getattr(character, "box", None), dy)
        same = getattr(composition, "pdf_same_style_characters", None)
        if same is not None:
            _shift_box(getattr(same, "box", None), dy)
            for char in getattr(same, "pdf_character", None) or []:
                _shift_box(getattr(char, "box", None), dy)


def _shift_box(box, dy: float) -> None:
    if box is None or box.y is None or box.y2 is None:
        return
    box.y = float(box.y) + dy
    box.y2 = float(box.y2) + dy


def _page_size(page) -> tuple[float, float]:
    for name in ("cropbox", "mediabox"):
        holder = getattr(page, name, None)
        box = getattr(holder, "box", None) if holder is not None else None
        if (
            box is None
            or box.x is None
            or box.y is None
            or box.x2 is None
            or box.y2 is None
        ):
            continue
        return abs(float(box.x2) - float(box.x)), abs(float(box.y2) - float(box.y))
    return 612.0, 792.0
