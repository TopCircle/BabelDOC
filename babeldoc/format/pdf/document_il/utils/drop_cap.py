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
