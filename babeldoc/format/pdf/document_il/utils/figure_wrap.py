"""Single source of truth for figure-wrap column detection.

Figure-wrap columns (text designed over a side photo, e.g. Orgasmic
Addiction p19 TAKING CHARGE) pin the right edge at the page margin while
stepping the left edge right line by line. They must not be treated as
pull-quotes, must not be pre-expanded left over the photo, and their
per-line reference widths must be preserved so CJK follows the wrap.

Canonical examples (per-line widths):
  taper TRUE : [194, 174, 143, 67]      # OA p19 TAKING CHARGE
  taper FALSE: [467, 467, 258]          # EN body, one short last line
  taper FALSE: [180, 180, 175, 100]     # flat narrow figure column
"""

from __future__ import annotations

from babeldoc.format.pdf.document_il import il_version_1


def is_figure_wrap_taper(reference_widths) -> bool:
    """True when per-line widths form a genuine figure-wrap taper.

    A real taper has 3+ distinct, monotonically decreasing lines with every
    step >= 8pt and a clearly short tail. English body paragraphs have ONE
    short last line ([467,467,258]) and flat narrow columns stay flat
    ([180,180,175,100]) — neither is a taper.
    """
    if not reference_widths:
        return False
    usable = [float(w) for w in reference_widths if w is not None and float(w) >= 12.0]
    if len(usable) < 3:
        return False
    distinct = len({round(w, 1) for w in usable})
    if distinct < 3:
        return False
    for a, b in zip(usable, usable[1:]):
        if b > a - 8.0:
            return False
    return usable[-1] < usable[0] * 0.75


def is_figure_wrap_paragraph(para: il_version_1.PdfParagraph) -> bool:
    """Single entry point: is *para* a figure-wrap (taper) column?

    Either signal marks a wrap column:

    1. ``reference_metrics.per_line_widths`` taper — captured before
       translation, survives ILTranslator, so it works at quote-zone build
       time (after translation destroyed ``pdf_line`` compositions) and in
       typesetting.
    2. Pre-MT line-box geometry: multi-line with the left edge stepping right
       (>=12pt spread) while the right edge stays pinned (<=4pt spread).

    Signal 2 is also the fallback for noisy reference widths (fallback-line
    clustering can split a wrap tail into odd word chunks, e.g. OA p19
    ``the work plans...`` → [52, 100, 63]) — the geometry still shows the
    right-pinned wrap shape, and aligned body lines never match it.
    """
    rm = getattr(para, "reference_metrics", None)
    if rm is not None:
        widths = getattr(rm, "per_line_widths", None) or []
        if is_figure_wrap_taper(widths):
            return True
        # not a clear taper — fall through to line-box geometry (noisy
        # reference widths are possible for fallback-clustered tails)

    lines = []
    for comp in getattr(para, "pdf_paragraph_composition", None) or []:
        line = getattr(comp, "pdf_line", None)
        if line is None or getattr(line, "box", None) is None:
            continue
        if line.box.x is None or line.box.x2 is None:
            continue
        lines.append((line.box.x, line.box.x2))
    if len(lines) < 2:
        return False
    xs = [float(l[0]) for l in lines]
    x2s = [float(l[1]) for l in lines]
    left_spread = max(xs) - min(xs)
    right_spread = max(x2s) - min(x2s)
    return left_spread >= 12.0 and right_spread <= 4.0
