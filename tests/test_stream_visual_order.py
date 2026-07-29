"""Reverse-paint decorative titles → visual LTR reorder."""

from __future__ import annotations

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter
from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
from babeldoc.format.pdf.document_il.il_version_1 import VisualBbox
from babeldoc.format.pdf.document_il.utils.layout_helper import (
    get_char_unicode_string,
)
from babeldoc.format.pdf.document_il.utils.layout_helper import (
    is_stream_visually_reversed,
)
from babeldoc.format.pdf.document_il.utils.layout_helper import (
    sort_chars_visual_order,
)


def _ch(text: str, x: float, y: float = 100.0, w: float = 8.0) -> PdfCharacter:
    box = Box(x=x, y=y, x2=x + w, y2=y + 12)
    return PdfCharacter(
        pdf_character_id=None,
        char_unicode=text,
        box=box,
        visual_bbox=VisualBbox(box=box),
        pdf_style=PdfStyle(font_id="base", font_size=12.0, graphic_state=None),
        scale=1.0,
        advance=w,
        vertical=False,
        xobj_id=None,
    )


def test_who_has_orgasms_reverse_stream_detected():
    # Paint order right-to-left: ? S M S a g r o   S a h o h W
    # Visual LTR: W h o   h a S   o r g a S M S ?
    letters = list("Who haS orgaSMS?")
    xs = list(range(100, 100 + 10 * len(letters), 10))
    # reverse paint
    stream = [_ch(ch, x) for ch, x in zip(reversed(letters), reversed(xs))]
    assert is_stream_visually_reversed(stream) is True
    ordered = sort_chars_visual_order(stream)
    text = get_char_unicode_string(ordered)
    assert text.replace(" ", "").lower().startswith("who")
    assert "orgasms" in text.replace(" ", "").lower() or "orgasms" in "".join(
        c.char_unicode for c in ordered
    ).lower().replace(" ", "")


def test_ltr_body_not_reversed():
    word = "There is a myth"
    chars = [_ch(ch, 100 + i * 7) for i, ch in enumerate(word)]
    assert is_stream_visually_reversed(chars) is False
    assert [c.char_unicode for c in sort_chars_visual_order(chars)] == list(word)


def test_sort_is_idempotent_on_ltr():
    word = "prepare for the best"
    chars = [_ch(ch, 50 + i * 6) for i, ch in enumerate(word)]
    once = sort_chars_visual_order(chars)
    twice = sort_chars_visual_order(once)
    assert [c.char_unicode for c in once] == [c.char_unicode for c in twice]
