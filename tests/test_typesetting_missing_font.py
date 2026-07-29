"""Missing style font_id (e.g. F33) must not abort Typesetting with KeyError."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import PdfFont
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraphComposition
from babeldoc.format.pdf.document_il.il_version_1 import PdfSameStyleUnicodeCharacters
from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
from babeldoc.format.pdf.document_il.midend.typesetting import Typesetting


def _typesetter() -> Typesetting:
    cfg = MagicMock()
    cfg.lang_out = "zh-CN"
    cfg.primary_font_family = None
    # FontMapper is heavy; stub map to return a dummy mupdf-like font object
    ts = object.__new__(Typesetting)
    ts.translation_config = cfg
    ts.is_cjk = False  # skip CJK word merge path
    ts.font_mapper = MagicMock()
    dummy = MagicMock()
    dummy.char_lengths = MagicMock(return_value=(10.0,))
    # TypesettingUnit.width may call into the mapped font
    dummy.has_glyph = MagicMock(return_value=True)
    ts.font_mapper.map = MagicMock(return_value=dummy)
    return ts


def test_create_typesetting_units_missing_font_id_falls_back():
    """Style references F33 which is not in page fonts → no KeyError."""
    ts = _typesetter()
    known = PdfFont(
        name="Helvetica",
        font_id="F1",
        xref_id=1,
        encoding_length=1,
        bold=False,
        italic=False,
        monospace=False,
        serif=True,
    )
    fonts = {"F1": known}

    style = PdfStyle(font_id="F33", font_size=12.0, graphic_state=None)
    comp = PdfParagraphComposition(
        pdf_same_style_unicode_characters=PdfSameStyleUnicodeCharacters(
            unicode="你好",
            pdf_style=style,
        )
    )
    para = PdfParagraph(
        box=Box(x=0, y=0, x2=100, y2=20),
        pdf_style=style,
        pdf_paragraph_composition=[comp],
        unicode="你好",
        xobj_id=0,
    )

    units = ts.create_typesetting_units(para, fonts)
    assert len(units) == 2  # two CJK chars
    # FontMapper.map received the fallback PdfFont (F1), not KeyError
    assert ts.font_mapper.map.called
    original_font = ts.font_mapper.map.call_args[0][0]
    assert original_font.font_id == "F1"


def test_create_typesetting_units_missing_xobj_font_falls_back_to_page():
    ts = _typesetter()
    known = PdfFont(
        name="Helvetica",
        font_id="F1",
        xref_id=1,
        encoding_length=1,
        bold=False,
        italic=False,
        monospace=False,
        serif=True,
    )
    # xobj 7 has its own map without F33; page has F1
    fonts = {
        "F1": known,
        7: {"F2": known},
    }
    style = PdfStyle(font_id="F33", font_size=11.0, graphic_state=None)
    comp = PdfParagraphComposition(
        pdf_same_style_unicode_characters=PdfSameStyleUnicodeCharacters(
            unicode="Hi",
            pdf_style=style,
        )
    )
    para = PdfParagraph(
        box=Box(x=0, y=0, x2=100, y2=20),
        pdf_style=style,
        pdf_paragraph_composition=[comp],
        unicode="Hi",
        xobj_id=7,
    )
    units = ts.create_typesetting_units(para, fonts)
    assert len(units) == 2
    original_font = ts.font_mapper.map.call_args[0][0]
    assert original_font.font_id == "F1"


def test_create_typesetting_units_no_page_fonts_uses_synthetic():
    ts = _typesetter()
    fonts = {}  # empty
    style = PdfStyle(font_id="F33", font_size=12.0, graphic_state=None)
    comp = PdfParagraphComposition(
        pdf_same_style_unicode_characters=PdfSameStyleUnicodeCharacters(
            unicode="A",
            pdf_style=style,
        )
    )
    para = PdfParagraph(
        box=Box(x=0, y=0, x2=50, y2=20),
        pdf_style=style,
        pdf_paragraph_composition=[comp],
        unicode="A",
        xobj_id=0,
    )
    units = ts.create_typesetting_units(para, fonts)
    assert len(units) == 1
    original_font = ts.font_mapper.map.call_args[0][0]
    assert original_font.font_id == "F33"
    assert original_font.name == "F33"
