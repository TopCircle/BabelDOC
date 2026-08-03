"""Visual reading-order repair for reverse-paint PDF text streams.

Design PDFs often paint decorative titles as per-character objects in
non-reading order:

* Full reverse: ``WHO HAS ORGASMS?`` → stream ``?SMSrgao SahWho``
* Misplaced chapter digit: large ``1`` painted first at the right edge →
  stream ``1Chapter`` instead of visual ``Chapter 1``

Body prose (arXiv two-column) must **not** be reordered.  A prior bug used
glyph-box mid-Y for line clustering: descenders (``p``, ``y``, ``g``) have
a lower ``box.y``, fell into another bucket, and ``pseudo`` became ``seudo``
with orphan ``p`` — wrecking the figure golden dual.

Line clustering therefore uses the **top** of the glyph box (``y2``), which
is stable across descenders on the same baseline.

Policy (single entry :func:`maybe_reorder_reversed_stream`):
  1. Decorative short-run geometry
  2. Reverse-paint **or** misplaced leading digit
  3. Label is title/section_header **or** plain-text family
     (not abandon/figure/table)

Long LTR body fails (1) or (2).  OA mid-page plain decorative reverse passes
all three without fake ``layout_label="title"`` promote.
"""

from __future__ import annotations

from typing import Any

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter

# Same-line reverse pairs / total pairs ≥ this → consider reverse-paint.
_DEFAULT_REVERSE_RATIO = 0.20
_DEFAULT_Y_TOL = 6.0
_DEFAULT_MIN_PAIRS = 4
# Guard: only reorder short decorative-like runs, not long body lines.
_MAX_REORDER_CHARS = 64
_MIN_SINGLE_LETTER_RATIO = 0.55

_REORDER_ALLOWED_LABELS = frozenset(
    {
        "title",
        "section_header",
    }
)
# Plain-text family may reorder only after decorative+reverse gates pass.
_REORDER_PLAIN_LABELS = frozenset(
    {
        "",
        "plain text",
        "text",
        "paragraph",
        "paragraph_hybrid",
    }
)
# Backward-compatible name (top-band no longer required for plain).
_REORDER_PLAIN_TOP_LABELS = _REORDER_PLAIN_LABELS

# Multi-line stream climb (bottom→top emit) → sort lines top-first.
_LINE_Y_EPS_PT = 2.0
_LINE_CLIMB_MIN_STEPS = 2


def _resolve_char_box(char: PdfCharacter) -> Box | None:
    """Prefer visual_bbox when it overlaps pdf box; else fall back."""
    visual = None
    vb = getattr(char, "visual_bbox", None)
    if vb is not None and getattr(vb, "box", None) is not None:
        visual = vb.box
    pdf = getattr(char, "box", None)

    if visual is not None and pdf is not None:
        try:
            from babeldoc.format.pdf.document_il.utils.layout_helper import (
                calculate_iou_for_boxes,
            )

            if calculate_iou_for_boxes(visual, pdf) >= 0.1:
                return visual
            return pdf
        except Exception:
            return visual
    return visual if visual is not None else pdf


def char_visual_xy(char: PdfCharacter) -> tuple[float, float] | None:
    """Return ``(x, y_line)`` for reading-order comparisons.

    ``y_line`` is the **top** of the glyph box (``y2``).  Using mid-Y or
    bottom (``y``) splits descenders (p/y/g/q) onto a false second line.
    """
    box = _resolve_char_box(char)
    if box is None or box.x is None:
        return None
    if box.y2 is not None:
        y_line = float(box.y2)
    elif box.y is not None:
        y_line = float(box.y)
    else:
        return None
    return (float(box.x), y_line)


def is_stream_visually_reversed(
    chars: list[PdfCharacter],
    *,
    reverse_ratio: float = _DEFAULT_REVERSE_RATIO,
    y_tol: float = _DEFAULT_Y_TOL,
    min_pairs: int = _DEFAULT_MIN_PAIRS,
) -> bool:
    """True when same-line stream order is mostly right-to-left."""
    pdf_chars = [c for c in chars if isinstance(c, PdfCharacter)]
    if len(pdf_chars) < min_pairs + 1:
        return False

    decreasing = 0
    total = 0
    for i in range(len(pdf_chars) - 1):
        a = char_visual_xy(pdf_chars[i])
        b = char_visual_xy(pdf_chars[i + 1])
        if a is None or b is None:
            continue
        if abs(a[1] - b[1]) > y_tol:
            continue  # different visual line
        total += 1
        if b[0] < a[0] - 0.5:
            decreasing += 1
    if total < min_pairs:
        return False
    return (decreasing / total) >= reverse_ratio


def looks_like_decorative_run(chars: list[PdfCharacter]) -> bool:
    """True for short, mostly single-letter runs (typical reverse-paint titles)."""
    pdf_chars = [c for c in chars if isinstance(c, PdfCharacter)]
    if not pdf_chars or len(pdf_chars) > _MAX_REORDER_CHARS:
        return False
    letters = 0
    single = 0
    for c in pdf_chars:
        u = (c.char_unicode or "").strip()
        if not u or u.isspace():
            continue
        letters += 1
        if len(u) == 1 and u.isalpha():
            single += 1
    if letters < 3:
        return False
    return (single / letters) >= _MIN_SINGLE_LETTER_RATIO


# Private alias kept for any external private imports during transition.
_looks_like_decorative_run = looks_like_decorative_run


def is_misplaced_leading_digit(chars: list[PdfCharacter]) -> bool:
    """Stream starts with a digit whose x is right of the following word (1Chapter)."""
    pdf_chars = [c for c in chars if isinstance(c, PdfCharacter)]
    if len(pdf_chars) < 3:
        return False
    i0 = 0
    while i0 < len(pdf_chars) and (pdf_chars[i0].char_unicode or "").isspace():
        i0 += 1
    if i0 >= len(pdf_chars):
        return False
    first = pdf_chars[i0]
    fu = (first.char_unicode or "").strip()
    if not fu or not fu[0].isdigit():
        return False
    xy0 = char_visual_xy(first)
    if xy0 is None:
        return False
    rest_x: list[float] = []
    for c in pdf_chars[i0 + 1 :]:
        u = (c.char_unicode or "").strip()
        if not u or u.isspace():
            continue
        xy = char_visual_xy(c)
        if xy is not None:
            rest_x.append(xy[0])
    if len(rest_x) < 2:
        return False
    return xy0[0] > (min(rest_x) + 20.0)


_is_misplaced_leading_digit = is_misplaced_leading_digit


def sort_chars_visual_order(
    chars: list[PdfCharacter],
    *,
    y_tol: float = _DEFAULT_Y_TOL,
) -> list[PdfCharacter]:
    """Sort characters top-to-bottom, left-to-right within each visual line.

    Lines are clustered by glyph **top** (``y2``), then sorted by ``x``.
    """
    if len(chars) < 2:
        return list(chars)

    items: list[tuple[int, float, float, PdfCharacter]] = []
    for i, ch in enumerate(chars):
        xy = char_visual_xy(ch)
        if xy is None:
            items.append((i, 0.0, float(i), ch))
        else:
            items.append((i, xy[1], xy[0], ch))

    buckets: dict[int, list[tuple[int, float, float, PdfCharacter]]] = {}
    for item in items:
        bucket = int(round(item[1] / y_tol))
        buckets.setdefault(bucket, []).append(item)

    ordered: list[PdfCharacter] = []
    # Higher PDF y = higher on page → emit larger y2 buckets first
    for bucket in sorted(buckets.keys(), reverse=True):
        line = buckets[bucket]
        line.sort(key=lambda t: (t[2], t[0]))
        ordered.extend(t[3] for t in line)
    return ordered


def _same_order(a: list[PdfCharacter], b: list[PdfCharacter]) -> bool:
    return len(a) == len(b) and all(x is y for x, y in zip(a, b))


def label_allows_stream_reorder(
    layout_label: str | None,
    *,
    in_page_top_band: bool = False,
) -> bool:
    """Whether *layout_label* may reorder after geometry gates pass.

    - ``title`` / ``section_header``: always
    - plain-text family: always (geometry already blocked long LTR body)
    - ``in_page_top_band`` retained for API compatibility; unused for gating
    - abandon / figure / table: never
    """
    _ = in_page_top_band  # API compat (PR-B callers)
    label = (layout_label or "").strip().lower()
    if label in _REORDER_ALLOWED_LABELS:
        return True
    if label in _REORDER_PLAIN_LABELS:
        return True
    return False


def maybe_reorder_reversed_stream(
    chars: list[PdfCharacter],
    *,
    layout_label: str | None = None,
    in_page_top_band: bool = False,
) -> list[PdfCharacter]:
    """Reorder reverse-paint / misplaced-digit runs (single policy entry).

    Order of checks (all required):
      1. Short single-letter decorative geometry
      2. Reverse-paint ratio high **or** misplaced leading digit
      3. Label is title/section_header **or** plain-text family

    Does **not** reorder merely because visual sort differs.
    Long LTR body fails (1) or (2).  Mid-page plain decorative reverse
    (OA Who has / Are You Lost) passes without fake title promote.
    """
    if not chars:
        return chars
    # Geometry first — figure-golden long LTR never reaches label policy.
    if not looks_like_decorative_run(chars):
        return chars
    if not (
        is_stream_visually_reversed(chars) or is_misplaced_leading_digit(chars)
    ):
        return chars
    if not label_allows_stream_reorder(
        layout_label, in_page_top_band=in_page_top_band
    ):
        return chars
    ordered = sort_chars_visual_order(chars)
    if _same_order(ordered, chars):
        return chars
    return ordered


def sort_line_compositions_if_stream_climbs(
    compositions: list[Any],
) -> list[Any] | None:
    """If stream walks up the page between consecutive lines, return top-first order.

    Only runs when **every** composition is a ``pdf_line`` with a box (no
    formula interleave).  Returns None when no change (caller keeps original).
    """
    if len(compositions) < 2:
        return None
    line_y2: list[float] = []
    for comp in compositions:
        line = getattr(comp, "pdf_line", None)
        if line is None:
            return None  # mixed composition — do not reorder
        box = getattr(line, "box", None)
        if box is None or box.y2 is None:
            return None
        line_y2.append(float(box.y2))

    climbs = 0
    drops = 0
    for a, b in zip(line_y2, line_y2[1:]):
        if b > a + _LINE_Y_EPS_PT:
            climbs += 1
        elif b < a - _LINE_Y_EPS_PT:
            drops += 1
    if climbs < _LINE_CLIMB_MIN_STEPS or climbs <= drops:
        return None

    return sorted(
        compositions,
        key=lambda c: (
            -(c.pdf_line.box.y2 or 0.0),
            c.pdf_line.box.x if c.pdf_line.box.x is not None else 0.0,
        ),
    )


# Narrow callout / design columns (OA TAKING CHARGE ~190pt wide).
_MULTILINE_CLIMB_MAX_WIDTH = 240.0
# Wide body may still bottom→top paint (OA p19 intro); require stronger climb.
_MULTILINE_CLIMB_STRONG_RATIO = 0.70
_MULTILINE_CLIMB_STRONG_MIN_LINES = 4
_MULTILINE_CLIMB_MIN_LINES = 3


def _cluster_stream_line_keys(
    chars: list[PdfCharacter],
    *,
    y_tol: float = _DEFAULT_Y_TOL,
) -> list[tuple[float, list[PdfCharacter]]]:
    """Group chars into visual lines in **stream order** of first appearance.

    Returns list of ``(y_line, chars_on_line)`` in the order lines are first
    encountered in the stream (not sorted by y).
    """
    lines: list[tuple[float, list[PdfCharacter]]] = []
    for ch in chars:
        if not isinstance(ch, PdfCharacter):
            continue
        xy = char_visual_xy(ch)
        if xy is None:
            continue
        y_line, x = xy[1], xy[0]
        placed = False
        for i, (ly, bucket) in enumerate(lines):
            if abs(ly - y_line) <= y_tol:
                bucket.append(ch)
                # refresh representative y toward mean top
                lines[i] = ((ly * (len(bucket) - 1) + y_line) / len(bucket), bucket)
                placed = True
                break
        if not placed:
            lines.append((y_line, [ch]))
    return lines


def _climb_drop_counts(
    chars: list[PdfCharacter],
    *,
    y_tol: float = _DEFAULT_Y_TOL,
) -> tuple[int, int, int]:
    """Return ``(climbs, drops, n_lines)`` for stream line sequence."""
    lines = _cluster_stream_line_keys(chars, y_tol=y_tol)
    if len(lines) < 2:
        return 0, 0, len(lines)
    climbs = 0
    drops = 0
    for (y_a, _), (y_b, _) in zip(lines, lines[1:]):
        if y_b > y_a + _LINE_Y_EPS_PT:
            climbs += 1
        elif y_b < y_a - _LINE_Y_EPS_PT:
            drops += 1
    return climbs, drops, len(lines)


def is_multiline_stream_climbing(
    chars: list[PdfCharacter],
    *,
    y_tol: float = _DEFAULT_Y_TOL,
    min_lines: int = _MULTILINE_CLIMB_MIN_LINES,
) -> bool:
    """True when successive stream lines move up the page (bottom→top paint).

    OA p19 TAKING CHARGE body is painted tip-first (bottom line first), so
    MT sees ``the program… In order to…`` reversed.  Detect climb without
    requiring decorative single-letter geometry.
    """
    climbs, drops, n_lines = _climb_drop_counts(chars, y_tol=y_tol)
    if n_lines < min_lines:
        return False
    return climbs >= _LINE_CLIMB_MIN_STEPS and climbs > drops


def _has_drop_cap_glyph(chars: list[PdfCharacter]) -> bool:
    from babeldoc.format.pdf.document_il.utils.drop_cap import is_drop_cap_letter

    for ch in chars:
        if is_drop_cap_letter(ch):
            return True
    return False


def maybe_reorder_multiline_stream_climb(
    chars: list[PdfCharacter],
    *,
    para_width: float | None = None,
    max_width: float = _MULTILINE_CLIMB_MAX_WIDTH,
) -> list[PdfCharacter]:
    """Reorder chars top→bottom when stream paints lines bottom→top.

    * Narrow (≤ *max_width*): reorder on normal climb evidence.
    * Wide body: only when climb is **strong** (≥70% steps up, ≥4 lines)
      **or** a drop-cap glyph is present (OA p19 intro) — avoids figure LTR.
    """
    if not chars or len(chars) < 8:
        return chars

    width = para_width
    if width is None:
        xs: list[float] = []
        x2s: list[float] = []
        for ch in chars:
            box = _resolve_char_box(ch)
            if box is None:
                continue
            if box.x is not None:
                xs.append(float(box.x))
            if box.x2 is not None:
                x2s.append(float(box.x2))
        if xs and x2s:
            width = max(x2s) - min(xs)

    climbs, drops, n_lines = _climb_drop_counts(chars)
    if n_lines < _MULTILINE_CLIMB_MIN_LINES:
        return chars
    if climbs < _LINE_CLIMB_MIN_STEPS or climbs <= drops:
        return chars

    total = climbs + drops
    ratio = climbs / total if total else 0.0
    narrow = width is None or width <= max_width
    strong = (
        ratio >= _MULTILINE_CLIMB_STRONG_RATIO
        and n_lines >= _MULTILINE_CLIMB_STRONG_MIN_LINES
    )
    if not narrow and not strong and not _has_drop_cap_glyph(chars):
        return chars

    ordered = sort_chars_visual_order(chars)
    if _same_order(ordered, list(chars)):
        return chars
    return ordered
