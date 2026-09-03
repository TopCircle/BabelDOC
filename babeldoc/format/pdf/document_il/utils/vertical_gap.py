"""Title→body vertical gap (Layout-First P1).

P1 transition (layout-first-plan §6):
- End state: zero mutual paragraph shifts after typesetting.
- **P1 allows** post-typeset emergency repair: single hop, ``|dy| ≤ 24pt``,
  cascade length ≤ 1, never chrome / display-title / subtitle_overlay.
- Target gap is **relative EN ink gap** from ``layout_intent.gap_contract``
  (resolved on title **or** nearest upper stack-bottom that carries it).

Shared geometry helpers (:func:`boxes_x_overlap`, :func:`find_content_below`,
:func:`resolve_en_gap_contract`, :func:`gap_deficit`) are the single source
for first-pass reservation and post-pass repair.

Legacy unrestricted cascade lives in :func:`enforce_title_body_gaps_legacy`
for Δ comparison until P3.
"""

from __future__ import annotations

import logging

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import Page
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.utils.layout_audit import LayoutAuditReport
from babeldoc.format.pdf.document_il.utils.layout_intent import LayoutIntentRole
from babeldoc.format.pdf.document_il.utils.region_skip import is_chrome_paragraph
from babeldoc.format.pdf.document_il.utils.region_skip import is_layout_debug_stub

logger = logging.getLogger(__name__)

# Fallback when no gap_contract is resolvable.
DEFAULT_MIN_GAP_PT = 14.0
# P1 post-pass single-jump clamp (plan §6 / coding-plan §3.1).
MAX_SINGLE_JUMP_DY_PT = 24.0
# Relative acceptance epsilon for gap_deficit.
RELATIVE_GAP_EPS_PT = 2.0
# Treat as display title when max rendered size reaches this.
DISPLAY_TITLE_SIZE_PT = 28.0
_TITLE_LABELS = frozenset({"title", "section_header"})
_X_OVERLAP_SLACK = 8.0


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


def boxes_x_overlap(a: Box, b: Box, *, slack: float = _X_OVERLAP_SLACK) -> bool:
    """Public x-overlap test (slack default matches historical vertical_gap)."""
    return a.x < b.x2 + slack and a.x2 > b.x - slack


# Back-compat alias used inside this module and older call sites.
def _x_overlap(a: Box, b: Box, *, slack: float = _X_OVERLAP_SLACK) -> bool:
    return boxes_x_overlap(a, b, slack=slack)


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


def measured_ink_gap(upper: PdfParagraph, lower: PdfParagraph) -> float | None:
    """Ink-to-ink gap: upper.ink.y − lower.ink.y2 (positive = clearance)."""
    u = ink_box(upper)
    lo = ink_box(lower)
    if u is None or lo is None:
        return None
    return float(u.y) - float(lo.y2)


def gap_deficit(
    zh_gap: float,
    en_gap: float | None,
    *,
    fallback: float = DEFAULT_MIN_GAP_PT,
    eps: float = RELATIVE_GAP_EPS_PT,
) -> float:
    """How many pt of additional clearance ZH still needs (0 = ok).

    Single source for relative-EN acceptance:
    ``need = max(en_gap, 0)`` when EN is known, else ``fallback``.
    Deficit = max(0, need - eps - zh_gap).
    """
    if en_gap is None:
        need = float(fallback)
    else:
        need = max(float(en_gap), 0.0)
    return max(0.0, need - float(eps) - float(zh_gap))


def relative_gap_ok(
    zh_gap: float,
    en_gap: float | None,
    *,
    eps: float = RELATIVE_GAP_EPS_PT,
    fallback: float = DEFAULT_MIN_GAP_PT,
) -> bool:
    """True when :func:`gap_deficit` is zero."""
    return gap_deficit(zh_gap, en_gap, fallback=fallback, eps=eps) <= 0.0


def resolve_en_gap_contract(
    upper: PdfParagraph,
    page: Page | None = None,
) -> float | None:
    """EN ink gap for *upper* → content below.

    Resolution order (review fix: contract may sit on stack-bottom, not title):
    1. ``upper.layout_intent.gap_contract`` if set
    2. Walk paragraphs that x-overlap and sit at/above *upper*, prefer those
       with ``gap_contract`` whose design/ink bottom is nearest above the body
       (same column). For a display title this finds the stack-bottom carrier.
    """
    intent = getattr(upper, "layout_intent", None)
    if intent is not None and intent.gap_contract is not None:
        return float(intent.gap_contract)

    if page is None:
        return None

    upper_box = _layout_box(upper)
    if upper_box is None:
        return None

    best: tuple[float, float] | None = None  # (proximity, gap)
    for cand in page.pdf_paragraph or []:
        c_intent = getattr(cand, "layout_intent", None)
        if c_intent is None or c_intent.gap_contract is None:
            continue
        cbox = _layout_box(cand)
        if cbox is None or not boxes_x_overlap(upper_box, cbox):
            continue
        # Prefer carriers at/above upper (same stack / title band).
        if cbox.y2 is not None and upper_box.y2 is not None:
            if float(cbox.y2) < float(upper_box.y) - 1.0:
                continue  # clearly below upper — not a carrier for this pair
        proximity = abs(float(cbox.y or 0) - float(upper_box.y or 0))
        gap = float(c_intent.gap_contract)
        if best is None or proximity < best[0]:
            best = (proximity, gap)
    return best[1] if best else None


def layout_box(para: PdfParagraph) -> Box | None:
    """design_box when present, else paragraph.box (shared layout geometry)."""
    intent = getattr(para, "layout_intent", None)
    if intent is not None and intent.design_box is not None:
        return intent.design_box
    return para.box


# Back-compat private alias
_layout_box = layout_box


def _is_subtitle_overlay_role(para: PdfParagraph) -> bool:
    intent = getattr(para, "layout_intent", None)
    return (
        intent is not None and intent.role is LayoutIntentRole.SUBTITLE_OVERLAY
    )


def is_gap_protected(para: PdfParagraph, page: Page | None = None) -> bool:
    """True for segments that must not be moved or used as gap 'body'.

    Covers chrome/stubs, subtitle_overlay/title roles, **and** geometric
    display titles (``is_display_title``) so large section headers are never
    treated as the next body by first-pass or post-pass (external P1 review).
    """
    if is_layout_debug_stub(para):
        return True
    if page is not None and is_chrome_paragraph(para, page):
        return True
    if is_display_title(para):
        return True
    intent = getattr(para, "layout_intent", None)
    if intent is not None:
        if intent.is_chrome:
            return True
        if intent.role in (
            LayoutIntentRole.CHROME,
            LayoutIntentRole.SUBTITLE_OVERLAY,
            LayoutIntentRole.TITLE,
            LayoutIntentRole.SECTION_HEADER,
        ):
            return True
    return False


def body_fully_inside_title_band(tbox: Box, cbox: Box) -> bool:
    return (cbox.y or 0) >= (tbox.y or 0) - 0.5 and (
        cbox.y2 or 0
    ) <= (tbox.y2 or 0) + 0.5


def find_content_below(
    page: Page,
    upper: PdfParagraph,
    *,
    upper_box: Box | None = None,
    ink: dict[int, Box] | None = None,
) -> PdfParagraph | None:
    """Nearest non-protected paragraph strictly below *upper* (x-overlap).

    Shared by first-pass reservation and post-pass title→body pairing.
    Display titles / chrome / stubs are excluded via :func:`is_gap_protected`.
    When *ink* is provided, uses rendered ink boxes; else layout/design boxes.
    """
    ubox = upper_box or (ink.get(id(upper)) if ink else None) or _layout_box(upper)
    if ubox is None or ubox.y is None:
        return None
    upper_top = float(ubox.y2) if ubox.y2 is not None else float(ubox.y)

    best: tuple[float, PdfParagraph] | None = None
    for cand in page.pdf_paragraph or []:
        if cand is upper:
            continue
        if is_gap_protected(cand, page):
            continue

        if ink is not None and id(cand) in ink:
            cbox = ink[id(cand)]
        else:
            cbox = _layout_box(cand)
        if cbox is None or cbox.y2 is None:
            continue
        # Strictly below upper top band.
        if float(cbox.y2) >= upper_top - 0.5:
            continue
        # Prefer content that is not fully inside the upper ink band (overlay).
        if body_fully_inside_title_band(ubox, cbox):
            continue
        if not boxes_x_overlap(ubox, cbox):
            continue
        if best is None or float(cbox.y2) > best[0]:
            best = (float(cbox.y2), cand)
    return best[1] if best else None


def enforce_title_body_gaps(
    page: Page,
    *,
    min_gap: float = DEFAULT_MIN_GAP_PT,
    max_dy: float = MAX_SINGLE_JUMP_DY_PT,
    report: LayoutAuditReport | None = None,
) -> LayoutAuditReport:
    """P1: audit + limited single-hop repair (no follower cascade).

    Returns a :class:`LayoutAuditReport`. For the pre-P1 cascade behaviour
    use :func:`enforce_title_body_gaps_legacy`.
    """
    if report is None:
        report = LayoutAuditReport(target_rule="ink_gap_relative")
    page_no = getattr(page, "page_number", None)
    post_shifts_before = report.shifts

    paras = [
        p
        for p in (page.pdf_paragraph or [])
        if p.pdf_paragraph_composition and not is_layout_debug_stub(p)
    ]
    if len(paras) < 2:
        return report

    ink: dict[int, Box] = {}
    for p in paras:
        box = ink_box(p)
        if box is not None:
            ink[id(p)] = box

    ordered = sorted(
        [p for p in paras if id(p) in ink],
        key=lambda p: (-(ink[id(p)].y2 or 0.0), ink[id(p)].x or 0.0),
    )

    for title in ordered:
        if not is_display_title(title):
            continue
        body = find_content_below(
            page,
            title,
            upper_box=ink[id(title)],
            ink=ink,
        )
        if body is None or id(body) not in ink:
            continue
        if is_gap_protected(body, page):
            continue

        tbox = ink[id(title)]
        bbox = ink[id(body)]
        en_gap = resolve_en_gap_contract(title, page)
        title_bottom = float(tbox.y)
        body_top = float(bbox.y2)
        zh_gap = title_bottom - body_top

        deficit = gap_deficit(zh_gap, en_gap, fallback=min_gap)
        if deficit <= 0:
            continue

        # Move body down by deficit (negative dy in PDF y-up).
        dy = -deficit
        raw_dy = dy
        if abs(dy) > max_dy:
            dy = -max_dy

        shift_paragraph_y(body, dy)
        new_ink = ink_box(body)
        if new_ink is not None:
            ink[id(body)] = new_ink
        report.record_shift(dy, cascade=1)
        report.record_violation(
            debug_id=getattr(body, "debug_id", None),
            kind="gap",
            delta_pt=dy,
            policy="single_jump_clamp_24",
            page_number=page_no,
            extra={
                "title_debug_id": getattr(title, "debug_id", None),
                "en_gap": en_gap,
                "zh_gap_before": round(zh_gap, 3),
                "deficit": round(deficit, 3),
                "raw_dy": round(raw_dy, 3),
                "clamped": abs(raw_dy) > max_dy + 1e-6,
            },
        )
        logger.debug(
            "title-body gap P1: page=%s dy=%.1f (raw=%.1f) en_gap=%s deficit=%.1f",
            page_no,
            dy,
            raw_dy,
            en_gap,
            deficit,
        )

    if page_no is not None:
        phase_shifts = report.shifts - post_shifts_before
        report.pages[str(page_no)] = {
            **(report.pages.get(str(page_no)) or {}),
            "post_pass": {
                "shifts": phase_shifts,
                "violations": len(report.violations),
            },
        }
    return report


def enforce_title_body_gaps_legacy(
    page: Page,
    *,
    min_gap: float = DEFAULT_MIN_GAP_PT,
) -> int:
    """Pre-P1 cascade behaviour (follower chains, global min_gap).

    Kept for Δ comparison until P3 zero-mutual-shift lands. Prefer
    :func:`enforce_title_body_gaps` on the production path.
    """
    paras = [
        p
        for p in (page.pdf_paragraph or [])
        if p.pdf_paragraph_composition and not is_layout_debug_stub(p)
    ]
    if len(paras) < 2:
        return 0

    ink: dict[int, Box] = {}
    for p in paras:
        box = ink_box(p)
        if box is not None:
            ink[id(p)] = box

    ordered = sorted(
        [p for p in paras if id(p) in ink],
        key=lambda p: (-(ink[id(p)].y2 or 0.0), ink[id(p)].x or 0.0),
    )

    shifted = 0
    for i, title in enumerate(ordered):
        if not is_display_title(title):
            continue
        tbox = ink[id(title)]
        body = None
        for cand in ordered[i + 1 :]:
            cbox = ink[id(cand)]
            if (cbox.y2 or 0) >= (tbox.y2 or 0) - 0.5:
                continue
            if not boxes_x_overlap(tbox, cbox):
                continue
            if body_fully_inside_title_band(tbox, cbox):
                continue
            if is_display_title(cand) and max_font_size(cand) >= max_font_size(title) * 0.85:
                continue
            if is_chrome_paragraph(cand, page):
                continue
            body = cand
            break
        if body is None:
            continue

        bbox = ink[id(body)]
        title_bottom = float(tbox.y)
        body_top = float(bbox.y2)
        target_top = title_bottom - min_gap
        if body_top <= target_top + 0.5:
            continue

        dy = target_top - body_top
        to_shift = [body]
        for cand in ordered:
            if cand is body or cand is title:
                continue
            cbox = ink[id(cand)]
            if (cbox.y2 or 0) > body_top + 1:
                continue
            if not boxes_x_overlap(bbox, cbox):
                continue
            if is_display_title(cand):
                continue
            if is_chrome_paragraph(cand, page):
                continue
            to_shift.append(cand)

        for p in to_shift:
            shift_paragraph_y(p, dy)
            new_ink = ink_box(p)
            if new_ink is not None:
                ink[id(p)] = new_ink
            shifted += 1

        logger.debug(
            "title-body gap legacy: page=%s shifted=%d dy=%.1f",
            getattr(page, "page_number", None),
            len(to_shift),
            dy,
        )

    return shifted
