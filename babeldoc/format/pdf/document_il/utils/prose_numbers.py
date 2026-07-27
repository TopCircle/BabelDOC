"""Prose-number policy: keep body digits/percentages out of formula MT path.

TeX and DocLayout often mark digits as formulas. That wraps them as ``{vN}``
for DeepLX, which mangles abstract percentages into tokens like ``99.BS5Q%``.
Also TeX uses different subset fonts for digits vs ``.`` vs ``%``, so style
spans fragment ``99.00%`` and rich-text markers scramble.

This module owns:
* detecting prose digit runs (``50 Shades``, ``99.00%``, ``20 feet``)
* deciding which formula spans are actually translatable body numbers
* coalescing adjacent pure-numeric style fragments under base style
"""

from __future__ import annotations

import re
from copy import copy

from babeldoc.format.pdf.document_il import Box
from babeldoc.format.pdf.document_il import PdfCharacter
from babeldoc.format.pdf.document_il import PdfParagraphComposition
from babeldoc.format.pdf.document_il import PdfSameStyleCharacters
from babeldoc.format.pdf.document_il.il_version_1 import Page
from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle

# Pure numeric / percent fragments that should not get rich-text markers.
PROSE_NUM_FRAG_RE = re.compile(r"^[0-9.,\s%±+\-−]+$")


def is_prose_number_run(chars: list[PdfCharacter], start: int) -> bool:
    """Digit run in body prose → must not become formula placeholders.

    Examples: ``50 Shades``, ``4th``, ``3D``, ``20 feet``, ``ideally 25, longer``,
    ``99.00%``, ``99.63%`` (figure-dual abstract percentages).

    Not ``x=50``, ``a^2`` (math). Bare ``21%`` in isolation used to be
    excluded; percentages in prose are now treated as body text so DeepLX
    does not mangle ``{vN}`` placeholders into garbage like ``99.BS5Q%``.
    """
    if start < 0 or start >= len(chars):
        return False
    ch0 = chars[start].char_unicode or ""
    if not ch0 or not re.match(r"[0-9]", ch0):
        return False
    j = start + 1
    # Integer part
    while j < len(chars):
        u = chars[j].char_unicode or ""
        if u and re.match(r"[0-9]", u):
            j += 1
            continue
        break
    # Decimal part: .00 in 99.00%
    if j < len(chars) and (chars[j].char_unicode or "") == ".":
        k = j + 1
        if k < len(chars) and re.match(r"[0-9]", chars[k].char_unicode or ""):
            j = k
            while j < len(chars):
                u = chars[j].char_unicode or ""
                if u and re.match(r"[0-9]", u):
                    j += 1
                    continue
                break
    # Percentage: 99.00% / 21% — abstract body, not display math
    if j < len(chars) and (chars[j].char_unicode or "") == "%":
        return True
    # Skip spaces and light prose punctuation before the next word
    # ("25, longer" / "20 feet" / "3. something").
    while j < len(chars):
        u = chars[j].char_unicode or ""
        if u in " \t,.;:":
            j += 1
            continue
        break
    if j >= len(chars):
        return False
    nxt = chars[j].char_unicode or ""
    if not nxt:
        return False
    # ASCII letter after the number → "50 Shades" / "20 feet" / "4th"
    return bool(re.match(r"[A-Za-z]", nxt))


def is_translatable_formula_text(text: str, y_offset: float = 0.0) -> bool:
    """Whether a formula span is really body numbers that MT should see as text.

    Pure body numbers (ATU p20 ``20 feet`` / ``25,``) must become plain text
    even when DocLayout set ``formula_layout_id`` — otherwise placeholders
    stack as ``2025`` and the counts vanish from prose.

    Percentages (figure dual abstract ``99.00%`` / ``0.12%``) and simple
    uncertainty ``0.12±0.03`` must also demote — otherwise DeepLX mangles
    formula placeholders into tokens like ``99.BS5Q%`` / trailing ``。00%``.
    """
    if y_offset > 0.1:
        return False
    # Pure digit / comma / space / period runs are always body numbers.
    if re.match(r"^[0-9, .]+$", text):
        return True
    # Percentages: 99.00%  21%  0.12%
    if re.match(r"^[0-9]+([.,][0-9]+)?\s*%$", text.strip()):
        return True
    # Uncertainty intervals common in abstracts: 0.12±0.03  0.12 ± 0.03
    if re.match(
        r"^[0-9]+([.,][0-9]+)?\s*[±+\-−]\s*[0-9]+([.,][0-9]+)?$",
        text.strip(),
    ):
        return True
    return False


def composition_plain_text(comp: PdfParagraphComposition) -> str:
    ssc = comp.pdf_same_style_characters
    if ssc is not None and ssc.pdf_character:
        return "".join(c.char_unicode or "" for c in ssc.pdf_character)
    return ""


def create_same_style_composition(
    chars: list[PdfCharacter],
    style: PdfStyle | None,
) -> PdfParagraphComposition | None:
    """Build a same-style characters composition from a char list."""
    if not chars:
        return None
    min_x = min(char.visual_bbox.box.x for char in chars)
    min_y = min(char.visual_bbox.box.y for char in chars)
    max_x = max(char.visual_bbox.box.x2 for char in chars)
    max_y = max(char.visual_bbox.box.y2 for char in chars)
    box = Box(min_x, min_y, max_x, max_y)
    return PdfParagraphComposition(
        pdf_same_style_characters=PdfSameStyleCharacters(
            box=box,
            pdf_style=style,
            pdf_character=chars,
        ),
    )


def ensure_space_after_percent(paragraph) -> None:
    """If a style span ends with ``%`` and the next starts with a letter, insert space."""
    comps = paragraph.pdf_paragraph_composition or []
    for i in range(len(comps) - 1):
        a = comps[i].pdf_same_style_characters
        b = comps[i + 1].pdf_same_style_characters
        if a is None or b is None:
            continue
        ach = a.pdf_character or []
        bch = b.pdf_character or []
        if not ach or not bch:
            continue
        last_u = ach[-1].char_unicode or ""
        first_u = bch[0].char_unicode or ""
        if last_u == "%" and first_u and first_u[0].isalpha():
            space = copy(bch[0])
            space.char_unicode = " "
            # Zero-width visual so layout does not double-gap badly
            if space.box and space.visual_bbox and space.visual_bbox.box:
                x = space.box.x
                space.box = Box(x=x, y=space.box.y, x2=x, y2=space.box.y2)
                space.visual_bbox.box = Box(
                    x=x,
                    y=space.visual_bbox.box.y,
                    x2=x,
                    y2=space.visual_bbox.box.y2,
                )
            b.pdf_character = [space, *bch]


def coalesce_prose_number_style_spans(page: Page) -> None:
    """Merge adjacent same-style digit/percent fragments into base-style text.

    Figure dual abstract: TeX splits ``99.00%`` into style runs
    ``99`` / ``.`` / ``00`` / ``%which…``. Markers around each digit cause
    DeepLX to emit ``99.BS5Q%`` and a stray ``。00%``. Keep percentages as
    one base-style span so they ride through translation as plain text.
    """
    if not page.pdf_paragraph:
        return
    for paragraph in page.pdf_paragraph:
        comps = paragraph.pdf_paragraph_composition
        if not comps or len(comps) < 2:
            continue
        base = paragraph.pdf_style
        out: list[PdfParagraphComposition] = []
        i = 0
        while i < len(comps):
            comp = comps[i]
            text = composition_plain_text(comp)
            if (
                not text
                or not PROSE_NUM_FRAG_RE.match(text)
                or comp.pdf_same_style_characters is None
            ):
                out.append(comp)
                i += 1
                continue
            # Grow a run of pure numeric fragments
            chars: list[PdfCharacter] = list(
                comp.pdf_same_style_characters.pdf_character or []
            )
            j = i + 1
            while j < len(comps):
                nxt = comps[j]
                nt = composition_plain_text(nxt)
                if nxt.pdf_same_style_characters is None or not nt:
                    break
                # Whole fragment is numeric/%
                if PROSE_NUM_FRAG_RE.match(nt):
                    chars.extend(
                        nxt.pdf_same_style_characters.pdf_character or []
                    )
                    j += 1
                    continue
                # TeX glues ``%`` to following Latin in one style span:
                # ``%which takes…`` — peel leading % into the number run.
                if nt.startswith("%") and nxt.pdf_same_style_characters.pdf_character:
                    pct_chars = nxt.pdf_same_style_characters.pdf_character
                    # First char should be %
                    if (pct_chars[0].char_unicode or "") == "%":
                        chars.append(pct_chars[0])
                        rest = pct_chars[1:]
                        if rest:
                            nxt.pdf_same_style_characters.pdf_character = rest
                            # Keep j pointing at remaining Latin span
                        else:
                            j += 1  # consumed whole span
                        break
                break
            # Prefer paragraph base style so translate path skips markers
            use_style = base or comp.pdf_same_style_characters.pdf_style
            merged = create_same_style_composition(chars, use_style)
            if merged is not None:
                out.append(merged)
            i = j
        paragraph.pdf_paragraph_composition = out
        # Ensure space after % before Latin in style unicode path
        ensure_space_after_percent(paragraph)
