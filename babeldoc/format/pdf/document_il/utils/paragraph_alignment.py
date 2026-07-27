"""Paragraph horizontal alignment from original PDF geometry.

Extracted from ``layout_helper`` so alignment policy (page-symmetric center
vs body-column flush-left) stays in one focused module.

Public API:
  - ``detect_paragraph_alignment``
  - ``dominant_body_column_left``
  - ``flush_with_body_column``
"""

from __future__ import annotations

from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph


def _line_ranges(para: PdfParagraph) -> list[tuple[float, float]]:
    """Lazy import avoids circular load with layout_helper."""
    from babeldoc.format.pdf.document_il.utils.layout_helper import (
        _line_x_ranges_from_para,
    )

    return _line_x_ranges_from_para(para)


def dominant_body_column_left(
    page,
    exclude: PdfParagraph | None = None,
    *,
    edge_tolerance: float = 8.0,
    min_strong_lines: int = 3,
) -> float | None:
    """Left edge of the page's main text column, if detectable.

    Collects multi-line paragraphs whose lines share a left edge (ebook body).
    Single-line headings are ignored so a run of short titles does not define
    the column.  Tapering centered blocks (arXiv affil) are skipped when line
    lefts disagree by more than *edge_tolerance*.

    Evidence threshold:
      * ≥2 body peers → median left (stable)
      * exactly 1 peer with ≥ *min_strong_lines* lines → use that left
        (short pages / sparse body still demote long section heads)
      * otherwise → ``None`` (keep pure page-symmetric center)

    Returns:
        Body left in page coords, or ``None`` if not enough evidence.
    """
    paras = getattr(page, "pdf_paragraph", None) if page is not None else None
    if not paras:
        return None

    # (left_edge, line_count) for each qualifying multi-line body peer
    peers: list[tuple[float, int]] = []
    for p in paras:
        if p is exclude:
            continue
        ranges = _line_ranges(p)
        n_lines = len(ranges)
        if n_lines < 2:
            continue
        line_lefts = [x for x, _ in ranges]
        if max(line_lefts) - min(line_lefts) > edge_tolerance:
            continue  # not a shared column edge
        peers.append((min(line_lefts), n_lines))

    if not peers:
        return None
    if len(peers) == 1:
        left, n_lines = peers[0]
        if n_lines >= min_strong_lines:
            return left
        return None

    lefts = sorted(left for left, _ in peers)
    return lefts[len(lefts) // 2]


def flush_with_body_column(
    line_ranges: list[tuple[float, float]],
    body_left: float | None,
    *,
    edge_tolerance: float = 8.0,
) -> bool:
    """True when every line starts on the page body column.

    A long left-aligned line that starts at body column C with width ≈
    page_width − 2C has lm≈rm and mid≈page center — pure page-symmetric
    geometry cannot tell it from a designed centered title.  Sharing the
    body column left edge is the distinguishing signal (Day6 MOREGASM TIP 2
    vs arXiv figure dual title).
    """
    if body_left is None or not line_ranges:
        return False
    return all(abs(x - body_left) <= edge_tolerance for x, _ in line_ranges)


def detect_paragraph_alignment(
    para: PdfParagraph,
    page=None,
    *,
    edge_tolerance: float = 8.0,
    page_center_tolerance: float = 20.0,
) -> str:
    """Detect horizontal alignment from original paragraph geometry.

    Prefer edge consistency over "L≈R within bbox" (which falsely marks
    left-aligned body text as center: full lines have lm≈rm≈0, and a short
    last line creates width variation).

    Multi-line rules (priority):
      1. Line left edges cluster  → left
      2. Line right edges cluster → right
      3. Line centers cluster AND short lines are inset on both sides → center

    Single-line / fallback:
      - page-centered short line → center
      - **except** lines flush with the page body column → left
        (long ebook section heads can look page-symmetric by length alone)
      - default → left

    Note: layout_label == "title" is NOT forced to center. Many ebooks use
    left-aligned section headings that DocLayout still labels "title"; forcing
    center made those headings (and short labels like "IMPORTANT NOTE:") float
    to the middle of their original wide box after translation.

    Returns:
        One of "left", "center", "right".
    """
    line_ranges = _line_ranges(para)
    if not line_ranges:
        return "left"

    para_left = min(x for x, _ in line_ranges)
    para_right = max(x2 for _, x2 in line_ranges)
    para_width = para_right - para_left
    if para_width <= 1:
        return "left"

    tol = max(edge_tolerance, para_width * 0.03)
    n = len(line_ranges)
    lefts = [x for x, _ in line_ranges]
    rights = [x2 for _, x2 in line_ranges]
    centers = [(x + x2) / 2.0 for x, x2 in line_ranges]
    widths = [x2 - x for x, x2 in line_ranges]
    max_w = max(widths)

    def _cluster_ratio(values: list[float], ref: float) -> float:
        if not values:
            return 0.0
        return sum(1 for v in values if abs(v - ref) <= tol) / len(values)

    page_box = None
    if page is not None:
        if getattr(page, "cropbox", None) and page.cropbox.box:
            page_box = page.cropbox.box
        elif getattr(page, "mediabox", None) and page.mediabox.box:
            page_box = page.mediabox.box

    body_left = dominant_body_column_left(
        page, para, edge_tolerance=edge_tolerance
    )

    def _page_symmetric_centered() -> bool:
        """True when every line is roughly page-centered with symmetric margins.

        Catches arXiv-style multi-line headers (title/author/affil/date) where
        successive lines share a similar left edge *relative to the para bbox*
        (so left_ratio is high) but each line is still centered on the page.
        Must not match left-column body (asymmetric page margins) or near-full
        justified body lines.

        All Tied Up book p4 (above Nice Rack): 2–3 EN body lines at x≈56 with
        width ~80% of page have lm≈rm and centers near mid-page. That is
        *flush-left full-measure body*, not a centered header — reject when
        lines share a left edge and the longest is still wide.

        Day6-style section heads at the body column (x≈102) can also look
        page-symmetric when the EN line is long; reject via body-column flush.
        """
        if page_box is None or page_box.x2 <= page_box.x:
            return False
        if flush_with_body_column(
            line_ranges, body_left, edge_tolerance=edge_tolerance
        ):
            return False
        page_center = (page_box.x + page_box.x2) / 2.0
        page_width = page_box.x2 - page_box.x
        # Flush-left wide body: shared left edge + long measure (ebook body).
        # arXiv author/affil lines *vary* their left edge as they taper.
        if len(line_ranges) >= 2:
            line_lefts = [x for x, _ in line_ranges]
            line_ws = [x2 - x for x, x2 in line_ranges]
            shared_left = (max(line_lefts) - min(line_lefts)) <= tol
            if shared_left and max(line_ws) >= page_width * 0.72:
                return False
        for x, x2 in line_ranges:
            w = x2 - x
            # 0.78: near-full body (ATU ~0.80–0.82) must not count as centered
            # header; keep true titles under that threshold.
            if w > page_width * 0.78:
                return False
            line_center = (x + x2) / 2.0
            if abs(line_center - page_center) > page_center_tolerance:
                return False
            lm = x - page_box.x
            rm = page_box.x2 - x2
            # Require both margins and near-symmetry (page-centered, not column)
            if lm < 40.0 or rm < 40.0:
                return False
            if abs(lm - rm) > max(page_center_tolerance * 2, page_width * 0.06):
                return False
        return True

    page_sym = _page_symmetric_centered()

    if n >= 2:
        # 0) Page-symmetric multi-line header (arXiv affil+date, author block)
        # before left-edge clustering — those lines share a para-left edge
        # but are still page-centered.
        if page_sym:
            return "center"

        # 1) Shared left edge → left-aligned body (most common)
        # Use the leftmost edge as reference (flush-left column).
        # Slightly lenient (0.65): InDesign ebooks often have one wrap line
        # inset by a few points without being true center text.
        left_ratio = _cluster_ratio(lefts, para_left)
        if left_ratio >= 0.65:
            return "left"

        # 2) Shared right edge → right-aligned
        right_ratio = _cluster_ratio(rights, para_right)
        if right_ratio >= 0.7:
            return "right"

        # 3) Shared centers + short lines inset both sides → center
        # Median center is robust when one line is an outlier
        sorted_centers = sorted(centers)
        mid_c = sorted_centers[len(sorted_centers) // 2]
        center_ratio = _cluster_ratio(centers, mid_c)
        if center_ratio >= 0.75:
            # Longest line nearly fills the paragraph span → body, not
            # a centered pull-quote/title block (Orgasms p.11 step body).
            if max_w >= para_width * 0.85 and left_ratio >= 0.4:
                return "left"

            # Require at least one clearly short line that is inset on BOTH
            # sides. Full lines always have lm≈rm≈0 and must not alone prove
            # center (that was the body-text false positive).
            short_both_inset = 0
            short_total = 0
            for x, x2 in line_ranges:
                w = x2 - x
                if w >= max_w * 0.9:
                    continue  # nearly full-width line
                short_total += 1
                lm = x - para_left
                rm = para_right - x2
                if lm > tol and rm > tol and abs(lm - rm) <= tol * 2:
                    short_both_inset += 1
            # Need a clear majority of short lines inset both sides
            if short_total >= 2 and short_both_inset >= max(2, int(short_total * 0.6)):
                return "center"
            # Centers align but short lines flush-left → still left
            return "left"

    # Single-line or ambiguous multi-line: use page geometry
    if page_box is not None and page_box.x2 > page_box.x:
        page_center = (page_box.x + page_box.x2) / 2.0
        page_width = page_box.x2 - page_box.x
        # True page-centered titles (arXiv golden figure): L≈R margins both
        # substantial (e.g. lm=rm≈64 for a 484pt title on letter).
        # Flush-left ebook body/heads (ATU): lm≈56 on the body column while
        # mid may still sit near page center for long lines — require BOTH
        # margins ≥ ~60 and near-equal, not just mid≈page_center.
        all_centered = True
        for x, x2 in line_ranges:
            line_center = (x + x2) / 2.0
            line_width = x2 - x
            lm = x - page_box.x
            rm = page_box.x2 - x2
            if abs(line_center - page_center) > page_center_tolerance:
                all_centered = False
                break
            # Near-full-page lines are body text, not centered titles
            if line_width > page_width * 0.85:
                all_centered = False
                break
            # Designed center has real inset on both sides (arXiv ≥~60).
            # ATU body/heads at x≈56 fail this (lm too small / unequal).
            if lm < 60.0 or rm < 60.0:
                all_centered = False
                break
            if abs(lm - rm) > max(page_center_tolerance, page_width * 0.04):
                all_centered = False
                break
        if all_centered:
            # Long left-aligned head at body column C with width ≈ page−2C
            # looks page-symmetric but must stay left (Day6 TIP 2).
            if flush_with_body_column(
                line_ranges, body_left, edge_tolerance=edge_tolerance
            ):
                return "left"
            return "center"

    return "left"

