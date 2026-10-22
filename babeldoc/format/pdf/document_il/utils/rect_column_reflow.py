"""Reflow a rectangular column from the source column, not each English line.

Paragraphs that share a column use that column's left and right edges.
Stacked source lines of one paragraph become one Chinese run: lines fill
the column, and only the last line stays short. A narrowing cone keeps
its own box and pin. A short Chinese column then opens down the English
column, and each line stays inside the source line at that height.
"""

from __future__ import annotations

import unicodedata

from babeldoc.format.pdf.document_il.utils.layout_intent import LayoutIntentRole
from babeldoc.format.pdf.document_il.utils.layout_intent import WrapMode
from babeldoc.format.pdf.document_il.utils.placement_paradigm import ParadigmMark
from babeldoc.format.pdf.document_il.utils.placement_paradigm import PlacementParadigm

_X_OVERLAP = 0.35
_WIDE_FRACTION = 0.72
# A short source line sits inside the column. A photo step is farther in.
_SAME_LEFT_SLACK = 48.0
# Gap between two line boxes of one paragraph is smaller than a paragraph break.
_CONTINUE_GAP = 8.0
# Same paragraph may step in for a hang or a photo shoulder. A new column is farther.
_HANGING_INDENT = 72.0
# Display quotes and titles are larger than body. Body-sized labels are column prose.
_BODY_FONT_MAX = 16.0
# Large type in the left gutter is a quote beside the column, not a member of it.
_GUTTER_X = 120.0
_GUTTER_MAX_W = 220.0
# A body-sized quote in the left gutter, beside a wider paragraph. The
# centered-quote test wants a deep indent; this one starts at the margin
# and stops before the hanging body. Taller than this is a column.
_SIDE_QUOTE_X = 72.0
_SIDE_QUOTE_MIN_W = 160.0
_SIDE_QUOTE_MAX_W = 260.0
_SIDE_QUOTE_MIN_H = 28.0
_SIDE_QUOTE_MAX_H = 96.0
# One body line is shorter than this. Used only when the source size is missing.
_BODY_LINE_MAX = 22.0
# A hole taller than this is unused source box, not a paragraph break.
_OPEN_GAP = 48.0
# Space left between two blocks of the same column after the hole is closed.
_FOLLOW_GAP = 18.0
# A line this much narrower than the line above is a short tail, not the photo edge.
_TAIL_FRACTION = 0.45
# Open leading at most this many times the leading the typesetter just used.
_MAX_OPEN_RATIO = 2.0
# Extra space between paragraphs, as a fraction of the line step.
_PARA_EXTRA = 0.4
_CROSS_SLACK = 4.0
# Source line boxes captured before the column box is widened. Not on the IL.
# Keyed by id because PdfParagraph is a slots dataclass and cannot be weak-referenced.
# A later page must not drop these: its flow runs after the widths are cleared.
_PROFILES: dict[int, list] = {}
_SIGS: dict[int, str] = {}
_SKIP_ROLES = frozenset(
    {
        LayoutIntentRole.CHROME,
        LayoutIntentRole.FORMULA,
        LayoutIntentRole.TITLE,
        LayoutIntentRole.PULL_QUOTE,
        LayoutIntentRole.FIGURE_CAPTION,
        LayoutIntentRole.DROPCAP,
        LayoutIntentRole.SECTION_HEADER,
        LayoutIntentRole.CALLOUT,
    }
)
# Ordinary column lines are often labeled formula, callout, or pull quote.
_MISREAD_ROLES = frozenset(
    {
        LayoutIntentRole.FORMULA,
        LayoutIntentRole.CALLOUT,
        LayoutIntentRole.PULL_QUOTE,
    }
)
_FILL_ROLES = frozenset(
    {
        LayoutIntentRole.BODY,
        LayoutIntentRole.LIST,
        LayoutIntentRole.WRAP_COLUMN,
    }
)


# Paragraphs that own a display band. Not on the IL. Ids stay for the
# process so a later page flow does not drop them; tests forget their own.
_DISPLAY_IDS: set[int] = set()
# Page id -> (bottom, top, left, right). A bar uses the graphic, not the
# paragraph box, so an expanded title cannot enlarge the reserved band.
# A mark in the margin does not share that x, and is left where it is.
_PAGE_BANDS: dict[int, list[tuple[float, float, float, float]]] = {}
# A filled bar is one text line tall, not a page background or a photo.
_BAR_MIN_H = 8.0
_BAR_MAX_H = 56.0
_BAR_MIN_W = 80.0
_BAR_PAGE_FRACTION = 0.15
# White under a filled bar. English leaves about 10pt; the font paints
# about 2pt past the line box, so the stop sits a little further down.
_BAR_CLEAR = 12.0
# A list marker is about one em. A quotation mark is much wider.
_MARKER_HANG_MAX = 36.0
# Continuation text still needs a few glyphs after the marker indent.
_MIN_HUNG_BODY = 48.0


def stays_in_source_box(paragraph) -> bool:
    """Painted on a figure, or sitting in a title / quote / bar band."""
    intent = getattr(paragraph, "layout_intent", None)
    if getattr(intent, "text_on_photo", False):
        return True
    return id(paragraph) in _DISPLAY_IDS


def forget_display_bands(paragraphs, page=None) -> None:
    """Drop display marks for paragraphs a test is finished with."""
    for paragraph in paragraphs or []:
        _DISPLAY_IDS.discard(id(paragraph))
    if page is not None:
        _PAGE_BANDS.pop(id(page), None)


def drop_below_display_band(
    paragraph, y: float, line_h: float, page, span=None
) -> float:
    """Move a line that lands in someone else's band to just below it.

    The paragraph that owns the band stays. A paragraph whose source box
    sits entirely above the band stays above it, so one sentence is not
    split across a title. Other lines continue underneath. ``span`` is
    this line's own width. The paragraph box is wider when the contour
    steps, and that union must not drop a line that stops short of the band.
    """
    if page is None or id(paragraph) in _DISPLAY_IDS:
        return y
    bands = _PAGE_BANDS.get(id(page), ())
    if not bands:
        return y
    step = max(float(line_h), 1.0)
    if span is not None:
        x0, x1 = float(span[0]), float(span[1])
    else:
        box = getattr(paragraph, "box", None)
        x0 = float(box.x) if box is not None and box.x is not None else None
        x1 = float(box.x2) if box is not None and box.x2 is not None else None
    for _ in range(4):
        top = y + step
        hit = None
        for band_y, band_y2, band_x, band_x2 in bands:
            if not _overlaps_x(x0, x1, band_x, band_x2):
                continue
            if top <= band_y + 0.5 or y >= band_y2 - 0.5:
                continue
            # This paragraph sits above the band. Do not continue it
            # underneath — that splits one sentence across the title.
            if _source_sits_above(paragraph, band_y2):
                continue
            hit = band_y - step
            break
        if hit is None or hit == y:
            return y
        y = hit
    return y


def is_gutter_display(paragraph) -> bool:
    """True when large type sits in the left gutter, beside the column."""
    if _source_font_size(paragraph) <= _BODY_FONT_MAX:
        return False
    box = getattr(paragraph, "box", None)
    if box is None or box.x is None or box.x2 is None:
        return False
    width = float(box.x2) - float(box.x)
    return float(box.x) < _GUTTER_X and 0.0 < width < _GUTTER_MAX_W


def keep_gutter_displays(page) -> None:
    """Leave a gutter quote in its own box. Do not walk it into the column."""
    for paragraph in getattr(page, "pdf_paragraph", None) or []:
        if not is_gutter_display(paragraph):
            continue
        intent = getattr(paragraph, "layout_intent", None)
        if intent is None:
            continue
        intent.wrap_mode = WrapMode.NONE
        intent.wrap_shape = None
        intent.expansion_policy = ()
        intent.overflow_policy = "scale_down"


def uses_rect_column_fill(paragraph) -> bool:
    """True when this paragraph should fill one left-aligned column."""
    if id(paragraph) in _DISPLAY_IDS:
        return False
    if is_gutter_display(paragraph):
        return False
    intent = getattr(paragraph, "layout_intent", None)
    if (
        intent is None
        or getattr(intent, "text_on_photo", False)
        or _is_narrowing_cone(paragraph)
    ):
        return False
    role = getattr(intent, "role", None)
    if role in _SKIP_ROLES:
        # A body-sized line with a formula / callout / quote label still fills.
        return _is_misread_column_prose(paragraph)
    mark = getattr(intent, "paradigm_mark", None)
    paradigm = getattr(mark, "paradigm", None) if mark is not None else None
    if paradigm is PlacementParadigm.SHAPED_POCKET and role not in _FILL_ROLES:
        # No measured lines, and not body/list: leave the stored pin alone.
        return len(_line_widths(paragraph)) >= 2
    if paradigm is PlacementParadigm.RECT_REFLOW or role in _FILL_ROLES:
        return True
    return False


def assign_rect_columns(paragraphs) -> None:
    """Give each rectangular column one shared left and right edge."""
    chosen = [p for p in _candidates(paragraphs) if _has_text(p)]
    for group in _cluster(chosen):
        _apply_group(group)


def mark_display_bands(page) -> None:
    """Titles, large quotes, and text on a short filled bar own their band."""
    bars = _filled_bars(page)
    page_w = _page_width(page)
    found: list[tuple[float, float, float, float]] = []
    for paragraph in getattr(page, "pdf_paragraph", None) or []:
        band = _display_band(paragraph, bars, page_w)
        if band is None and _is_side_gutter_quote(paragraph, page):
            box = paragraph.box
            band = (float(box.y), float(box.y2), None)
        if band is None:
            # Keep the mark in its own box, but do not open a hole under it.
            if _is_narrow_mark(paragraph) and _source_font_size(paragraph) >= 28.0:
                _DISPLAY_IDS.add(id(paragraph))
            else:
                _DISPLAY_IDS.discard(id(paragraph))
            continue
        bottom, top, bar = band
        _DISPLAY_IDS.add(id(paragraph))
        band_x, band_x2 = _band_x(paragraph, bar)
        if bar is not None and getattr(paragraph, "box", None) is not None:
            # Typeset this run inside the graphic, flush left, like the English bar.
            paragraph.box.x = float(bar.x)
            paragraph.box.y = float(bar.y)
            paragraph.box.x2 = float(bar.x2)
            paragraph.box.y2 = float(bar.y2)
            paragraph.alignment = "left"
        if bar is not None:
            bottom -= _BAR_CLEAR
        elif _source_font_size(paragraph) >= 28.0:
            # The painted letters hang below the box. Keep the next line clear.
            bottom -= max(18.0, _source_font_size(paragraph) * 0.55)
        found.append((bottom, top, band_x, band_x2))
    _PAGE_BANDS[id(page)] = found


def yield_to_display_bands(page) -> None:
    """Keep other paragraphs out of a display band.

    A line that sits in the band moves below it. A paragraph that only
    crosses one edge stops at that edge. A paragraph that runs well above
    and well below the band is left whole; line layout steps over the band
    so those glyphs continue on the other side.
    """
    bands = _PAGE_BANDS.get(id(page), ())
    if not bands:
        return
    for paragraph in getattr(page, "pdf_paragraph", None) or []:
        if id(paragraph) in _DISPLAY_IDS:
            continue
        box = getattr(paragraph, "box", None)
        if box is None or box.y is None or box.y2 is None:
            continue
        for band_y, band_y2, band_x, band_x2 in bands:
            _yield_box(box, band_y, band_y2, band_x, band_x2)


def prepare_rect_columns(docs) -> None:
    """Join stacked column lines before translation.

    A list item split into an English line each would otherwise be translated
    as fragments, then drawn back together in the wrong order.
    """
    for page in getattr(docs, "page", None) or []:
        mark_display_bands(page)
        yield_to_display_bands(page)
        flow_rect_columns(page.pdf_paragraph)


def flow_rect_columns(paragraphs) -> None:
    """Join stacked lines, then typeset them on the column measure."""
    if not paragraphs:
        return
    for paragraph in paragraphs:
        if uses_rect_column_fill(paragraph):
            _cover_ink(paragraph)
    chosen = _candidates(paragraphs)
    for paragraph in chosen:
        _remember(paragraph)
    absorbed: set[int] = set()
    for group in _cluster(chosen):
        _join_continuations(group, absorbed)
        _join_across_display(group, paragraphs, absorbed)
    if absorbed:
        kept = [p for p in paragraphs if id(p) not in absorbed]
        paragraphs[:] = kept
    assign_rect_columns(paragraphs)
    for paragraph in paragraphs:
        if uses_rect_column_fill(paragraph) and _has_text(paragraph):
            _release_old_line_path(paragraph)


def close_rect_column_gaps(paragraphs, page=None) -> None:
    """Move the next same-column block up when the one above ended early.

    A display band between the two blocks is a stop. The lower block may
    rise to the band, and no further.
    """
    if not paragraphs:
        return
    bands = _PAGE_BANDS.get(id(page), ()) if page is not None else ()
    spans: dict[int, tuple[float, float, float]] = {}
    chosen = []
    for paragraph in paragraphs:
        if not uses_rect_column_fill(paragraph):
            continue
        span = _ink_span(paragraph)
        if span is None:
            continue
        chosen.append(paragraph)
        spans[id(paragraph)] = span
    for group in _cluster(chosen):
        ordered = sorted(group, key=lambda p: -spans[id(p)][1])
        for index in range(len(ordered) - 1):
            upper = ordered[index]
            lower = ordered[index + 1]
            moved = _raise_into_gap(paragraphs, page, bands, spans, upper, lower)
            if moved is None:
                continue
            spans[id(lower)] = moved


def _raise_into_gap(paragraphs, page, bands, spans, upper, lower):
    """Shift the lower block up, or return None when it has to stay."""
    bottom, _top, left = spans[id(upper)]
    low_bottom, low_top, low_left = spans[id(lower)]
    if low_left - left > _SAME_LEFT_SLACK:
        return None
    gap = bottom - low_top
    if gap <= _OPEN_GAP:
        return None
    if _gap_blocked(paragraphs, upper, lower, bottom, low_top):
        return None
    if _span_blocked(page, lower, bottom, low_top):
        return None
    target = _stop_at_band(lower, bands, low_top, gap)
    dy = target - low_top
    if dy <= 1.0:
        return None
    _shift_up(lower, dy)
    return (low_bottom + dy, low_top + dy, low_left)


def _stop_at_band(lower, bands, low_top: float, gap: float) -> float:
    """Rise stops at a display band that shares this column's x."""
    target = low_top + gap - _FOLLOW_GAP
    low_x = float(lower.box.x) if lower.box.x is not None else None
    low_x2 = float(lower.box.x2) if lower.box.x2 is not None else None
    for band_y, _band_y2, band_x, band_x2 in bands:
        if not _overlaps_x(low_x, low_x2, band_x, band_x2):
            continue
        if low_top < band_y - 0.5 and target > band_y + 0.5:
            target = band_y
    return target


def source_profile(paragraph):
    """Source line boxes kept for this column run. Tests and settle read this."""
    return _stored_profile(paragraph)


def settle_rect_columns(paragraphs, page=None) -> None:
    """Open a short Chinese column so it occupies the English column band."""
    if not paragraphs:
        return
    chosen = []
    for paragraph in paragraphs:
        if uses_rect_column_fill(paragraph) and _chars_in_order(paragraph):
            chosen.append(paragraph)
    for group in _cluster(chosen):
        _settle_group(group, page)
    _push_glyphs_below_bands(paragraphs, page)
    _flush_bar_titles(paragraphs, page)


def _settle_group(group, page=None) -> None:
    samples = _group_samples(group)
    measure = _drop_tails(samples)
    if len(measure) < 2:
        return
    band_bottom = min(sample[0] for sample in samples)
    band_top = max(sample[1] for sample in samples)
    ordered = _order_group(group)
    natural = _natural_step(ordered)
    if natural <= 0.0 or band_top - band_bottom < natural * 3:
        return
    # A quote between the two halves is a hole, not empty leading.
    # Reflow at the body step and let each line step over that hole.
    if _spans_display_band(ordered, page):
        _apply_placed(_place_group(ordered, measure, band_top, natural, page))
        return
    if _already_settled(ordered, measure, band_bottom):
        return
    _apply_placed(_opened(ordered, measure, band_top, band_bottom, natural, page))


def _opened(ordered, measure, band_top: float, band_bottom: float, natural: float, page=None):
    """Largest leading that still ends inside the English column.

    A bigger step fills the empty band. A step that passes the band bottom
    is discarded, so the last line does not land on the footer.
    """
    placed = _place_group(ordered, measure, band_top, natural, page)
    if _last_bottom(placed) < band_bottom:
        return placed
    lo = natural
    hi = natural * _MAX_OPEN_RATIO
    best = placed
    for _ in range(8):
        if hi - lo < 0.4:
            break
        step = (lo + hi) / 2.0
        trial = _place_group(ordered, measure, band_top, step, page)
        if _last_bottom(trial) >= band_bottom:
            best = trial
            lo = step
        else:
            hi = step
    return best


def _already_settled(ordered, measure, band_bottom: float) -> bool:
    bottoms = []
    for _paragraph, chars in ordered:
        for char in chars:
            bottoms.append(float(char.box.y))
        if _crosses(chars, measure):
            return False
    if not bottoms:
        return True
    return min(bottoms) - band_bottom <= _OPEN_GAP


def _crosses(chars, measure) -> bool:
    for _top, row in _rows(chars):
        y = sum(float(c.box.y) + float(c.box.y2) for c in row) / (2 * len(row))
        left, right = _edges(measure, y)
        ink_left = min(float(c.box.x) for c in row)
        ink_right = max(float(c.box.x2) for c in row)
        if ink_right > right + _CROSS_SLACK or ink_left < left - _CROSS_SLACK:
            return True
    return False


def _remember(paragraph) -> None:
    key = id(paragraph)
    fresh = _samples(paragraph)
    sig = _signature(paragraph)
    existing = _PROFILES.get(key)
    if existing and _SIGS.get(key) == sig and _keeps(existing, fresh):
        return
    _PROFILES[key] = fresh
    _SIGS[key] = sig


def _signature(paragraph) -> str:
    return _plain(paragraph).replace("\n", "").replace("\r", "")[:160]


def _keeps(existing, fresh) -> bool:
    """Keep a detailed profile when this paragraph is measured again."""
    if len(existing) < len(fresh):
        return False
    if len(fresh) != 1:
        return abs(existing[0][1] - fresh[0][1]) < 1.0
    top = max(sample[1] for sample in existing)
    bottom = min(sample[0] for sample in existing)
    # A later pass may widen the column box. It still covers these lines.
    return fresh[0][1] >= top - 1.0 and fresh[0][0] <= bottom + 1.0


def _merge_profile(host, nxt) -> None:
    host_samples = list(_PROFILES.get(id(host), ()))
    nxt_samples = list(_PROFILES.get(id(nxt), ()))
    if host_samples or nxt_samples:
        _PROFILES[id(host)] = host_samples + nxt_samples
    _PROFILES.pop(id(nxt), None)
    _SIGS.pop(id(nxt), None)
    _SIGS[id(host)] = _signature(host)


def _samples(paragraph):
    box = paragraph.box
    widths = _line_widths(paragraph)
    if len(widths) >= 2 and max(widths) - min(widths) >= 12.0:
        offsets = _line_offsets(paragraph)
        if len(offsets) != len(widths):
            offsets = []
        return _spread_lines(box, widths, offsets, _wrap_mode(paragraph))
    return [_box_sample(box)]


def _spread_lines(box, widths, offsets, mode):
    span = float(box.y2) - float(box.y)
    step = span / len(widths)
    samples = []
    for index, width in enumerate(widths):
        top = float(box.y2) - index * step
        bottom = top - step
        if mode is WrapMode.RIGHT_FIXED:
            right = float(box.x2)
            left = right - width
        else:
            offset = offsets[index] if index < len(offsets) else 0.0
            left = float(box.x) + offset
            right = left + width
        if right - left >= 8.0:
            samples.append((bottom, top, left, right))
    return samples or [_box_sample(box)]


def _box_sample(box):
    return (float(box.y), float(box.y2), float(box.x), float(box.x2))


def _line_offsets(paragraph) -> list[float]:
    intent = getattr(paragraph, "layout_intent", None)
    shape = getattr(intent, "wrap_shape", None) if intent is not None else None
    if not shape:
        return []
    return [float(offset) for offset, _width in shape]


def _wrap_mode(paragraph):
    intent = getattr(paragraph, "layout_intent", None)
    if intent is None:
        return WrapMode.NONE
    return getattr(intent, "wrap_mode", WrapMode.NONE)


def _stored_profile(paragraph) -> list:
    """Line samples that still sit in this box.

    A profile that sticks out belongs to a recycled ``id()``.
    """
    samples = _PROFILES.get(id(paragraph))
    if not samples:
        return []
    box = getattr(paragraph, "box", None)
    if box is None or box.y is None or box.y2 is None:
        return list(samples)
    top = max(float(sample[1]) for sample in samples)
    bottom = min(float(sample[0]) for sample in samples)
    if bottom < float(box.y) - 2.0 or top > float(box.y2) + 2.0:
        return []
    return list(samples)


def _group_samples(group):
    samples = []
    for paragraph in group:
        samples.extend(_stored_profile(paragraph))
    return samples


def _drop_tails(samples):
    ordered = sorted(samples, key=lambda sample: -sample[1])
    kept = []
    for sample in ordered:
        width = sample[3] - sample[2]
        if kept and width < (kept[-1][3] - kept[-1][2]) * _TAIL_FRACTION:
            continue
        if width >= 8.0:
            kept.append(sample)
    return kept


def _order_group(group):
    ranked = []
    for paragraph in group:
        chars = _chars_in_order(paragraph)
        if not chars:
            continue
        top = max(float(char.box.y2) for char in chars)
        ranked.append((top, paragraph, chars))
    ranked.sort(key=lambda item: -item[0])
    return [(paragraph, chars) for _top, paragraph, chars in ranked]


def _natural_step(ordered) -> float:
    tops = []
    heights = []
    for _paragraph, chars in ordered:
        for char in chars:
            tops.append(round(float(char.box.y2), 1))
            heights.append(float(char.box.y2) - float(char.box.y))
    unique = sorted(set(tops), reverse=True)
    gaps = [unique[i] - unique[i + 1] for i in range(len(unique) - 1)]
    gaps = [gap for gap in gaps if gap > 1.0]
    if gaps:
        gaps.sort()
        return gaps[len(gaps) // 2]
    if not heights:
        return 0.0
    heights.sort()
    return max(8.0, heights[len(heights) // 2] * 1.5)


def _overlaps_x(x, x2, band_x, band_x2) -> bool:
    """True when the line and the band share horizontal space."""
    if x is None or x2 is None:
        return True
    return min(float(x2), float(band_x2)) - max(float(x), float(band_x)) > 2.0


def _band_x(paragraph, bar):
    if bar is not None and getattr(bar, "x", None) is not None:
        return float(bar.x), float(bar.x2)
    box = getattr(paragraph, "box", None)
    if box is not None and box.x is not None and box.x2 is not None:
        return float(box.x), float(box.x2)
    return 0.0, 1.0e9


def _clear_of_bands(y: float, step: float, page, x=None, x2=None) -> float:
    """Keep a line top out of a display band. y is the line top, y-up."""
    if page is None:
        return y
    bands = _PAGE_BANDS.get(id(page), ())
    if not bands:
        return y
    for _ in range(6):
        landed = None
        for band_y, band_y2, band_x, band_x2 in bands:
            if not _overlaps_x(x, x2, band_x, band_x2):
                continue
            if y <= band_y + 0.5 or (y - step) >= band_y2 - 0.5:
                continue
            landed = band_y
            break
        if landed is None:
            return y
        y = landed
    return y


def _push_glyphs_below_bands(paragraphs, page) -> None:
    """Move any non-display line that still sits in a band to just below it.

    Settle skips a short column. Gap closing and the typesetter can still
    leave that line on the bar. Lines above the band stay; the line that
    hits, and the lines under it, step down together.
    """
    if page is None:
        return
    bands = _PAGE_BANDS.get(id(page), ())
    if not bands:
        return
    for paragraph in paragraphs or []:
        if id(paragraph) in _DISPLAY_IDS:
            continue
        _push_paragraph_below_bands(paragraph, bands)


def _source_sits_above(paragraph, band_top: float) -> bool:
    """True when the source box is entirely above the band."""
    samples = _stored_profile(paragraph)
    if samples:
        bottom = min(float(sample[0]) for sample in samples)
    else:
        box = getattr(paragraph, "box", None)
        if box is None or box.y is None:
            return False
        bottom = float(box.y)
    return bottom >= float(band_top) - 1.0


def _push_paragraph_below_bands(paragraph, bands) -> None:
    boxes = _glyph_boxes(paragraph)
    if not boxes:
        return
    rows: dict[float, list] = {}
    for box in boxes:
        rows.setdefault(round(float(box.y2), 1), []).append(box)
    shift = 0.0
    moved = False
    for top0 in sorted(rows, reverse=True):
        row = rows[top0]
        top = top0 + shift
        bottom = min(float(box.y) for box in row) + shift
        xs = [float(box.x) for box in row if box.x is not None]
        x2s = [float(box.x2) for box in row if box.x2 is not None]
        row_x = min(xs) if xs else None
        row_x2 = max(x2s) if x2s else None
        for _ in range(6):
            landed = None
            for band_y, band_y2, band_x, band_x2 in bands:
                if not _overlaps_x(row_x, row_x2, band_x, band_x2):
                    continue
                if top <= band_y + 0.5 or bottom >= band_y2 - 0.5:
                    continue
                if _source_sits_above(paragraph, band_y2):
                    continue
                landed = band_y
                break
            if landed is None:
                break
            delta = landed - top
            if abs(delta) < 0.5:
                break
            shift += delta
            top += delta
            bottom += delta
        if abs(shift) < 0.5:
            continue
        for box in row:
            box.y = float(box.y) + shift
            box.y2 = float(box.y2) + shift
        moved = True
    if moved:
        _fit_paragraph_box(paragraph)


def _group_x(ordered):
    lefts = []
    rights = []
    for paragraph, _chars in ordered:
        box = getattr(paragraph, "box", None)
        if box is None or box.x is None or box.x2 is None:
            continue
        lefts.append(float(box.x))
        rights.append(float(box.x2))
    if not lefts:
        return None, None
    return min(lefts), max(rights)


def _stay_under_band(paragraph, y: float, step: float, page) -> float:
    """A paragraph that already sits under a band does not climb above it."""
    if page is None:
        return y
    box = getattr(paragraph, "box", None)
    if box is None or box.y2 is None:
        return y
    bands = _PAGE_BANDS.get(id(page), ())
    for band_y, _band_y2, band_x, band_x2 in bands:
        if not _overlaps_x(getattr(box, "x", None), getattr(box, "x2", None), band_x, band_x2):
            continue
        if float(box.y2) <= band_y + step and y > band_y:
            y = band_y
    return y


def _flush_bar_titles(paragraphs, page) -> None:
    """Shorter Chinese on a bar stays at the bar's left, like the English."""
    if page is None:
        return
    bars = _filled_bars(page)
    if not bars:
        return
    for paragraph in paragraphs or []:
        if id(paragraph) not in _DISPLAY_IDS:
            continue
        bar = _matching_bar(paragraph, bars)
        if bar is None:
            continue
        glyphs = _glyph_boxes(paragraph)
        xs = [float(box.x) for box in glyphs if box.x is not None]
        rights = [float(box.x2) for box in glyphs if box.x2 is not None]
        if not xs or not rights:
            continue
        if min(xs) <= float(bar.x) + 6.0:
            continue
        delta = (float(bar.x) + 5.0) - min(xs)
        right = max(rights) + delta
        if right > float(bar.x2) - 2.0:
            continue
        for box in glyphs:
            if box.x is None:
                continue
            box.x = float(box.x) + delta
            if box.x2 is not None:
                box.x2 = float(box.x2) + delta


def _place_group(ordered, measure, band_top: float, step: float, page=None):
    placed = []
    x0, x1 = _group_x(ordered)
    y = _clear_of_bands(band_top, step, page, x0, x1)
    last = len(ordered) - 1
    for index, (paragraph, chars) in enumerate(ordered):
        y = _stay_under_band(paragraph, y, step, page)
        lines, y = _place_paragraph(chars, measure, y, step, page, x0, x1)
        placed.append((paragraph, lines))
        if index != last:
            y = _clear_of_bands(y - step * _PARA_EXTRA, step, page, x0, x1)
    return placed


def _place_paragraph(chars, measure, y: float, step: float, page=None, x0=None, x1=None):
    lines = []
    current = []
    used = 0.0
    line_index = 0
    hang = _marker_hang(chars)
    y = _clear_of_bands(y, step, page, x0, x1)
    left, room = _line_pocket(measure, y, step, hang, line_index)
    for item in _prepared(chars):
        if current and used + item[1] > room and not _sticks(current[-1][0], item[0]):
            pulled = _take_number_for_percent(current, item[0])
            if pulled is None:
                # The digit run is the whole line. Keep the percent with it.
                current.append(item)
                used += item[1]
                continue
            lines.append((y, left, current))
            y = _clear_of_bands(y - step, step, page, x0, x1)
            line_index += 1
            current = pulled
            used = sum(piece[1] for piece in current)
            left, room = _line_pocket(measure, y, step, hang, line_index)
        current.append(item)
        used += item[1]
    if current:
        lines.append((y, left, current))
        y = _clear_of_bands(y - step, step, page, x0, x1)
    return lines, y


def _line_pocket(measure, y: float, step: float, hang: float, line_index: int):
    """Column pocket for this line. Later list lines indent past the marker."""
    left, room = _room(measure, y, step)
    if line_index > 0 and hang > 0.5 and room - hang >= _MIN_HUNG_BODY:
        left += hang
        room -= hang
    return left, room


def _marker_hang(chars) -> float:
    """Width of a leading list marker plus the gap before the words.

    Continuation lines then start under the text. A wide dingbat is a
    quotation mark and stays flush.
    """
    index = 0
    while index < len(chars) and _is_bridge_glyph(chars[index]):
        index += 1
    if index >= len(chars) or not _is_marker_glyph(chars[index]):
        return 0.0
    marker = chars[index]
    width = _box_width(marker)
    if width <= 0.5 or width > _MARKER_HANG_MAX:
        return 0.0
    origin = float(marker.box.x) if marker.box is not None else 0.0
    index += 1
    while index < len(chars) and _is_marker_or_gap(chars[index]):
        index += 1
    if index < len(chars) and _same_row(marker, chars[index]):
        gap = float(chars[index].box.x) - origin
        # The words sit a little past the marker. Use that inset, not
        # only the marker box, so a following space is part of the hang.
        if width < gap <= _MARKER_HANG_MAX + 8.0:
            return gap
    return width


def _is_marker_or_gap(char) -> bool:
    if _is_marker_glyph(char) or _is_bridge_glyph(char):
        return True
    return not _glyph_text(char).strip()


def _take_number_for_percent(current, char):
    """Pull a trailing number so ``57`` stays with ``7`` and with ``%``.

    Returns the items that open the next line. An empty list is a normal
    wrap, including a percent that does not follow a digit. ``None`` means
    the number stays on this line, because moving it would leave that line
    empty. A percent after a CJK character is not glued to it.
    """
    if not (_is_percent_glyph(char) or _is_digit_glyph(char)):
        return []
    if not current or not (
        _is_digit_glyph(current[-1][0]) or _is_bridge_glyph(current[-1][0])
    ):
        return []
    pulled = []
    while current and (
        _is_digit_glyph(current[-1][0]) or _is_bridge_glyph(current[-1][0])
    ):
        pulled.append(current.pop())
    if not any(_is_digit_glyph(item[0]) for item in pulled):
        current.extend(reversed(pulled))
        return []
    while pulled and _is_bridge_glyph(pulled[-1][0]):
        current.append(pulled.pop())
    if not current:
        current.extend(reversed(pulled))
        return None
    pulled.reverse()
    return pulled


def _is_marker_glyph(char) -> bool:
    text = _glyph_text(char)
    if text[:1] in _BULLET_OPEN:
        return True
    from babeldoc.format.pdf.document_il.utils.layout_helper import is_bullet_point

    return bool(is_bullet_point(char))


def _is_percent_glyph(char) -> bool:
    return _glyph_text(char) in {"%", "％"}


def _is_digit_glyph(char) -> bool:
    text = _glyph_text(char)
    return len(text) == 1 and text.isdigit()


def _is_bridge_glyph(char) -> bool:
    """Space or invisible mark that may sit between a number and ``%``."""
    text = _glyph_text(char)
    if text == " ":
        return True
    if len(text) != 1:
        return False
    if text == "\u00ad":
        return True
    category = unicodedata.category(text)
    return category == "Zs" or category == "Cf"


def _glyph_text(char) -> str:
    return str(getattr(char, "char_unicode", None) or "")


def _box_width(char) -> float:
    box = getattr(char, "box", None)
    if box is None or box.x is None or box.x2 is None:
        return 0.0
    return max(0.0, float(box.x2) - float(box.x))


def _room(measure, y: float, step: float):
    left, right = _edges(measure, y - step * 0.5)
    return left, max(8.0, right - left)


def _prepared(chars):
    items = []
    for index, char in enumerate(chars):
        width = max(0.0, float(char.box.x2) - float(char.box.x))
        advance = width
        if index + 1 < len(chars) and _same_row(char, chars[index + 1]):
            gap = float(chars[index + 1].box.x) - float(char.box.x)
            if gap >= width:
                advance = gap
        items.append((char, advance, width))
    return items


def _same_row(left, right) -> bool:
    return abs(float(left.box.y2) - float(right.box.y2)) <= 3.0


def _sticks(prev, char) -> bool:
    prev_text = getattr(prev, "char_unicode", None) or ""
    text = getattr(char, "char_unicode", None) or ""
    if prev_text and prev_text[-1] in "（【《「『“([":
        return True
    return bool(text) and text[0] in "，。、；：！？）】》」』,.!?;:)]}"


def _apply_placed(placed) -> None:
    for paragraph, lines in placed:
        for y, left, items in lines:
            x = left
            for char, advance, width in items:
                height = float(char.box.y2) - float(char.box.y)
                char.box.x = x
                char.box.x2 = x + width
                char.box.y2 = y
                char.box.y = y - height
                x += advance
        _fit_paragraph_box(paragraph)


def _fit_paragraph_box(paragraph) -> None:
    boxes = _glyph_boxes(paragraph)
    if not boxes or paragraph.box is None:
        return
    paragraph.box.x = min(float(box.x) for box in boxes)
    paragraph.box.y = min(float(box.y) for box in boxes)
    paragraph.box.x2 = max(float(box.x2) for box in boxes)
    paragraph.box.y2 = max(float(box.y2) for box in boxes)


def _last_bottom(placed) -> float:
    last = 0.0
    found = False
    for _paragraph, lines in placed:
        for y, _left, items in lines:
            for char, _advance, _width in items:
                bottom = y - (float(char.box.y2) - float(char.box.y))
                if not found or bottom < last:
                    last = bottom
                    found = True
    return last


def _edges(samples, y: float):
    best = min(samples, key=lambda sample: abs((sample[0] + sample[1]) / 2.0 - y))
    return best[2], best[3]


def _page_height(page) -> float:
    for attr in ("cropbox", "mediabox"):
        crop = getattr(page, attr, None)
        if crop is None:
            continue
        box = getattr(crop, "box", None)
        if box is None:
            box = crop
        if box is not None and box.y is not None and box.y2 is not None:
            return abs(float(box.y2) - float(box.y))
    return 792.0


def _filled_bars(page) -> list:
    """Short filled rectangles. These are the black title bars."""
    page_h = _page_height(page)
    bars = []
    shapes = list(getattr(page, "pdf_curve", None) or [])
    shapes.extend(getattr(page, "pdf_rectangle", None) or [])
    for shape in shapes:
        # Real curves carry debug_info="a". Only boolean True is a debug box.
        if getattr(shape, "debug_info", None) is True:
            continue
        if not getattr(shape, "fill_background", False):
            continue
        box = getattr(shape, "box", None)
        if box is None or box.x is None or box.y is None:
            continue
        if box.x2 is None or box.y2 is None:
            continue
        width = abs(float(box.x2) - float(box.x))
        height = abs(float(box.y2) - float(box.y))
        if width < _BAR_MIN_W or height < _BAR_MIN_H or height > _BAR_MAX_H:
            continue
        if page_h > 0 and height > page_h * _BAR_PAGE_FRACTION:
            continue
        bars.append(box)
    return bars


def _is_side_gutter_quote(paragraph, page) -> bool:
    """A short block in the left gutter, with text continuing to its right.

    The quote keeps its box. Lines that run through that box drop below it.
    A line that stops short of the quote, on the hanging indent, stays.
    A gutter quote is often labeled a wrap column because it sits beside
    the hanging body.
    """
    intent = getattr(paragraph, "layout_intent", None)
    role = getattr(intent, "role", None) if intent is not None else None
    if role not in (None, LayoutIntentRole.BODY, LayoutIntentRole.WRAP_COLUMN):
        return False
    box = getattr(paragraph, "box", None)
    if box is None or None in (box.x, box.y, box.x2, box.y2):
        return False
    width = float(box.x2) - float(box.x)
    height = float(box.y2) - float(box.y)
    if float(box.x) >= _SIDE_QUOTE_X:
        return False
    if not _SIDE_QUOTE_MIN_W < width < _SIDE_QUOTE_MAX_W:
        return False
    if not _SIDE_QUOTE_MIN_H < height <= _SIDE_QUOTE_MAX_H:
        return False
    if _source_font_size(paragraph) > _BODY_FONT_MAX:
        return False
    for other in getattr(page, "pdf_paragraph", None) or []:
        if other is paragraph:
            continue
        other_box = getattr(other, "box", None)
        if other_box is None or None in (
            other_box.x,
            other_box.y,
            other_box.x2,
            other_box.y2,
        ):
            continue
        overlap = min(float(box.y2), float(other_box.y2)) - max(
            float(box.y), float(other_box.y)
        )
        if overlap < height * 0.5:
            continue
        if float(other_box.x2) >= float(box.x2) + 48.0:
            return True
    return False


def _is_left_gutter_callout(paragraph) -> bool:
    intent = getattr(paragraph, "layout_intent", None)
    role = getattr(intent, "role", None) if intent is not None else None
    if role is not LayoutIntentRole.CALLOUT:
        return False
    box = getattr(paragraph, "box", None)
    if box is None or box.x is None or box.x2 is None:
        return False
    width = float(box.x2) - float(box.x)
    return float(box.x) < 80.0 and 0.0 < width < 180.0


def _page_width(page) -> float:
    for attr in ("cropbox", "mediabox"):
        crop = getattr(page, attr, None)
        if crop is None:
            continue
        box = getattr(crop, "box", None)
        if box is None:
            box = crop
        if box is not None and box.x is not None and box.x2 is not None:
            return abs(float(box.x2) - float(box.x))
    return 612.0


def _matching_bar(paragraph, bars):
    box = getattr(paragraph, "box", None)
    if box is None or box.x is None or box.y is None:
        return None
    if box.x2 is None or box.y2 is None:
        return None
    area = abs(float(box.x2) - float(box.x)) * abs(float(box.y2) - float(box.y))
    if area <= 1.0:
        return None
    best = None
    best_frac = 0.0
    for bar in bars:
        left = max(float(box.x), float(bar.x))
        right = min(float(box.x2), float(bar.x2))
        bottom = max(float(box.y), float(bar.y))
        top = min(float(box.y2), float(bar.y2))
        if right <= left or top <= bottom:
            continue
        frac = (right - left) * (top - bottom) / area
        if frac > best_frac:
            best = bar
            best_frac = frac
    if best is not None and best_frac >= 0.60:
        return best
    # A heading box is often the whole column, wider than the bar. If that
    # short box sits in the bar, the bar still owns the heading.
    height = abs(float(box.y2) - float(box.y))
    if height > _BAR_MAX_H + 8.0:
        return None
    fallback = None
    fallback_w = 0.0
    for bar in bars:
        left = max(float(box.x), float(bar.x))
        right = min(float(box.x2), float(bar.x2))
        bottom = max(float(box.y), float(bar.y))
        top = min(float(box.y2), float(bar.y2))
        if right <= left or top <= bottom:
            continue
        if (top - bottom) < height * 0.70:
            continue
        bar_w = abs(float(bar.x2) - float(bar.x))
        overlap = right - left
        if bar_w <= 0.0 or overlap < bar_w * 0.50:
            continue
        if overlap > fallback_w:
            fallback = bar
            fallback_w = overlap
    return fallback


def _is_narrow_mark(paragraph) -> bool:
    """True when the box is a decorative mark, not a line of display type."""
    box = getattr(paragraph, "box", None)
    if box is None or box.x is None or box.x2 is None:
        return False
    return float(box.x2) - float(box.x) < 80.0


def _is_wide_short_display(paragraph, page_w: float) -> bool:
    """A short line across most of the page is a pull quote, not body."""
    box = getattr(paragraph, "box", None)
    if box is None or page_w <= 0:
        return False
    if box.x is None or box.x2 is None or box.y is None or box.y2 is None:
        return False
    width = float(box.x2) - float(box.x)
    height = float(box.y2) - float(box.y)
    if width < page_w * 0.70:
        return False
    size = _source_font_size(paragraph)
    if size <= _BODY_FONT_MAX:
        return False
    return height <= max(80.0, size * 4.0)


def _display_band(paragraph, bars, page_w: float):
    """(bottom, top, bar or None) when this paragraph owns a display band."""
    bar = _matching_bar(paragraph, bars)
    if bar is not None:
        return (float(bar.y), float(bar.y2), bar)
    if _is_left_gutter_callout(paragraph):
        return None
    intent = getattr(paragraph, "layout_intent", None)
    role = getattr(intent, "role", None) if intent is not None else None
    if role is LayoutIntentRole.CHROME:
        return None
    box = getattr(paragraph, "box", None)
    if box is None or box.y is None or box.y2 is None:
        return None
    span = (float(box.y), float(box.y2), None)
    if role is LayoutIntentRole.TITLE:
        return span
    # A 100pt quotation mark is narrower than a word. Its font box reaches
    # the body line above the quote; that line has to stay there.
    if _is_narrow_mark(paragraph) and (
        role is LayoutIntentRole.PULL_QUOTE or _source_font_size(paragraph) >= 28.0
    ):
        return None
    if role is LayoutIntentRole.PULL_QUOTE and not _is_body_sized(paragraph):
        return span
    if _source_font_size(paragraph) >= 28.0:
        return span
    large = _large_type_span(paragraph)
    if large is not None:
        return (large[0], large[1], None)
    if _is_wide_short_display(paragraph, page_w):
        return span
    return None


def _large_type_span(paragraph):
    """(bottom, top) when this is a short run of display type.

    The stored metric is often the TOC size (16) while the painted line is
    36. A body paragraph, a 12pt quote in a tall box, and a narrow quotation
    mark are not this.
    """
    box = getattr(paragraph, "box", None)
    if box is None or box.x is None or box.x2 is None:
        return None
    if box.y is None or box.y2 is None:
        return None
    if float(box.x2) - float(box.x) < 80.0:
        return None
    ink = _glyph_boxes(paragraph)
    if ink:
        heights = [float(item.y2) - float(item.y) for item in ink]
        rows = {round(float(item.y2), 0) for item in ink}
        if max(heights) >= 28.0 and len(rows) <= 2:
            return (
                min(float(item.y) for item in ink),
                max(float(item.y2) for item in ink),
            )
    size = max(_source_font_size(paragraph), _style_font_size(paragraph))
    if size < 28.0:
        return None
    height = float(box.y2) - float(box.y)
    if height > max(80.0, size * 3.0):
        return None
    return float(box.y), float(box.y2)


def _style_font_size(paragraph) -> float:
    best = 0.0
    for comp in getattr(paragraph, "pdf_paragraph_composition", None) or []:
        styled = getattr(comp, "pdf_same_style_unicode_characters", None)
        style = getattr(styled, "pdf_style", None) if styled is not None else None
        raw = getattr(style, "font_size", None) if style is not None else None
        try:
            if raw is not None and float(raw) > best:
                best = float(raw)
        except (TypeError, ValueError):
            continue
    return best


def _yield_box(box, band_y: float, band_y2: float, band_x: float, band_x2: float) -> None:
    if not _overlaps_x(
        getattr(box, "x", None), getattr(box, "x2", None), band_x, band_x2
    ):
        return
    overlap_top = min(float(box.y2), band_y2)
    overlap_bottom = max(float(box.y), band_y)
    overlap = overlap_top - overlap_bottom
    if overlap <= 1.0:
        return
    height = float(box.y2) - float(box.y)
    if height <= 4.0:
        return
    above = float(box.y2) - band_y2
    below = band_y - float(box.y)
    # Two lines above a quote and six below still fail the 30% test.
    # One line on each side is enough to keep the sentence whole.
    if above > 14.0 and below > 14.0:
        return
    if above > height * 0.3 and below > height * 0.3:
        return
    if overlap >= height * 0.5 or (above <= 4.0 and below <= 4.0):
        box.y2 = band_y
        box.y = band_y - height
        return
    if above >= below:
        if band_y2 < float(box.y2) - 2.0:
            box.y = band_y2
        return
    if band_y > float(box.y) + 2.0:
        box.y2 = band_y


def _is_misread_column_prose(paragraph) -> bool:
    """Body-sized formula, callout, or quote text still fills the column."""
    intent = getattr(paragraph, "layout_intent", None)
    role = getattr(intent, "role", None) if intent is not None else None
    if role not in _MISREAD_ROLES:
        return False
    return _is_body_sized(paragraph)


def _source_font_size(paragraph) -> float:
    metrics = getattr(paragraph, "reference_metrics", None)
    size = getattr(metrics, "font_size", None) if metrics is not None else None
    try:
        if size is not None and float(size) > 0.0:
            return float(size)
    except (TypeError, ValueError):
        pass
    best = 0.0
    for comp in getattr(paragraph, "pdf_paragraph_composition", None) or []:
        styled = getattr(comp, "pdf_same_style_unicode_characters", None)
        style = getattr(styled, "pdf_style", None) if styled is not None else None
        raw = getattr(style, "font_size", None) if style is not None else None
        try:
            if raw is not None and float(raw) > best:
                best = float(raw)
        except (TypeError, ValueError):
            continue
    return best


def _is_body_sized(paragraph) -> bool:
    size = _source_font_size(paragraph)
    if size > 0.0:
        return size <= _BODY_FONT_MAX
    box = getattr(paragraph, "box", None)
    if box is None or box.y is None or box.y2 is None:
        return False
    height = float(box.y2) - float(box.y)
    metrics = getattr(paragraph, "reference_metrics", None)
    lines = getattr(metrics, "line_count", None) if metrics is not None else None
    if lines and float(lines) > 0.0:
        return height / float(lines) <= _BODY_LINE_MAX
    return height <= _BODY_LINE_MAX


def _chars_in_order(paragraph):
    chars = []
    for comp in getattr(paragraph, "pdf_paragraph_composition", None) or []:
        chars.extend(_chars_of(comp))
    chars = [char for char in chars if _has_box(char)]
    return [char for _top, row in _rows(chars) for char in row]


def _chars_of(comp):
    character = getattr(comp, "pdf_character", None)
    if character is not None and not isinstance(character, list):
        return [character]
    if isinstance(character, list) and character:
        return list(character)
    line = getattr(comp, "pdf_line", None)
    if line is not None and getattr(line, "pdf_character", None):
        return list(line.pdf_character)
    formula = getattr(comp, "pdf_formula", None)
    if formula is not None and getattr(formula, "pdf_character", None):
        return list(formula.pdf_character)
    return []


def _has_box(char) -> bool:
    box = getattr(char, "box", None)
    return box is not None and box.x is not None and box.y is not None and box.y2 is not None


def _rows(chars):
    rows = []
    for char in sorted(chars, key=lambda item: -float(item.box.y2)):
        top = float(char.box.y2)
        if rows and abs(rows[-1][0] - top) <= 3.0:
            rows[-1][1].append(char)
        else:
            rows.append([top, [char]])
    for _top, row in rows:
        row.sort(key=lambda item: float(item.box.x))
    return rows


def _glyph_boxes(paragraph):
    boxes = []
    for comp in getattr(paragraph, "pdf_paragraph_composition", None) or []:
        chars = []
        character = getattr(comp, "pdf_character", None)
        if character is not None:
            chars = [character]
        else:
            line = getattr(comp, "pdf_line", None)
            if line is not None and getattr(line, "pdf_character", None):
                chars = line.pdf_character
            formula = getattr(comp, "pdf_formula", None)
            if formula is not None and getattr(formula, "pdf_character", None):
                chars = formula.pdf_character
        for char in chars:
            box = getattr(char, "box", None)
            if box is None or box.y is None or box.y2 is None:
                continue
            boxes.append(box)
    return boxes


def _ink_span(paragraph):
    boxes = _glyph_boxes(paragraph)
    if boxes:
        return (
            min(float(box.y) for box in boxes),
            max(float(box.y2) for box in boxes),
            min(float(box.x) for box in boxes if box.x is not None),
        )
    box = getattr(paragraph, "box", None)
    if box is None or box.y is None or box.y2 is None or box.x is None:
        return None
    return (float(box.y), float(box.y2), float(box.x))


def _shift_up(paragraph, dy: float) -> None:
    box = paragraph.box
    box.y = float(box.y) + dy
    box.y2 = float(box.y2) + dy
    for glyph in _glyph_boxes(paragraph):
        glyph.y = float(glyph.y) + dy
        glyph.y2 = float(glyph.y2) + dy


def _span_blocked(page, lower, bottom: float, low_top: float) -> bool:
    """True when a paragraph held out of this pass already sits in the gap."""
    if page is None:
        return False
    from babeldoc.format.pdf.document_il.utils.rect_flow_stack import held_column_spans

    low_x = float(lower.box.x) if lower.box.x is not None else None
    low_x2 = float(lower.box.x2) if lower.box.x2 is not None else None
    for span_y, span_y2, span_x, span_x2 in held_column_spans(page):
        if span_y2 <= low_top or span_y >= bottom:
            continue
        if _overlaps_x(low_x, low_x2, span_x, span_x2):
            return True
    return False


def _gap_blocked(paragraphs, upper, lower, bottom: float, low_top: float) -> bool:
    """True when some other block already sits in the open gap."""
    for other in paragraphs:
        if other is upper or other is lower:
            continue
        box = getattr(other, "box", None)
        if box is None or box.y is None or box.y2 is None:
            continue
        if float(box.y2) <= low_top or float(box.y) >= bottom:
            continue
        if _overlap_ratio(upper, other) >= _X_OVERLAP:
            return True
    return False


def _candidates(paragraphs):
    chosen = []
    for paragraph in paragraphs or []:
        box = getattr(paragraph, "box", None)
        if box is None or box.x is None or box.x2 is None:
            continue
        if box.y is None or box.y2 is None:
            continue
        if float(box.x2) - float(box.x) < 8.0:
            continue
        if uses_rect_column_fill(paragraph):
            chosen.append(paragraph)
    return chosen


def _line_widths(paragraph) -> list[float]:
    metrics = getattr(paragraph, "reference_metrics", None)
    stored = getattr(metrics, "per_line_widths", None) if metrics is not None else None
    if stored:
        return [float(width) for width in stored if width and float(width) > 0.0]
    intent = getattr(paragraph, "layout_intent", None)
    shape = getattr(intent, "wrap_shape", None) if intent is not None else None
    if not shape:
        return []
    return [float(width) for _offset, width in shape if float(width) > 0.0]


def _is_narrowing_cone(paragraph) -> bool:
    """True when later lines keep shrinking, as in a real text cone."""
    widths = _line_widths(paragraph)
    if len(widths) < 4:
        return False
    peak = max(widths)
    if peak < 12.0:
        return False
    body = widths[:-1] if widths[-1] < peak * _WIDE_FRACTION else list(widths)
    if len(body) < 3:
        return False
    narrowed = [width for width in body if width < peak * _WIDE_FRACTION]
    return len(narrowed) >= 2 and body[-1] < peak * 0.55


def _overlap_ratio(left_para, right_para) -> float:
    left = max(float(left_para.box.x), float(right_para.box.x))
    right = min(float(left_para.box.x2), float(right_para.box.x2))
    overlap = right - left
    if overlap <= 0.0:
        return 0.0
    width_a = float(left_para.box.x2) - float(left_para.box.x)
    width_b = float(right_para.box.x2) - float(right_para.box.x)
    return overlap / min(width_a, width_b)


def _cluster(paragraphs):
    parent = list(range(len(paragraphs)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for i, left_para in enumerate(paragraphs):
        for j in range(i + 1, len(paragraphs)):
            if _overlap_ratio(left_para, paragraphs[j]) >= _X_OVERLAP:
                root_i, root_j = find(i), find(j)
                if root_i != root_j:
                    parent[root_j] = root_i
    buckets: dict[int, list] = {}
    for index, paragraph in enumerate(paragraphs):
        buckets.setdefault(find(index), []).append(paragraph)
    return list(buckets.values())


def _apply_group(group) -> None:
    wide = _edge_group(group)
    left = min(float(p.box.x) for p in wide)
    right = max(float(p.box.x2) for p in wide)
    for paragraph in group:
        _pin_column_edge(paragraph, left, right)


def _edge_group(group):
    """Wide members that set the column. A short banner off to the side does not."""
    tall = [paragraph for paragraph in group if not _is_short_line(paragraph)]
    pool = list(group)
    if tall:
        pool = [
            paragraph
            for paragraph in group
            if not _is_short_line(paragraph) or _near_tall_left(paragraph, tall)
        ]
    if not pool:
        pool = list(group)
    widths = [float(p.box.x2) - float(p.box.x) for p in pool]
    peak = max(widths)
    wide = [
        paragraph
        for paragraph, width in zip(pool, widths, strict=True)
        if width >= peak * _WIDE_FRACTION
    ]
    return wide or pool


def _near_tall_left(paragraph, tall) -> bool:
    left = float(paragraph.box.x)
    return any(abs(left - float(item.box.x)) <= _SAME_LEFT_SLACK for item in tall)


def _pin_column_edge(paragraph, left: float, right: float) -> None:
    paragraph.alignment = "left"
    box = paragraph.box
    # A list marker sits in from the column edge. Pulling it out to that
    # edge puts the continuation under the marker, or past it.
    if _opens_with_bullet(paragraph) and float(box.x) > left + 2.0:
        if float(box.x2) < right:
            box.x2 = right
        return
    # A page banner sits left of the column. Leave its box alone.
    if _is_short_line(paragraph) and left - float(box.x) > _SAME_LEFT_SLACK:
        return
    if float(box.x) - left > _SAME_LEFT_SLACK:
        # Deeper photo step keeps its left, and still fills to the column right.
        if float(box.x2) < right:
            box.x2 = right
        return
    if float(box.x) != left or float(box.x2) != right:
        box.x = left
        box.x2 = right


def _join_continuations(group, absorbed: set[int]) -> None:
    ordered = sorted(
        (p for p in group if id(p) not in absorbed and _has_text(p)),
        key=lambda p: -float(p.box.y2),
    )
    # A one-line list lead often sits inside the continuation's box.
    # The lead is the start of the sentence, so it stays in front.
    for lead in list(ordered):
        if id(lead) in absorbed or not _is_short_line(lead):
            continue
        for body in list(ordered):
            if body is lead or id(body) in absorbed:
                continue
            if not _indented_body(lead, body):
                continue
            _absorb(lead, body)
            absorbed.add(id(body))
    index = 0
    while index < len(ordered):
        host = ordered[index]
        if id(host) in absorbed:
            index += 1
            continue
        nxt = index + 1
        while nxt < len(ordered):
            if id(ordered[nxt]) in absorbed:
                nxt += 1
                continue
            if not _continues(host, ordered[nxt]):
                break
            _absorb(host, ordered[nxt])
            absorbed.add(id(ordered[nxt]))
            nxt += 1
        index = nxt


def _is_short_line(paragraph) -> bool:
    box = paragraph.box
    return float(box.y2) - float(box.y) <= 22.0


def _indented_body(lead, body) -> bool:
    """True when body continues a one-line lead that shares its first line.

    The lead starts a list item. The body box is indented a little to the
    right and usually overlaps that first line, so a gap test never sees it.
    """
    if not _is_short_line(lead):
        return False
    dx = float(body.box.x) - float(lead.box.x)
    if dx < 6.0 or dx > 40.0:
        return False
    if float(body.box.x2) <= float(lead.box.x2) + 8.0:
        return False
    if float(body.box.y2) < float(lead.box.y) - 1.0:
        return False
    if float(body.box.y) > float(lead.box.y2) + _CONTINUE_GAP:
        return False
    return not _starts_list(body)


# A pull quote can sit in the middle of one sentence. The lower half
# still starts with a lowercase word, just farther down the column.
_ACROSS_DISPLAY_GAP = 240.0


def _join_across_display(group, paragraphs, absorbed: set[int]) -> None:
    displays = [
        item
        for item in paragraphs
        if id(item) in _DISPLAY_IDS and getattr(item, "box", None) is not None
    ]
    if not displays:
        return
    ordered = sorted(
        (p for p in group if id(p) not in absorbed and _has_text(p)),
        key=lambda p: -float(p.box.y2),
    )
    index = 0
    while index < len(ordered):
        host = ordered[index]
        if id(host) in absorbed:
            index += 1
            continue
        nxt = index + 1
        while nxt < len(ordered):
            if id(ordered[nxt]) in absorbed:
                nxt += 1
                continue
            if not _continues_across_display(host, ordered[nxt], displays):
                break
            _absorb(host, ordered[nxt])
            absorbed.add(id(ordered[nxt]))
            nxt += 1
        index = nxt


def _continues_across_display(upper, lower, displays) -> bool:
    if _starts_list(upper) or _starts_list(lower):
        return False
    gap = float(upper.box.y) - float(lower.box.y2)
    if gap <= _CONTINUE_GAP or gap > _ACROSS_DISPLAY_GAP:
        return False
    if abs(float(lower.box.x) - float(upper.box.x)) > _SAME_LEFT_SLACK:
        return False
    if _overlap_ratio(upper, lower) < _X_OVERLAP:
        return False
    if not _opens_mid_sentence(lower):
        return False
    return _display_in_gap(upper, lower, displays)


def _opens_mid_sentence(paragraph) -> bool:
    text = _plain(paragraph).lstrip(" \t\"'“”‘’([{")
    if not text:
        return False
    first = text[0]
    return first.isascii() and first.islower()


def _display_in_gap(upper, lower, displays) -> bool:
    gap_lo = float(lower.box.y2)
    gap_hi = float(upper.box.y)
    for item in displays:
        box = item.box
        if float(box.y) >= gap_hi - 1.0 or float(box.y2) <= gap_lo + 1.0:
            continue
        if (
            _overlap_ratio(upper, item) < 0.15
            and _overlap_ratio(lower, item) < 0.15
        ):
            continue
        return True
    return False


def _spans_display_band(ordered, page) -> bool:
    """True when this column's source runs above and below a display band."""
    if page is None:
        return False
    bands = _PAGE_BANDS.get(id(page), ())
    if not bands:
        return False
    for paragraph, _chars in ordered:
        samples = _stored_profile(paragraph)
        if not samples:
            continue
        bottom = min(float(sample[0]) for sample in samples)
        top = max(float(sample[1]) for sample in samples)
        box = getattr(paragraph, "box", None)
        x0 = float(box.x) if box is not None and box.x is not None else None
        x1 = float(box.x2) if box is not None and box.x2 is not None else None
        for band_y, band_y2, band_x, band_x2 in bands:
            if not _overlaps_x(x0, x1, band_x, band_x2):
                continue
            if bottom < band_y - 4.0 and top > band_y2 + 4.0:
                return True
    return False


def _continues(upper, lower) -> bool:
    gap = float(upper.box.y) - float(lower.box.y2)
    line_h = max(8.0, float(upper.box.y2) - float(upper.box.y))
    if gap > _CONTINUE_GAP:
        return False
    # A small overlap is shared leading. Half a line of overlap is a neighbor.
    if gap < 0.0 and -gap > line_h * 0.45:
        return False
    if float(lower.box.x) - float(upper.box.x) > _HANGING_INDENT:
        return False
    # A continuation may step left a little. It does not jump into the gutter.
    if float(upper.box.x) - float(lower.box.x) > _SAME_LEFT_SLACK:
        return False
    return not _starts_list(lower)


def absorb_short_continuations(page) -> None:
    """Join a one-line mid-sentence tail onto the line above it.

    The host may be a line-edge paragraph the column pass never sees.
    This runs after that paragraph's plan is frozen.
    """
    paragraphs = list(getattr(page, "pdf_paragraph", None) or [])
    absorbed: set[int] = set()
    tails = sorted(
        (paragraph for paragraph in paragraphs if _is_orphan_tail(paragraph)),
        key=lambda paragraph: -float(paragraph.box.y2),
    )
    for tail in tails:
        if id(tail) in absorbed:
            continue
        host = _nearest_host(tail, paragraphs, absorbed)
        if host is None:
            continue
        _absorb(host, tail)
        absorbed.add(id(tail))
    if absorbed:
        page.pdf_paragraph = [
            paragraph for paragraph in paragraphs if id(paragraph) not in absorbed
        ]


def _is_orphan_tail(paragraph) -> bool:
    box = getattr(paragraph, "box", None)
    if box is None or None in (box.x, box.y, box.x2, box.y2):
        return False
    if not _is_short_line(paragraph) or not _has_text(paragraph):
        return False
    if is_gutter_display(paragraph):
        return False
    return _opens_mid_sentence(paragraph)


def _nearest_host(tail, paragraphs, absorbed: set[int]):
    best = None
    best_gap = None
    for other in paragraphs:
        if other is tail or id(other) in absorbed or not _has_text(other):
            continue
        box = getattr(other, "box", None)
        if box is None or box.y is None:
            continue
        if not _continues(other, tail):
            continue
        gap = float(other.box.y) - float(tail.box.y2)
        if best_gap is None or gap < best_gap:
            best = other
            best_gap = gap
    return best


def _cover_ink(paragraph) -> None:
    """Grow the box out to character ink. Never shrink it."""
    from babeldoc.format.pdf.document_il.utils.rect_flow_stack import _line_chars

    box = getattr(paragraph, "box", None)
    if box is None or None in (box.x, box.y, box.x2, box.y2):
        return
    xs: list[float] = []
    ys: list[float] = []
    x2s: list[float] = []
    y2s: list[float] = []
    for comp in getattr(paragraph, "pdf_paragraph_composition", None) or []:
        _collect_ink(comp, _line_chars(comp), xs, ys, x2s, y2s)
    if xs:
        box.x = min(float(box.x), min(xs))
        box.y = min(float(box.y), min(ys))
        box.x2 = max(float(box.x2), max(x2s))
        box.y2 = max(float(box.y2), max(y2s))
    _restore_covered_bottom(paragraph)


def _collect_ink(comp, chars, xs, ys, x2s, y2s) -> None:
    """Glyph, visual, and line boxes. A clipped paragraph box is not the ink."""
    boxes = []
    for char in chars:
        boxes.append(getattr(char, "box", None))
        visual = getattr(char, "visual_bbox", None)
        boxes.append(getattr(visual, "box", None))
    same = getattr(comp, "pdf_same_style_characters", None)
    if same is not None:
        boxes.append(getattr(same, "box", None))
    line = getattr(comp, "pdf_line", None)
    if line is not None:
        boxes.append(getattr(line, "box", None))
    for glyph in boxes:
        if glyph is None or None in (glyph.x, glyph.y, glyph.x2, glyph.y2):
            continue
        xs.append(float(glyph.x))
        ys.append(float(glyph.y))
        x2s.append(float(glyph.x2))
        y2s.append(float(glyph.y2))


def _restore_covered_bottom(paragraph) -> None:
    """Put back an ink bottom the overlap pass lifted off.

    Once a column pass has covered the ink, ``design_box`` keeps that
    bottom and the same top. Translation then drops the character boxes,
    and the render overlap pass lifts only ``box.y``.
    """
    box = paragraph.box
    intent = getattr(paragraph, "layout_intent", None)
    design = getattr(intent, "design_box", None) if intent is not None else None
    if design is None or None in (design.y, design.y2):
        return
    if abs(float(design.y2) - float(box.y2)) > 0.5:
        return
    if float(design.y) < float(box.y):
        box.y = float(design.y)


def _absorb(host, nxt) -> None:
    host_text = _plain(host).replace("\n", "").replace("\r", "")
    nxt_text = _plain(nxt).replace("\n", "").replace("\r", "")
    _prepend_space(nxt, host_text, nxt_text)
    host.pdf_paragraph_composition = list(host.pdf_paragraph_composition or [])
    host.pdf_paragraph_composition.extend(nxt.pdf_paragraph_composition or [])
    if host_text and nxt_text and _needs_space(host_text, nxt_text):
        host.unicode = host_text + " " + nxt_text
    else:
        host.unicode = host_text + nxt_text
    _union_box(host, nxt)
    _merge_profile(host, nxt)
    nxt.pdf_paragraph_composition = []
    nxt.unicode = ""


def _prepend_space(paragraph, host_text: str, nxt_text: str) -> None:
    if not _needs_space(host_text, nxt_text):
        return
    for comp in paragraph.pdf_paragraph_composition or []:
        styled = getattr(comp, "pdf_same_style_unicode_characters", None)
        if styled is not None and styled.unicode:
            styled.unicode = " " + styled.unicode.replace("\n", "").replace("\r", "")
            return
    for comp in paragraph.pdf_paragraph_composition or []:
        for char in _chars_of(comp):
            raw = getattr(char, "char_unicode", None) or ""
            if not str(raw).strip():
                continue
            char.char_unicode = " " + str(raw)
            return


def _needs_space(left: str, right: str) -> bool:
    if not left or not right:
        return False
    return (
        left[-1].isascii()
        and left[-1].isalnum()
        and right[0].isascii()
        and right[0].isalnum()
    )


def _union_box(host, nxt) -> None:
    box = host.box
    other = nxt.box
    box.x = min(float(box.x), float(other.x))
    box.y = min(float(box.y), float(other.y))
    box.x2 = max(float(box.x2), float(other.x2))
    box.y2 = max(float(box.y2), float(other.y2))


_BULLET_OPEN = frozenset("•·●▪◦►▸\x12")


def _opens_with_bullet(paragraph) -> bool:
    """True when the paragraph starts with a list marker."""
    text = _plain(paragraph).lstrip(" \t")
    if text[:1] in _BULLET_OPEN:
        return True
    from babeldoc.format.pdf.document_il.utils.layout_helper import is_bullet_point

    for comp in getattr(paragraph, "pdf_paragraph_composition", None) or []:
        for char in _chars_of(comp):
            if is_bullet_point(char):
                return True
            raw = getattr(char, "char_unicode", None) or ""
            if not str(raw).strip():
                continue
            return False
    return False


def _starts_list(paragraph) -> bool:
    if _opens_with_bullet(paragraph):
        return True
    text = _plain(paragraph).lstrip(" \t")
    if not text:
        return False
    return text[0] in "•·●▪◦►▸-*–—"


def _has_text(paragraph) -> bool:
    return bool(_plain(paragraph).strip())


def _plain(paragraph) -> str:
    if getattr(paragraph, "unicode", None):
        return str(paragraph.unicode)
    parts = []
    for comp in getattr(paragraph, "pdf_paragraph_composition", None) or []:
        styled = getattr(comp, "pdf_same_style_unicode_characters", None)
        if styled is not None and styled.unicode:
            parts.append(styled.unicode)
    return "".join(parts)


def _release_old_line_path(paragraph) -> None:
    """Drop English line widths and the wrap pin for this column run."""
    paragraph.alignment = "left"
    _strip_hard_breaks(paragraph)
    metrics = getattr(paragraph, "reference_metrics", None)
    if metrics is not None:
        metrics.per_line_widths = None
    intent = getattr(paragraph, "layout_intent", None)
    if intent is None:
        return
    intent.wrap_shape = None
    intent.wrap_mode = WrapMode.NONE
    mark = getattr(intent, "paradigm_mark", None)
    confidence = mark.confidence if mark is not None else 0.8
    intent.paradigm_mark = ParadigmMark(
        PlacementParadigm.RECT_REFLOW,
        confidence,
        "rect_column",
    )
    design = getattr(intent, "design_box", None)
    box = paragraph.box
    if design is None or box is None:
        return
    design.x = box.x
    design.y = box.y
    design.x2 = box.x2
    design.y2 = box.y2


def _strip_hard_breaks(paragraph) -> None:
    if getattr(paragraph, "unicode", None):
        paragraph.unicode = paragraph.unicode.replace("\n", "").replace("\r", "")
    for comp in paragraph.pdf_paragraph_composition or []:
        styled = getattr(comp, "pdf_same_style_unicode_characters", None)
        if styled is not None and styled.unicode:
            styled.unicode = styled.unicode.replace("\n", "").replace("\r", "")
