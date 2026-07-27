"""Scrub DeepLX/MT garbage tokens that leak into translated unicode.

Seen on Gabrielle Moore Day 6 dual (DeepLX path):

* ``{1cH00FFFFi1}`` — hex / style debris (color or rich-text mangled)
* ``QBS0`` / ``BS5Q`` — formula-placeholder debris (``{vN}`` after MT)
* ``{ 箴言`` — orphan open-brace before CJK (tip labels)

Engine already strips formal ``{vN}`` / ``<style>`` when placeholders match;
these patterns are the residual shapes DeepLX emits when match fails.
"""

from __future__ import annotations

import re

# Style/color debris inside braces, e.g. {1cH00FFFFi1} (H is not hex — color
# tags mix letters). Skip short formula placeholders {v1}/{v12}.
_HEX_BRACE_TOKEN_RE = re.compile(
    r"\{\s*(?![vV]\s*\d+\s*\})[0-9a-zA-Z#]{4,32}\s*\}",
)

# Known formula/style scramble tokens (Day 6 QBS0; figure dual BS5Q).
# Do NOT use \b — between CJK and ASCII Python treats both as \w so \b fails
# (``努力QBS0`` would not match).
_GARBAGE_ALNUM_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:QBS\d+|BS5Q%?|BS5Q)(?![A-Za-z0-9_])",
    re.IGNORECASE,
)

# Leftover formula placeholders that were not rehydrated
_FORMULA_V_TOKEN_RE = re.compile(r"\{\s*v\s*\d+\s*\}", re.IGNORECASE)

# Orphan "{" immediately before CJK only (``{ 箴言`` / ``{第一步``).
# Must not fire on ``{1cH…}`` hex tokens (digit after brace).
_ORPHAN_BRACE_BEFORE_CJK_RE = re.compile(
    r"\{\s*(?=[\u4e00-\u9fff])",
)

# Collapse whitespace left by removals
_MULTI_SPACE_RE = re.compile(r"[ \t\u00a0]{2,}")


def sanitize_mt_output(text: str | None) -> str | None:
    """Remove leaked MT control / formula debris from translated text.

    Safe on ``None``. Does not touch normal prose braces like JSON examples
    (requires hex-heavy or known garbage shapes).
    """
    if text is None:
        return None
    if not text:
        return text
    out = text
    out = _HEX_BRACE_TOKEN_RE.sub("", out)
    out = _GARBAGE_ALNUM_TOKEN_RE.sub("", out)
    out = _FORMULA_V_TOKEN_RE.sub("", out)
    out = _ORPHAN_BRACE_BEFORE_CJK_RE.sub("", out)
    # Tidy spaces around removals (keep newlines)
    out = _MULTI_SPACE_RE.sub(" ", out)
    # "努力 。" → "努力。" after QBS0 strip
    out = re.sub(r" +\n", "\n", out)
    out = re.sub(r"([^\s]) +([。．.!？?，,；;：:])", r"\1\2", out)
    # Leading space after removing a token at start of string/line
    out = re.sub(r"(?m)^ +", "", out)
    return out
