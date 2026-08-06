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
from babeldoc.format.pdf.document_il.utils.figure_wrap import is_figure_wrap_paragraph
from babeldoc.format.pdf.document_il.utils.layout_intent import LayoutIntentRole

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
    """
    if not widths:
        return None
    out: list[tuple[float, float]] = []
    for w in widths:
        if w is None:
            continue
        wf = float(w)
        if wf >= 8.0:
            out.append((0.0, wf))
    return out or None


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
            return list(shape)
        role = getattr(intent, "role", None)
        if role is LayoutIntentRole.WRAP_COLUMN:
            synth = shape_from_widths(_widths_from_paragraph(paragraph))
            if synth:
                return synth
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
    """Right edge pinned at ``design_box.x2``; left = right − width.

    This is EN figure-wrap geometry (left edge steps right as the column
    narrows around a photo). Not mirror taper (fixed left, shrinking right).

    ``wrap_shape`` entries are ``(left_offset, width)``; placement uses
    **width only**. Lines past the shape reuse the last width. Empty shape
    falls back to the full design box (caller should usually not call this
    without a resolved shape). ``design_box`` must be non-None.
    """
    if design_box is None:
        raise TypeError("typeset_wrap_line requires a design_box")
    if not wrap_shape:
        return float(design_box.x), float(design_box.x2)
    idx = 0 if line_idx < 0 else line_idx
    if idx >= len(wrap_shape):
        _off, width = wrap_shape[-1]
    else:
        _off, width = wrap_shape[idx]
    width = float(width)
    if width < 8.0:
        width = 8.0
    right = float(design_box.x2)
    return right - width, right


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

    Triggers when pin layout never fits, or fits only by overflowing into
    far more lines than the EN wrap shape implies.
    """
    if not wrap_shape:
        return False
    budget = wrap_line_budget(wrap_shape)
    n_lines = count_typeset_baselines(typeset_units)
    if not all_units_fit and (typeset_units is None or n_lines >= budget):
        return True
    if n_lines > budget:
        return True
    return False
