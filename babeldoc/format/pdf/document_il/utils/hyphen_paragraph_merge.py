"""Join a hyphen-wrapped stem with the paragraph directly under it.

Same-paragraph wraps already rejoin before MT. A stem that became its own
paragraph (``stimula-`` | ``tion feels``) is a separate ``translate()``
call, so the stem stays in English. Only the nearest same-column neighbor
below is eligible. An intervening paragraph blocks the join.
"""

from __future__ import annotations

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.utils.layout_helper import composition_characters
from babeldoc.format.pdf.document_il.utils.text_recovery import HYPHEN_CHARS
from babeldoc.format.pdf.document_il.utils.text_recovery import should_join_hyphen_wrap

_MAX_GAP = 22.0
_MIN_GAP = -4.0
_MIN_X_OVERLAP = 8.0
_MAX_LEFT_DELTA = 36.0


def _box_complete(box: Box | None) -> bool:
    return box is not None and None not in (box.x, box.y, box.x2, box.y2)


def _paragraph_text(paragraph: PdfParagraph) -> str:
    parts: list[str] = []
    for comp in paragraph.pdf_paragraph_composition or []:
        parts.append(
            "".join(char.char_unicode or "" for char in composition_characters(comp))
        )
    return "".join(parts)


def _column_gap(upper: PdfParagraph, lower: PdfParagraph) -> float | None:
    """Gap from *upper*'s bottom to *lower*'s top, or None if not the same column."""
    if getattr(upper, "xobj_id", None) != getattr(lower, "xobj_id", None):
        return None
    upper_box = upper.box
    lower_box = lower.box
    if not _box_complete(upper_box) or not _box_complete(lower_box):
        return None
    gap = float(upper_box.y) - float(lower_box.y2)
    if gap < _MIN_GAP or gap > _MAX_GAP:
        return None
    overlap = min(float(upper_box.x2), float(lower_box.x2)) - max(
        float(upper_box.x), float(lower_box.x)
    )
    if overlap <= _MIN_X_OVERLAP:
        return None
    if abs(float(upper_box.x) - float(lower_box.x)) > _MAX_LEFT_DELTA:
        return None
    return gap


def _nearest_below(
    paragraphs: list[PdfParagraph], upper: PdfParagraph
) -> PdfParagraph | None:
    best: PdfParagraph | None = None
    best_gap: float | None = None
    for other in paragraphs:
        if other is upper:
            continue
        gap = _column_gap(upper, other)
        if gap is None:
            continue
        if best_gap is None or gap < best_gap:
            best = other
            best_gap = gap
    return best


def _union_box(upper_box: Box, lower_box: Box) -> Box:
    return Box(
        x=min(float(upper_box.x), float(lower_box.x)),
        y=min(float(upper_box.y), float(lower_box.y)),
        x2=max(float(upper_box.x2), float(lower_box.x2)),
        y2=max(float(upper_box.y2), float(lower_box.y2)),
    )


def merge_hyphen_wrapped_paragraphs(paragraphs: list[PdfParagraph]) -> int:
    """Absorb each hyphen stem's nearest lower neighbor. Return the merge count."""
    merges = 0
    changed = True
    while changed:
        changed = False
        for upper in list(paragraphs):
            upper_text = _paragraph_text(upper).rstrip()
            if not upper_text or upper_text[-1] not in HYPHEN_CHARS:
                continue
            if not _box_complete(upper.box):
                continue
            lower = _nearest_below(paragraphs, upper)
            if lower is None or not _box_complete(lower.box):
                continue
            if not should_join_hyphen_wrap(
                upper_text, _paragraph_text(lower).lstrip()
            ):
                continue
            upper_box = upper.box
            lower_box = lower.box
            if upper_box is None or lower_box is None:
                continue
            new_compositions = list(upper.pdf_paragraph_composition or []) + list(
                lower.pdf_paragraph_composition or []
            )
            new_box = _union_box(upper_box, lower_box)
            upper.pdf_paragraph_composition = new_compositions
            upper.box = new_box
            paragraphs.remove(lower)
            merges += 1
            changed = True
            break
    return merges
