"""C0/C1 controls are removed from the string passed to TranslateInput."""

from __future__ import annotations

from unittest.mock import MagicMock

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter
from babeldoc.format.pdf.document_il.il_version_1 import PdfLine
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraphComposition
from babeldoc.format.pdf.document_il.il_version_1 import PdfSameStyleCharacters
from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
from babeldoc.format.pdf.document_il.il_version_1 import VisualBbox
from babeldoc.format.pdf.document_il.midend.il_translator import ILTranslator
from babeldoc.format.pdf.translation_config import TranslationConfig
from babeldoc.translator.fixed_map_translator import FixedMapTranslator


def _style(font_id: str = "Body", size: float = 12.0) -> PdfStyle:
    return PdfStyle(font_id=font_id, font_size=size, graphic_state=None)


def _chars(
    text: str,
    x0: float,
    y: float,
    font_id: str = "Body",
) -> list[PdfCharacter]:
    chars: list[PdfCharacter] = []
    x = x0
    for ch in text:
        box = Box(x=x, y=y, x2=x + 6.0, y2=y + 12.0)
        chars.append(
            PdfCharacter(
                char_unicode=ch,
                box=box,
                visual_bbox=VisualBbox(box=box),
                pdf_style=_style(font_id),
                advance=6.0,
            )
        )
        x += 6.0
    return chars


def _line(
    text: str,
    y: float,
    x0: float = 50.0,
    font_id: str = "Body",
) -> PdfParagraphComposition:
    chars = _chars(text, x0, y, font_id)
    x2 = chars[-1].box.x2 if chars else x0
    return PdfParagraphComposition(
        pdf_line=PdfLine(
            box=Box(x=x0, y=y, x2=x2, y2=y + 12.0),
            pdf_character=chars,
        )
    )


def _emphasis(
    text: str,
    y: float,
    x0: float,
    font_id: str = "BoldFace",
) -> PdfParagraphComposition:
    chars = _chars(text, x0, y, font_id)
    x2 = chars[-1].box.x2 if chars else x0
    return PdfParagraphComposition(
        pdf_same_style_characters=PdfSameStyleCharacters(
            box=Box(x=x0, y=y, x2=x2, y2=y + 12.0),
            pdf_style=_style(font_id),
            pdf_character=chars,
        )
    )


def _paragraph(compositions: list[PdfParagraphComposition]) -> PdfParagraph:
    return PdfParagraph(
        box=Box(x=50, y=80, x2=400, y2=140),
        pdf_style=_style(),
        pdf_paragraph_composition=compositions,
        unicode="body",
        layout_label="text",
        debug_id="controls",
    )


def _translator() -> ILTranslator:
    cfg = TranslationConfig(
        translator=FixedMapTranslator(),
        input_file="controls.pdf",
        lang_in="en",
        lang_out="zh-CN",
        doc_layout_model=MagicMock(),
        auto_extract_glossary=False,
    )
    return ILTranslator(cfg.translator, cfg)


def test_single_line_strips_leading_soh():
    """One PdfLine starting with U+0001: control is gone, English remains."""
    sentence = "The sensation starts here."
    para = _paragraph([_line("\x01" + sentence, y=100)])
    got = _translator().get_translate_input(para)
    assert got is not None
    assert "\x01" not in got.unicode
    assert sentence in got.unicode


def test_two_lines_strip_c1_keep_newline_and_tab():
    """Two PdfLines contain U+0081, a newline, and a tab.

    U+0081 is removed. Newline and tab are not C1 deletes: the glyph
    assembler folds them to the space between the lines, and that gap stays.
    """
    para = _paragraph(
        [
            _line("Keep\x81 this\n", y=120),
            _line("\tline intact", y=100),
        ]
    )
    got = _translator().get_translate_input(para)
    assert got is not None
    assert "\x81" not in got.unicode
    # get_char_unicode_string maps \n and \t to U+0020 before the strip.
    # The keep-list must not turn that gap into a hole or drop the second line.
    assert got.unicode == "Keep this line intact"


def test_style_marker_b0_preserved():
    """〖B0〗 embedded for a non-LLM emphasis span survives the strip."""
    para = _paragraph(
        [
            _line("See ", y=100),
            _emphasis("Bo\x01ld", y=100, x0=50.0 + 4 * 6.0),
        ]
    )
    got = _translator().get_translate_input(
        para,
        disable_rich_text_translate=True,
    )
    assert got is not None
    assert "〖B0〗" in got.unicode
    assert "〖/B0〗" in got.unicode
    assert "\x01" not in got.unicode
    assert "Bold" in got.unicode
