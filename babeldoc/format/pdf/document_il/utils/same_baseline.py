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
# A side quote can cross the paragraph's union when another line is
# wider. A touch under this stays beside that line.
_BESIDE_LINE = 8.0


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


def _composition_chars(comp) -> list:
    if comp.pdf_character is not None:
        return [comp.pdf_character]
    if comp.pdf_line is not None:
        return list(comp.pdf_line.pdf_character or [])
    same = comp.pdf_same_style_characters
    if same is not None:
        return list(same.pdf_character or [])
    formula = comp.pdf_formula
    if formula is not None:
        return list(formula.pdf_character or [])
    return []


def _line_tops(paragraph: PdfParagraph) -> list[float]:
    """One top per rendered line. Characters are the line when no pdf_line exists."""
    raw: list[float] = []
    for comp in paragraph.pdf_paragraph_composition or []:
        for char in _composition_chars(comp):
            box = getattr(char, "box", None)
            if box is None or box.y is None or box.y2 is None:
                continue
            if float(box.y2) - float(box.y) <= 1.0:
                continue
            raw.append(float(box.y2))
    if not raw:
        return []
    ordered = sorted(raw, reverse=True)
    lines = [ordered[0]]
    for top in ordered[1:]:
        if lines[-1] - top > 1.5:
            lines.append(top)
    return lines


def _line_pitch(paragraph: PdfParagraph) -> float:
    """Leading already used inside this paragraph. One line uses its height."""
    lines = _line_tops(paragraph)
    if len(lines) >= 2:
        steps = [
            lines[index] - lines[index + 1]
            for index in range(len(lines) - 1)
            if lines[index] - lines[index + 1] > 1.0
        ]
        if steps:
            return min(steps)
    for comp in paragraph.pdf_paragraph_composition or []:
        for char in _composition_chars(comp):
            box = getattr(char, "box", None)
            if box is None or box.y is None or box.y2 is None:
                continue
            height = float(box.y2) - float(box.y)
            if height > 1.0:
                return height
    return 0.0


def _rendered_line_boxes(paragraph: PdfParagraph) -> list[Box]:
    """One box per rendered line. The paragraph union is not a line."""
    raw: list[tuple[float, float, float, float]] = []
    for comp in paragraph.pdf_paragraph_composition or []:
        for char in _composition_chars(comp):
            box = getattr(char, "box", None)
            if box is None or None in (box.x, box.x2, box.y, box.y2):
                continue
            if float(box.y2) - float(box.y) <= 1.0:
                continue
            raw.append((float(box.x), float(box.x2), float(box.y), float(box.y2)))
    if not raw:
        return []
    ordered = sorted(raw, key=lambda item: item[3], reverse=True)
    groups: list[list[tuple[float, float, float, float]]] = [[ordered[0]]]
    for item in ordered[1:]:
        if groups[-1][0][3] - item[3] > 1.5:
            groups.append([item])
        else:
            groups[-1].append(item)
    return [
        Box(
            x=min(item[0] for item in group),
            y=min(item[2] for item in group),
            x2=max(item[1] for item in group),
            y2=max(item[3] for item in group),
        )
        for group in groups
    ]


def _boxes_cross(left: Box, right: Box, *, min_x: float) -> bool:
    overlap_x = min(float(left.x2), float(right.x2)) - max(float(left.x), float(right.x))
    overlap_y = min(float(left.y2), float(right.y2)) - max(float(left.y), float(right.y))
    return overlap_x >= min_x and overlap_y > 0


def _kept_line_crosses(keep: PdfParagraph, keep_box: Box, move_box: Box) -> bool:
    """True when *keep*'s ink, not its union, runs under *move_box*."""
    lines = _rendered_line_boxes(keep)
    if not lines:
        return _boxes_cross(keep_box, move_box, min_x=0.0)
    return any(_boxes_cross(line, move_box, min_x=_BESIDE_LINE) for line in lines)


def seat_below_kept_ink(
    first: PdfParagraph,
    second: PdfParagraph,
    first_box: Box | None,
    second_box: Box | None,
    *,
    keep_ids: set[str],
    anchored_ids: set[str],
    floor_y: float | None = None,
) -> bool:
    """Drop the paragraph under a kept paragraph's rendered ink.

    Chinese leading hangs past a scanned contour. The kept paragraph
    stays. A paragraph in ``anchored_ids`` stays on its own plan. A
    paragraph whose top is above that ink is not pulled down through it.
    A side quote that only meets the union, or grazes a line by under
    8pt, stays where it was set.
    """
    id_first = getattr(first, "layout_region_id", None)
    id_second = getattr(second, "layout_region_id", None)
    first_kept = id_first in keep_ids
    second_kept = id_second in keep_ids
    if first_kept == second_kept:
        return False
    if first_kept:
        keep, keep_box, move, move_box, move_id = (
            first,
            first_box,
            second,
            second_box,
            id_second,
        )
    else:
        keep, keep_box, move, move_box, move_id = (
            second,
            second_box,
            first,
            first_box,
            id_first,
        )
    if move_id in anchored_ids or keep_box is None or move_box is None:
        return False
    coords = (
        keep_box.x,
        keep_box.x2,
        keep_box.y,
        keep_box.y2,
        move_box.x,
        move_box.x2,
        move_box.y,
        move_box.y2,
    )
    if any(value is None for value in coords):
        return False
    if float(move_box.y2) >= float(keep_box.y2):
        return False
    # The union reaches a side quote when a lower line steps out.
    # Only a line that actually runs under the quote seats it.
    if not _kept_line_crosses(keep, keep_box, move_box):
        return False
    pitch = max(_line_pitch(keep), _line_pitch(move))
    keep_tops = _line_tops(keep)
    if pitch <= 1.0 or not keep_tops:
        return separate_same_baseline_overlap(
            move, keep_box, move_box, floor_y=floor_y
        )
    # One more line of the leading already on the page, and clear of the ink.
    target = min(min(keep_tops) - pitch, float(keep_box.y) - _SAME_BASELINE_GAP)
    dy = float(move_box.y2) - target
    if dy <= 0.5:
        return False
    new_bottom = float(move_box.y) - dy
    if floor_y is not None and new_bottom < float(floor_y) + 0.5:
        return False
    _shift_paragraph_down(move, dy)
    return True


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
