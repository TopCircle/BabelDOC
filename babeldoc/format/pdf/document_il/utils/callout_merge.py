"""Merge callout fragments into single MT/reflow units.

Two independent product problems, one module:

1. **Vertical stack** (OA TAKING CHARGE tip): each triangle row is its own
   short paragraph → merge stacked narrow lines (width ≤220) so unicode is one
   block.  Whole-page y-sort of every medium strip over-merged body in
   0.6.4.48; that path stays ultra-narrow only.

2. **Horizontal prefix pair** (OA p5 red/black dual column): left fragment
   text is a prefix of the right fuller column → absorb shorter into longer
   with union box.  Vertical stack constants are intentionally *not* loosened
   for this case.

Entry: :func:`merge_stacked_narrow_callout_paragraphs` (name kept for callers).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from typing import Any

if TYPE_CHECKING:
    from babeldoc.format.pdf.document_il.il_version_1 import Page
    from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph

logger = logging.getLogger(__name__)

# --- vertical stack (list-adjacent + ultra-narrow y-pass) ---
_MAX_LINE_WIDTH = 220.0
_ULTRA_NARROW_Y_MERGE = 120.0
_MAX_VERTICAL_GAP = 22.0
_MAX_X_DELTA = 160.0
# OA p19 TAKING CHARGE wrap rows (~228–255pt) sit just over the callout cap.
# Right-edge pin is the extra gate so this path cannot re-open the 0.6.4.48
# medium-strip y-merge. Do not raise _MAX_LINE_WIDTH.
_WRAP_LINE_MAX_WIDTH = 280.0
# Union box of a left-stepping wrap column is wider than any single row
# (OA p19 ~290pt). Cap the host, not the incoming line, at this.
_WRAP_HOST_MAX_WIDTH = 340.0
_WRAP_RIGHT_PIN_SPREAD = 8.0

# --- horizontal prefix pair (dual-column callout) ---
_H_PAIR_MIN_Y_IOU = 0.25
_H_PAIR_MAX_LEFT_WIDTH = 280.0
_H_PAIR_MIN_PREFIX = 8

_MIN_PULLQUOTE_FRAGMENT = 25
_MIN_MULTIROW_CHARS = 8
_TRAIL_PUNCT = ".:;。：；,，!！?？\"'”’"


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


def _char_y_bounds(c: Any) -> tuple[float, float] | None:
    box = None
    vb = getattr(c, "visual_bbox", None)
    if vb is not None and getattr(vb, "box", None) is not None:
        box = vb.box
    if box is None:
        box = getattr(c, "box", None)
    if box is None or box.y is None or box.y2 is None:
        return None
    return float(box.y), float(box.y2)


def _is_multi_row_block(paragraph: PdfParagraph) -> bool:
    """True when one composition line spans multiple visual rows (p82 quote)."""
    comps = list(paragraph.pdf_paragraph_composition or [])
    if len(comps) != 1:
        return False
    line = comps[0].pdf_line
    if line is None:
        return False
    chars = list(line.pdf_character or [])
    if len(chars) < _MIN_MULTIROW_CHARS:
        return False
    centers: list[float] = []
    heights: list[float] = []
    for c in chars:
        bounds = _char_y_bounds(c)
        if bounds is None:
            continue
        y, y2 = bounds
        centers.append((y + y2) / 2.0)
        heights.append(y2 - y)
    if len(centers) < _MIN_MULTIROW_CHARS:
        return False
    heights.sort()
    med_h = heights[len(heights) // 2]
    if med_h <= 0:
        return False
    centers.sort()
    rows = 1
    last = centers[0]
    tol = max(3.0, med_h * 0.4)
    for y in centers[1:]:
        if y - last > tol:
            rows += 1
        last = y
    y_bounds = [b for b in (_char_y_bounds(c) for c in chars) if b is not None]
    ymin = min((b[0] for b in y_bounds), default=0.0)
    ymax = max((b[1] for b in y_bounds), default=0.0)
    return rows >= 2 and (ymax - ymin) > 1.5 * med_h


def _para_text(p: PdfParagraph) -> str:
    try:
        from babeldoc.format.pdf.document_il.utils.layout_helper import (
            get_paragraph_unicode,
        )

        u = get_paragraph_unicode(p)
        if u:
            return u
    except Exception:
        pass
    return getattr(p, "unicode", None) or ""


def _pullquote_host_ids(paragraphs: list[PdfParagraph]) -> set[int]:
    """Hosts whose text contains another para's text — stay out of vertical stack."""
    from babeldoc.format.pdf.document_il.utils.side_callout_skip import (
        normalize_for_dup,
    )

    texts = {id(p): normalize_for_dup(_para_text(p)) for p in paragraphs}
    hosts: set[int] = set()
    for p in paragraphs:
        pt = texts.get(id(p), "")
        if len(pt) < _MIN_PULLQUOTE_FRAGMENT:
            continue
        for q in paragraphs:
            if q is p:
                continue
            qt = texts.get(id(q), "")
            if len(qt) < _MIN_PULLQUOTE_FRAGMENT:
                continue
            if len(qt) <= len(pt) and qt in pt:
                hosts.add(id(p))
                break
    return hosts


def _can_merge_vertical(
    upper: PdfParagraph,
    lower: PdfParagraph,
    excluded: set[int] | frozenset[int] = frozenset(),
) -> bool:
    bu, bl = _box(upper), _box(lower)
    if bu is None or bl is None:
        return False
    if bu.x is None or bl.x is None or bu.y is None or bl.y2 is None:
        return False
    if _width(upper) > _MAX_LINE_WIDTH or _width(lower) > _MAX_LINE_WIDTH:
        return False
    if not _same_xobj(upper, lower):
        return False
    if _is_multi_row_block(upper) or _is_multi_row_block(lower):
        return False
    if id(upper) in excluded or id(lower) in excluded:
        return False
    if (bl.y2 or 0) >= (bu.y2 or 0) - 0.5:
        return False
    gap = float(bu.y) - float(bl.y2)
    if gap > _MAX_VERTICAL_GAP or gap < -12.0:
        return False
    if abs(float(bu.x) - float(bl.x)) > _MAX_X_DELTA and float(bl.x) + 5 < float(bu.x):
        return False
    if float(bl.x) > float(bu.x2) or float(bl.x2) < float(bu.x):
        return False
    return True


def _can_merge_right_pinned_wrap(
    upper: PdfParagraph,
    lower: PdfParagraph,
    excluded: set[int] | frozenset[int] = frozenset(),
) -> bool:
    """Stacked figure-wrap rows: right edge pinned, width up to ~280pt."""
    bu, bl = _box(upper), _box(lower)
    if bu is None or bl is None:
        return False
    if None in (bu.x, bu.x2, bu.y, bl.x, bl.x2, bl.y2):
        return False
    wu, wl = _width(upper), _width(lower)
    if wu <= 0 or wl <= 0:
        return False
    incoming = min(wu, wl)
    host_w = max(wu, wl)
    if incoming > _WRAP_LINE_MAX_WIDTH or host_w > _WRAP_HOST_MAX_WIDTH:
        return False
    if abs(float(bu.x2) - float(bl.x2)) > _WRAP_RIGHT_PIN_SPREAD:
        return False
    # Flat same-x stacks are body/callout columns (0.6.4.48). Wrap rows step.
    if abs(float(bu.x) - float(bl.x)) < 8.0:
        return False
    if not _same_xobj(upper, lower):
        return False
    # EN wrap column is often one composition spanning several visual rows
    # (OA p19 cluster y-span ~87pt). Do not use _is_multi_row_block here.
    if id(upper) in excluded or id(lower) in excluded:
        return False
    if (bl.y2 or 0) >= (bu.y2 or 0) - 0.5:
        return False
    gap = float(bu.y) - float(bl.y2)
    if gap > _MAX_VERTICAL_GAP or gap < -12.0:
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
    comps = list(paragraph.pdf_paragraph_composition or [])
    if len(comps) < 2:
        return
    paragraph.pdf_paragraph_composition = sorted(comps, key=_composition_sort_key)


def _absorb(host: PdfParagraph, other: PdfParagraph, *, unicode: str | None = None) -> None:
    """Union compositions + boxes into *host*; drop *other* must be done by caller."""
    from babeldoc.format.pdf.document_il.il_version_1 import Box

    host.pdf_paragraph_composition = list(
        host.pdf_paragraph_composition or []
    ) + list(other.pdf_paragraph_composition or [])
    hb, ob = host.box, other.box
    host.box = Box(
        x=min(float(hb.x), float(ob.x)),
        y=min(float(hb.y), float(ob.y)),
        x2=max(float(hb.x2), float(ob.x2)),
        y2=max(float(hb.y2), float(ob.y2)),
    )
    if getattr(other, "layout_label", None) in ("title", "section_header"):
        if getattr(host, "layout_label", None) not in ("title", "section_header"):
            host.layout_label = other.layout_label
    if unicode is not None:
        host.unicode = unicode
    _sort_compositions_visual(host)


# Back-compat name used by vertical passes (upper absorbs lower).
def _merge_lower_into_upper(upper: PdfParagraph, lower: PdfParagraph) -> None:
    _absorb(upper, lower)


def _column_band(a: PdfParagraph, b: PdfParagraph) -> tuple[float, float]:
    ba, bb = _box(a), _box(b)
    return min(float(ba.x), float(bb.x)), max(float(ba.x2), float(bb.x2))


def _has_intervening_paragraph(
    upper: PdfParagraph,
    lower: PdfParagraph,
    paragraphs: list[PdfParagraph],
) -> bool:
    bu, bl = _box(upper), _box(lower)
    if bu is None or bl is None:
        return True
    top = float(bu.y)
    bot = float(bl.y2)
    if top <= bot:
        return False
    x0, x1 = _column_band(upper, lower)
    from babeldoc.format.pdf.document_il.utils.region_skip import is_layout_debug_stub

    for p in paragraphs:
        if p is upper or p is lower:
            continue
        if is_layout_debug_stub(p):
            continue
        b = _box(p)
        if b is None or b.x is None or b.x2 is None or b.y is None or b.y2 is None:
            continue
        cy = 0.5 * (float(b.y) + float(b.y2))
        if not (bot < cy < top):
            continue
        if float(b.x2) < x0 or float(b.x) > x1:
            continue
        return True
    return False


def _merge_list_adjacent(
    paragraphs: list[PdfParagraph],
    excluded: set[int] | frozenset[int] = frozenset(),
) -> int:
    merges = 0
    i = 0
    while i < len(paragraphs) - 1:
        a, b = paragraphs[i], paragraphs[i + 1]
        ba, bb = _box(a), _box(b)
        if ba is None or bb is None:
            i += 1
            continue
        if (ba.y2 or 0) >= (bb.y2 or 0):
            upper, lower = a, b
        else:
            upper, lower = b, a
        if not _can_merge_vertical(upper, lower, excluded):
            i += 1
            continue
        _absorb(upper, lower)
        paragraphs.remove(lower)
        merges += 1
    return merges


def _merge_y_sorted_ultra_narrow(
    paragraphs: list[PdfParagraph],
    excluded: set[int] | frozenset[int] = frozenset(),
) -> int:
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
            upper, lower = candidates[i], candidates[i + 1]
            if upper not in paragraphs or lower not in paragraphs:
                continue
            if not _can_merge_vertical(upper, lower, excluded):
                continue
            if _has_intervening_paragraph(upper, lower, paragraphs):
                continue
            _absorb(upper, lower)
            paragraphs.remove(lower)
            merges += 1
            merged_this_pass = True
            break
        if not merged_this_pass:
            break
    return merges


def _merge_y_sorted_right_pinned_wrap(
    paragraphs: list[PdfParagraph],
    excluded: set[int] | frozenset[int] = frozenset(),
) -> int:
    """Merge right-pinned wrap-column rows (OA p19 TAKING CHARGE)."""
    from babeldoc.format.pdf.document_il.utils.region_skip import is_layout_debug_stub

    merges = 0
    while True:
        candidates = [
            p
            for p in paragraphs
            if _box(p) is not None
            and 0 < _width(p) <= _WRAP_HOST_MAX_WIDTH
            and not is_layout_debug_stub(p)
        ]
        if len(candidates) < 2:
            break
        candidates.sort(key=_y2, reverse=True)
        merged_this_pass = False
        for i in range(len(candidates) - 1):
            upper, lower = candidates[i], candidates[i + 1]
            if upper not in paragraphs or lower not in paragraphs:
                continue
            if not _can_merge_right_pinned_wrap(upper, lower, excluded):
                continue
            if _has_intervening_paragraph(upper, lower, paragraphs):
                continue
            _absorb(upper, lower)
            paragraphs.remove(lower)
            merges += 1
            merged_this_pass = True
            break
        if not merged_this_pass:
            break
    return merges


def _compact(s: str) -> str:
    """Alnum-ish compact form for prefix checks (reuse pull-quote normalizer)."""
    from babeldoc.format.pdf.document_il.utils.side_callout_skip import (
        normalize_for_dup,
    )

    return normalize_for_dup(s).rstrip(_TRAIL_PUNCT)


def _is_text_prefix(short: str, long: str) -> bool:
    """True if *short* is a meaningful prefix of *long* after compacting."""
    a, b = _compact(short), _compact(long)
    if len(a) < _H_PAIR_MIN_PREFIX or len(b) <= len(a) + 5:
        return False
    if b.startswith(a):
        return True
    for sep in (":", "：", ".", "。"):
        if sep in short:
            head = _compact(short.split(sep, 1)[0])
            return len(head) >= _H_PAIR_MIN_PREFIX and b.startswith(head)
    return False


def _y_iou(a: PdfParagraph, b: PdfParagraph) -> float:
    ba, bb = _box(a), _box(b)
    if ba is None or bb is None:
        return 0.0
    if None in (ba.y, ba.y2, bb.y, bb.y2):
        return 0.0
    y0 = max(float(ba.y), float(bb.y))
    y1 = min(float(ba.y2), float(bb.y2))
    if y1 <= y0:
        return 0.0
    ha = float(ba.y2) - float(ba.y)
    hb = float(bb.y2) - float(bb.y)
    if ha <= 0 or hb <= 0:
        return 0.0
    return (y1 - y0) / min(ha, hb)


def _can_merge_horizontal_prefix(left: PdfParagraph, right: PdfParagraph) -> bool:
    """Geometry + prefix gate for dual-column callout (left short, right fuller)."""
    bl, br = _box(left), _box(right)
    if bl is None or br is None:
        return False
    if None in (bl.x, bl.x2, br.x, br.x2):
        return False
    if float(bl.x) >= float(br.x) - 2.0:
        return False
    if float(bl.x2) > float(br.x2) + 5.0:
        return False
    lw = _width(left)
    if lw <= 0 or lw > _H_PAIR_MAX_LEFT_WIDTH:
        return False
    if _y_iou(left, right) < _H_PAIR_MIN_Y_IOU:
        return False
    if not _same_xobj(left, right):
        return False
    if _is_multi_row_block(left) and _is_multi_row_block(right):
        return False
    lt, rt = _para_text(left), _para_text(right)
    if len(lt.strip()) < _H_PAIR_MIN_PREFIX:
        return False
    return _is_text_prefix(lt, rt) or _is_text_prefix(rt, lt)


def _merge_horizontal_prefix_pairs(paragraphs: list[PdfParagraph]) -> int:
    """Absorb left short prefix column into right fuller column (or vice versa)."""
    merges = 0
    changed = True
    while changed:
        changed = False
        for left in list(paragraphs):
            for right in list(paragraphs):
                if right is left:
                    continue
                if not _can_merge_horizontal_prefix(left, right):
                    continue
                lt, rt = _para_text(left), _para_text(right)
                if len(_compact(rt)) >= len(_compact(lt)):
                    host, other, text = right, left, rt
                else:
                    host, other, text = left, right, lt
                _absorb(host, other, unicode=text)
                if other in paragraphs:
                    paragraphs.remove(other)
                merges += 1
                changed = True
                break
            if changed:
                break
    return merges


def merge_stacked_narrow_callout_paragraphs(
    paragraphs: list[PdfParagraph],
    page: Page | None = None,
) -> int:
    """In-place callout fragment merge. Returns total merge count.

    Passes:
      1. list-adjacent vertical stack (width ≤220, gap ≤22)
      2. ultra-narrow y-stack (width ≤120, no intervening)
      3. right-pinned wrap rows (width ≤280, x2 spread ≤8)
      4. horizontal prefix pair (left short ⊆ right longer text)
    """
    _ = page
    if len(paragraphs) < 2:
        return 0
    excluded = _pullquote_host_ids(paragraphs)
    merges = _merge_list_adjacent(paragraphs, excluded)
    merges += _merge_y_sorted_ultra_narrow(paragraphs, excluded)
    merges += _merge_y_sorted_right_pinned_wrap(paragraphs, excluded)
    merges += _merge_horizontal_prefix_pairs(paragraphs)
    if merges:
        logger.debug("callout_merge: merged %d units", merges)
    return merges
