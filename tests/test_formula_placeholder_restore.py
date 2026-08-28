"""OA p5: {v1}/{v2} must become formula compositions, not empty （,）."""

from __future__ import annotations

from unittest.mock import MagicMock

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter
from babeldoc.format.pdf.document_il.il_version_1 import PdfFormula
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
from babeldoc.format.pdf.document_il.il_version_1 import VisualBbox
from babeldoc.format.pdf.document_il.midend.il_translator import FormulaPlaceholder
from babeldoc.format.pdf.document_il.midend.il_translator import ILTranslator
from babeldoc.format.pdf.document_il.midend.il_translator import ParagraphTranslateTracker
from babeldoc.format.pdf.translation_config import TranslationConfig
from babeldoc.translator.fixed_map_translator import FixedMapTranslator


def _ch(u: str) -> PdfCharacter:
    box = Box(x=0, y=0, x2=6, y2=10)
    return PdfCharacter(
        char_unicode=u,
        box=box,
        visual_bbox=VisualBbox(box=box),
        pdf_style=PdfStyle(font_id="base", font_size=10.0, graphic_state=None),
    )


def _formula(text: str) -> PdfFormula:
    f = PdfFormula(box=Box(x=0, y=0, x2=40, y2=10))
    f.pdf_character = [_ch(c) for c in text]
    return f


def test_post_translate_keeps_p5_combo_formulas():
    cfg = TranslationConfig(
        translator=FixedMapTranslator(),
        input_file="t.pdf",
        lang_in="en",
        lang_out="zh-CN",
        doc_layout_model=MagicMock(),
        auto_extract_glossary=False,
    )
    ilt = ILTranslator(FixedMapTranslator(), cfg)
    style = PdfStyle(font_id="base", font_size=12.0, graphic_state=None)
    f1 = _formula("3+2+2=7")
    f2 = _formula("3x2x2 = 12")
    placeholders = [
        FormulaPlaceholder(1, f1, "{v1}", r"\{\s*v\s*1\s*\}"),
        FormulaPlaceholder(2, f2, "{v2}", r"\{\s*v\s*2\s*\}"),
    ]
    tin = ILTranslator.TranslateInput(
        "12 trigasmic combination ({v1},{v2})",
        placeholders,
        style,
    )
    para = PdfParagraph(
        box=Box(x=0, y=0, x2=200, y2=20),
        pdf_style=style,
        pdf_paragraph_composition=[],
        unicode=tin.unicode,
    )
    tracker = ParagraphTranslateTracker()
    ilt.post_translate_paragraph(
        para,
        tracker,
        tin,
        "12 个三重高潮组合（{v1},{v2}）",
    )
    formulas = [
        "".join(c.char_unicode for c in comp.pdf_formula.pdf_character)
        for comp in para.pdf_paragraph_composition
        if comp.pdf_formula
    ]
    assert "3+2+2=7" in formulas
    assert "3x2x2 = 12" in formulas
    assert "{v1}" not in (para.unicode or "")
    assert "3+2+2=7" in (para.unicode or "")
    assert "（," not in (para.unicode or "") and "(," not in (para.unicode or "")
