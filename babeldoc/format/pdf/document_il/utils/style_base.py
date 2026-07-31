"""Robust paragraph base style (drop-cap / size outliers).

``StylesAndFormulas._calculate_base_style`` previously took a style
intersection then filled None fields with a mode over *all* chars. A single
large drop-cap (Trajan ``I`` / ``W``) can pollute font_id or leave a bad
intersection path when sizes disagree.

Policy (PR-1):
  1. Mode of font sizes over the paragraph
  2. Drop chars whose size is far from that mode (high/low), if they are a
     small fraction of the run (≤15%)
  3. Single-letter high-size glyphs always count as drop-cap outliers
  4. Recompute intersection + mode on the filtered set
  5. Title/section_header with large median size: do not strip high outliers
     that are not single-letter drop-caps (avoid crushing true big titles)
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence

from babeldoc.format.pdf.document_il.il_version_1 import GraphicState
from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle

# Sizes above mode * HIGH or below mode * LOW are outlier candidates.
SIZE_HIGH_RATIO = 1.4
SIZE_LOW_RATIO = 0.6
# Only apply filtering when outliers are a minority.
MAX_OUTLIER_FRACTION = 0.15
# Title-like labels with large median: keep multi-glyph large runs.
_TITLE_LABELS = frozenset({"title", "section_header"})
_TITLE_PROTECT_MEDIAN_PT = 14.0


def mode_value(values: Sequence) -> object | None:
    """Most common value; None if empty. Ties → first most_common entry."""
    cleaned = [v for v in values if v is not None]
    if not cleaned:
        return None
    return Counter(cleaned).most_common(1)[0][0]


def _merge_graphic_states(
    state1: GraphicState | None, state2: GraphicState | None
) -> GraphicState | None:
    if state1 is None:
        return state2
    if state2 is None:
        return state1
    return GraphicState(
        passthrough_per_char_instruction=(
            state1.passthrough_per_char_instruction
            if state1.passthrough_per_char_instruction
            == state2.passthrough_per_char_instruction
            else None
        ),
    )


def merge_styles(style1: PdfStyle | None, style2: PdfStyle | None) -> PdfStyle | None:
    """Intersection of two styles (same contract as StylesAndFormulas)."""
    if style1 is None or style1.font_size is None:
        return style2
    if style2 is None or style2.font_size is None:
        return style1
    return PdfStyle(
        font_id=style1.font_id if style1.font_id == style2.font_id else None,
        font_size=(
            style1.font_size
            if math.fabs(style1.font_size - style2.font_size) < 0.02
            else None
        ),
        graphic_state=_merge_graphic_states(
            style1.graphic_state, style2.graphic_state
        ),
    )


def _is_single_letter(u: str | None) -> bool:
    if not u:
        return False
    t = u.strip()
    return len(t) == 1 and t.isalpha()


def filter_styles_for_base(
    styles: Sequence[PdfStyle | None],
    *,
    layout_label: str | None = None,
    char_unicodes: Sequence[str | None] | None = None,
) -> list[PdfStyle]:
    """Return styles with drop-cap / size outliers removed when safe.

    If filtering would remove more than ``MAX_OUTLIER_FRACTION`` of samples,
    returns the original non-None styles unchanged.
    """
    pairs: list[tuple[PdfStyle, str | None]] = []
    for i, s in enumerate(styles):
        if s is None:
            continue
        u = char_unicodes[i] if char_unicodes is not None and i < len(char_unicodes) else None
        pairs.append((s, u))
    if not pairs:
        return []

    sizes = [s.font_size for s, _ in pairs if s.font_size is not None]
    if not sizes:
        return [s for s, _ in pairs]

    size_mode = mode_value(sizes)
    if size_mode is None or not isinstance(size_mode, (int, float)) or size_mode <= 0:
        return [s for s, _ in pairs]
    size_mode = float(size_mode)

    ordered = sorted(float(x) for x in sizes)
    median = ordered[len(ordered) // 2]
    label = (layout_label or "").strip().lower()
    protect_large_runs = (
        label in _TITLE_LABELS and median >= _TITLE_PROTECT_MEDIAN_PT
    )

    kept: list[PdfStyle] = []
    n_out = 0
    for s, u in pairs:
        sz = s.font_size
        if sz is None:
            kept.append(s)
            continue
        sz = float(sz)
        is_high = sz > size_mode * SIZE_HIGH_RATIO
        is_low = sz < size_mode * SIZE_LOW_RATIO
        drop_cap = is_high and _is_single_letter(u)
        if protect_large_runs and is_high and not drop_cap:
            kept.append(s)
            continue
        if is_high or is_low:
            n_out += 1
            continue
        kept.append(s)

    if not kept:
        return [s for s, _ in pairs]
    if n_out / len(pairs) > MAX_OUTLIER_FRACTION:
        return [s for s, _ in pairs]
    return kept


def calculate_base_style(
    styles: Sequence[PdfStyle | None],
    *,
    layout_label: str | None = None,
    char_unicodes: Sequence[str | None] | None = None,
) -> PdfStyle | None:
    """Base style: intersection on filtered styles, mode fill for None fields.

    Only ``font_id`` / ``font_size`` are filled from the filtered set (PR-1);
    graphic_state still follows intersection (color left for PR-1b).
    """
    work = filter_styles_for_base(
        styles, layout_label=layout_label, char_unicodes=char_unicodes
    )
    if not work:
        return None

    base = work[0]
    for style in work[1:]:
        base = merge_styles(base, style)
    if base is None:
        return None

    # Mode fill on *filtered* set (not full paragraph).
    if base.font_id is None:
        base.font_id = mode_value([s.font_id for s in work])  # type: ignore[assignment]
    if base.font_size is None:
        base.font_size = mode_value([s.font_size for s in work])  # type: ignore[assignment]
    return base
