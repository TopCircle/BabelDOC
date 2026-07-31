"""Drop-cap letter rejoined to word remainder for MT input."""

from __future__ import annotations

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter
from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
from babeldoc.format.pdf.document_il.il_version_1 import VisualBbox
from babeldoc.format.pdf.document_il.utils.drop_cap import (
    is_drop_cap_pair,
    rejoin_drop_cap_in_text,
)
from babeldoc.format.pdf.document_il.utils.layout_helper import get_char_unicode_string
from babeldoc.format.pdf.document_il.utils.text_recovery import recover_latin_word_fragments


def _ch(
    u: str,
    x: float,
    *,
    size: float = 12.0,
    w: float | None = None,
    y: float = 200.0,
    font_id: str = "Body",
) -> PdfCharacter:
    if w is None:
        w = size * 0.55
    box = Box(x=x, y=y, x2=x + w, y2=y + size)
    return PdfCharacter(
        char_unicode=u,
        box=box,
        visual_bbox=VisualBbox(box=box),
        pdf_style=PdfStyle(font_id=font_id, font_size=size, graphic_state=None),
        scale=1.0,
        advance=w,
    )


def test_rejoin_drop_cap_text_if_you():
    assert rejoin_drop_cap_in_text("I f you want") == "If you want"
    assert rejoin_drop_cap_in_text("W e are told") == "We are told"
    # Must not glue full words
    assert rejoin_drop_cap_in_text("A man with a plan") == "A man with a plan"
    assert rejoin_drop_cap_in_text("I love you") == "I love you"


def test_geometry_if_you_want():
    """OA-style: Trajan I @35 + Myriad 'f you want…' @12.5 → If you want…"""
    chars = [
        _ch("I", 102.0, size=35.4, w=18.0, font_id="Trajan"),
        _ch("f", 121.1, size=12.5, w=5.0, font_id="Myriad"),
        _ch(" ", 126.0, size=12.5, w=3.0),
        _ch("y", 129.0, size=12.5, w=6.0, font_id="Myriad"),
        _ch("o", 135.0, size=12.5, w=6.0, font_id="Myriad"),
        _ch("u", 141.0, size=12.5, w=6.0, font_id="Myriad"),
        _ch(" ", 147.0, size=12.5, w=3.0),
        _ch("w", 150.0, size=12.5, w=7.0, font_id="Myriad"),
        _ch("a", 157.0, size=12.5, w=6.0, font_id="Myriad"),
        _ch("n", 163.0, size=12.5, w=6.0, font_id="Myriad"),
        _ch("t", 169.0, size=12.5, w=5.0, font_id="Myriad"),
    ]
    assert is_drop_cap_pair(chars[0], chars[1])
    text = get_char_unicode_string(chars)
    assert text.startswith("If you want")
    assert "I f" not in text


def test_nbsp_drop_cap_i():
    """Source often has NBSP before I; layout_helper normalizes NBSP first."""
    assert rejoin_drop_cap_in_text("I f you") == "If you"
    assert rejoin_drop_cap_in_text("\u00a0I f you").replace("\u00a0", "") == "If you"
    # recover path
    assert recover_latin_word_fragments("I f you want some action") == (
        "If you want some action"
    )


def test_no_false_join_sentence_i():
    """Standalone pronoun I before a full word stays."""
    assert rejoin_drop_cap_in_text("I love maintaining") == "I love maintaining"
