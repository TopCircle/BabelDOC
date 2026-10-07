"""Separate two translations that were painted on one baseline.

Equal tops are not vertical containment, and shrinking the box puts
``new_y2`` below the paragraph's own bottom, so retypeset draws the same
line again. Move the later paragraph down instead.
"""

from __future__ import annotations

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph

_SAME_BASELINE_OVERLAP = 0.55
_SAME_BASELINE_HEIGHT_RATIO = 1.8
_SAME_BASELINE_GAP = 1.5


def _box_height(box: Box | None) -> float | None:
    if box is None or box.y is None or box.y2 is None:
        return None
    height = float(box.y2) - float(box.y)
    if height <= 1.0:
        return None
    return height


def same_baseline_overlap(b1: Box | None, b2: Box | None) -> bool:
    """True when two rendered boxes share a baseline and overlap in x.

    A short label inside a tall paragraph is containment, not a same-line
    double paint: the taller box must be within 1.8× the shorter one.
    """
    if (
        b1 is None
        or b2 is None
        or None in (b1.x, b1.x2, b1.y, b1.y2, b2.x, b2.x2, b2.y, b2.y2)
    ):
        return False
    overlap_x = min(float(b1.x2), float(b2.x2)) - max(float(b1.x), float(b2.x))
    if overlap_x <= 4.0:
        return False
    overlap_y = min(float(b1.y2), float(b2.y2)) - max(float(b1.y), float(b2.y))
    if overlap_y <= 0:
        return False
    h1 = _box_height(b1)
    h2 = _box_height(b2)
    if h1 is None or h2 is None:
        return False
    shorter, taller = (h1, h2) if h1 <= h2 else (h2, h1)
    if overlap_y / shorter < _SAME_BASELINE_OVERLAP:
        return False
    return taller <= shorter * _SAME_BASELINE_HEIGHT_RATIO


def _shift_box_down(box: Box | None, dy: float) -> None:
    if box is None or dy == 0:
        return
    if box.y is not None:
        box.y = float(box.y) - dy
    if box.y2 is not None:
        box.y2 = float(box.y2) - dy


def _shift_char_down(char: PdfCharacter | None, dy: float) -> None:
    if char is None:
        return
    pdf_box = char.box
    _shift_box_down(pdf_box, dy)
    visual = char.visual_bbox
    visual_box = visual.box if visual is not None else None
    if visual_box is not None and visual_box is not pdf_box:
        _shift_box_down(visual_box, dy)


def _shift_paragraph_down(paragraph: PdfParagraph, dy: float) -> None:
    """Move a typeset paragraph down by *dy* pt (PDF y grows upward)."""
    if dy <= 0:
        return
    _shift_box_down(paragraph.box, dy)
    for comp in paragraph.pdf_paragraph_composition or []:
        if comp.pdf_line:
            _shift_box_down(comp.pdf_line.box, dy)
            for char in comp.pdf_line.pdf_character or []:
                _shift_char_down(char, dy)
        elif comp.pdf_character:
            _shift_char_down(comp.pdf_character, dy)
        elif comp.pdf_same_style_characters:
            _shift_box_down(comp.pdf_same_style_characters.box, dy)
            for char in comp.pdf_same_style_characters.pdf_character or []:
                _shift_char_down(char, dy)
        elif comp.pdf_formula:
            _shift_box_down(comp.pdf_formula.box, dy)
            for char in comp.pdf_formula.pdf_character or []:
                _shift_char_down(char, dy)


def separate_same_baseline_overlap(
    move: PdfParagraph,
    keep_box: Box,
    move_box: Box,
    *,
    floor_y: float | None = None,
) -> bool:
    """Drop *move* so its top sits just under *keep*. False if it leaves the page."""
    dy = float(move_box.y2) - float(keep_box.y) + _SAME_BASELINE_GAP
    if dy <= 0.5:
        return False
    new_bottom = float(move_box.y) - dy
    if floor_y is not None and new_bottom < float(floor_y) + 0.5:
        return False
    _shift_paragraph_down(move, dy)
    return True
