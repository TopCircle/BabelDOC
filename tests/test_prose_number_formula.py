"""Prose numbers must not become formula placeholders for DeepLX (ATU intro)."""

from __future__ import annotations

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter
from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
from babeldoc.format.pdf.document_il.il_version_1 import VisualBbox
from babeldoc.format.pdf.document_il.midend.styles_and_formulas import StylesAndFormulas


def _ch(u: str, *, x: float = 0.0) -> PdfCharacter:
    box = Box(x=x, y=0, x2=x + 6, y2=12)
    return PdfCharacter(
        char_unicode=u,
        box=box,
        visual_bbox=VisualBbox(box=Box(x=x, y=0, x2=x + 6, y2=12)),
        pdf_style=PdfStyle(font_id="base", font_size=12.0, graphic_state=None),
    )


class TestProseNumberRun:
    def test_fifty_shades(self):
        chars = [_ch(c, x=i * 6) for i, c in enumerate("50 Shades")]
        assert StylesAndFormulas._is_prose_number_run(chars, 0)
        assert StylesAndFormulas._is_prose_number_run(chars, 1)  # '0' still in run

    def test_percent_is_prose(self):
        """Figure dual abstract: 21% / 99.00% must not become formula placeholders."""
        chars = [_ch(c, x=i * 6) for i, c in enumerate("21%")]
        assert StylesAndFormulas._is_prose_number_run(chars, 0)

    def test_ninety_nine_point_zero_percent(self):
        """``99.00%`` — root cause of dual ``99.BS5Q%`` / trailing ``。00%``."""
        chars = [_ch(c, x=i * 6) for i, c in enumerate("99.00% which")]
        assert StylesAndFormulas._is_prose_number_run(chars, 0)
        assert StylesAndFormulas._is_prose_number_run(chars, 1)
        # decimal digits still in the percentage run
        assert StylesAndFormulas._is_prose_number_run(chars, 3)

    def test_trailing_digit_alone(self):
        chars = [_ch(c, x=i * 6) for i, c in enumerate("x=50")]
        # start at '5'
        assert not StylesAndFormulas._is_prose_number_run(chars, 2)

    def test_ordinal(self):
        chars = [_ch(c, x=i * 6) for i, c in enumerate("4th")]
        assert StylesAndFormulas._is_prose_number_run(chars, 0)

    def test_twenty_feet(self):
        """ATU p20: 20 feet / 25, longer — must not become {vN}."""
        chars = [_ch(c, x=i * 6) for i, c in enumerate("20 feet")]
        assert StylesAndFormulas._is_prose_number_run(chars, 0)
        assert StylesAndFormulas._is_prose_number_run(chars, 1)

    def test_twenty_five_comma_longer(self):
        chars = [_ch(c, x=i * 6) for i, c in enumerate("25, longer")]
        assert StylesAndFormulas._is_prose_number_run(chars, 0)
        assert StylesAndFormulas._is_prose_number_run(chars, 1)

    def test_is_translatable_pure_digits_even_with_layout_id(self):
        """DocLayout formula_layout_id must not keep pure 20/25 as formula."""
        from babeldoc.format.pdf.document_il.il_version_1 import PdfFormula

        chars = [_ch("2", x=0), _ch("0", x=6)]
        for c in chars:
            c.formula_layout_id = 1
        formula = PdfFormula(pdf_character=chars, y_offset=0.0)
        # Call unbound — no FontMapper needed for this check
        assert StylesAndFormulas.is_translatable_formula(None, formula)

    def test_is_translatable_percentage(self):
        from babeldoc.format.pdf.document_il.il_version_1 import PdfFormula

        for s in ("99.00%", "99.63%", "0.12%", "21%"):
            chars = [_ch(c, x=i * 6) for i, c in enumerate(s)]
            formula = PdfFormula(pdf_character=chars, y_offset=0.0)
            assert StylesAndFormulas.is_translatable_formula(None, formula), s

    def test_is_translatable_uncertainty(self):
        from babeldoc.format.pdf.document_il.il_version_1 import PdfFormula

        chars = [_ch(c, x=i * 6) for i, c in enumerate("0.12±0.03")]
        formula = PdfFormula(pdf_character=chars, y_offset=0.0)
        assert StylesAndFormulas.is_translatable_formula(None, formula)

    def test_coalesce_numeric_style_fragments(self):
        """TeX-split ``99``/``.``/``00``/``%which`` → one ``99.00%`` + Latin."""
        from types import SimpleNamespace

        from babeldoc.format.pdf.document_il.il_version_1 import Page
        from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
        from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraphComposition
        from babeldoc.format.pdf.document_il.il_version_1 import PdfSameStyleCharacters

        def style_comp(text: str, font_id: str) -> PdfParagraphComposition:
            chars = [_ch(c, x=i * 6) for i, c in enumerate(text)]
            for c in chars:
                c.pdf_style = PdfStyle(
                    font_id=font_id, font_size=9.0, graphic_state=None
                )
            return PdfParagraphComposition(
                pdf_same_style_characters=PdfSameStyleCharacters(
                    pdf_character=chars,
                    pdf_style=PdfStyle(
                        font_id=font_id, font_size=9.0, graphic_state=None
                    ),
                )
            )

        base = PdfStyle(font_id="base", font_size=9.0, graphic_state=None)
        para = PdfParagraph(
            box=Box(x=0, y=0, x2=400, y2=20),
            pdf_style=base,
            pdf_paragraph_composition=[
                style_comp("99", "F1"),
                style_comp(".", "F2"),
                style_comp("00", "F3"),
                style_comp("%which takes", "F4"),
            ],
            unicode="",
        )
        page = Page(pdf_paragraph=[para], page_number=0)
        # Minimal instance — only coalesce + create_same_style need to work
        saf = StylesAndFormulas.__new__(StylesAndFormulas)
        saf.translation_config = SimpleNamespace()
        saf.coalesce_prose_number_style_spans(page)
        comps = para.pdf_paragraph_composition
        assert len(comps) == 2
        t0 = "".join(
            c.char_unicode or ""
            for c in comps[0].pdf_same_style_characters.pdf_character
        )
        t1 = "".join(
            c.char_unicode or ""
            for c in comps[1].pdf_same_style_characters.pdf_character
        )
        assert t0 == "99.00%"
        # space inserted before Latin after %
        assert t1.lstrip().startswith("which")
        assert t1[0] == " " or t1.startswith("which")
