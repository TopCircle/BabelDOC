"""Latin presentation ligature expansion (ﬁ/ﬂ/ﬀ/ﬃ)."""

from __future__ import annotations

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter
from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
from babeldoc.format.pdf.document_il.il_version_1 import VisualBbox
from babeldoc.format.pdf.document_il.utils.layout_helper import get_char_unicode_string
from babeldoc.format.pdf.document_il.utils.text_recovery import expand_latin_ligatures
from babeldoc.format.pdf.document_il.utils.text_recovery import (
    rejoin_soft_hyphens_in_text,
)


def test_expand_common_ligatures():
    assert expand_latin_ligatures("ﬁnd") == "find"
    assert expand_latin_ligatures("diﬀerent") == "different"
    assert expand_latin_ligatures("eﬃcient") == "efficient"
    assert expand_latin_ligatures("ﬂow") == "flow"
    assert expand_latin_ligatures("aﬄuent") == "affluent"


def test_expand_idempotent_on_ascii():
    assert expand_latin_ligatures("different") == "different"
    assert expand_latin_ligatures("") == ""
    assert expand_latin_ligatures(None) == ""


def test_soft_hyphen_rejoin_expands_ligature_continuation():
    # di- + ﬃcult (ligature in continuation) → difficult
    out = rejoin_soft_hyphens_in_text("di- ﬃcult")
    assert "ﬃ" not in out
    assert out == "difficult"


def _ch(text: str, x: float) -> PdfCharacter:
    box = Box(x=x, y=100, x2=x + 8, y2=112)
    return PdfCharacter(
        pdf_character_id=None,
        char_unicode=text,
        box=box,
        visual_bbox=VisualBbox(box=box),
        pdf_style=PdfStyle(font_id="base", font_size=12.0, graphic_state=None),
        scale=1.0,
        advance=8.0,
        vertical=False,
        xobj_id=None,
    )


def test_get_char_unicode_string_expands_ligatures():
    chars = [_ch("di", 10), _ch("ﬀ", 20), _ch("erent", 30)]
    # Char-level paths: each unit may be multi-letter from extraction
    text = get_char_unicode_string(chars)
    assert "ﬀ" not in text
    assert "ff" in text or "different" in text.replace(" ", "")
