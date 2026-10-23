"""Style marker recovery: bold + color when DeepLX drops 〖Bn〗 tags."""

from __future__ import annotations

from babeldoc.format.pdf.document_il.il_version_1 import GraphicState
from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
from babeldoc.format.pdf.document_il.utils.style_marker_recover import StyleSpan
from babeldoc.format.pdf.document_il.utils.style_marker_recover import (
    rewrap_styles_from_source,
)
from babeldoc.format.pdf.document_il.utils.style_marker_recover import style_by_id


def _style(font_id: str, color_ops: str | None = None) -> PdfStyle:
    gs = GraphicState(passthrough_per_char_instruction=color_ops)
    return PdfStyle(font_id=font_id, font_size=11.8, graphic_state=gs)


def _spans(*pairs: tuple[int, str]) -> list[StyleSpan]:
    bold = _style("MyriadPro-Bold", "0.45 0.05 0.25 rg")
    return [StyleSpan(i, bold, src) for i, src in pairs]


def test_rewrap_case_insensitive_sequential_serial():
    """Day6 p8 mono: sequenTiaL / seriaL after marker loss."""
    output = (
        "有两种类型的多重高潮 sequenTiaL-- 一连串过山车般的波浪，"
        "间隔 2 到 10 分钟；seriaL-- 快感的快速射击"
    )
    recovered = rewrap_styles_from_source(
        output,
        _spans((0, "sequential"), (1, "serial")),
    )
    assert recovered is not None
    assert "〖B0〗sequenTiaL〖/B0〗" in recovered
    assert "〖B1〗seriaL〖/B1〗" in recovered


def test_rewrap_skips_present_ids_fills_missing():
    """Partial marker survival: keep B0, recover B1 only."""
    output = "因〖B0〗阴道痉挛〖/B0〗（紧缩）and serial later"
    recovered = rewrap_styles_from_source(
        output,
        _spans((0, "vaginismus"), (1, "serial")),
    )
    assert recovered is not None
    assert "〖B0〗阴道痉挛〖/B0〗" in recovered
    assert "〖B1〗serial〖/B1〗" in recovered
    assert recovered.count("〖B0〗") == 1


def test_rewrap_noop_when_all_present():
    output = "因〖B0〗阴道痉挛〖/B0〗（紧缩）"
    assert (
        rewrap_styles_from_source(output, _spans((0, "vaginismus"))) is None
    )


def test_style_by_id():
    spans = _spans((0, "sequential"), (1, "serial"))
    m = style_by_id(spans)
    assert m[0].font_id == "MyriadPro-Bold"
    assert "0.45" in (m[0].graphic_state.passthrough_per_char_instruction or "")


def test_rewrap_fullwidth_colon_keeps_the_english_name():
    """DeepLX turns "Vulva:" into "Vulva：" and drops the markers."""
    recovered = rewrap_styles_from_source(
        "{v1}Vulva：从阴毛线到会阴的区域。",
        _spans((0, "Vulva:")),
    )
    assert recovered is not None
    assert "〖B0〗Vulva：〖/B0〗" in recovered
    assert recovered.count("〖B0〗") == 1


def test_rewrap_translated_label_stops_at_the_colon():
    """The English name is gone. The opening label before ： stays one span."""
    recovered = rewrap_styles_from_source(
        "肛门：肛门周围有许多神经末梢。",
        _spans((0, "Anus:")),
    )
    assert recovered is not None
    assert recovered.startswith("〖B0〗肛门：〖/B0〗")
    assert "神经" not in recovered.split("〖/B0〗", 1)[0]


def test_rewrap_does_not_invent_a_label_when_the_colon_is_gone():
    """No colon, no name boundary. Do not bold the whole sentence."""
    assert (
        rewrap_styles_from_source(
            "阴唇阴道的肉质外阴唇。用手指按摩。",
            _spans((0, "Outer labia:")),
        )
        is None
    )


def test_rewrap_does_not_bold_a_colon_later_in_the_sentence():
    assert (
        rewrap_styles_from_source(
            "请先阅读说明。注意：后面还有",
            _spans((0, "Warning:")),
        )
        is None
    )


def test_formula_bullet_keeps_the_bold_lead_in():
    """Placeholder split must not paint the name in the body face."""
    import re

    from babeldoc.format.pdf.document_il.il_version_1 import Box
    from babeldoc.format.pdf.document_il.il_version_1 import PdfFormula
    from babeldoc.format.pdf.document_il.midend.il_translator import FormulaPlaceholder
    from babeldoc.format.pdf.document_il.midend.il_translator import ILTranslator

    ilt = object.__new__(ILTranslator)
    ilt._formula_placeholder_pattern = re.compile(r"\{v\d+\}")
    ilt._style_left_placeholder_pattern = re.compile(r"(?!)")
    ilt._style_right_placeholder_pattern = re.compile(r"(?!)")
    bold = _style("Ubuntu-Bold")
    body = _style("Ubuntu-Light")
    formula = PdfFormula(box=Box(x=0, y=0, x2=8, y2=10))
    tin = ILTranslator.TranslateInput(
        "{v1}〖B0〗Anus:〖/B0〗 The area.",
        [FormulaPlaceholder(1, formula, "{v1}", r"\{\s*v\s*1\s*\}")],
        body,
    )
    tin.style_spans = [StyleSpan(0, bold, "Anus:")]
    comps = ilt.parse_translate_output(tin, "{v1}肛门：肛门周围。")
    assert comps[0].pdf_formula is formula
    styled = [
        comp.pdf_same_style_unicode_characters
        for comp in comps
        if comp.pdf_same_style_unicode_characters
    ]
    assert styled[0].pdf_style.font_id == "Ubuntu-Bold"
    assert styled[0].unicode == "肛门："
    assert styled[1].pdf_style.font_id == "Ubuntu-Light"
    assert "〖" not in styled[1].unicode


def test_serial_not_eaten_by_sequential():
    output = "sequential and serial orgasms"
    recovered = rewrap_styles_from_source(
        output,
        _spans((0, "sequential"), (1, "serial")),
    )
    assert recovered is not None
    assert recovered.count("〖B0〗") == 1
    assert recovered.count("〖B1〗") == 1


def test_coalesce_emphasis_merges_line_broken_italic():
    """Adjacent same-style runs become one char list (book title split)."""
    from babeldoc.format.pdf.document_il.il_version_1 import Box
    from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter
    from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraphComposition
    from babeldoc.format.pdf.document_il.il_version_1 import PdfSameStyleCharacters
    from babeldoc.format.pdf.document_il.il_version_1 import VisualBbox
    from babeldoc.format.pdf.document_il.utils.style_marker_recover import (
        coalesce_emphasis_style_run,
    )

    def _ch(u: str, x: float = 0.0) -> PdfCharacter:
        b = Box(x=x, y=0, x2=x + 5, y2=10)
        return PdfCharacter(
            char_unicode=u,
            box=b,
            visual_bbox=VisualBbox(box=b),
            pdf_style=_style("MyriadPro-LightIt"),
        )

    italic = _style("MyriadPro-LightIt")
    body = _style("MyriadPro-Light")

    def _run(text: str) -> PdfParagraphComposition:
        chars = [_ch(c, i * 5) for i, c in enumerate(text)]
        return PdfParagraphComposition(
            pdf_same_style_characters=PdfSameStyleCharacters(
                pdf_style=italic,
                pdf_character=chars,
            )
        )

    comps = [_run("The "), _run("Passion Prescription"), _run(" end")]
    # third is same italic in this fixture — force body by different style
    comps[2] = PdfParagraphComposition(
        pdf_same_style_characters=PdfSameStyleCharacters(
            pdf_style=body,
            pdf_character=[_ch(".")],
        )
    )
    chars, style, nxt = coalesce_emphasis_style_run(comps, 0, body)
    assert "".join(c.char_unicode for c in chars) == "The Passion Prescription"
    assert style.font_id == "MyriadPro-LightIt"
    assert nxt == 2


def test_rewrap_recognizes_lowercase_b_pairs():
    """〖b0〗 pairs must count as present so we do not double-wrap."""
    output = "因〖b0〗阴道痉挛〖/b0〗（紧缩）"
    assert rewrap_styles_from_source(output, _spans((0, "vaginismus"))) is None


def test_rewrap_handles_quoted_terms_with_trailing_punct():
    """“Ladyscape.” in EN becomes "Ladyscape"。 in ZH (period outside quote)."""
    output = '• "Ladyscape"。尽管修剪或脱毛全部或部分阴部对许多女性来说很常见'
    recovered = rewrap_styles_from_source(
        output,
        _spans((0, "“Ladyscape.”")),
    )
    assert recovered is not None
    assert '〖B0〗"Ladyscape"〖/B0〗。' in recovered or '〖B0〗"Ladyscape"。〖/B0〗' in recovered

    # Also handle when closing quote was in a separate span so source_text is “Ladyscape.
    recovered_split = rewrap_styles_from_source(
        output,
        _spans((0, "“Ladyscape.")),
    )
    assert recovered_split is not None
    assert '〖B0〗"Ladyscape"〖/B0〗。' in recovered_split or '〖B0〗"Ladyscape"。〖/B0〗' in recovered_split
