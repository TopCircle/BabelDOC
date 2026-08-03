"""Enforce visual gap between large titles and following body (dual layout).

CJK display titles (e.g. Source Han 56pt) often have taller ink boxes than the
English Microstyle title at the same nominal size. Body paragraphs stay at the
original EN y, so title and first body **overlap** on the ZH half of dual PDFs
(OA p19: title.y1 past body.y0). English keeps ~12–18pt clearance.

After typesetting, shift the body (and x-overlapping followers) down so:

    body.ink_top <= title.ink_bottom - min_gap   (PDF y-up: y2 is top, y is bottom)
"""

from __future__ import annotations

import logging
from typing import Any

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import Page
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.utils.region_skip import (
    is_chrome_paragraph,
    is_layout_debug_stub,
)

logger = logging.getLogger(__name__)

# Match OA EN title→body clearance (~11–18pt).
DEFAULT_MIN_GAP_PT = 14.0
# Treat as display title when max rendered size reaches this.
DISPLAY_TITLE_SIZE_PT = 28.0
_TITLE_LABELS = frozenset({"title", "section_header"})


def _iter_chars(paragraph: PdfParagraph):
    for composition in paragraph.pdf_paragraph_composition or []:
        if composition.pdf_character:
            yield composition.pdf_character
        elif composition.pdf_line and composition.pdf_line.pdf_character:
            yield from composition.pdf_line.pdf_character
        elif composition.pdf_formula and composition.pdf_formula.pdf_character:
            yield from composition.pdf_formula.pdf_character
        elif (
            composition.pdf_same_style_characters
            and composition.pdf_same_style_characters.pdf_character
        ):
            yield from composition.pdf_same_style_characters.pdf_character


def ink_box(paragraph: PdfParagraph) -> Box | None:
    """Tight box of rendered glyphs (PDF coords: y bottom, y2 top)."""
    ys: list[float] = []
    y2s: list[float] = []
    xs: list[float] = []
    x2s: list[float] = []
    for ch in _iter_chars(paragraph):
        box = getattr(ch, "box", None)
        if box is None or box.x is None or box.y is None:
            continue
        if box.x2 is None or box.y2 is None:
            continue
        xs.append(float(box.x))
        x2s.append(float(box.x2))
        ys.append(float(box.y))
        y2s.append(float(box.y2))
    if not ys:
        return None
    return Box(x=min(xs), y=min(ys), x2=max(x2s), y2=max(y2s))


def max_font_size(paragraph: PdfParagraph) -> float:
    best = 0.0
    for ch in _iter_chars(paragraph):
        st = getattr(ch, "pdf_style", None)
        if st is None or st.font_size is None:
            continue
        try:
            best = max(best, float(st.font_size))
        except (TypeError, ValueError):
            continue
    return best


def is_display_title(paragraph: PdfParagraph) -> bool:
    """Large chapter/display title that must not collide with body below."""
    label = (getattr(paragraph, "layout_label", None) or "").strip().lower()
    size = max_font_size(paragraph)
    if size >= DISPLAY_TITLE_SIZE_PT:
        return True
    if label in _TITLE_LABELS and size >= 18.0:
        return True
    return False


def _x_overlap(a: Box, b: Box, *, slack: float = 8.0) -> bool:
    return a.x < b.x2 + slack and a.x2 > b.x - slack


def shift_paragraph_y(paragraph: PdfParagraph, dy: float) -> None:
    """Translate all rendered glyphs and paragraph.box by *dy* (PDF y-up)."""
    if abs(dy) < 0.05:
        return
    for ch in _iter_chars(paragraph):
        box = getattr(ch, "box", None)
        if box is not None:
            if box.y is not None:
                box.y = float(box.y) + dy
            if box.y2 is not None:
                box.y2 = float(box.y2) + dy
        vb = getattr(ch, "visual_bbox", None)
        if vb is not None and getattr(vb, "box", None) is not None:
            vbox = vb.box
            if vbox.y is not None:
                vbox.y = float(vbox.y) + dy
            if vbox.y2 is not None:
                vbox.y2 = float(vbox.y2) + dy
    if paragraph.box is not None:
        b = paragraph.box
        if b.y is not None:
            b.y = float(b.y) + dy
        if b.y2 is not None:
            b.y2 = float(b.y2) + dy


def enforce_title_body_gaps(
    page: Page,
    *,
    min_gap: float = DEFAULT_MIN_GAP_PT,
) -> int:
    """Shift body paragraphs down so they clear large titles by *min_gap*.

    Returns number of paragraphs shifted.
    """
    paras = [
        p
        for p in (page.pdf_paragraph or [])
        if p.pdf_paragraph_composition
        # LayoutParser label stubs (unicode == class name / debug
        # composition) are diagnostic boxes — never titles, bodies or
        # followers. xobj_id is NOT the signal (page-level text uses -1 too).
        and not is_layout_debug_stub(p)
    ]
    if len(paras) < 2:
        return 0

    ink: dict[int, Box] = {}
    for p in paras:
        box = ink_box(p)
        if box is not None:
            ink[id(p)] = box

    # Top-first: higher y2 first
    ordered = sorted(
        [p for p in paras if id(p) in ink],
        key=lambda p: (-(ink[id(p)].y2 or 0.0), ink[id(p)].x or 0.0),
    )

    shifted = 0
    for i, title in enumerate(ordered):
        if not is_display_title(title):
            continue
        tbox = ink[id(title)]
        # Find next paragraph below (smaller y2) with horizontal overlap
        body = None
        for cand in ordered[i + 1 :]:
            cbox = ink[id(cand)]
            if (cbox.y2 or 0) >= (tbox.y2 or 0) - 0.5:
                continue  # not below
            if not _x_overlap(tbox, cbox):
                continue
            # Designed overlay: the candidate sits ENTIRELY inside the title's
            # ink band (subtitle stacked on a chapter head, OA p19 "Chapter 3"
            # + 15pt subtitle: 668.6..692.8 within 661.5..693.5). Not a real
            # body below — never enforce a gap on it or the cascade drags the
            # big heading down with it. A body whose bottom pokes below the
            # title's bottom edge (title ink pressing into body) is a genuine
            # collision and still gets the gap.
            if (cbox.y or 0) >= (tbox.y or 0) - 0.5 and (
                cbox.y2 or 0
            ) <= (tbox.y2 or 0) + 0.5:
                continue
            if is_display_title(cand) and max_font_size(cand) >= max_font_size(title) * 0.85:
                # another big title — skip pairing into it as "body"
                continue
            if is_chrome_paragraph(cand, page):
                continue  # site chrome is never a body
            body = cand
            break
        if body is None:
            continue

        bbox = ink[id(body)]
        # Need body.top (y2) <= title.bottom (y) - min_gap
        title_bottom = float(tbox.y)
        body_top = float(bbox.y2)
        target_top = title_bottom - min_gap
        if body_top <= target_top + 0.5:
            continue  # already enough gap

        dy = target_top - body_top  # negative → move down the page
        # Also shift followers that would be crossed (same column, below body)
        to_shift = [body]
        for cand in ordered:
            if cand is body or cand is title:
                continue
            cbox = ink[id(cand)]
            if (cbox.y2 or 0) > body_top + 1:
                continue  # above body top
            if not _x_overlap(bbox, cbox):
                continue
            if is_display_title(cand):
                # independent display titles have their own gap pass; dragging
                # them as followers cascades the whole chapter head down
                continue
            if is_chrome_paragraph(cand, page):
                # skipped footer/header/URL chrome must stay put — the skip
                # contract is "leave EN visible at the original position"
                continue
            to_shift.append(cand)

        for p in to_shift:
            shift_paragraph_y(p, dy)
            new_ink = ink_box(p)
            if new_ink is not None:
                ink[id(p)] = new_ink
            shifted += 1

        logger.debug(
            "title-body gap: page=%s shifted=%d dy=%.1f title_bottom=%.1f body_top=%.1f→%.1f",
            getattr(page, "page_number", None),
            len(to_shift),
            dy,
            title_bottom,
            body_top,
            body_top + dy,
        )

    return shifted
