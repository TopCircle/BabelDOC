"""Numbered-list serial repair for dual ZH/EN PDFs.

DeepLX/MT often:
* glues the next item's serial onto the previous sentence end (``…恰到好处。4.``)
* rewrites ASCII ``1.`` to ideographic ``1。`` / fullwidth ``1．``

These helpers run once before typesetting so hang-indent and body column stay
aligned. Layout hang-width math remains in ``Typesetting``; this module owns
only unicode/composition repair.
"""

from __future__ import annotations

import logging
import re

from babeldoc.format.pdf.document_il import PdfParagraphComposition
from babeldoc.format.pdf.document_il import PdfSameStyleUnicodeCharacters
from babeldoc.format.pdf.document_il import PdfStyle
from babeldoc.format.pdf.document_il import il_version_1

logger = logging.getLogger(__name__)

# Leading marker for numbered / lettered list items (EN/CJK dual hanging indent).
# Include ideographic ``。`` — DeepLX/MT often rewrites ``2.`` → ``2。``.
# Day 6 quiz uses ``a.``/``b.`` options — lettered serials need the same hang path.
LIST_MARKER_RE = re.compile(
    r"^(?:"
    r"\d{1,3}\s*[\.．。、\)]\s*"  # 1.  1． 1。 1、  1)
    r"|[a-zA-Z]\s*[\.．。、\)]\s*"  # a.  b） A.
    r"|\(\s*\d{1,3}\s*\)\s*"  # (1)
    r"|\(\s*[a-zA-Z]\s*\)\s*"  # (a)
    r"|[①-⑳]\s*"
    r")"
)

# Next-item serial glued onto the previous item's last sentence
# (All Tied Up dual p21: item 3 ends ``恰到好处。4.`` / item 4 ends ``垂下来。5.``).
# Require a sentence terminator immediately before the serial so prose like
# ``The answer is 42.`` is not stripped.
TRAILING_LIST_MARKER_RE = re.compile(
    r"(?P<body>.*[。．.!?！？])\s*"
    r"(?P<marker>(?:\d{1,3}|[a-zA-Z])\s*[\.．。、\)])\s*$",
    re.DOTALL,
)

# Leading serial with CJK/fullwidth punct that MT rewrote from ``1.`` / ``a.``
LEADING_LIST_MARKER_DOT_RE = re.compile(
    r"^(?P<lead>\s*)(?P<num>\d{1,3}|[a-zA-Z])\s*(?P<punct>[。．、])\s*"
)

# Mid-string tip/list serials: ``提示 3。最大值`` / ``TIP 3。`` (not sentence end)
MID_LIST_IDEO_PERIOD_RE = re.compile(
    r"(?<![.\dA-Za-z\u4e00-\u9fff])"
    r"(?P<num>\d{1,3}|[a-zA-Z])"
    r"\s*。"
    r"(?=[\u4e00-\u9fffA-Za-z「『《])"
)


def _is_cjk_char0(ch: str) -> bool:
    o = ord(ch[0])
    return (
        0x4E00 <= o <= 0x9FFF
        or 0x3400 <= o <= 0x4DBF
        or 0x3040 <= o <= 0x30FF
        or 0xAC00 <= o <= 0xD7AF
    )


def looks_like_numbered_list_item(paragraph: il_version_1.PdfParagraph) -> bool:
    """True when translated/source text starts like ``1.`` / ``1、`` / ``2。``."""
    text = (getattr(paragraph, "unicode", None) or "").strip()
    if not text:
        return False
    # NBSP / thin space after marker still counts as list
    text = text.replace("\xa0", " ").replace("\u2009", " ")
    return bool(LIST_MARKER_RE.match(text))


def marker_digit(marker: str) -> str | None:
    """Numeric serial only (``4.`` → ``4``). Letters use :func:`marker_key`."""
    m = re.match(r"(\d{1,3})", (marker or "").strip())
    return m.group(1) if m else None


def marker_key(marker: str) -> str | None:
    """Stable id for a list serial: digit string or single letter (lowercased)."""
    s = (marker or "").strip()
    d = marker_digit(s)
    if d:
        return d
    m = re.match(r"([a-zA-Z])", s)
    return m.group(1).lower() if m else None


def normalize_list_marker_token(marker: str) -> str:
    """Force list serial to ASCII ``N.`` / ``a.`` (never ``N。`` from DeepLX)."""
    key = marker_key(marker)
    if not key:
        return (marker or "").strip()
    return f"{key}."


def normalize_leading_list_marker_text(text: str | None) -> str | None:
    """Rewrite leading ``1。`` / ``a。`` / ``1．`` → ``1.`` / ``a.`` for list items.

    DeepLX often localizes the list period to ideographic ``。``, which
    looks like a Chinese sentence end and breaks hang-width consistency.
    Also rewrites mid-string tip serials ``3。最大值`` → ``3.最大值``.
    Leading serial uses ASCII period; body ``句号。`` stays.
    """
    if text is None:
        return None
    if not text:
        return text
    # NBSP from MT
    t = text.replace("\xa0", " ").replace("\u2009", " ")
    m = LEADING_LIST_MARKER_DOT_RE.match(t)
    if m:
        rest = t[m.end() :]
        # CJK body: no space after ``1.`` (same as EN dual ``1.Start`` often);
        # Latin body: one space.
        if rest and not rest[0].isspace():
            if not _is_cjk_char0(rest):
                rest = " " + rest
        num = m.group("num")
        # Letters stay lowercase for hang consistency (a. b. …)
        if num.isalpha():
            num = num.lower()
        t = f"{m.group('lead')}{num}.{rest}"
    # Mid-string tip/list serials (Day 6 ``提示 3。最大值前戏``)
    t2 = MID_LIST_IDEO_PERIOD_RE.sub(
        lambda mm: f"{mm.group('num').lower() if mm.group('num').isalpha() else mm.group('num')}.",
        t,
    )
    return t2


def join_list_marker_to_body(marker: str, body: str) -> str:
    """Prepend normalized ``4.`` to body without double spaces; CJK needs no gap."""
    m = normalize_list_marker_token(marker)
    b = body or ""
    if not m:
        return b
    if not b:
        return m
    if m[-1:].isspace() or b[0].isspace():
        return m + b
    # Ideographic body (CJK) — ``1.先将…`` (ASCII period, no space)
    if _is_cjk_char0(b):
        return m + b
    return m + " " + b


def strip_trailing_marker_from_compositions(
    paragraph: il_version_1.PdfParagraph,
    marker: str,
) -> bool:
    """Remove trailing serial from compositions. Returns True if a composition changed."""
    want = marker_key(marker)
    if not want or not paragraph.pdf_paragraph_composition:
        return False
    comps = paragraph.pdf_paragraph_composition
    for i in range(len(comps) - 1, -1, -1):
        comp = comps[i]
        ssu = comp.pdf_same_style_unicode_characters
        if ssu is not None and ssu.unicode:
            text = ssu.unicode
            m = TRAILING_LIST_MARKER_RE.search(text.rstrip())
            if m and marker_key(m.group("marker")) == want:
                # Keep body including its sentence terminator; drop marker.
                new_text = m.group("body").rstrip()
                ssu.unicode = new_text
                if not ssu.unicode.strip():
                    del comps[i]
                return True
        formula = comp.pdf_formula
        if formula is not None and formula.pdf_character:
            ftext = "".join(
                (c.char_unicode or "") for c in formula.pdf_character
            ).strip()
            if marker_key(ftext) == want and re.fullmatch(
                r"(?:\d{1,3}|[a-zA-Z])\s*[\.．。、\)]?", ftext
            ):
                del comps[i]
                return True
    return False


def prepend_marker_to_compositions(
    paragraph: il_version_1.PdfParagraph,
    marker: str,
    style: PdfStyle | None = None,
) -> None:
    """Ensure leading serial exists on compositions (and matches ``unicode``)."""
    marker = normalize_list_marker_token(marker)
    if not marker:
        return
    comps = paragraph.pdf_paragraph_composition
    if comps is None:
        paragraph.pdf_paragraph_composition = []
        comps = paragraph.pdf_paragraph_composition

    # Prefer mutating the first unicode span.
    if comps:
        ssu = comps[0].pdf_same_style_unicode_characters
        if ssu is not None and ssu.unicode is not None:
            body = ssu.unicode
            if LIST_MARKER_RE.match(body.lstrip()):
                # Already has a serial — still normalize ``4。`` → ``4.``
                ssu.unicode = normalize_leading_list_marker_text(body)
                return
            ssu.unicode = join_list_marker_to_body(marker, body)
            return

    use_style = style or getattr(paragraph, "pdf_style", None)
    ssu = PdfSameStyleUnicodeCharacters(unicode=marker, pdf_style=use_style)
    comps.insert(0, PdfParagraphComposition(pdf_same_style_unicode_characters=ssu))


def normalize_list_marker_on_paragraph(
    paragraph: il_version_1.PdfParagraph,
) -> bool:
    """Normalize leading list punct on unicode + first composition. True if changed."""
    changed = False
    old_u = getattr(paragraph, "unicode", None)
    new_u = normalize_leading_list_marker_text(old_u)
    if new_u is not None and new_u != old_u:
        paragraph.unicode = new_u
        changed = True
    comps = paragraph.pdf_paragraph_composition or []
    if comps:
        ssu = comps[0].pdf_same_style_unicode_characters
        if ssu is not None and ssu.unicode is not None:
            new_c = normalize_leading_list_marker_text(ssu.unicode)
            if new_c is not None and new_c != ssu.unicode:
                ssu.unicode = new_c
                changed = True
    return changed


def reattach_trailing_list_markers(
    paragraphs: list[il_version_1.PdfParagraph] | None,
) -> int:
    """Strip trailing glued serials; move onto next item when it lacks one.

    ATU dual p21 cases:
    * Item 3 ends ``…恰到好处。4.`` and item 4 body has no leading serial
      → move ``4.`` to item 4 start.
    * Item 4 *already* starts with ``4。`` but item 3 still ends with ``4.``
      (duplicate after partial fix / MT) → **still strip** trailing from 3.

    Always normalize leading serials to ASCII ``N.`` (not ``N。``).
    """
    if not paragraphs or len(paragraphs) < 2:
        return 0
    moved = 0
    for i in range(len(paragraphs) - 1):
        prev = paragraphs[i]
        nxt = paragraphs[i + 1]
        prev_text = (getattr(prev, "unicode", None) or "").replace("\xa0", " ")
        next_text = (getattr(nxt, "unicode", None) or "").replace("\xa0", " ")
        if not prev_text.strip():
            continue
        m = TRAILING_LIST_MARKER_RE.search(prev_text.rstrip())
        if not m:
            continue
        marker_raw = m.group("marker").strip()
        marker = normalize_list_marker_token(marker_raw)
        body_prev = m.group("body").rstrip()
        if len(body_prev) < 8:
            continue

        next_has_marker = looks_like_numbered_list_item(nxt)
        # Strip trailing serial from prev always (dedupe when next already
        # has the leading marker — ATU p21 after partial reattach).
        prev.unicode = body_prev
        strip_trailing_marker_from_compositions(prev, marker_raw)
        # Sync first composition if strip missed multi-span residual
        if (prev.unicode or "").rstrip() != body_prev:
            prev.unicode = body_prev
        comps = prev.pdf_paragraph_composition or []
        if comps:
            ssu = comps[-1].pdf_same_style_unicode_characters
            if ssu is not None and ssu.unicode:
                tm = TRAILING_LIST_MARKER_RE.search(ssu.unicode.rstrip())
                if tm and marker_key(tm.group("marker")) == marker_key(marker):
                    ssu.unicode = tm.group("body").rstrip()

        if not next_has_marker:
            if len((next_text or "").strip()) < 6:
                # Stripped prev only; next too short to own the serial
                moved += 1
                continue
            nxt.unicode = join_list_marker_to_body(marker, next_text.lstrip())
            prepend_marker_to_compositions(
                nxt, marker, style=getattr(nxt, "pdf_style", None)
            )
            if (
                prev.box is not None
                and nxt.box is not None
                and prev.box.x is not None
                and nxt.box.x is not None
                and float(nxt.box.x) > float(prev.box.x) + 4.0
            ):
                nxt.box.x = float(prev.box.x)
            try:
                nxt.first_line_indent = 0.0
            except Exception:
                pass
        else:
            # Next already has a leading serial — just normalize its punct
            normalize_list_marker_on_paragraph(nxt)

        moved += 1
        logger.debug(
            "List marker glue: stripped trailing %r from prev; next_has=%s",
            marker,
            next_has_marker,
        )
    return moved


def normalize_list_markers_on_document(
    document: il_version_1.Document,
) -> int:
    """Normalize leading ``N。`` → ``N.`` on every list-like paragraph."""
    n = 0
    for page in document.page or []:
        for para in page.pdf_paragraph or []:
            if normalize_list_marker_on_paragraph(para):
                n += 1
    if n:
        logger.info(
            "Normalized %d leading list marker(s) to ASCII period", n
        )
    return n


def reattach_trailing_list_markers_on_document(
    document: il_version_1.Document,
) -> int:
    """Page-wise pass; call once before typesetting."""
    total = 0
    for page in document.page or []:
        total += reattach_trailing_list_markers(page.pdf_paragraph)
    # Always normalize leading list dots after reattach (and for clean items)
    normalize_list_markers_on_document(document)
    if total:
        logger.info(
            "Reattached/stripped %d trailing list marker(s) before typesetting",
            total,
        )
    return total
