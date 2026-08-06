"""Layout-First P1: pre-typeset gap_contract reservation (first pass).

Runs **before** glyph layout on each page. For every paragraph whose
``layout_intent.gap_contract`` is set (stack-bottom EN ink→ink spacing),
shifts the **next** content paragraph's ``paragraph.box`` so its planned
first-line ink top lands at::

    upper_ink_bottom − gap_contract   (PDF y-up)

**Only downward moves** (``dy < 0``): P1 reserves room for taller CJK titles;
never pull body upward into title/figure space.

**|dy| ≤ MAX_SINGLE_JUMP_DY_PT (24)** — same clamp as post-pass (plan §3.1 /
external review). Display titles are never first-pass targets
(:func:`is_gap_protected` includes ``is_display_title``).

Uses intent design_box + top/bottom_inset only (never mutates design_box).
Single next body only (cascade_len ≤ 1).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.utils.layout_audit import LayoutAuditReport
from babeldoc.format.pdf.document_il.utils.region_skip import is_chrome_paragraph
from babeldoc.format.pdf.document_il.utils.region_skip import is_layout_debug_stub
from babeldoc.format.pdf.document_il.utils.vertical_gap import MAX_SINGLE_JUMP_DY_PT
from babeldoc.format.pdf.document_il.utils.vertical_gap import find_content_below
from babeldoc.format.pdf.document_il.utils.vertical_gap import is_gap_protected
from babeldoc.format.pdf.document_il.utils.vertical_gap import layout_box

if TYPE_CHECKING:
    from babeldoc.format.pdf.document_il.il_version_1 import Page
    from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph

logger = logging.getLogger(__name__)


def _intent(para: PdfParagraph):
    return getattr(para, "layout_intent", None)


def _ink_bottom_est(para: PdfParagraph) -> float | None:
    """Estimated ink bottom (y min) from design_box + bottom_inset."""
    intent = _intent(para)
    box = layout_box(para)
    if box is None or box.y is None:
        return None
    if intent is not None:
        return float(box.y) + float(intent.bottom_inset or 0.0)
    return float(box.y)


def _ink_top_est(para: PdfParagraph) -> float | None:
    """Estimated ink top (y2 max) from design_box + top_inset."""
    intent = _intent(para)
    box = layout_box(para)
    if box is None or box.y2 is None:
        return None
    if intent is not None:
        return float(box.y2) - float(intent.top_inset or 0.0)
    return float(box.y2)


def _shift_box_y(para: PdfParagraph, dy: float) -> None:
    """Move layout box only (pre-typeset); never touch intent.design_box."""
    if abs(dy) < 0.05 or para.box is None:
        return
    if para.box.y is not None:
        para.box.y = float(para.box.y) + dy
    if para.box.y2 is not None:
        para.box.y2 = float(para.box.y2) + dy


def apply_gap_contract_first_pass(page: Page) -> LayoutAuditReport:
    """Reserve EN ink gaps on ``paragraph.box`` before glyph layout.

    Returns a :class:`LayoutAuditReport` (may be empty when no intents).
    """
    report = LayoutAuditReport(target_rule="ink_gap_relative")
    page_no = getattr(page, "page_number", None)
    phase_shifts = 0
    # One body may be the "next" of several upper carriers (title + stack
    # mid). Shift at most once so two × 24pt clamps cannot sum to −48.
    shifted_ids: set[int] = set()

    for para in page.pdf_paragraph or []:
        intent = _intent(para)
        if intent is None or intent.gap_contract is None:
            continue
        # Titles may carry gap_contract (must not *move* them as body).
        # Chrome/stubs never act as upper carriers.
        if (
            is_layout_debug_stub(para)
            or is_chrome_paragraph(para, page)
            or intent.is_chrome
        ):
            continue

        upper_box = layout_box(para)
        if upper_box is None:
            continue
        upper_ink_bottom = _ink_bottom_est(para)
        if upper_ink_bottom is None:
            continue

        # Pair with ink-bottom as the "upper" edge so next-below matches target.
        pair_box = Box(
            x=upper_box.x,
            y=upper_ink_bottom,
            x2=upper_box.x2,
            y2=upper_box.y2 if upper_box.y2 is not None else upper_ink_bottom,
        )
        nxt = find_content_below(page, para, upper_box=pair_box)
        if nxt is None or nxt.box is None:
            continue
        if is_gap_protected(nxt, page):
            continue
        nxt_id = id(nxt)
        if nxt_id in shifted_ids:
            report.record_action(
                debug_id=getattr(nxt, "debug_id", None),
                kind="gap_contract_skip_already_shifted",
                delta_pt=0.0,
                policy="first_pass_body_once",
                page_number=page_no,
                extra={
                    "upper_debug_id": getattr(para, "debug_id", None),
                    "gap_contract": float(intent.gap_contract),
                },
            )
            continue

        next_ink_top = _ink_top_est(nxt)
        if next_ink_top is None:
            continue

        gap_contract = float(intent.gap_contract)
        # Only reserve positive EN clearance (downward body move).
        if gap_contract <= 0:
            continue

        target_ink_top = upper_ink_bottom - gap_contract
        dy = target_ink_top - next_ink_top
        # Only move body down (negative dy). Never pull content upward.
        if dy >= -0.5:
            continue

        raw_dy = dy
        if abs(dy) > MAX_SINGLE_JUMP_DY_PT:
            dy = -MAX_SINGLE_JUMP_DY_PT

        _shift_box_y(nxt, dy)
        shifted_ids.add(nxt_id)
        report.record_shift(dy, cascade=1)
        phase_shifts += 1
        report.record_action(
            debug_id=getattr(nxt, "debug_id", None),
            kind="gap_contract_reservation",
            delta_pt=dy,
            policy="first_pass_down_only_clamp_24",
            page_number=page_no,
            extra={
                "upper_debug_id": getattr(para, "debug_id", None),
                "gap_contract": gap_contract,
                "target_ink_top": round(target_ink_top, 3),
                "raw_dy": round(raw_dy, 3),
                "clamped": abs(raw_dy) > MAX_SINGLE_JUMP_DY_PT + 1e-6,
            },
        )
        logger.debug(
            "gap_contract first-pass: page=%s upper=%s next=%s dy=%.2f raw=%.2f gap=%.2f",
            page_no,
            getattr(para, "debug_id", None),
            getattr(nxt, "debug_id", None),
            dy,
            raw_dy,
            gap_contract,
        )

    if page_no is not None:
        report.pages[str(page_no)] = {
            "first_pass": {
                "shifts": phase_shifts,
                "actions": len(report.actions),
            }
        }
    return report
