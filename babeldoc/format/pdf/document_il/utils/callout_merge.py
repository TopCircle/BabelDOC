"""Merge stacked ultra-narrow callout lines into one paragraph for whole-MT.

OA TAKING CHARGE paints each triangle row as its own short paragraph.  Line-by-
line MT loses discourse context and typesetting keeps the inverted-triangle
geometry (one CJK char per tip line).

Merge vertically adjacent narrow strips (same column) so unicode is one block
and typesetting can reflow in the union box.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from babeldoc.format.pdf.document_il.il_version_1 import Page
    from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph

logger = logging.getLogger(__name__)

_MAX_LINE_WIDTH = 220.0
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


def merge_stacked_narrow_callout_paragraphs(
    paragraphs: list[PdfParagraph],
    page: Page | None = None,
) -> int:
    """In-place merge of stacked narrow callout lines. Returns merge count."""
    _ = page
    if len(paragraphs) < 2:
        return 0
    merges = 0
    i = 0
    while i < len(paragraphs) - 1:
        a = paragraphs[i]
        b = paragraphs[i + 1]
        ba, bb = _box(a), _box(b)
        if ba is None or bb is None:
            i += 1
            continue
        # Order so upper is visually above (higher y2)
        if (ba.y2 or 0) >= (bb.y2 or 0):
            upper, lower = a, b
        else:
            upper, lower = b, a
        if not _can_merge(upper, lower):
            i += 1
            continue
        # Append lower compositions to upper; delete lower by identity
        upper.pdf_paragraph_composition = list(
            upper.pdf_paragraph_composition or []
        ) + list(lower.pdf_paragraph_composition or [])
        from babeldoc.format.pdf.document_il.il_version_1 import Box

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
        paragraphs.remove(lower)
        merges += 1
        # stay on i to chain-merge further lines into the same stack
        continue
    if merges:
        logger.debug("callout_merge: merged %d stacked narrow lines", merges)
    return merges
