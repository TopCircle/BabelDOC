"""Single post-MT text normalize path for dual unicode.

DeepLX/MT residual shapes (Day 6 dual):

* ``{1cH00FFFFi1}`` — style/color debris
* ``QBS0`` / ``BS5Q`` — formula-placeholder debris
* ``{ 箴言`` — orphan open-brace before CJK
* C0 controls (U+0001) and residual ``〖B…〗`` style markers
* CJK Compatibility Ideographs (``U+F9xx`` / ``U+FAxx``) from some MT/font
  paths — e.g. ``不`` → ``不``, ``刺`` → ``刺`` (OA dual P0-1)

Call :func:`normalize_translated_text` **once** per final text unit (paragraph
unicode or composition), not a chain of ad-hoc scrubbers. Always run
**before typeset** so the text layer never embeds compatibility codepoints.
"""

from __future__ import annotations

import re
import unicodedata

from babeldoc.format.pdf.document_il.utils.layout_helper import strip_ascii_controls
from babeldoc.format.pdf.document_il.utils.text_recovery import expand_latin_ligatures

# Style/color debris inside braces (H is not hex). Skip short {v1}/{v12}.
_HEX_BRACE_TOKEN_RE = re.compile(
    r"\{\s*(?![vV]\s*\d+\s*\})[0-9a-zA-Z#]{4,32}\s*\}",
)

# Do NOT use \b — between CJK and ASCII Python treats both as \w.
_GARBAGE_ALNUM_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:QBS\d+|BS5Q%?|BS5Q)(?![A-Za-z0-9_])",
    re.IGNORECASE,
)

_FORMULA_V_TOKEN_RE = re.compile(r"\{\s*v\s*\d+\s*\}", re.IGNORECASE)

# Orphan "{" before CJK only (not ``{1cH…}``).
_ORPHAN_BRACE_BEFORE_CJK_RE = re.compile(
    r"\{\s*(?=[\u4e00-\u9fff])",
)

_STYLE_MARKER_RE = re.compile(r"〖B\d+〗|〖/B\d+〗")
_MULTI_SPACE_RE = re.compile(r"[ \t\u00a0]{2,}")


def _scrub_mt_debris(text: str) -> str:
    out = text
    out = _HEX_BRACE_TOKEN_RE.sub("", out)
    out = _GARBAGE_ALNUM_TOKEN_RE.sub("", out)
    out = _FORMULA_V_TOKEN_RE.sub("", out)
    out = _ORPHAN_BRACE_BEFORE_CJK_RE.sub("", out)
    out = _MULTI_SPACE_RE.sub(" ", out)
    out = re.sub(r" +\n", "\n", out)
    out = re.sub(r"([^\s]) +([。．.!？?，,；;：:])", r"\1\2", out)
    out = re.sub(r"(?m)^ +", "", out)
    return out


def _nfkc_cjk_compatibility(text: str) -> str:
    """NFKC only CJK Compatibility Ideographs (U+F900–U+FAFF).

    Full-string ``unicodedata.normalize('NFKC', text)`` also folds fullwidth
    CJK punctuation (``，``→``,``), which breaks Chinese typesetting.

    Latin presentation ligatures (U+FB00–U+FB06) use the canonical
    :func:`expand_latin_ligatures` instead of a second NFKC path.
    """
    if not text:
        return text
    out: list[str] = []
    for ch in text:
        if 0xF900 <= ord(ch) <= 0xFAFF:
            out.append(unicodedata.normalize("NFKC", ch))
        else:
            out.append(ch)
    return "".join(out)


# Public alias kept for tests / call sites that imported the old name.
nfkc_compatibility_codepoints = _nfkc_cjk_compatibility


def normalize_translated_text(text: str | None) -> str | None:
    """Canonical post-MT cleanup: controls + debris + residual style markers + compat NFKC.

    Compatibility ideographs are mapped to unified CJK so dual/mono text layers
    stay searchable and font-stable. Must run after MT and before typeset
    (``post_translate_paragraph``). Does **not** fold fullwidth punctuation.

    Safe on ``None`` / empty. Idempotent for clean text.
    """
    if text is None:
        return None
    if not text:
        return text
    out = strip_ascii_controls(text)
    out = _scrub_mt_debris(out)
    if out and "〖B" in out:
        out = _STYLE_MARKER_RE.sub("", out)
    out = expand_latin_ligatures(out)
    out = _nfkc_cjk_compatibility(out)
    return out


def sanitize_mt_output(text: str | None) -> str | None:
    """Alias kept for tests / call sites — same as :func:`normalize_translated_text`."""
    return normalize_translated_text(text)
