"""Recover missing word boundaries and TeX soft hyphens from PDF geometry.

PDF often omits explicit space glyphs; TeX author lines use ~3.6pt gaps that
fall just under the classic 0.5× width threshold (``S.Hazra`` / ``andM.H.``).
Line wraps also leave soft hyphens (``ap-`` + ``proximation``).

Used by ``layout_helper.get_char_unicode_string`` and dummy-space insertion.
"""

from __future__ import annotations

import regex

from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter

# Default: gap > 50% of the *wider* glyph (avoids "There"→"The re").
SPACE_WIDTH_RATIO = 0.5
# TeX author lines (figure dual): inter-word gaps ~3.6pt sit just under
# 0.5× wide capitals (H/D/M thr≈3.7–5.1) → ``S.Hazra`` / ``andM.H.Devoret``.
# Relaxed Latin-only path uses 35% + absolute floor without reopening CJK glue.
LATIN_WORD_GAP_RATIO = 0.35
LATIN_WORD_MIN_GAP_PT = 2.0

# Soft hyphen rejoined after style regroup: ``ap- proximation`` → ``approximation``
SOFT_HYPHEN_TEXT_RE = regex.compile(r"(?<=[A-Za-z])-\s+(?=[a-z])")


def is_ascii_alpha(ch: str | None) -> bool:
    return bool(ch) and ch[0].isalpha() and ord(ch[0]) < 128


def gap_is_word_boundary(
    prev: PdfCharacter,
    next_ch: PdfCharacter,
    distance: float,
) -> bool:
    """Whether ``distance`` between two chars should insert a word space.

    Standard rule: ``distance > 0.5 * max(widths)``.
    Latin token rule (figure dual authors): after ``.``/``,`` before a letter,
    or lower→Upper (``and M``), accept slightly tighter TeX gaps (≥2pt and
    ``> 0.35 * max width``).
    """
    if distance <= 0:
        return False
    if not prev.box or not next_ch.box:
        return False
    curr_w = prev.box.x2 - prev.box.x
    next_w = next_ch.box.x2 - next_ch.box.x
    max_w = max(curr_w, next_w)
    if max_w <= 0:
        return False
    if distance > max_w * SPACE_WIDTH_RATIO:
        return True
    if distance < LATIN_WORD_MIN_GAP_PT or distance <= max_w * LATIN_WORD_GAP_RATIO:
        return False
    prev_u = prev.char_unicode or ""
    next_u = next_ch.char_unicode or ""
    if not next_u:
        return False
    # ``S. Hazra`` / ``P. D.`` / ``M. H.``
    if prev_u == "." and next_u[0].isupper() and ord(next_u[0]) < 128:
        return True
    # ``and M`` (lowercase then capital)
    if (
        prev_u
        and prev_u[-1].islower()
        and ord(prev_u[-1]) < 128
        and next_u[0].isupper()
        and ord(next_u[0]) < 128
    ):
        return True
    # ``Hazra,1`` usually no space before digit; ``1, ∗`` thin — skip comma+digit
    # ``Frunzio,1 and`` — comma then space glyph usually present
    if prev_u == "," and is_ascii_alpha(next_u):
        return True
    return False


def is_soft_hyphen_line_wrap(prev: PdfCharacter, next_ch: PdfCharacter) -> bool:
    """TeX soft hyphen at line wrap: ``ap-`` + ``proximation`` → join without space."""
    prev_u = prev.char_unicode or ""
    next_u = next_ch.char_unicode or ""
    return prev_u == "-" and bool(next_u) and next_u[0].islower()


def rejoin_soft_hyphens_in_text(text: str) -> str:
    """Collapse ``ap- proximation`` style soft hyphens left after style regroup."""
    return SOFT_HYPHEN_TEXT_RE.sub("", text)
