"""Line-pair policies for splitting multi-line paragraphs.

Used by ``ParagraphFinder.process_independent_paragraphs`` so split triggers
live in one place instead of growing if-ladders inside the finder loop.

Phase B (dual-layer recover): font-face switch is **hard** on born-digital
PDFs and **soft** (sentence-final only) when ``ocr_workaround`` is on.
"""

from __future__ import annotations

import re
from collections import Counter

from babeldoc.format.pdf.document_il import Box
from babeldoc.format.pdf.document_il import PdfLine
from babeldoc.format.pdf.document_il import PdfParagraph
from babeldoc.format.pdf.document_il.utils.layout_helper import is_bullet_point

# arXiv / journal date lines glued under affiliation
_DATE_LINE_RE = re.compile(
    r"(\(\s*Dated\b|Dated\s*:|日期\s*[:：]|\(\s*日期)",
    re.IGNORECASE,
)
_TOC_LEADER_RE = re.compile(r"\.{20,}")


def line_text(line: PdfLine | None) -> str:
    if line is None or not line.pdf_character:
        return ""
    return "".join(c.char_unicode or "" for c in line.pdf_character)


def line_dominant_font_id(line: PdfLine | None) -> str | None:
    """Most common non-space font_id on a line."""
    if line is None or not line.pdf_character:
        return None
    ids: list[str] = []
    for c in line.pdf_character:
        u = c.char_unicode
        if not u or u.isspace():
            continue
        fid = c.pdf_style.font_id if c.pdf_style else None
        if fid:
            ids.append(fid)
    if not ids:
        return None
    return Counter(ids).most_common(1)[0][0]


def is_toc_leader_line(prev_line: PdfLine) -> bool:
    """Directory-style leaders: many consecutive dots on the previous line."""
    return bool(_TOC_LEADER_RE.search(line_text(prev_line)))


def is_font_face_switch(prev_line: PdfLine, curr_line: PdfLine) -> bool:
    """Dominant font_id changes between adjacent lines (e.g. Times → Courier).

    Uses font_id rather than full typeface metadata because compositions only
    carry style.font_id at this stage; subset IDs still differ across faces.
    """
    prev_fid = line_dominant_font_id(prev_line)
    curr_fid = line_dominant_font_id(curr_line)
    return bool(prev_fid and curr_fid and prev_fid != curr_fid)


# Trailing closers stripped before checking sentence terminators.
_TRAILING_CLOSERS = "\"'”’)]）』」"


def line_ends_sentence(line: PdfLine | None) -> bool:
    """True if the line's text ends a clause/sentence (not mid-phrase wrap).

    Used to avoid bisecting a clause on a mid-sentence Times→Courier switch
    (font.unknown: ``… occasional | sensationalism …``), which yields broken
    machine translation on both sides of the cut.
    """
    text = line_text(line).rstrip()
    if not text:
        return False
    while text and text[-1] in _TRAILING_CLOSERS:
        text = text[:-1].rstrip()
    if not text:
        return False
    return text[-1] in ".!?。！？…:"


def should_split_on_font_face_switch(
    prev_line: PdfLine,
    curr_line: PdfLine,
    *,
    soft_mid_sentence: bool = False,
) -> bool:
    """Whether a dominant-font change should start a new paragraph.

    **Born-digital default** (``soft_mid_sentence=False``): any face switch
    splits. arXiv pages interleave body (``SFRM*``) with figure labels
    (``Arial*``) in reading order; keeping those mid-sentence glues labels
    into body paragraphs (translated chart labels mid-clause).

    **OCR / searchable-image** (``soft_mid_sentence=True``): only split when
    the previous line is sentence-final. Mid-sentence Times→Courier emphasis
    on dual-layer scans (font.unknown) must stay one clause for MT; rich-text
    still paints faces without a hard break.
    """
    if not is_font_face_switch(prev_line, curr_line):
        return False
    if soft_mid_sentence:
        return line_ends_sentence(prev_line)
    return True


def is_short_centered_date_tail(
    prev_line: PdfLine,
    curr_line: PdfLine,
    *,
    median_width: float,
) -> bool:
    """Short inset last line that looks like (Dated: …) under affiliation."""
    if not prev_line.box or not curr_line.box:
        return False
    prev_width = prev_line.box.x2 - prev_line.box.x
    curr_w = curr_line.box.x2 - curr_line.box.x
    curr_text = line_text(curr_line).strip()
    short_tail = curr_w < prev_width * 0.45 and (
        median_width <= 0 or curr_w < median_width * 0.55
    )
    both_inset = (
        curr_line.box.x > prev_line.box.x + 8.0
        and curr_line.box.x2 < prev_line.box.x2 - 8.0
    )
    date_like = bool(_DATE_LINE_RE.search(curr_text))
    return bool(short_tail and both_inset and (date_like or curr_w < 120.0))


def should_split_line_pair(
    prev_line: PdfLine,
    curr_line: PdfLine | None,
    *,
    median_width: float,
    split_short_lines: bool,
    short_line_split_factor: float,
    soft_mid_sentence_font_split: bool = False,
) -> bool:
    """Whether to split a multi-line paragraph so ``curr_line`` starts a new para.

    Order is intentional: cheap geometric/text checks first, then face switch.
    ``soft_mid_sentence_font_split`` is True under OCR workaround (see
    ``should_split_on_font_face_switch``).
    """
    if is_toc_leader_line(prev_line):
        return True
    if curr_line is None:
        return False

    prev_width = (prev_line.box.x2 - prev_line.box.x) if prev_line.box else 0.0
    if (
        split_short_lines
        and prev_width > 0
        and prev_width < median_width * short_line_split_factor
    ):
        return True
    if curr_line.pdf_character and is_bullet_point(curr_line.pdf_character[0]):
        return True
    if should_split_on_font_face_switch(
        prev_line,
        curr_line,
        soft_mid_sentence=soft_mid_sentence_font_split,
    ):
        return True
    if is_short_centered_date_tail(
        prev_line, curr_line, median_width=median_width
    ):
        return True
    return False


def split_paragraph_at(
    paragraph: PdfParagraph,
    j: int,
    *,
    new_debug_id: str,
) -> PdfParagraph:
    """Split ``paragraph`` so compositions ``[j:]`` become a new paragraph.

    Mutates ``paragraph`` to keep ``[:j]``. Returns the new tail paragraph
    (caller should run ``update_paragraph_data`` on both).
    """
    tail = paragraph.pdf_paragraph_composition[j:]
    paragraph.pdf_paragraph_composition = paragraph.pdf_paragraph_composition[:j]
    return PdfParagraph(
        box=Box(0, 0, 0, 0),  # temporary; update_paragraph_data recomputes
        pdf_paragraph_composition=tail,
        unicode="",
        debug_id=new_debug_id,
        layout_label=paragraph.layout_label,
        layout_id=paragraph.layout_id,
    )
