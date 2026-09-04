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
    """True when *usable* alone is a 3+ line monotonic figure-wrap taper.

    Every step must be non-increasing. At least two steps must drop by
    ``_TAPER_MIN_STEP`` so a single short last line ([467,467,258]) stays
    false, while a gentle cone with small intermediate steps (OA p59
    ``[237.5, 227.9, 223.4…193]``) still counts.
    """
    if len(usable) < 3:
        return False
    distinct = len({round(w, 1) for w in usable})
    if distinct < 3:
        return False
    drops = [a - b for a, b in zip(usable, usable[1:], strict=False)]
    # Allow tiny float noise upward; anything larger is not a taper.
    if any(d < -0.05 for d in drops):
        return False
    if sum(1 for d in drops if d >= _TAPER_MIN_STEP) < 2:
        return False
    peak = max(usable)
    # Prefer a clearly short tip; also accept a solid absolute drop when the
    # clustered tip lines were dropped from reference_metrics (OA p59 often
    # logs [218…172] without the 66pt tip).
    return usable[-1] < peak * 0.80 or (peak - usable[-1]) >= 40.0


def _taper_envelope_from_peak(usable: list[float]) -> list[float]:
    """Soft free-edge max envelope when clustered widths have no clean window.

    Fallback-line clustering on OA p19/p59 injects mid-paragraph rises so no
    contiguous strict taper exists, yet WRAP_COLUMN geometry still detected a
    pin. Without this envelope, ``layout_intent`` keeps the raw zigzag
    ``wrap_shape`` and CJK left/right edges wander (p59 left spread ~120pt).

    Plain peak→cummin locks onto transient narrow spikes (OA p59 ~89pt dip that
    recovers to ~210), producing a steeper cone than EN's gentle free-edge
    profile and needle tips (~63–86pt). Soften by taking a short look-ahead
    **max** (free-edge upper hull per band) before cummin so left-pinned wraps
    keep design.x≈102 with EN-like right clearance, while genuine unrecovered
    tips (OA p19 ~52pt) still taper.
    """
    if len(usable) < 3:
        return []
    peak_i = max(range(len(usable)), key=lambda i: usable[i])
    seq = usable[peak_i:]
    if len(seq) < 3:
        return []
    # Look-ahead max band (i..i+2): free-edge upper hull, then cummin.
    _LOOKAHEAD = 2
    n = len(seq)
    softened = [
        max(float(w) for w in seq[i : min(i + 1 + _LOOKAHEAD, n)])
        for i in range(n)
    ]
    out = [softened[0]]
    for w in softened[1:]:
        out.append(min(out[-1], w))
    # Collapse plateaus from rises that cummin flattened, keep a compact cone.
    compact = [out[0]]
    for w in out[1:]:
        if abs(w - compact[-1]) >= 1.0:
            compact.append(w)
    if _is_strict_taper(compact):
        return compact
    if _is_strict_taper(out):
        return out
    return []


def taper_prefix_widths(reference_widths) -> list[float]:
    """Longest contiguous body-width window that forms a figure-wrap taper.

    Midcaps are stripped first. A non-monotonic clustered *tail* is dropped so
    OA p19 ``[254.6…142.6, 51.6, 99.6, 63.0]`` still yields the real cone. A
    short rising/flat *head* is also skipped so OA p59
    ``[213.8, 216.8, 218.3, 207.7…66]`` keeps the LEFT_FIXED cone.

    When clustering leaves *no* contiguous taper window (OA p19/p59 zigzag
    shapes that still pass pin geometry), fall back to a soft free-edge max
    envelope so WRAP_COLUMN still gets a gentle cone instead of a needle.
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
    if best:
        # OA p19 clustered tip crumb: strict window ends at ~51.6 then usable
        # recovers to 99.6→63. Prefer soft envelope tip so CJK does not lock
        # onto the crumb needle (prior: prefer [...99.6, 63.0] over ...51.6).
        end = None
        for i in range(len(usable) - len(best) + 1):
            if all(abs(usable[i + j] - best[j]) <= 0.05 for j in range(len(best))):
                end = i + len(best)
                break
        if (
            end is not None
            and end < len(usable)
            and float(usable[end]) > float(best[-1]) + 8.0
        ):
            env = _taper_envelope_from_peak(usable)
            if env and len(env) >= 3 and float(env[-1]) >= 24.0:
                return env
        return best
    return _taper_envelope_from_peak(usable)


def is_figure_wrap_tip_crumb(
    para: il_version_1.PdfParagraph,
    *,
    page_width: float = 612.0,
) -> bool:
    """True for OA p19 cone-tip leftovers (``，使``) that must not typeset.

    LayoutParser labels tip word fragments ``fallback_line``; after MT they
    become 1–4 char pull-quote-shaped crumbs right-pinned at the wrap tip.
    """
    if page_width <= 0:
        return False
    label = (getattr(para, "layout_label", None) or "").strip().lower()
    uni = (getattr(para, "unicode", None) or "").strip()
    box = getattr(para, "box", None)
    if box is None or box.x is None or box.x2 is None:
        return False
    width = float(box.x2) - float(box.x)
    right_gap = float(page_width) - float(box.x2)
    # Right-pinned tip sliver (OA p19: x≈502..570, w≈67).
    if width > 90.0:
        return False
    if right_gap > float(page_width) * 0.12:
        return False
    # Stub class-name unicode is not a crumb.
    if uni.lower() in {"fallback_line", "plain text", "title"}:
        return False
    # Pre-MT tip fragments can be a few English words ("make the"); post-MT
    # they shrink to 「，使」. Label + tip geometry is the stable signal.
    if label == "fallback_line":
        return True
    if uni and len(uni) <= 4 and width <= 40.0:
        return True
    if not uni and width <= 40.0:
        return True
    return False


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
