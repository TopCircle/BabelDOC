"""Day 6 quiz options: a.a. / a.b. glue + multi-option split."""

from __future__ import annotations

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraphComposition
from babeldoc.format.pdf.document_il.il_version_1 import PdfSameStyleUnicodeCharacters
from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
from babeldoc.format.pdf.document_il.utils.list_marker_repair import (
    expand_glued_quiz_options_text,
    split_glued_quiz_options_on_page,
)


def _para(text: str) -> PdfParagraph:
    ssu = PdfSameStyleUnicodeCharacters(
        unicode=text,
        pdf_style=PdfStyle(font_id="base", font_size=11.0, graphic_state=None),
    )
    return PdfParagraph(
        box=Box(x=56, y=100, x2=360, y2=200),
        pdf_style=PdfStyle(font_id="base", font_size=11.0, graphic_state=None),
        pdf_paragraph_composition=[
            PdfParagraphComposition(pdf_same_style_unicode_characters=ssu)
        ],
        unicode=text,
    )


class TestExpandGluedQuizOptions:
    def test_double_a_from_article(self):
        # EN ``a. A chocolate…`` → MT ``a.a. 巧克力``
        assert expand_glued_quiz_options_text("a.a. 巧克力，满足嗜好") == "a. 巧克力，满足嗜好"

    def test_a_b_collapsed_to_b(self):
        # Collapsed option b body with a.b. glue
        assert expand_glued_quiz_options_text("a.b. 黑色上衣搭配牛仔裤") == "b. 黑色上衣搭配牛仔裤"

    def test_split_mid_options(self):
        t = expand_glued_quiz_options_text("b. 饼干； c. 酸糖")
        assert "\n" in t
        assert "b." in t and "c." in t


class TestSplitGluedQuizParagraphs:
    def test_splits_into_multiple_paras(self):
        p = _para("b. 饼干，盐； c. 酸糖，酸味。")
        out = split_glued_quiz_options_on_page([p])
        assert len(out) >= 2
        assert out[0].unicode.startswith("b.")
        assert any(x.unicode.lstrip().startswith("c.") for x in out)

    def test_double_a_single_para(self):
        p = _para("a.a. 花香。")
        out = split_glued_quiz_options_on_page([p])
        assert len(out) == 1
        assert out[0].unicode.startswith("a.")
        assert "a.a." not in out[0].unicode
