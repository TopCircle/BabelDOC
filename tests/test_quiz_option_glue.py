"""Day 6 quiz options: a.a. / a.b. glue + multi-option split."""

from __future__ import annotations

import pytest
from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter
from babeldoc.format.pdf.document_il.il_version_1 import PdfFormula
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraphComposition
from babeldoc.format.pdf.document_il.il_version_1 import PdfSameStyleUnicodeCharacters
from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
from babeldoc.format.pdf.document_il.utils.list_marker_repair import (
    expand_glued_quiz_options_text,
)
from babeldoc.format.pdf.document_il.utils.list_marker_repair import (
    normalize_embedded_numeric_markers_on_page,
)
from babeldoc.format.pdf.document_il.utils.list_marker_repair import (
    normalize_leading_bullets_on_paragraph,
)
from babeldoc.format.pdf.document_il.utils.list_marker_repair import (
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

    def test_split_options_get_stacked_boxes_not_same_y(self):
        """Day6 dual p3: a–d must not share one baseline after split."""
        p = _para(
            "a. 巧克力，满足嗜好； b. 脆饼干，盐瘾； c. 酸糖，酸味； d. 薯片，辣味。"
        )
        # Tall band like multi-option source (100pt → 4 parts ≈ 25pt pitch)
        p.box = Box(x=150, y=100, x2=500, y2=200)
        out = split_glued_quiz_options_on_page([p])
        assert len(out) >= 4
        y2s = [float(o.box.y2) for o in out if o.box and o.box.y2 is not None]
        # Each option lower on the page (smaller y2 in PDF coords)
        assert y2s == sorted(y2s, reverse=True)
        # Distinct baselines (not all equal)
        assert len({round(y, 1) for y in y2s}) == len(y2s)
        # Adjacent pitch ≈ constant and fits the source band
        pitches = [y2s[i] - y2s[i + 1] for i in range(len(y2s) - 1)]
        assert all(p > 10 for p in pitches)
        assert max(pitches) - min(pitches) < 0.5
        # Stacked band stays inside original [100, 200]
        bottoms = [float(o.box.y) for o in out if o.box and o.box.y is not None]
        assert min(bottoms) >= 100.0 - 0.1
        assert max(y2s) <= 200.0 + 0.1

    def test_pitch_uses_band_height_over_n_parts(self):
        """Even split of origin band, not a fixed oversized font pitch."""
        from babeldoc.format.pdf.document_il.utils.list_marker_repair import (
            _option_line_pitch,
        )

        p = _para("a. x； b. y； c. z； d. w")
        p.box = Box(x=100, y=0, x2=400, y2=80)  # band=80, n=4 → pitch=20
        pitch = _option_line_pitch(p, n_parts=4, origin_box=p.box)
        assert pitch == pytest.approx(20.0)

    def test_double_a_single_para(self):
        p = _para("a.a. 花香。")
        out = split_glued_quiz_options_on_page([p])
        assert len(out) == 1
        assert out[0].unicode.startswith("a.")
        assert "a.a." not in out[0].unicode


class TestLeadingSymbolBulletRepair:
    def _bullet_formula(self, x: float = 56.0) -> PdfParagraphComposition:
        style = PdfStyle(font_id="bullet", font_size=11.0, graphic_state=None)
        bullet = PdfCharacter(
            pdf_style=style,
            box=Box(x=x, y=120, x2=x + 6, y2=132),
            char_unicode="\uf643",
            advance=0.512,
        )
        space = PdfCharacter(
            pdf_style=style,
            box=Box(x=x + 6, y=120, x2=x + 12, y2=132),
            char_unicode=" ",
            advance=6.0,
        )
        return PdfParagraphComposition(
            pdf_formula=PdfFormula(
                box=Box(x=x, y=120, x2=x + 12, y2=132),
                pdf_character=[bullet, space],
                x_offset=0,
                y_offset=0,
            )
        )

    def test_private_use_bullet_moves_to_paragraph_start(self):
        p = _para("您的恋人上一次高潮\uf643是什么时候？")
        p.pdf_paragraph_composition = [
            PdfParagraphComposition(
                pdf_same_style_unicode_characters=PdfSameStyleUnicodeCharacters(
                    unicode="您的恋人上一次高潮",
                    pdf_style=p.pdf_style,
                )
            ),
            self._bullet_formula(),
            PdfParagraphComposition(
                pdf_same_style_unicode_characters=PdfSameStyleUnicodeCharacters(
                    unicode="是什么时候？",
                    pdf_style=p.pdf_style,
                )
            ),
        ]
        assert normalize_leading_bullets_on_paragraph(p)
        assert p.pdf_paragraph_composition[0].pdf_formula is not None
        assert p.unicode.startswith("\uf643")

    def test_inline_bullet_is_not_moved(self):
        p = _para("标签\uf643正文")
        p.pdf_paragraph_composition = [
            PdfParagraphComposition(
                pdf_same_style_unicode_characters=PdfSameStyleUnicodeCharacters(
                    unicode="标签",
                    pdf_style=p.pdf_style,
                )
            ),
            self._bullet_formula(x=120.0),
            PdfParagraphComposition(
                pdf_same_style_unicode_characters=PdfSameStyleUnicodeCharacters(
                    unicode="正文",
                    pdf_style=p.pdf_style,
                )
            ),
        ]
        assert not normalize_leading_bullets_on_paragraph(p)
        assert p.pdf_paragraph_composition[0].pdf_same_style_unicode_characters.unicode == "标签"


class TestEmbeddedNumericMarkerRepair:
    def test_moves_mid_marker_to_item_start(self):
        p = _para("让她保持高性唤起 3。慢慢来并寻求同意")
        assert normalize_embedded_numeric_markers_on_page([p]) == 1
        assert p.unicode.startswith("3.")
        assert "3。" not in p.unicode

    def test_carries_trailing_marker_to_next_item(self):
        first = _para("1. 基本动作说明 2.")
        second = _para("第一门动作是第二步 3。继续深入")
        third = _para("如果她准备好了再继续")
        normalize_embedded_numeric_markers_on_page([first, second, third])
        assert first.unicode.startswith("1.")
        assert not first.unicode.rstrip().endswith("2.")
        assert second.unicode.startswith("2.")
        assert "3。" not in second.unicode
        assert third.unicode.startswith("3.")
