"""Put a sentence the layout model cut apart back into one paragraph.

A line that does not end a sentence, sitting one line-gap above the next
line of the same column, is still that sentence. ``and,`` | ``zing`` |
``your fingers`` is one sentence. A period followed by a paragraph gap
stays a new paragraph: ``breasts.`` then ``Some women``. A hyphen stem is
left for the hyphen join.
"""

from __future__ import annotations

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.utils.paragraph_split_policy import (
    line_dominant_font_id,
)
from babeldoc.format.pdf.document_il.utils.paragraph_split_policy import (
    line_dominant_font_size,
)
from babeldoc.format.pdf.document_il.utils.paragraph_split_policy import (
    line_ends_sentence,
)
from babeldoc.format.pdf.document_il.utils.paragraph_split_policy import (
    line_starts_with_list_marker,
)
from babeldoc.format.pdf.document_il.utils.paragraph_split_policy import (
    split_paragraph_at,
)
from babeldoc.format.pdf.document_il.utils.text_recovery import HYPHEN_CHARS

# Body leading leaves about 2pt between line boxes. A new paragraph on
# these pages leaves about 11pt. 6pt still joins a line; 8pt is a new paragraph.
_MAX_JOIN_GAP = 6.0
_MIN_JOIN_GAP = -2.0
_PARAGRAPH_GAP = 8.0
_GAP_FACTOR = 4.0
_MAX_LEFT_DELTA = 8.0
_SIZE_RATIO = 1.18


def repair_broken_sentences(paragraphs: list[PdfParagraph]) -> None:
    """Split paragraph gaps after a sentence, then join a cut sentence."""
    split_sentence_paragraph_gaps(paragraphs)
    merge_mid_sentence_paragraphs(paragraphs)


def split_sentence_paragraph_gaps(paragraphs: list[PdfParagraph]) -> int:
    """Split where a sentence ends and the next line is a paragraph below."""
    from babeldoc.format.pdf.document_il.midend.paragraph_finder import (
        generate_base58_id,
    )

    splits = 0
    index = 0
    while index < len(paragraphs):
        cut = _sentence_gap_cut(paragraphs[index])
        if cut is None:
            index += 1
            continue
        head = paragraphs[index]
        tail = split_paragraph_at(
            head,
            cut,
            new_debug_id=generate_base58_id(),
        )
        # Paragraph data is refreshed only after this whole repair returns.
        # Until then the tail has no characters of its own to copy these from.
        tail.xobj_id = head.xobj_id
        tail.vertical = head.vertical
        _reset_box(head)
        _reset_box(tail)
        paragraphs.insert(index + 1, tail)
        splits += 1
    return splits


def merge_mid_sentence_paragraphs(paragraphs: list[PdfParagraph]) -> int:
    """Join the nearest line below when this paragraph stops mid-sentence."""
    merges = 0
    changed = True
    while changed:
        changed = False
        for upper in list(paragraphs):
            if not _stops_mid_sentence(upper):
                continue
            lower = _nearest_below(paragraphs, upper)
            if lower is None or not _can_continue(upper, lower):
                continue
            upper.pdf_paragraph_composition = list(
                upper.pdf_paragraph_composition or []
            ) + list(lower.pdf_paragraph_composition or [])
            upper.box = _union_box(upper.box, lower.box)
            paragraphs.remove(lower)
            merges += 1
            changed = True
            break
    return merges


def _sentence_gap_cut(paragraph: PdfParagraph) -> int | None:
    rows = _ordered_lines(paragraph)
    if rows is None or len(rows) < 2:
        return None
    gaps = [
        float(rows[index][1].box.y) - float(rows[index + 1][1].box.y2)
        for index in range(len(rows) - 1)
    ]
    for offset, gap in enumerate(gaps):
        others = [item for index, item in enumerate(gaps) if index != offset]
        if others:
            median = sorted(others)[len(others) // 2]
            limit = max(_PARAGRAPH_GAP, _GAP_FACTOR * median)
        else:
            limit = _PARAGRAPH_GAP
        if gap < limit:
            continue
        if not line_ends_sentence(rows[offset][1]):
            continue
        return rows[offset + 1][0]
    return None


def _ordered_lines(paragraph: PdfParagraph):
    """Composition order, top first. None when a line is missing or out of order."""
    compositions = paragraph.pdf_paragraph_composition or []
    rows = []
    for index, composition in enumerate(compositions):
        line = getattr(composition, "pdf_line", None)
        box = getattr(line, "box", None) if line is not None else None
        if box is None or None in (box.y, box.y2):
            return None
        rows.append((index, line))
    tops = [float(line.box.y2) for _, line in rows]
    if tops != sorted(tops, reverse=True):
        return None
    return rows


def _stops_mid_sentence(paragraph: PdfParagraph) -> bool:
    line = _bottom_line(paragraph)
    if line is None:
        return False
    text = "".join(
        char.char_unicode or "" for char in (line.pdf_character or [])
    ).rstrip()
    if not text or text[-1] in HYPHEN_CHARS:
        return False
    return not line_ends_sentence(line)


def _bottom_line(paragraph: PdfParagraph):
    lines = []
    for composition in paragraph.pdf_paragraph_composition or []:
        line = getattr(composition, "pdf_line", None)
        box = getattr(line, "box", None) if line is not None else None
        if box is None or box.y is None:
            continue
        lines.append(line)
    if not lines:
        return None
    return min(lines, key=lambda line: float(line.box.y))


def _top_line(paragraph: PdfParagraph):
    lines = []
    for composition in paragraph.pdf_paragraph_composition or []:
        line = getattr(composition, "pdf_line", None)
        box = getattr(line, "box", None) if line is not None else None
        if box is None or box.y2 is None:
            continue
        lines.append(line)
    if not lines:
        return None
    return max(lines, key=lambda line: float(line.box.y2))


def _can_continue(upper: PdfParagraph, lower: PdfParagraph) -> bool:
    if getattr(upper, "xobj_id", None) != getattr(lower, "xobj_id", None):
        return False
    upper_line = _bottom_line(upper)
    lower_line = _top_line(lower)
    if upper_line is None or lower_line is None:
        return False
    if line_starts_with_list_marker(lower_line):
        return False
    if _font_blocks(upper_line, lower_line):
        return False
    if abs(float(upper_line.box.x) - float(lower_line.box.x)) > _MAX_LEFT_DELTA:
        return False
    return True


def _font_blocks(upper_line, lower_line) -> bool:
    upper_size = line_dominant_font_size(upper_line)
    lower_size = line_dominant_font_size(lower_line)
    if upper_size and lower_size:
        lo, hi = (
            (upper_size, lower_size)
            if upper_size <= lower_size
            else (lower_size, upper_size)
        )
        if hi / lo >= _SIZE_RATIO:
            return True
    upper_face = line_dominant_font_id(upper_line)
    lower_face = line_dominant_font_id(lower_line)
    return bool(upper_face and lower_face and upper_face != lower_face)


def _nearest_below(paragraphs: list[PdfParagraph], upper: PdfParagraph):
    if upper.box is None or None in (upper.box.y, upper.box.y2, upper.box.x):
        return None
    best = None
    best_gap = None
    for other in paragraphs:
        if other is upper or other.box is None:
            continue
        if None in (other.box.y, other.box.y2, other.box.x):
            continue
        if getattr(upper, "xobj_id", None) != getattr(other, "xobj_id", None):
            continue
        gap = float(upper.box.y) - float(other.box.y2)
        if gap < _MIN_JOIN_GAP or gap > _MAX_JOIN_GAP:
            continue
        if abs(float(upper.box.x) - float(other.box.x)) > _MAX_LEFT_DELTA:
            continue
        if best_gap is None or gap < best_gap:
            best = other
            best_gap = gap
    return best


def _reset_box(paragraph: PdfParagraph) -> None:
    boxes = []
    for composition in paragraph.pdf_paragraph_composition or []:
        line = getattr(composition, "pdf_line", None)
        box = getattr(line, "box", None) if line is not None else None
        if box is None or None in (box.x, box.y, box.x2, box.y2):
            continue
        boxes.append(box)
    if not boxes:
        return
    paragraph.box = Box(
        x=min(float(box.x) for box in boxes),
        y=min(float(box.y) for box in boxes),
        x2=max(float(box.x2) for box in boxes),
        y2=max(float(box.y2) for box in boxes),
    )


def _union_box(upper: Box, lower: Box) -> Box:
    return Box(
        x=min(float(upper.x), float(lower.x)),
        y=min(float(upper.y), float(lower.y)),
        x2=max(float(upper.x2), float(lower.x2)),
        y2=max(float(upper.y2), float(lower.y2)),
    )
