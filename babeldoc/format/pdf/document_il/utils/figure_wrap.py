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

Decorative mid-caps titles (OA p19 ``t``/``ak``/``I``/``ng `` fragments,
widths ~3–42pt) often share the same paragraph as the wrap body. Those
slivers must be stripped before taper / pin geometry checks, otherwise
detection fails and CJK falls back to a flat BODY pin on the photo.

Fallback-line clustering can also split the wrap *tail* into non-monotonic
chunks (OA p19 ``…51.6, 99.6, 63.0``). Detection uses the longest monotonic
taper *prefix* so a noisy tail cannot kill WRAP_COLUMN.
"""

from __future__ import annotations

from babeldoc.format.pdf.document_il import il_version_1

# Midcap / page-number fragments vs wrap body (OA p19: midcaps ≤42pt,
# body peak ~259pt, taper tip ~64pt). Keep lines at least this fraction of
# the peak (and never below an absolute floor that still admits taper tips).
_BODY_WIDTH_PEAK_RATIO = 0.20
_BODY_WIDTH_ABS_FLOOR = 48.0
_TAPER_MIN_STEP = 8.0


def body_line_widths(reference_widths) -> list[float]:
    """Drop decorative midcap / page-number slivers; keep wrap-body widths.

    Used by taper detection, wrap_shape synth, and line-box pin checks so
    OA p19's TAKING CHARGE midcaps cannot poison the body taper.
    """
    if not reference_widths:
        return []
    usable = [
        float(w) for w in reference_widths if w is not None and float(w) >= 12.0
    ]
    if not usable:
        return []
    peak = max(usable)
    floor = max(_BODY_WIDTH_ABS_FLOOR, peak * _BODY_WIDTH_PEAK_RATIO)
    return [w for w in usable if w >= floor]


def body_line_spans(
    lines: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    """Same midcap filter for ``(x, x2)`` line spans."""
    if not lines:
        return []
    widths = [float(x2) - float(x) for x, x2 in lines]
    kept_w = body_line_widths(widths)
    if not kept_w:
        return []
    # Preserve order; match by width membership with multiplicity.
    remaining = list(kept_w)
    out: list[tuple[float, float]] = []
    for (x, x2), w in zip(lines, widths, strict=False):
        wf = float(w)
        for i, kw in enumerate(remaining):
            if abs(kw - wf) <= 0.05:
                out.append((float(x), float(x2)))
                del remaining[i]
                break
    return out


def _is_strict_taper(usable: list[float]) -> bool:
    """True when *usable* alone is a 3+ line monotonic figure-wrap taper."""
    if len(usable) < 3:
        return False
    distinct = len({round(w, 1) for w in usable})
    if distinct < 3:
        return False
    for a, b in zip(usable, usable[1:], strict=False):
        if b > a - _TAPER_MIN_STEP:
            return False
    return usable[-1] < usable[0] * 0.75


def taper_prefix_widths(reference_widths) -> list[float]:
    """Longest contiguous body-width window that forms a figure-wrap taper.

    Midcaps are stripped first. A non-monotonic clustered *tail* is dropped so
    OA p19 ``[254.6…142.6, 51.6, 99.6, 63.0]`` still yields the real cone. A
    short rising/flat *head* is also skipped so OA p59
    ``[213.8, 216.8, 218.3, 207.7…66]`` keeps the LEFT_FIXED cone.
    """
    usable = body_line_widths(reference_widths)
    if len(usable) < 3:
        return []
    best: list[float] = []
    n = len(usable)
    for start in range(n - 2):
        for end in range(start + 3, n + 1):
            window = usable[start:end]
            if _is_strict_taper(window) and len(window) >= len(best):
                best = window
    return best


def is_figure_wrap_taper(reference_widths) -> bool:
    """True when per-line widths form a genuine figure-wrap taper.

    A real taper has 3+ distinct, monotonically decreasing lines with every
    step >= 8pt and a clearly short tail. English body paragraphs have ONE
    short last line ([467,467,258]) and flat narrow columns stay flat
    ([180,180,175,100]) — neither is a taper.

    Decorative midcap prefixes and noisy clustered tails are ignored via
    ``taper_prefix_widths``.
    """
    return bool(taper_prefix_widths(reference_widths))


def is_figure_wrap_paragraph(para: il_version_1.PdfParagraph) -> bool:
    """Single entry point: is *para* a figure-wrap (taper) column?

    Either signal marks a wrap column:

    1. ``reference_metrics.per_line_widths`` taper — captured before
       translation, survives ILTranslator, so it works at quote-zone build
       time (after translation destroyed ``pdf_line`` compositions) and in
       typesetting.
    2. Pre-MT line-box geometry: multi-line with one edge pinned (<=4pt
       spread) and the free edge stepping (>=12pt). Right-pinned / left-
       stepping is OA p19 (photo on the left). Left-pinned / right-stepping
       is OA p59 (photo on the right).

    Signal 2 is also the fallback for noisy reference widths (fallback-line
    clustering can split a wrap tail into odd word chunks, e.g. OA p19
    ``the work plans...`` → [52, 100, 63]) — the geometry still shows the
    wrap shape, and aligned body lines never match it.
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
    lines = body_line_spans([(float(a), float(b)) for a, b in lines])
    if len(lines) < 2:
        return False
    xs = [float(l[0]) for l in lines]
    x2s = [float(l[1]) for l in lines]
    left_spread = max(xs) - min(xs)
    right_spread = max(x2s) - min(x2s)
    right_fixed = left_spread >= 12.0 and right_spread <= 4.0
    left_fixed = right_spread >= 12.0 and left_spread <= 4.0
    return right_fixed or left_fixed
