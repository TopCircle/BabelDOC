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
from babeldoc.format.pdf.document_il import PdfParagraphComposition
from babeldoc.format.pdf.document_il.utils.layout_helper import is_bullet_point
from babeldoc.format.pdf.document_il.utils.text_recovery import should_join_hyphen_wrap

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


def line_dominant_font_size(line: PdfLine | None) -> float | None:
    """Most common non-space font_size on a line."""
    if line is None or not line.pdf_character:
        return None
    sizes: list[float] = []
    for c in line.pdf_character:
        u = c.char_unicode
        if not u or u.isspace():
            continue
        fs = c.pdf_style.font_size if c.pdf_style else None
        if fs is not None and fs > 0:
            sizes.append(float(fs))
    if not sizes:
        return None
    return Counter(sizes).most_common(1)[0][0]


# Soft OCR face-keep still hard-splits when sizes differ by this ratio
# (title 15pt → body 11pt) or either line is short (heading / uni line).
_SOFT_SIZE_RATIO_HARD_SPLIT = 1.18
_SOFT_SHORT_LINE_CHARS = 48


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


def should_split_on_font_size_jump(
    prev_line: PdfLine,
    curr_line: PdfLine,
    *,
    ratio_threshold: float = _SOFT_SIZE_RATIO_HARD_SPLIT,
) -> bool:
    """Split when dominant font *size* jumps (title→author→affiliation).

    Searchable dual-layer PDFs often use the **same** Times face for title,
    author, and uni line — only size changes (15 → 12 → 9). Face-id switch
    alone cannot separate them, which glued ``SchudsonUNIVERSITY`` and lost
    independent title typesetting.

    Do **not** split long body lines on moderate size noise (e.g. 11pt body vs
    7.5pt Courier mid-clause) — that orphans the courier tail and soft face
    keep never runs. Require a short line (header stack) or title-scale size.
    """
    prev_sz = line_dominant_font_size(prev_line)
    curr_sz = line_dominant_font_size(curr_line)
    if not prev_sz or not curr_sz:
        return False
    lo, hi = (prev_sz, curr_sz) if prev_sz <= curr_sz else (curr_sz, prev_sz)
    if hi / lo < ratio_threshold:
        return False
    # Title-scale face (either side)
    if prev_sz >= 13.0 or curr_sz >= 13.0:
        return True
    prev_len = len(line_text(prev_line).strip())
    curr_len = len(line_text(curr_line).strip())
    # Header/affiliation lines are short; long body runs keep soft face policy
    return prev_len <= _SOFT_SHORT_LINE_CHARS or curr_len <= _SOFT_SHORT_LINE_CHARS


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

    **OCR / searchable-image** (``soft_mid_sentence=True``): keep mid-sentence
    Times→Courier (often smaller) in **long body** for MT — size alone must
    not hard-split those. Still **hard-split** structural cases: title-scale
    size, or short heading-like lines (title/author/uni stack).
    """
    if not is_font_face_switch(prev_line, curr_line):
        return False
    if not soft_mid_sentence:
        return True

    prev_sz = line_dominant_font_size(prev_line)
    curr_sz = line_dominant_font_size(curr_line)
    prev_len = len(line_text(prev_line).strip())
    curr_len = len(line_text(curr_line).strip())
    size_jump = False
    if prev_sz and curr_sz:
        lo, hi = (prev_sz, curr_sz) if prev_sz <= curr_sz else (curr_sz, prev_sz)
        size_jump = hi / lo >= _SOFT_SIZE_RATIO_HARD_SPLIT

    # Structural hard split (same policy as should_split_on_font_size_jump)
    if size_jump and (prev_sz >= 13.0 or curr_sz >= 13.0):
        return True
    if size_jump and (
        prev_len <= _SOFT_SHORT_LINE_CHARS or curr_len <= _SOFT_SHORT_LINE_CHARS
    ):
        return True
    # Short heading line + face change without large size jump
    if (
        not size_jump
        and (prev_len <= _SOFT_SHORT_LINE_CHARS or curr_len <= _SOFT_SHORT_LINE_CHARS)
        and line_ends_sentence(prev_line)
    ):
        return True

    # Long body mid-clause Times→Courier: keep for MT
    return line_ends_sentence(prev_line)


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



# OA chapter openers: Trajan "CHAPTER N" (~32pt) + display title (~56pt) often
# share one line because the chapter NUMBER is painted at the title size
# (Ch1 "1 Love and Sex", Ch3 "3 beanactIonMan"). Ch5 keeps the digit at 32pt
# so line-threading already splits. Cut after the marker, not after "Chapter".
_CHAPTER_OPENER_PREFIX_RE = re.compile(
    r"^(?P<marker>chapter\s*\d{1,3})(?!\d)",
    re.IGNORECASE,
)
# Running headers are 13–15pt; openers are 32/56pt.
_CHAPTER_OPENER_MIN_PT = 24.0


def _char_font_size(ch) -> float:
    st = getattr(ch, "pdf_style", None)
    if st is None or st.font_size is None:
        return 0.0
    try:
        return float(st.font_size)
    except (TypeError, ValueError):
        return 0.0


def paragraph_line_chars(paragraph: PdfParagraph) -> list:
    """Flatten line/character compositions (pre-styles chapter split)."""
    chars: list = []
    for comp in paragraph.pdf_paragraph_composition or []:
        if comp.pdf_line and comp.pdf_line.pdf_character:
            chars.extend(comp.pdf_line.pdf_character)
        elif comp.pdf_character:
            chars.append(comp.pdf_character)
        elif (
            comp.pdf_same_style_characters
            and comp.pdf_same_style_characters.pdf_character
        ):
            chars.extend(comp.pdf_same_style_characters.pdf_character)
    return chars


def _box_from_chars(chars) -> Box:
    xs: list[float] = []
    ys: list[float] = []
    x2s: list[float] = []
    y2s: list[float] = []
    for ch in chars:
        box = getattr(ch, "box", None)
        vb = getattr(ch, "visual_bbox", None)
        if box is None and vb is not None:
            box = getattr(vb, "box", None)
        if box is None or box.x is None or box.y is None:
            continue
        xs.append(float(box.x))
        ys.append(float(box.y))
        x2s.append(float(box.x2) if box.x2 is not None else float(box.x))
        y2s.append(float(box.y2) if box.y2 is not None else float(box.y))
    if not xs:
        return Box(x=0, y=0, x2=0, y2=0)
    return Box(x=min(xs), y=min(ys), x2=max(x2s), y2=max(y2s))


def chapter_display_title_cut_index(chars: list) -> int | None:
    """Index of the first display-title glyph after ``Chapter N``, or None.

    Requires an opener-scale max font so 13pt running headers
    (``Love and Sex Chapter 1``) stay one paragraph.
    """
    if not chars:
        return None
    raw = "".join((c.char_unicode or "") for c in chars)
    match = _CHAPTER_OPENER_PREFIX_RE.match(raw)
    if not match:
        return None
    rest = raw[match.end() :]
    if not any(ch.isalpha() for ch in rest):
        return None
    max_sz = max((_char_font_size(c) for c in chars), default=0.0)
    if max_sz < _CHAPTER_OPENER_MIN_PT:
        return None
    target = match.end()
    while target < len(raw) and raw[target].isspace():
        target += 1
    if target >= len(raw):
        return None
    pos = 0
    for i, ch in enumerate(chars):
        u = ch.char_unicode or ""
        n = len(u) if u else 0
        if n == 0:
            continue
        if pos <= target < pos + n:
            return i
        pos += n
    return None


def split_glued_chapter_title_paragraph(
    paragraph: PdfParagraph,
    *,
    new_debug_id: str,
) -> PdfParagraph | None:
    """Split ``Chapter N`` + display title into two paragraphs. Mutates *paragraph*.

    Returns the new title paragraph, or None when no cut applies.
    """
    chars = paragraph_line_chars(paragraph)
    cut = chapter_display_title_cut_index(chars)
    if cut is None or cut <= 0 or cut >= len(chars):
        return None
    chapter_chars = chars[:cut]
    title_chars = chars[cut:]
    if not chapter_chars or not title_chars:
        return None
    if not any((c.char_unicode or "").strip() for c in title_chars):
        return None

    def _as_line(part) -> PdfParagraphComposition:
        box = _box_from_chars(part)
        return PdfParagraphComposition(
            pdf_line=PdfLine(box=box, pdf_character=list(part))
        )

    paragraph.pdf_paragraph_composition = [_as_line(chapter_chars)]
    paragraph.box = _box_from_chars(chapter_chars)
    title_box = _box_from_chars(title_chars)
    return PdfParagraph(
        box=title_box,
        pdf_paragraph_composition=[_as_line(title_chars)],
        unicode="",
        debug_id=new_debug_id,
        layout_label=paragraph.layout_label,
        layout_id=paragraph.layout_id,
    )


def split_glued_chapter_title_paragraphs(
    paragraphs: list[PdfParagraph],
    *,
    new_debug_id_factory,
) -> None:
    """In-place: cut glued OA chapter openers into Chapter N + display title."""
    i = 0
    while i < len(paragraphs):
        new_para = split_glued_chapter_title_paragraph(
            paragraphs[i],
            new_debug_id=new_debug_id_factory(),
        )
        if new_para is None:
            i += 1
            continue
        paragraphs.insert(i + 1, new_para)
        i += 2



def is_hyphen_wrap_continuation(prev_line: PdfLine, curr_line: PdfLine | None) -> bool:
    """True when *curr_line* continues a TeX soft-hyphen wrap on *prev_line*.

    Keeps ``stu-`` / ligature ``ff`` in one paragraph so MT sees ``stuff``.
    Figure labels after a hyphen (``ap-`` / ``Ancilla``) do not match.
    """
    if curr_line is None:
        return False
    return should_join_hyphen_wrap(line_text(prev_line), line_text(curr_line))


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

    if curr_line.pdf_character and is_bullet_point(curr_line.pdf_character[0]):
        return True
    # Keep hyphen-wrap tails in this paragraph (even if the ligature glyph
    # uses a different subset font_id). Split would make two translate() calls.
    if is_hyphen_wrap_continuation(prev_line, curr_line):
        return False

    prev_width = (prev_line.box.x2 - prev_line.box.x) if prev_line.box else 0.0
    if (
        split_short_lines
        and prev_width > 0
        and prev_width < median_width * short_line_split_factor
    ):
        return True
    # Size jump first: same face, different pt (font.unknown title stack).
    if should_split_on_font_size_jump(prev_line, curr_line):
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
