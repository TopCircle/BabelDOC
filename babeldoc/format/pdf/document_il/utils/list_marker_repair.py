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

# Leading list markers (EN/CJK dual hanging indent).
# Digits: full range. Letters: **a–d / A–D only** (quiz options) — avoid
# hanging academic ``I. Introduction`` / ``A. Methods`` body titles.
# Ideographic ``。`` — DeepLX often rewrites ``2.`` → ``2。``.
LIST_MARKER_RE = re.compile(
    r"^(?:"
    r"\d{1,3}\s*[\.．。、\)]\s*"  # 1.  1． 1。 1、  1)
    r"|[a-dA-D]\s*[\.．。、\)]\s*"  # a. b） (quiz)
    r"|\(\s*\d{1,3}\s*\)\s*"  # (1)
    r"|\(\s*[a-dA-D]\s*\)\s*"  # (a)
    r"|[①-⑳]\s*"
    r")"
)

# Next-item serial glued onto the previous item's last sentence
# (All Tied Up dual p21: item 3 ends ``恰到好处。4.`` / item 4 ends ``垂下来。5.``).
# Require a sentence terminator immediately before the serial so prose like
# ``The answer is 42.`` is not stripped.
TRAILING_LIST_MARKER_RE = re.compile(
    r"(?P<body>.*[。．.!?！？])\s*"
    r"(?P<marker>(?:\d{1,3}|[a-dA-D])\s*[\.．。、\)])\s*$",
    re.DOTALL,
)

# Leading serial with CJK/fullwidth punct that MT rewrote from ``1.`` / ``a.``
LEADING_LIST_MARKER_DOT_RE = re.compile(
    r"^(?P<lead>\s*)(?P<num>\d{1,3}|[a-dA-D])\s*(?P<punct>[。．、])\s*"
)

# Mid-string tip serials only (Day 6 ``提示 3。最大值``) — not arbitrary ``a。``
MID_LIST_IDEO_PERIOD_RE = re.compile(
    r"(?:提示|TIP|秘诀|Moregas\w*|MOREGASM)\s*"
    r"(?P<num>\d{1,3})"
    r"\s*。"
    r"(?=[\u4e00-\u9fffA-Za-z「『《])",
    re.IGNORECASE,
)


def _is_cjk_char0(ch: str) -> bool:
    o = ord(ch[0])
    return (
        0x4E00 <= o <= 0x9FFF
        or 0x3400 <= o <= 0x4DBF
        or 0x3040 <= o <= 0x30FF
        or 0xAC00 <= o <= 0xD7AF
    )


def looks_like_list_item(paragraph: il_version_1.PdfParagraph) -> bool:
    """True when text starts like ``1.`` / ``a.`` / ``2。`` / ``(b)``."""
    text = (getattr(paragraph, "unicode", None) or "").strip()
    if not text:
        return False
    # NBSP / thin space after marker still counts as list
    text = text.replace("\xa0", " ").replace("\u2009", " ")
    return bool(LIST_MARKER_RE.match(text))


def looks_like_numbered_list_item(paragraph: il_version_1.PdfParagraph) -> bool:
    """Backward-compatible alias for :func:`looks_like_list_item`."""
    return looks_like_list_item(paragraph)


def marker_digit(marker: str) -> str | None:
    """Numeric serial only (``4.`` → ``4``). Letters use :func:`marker_key`."""
    m = re.match(r"(\d{1,3})", (marker or "").strip())
    return m.group(1) if m else None


def marker_key(marker: str) -> str | None:
    """Stable id for a list serial: digit string or quiz letter a–d (lower)."""
    s = (marker or "").strip()
    d = marker_digit(s)
    if d:
        return d
    m = re.match(r"([a-dA-D])", s)
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
    Mid-string tip serials only after tip labels: ``提示 3。最大值`` → ``3.``.
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
    # Mid-string tip serials only (``提示 3。最大值`` → keep label, ``3.``)
    t2 = MID_LIST_IDEO_PERIOD_RE.sub(
        lambda mm: mm.group(0).replace("。", ".", 1),
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
                r"(?:\d{1,3}|[a-dA-D])\s*[\.．。、\)]?", ftext
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

        next_has_marker = looks_like_list_item(nxt)
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


# Day 6 quiz: EN ``a. A flirty…`` / collapsed multi-options → ``a.a.`` / ``a.b.``
_GLUED_DUP_LETTER_RE = re.compile(
    r"(?i)(?<![a-z0-9])([a-d])\.\1\.\s*"
)
_GLUED_CONSEC_LETTERS_RE = re.compile(
    r"(?i)(?<![a-z0-9])([a-d])\.([a-d])\.\s*"
)
# Mid-paragraph next options after CJK/Latin sentence end or semicolon
_MID_OPTION_SPLIT_RE = re.compile(
    r"(?<=[。；;!?！？])\s*(?=[a-dA-D]\.\s*)"
)
# Also split when options jammed: ``…； c.`` or ``…。 b.``
_MID_OPTION_LOOSE_RE = re.compile(
    r"(?<=[\u4e00-\u9fffA-Za-z0-9）\)])\s+(?=[a-dA-D]\.\s*[\u4e00-\u9fffA-Za-z])"
)


def expand_glued_quiz_options_text(text: str | None) -> str | None:
    """Fix Day-6 style glued quiz markers in a single string.

    * ``a.a. 巧克力`` (from EN ``a. A chocolate…``) → ``a. 巧克力``
    * ``a.b. 黑色上衣`` (collapsed option b) → ``b. 黑色上衣``
    * ``b. …； c. …`` → split on newline for later paragraph split
    """
    if text is None:
        return None
    if not text:
        return text
    t = text.replace("\xa0", " ").replace("\u2009", " ")
    # Same letter doubled (article A after a.)
    t = _GLUED_DUP_LETTER_RE.sub(r"\1. ", t)
    # Two different letters with no body between → keep the *second* option letter
    # (content belongs to the latter after paragraph merge).
    t = _GLUED_CONSEC_LETTERS_RE.sub(r"\2. ", t)
    # Split subsequent options onto their own lines
    t = _MID_OPTION_SPLIT_RE.sub("\n", t)
    t = _MID_OPTION_LOOSE_RE.sub("\n", t)
    return t


def _option_line_pitch(
    paragraph: il_version_1.PdfParagraph,
    *,
    n_parts: int = 1,
    origin_box=None,
) -> float:
    """Vertical pitch (pt) between stacked quiz options (PDF y-up).

    Prefer carving the original multi-line band evenly:
    ``pitch = max(min_readable, band_height / n_parts)``.
    Falls back to font-based pitch when the box is missing or degenerate.
    """
    style = getattr(paragraph, "pdf_style", None)
    fs = float(getattr(style, "font_size", None) or 11.0)
    min_pitch = max(12.0, fs * 1.25)
    n = max(1, int(n_parts))
    b = origin_box if origin_box is not None else getattr(paragraph, "box", None)
    if (
        b is not None
        and getattr(b, "y", None) is not None
        and getattr(b, "y2", None) is not None
    ):
        band = float(b.y2) - float(b.y)
        if band > min_pitch * 0.5:
            # Even split of source band; never thinner than readable min.
            return max(min_pitch, band / n)
    return max(14.0, fs * 1.45)


def _box_for_split_option(
    origin_box,
    line_index: int,
    pitch: float,
):
    """Box for option *line_index* (0=first) stacked below *origin_box* top.

    Clones used to copy the parent box unchanged → all a–d typeset at the
    same ``box.y2`` and overpaint (Day6 dual p3–4 quiz).
    """
    b = origin_box
    if b is None or getattr(b, "x", None) is None or getattr(b, "x2", None) is None:
        return None
    top = float(b.y2) if b.y2 is not None else float(b.y or 0.0) + pitch
    y2 = top - pitch * line_index
    y = y2 - pitch
    return type(b)(x=b.x, y=y, x2=b.x2, y2=y2)


def _clone_paragraph_shell(
    paragraph: il_version_1.PdfParagraph,
    unicode: str,
    *,
    origin_box=None,
    line_index: int = 0,
    pitch: float | None = None,
) -> il_version_1.PdfParagraph:
    """Shallow-copy layout fields; new unicode composition.

    *line_index* > 0 stacks the box below *origin_box* top (PDF y-up) so
    split quiz options do not share one baseline.
    """
    style = getattr(paragraph, "pdf_style", None)
    ssu = PdfSameStyleUnicodeCharacters(unicode=unicode, pdf_style=style)
    if pitch is None:
        pitch = _option_line_pitch(paragraph)
    src_box = origin_box if origin_box is not None else getattr(paragraph, "box", None)
    box = _box_for_split_option(src_box, line_index, pitch)
    return il_version_1.PdfParagraph(
        box=box,
        pdf_style=style,
        pdf_paragraph_composition=[
            PdfParagraphComposition(pdf_same_style_unicode_characters=ssu)
        ],
        unicode=unicode,
        layout_label=getattr(paragraph, "layout_label", None),
        alignment="left",
        first_line_indent=0.0,
        debug_id=getattr(paragraph, "debug_id", None),
        xobj_id=getattr(paragraph, "xobj_id", None),
    )


def split_glued_quiz_options_on_page(
    paragraphs: list[il_version_1.PdfParagraph] | None,
) -> list[il_version_1.PdfParagraph]:
    """Expand glued ``a.a.``/``a.b.`` and split multi-option paragraphs.

    Each split option gets its **own stacked box** (not a clone of the parent
    box) so typesetting does not overpaint a–d on one baseline.
    """
    if not paragraphs:
        return paragraphs or []
    out: list[il_version_1.PdfParagraph] = []
    for para in paragraphs:
        raw = getattr(para, "unicode", None) or ""
        expanded = expand_glued_quiz_options_text(raw)
        if expanded is None:
            out.append(para)
            continue
        parts = [p.strip() for p in expanded.split("\n") if p.strip()]
        if len(parts) <= 1:
            if expanded != raw:
                para.unicode = expanded
                comps = para.pdf_paragraph_composition or []
                if comps and comps[0].pdf_same_style_unicode_characters is not None:
                    comps[0].pdf_same_style_unicode_characters.unicode = expanded
                normalize_list_marker_on_paragraph(para)
            out.append(para)
            continue
        # Multi-option: first part mutates original; rest are stacked clones.
        # Snapshot origin box *before* carving (clones must share that top).
        origin = para.box
        if origin is not None and hasattr(origin, "x"):
            origin_box = type(origin)(
                x=origin.x, y=origin.y, x2=origin.x2, y2=origin.y2
            )
        else:
            origin_box = origin
        pitch = _option_line_pitch(
            para, n_parts=len(parts), origin_box=origin_box
        )
        first = parts[0]
        para.unicode = first
        comps = para.pdf_paragraph_composition or []
        if comps and comps[0].pdf_same_style_unicode_characters is not None:
            comps[0].pdf_same_style_unicode_characters.unicode = first
        if len(comps) > 1:
            para.pdf_paragraph_composition = comps[:1]
        first_box = _box_for_split_option(origin_box, 0, pitch)
        if first_box is not None:
            para.box = first_box
        try:
            para.first_line_indent = 0.0
            para.alignment = "left"
        except Exception:
            pass
        normalize_list_marker_on_paragraph(para)
        out.append(para)
        for i, part in enumerate(parts[1:], start=1):
            clone = _clone_paragraph_shell(
                para,
                part,
                origin_box=origin_box,
                line_index=i,
                pitch=pitch,
            )
            normalize_list_marker_on_paragraph(clone)
            out.append(clone)
    return out


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
        # Quiz glue before reattach so hang sees clean serials
        if page.pdf_paragraph:
            page.pdf_paragraph = split_glued_quiz_options_on_page(
                page.pdf_paragraph
            )
        total += reattach_trailing_list_markers(page.pdf_paragraph)
    # Always normalize leading list dots after reattach (and for clean items)
    normalize_list_markers_on_document(document)
    if total:
        logger.info(
            "Reattached/stripped %d trailing list marker(s) before typesetting",
            total,
        )
    return total
