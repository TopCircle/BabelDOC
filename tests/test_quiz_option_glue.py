"""Day 6 quiz options: a.a. / a.b. glue + multi-option split."""

from __future__ import annotations

import pytest

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
        assert len(set(round(y, 1) for y in y2s)) == len(y2s)
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
