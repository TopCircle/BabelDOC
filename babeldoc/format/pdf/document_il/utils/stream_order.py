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

Owns only geometry/order; callers decide when to apply.
"""

from __future__ import annotations

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter

# Same-line reverse pairs / total pairs ≥ this → consider reverse-paint.
_DEFAULT_REVERSE_RATIO = 0.20
_DEFAULT_Y_TOL = 6.0
_DEFAULT_MIN_PAIRS = 4
# Guard: only reorder short decorative-like runs, not long body lines.
_MAX_REORDER_CHARS = 64
_MIN_SINGLE_LETTER_RATIO = 0.55


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


def _looks_like_decorative_run(chars: list[PdfCharacter]) -> bool:
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


def _is_misplaced_leading_digit(chars: list[PdfCharacter]) -> bool:
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


def maybe_reorder_reversed_stream(
    chars: list[PdfCharacter],
) -> list[PdfCharacter]:
    """Reorder only reverse-paint / misplaced-digit decorative runs.

    Does **not** reorder merely because visual sort differs — that path
    scrambled arXiv body lines when descenders fell into other y-buckets.
    """
    if not chars:
        return chars
    if not _looks_like_decorative_run(chars):
        return chars
    if not (
        is_stream_visually_reversed(chars) or _is_misplaced_leading_digit(chars)
    ):
        return chars
    ordered = sort_chars_visual_order(chars)
    if _same_order(ordered, chars):
        return chars
    return ordered
