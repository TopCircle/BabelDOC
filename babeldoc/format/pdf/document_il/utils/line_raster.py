"""Skip a short image that replays a line already translated into the body.

Photos are taller than one text line. A header badge is this height, but
it only sits on a title, which is not a planned body paragraph. The check
uses the glyph ink, one body line past it, and a few points to the side.
A shaped pocket also hides the English that continues past that ink.
A straight column does not, so a badge beside the column stays.
A narrow second paint of a line end is hidden on any Chinese line,
including one the plan left as preserve. A wider badge stays.
"""

from __future__ import annotations

from babeldoc.format.pdf.document_il.utils.layout_plan.consume import (
    consume_layout_plan,
)

# One English line painted as an image. A photo tile is taller than this.
_MIN_HEIGHT = 6.0
_MAX_HEIGHT = 18.0
# A single letter stem is only a few points wide.
_MIN_WIDTH = 2.0
# The second paint of a line end: "n", "m", or a short "asm,".
_LETTER_WIDTH = 24.0
# It starts at the glyph edge. A badge sits further out.
_LETTER_HANG = 16.0
# One body line below the ink, and a few points past the glyph edge.
_Y_SLACK = 18.0
_X_SLACK = 4.0
_PLANNED_BODY = frozenset({"rect_flow", "shaped_pocket"})


def hides_translated_line(form, page) -> bool:
    """True when this form is a line image over translated body text."""
    if getattr(form, "form_type", None) != "image":
        return False
    box = _box_of(form)
    if box is None:
        return False
    x0, y0, x1, y1 = box
    height = y1 - y0
    width = x1 - x0
    if not (_MIN_HEIGHT < height <= _MAX_HEIGHT and width >= _MIN_WIDTH):
        return False
    # A preserved body line still has this second paint. A title badge is
    # wider than one line end, and a column badge starts further aside.
    if width <= _LETTER_WIDTH and _hangs_on_cjk(x0, y0, x1, y1, page):
        return True
    for paragraph in getattr(page, "pdf_paragraph", None) or []:
        strategy = _body_strategy(page, paragraph)
        if strategy is None:
            continue
        if _hits(x0, y0, x1, y1, paragraph, strategy):
            return True
    return False


def _box_of(form) -> tuple[float, float, float, float] | None:
    box = getattr(form, "box", None)
    if box is None or None in (box.x, box.y, box.x2, box.y2):
        return None
    x0, x1 = float(box.x), float(box.x2)
    y0, y1 = float(box.y), float(box.y2)
    if x1 < x0:
        x0, x1 = x1, x0
    if y1 < y0:
        y0, y1 = y1, y0
    return x0, y0, x1, y1


def _body_strategy(page, paragraph) -> str | None:
    plan = getattr(page, "layout_plan", None)
    region_id = getattr(paragraph, "layout_region_id", None)
    if plan is None or not region_id:
        return None
    seen = consume_layout_plan(plan, region_id)
    if seen.base_strategy not in _PLANNED_BODY:
        return None
    if not _contains_cjk(paragraph):
        return None
    return seen.base_strategy


def _contains_cjk(paragraph) -> bool:
    if _has_cjk(getattr(paragraph, "unicode", None) or ""):
        return True
    for composition in getattr(paragraph, "pdf_paragraph_composition", None) or []:
        for char in _glyphs(composition):
            if _has_cjk(getattr(char, "char_unicode", None) or ""):
                return True
    return False


def _has_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def _glyphs(composition) -> list:
    line = getattr(composition, "pdf_line", None)
    if line is not None and getattr(line, "pdf_character", None):
        return list(line.pdf_character)
    character = getattr(composition, "pdf_character", None)
    if character is not None:
        return [character]
    same = getattr(composition, "pdf_same_style_characters", None)
    if same is not None and getattr(same, "pdf_character", None):
        return list(same.pdf_character)
    formula = getattr(composition, "pdf_formula", None)
    if formula is not None and getattr(formula, "pdf_character", None):
        return list(formula.pdf_character)
    return []


def _hangs_on_cjk(x0: float, y0: float, _x1: float, y1: float, page) -> bool:
    """True when a narrow image continues a Chinese line past its last glyph."""
    from babeldoc.format.pdf.document_il.utils.shaped_pocket_stack import _ink_extent

    for paragraph in getattr(page, "pdf_paragraph", None) or []:
        if not _contains_cjk(paragraph):
            continue
        ink = _ink_extent(paragraph)
        if ink is None:
            continue
        _left, top, right, bottom = ink
        if y1 < bottom - _Y_SLACK or y0 > top + _Y_SLACK:
            continue
        if right - _X_SLACK <= x0 <= right + _LETTER_HANG:
            return True
    return False


def _hits(
    x0: float, y0: float, x1: float, y1: float, paragraph, strategy: str
) -> bool:
    from babeldoc.format.pdf.document_il.utils.shaped_pocket_stack import _ink_extent

    ink = _ink_extent(paragraph)
    if ink is None:
        return False
    left, top, right, bottom = ink
    if y1 < bottom - _Y_SLACK or y0 > top + _Y_SLACK:
        return False
    if not (x1 < left - _X_SLACK or x0 > right + _X_SLACK):
        return True
    # The English line keeps going into the figure. A straight column has
    # no such tail, and a badge beside it must stay.
    if strategy != "shaped_pocket":
        return False
    return x0 >= right - _X_SLACK
