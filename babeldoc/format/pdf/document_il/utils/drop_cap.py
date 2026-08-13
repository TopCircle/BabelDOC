"""Rejoin English drop-cap letters to the rest of the first word (MT input).

Design PDFs often paint a large initial (``I`` / ``W`` / ``T``) as its own
glyph, then the body continues with the *remainder* of the word in a smaller
face (``f you want…`` for ``If you want…``).

For translation we must feed complete English (``If you want…``). Chinese
typesetting should not keep a Latin drop-cap geometry (handled separately via
base_style outliers).
"""

from __future__ import annotations

import regex

from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter

# Drop-cap size vs following body size.
DROP_CAP_SIZE_RATIO = 1.35

# Text cleanup: lone capital + space + single lowercase letter (``I f`` → ``If``).
# Does NOT glue ``A man`` (second token longer than one letter).
_DROP_CAP_TEXT_RE = regex.compile(
    r"(?<![A-Za-z])([A-Z])[ \t\u00a0\u2002\u2003\u2009]+([a-z])(?![a-zA-Z])"
)


def _font_size(ch: PdfCharacter) -> float | None:
    st = getattr(ch, "pdf_style", None)
    if st is None or st.font_size is None:
        return None
    try:
        return float(st.font_size)
    except (TypeError, ValueError):
        return None


def is_drop_cap_letter(ch: PdfCharacter) -> bool:
    """True if *ch* looks like a single uppercase Latin drop-cap glyph."""
    u = (ch.char_unicode or "").strip()
    # NBSP-only or " I" cleaned
    u = u.replace("\u00a0", "").strip()
    if len(u) != 1 or not u.isalpha() or not u.isupper() or ord(u) >= 128:
        return False
    return True


def is_drop_cap_continuation(ch: PdfCharacter) -> bool:
    """True if *ch* starts the remainder of a word (lowercase Latin)."""
    u = (ch.char_unicode or "").strip()
    u = u.replace("\u00a0", "").strip()
    if not u:
        return False
    c0 = u[0]
    return c0.isalpha() and c0.islower() and ord(c0) < 128


def is_drop_cap_pair(prev: PdfCharacter, next_ch: PdfCharacter) -> bool:
    """Geometry + style: large single capital followed by lowercase body."""
    if not is_drop_cap_letter(prev) or not is_drop_cap_continuation(next_ch):
        return False
    ps = _font_size(prev)
    ns = _font_size(next_ch)
    if ps is None or ns is None or ns <= 0:
        # Size unknown: still rejoin single capital + lowercase (common IL).
        return True
    return ps >= ns * DROP_CAP_SIZE_RATIO


def should_suppress_space_after_drop_cap(
    prev: PdfCharacter,
    next_ch: PdfCharacter,
) -> bool:
    """Do not insert a word space between drop-cap and word remainder."""
    return is_drop_cap_pair(prev, next_ch)


def rejoin_drop_cap_in_text(text: str | None) -> str:
    """Glue ``I f`` / ``W e`` style splits left after space insertion.

    Only a **single** lowercase letter after the capital is joined, so
    ``A man with`` stays intact while ``I f you`` → ``If you``.
    """
    if not text:
        return "" if text is None else text
    return _DROP_CAP_TEXT_RE.sub(r"\1\2", text)


def _char_xy(ch: PdfCharacter) -> tuple[float, float] | None:
    box = getattr(ch, "visual_bbox", None)
    box = box.box if box is not None and getattr(box, "box", None) else getattr(ch, "box", None)
    if box is None or box.x is None:
        return None
    y = float(box.y2) if box.y2 is not None else (float(box.y) if box.y is not None else None)
    if y is None:
        return None
    return float(box.x), y


def place_drop_caps_before_continuations(
    chars: list[PdfCharacter],
) -> list[PdfCharacter]:
    """Move large drop-cap letters immediately before their word remainder.

    When stream order is bottom→top, ``I`` may appear far from ``f you…`` even
    after line sort.  Pair by geometry: large capital + leftmost smaller
    **word-start** lowercase to its right on a nearby baseline.
    """
    if not chars or len(chars) < 2:
        return chars

    result = list(chars)
    for _ in range(4):
        moved = False
        for i, ch in enumerate(result):
            if not is_drop_cap_letter(ch):
                continue
            # Adjacent lowercase is not done: W+d (darling) is a valid pair
            # while elcome sits further left on the same line.
            ps = _font_size(ch) or 0.0
            xy = _char_xy(ch)
            if xy is None:
                continue
            cx, cy = xy
            best_j: int | None = None
            best_ox = 1e18
            for j, other in enumerate(result):
                if j == i:
                    continue
                if not is_drop_cap_continuation(other):
                    continue
                # Prefer word starts: previous glyph not a letter
                if j > 0 and j - 1 != i:
                    prev_u = (result[j - 1].char_unicode or "").strip()
                    if prev_u and prev_u[-1].isalpha() and ord(prev_u[-1]) < 128:
                        continue
                ns = _font_size(other)
                if ns is not None and ps > 0 and ps < ns * DROP_CAP_SIZE_RATIO:
                    continue
                oxy = _char_xy(other)
                if oxy is None:
                    continue
                ox, oy = oxy
                if ox < cx - 2:
                    continue
                # Drop-cap baseline often sits below the first body line band.
                if abs(oy - cy) > 55.0:
                    continue
                if ox < best_ox:
                    best_ox = ox
                    best_j = j
            if best_j is None or best_j == i + 1:
                continue
            item = result.pop(i)
            insert_at = best_j if best_j < i else best_j - 1
            result.insert(insert_at, item)
            moved = True
            break
        if not moved:
            break
    return result
