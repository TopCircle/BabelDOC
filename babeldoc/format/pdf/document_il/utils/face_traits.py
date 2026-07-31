"""Infer CJK stand-in face traits from an original PostScript/TrueType name.

OS/2 flags in commercial PDFs are often wrong (Myriad flagged serif). When the
face *name* is available, map to the closest bundled CJK family via **token**
membership (not bare substring), so Cardinal/Academic/Monotype do not false-hit
``din`` / ``demi`` / ``mono``.
"""

from __future__ import annotations

import re

# Full tokens only (after CamelCase / separator split).
_SANS_TOKENS: frozenset[str] = frozenset(
    {
        "myriad",
        "helvetica",
        "arial",
        "calibri",
        "gotham",
        "futura",
        "montserrat",
        "frutiger",
        "univers",
        "franklin",
        "roboto",
        "inter",
        "sourcesans",
        "notosans",
        "din",
        "proxima",
        "avenir",
        "optima",
        "gilroy",
        "lato",
        "opensans",
        "segoe",
        "verdana",
        "tahoma",
        "trebuchet",
        "gill",
        "neutra",
        "microstyle",
        "impact",
        "arialnarrow",
    }
)
_SERIF_TOKENS: frozenset[str] = frozenset(
    {
        "times",
        "garamond",
        "georgia",
        "palatino",
        "minion",
        "baskerville",
        "caslon",
        "trajan",
        "bodoni",
        "didot",
        "cambria",
        "constantia",
        "sourceserif",
        "notoserif",
        "bookman",
        "century",
        "sabon",
        "janson",
        "bembo",
        "libertine",
        "charter",
        "merriweather",
        "ptserif",
        "garalde",
        "cochin",
        "hoefler",
    }
)
# Design / all-caps display faces → prefer Bold CJK for hierarchy (product).
_DISPLAY_TOKENS: frozenset[str] = frozenset(
    {
        "microstyle",
        "impact",
        "trajan",
        "copperplate",
        "engravers",
    }
)
_BOLD_TOKENS: frozenset[str] = frozenset(
    {
        "bold",
        "heavy",
        "black",
        "semibold",
        "extrabold",
        "demibold",
        "demi",
        "medium",
    }
)
_LIGHT_TOKENS: frozenset[str] = frozenset(
    {
        "light",
        "thin",
        "ultralight",
        "extralight",
        "hairline",
    }
)
_MONO_TOKENS: frozenset[str] = frozenset(
    {
        "courier",
        "mono",
        "consolas",
        "menlo",
        "monaco",
        "inconsolata",
        "sourcecode",
        "jetbrains",
        "firacode",
    }
)
# Compound family glued without CamelCase (rare).
_COMPOUND_SANS: tuple[str, ...] = (
    "sourcesans",
    "notosans",
    "opensans",
    "arialnarrow",
    "microstyle",
)
_COMPOUND_SERIF: tuple[str, ...] = (
    "sourceserif",
    "notoserif",
    "ptserif",
    "timesnewroman",
)


def normalize_ps_font_name(font_name: str | None) -> str:
    """Strip subset prefix; lowercase alnum-only key (tests / debug)."""
    if not font_name:
        return ""
    name = font_name.strip()
    if "+" in name:
        name = name.split("+", 1)[1]
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def font_name_tokens(font_name: str | None) -> frozenset[str]:
    """Tokenize a face name into lowercase family/style pieces.

    ``AAAA+MyriadPro-Light`` → ``{myriad, pro, light}``  
    ``MonotypeCorsiva`` → ``{monotype, corsiva}`` (not bare ``mono``)
    """
    if not font_name:
        return frozenset()
    name = font_name.strip()
    if "+" in name:
        name = name.split("+", 1)[1]
    # CamelCase boundaries
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name)
    spaced = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", spaced)
    parts = re.split(r"[^A-Za-z0-9]+", spaced)
    tokens = {p.lower() for p in parts if p and not p.isdigit()}
    # Drop pure style noise length-1 (except we don't have single-letter families)
    tokens = {t for t in tokens if len(t) >= 2}
    return frozenset(tokens)


def _tokens_hit_family(
    tokens: frozenset[str],
    flat_key: str,
    family_tokens: frozenset[str],
    compounds: tuple[str, ...],
) -> bool:
    if tokens & family_tokens:
        return True
    return any(c in flat_key for c in compounds)


def infer_face_traits_from_name(
    font_name: str | None,
    *,
    bold: bool,
    italic: bool,
    monospaced: bool,
    serif: bool,
    prefer_display_bold: bool = True,
) -> tuple[bool, bool, bool, bool]:
    """Refine bold/italic/mono/serif from the original face name.

    Returns ``(bold, italic, monospaced, serif)``. Unknown names leave flags
    unchanged. Known families override wrong OS/2 bits.

    ``prefer_display_bold``: Trajan/Microstyle-style display faces map to Bold
    CJK for title hierarchy (product). Family detection still runs without it.
    """
    tokens = font_name_tokens(font_name)
    flat = normalize_ps_font_name(font_name)
    if not tokens and not flat:
        return bold, italic, monospaced, serif

    # Weight / slant from style tokens
    if not bold and tokens & _BOLD_TOKENS:
        bold = True
    if tokens & _LIGHT_TOKENS:
        bold = False

    if not italic:
        if "italic" in tokens or "oblique" in tokens:
            italic = True
        elif flat.endswith("it") and re.search(
            r"(light|bold|regular|medium|black|semi|book|roman|extra)it$",
            flat,
        ):
            italic = True

    if not monospaced and tokens & _MONO_TOKENS:
        monospaced = True

    # Family: sans vs serif (token membership; serif wins if both — rare)
    is_sans = _tokens_hit_family(tokens, flat, _SANS_TOKENS, _COMPOUND_SANS)
    is_serif = _tokens_hit_family(tokens, flat, _SERIF_TOKENS, _COMPOUND_SERIF)
    # Condensed style alone is not a family; MyriadPro-Cond already has myriad.
    if is_serif and not is_sans:
        serif = True
    elif is_sans and not is_serif:
        serif = False
    elif is_sans and is_serif:
        # Conflicting names: prefer the longer matching token family signal
        # by keeping OS/2 if set, else sans for UI-ish dual hits.
        serif = bool(serif)

    if prefer_display_bold and not bold and tokens & _DISPLAY_TOKENS:
        bold = True

    return bold, italic, monospaced, serif
