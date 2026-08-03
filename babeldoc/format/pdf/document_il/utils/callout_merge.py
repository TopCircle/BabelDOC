"""Merge stacked ultra-narrow callout lines into one paragraph for whole-MT.

OA TAKING CHARGE paints each triangle row as its own short paragraph.  Line-by-
line MT loses discourse context and typesetting keeps the inverted-triangle
geometry (one CJK char per tip line).

Merge vertically stacked narrow strips (same column) so unicode is one block
and typesetting can reflow in the union box.

Strategy (0.6.4.49):
  1. List-adjacent chain merge (safe; matches stream/discovery order).
  2. Optional y-sorted merge only for remaining **ultra-narrow** tips that are
     not list-adjacent but sit in a clear vertical stack (no intervening para
     in the same column band).  Whole-page y-sort of every width≤220 strip
     over-merged body/subheads in 0.6.4.48 and wrecked dual layout.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from babeldoc.format.pdf.document_il.il_version_1 import Page
    from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph

logger = logging.getLogger(__name__)

_MAX_LINE_WIDTH = 220.0
# Non-list-adjacent y-merge only for tip-like fragments (OA tip ~50–100pt).
_ULTRA_NARROW_Y_MERGE = 120.0
_MAX_VERTICAL_GAP = 22.0
# Triangle tip indents far right of the first line (OA ~100pt+).
_MAX_X_DELTA = 160.0


def _box(p: PdfParagraph):
    return getattr(p, "box", None)


def _width(p: PdfParagraph) -> float:
    b = _box(p)
    if b is None or b.x is None or b.x2 is None:
        return 0.0
    return float(b.x2 - b.x)


def _y2(p: PdfParagraph) -> float:
    b = _box(p)
    if b is None or b.y2 is None:
        return 0.0
    return float(b.y2)


def _same_xobj(a: PdfParagraph, b: PdfParagraph) -> bool:
    return getattr(a, "xobj_id", None) == getattr(b, "xobj_id", None)


def _can_merge(upper: PdfParagraph, lower: PdfParagraph) -> bool:
    bu, bl = _box(upper), _box(lower)
    if bu is None or bl is None:
        return False
    if bu.x is None or bl.x is None or bu.y is None or bl.y2 is None:
        return False
    if _width(upper) > _MAX_LINE_WIDTH or _width(lower) > _MAX_LINE_WIDTH:
        return False
    if not _same_xobj(upper, lower):
        return False
    # lower is below upper: lower.y2 < upper.y2 (PDF y-up)
    if (bl.y2 or 0) >= (bu.y2 or 0) - 0.5:
        return False
    # gap between upper bottom and lower top (stacked rows may be denser)
    gap = float(bu.y) - float(bl.y2)
    if gap > _MAX_VERTICAL_GAP or gap < -12.0:
        return False
    # similar column (lower may indent more for triangle tip)
    if abs(float(bu.x) - float(bl.x)) > _MAX_X_DELTA and float(bl.x) + 5 < float(bu.x):
        return False
    if float(bl.x) > float(bu.x2) or float(bl.x2) < float(bu.x):
        return False
    return True


def _composition_sort_key(comp: Any) -> tuple[float, float]:
    line = getattr(comp, "pdf_line", None)
    box = getattr(line, "box", None) if line is not None else None
    if box is None:
        formula = getattr(comp, "pdf_formula", None)
        box = getattr(formula, "box", None) if formula is not None else None
    if box is None:
        ch = getattr(comp, "pdf_character", None)
        vb = getattr(ch, "visual_bbox", None) if ch is not None else None
        box = getattr(vb, "box", None) if vb is not None else getattr(ch, "box", None)
    if box is None:
        return (0.0, 0.0)
    return (-(float(box.y2) if box.y2 is not None else 0.0), float(box.x or 0.0))


def _sort_compositions_visual(paragraph: PdfParagraph) -> None:
    """Top-first composition order after merge (tip-first stream → reading order)."""
    comps = list(paragraph.pdf_paragraph_composition or [])
    if len(comps) < 2:
        return
    paragraph.pdf_paragraph_composition = sorted(comps, key=_composition_sort_key)


def _merge_lower_into_upper(upper: PdfParagraph, lower: PdfParagraph) -> None:
    from babeldoc.format.pdf.document_il.il_version_1 import Box

    upper.pdf_paragraph_composition = list(
        upper.pdf_paragraph_composition or []
    ) + list(lower.pdf_paragraph_composition or [])
    ub, lb = upper.box, lower.box
    upper.box = Box(
        x=min(float(ub.x), float(lb.x)),
        y=min(float(ub.y), float(lb.y)),
        x2=max(float(ub.x2), float(lb.x2)),
        y2=max(float(ub.y2), float(lb.y2)),
    )
    if getattr(lower, "layout_label", None) in ("title", "section_header"):
        if getattr(upper, "layout_label", None) not in ("title", "section_header"):
            upper.layout_label = lower.layout_label
    _sort_compositions_visual(upper)


def _column_band(a: PdfParagraph, b: PdfParagraph) -> tuple[float, float]:
    ba, bb = _box(a), _box(b)
    x0 = min(float(ba.x), float(bb.x))
    x1 = max(float(ba.x2), float(bb.x2))
    return x0, x1


def _has_intervening_paragraph(
    upper: PdfParagraph,
    lower: PdfParagraph,
    paragraphs: list[PdfParagraph],
) -> bool:
    """True if another para sits between upper/lower in y within their x-band."""
    bu, bl = _box(upper), _box(lower)
    if bu is None or bl is None:
        return True
    y_hi = min(float(bu.y2 or 0), float(bl.y2 or 0))  # noqa: not used for gap
    # Vertical interior between the two stacks (exclusive)
    top = float(bu.y)  # bottom edge of upper
    bot = float(bl.y2)  # top edge of lower
    if top <= bot:
        return False
    x0, x1 = _column_band(upper, lower)
    for p in paragraphs:
        if p is upper or p is lower:
            continue
        b = _box(p)
        if b is None or b.x is None or b.x2 is None or b.y is None or b.y2 is None:
            continue
        # center y of p in the open gap?
        cy = 0.5 * (float(b.y) + float(b.y2))
        if not (bot < cy < top):
            continue
        # x overlap with column band
        if float(b.x2) < x0 or float(b.x) > x1:
            continue
        return True
    return False


def _merge_list_adjacent(paragraphs: list[PdfParagraph]) -> int:
    merges = 0
    i = 0
    while i < len(paragraphs) - 1:
        a = paragraphs[i]
        b = paragraphs[i + 1]
        ba, bb = _box(a), _box(b)
        if ba is None or bb is None:
            i += 1
            continue
        if (ba.y2 or 0) >= (bb.y2 or 0):
            upper, lower = a, b
        else:
            upper, lower = b, a
        if not _can_merge(upper, lower):
            i += 1
            continue
        _merge_lower_into_upper(upper, lower)
        paragraphs.remove(lower)
        merges += 1
        # stay on i to chain-merge further lines into the same stack
    return merges


def _merge_y_sorted_ultra_narrow(paragraphs: list[PdfParagraph]) -> int:
    """Second pass: non-list-adjacent ultra-narrow tips only."""
    merges = 0
    while True:
        candidates = [
            p
            for p in paragraphs
            if _box(p) is not None and 0 < _width(p) <= _ULTRA_NARROW_Y_MERGE
        ]
        if len(candidates) < 2:
            break
        candidates.sort(key=_y2, reverse=True)
        merged_this_pass = False
        for i in range(len(candidates) - 1):
            upper = candidates[i]
            lower = candidates[i + 1]
            if upper not in paragraphs or lower not in paragraphs:
                continue
            if not _can_merge(upper, lower):
                continue
            if _has_intervening_paragraph(upper, lower, paragraphs):
                continue
            _merge_lower_into_upper(upper, lower)
            paragraphs.remove(lower)
            merges += 1
            merged_this_pass = True
            break
        if not merged_this_pass:
            break
    return merges


def merge_stacked_narrow_callout_paragraphs(
    paragraphs: list[PdfParagraph],
    page: Page | None = None,
) -> int:
    """In-place merge of stacked narrow callout lines. Returns merge count."""
    _ = page
    if len(paragraphs) < 2:
        return 0
    merges = _merge_list_adjacent(paragraphs)
    merges += _merge_y_sorted_ultra_narrow(paragraphs)
    if merges:
        logger.debug("callout_merge: merged %d stacked narrow lines", merges)
    return merges
