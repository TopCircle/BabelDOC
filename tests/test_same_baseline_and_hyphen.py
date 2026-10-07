"""Same-baseline double paints, TOC color splits, cross-paragraph hyphens."""

from __future__ import annotations

from unittest.mock import MagicMock

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import GraphicState
from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter
from babeldoc.format.pdf.document_il.il_version_1 import PdfLine
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraphComposition
from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
from babeldoc.format.pdf.document_il.il_version_1 import VisualBbox
from babeldoc.format.pdf.document_il.midend.paragraph_finder import ParagraphFinder
from babeldoc.format.pdf.document_il.utils.hyphen_paragraph_merge import (
    merge_hyphen_wrapped_paragraphs,
)
from babeldoc.format.pdf.document_il.utils.paragraph_split_policy import (
    line_starts_with_list_marker,
)
from babeldoc.format.pdf.document_il.utils.same_baseline import same_baseline_overlap
from babeldoc.format.pdf.document_il.utils.same_baseline import (
    separate_same_baseline_overlap,
)
from babeldoc.format.pdf.document_il.utils.style_base import calculate_base_style
from babeldoc.format.pdf.translation_config import TranslationConfig
from babeldoc.translator.fixed_map_translator import FixedMapTranslator


def _char(
    ch: str,
    x: float,
    y: float,
    *,
    font_id: str = "F",
    size: float = 12.0,
    fill: str | None = None,
) -> PdfCharacter:
    box = Box(x=x, y=y, x2=x + 8, y2=y + 14)
    graphic = (
        GraphicState(passthrough_per_char_instruction=fill) if fill else None
    )
    return PdfCharacter(
        char_unicode=ch,
        box=box,
        visual_bbox=VisualBbox(box=Box(x=box.x, y=box.y, x2=box.x2, y2=box.y2)),
        pdf_style=PdfStyle(font_id=font_id, font_size=size, graphic_state=graphic),
        scale=1.0,
        advance=8,
        vertical=False,
        xobj_id=0,
    )


def _line(
    text: str,
    *,
    x: float,
    y: float,
    font_id: str = "F",
    fill: str | None = None,
) -> PdfParagraphComposition:
    chars = []
    cx = x
    for ch in text:
        chars.append(_char(ch, cx, y, font_id=font_id, fill=fill))
        cx += 8
    return PdfParagraphComposition(
        pdf_line=PdfLine(
            box=Box(x=x, y=y, x2=cx, y2=y + 14),
            pdf_character=chars,
        )
    )


def _para_from_line(
    comp: PdfParagraphComposition,
    *,
    render_order: int = 0,
    xobj_id: int = 0,
) -> PdfParagraph:
    line = comp.pdf_line
    return PdfParagraph(
        box=Box(x=line.box.x, y=line.box.y, x2=line.box.x2, y2=line.box.y2),
        pdf_paragraph_composition=[comp],
        unicode="",
        render_order=render_order,
        xobj_id=xobj_id,
        layout_label="plain text",
    )


def _plain(paragraph: PdfParagraph) -> str:
    return "".join(
        c.char_unicode or ""
        for comp in paragraph.pdf_paragraph_composition or []
        if comp.pdf_line
        for c in comp.pdf_line.pdf_character
    )


def test_same_baseline_shifts_later_paragraph_down():
    keep = _para_from_line(_line("第一句在上", x=100, y=157.2), render_order=1)
    move = _para_from_line(_line("第二句叠上", x=100, y=157.2), render_order=2)
    assert same_baseline_overlap(keep.box, move.box)
    assert separate_same_baseline_overlap(move, keep.box, move.box, floor_y=0)
    assert move.box.y2 <= keep.box.y - 1.0
    moved = move.pdf_paragraph_composition[0].pdf_line.pdf_character[0]
    assert moved.box.y2 <= 157.2
    assert moved.visual_bbox.box.y2 <= 157.2
    assert keep.box.y2 > 157.2


def test_slightly_inset_same_line_still_separates():
    """Strict containment used to skip equal-baseline paints."""
    keep = _para_from_line(_line("第一句保持", x=80, y=157.2), render_order=1)
    keep.box = Box(x=80, y=157.2, x2=280, y2=174.4)
    move = _para_from_line(_line("第二", x=100, y=158.0), render_order=2)
    move.box = Box(x=100, y=158.0, x2=160, y2=170.0)
    assert same_baseline_overlap(keep.box, move.box)
    assert separate_same_baseline_overlap(move, keep.box, move.box, floor_y=0)
    assert move.box.y2 < keep.box.y


def test_tall_body_is_not_a_same_baseline_pair():
    short = Box(x=100, y=200, x2=180, y2=214)
    tall = Box(x=90, y=100, x2=400, y2=320)
    assert same_baseline_overlap(short, tall) is False


def test_shift_refuses_to_leave_the_page():
    keep = _para_from_line(_line("甲", x=100, y=2), render_order=1)
    move = _para_from_line(_line("乙", x=100, y=2), render_order=2)
    assert (
        separate_same_baseline_overlap(move, keep.box, move.box, floor_y=0) is False
    )
    assert move.box.y == 2


def test_cross_paragraph_hyphen_joins_stimula():
    upper = _para_from_line(
        _line("other stimula-", x=72, y=200),
    )
    lower = _para_from_line(
        _line("tion feels better", x=72, y=182),
    )
    paras = [lower, upper]
    assert merge_hyphen_wrapped_paragraphs(paras) == 1
    assert len(paras) == 1
    text = _plain(paras[0])
    assert "stimula-" in text
    assert "tion feels better" in text


def test_intervening_paragraph_blocks_hyphen_join():
    upper = _para_from_line(_line("other stimula-", x=72, y=200))
    middle = _para_from_line(_line("See note.", x=72, y=184))
    lower = _para_from_line(_line("tion feels better", x=72, y=168))
    paras = [upper, middle, lower]
    assert merge_hyphen_wrapped_paragraphs(paras) == 0
    assert len(paras) == 3


def test_intentional_dash_and_far_tail_stay_split():
    dash = _para_from_line(_line("Trigasm-", x=72, y=200))
    word = _para_from_line(_line("actually more", x=72, y=182))
    assert merge_hyphen_wrapped_paragraphs([dash, word]) == 0

    stem = _para_from_line(_line("the g-", x=72, y=200))
    tail = _para_from_line(_line("spot area", x=72, y=182))
    assert merge_hyphen_wrapped_paragraphs([stem, tail]) == 0

    near = _para_from_line(_line("stimula-", x=72, y=200))
    far = _para_from_line(_line("tion feels", x=72, y=100))
    assert merge_hyphen_wrapped_paragraphs([near, far]) == 0


def test_stroke_only_difference_still_splits():
    """Style intersection compares the whole graphic-state string."""
    pf = ParagraphFinder(
        TranslationConfig(
            translator=FixedMapTranslator(),
            input_file="toc.pdf",
            lang_in="en",
            lang_out="zh-CN",
            doc_layout_model=MagicMock(),
            auto_extract_glossary=False,
        )
    )
    white = _line("Part 3", x=41, y=500, fill="1 g 1 G")
    stroked = _line("The Mons", x=41, y=478, fill="1 g 0.2 G")
    paras = [
        PdfParagraph(
            box=Box(x=41, y=478, x2=400, y2=514),
            pdf_paragraph_composition=[white, stroked],
            unicode="",
            layout_label="list",
            xobj_id=0,
        )
    ]
    pf.process_independent_paragraphs(paras, median_width=400.0)
    assert len(paras) == 2


def test_white_line_splits_and_keeps_its_fill():
    pf = ParagraphFinder(
        TranslationConfig(
            translator=FixedMapTranslator(),
            input_file="toc.pdf",
            lang_in="en",
            lang_out="zh-CN",
            doc_layout_model=MagicMock(),
            auto_extract_glossary=False,
        )
    )
    white = _line("Part 3: Using The Rest Of The Vulva", x=41, y=500, fill="1 g 1 G")
    black = _line("The Mons", x=41, y=478, fill="0 g 0 G")
    paras = [
        PdfParagraph(
            box=Box(x=41, y=478, x2=400, y2=514),
            pdf_paragraph_composition=[white, black],
            unicode="",
            layout_label="list",
            xobj_id=0,
        )
    ]
    pf.process_independent_paragraphs(paras, median_width=400.0)
    assert len(paras) == 2
    styles = []
    for para in paras:
        chars = [
            c
            for comp in para.pdf_paragraph_composition
            if comp.pdf_line
            for c in comp.pdf_line.pdf_character
        ]
        styles.append(
            calculate_base_style(
                [c.pdf_style for c in chars],
                char_unicodes=[c.char_unicode for c in chars],
            )
        )
    fills = [
        s.graphic_state.passthrough_per_char_instruction
        for s in styles
        if s and s.graphic_state
    ]
    assert "1 g 1 G" in fills
    assert "0 g 0 G" in fills


def test_webdings_q_is_a_list_marker():
    chars = []
    x = 59.0
    for ch, font in (("Q", "Webdings"),) + tuple(
        (c, "Ubuntu") for c in " The Mons"
    ):
        if ch == " ":
            x += 6
            continue
        chars.append(_char(ch, x, 150, font_id=font))
        x += 8
    line = PdfLine(box=Box(x=59, y=150, x2=x, y2=164), pdf_character=chars)
    assert line_starts_with_list_marker(line)

    chars = []
    x = 59.0
    for ch, font in (("A", "ABCDEF+Janson"),) + tuple(
        (c, "Ubuntu") for c in " sentence"
    ):
        if ch == " ":
            x += 6
            continue
        chars.append(_char(ch, x, 120, font_id=font))
        x += 8
    text_line = PdfLine(box=Box(x=59, y=120, x2=x, y2=134), pdf_character=chars)
    assert line_starts_with_list_marker(text_line) is False
