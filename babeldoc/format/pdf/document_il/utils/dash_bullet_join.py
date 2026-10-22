"""Attach a tall dash bullet to the list item it marks.

A 30pt en-dash sits on the first line of an item, but its box starts above
that line. The heading then swallows it, or it stays its own paragraph and
paints in the gap after the item text moves. Move that one glyph onto the
item. A hyphen that ends a word stays where it is.
"""

from __future__ import annotations

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraphComposition
from babeldoc.format.pdf.document_il.utils.layout_helper import composition_characters

# En dash, em dash, figure dash, minus. Hyphen-minus is a word break.
_DASH_MARKS = frozenset("\u2013\u2014\u2012\u2212")
# The item text starts just to the right of the dash.
_MAX_GAP_X = 36.0
_MIN_Y_OVERLAP = 2.0


def _comp_text(comp: PdfParagraphComposition) -> str:
    return "".join(
        char.char_unicode or "" for char in composition_characters(comp)
    ).strip()


def _is_dash_mark(comp: PdfParagraphComposition) -> bool:
    return _comp_text(comp) in _DASH_MARKS


def _comp_box(comp: PdfParagraphComposition) -> Box | None:
    boxes: list[Box] = []
    for char in composition_characters(comp):
        visual = getattr(char, "visual_bbox", None)
        box = getattr(visual, "box", None) if visual is not None else None
        if box is None:
            box = getattr(char, "box", None)
        if box is None or None in (box.x, box.y, box.x2, box.y2):
            continue
        boxes.append(box)
    if not boxes:
        line = getattr(comp, "pdf_line", None)
        box = getattr(line, "box", None) if line is not None else None
        if box is None or None in (box.x, box.y, box.x2, box.y2):
            return None
        return box
    return Box(
        x=min(float(box.x) for box in boxes),
        y=min(float(box.y) for box in boxes),
        x2=max(float(box.x2) for box in boxes),
        y2=max(float(box.y2) for box in boxes),
    )


def _first_text_box(paragraph: PdfParagraph) -> Box | None:
    for comp in paragraph.pdf_paragraph_composition or []:
        if _is_dash_mark(comp):
            continue
        box = _comp_box(comp)
        if box is not None:
            return box
    return None


def _y_overlap(a: Box, b: Box) -> float:
    return min(float(a.y2), float(b.y2)) - max(float(a.y), float(b.y))


def _item_for(
    paragraphs: list[PdfParagraph],
    source: PdfParagraph,
    dash: Box,
) -> PdfParagraph | None:
    """The item whose first line sits just to the right of this dash."""
    best: PdfParagraph | None = None
    best_gap: float | None = None
    for other in paragraphs:
        if other is source:
            continue
        box = _first_text_box(other)
        if box is None or _y_overlap(dash, box) < _MIN_Y_OVERLAP:
            continue
        gap = float(box.x) - float(dash.x2)
        if gap < -2.0 or gap > _MAX_GAP_X:
            continue
        if best_gap is None or gap < best_gap:
            best = other
            best_gap = gap
    return best


def _dash_lines(paragraph: PdfParagraph) -> list[PdfParagraphComposition]:
    """A lone dash paragraph, or a heading's trailing dash line."""
    comps = list(paragraph.pdf_paragraph_composition or [])
    if not comps:
        return []
    dashes = [comp for comp in comps if _is_dash_mark(comp)]
    if not dashes:
        return []
    earlier = [comp for comp in comps if comp not in dashes]
    if not earlier:
        return dashes
    if comps[-1] in dashes:
        return [comps[-1]]
    return []


def join_dash_bullets(paragraphs: list[PdfParagraph]) -> int:
    """Move each dash bullet onto the item beside it. Returns how many moved."""
    if not paragraphs:
        return 0
    moves: list[tuple[PdfParagraph, PdfParagraphComposition, PdfParagraph]] = []
    for paragraph in paragraphs:
        for comp in _dash_lines(paragraph):
            box = _dash_reach(comp)
            if box is None:
                continue
            target = _item_for(paragraphs, paragraph, box)
            if target is None:
                continue
            moves.append((paragraph, comp, target))
    moved = 0
    for source, comp, target in moves:
        comps = source.pdf_paragraph_composition
        if comps is None or comp not in comps:
            continue
        comps.remove(comp)
        if target.pdf_paragraph_composition is None:
            target.pdf_paragraph_composition = []
        target.pdf_paragraph_composition.insert(0, comp)
        moved += 1
    if moved:
        paragraphs[:] = [
            paragraph
            for paragraph in paragraphs
            if paragraph.pdf_paragraph_composition
        ]
    return moved


def _comp_font_size(comp: PdfParagraphComposition) -> float:
    sizes = []
    for char in composition_characters(comp):
        style = getattr(char, "pdf_style", None)
        size = getattr(style, "font_size", None) if style is not None else None
        if size:
            sizes.append(float(size))
    if not sizes:
        return 0.0
    return max(sizes)


def _dash_reach(comp: PdfParagraphComposition) -> Box | None:
    """The dash glyph's vertical reach.

    A 30pt en-dash is sometimes stored as a 1pt sliver on its centerline.
    Open that sliver to the font size so it still meets the line it marks.
    """
    box = _comp_box(comp)
    if box is None:
        return None
    size = _comp_font_size(comp)
    height = float(box.y2) - float(box.y)
    if size <= 0.0 or height >= size * 0.5:
        return box
    mid = (float(box.y) + float(box.y2)) / 2.0
    half = size / 2.0
    return Box(
        x=float(box.x),
        y=mid - half,
        x2=float(box.x2),
        y2=mid + half,
    )
