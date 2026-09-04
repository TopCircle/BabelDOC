"""Layout-First P2: wrap-column line geometry (right pin, left-edge step).

Canonical home for *consuming* ``layout_intent.wrap_shape``. Detection stays
in ``figure_wrap``; extraction stays in ``layout_intent_extractor``. Typesetting
only wires these pure helpers into the line-interval path.

Replace matrix (flag on + active wrap):

| consumer                         | with wrap                         | without wrap        |
|----------------------------------|-----------------------------------|---------------------|
| CJK ``_uniform_cjk_…``           | skip (caller sets ref widths None)| status quo          |
| zone ``_query_line_intervals``   | skipped; single pin interval      | status quo          |
| ``_cap_available_with_reference``| skipped                           | status quo          |
| pre-expand                       | skipped via ``should_skip_…``     | status quo          |
"""

from __future__ import annotations

from babeldoc.format.pdf.document_il import il_version_1
from babeldoc.format.pdf.document_il.utils.figure_wrap import body_line_widths
from babeldoc.format.pdf.document_il.utils.figure_wrap import is_figure_wrap_paragraph
from babeldoc.format.pdf.document_il.utils.figure_wrap import taper_prefix_widths
from babeldoc.format.pdf.document_il.utils.layout_intent import LayoutIntentRole
from babeldoc.format.pdf.document_il.utils.layout_intent import WrapMode

Box = il_version_1.Box
PdfParagraph = il_version_1.PdfParagraph


def layout_intent_wrap_enabled(config) -> bool:
    """``TranslationConfig.enable_layout_intent_wrap``; missing → True (P2 default)."""
    if config is None:
        return True
    return bool(getattr(config, "enable_layout_intent_wrap", True))


def shape_from_widths(
    widths: list[float] | None,
) -> list[tuple[float, float]] | None:
    """Synthesize ``(left_offset, width)`` when line boxes are missing.

    ``left_offset`` is unused by ``typeset_wrap_line`` (right-pin uses width
    only); store 0.0 so the tuple shape matches extractor output.

    Midcap slivers and non-monotonic clustered tails are dropped via
    ``taper_prefix_widths`` (else ``body_line_widths``) so OA p19 still
    synthesizes the body cone.
    """
    cleaned = taper_prefix_widths(widths) or body_line_widths(widths)
    if not cleaned:
        return None
    return [(0.0, w) for w in cleaned]


def _widths_from_paragraph(
    paragraph: PdfParagraph,
) -> list[float] | None:
    rm = getattr(paragraph, "reference_metrics", None)
    if rm is not None:
        widths = getattr(rm, "per_line_widths", None)
        if widths:
            return list(widths)
    return None


def resolve_wrap_shape(
    paragraph: PdfParagraph | None,
) -> list[tuple[float, float]] | None:
    """Best available wrap_shape: intent, then synthesized from ref widths.

    Covers WRAP_COLUMN with ``wrap_shape=None`` (e.g. post-MT, no pdf_line
    boxes at extract time) so the pin path still fires. Also synthesizes when
    ``is_figure_wrap_paragraph`` is true but intent is missing (extract skip).
    """
    if paragraph is None:
        return None
    intent = getattr(paragraph, "layout_intent", None)
    if intent is not None:
        shape = getattr(intent, "wrap_shape", None)
        if shape:
            # Re-clean zigzag intent shapes (envelope) so CJK pin path never
            # consumes clustered rises even if extract stored the raw list.
            widths = [float(w) for _o, w in shape]
            cleaned = taper_prefix_widths(widths)
            if cleaned and (
                len(cleaned) != len(widths)
                or any(abs(cleaned[i] - widths[i]) > 0.05 for i in range(len(cleaned)))
            ):
                return [(0.0, float(w)) for w in cleaned]
            return list(shape)
        role = getattr(intent, "role", None)
        mode = getattr(intent, "wrap_mode", None)
        if role is LayoutIntentRole.WRAP_COLUMN or mode in (
            WrapMode.LEFT_FIXED,
            WrapMode.RIGHT_FIXED,
        ):
            synth = shape_from_widths(_widths_from_paragraph(paragraph))
            if synth:
                return synth
            # Last resort: one pocket from design_box width (OA p59 BODY+photo).
            design = getattr(intent, "design_box", None)
            if design is not None and design.x is not None and design.x2 is not None:
                w = float(design.x2) - float(design.x)
                if w >= 8.0:
                    return [(0.0, w)]
    # Extract failed / no intent: still pin when taper/geometry detection hits.
    if is_figure_wrap_paragraph(paragraph):
        return shape_from_widths(_widths_from_paragraph(paragraph))
    return None


def get_active_wrap(
    paragraph: PdfParagraph | None,
    *,
    enabled: bool = True,
    layout_box: Box | None = None,
) -> tuple[Box, list[tuple[float, float]]] | None:
    """``(design_box, wrap_shape)`` when pin geometry should drive line intervals.

    Returns None when the flag is off, shape cannot be resolved, or no design
    box is available. Callers must not invent a (0,0) interval.
    """
    if not enabled or paragraph is None:
        return None
    shape = resolve_wrap_shape(paragraph)
    if not shape:
        return None
    intent = getattr(paragraph, "layout_intent", None)
    design = None
    if intent is not None and getattr(intent, "design_box", None) is not None:
        design = intent.design_box
    elif layout_box is not None:
        design = layout_box
    else:
        design = getattr(paragraph, "box", None)
    if design is None or design.x2 is None:
        return None
    return design, shape


def typeset_wrap_line(
    design_box: Box,
    wrap_shape: list[tuple[float, float]],
    line_idx: int,
) -> tuple[float, float]:
    """Right-pin wrap pocket (legacy API).

    New code should use ``line_interval_plan.wrap_interval`` with an explicit
    ``WrapMode``. This function keeps pre-clamp right-pin math for existing
    tests and call sites.
    """
    from babeldoc.format.pdf.document_il.utils.line_interval_plan import (
        typeset_wrap_line_legacy,
    )

    return typeset_wrap_line_legacy(design_box, wrap_shape, line_idx)


def should_skip_pre_expand_for_wrap(
    paragraph: PdfParagraph | None,
    *,
    wrap_enabled: bool = True,
) -> bool:
    """Single pre-expand skip policy for figure-wrap / WRAP_COLUMN.

    One predicate replaces the previous triple gate (wrap_shape active +
    role string + taper metrics). True when:

    1. flag on and an active wrap shape can be resolved (intent or synth); or
    2. ``is_figure_wrap_paragraph`` (taper / right-pin geometry) — legacy and
       safety when intent is missing or the flag is off.
    """
    if paragraph is None:
        return False
    if wrap_enabled and get_active_wrap(paragraph, enabled=True) is not None:
        return True
    return is_figure_wrap_paragraph(paragraph)


def wrap_line_budget(wrap_shape: list[tuple[float, float]] | None) -> int:
    """Max layout lines allowed under pin geometry before block fallback.

    EN wrap columns are short (3–6 lines). Long CJK reflow under the same
    taper (OA p82) produces dozens of needle lines that crowd the page and
    no longer mirror EN. Cap = shape length + slack, with a floor.
    """
    if not wrap_shape:
        return 10
    return max(len(wrap_shape) + 4, 10)


def count_typeset_baselines(typeset_units) -> int:
    """Distinct y baselines in a typeset unit list (approx line count)."""
    if not typeset_units:
        return 0
    ys: set[float] = set()
    for u in typeset_units:
        y = getattr(u, "y", None)
        if y is None:
            y = getattr(u, "box", None)
            if y is not None:
                y = getattr(y, "y", None)
        if y is not None:
            ys.add(round(float(y), 1))
    return len(ys)


def should_fallback_wrap_to_block(
    *,
    wrap_shape: list[tuple[float, float]] | None,
    typeset_units,
    all_units_fit: bool,
) -> bool:
    """True when CJK should abandon pin wrap and use full design width.

    Triggers when pin layout never fits, or fits only by overflowing beyond
    the translated paragraph's source wrap budget. A single extra line is
    tolerated for normal language expansion; larger growth makes reusing the
    English tail geometry unsafe, especially with CJK over figures.
    """
    if not wrap_shape:
        return False
    # ``wrap_line_budget`` keeps a generous legacy margin for rough capacity
    # estimates. This is a safety gate: once translated text exceeds the
    # source shape by more than one line, abandon stale pin geometry and let
    # the FULL_MEASURE attempt reflow.
    budget = len(wrap_shape) + 1
    n_lines = count_typeset_baselines(typeset_units)
    if not all_units_fit and (typeset_units is None or n_lines >= budget):
        return True
    if n_lines > budget:
        return True
    return False


def residual_line_budget(
    residual_width: float | None,
    para_width: float | None,
) -> int:
    """Max layout lines allowed in a figure residual strip before block fallback.

    Side-photo residual columns (~150–200pt, OA p82) are fine for short EN
    wrap captions but turn long ZH into a dense wall. Budget scales with how
    wide the residual is relative to the paragraph; near-full width → no cap.
    """
    if residual_width is None or residual_width <= 0:
        return 10
    if para_width is not None and para_width > 0:
        if residual_width >= para_width * 0.75:
            return 10_000  # effectively full measure — keep figure
        ratio = residual_width / para_width
        # At ~0.4 measure (189/460), allow ~10 lines; narrower → fewer.
        return max(6, int(round(10 * (ratio / 0.4))))
    # No para width: absolute floor from residual pt (≈ one CJK line ~12pt)
    return max(6, int(residual_width / 18.0))


def should_fallback_residual_to_block(
    *,
    residual_width: float | None,
    para_width: float | None,
    typeset_units,
    all_units_fit: bool,
) -> bool:
    """True when CJK should abandon figure residual strip for full width.

    Complements pin-wrap fallback: even with wrap_enabled=False, a kept figure
    zone still carves a ~189pt left column (OA p82). If line count exceeds the
    residual budget (or never fits), drop figures and reflow at design width.
    """
    if residual_width is None:
        return False
    if para_width is not None and para_width > 0:
        if residual_width >= para_width * 0.75:
            return False
    budget = residual_line_budget(residual_width, para_width)
    n_lines = count_typeset_baselines(typeset_units)
    if not all_units_fit and (typeset_units is None or n_lines >= budget):
        return True
    if n_lines > budget:
        return True
    return False


#: Minimum usable line-pocket width for CJK reflow (points).
#:
#: CJK full-width characters need ~2 chars to form a readable line tail; a
#: pocket narrower than this (an EN sliver such as a lone "I" or a trailing
#: fragment) can only ever hold 0–1 Chinese characters, which forces a
#: single-character orphan line (acceptance V3: 无单/双字孤行). EN
#: proportional text tolerates 1–8pt slivers, so this sanitizer is applied
#: **only** on the CJK consumption path.
CJK_WRAP_MIN_LINE_WIDTH = 24.0

#: When CJK content width is below this fraction of Σ(wrap_shape), RIGHT_FIXED
#: cones under-consume the tip (OA p19: ZH stops ~4 lines / w≈168 while EN
#: continues to ~64pt). Scale widths so reflow reaches deeper tip bands.
CJK_WRAP_UNDERCONSUME_RATIO = 0.70

#: Headroom on content width when deepening so the last line is not jammed
#: into a tip-crumb-sized pocket.
CJK_WRAP_DEEPEN_HEADROOM = 1.02


def estimate_cjk_wrap_content_width(
    paragraph: PdfParagraph | None,
    *,
    default_em: float = 12.0,
) -> float | None:
    """Rough CJK ink width (em × char count) for wrap tip-consumption deepen.

    Full-width CJK advances ≈ 1em. Used only to detect under-consumption of a
    RIGHT_FIXED cone; not a substitute for real glyph metrics.
    """
    if paragraph is None:
        return None
    uni = (getattr(paragraph, "unicode", None) or "").strip()
    if not uni:
        return None
    size = float(default_em)
    style = getattr(paragraph, "pdf_style", None)
    if style is not None:
        fs = getattr(style, "font_size", None)
        if fs:
            size = float(fs)
    return len(uni) * size


def sanitize_wrap_shape_for_cjk(
    wrap_shape: list[tuple[float, float]] | None,
    *,
    min_width: float = CJK_WRAP_MIN_LINE_WIDTH,
    wrap_mode: WrapMode | None = None,
    content_width: float | None = None,
) -> list[tuple[float, float]] | None:
    """Replace degenerate wrap pockets that CJK reflow would orphan.

    ``wrap_shape`` entries are ``(left_offset, width)`` per EN line. A width
    below ``min_width`` (~2 full-width chars) is unusable for CJK: DP/placement
    would be forced to put exactly one character on that line (OA p19 "的"
    alone at y≈542). The pocket is merged into the nearest usable line by
    borrowing the next valid width (else previous valid, else the widest valid,
    else the floor), so the surrounding text reflows onto a real line instead
    of creating an orphan.

    Trailing cone tip (OA p19 ~52–64pt): keep absolute ``min_width`` tips even
    when they fall under the relative sliver cut. Replacing them with the
    previous body width flattened RIGHT_FIXED cones to ~143pt and blocked tip
    consumption. Mid-body relative slivers (42pt shred lines) still expand.

    LEFT_FIXED tip soften (OA p59): EN tip ~67pt matches Latin ("and
    flexibility.") but CJK stacks two underfilled tip lines (~46/~68pt) because
    the remaining clause needs ~100pt. Hoist the trailing tip up to the
    penultimate width so one CJK line can fill.

    RIGHT_FIXED tip deepen (OA p19): dense CJK finishes in the upper bands
    (~4 lines / w≈168) while EN continues to the tip. When ``content_width``
    under-fills the shape, uniformly scale widths (ratios preserved — cone not
    flattened) so reflow reaches deeper tip bands, floored at ``min_width``.

    Idempotent: when every entry is already usable and no tip hoist / deepen
    applies, the input list is returned unchanged.
    """
    if not wrap_shape:
        return wrap_shape
    widths = [float(w) for _off, w in wrap_shape]
    floor_valid = [w for w in widths if w >= min_width]
    max_valid = max(floor_valid) if floor_valid else min_width
    # Relative slivers (OA p19 42pt vs 193pt peak) are usable by the 24pt
    # floor but still force a 3–4 CJK shred line. Treat < 25% of the peak
    # as degenerate too — except the trailing tip (see below).
    sliver_cut = max(min_width, max_valid * 0.25) if max_valid > 0 else min_width
    last_i = len(widths) - 1

    def _usable(w: float, i: int) -> bool:
        if w >= sliver_cut:
            return True
        # Trailing cone tip: absolute floor only (OA p19 51.6pt tip).
        return i == last_i and w >= min_width

    if all(_usable(w, i) for i, w in enumerate(widths)):
        result: list[tuple[float, float]] = wrap_shape
        unchanged = True
    else:
        valid = [w for i, w in enumerate(widths) if _usable(w, i)]
        if valid:
            max_valid = max(valid)
        result = []
        for i, (_off, w) in enumerate(wrap_shape):
            w = float(w)
            if _usable(w, i):
                result.append((_off, w))
                continue
            replacement: float | None = None
            for j in range(i + 1, len(widths)):
                if _usable(widths[j], j):
                    replacement = widths[j]
                    break
            if replacement is None:
                for j in range(i - 1, -1, -1):
                    if _usable(widths[j], j):
                        replacement = widths[j]
                        break
            if replacement is None:
                replacement = max_valid
            result.append((_off, replacement))
        unchanged = False

    # LEFT_FIXED only: hoist needle tip to penultimate (OA p59 tip underfill).
    # Keep RIGHT_FIXED cone tips (OA p19 ~64pt) intact.
    _TIP_ABS = 90.0
    _TIP_RATIO = 0.55
    if (
        wrap_mode is WrapMode.LEFT_FIXED
        and len(result) >= 2
    ):
        last_off, last_w = result[-1]
        prev_w = float(result[-2][1])
        last_w_f = float(last_w)
        if last_w_f < _TIP_ABS and last_w_f < prev_w * _TIP_RATIO:
            if unchanged:
                result = list(wrap_shape)
                unchanged = False
            result[-1] = (last_off, prev_w)

    # RIGHT_FIXED only: deepen under-consumed cones (OA p19 tip empty bands).
    if (
        wrap_mode is WrapMode.RIGHT_FIXED
        and content_width is not None
        and content_width > 0
        and len(result) >= 5
    ):
        cur_widths = [float(w) for _o, w in result]
        total = sum(cur_widths)
        if total > 0 and content_width < total * CJK_WRAP_UNDERCONSUME_RATIO:
            target = min(total, content_width * CJK_WRAP_DEEPEN_HEADROOM)
            scale = target / total
            tip = cur_widths[-1]
            # Keep tip at absolute CJK floor only — raising the floor here
            # re-blocks tip bands (OA p19 needs ~36–52pt tips reachable).
            if tip > 0 and tip * scale < min_width:
                scale = min_width / tip
            if scale < 0.97:
                if unchanged:
                    result = list(wrap_shape)
                    unchanged = False
                result = [
                    (off, max(min_width, float(w) * scale))
                    for off, w in result
                ]

            # After deepen, a needle tip (<~3.5 CJK cells) strands end-of-
            # paragraph leftovers as 双字孤行 (OA p19 「下去」) because V3
            # orphan pull-back skips the final units. Hoist to penultimate.
            if len(result) >= 2:
                last_off, last_w = result[-1]
                prev_w = float(result[-2][1])
                last_w_f = float(last_w)
                _SAFE_TIP = max(min_width * 1.75, 42.0)
                if last_w_f < _SAFE_TIP and last_w_f < prev_w * 0.55:
                    result[-1] = (last_off, prev_w)

    if unchanged:
        return wrap_shape
    return result
