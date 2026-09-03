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
