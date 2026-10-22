"""Same-baseline double paints, TOC color splits, cross-paragraph hyphens."""

from __future__ import annotations

from types import SimpleNamespace
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
from babeldoc.format.pdf.document_il.midend.paragraph_finder import drop_painted_twice
from babeldoc.format.pdf.document_il.midend.typesetting import Typesetting
from babeldoc.format.pdf.document_il.utils.hyphen_paragraph_merge import (
    merge_hyphen_wrapped_paragraphs,
)
from babeldoc.format.pdf.document_il.utils.layout_helper import is_bullet_point
from babeldoc.format.pdf.document_il.utils.layout_plan.model import ColumnLink
from babeldoc.format.pdf.document_il.utils.layout_plan.model import LayoutPlan
from babeldoc.format.pdf.document_il.utils.layout_plan.model import LineEdgeLink
from babeldoc.format.pdf.document_il.utils.layout_plan.model import RegionDecision
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


def _loose(text: str, x: float, y: float) -> PdfParagraph:
    comps = []
    cx = x
    for ch in text:
        comps.append(PdfParagraphComposition(pdf_character=_char(ch, cx, y)))
        cx += 8
    return PdfParagraph(
        box=Box(x=x, y=y, x2=cx, y2=y + 14),
        pdf_paragraph_composition=comps,
        unicode=text,
        layout_label="plain text",
    )


def test_a_second_paint_of_the_line_end_is_dropped():
    """The wrap paints the last letters again. That echo is not a sentence."""
    host = _loose("from", 100.0, 200.0)
    echo = _loose("m", 124.0, 200.0)
    beside = _loose("OK", 300.0, 160.0)
    stray = _char("n", 124.0, 200.0)
    margin = _char("z", 40.0, 80.0)
    kept, skipped = drop_painted_twice([host, echo, beside], [stray, margin])
    assert kept == [host, beside]
    assert skipped == [margin]


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

    empty = _char("", 51, 160, font_id="Webdings")
    assert is_bullet_point(empty)
    plain = _char("", 51, 160, font_id="Ubuntu-Light")
    assert is_bullet_point(plain) is False


def _multi(lines, *, region_id: str, render_order: int = 0) -> PdfParagraph:
    comps = [_line(text, x=x, y=y) for text, x, y in lines]
    xs = [comp.pdf_line.box.x for comp in comps]
    ys = [comp.pdf_line.box.y for comp in comps]
    x2s = [comp.pdf_line.box.x2 for comp in comps]
    y2s = [comp.pdf_line.box.y2 for comp in comps]
    paragraph = PdfParagraph(
        box=Box(x=min(xs), y=min(ys), x2=max(x2s), y2=max(y2s)),
        pdf_paragraph_composition=comps,
        unicode="".join(text for text, _x, _y in lines),
        render_order=render_order,
        xobj_id=0,
        layout_label="text",
    )
    paragraph.layout_region_id = region_id
    return paragraph


def _first_y(paragraph: PdfParagraph) -> float:
    return paragraph.pdf_paragraph_composition[0].pdf_line.pdf_character[0].box.y


def _run_post_overlap(paragraphs, plan) -> None:
    page = SimpleNamespace(
        pdf_paragraph=paragraphs,
        layout_plan=plan,
        cropbox=SimpleNamespace(box=Box(x=0, y=0, x2=612, y2=792)),
        page_number=57,
    )
    typesetter = Typesetting(
        TranslationConfig(
            translator=FixedMapTranslator(),
            input_file="overlap.pdf",
            lang_in="en",
            lang_out="zh-CN",
            doc_layout_model=MagicMock(),
            auto_extract_glossary=False,
        )
    )
    typesetter.fix_overlapping_paragraphs_post_typesetting(page)


def _edge_plan(*region_ids: str, **kwargs) -> LayoutPlan:
    return LayoutPlan(
        "synthetic",
        0,
        "single_page",
        kwargs.get("decisions", ()),
        column_links=kwargs.get("column_links", ()),
        line_edge_links=tuple(
            LineEdgeLink(region_id, ((231.0, 512.0),)) for region_id in region_ids
        ),
    )


def test_line_edge_ink_seats_the_paragraph_under_it():
    """Chinese leading hangs past the scanned contour onto the next paragraph."""
    spur = _multi(
        [("提高她的", 231, 170), ("膝盖上时）。", 231, 150)],
        region_id="spur",
        render_order=1,
    )
    below = _multi(
        [("弯曲位置）。接下来一边用手抚摸她的大腿", 102, 152)],
        region_id="below",
        render_order=2,
    )
    later = _multi(
        [("在这些高度敏感区域", 102, 100)],
        region_id="later",
        render_order=3,
    )
    spur_high = _first_y(spur)
    spur_low = spur.pdf_paragraph_composition[1].pdf_line.pdf_character[0].box.y
    later_y = _first_y(later)
    _run_post_overlap([spur, below, later], _edge_plan("spur"))
    first = spur.pdf_paragraph_composition[0].pdf_line.box
    last = spur.pdf_paragraph_composition[1].pdf_line.box
    pitch = float(first.y2) - float(last.y2)
    seated = below.pdf_paragraph_composition[0].pdf_line.box.y2
    assert seated <= float(last.y2) - pitch + 0.05
    assert _first_y(spur) == spur_high
    assert spur.pdf_paragraph_composition[1].pdf_line.pdf_character[0].box.y == spur_low
    assert _first_y(later) == later_y


def test_a_side_quote_stays_when_only_the_union_reaches_it():
    """A lower line steps out. The quote is beside that line, not under it."""
    body = _multi(
        [
            ("窄行停在引文左边", 102, 420),
            ("这一行才伸出去", 102, 300),
        ],
        region_id="body",
        render_order=1,
    )
    # 8 chars at 8pt from x=102 ends at 166. Pad the lower line past the quote.
    wide = body.pdf_paragraph_composition[1].pdf_line
    wide.box.x2 = 420.0
    wide.pdf_character[-1].box.x2 = 420.0
    quote = _multi(
        [("为更长时间的冥想做好准备", 400, 400)],
        region_id="quote",
        render_order=2,
    )
    quote_y = _first_y(quote)
    _run_post_overlap([body, quote], _edge_plan("body"))
    assert _first_y(quote) == quote_y
    assert _first_y(body) == 420


def test_a_side_quote_stays_when_it_only_grazes_a_line():
    """Three points of corner overlap is not the next paragraph."""
    body = _multi(
        [
            ("上面一行", 102, 430),
            ("伸出", 102, 370),
        ],
        region_id="body",
        render_order=1,
    )
    wide = body.pdf_paragraph_composition[1].pdf_line
    wide.box.x2 = 410.0
    wide.pdf_character[-1].box.x2 = 410.0
    quote = _multi(
        [("增加和改善你的性高潮体验", 406, 372)],
        region_id="quote",
        render_order=2,
    )
    quote_y = _first_y(quote)
    _run_post_overlap([body, quote], _edge_plan("body"))
    assert _first_y(quote) == quote_y


def test_character_lines_clear_by_their_own_pitch():
    """Typesetting stores one character each, not a pdf_line."""

    def chars(text: str, x: float, y: float, region: str, order: int) -> PdfParagraph:
        comps = []
        cx = x
        for ch in text:
            comps.append(PdfParagraphComposition(pdf_character=_char(ch, cx, y)))
            cx += 8
        paragraph = PdfParagraph(
            box=Box(x=x, y=y, x2=cx, y2=y + 14),
            pdf_paragraph_composition=comps,
            unicode=text,
            render_order=order,
            xobj_id=0,
            layout_label="text",
        )
        paragraph.layout_region_id = region
        return paragraph

    spur = chars("提高她的性爱", 231, 170, "spur", 1)
    low = chars("膝盖上时）。", 231, 150, "spur", 1)
    spur.pdf_paragraph_composition.extend(low.pdf_paragraph_composition)
    spur.box = Box(x=231, y=150, x2=400, y2=184)
    below = chars("弯曲位置）。接下来一边用手抚摸她的大腿", 102, 152, "below", 2)
    _run_post_overlap([spur, below], _edge_plan("spur"))
    seated = below.pdf_paragraph_composition[0].pdf_character.box.y2
    assert seated <= 144.05


def test_paragraph_above_a_line_edge_stays():
    spur = _multi([("膝盖上时）。", 231, 150)], region_id="spur", render_order=2)
    above = _multi(
        [("欲之火欲望。这段在刺突上方", 200, 160)],
        region_id="above",
        render_order=1,
    )
    above_y = _first_y(above)
    _run_post_overlap([above, spur], _edge_plan("spur"))
    assert _first_y(above) == above_y
    assert _first_y(spur) == 150


def test_rect_column_under_a_line_edge_stays():
    spur = _multi([("膝盖上时）。", 231, 150)], region_id="spur", render_order=1)
    rect = _multi(
        [("弯曲位置）。接下来一边用手抚摸她的大腿", 102, 152)],
        region_id="rect",
        render_order=2,
    )
    decision = RegionDecision(
        region_id="rect",
        base_strategy="rect_flow",
        modifiers=(),
        confidence=0.9,
        plugin_id="rect_flow",
        plugin_version="1",
        evidence=(),
        fallback=None,
        rejected=(),
    )
    plan = _edge_plan(
        "spur",
        decisions=(decision,),
        column_links=(ColumnLink("rect", "c", None, 102.0, 512.0),),
    )
    rect_y = _first_y(rect)
    _run_post_overlap([spur, rect], plan)
    assert _first_y(rect) == rect_y
    assert _first_y(spur) == 150


def test_two_line_edges_are_not_shifted():
    upper = _multi([("接下来", 231, 160)], region_id="wide", render_order=1)
    lower = _multi([("膝盖上时）。", 231, 152)], region_id="spur", render_order=2)
    upper_y = _first_y(upper)
    lower_y = _first_y(lower)
    _run_post_overlap([upper, lower], _edge_plan("wide", "spur"))
    assert _first_y(upper) == upper_y
    assert _first_y(lower) == lower_y
