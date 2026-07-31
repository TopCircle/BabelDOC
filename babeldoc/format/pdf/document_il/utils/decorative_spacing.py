"""Decorative letter-spacing detection and word-gap policy.

Design PDFs (e.g. OA Microstyle titles) use large tracking between letters.
Uniform tracking must not invent word spaces (``G e n t l y``); bimodal gaps
still need word boundaries (``Who···has···orgasms``).
"""

from __future__ import annotations

from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter


def is_decorative_text(chars: list[PdfCharacter]) -> bool:
    """Detect decorative/artistic text layouts like 'G e n t l y'.

    All conditions must hold simultaneously:
      1. ≥70% of characters are single letters
      2. ≥50% of inter-character gaps exceed 2× average char width
      3. Font size consistency: max/min ratio < 1.10
      4. Baseline consistency: max baseline spread < 1pt
    """
    if len(chars) < 3:
        return False

    pdf_chars = [c for c in chars if isinstance(c, PdfCharacter) and c.visual_bbox]
    if len(pdf_chars) < 3:
        return False

    single_letter_count = sum(
        1
        for c in pdf_chars
        if len((c.char_unicode or "").strip()) == 1
        and (c.char_unicode or "").strip().isalpha()
    )
    if single_letter_count / len(pdf_chars) < 0.7:
        return False

    large_gap_count = 0
    total_gaps = 0
    for i in range(len(pdf_chars) - 1):
        c1, c2 = pdf_chars[i], pdf_chars[i + 1]
        gap = c2.visual_bbox.box.x - c1.visual_bbox.box.x2
        if gap <= 0:
            continue
        total_gaps += 1
        w1 = c1.visual_bbox.box.x2 - c1.visual_bbox.box.x
        w2 = c2.visual_bbox.box.x2 - c2.visual_bbox.box.x
        avg_w = (w1 + w2) / 2
        if avg_w > 0 and gap > avg_w * 2.0:
            large_gap_count += 1

    if total_gaps < 2 or large_gap_count / total_gaps < 0.5:
        return False

    sizes = [
        c.pdf_style.font_size
        for c in pdf_chars
        if c.pdf_style and c.pdf_style.font_size
    ]
    if sizes:
        min_s, max_s = min(sizes), max(sizes)
        if min_s > 0 and max_s / min_s > 1.10:
            return False

    baselines = [c.visual_bbox.box.y for c in pdf_chars]
    if baselines and (max(baselines) - min(baselines)) > 1.0:
        return False

    return True


def decorative_word_gap_threshold(chars: list[PdfCharacter]) -> float | None:
    """Gap (pt) at/above which a decorative run has a *word* boundary.

    Uniform tracking (max ≈ median) → ``None`` (no word spaces).
    Bimodal gaps → threshold for outliers only.
    """
    pdf_chars = [c for c in chars if isinstance(c, PdfCharacter) and c.visual_bbox]
    if len(pdf_chars) < 3:
        return None
    gaps: list[float] = []
    widths: list[float] = []
    for i in range(len(pdf_chars) - 1):
        c1, c2 = pdf_chars[i], pdf_chars[i + 1]
        gap = c2.visual_bbox.box.x - c1.visual_bbox.box.x2
        if gap <= 0:
            continue
        gaps.append(gap)
        w1 = c1.visual_bbox.box.x2 - c1.visual_bbox.box.x
        w2 = c2.visual_bbox.box.x2 - c2.visual_bbox.box.x
        widths.append(max(w1, w2))
    if len(gaps) < 2:
        return None
    ordered = sorted(gaps)
    mid = len(ordered) // 2
    median = (
        ordered[mid]
        if len(ordered) % 2 == 1
        else (ordered[mid - 1] + ordered[mid]) / 2
    )
    avg_w = sum(widths) / len(widths) if widths else 0.0
    if ordered[-1] < median * 1.35 + 0.5:
        return None
    return max(median * 1.75, avg_w * 1.2 if avg_w > 0 else 0.0, 2.0)


def compute_decorative_tracking(chars: list[PdfCharacter]) -> float | None:
    """Average inter-character gap (pt), or None if insufficient data."""
    pdf_chars = [c for c in chars if isinstance(c, PdfCharacter) and c.visual_bbox]
    if len(pdf_chars) < 2:
        return None
    gaps = []
    for i in range(len(pdf_chars) - 1):
        gap = pdf_chars[i + 1].visual_bbox.box.x - pdf_chars[i].visual_bbox.box.x2
        if gap > 0:
            gaps.append(gap)
    return sum(gaps) / len(gaps) if gaps else None


def gap_is_decorative_word_boundary(
    distance: float,
    decorative_word_gap: float | None,
) -> bool:
    """True when *distance* is a word gap under decorative letter-spacing."""
    if decorative_word_gap is None:
        return False
    return distance >= decorative_word_gap
