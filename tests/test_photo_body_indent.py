"""Photo body may claim. A left step keeps the next sentence. A display tail is not one character."""

from unittest.mock import MagicMock

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
from babeldoc.format.pdf.document_il.il_version_1 import VisualBbox
from babeldoc.format.pdf.document_il.midend.typesetting import Typesetting
from babeldoc.format.pdf.document_il.midend.typesetting import TypesettingUnit
from babeldoc.format.pdf.document_il.midend.typesetting import left_indent_holds
from babeldoc.format.pdf.document_il.utils.layout_intent import LayoutIntent
from babeldoc.format.pdf.document_il.utils.layout_intent import LayoutIntentRole
from babeldoc.format.pdf.document_il.utils.layout_plan.geometry import geometry_eligible
from babeldoc.format.pdf.document_il.utils.layout_plan.line_edges import _edges
from babeldoc.format.pdf.document_il.utils.layout_plan.line_edges import _evaluate
from babeldoc.format.pdf.document_il.utils.layout_plan.model import ContourLevel
from babeldoc.format.pdf.document_il.utils.layout_plan.model import LineBox
from babeldoc.format.pdf.document_il.utils.layout_plan.model import LineEdgeLink
from babeldoc.format.pdf.document_il.utils.layout_plan.model import PocketLink
from babeldoc.format.pdf.document_il.utils.layout_plan.model import Region
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms import load_catalog
from babeldoc.format.pdf.document_il.utils.placement_paradigm import ParadigmMark
from babeldoc.format.pdf.document_il.utils.placement_paradigm import PlacementParadigm
from babeldoc.format.pdf.translation_config import TranslationConfig
from babeldoc.translator.fixed_map_translator import FixedMapTranslator

_CROTCH = (
    (267.0, 362.6, 437.7),
    (260.0, 370.6, 422.7),
    (253.0, 375.6, 407.7),
    (246.0, 381.6, 392.7),
    (239.0, 389.6, 377.7),
    (232.0, 397.6, 362.7),
    (224.0, 405.6, 347.7),
    (214.0, 413.6, 332.7),
    (205.0, 423.6, 317.7),
    (195.0, 433.6, 302.7),
    (186.0, 365.5, 287.7),
)
_SKIN = (
    (113.0, 332.0, 400.0),
    (113.0, 306.0, 370.0),
    (113.0, 238.0, 340.0),
    (113.0, 249.0, 310.0),
    (113.0, 220.0, 280.0),
    (113.0, 200.0, 250.0),
)


def _region(lines, *, on_photo=False, role=None):
    return Region(
        "r",
        0,
        0,
        role,
        tuple(LineBox(*line) for line in lines),
        text_on_photo=on_photo,
    )


def test_a_photo_body_that_opens_may_claim_and_a_caption_stays_out():
    body = _region(_CROTCH, on_photo=True, role="body")
    caption = _region(_CROTCH[:2], on_photo=True, role="body")
    skin = _region(_SKIN, on_photo=True, role="wrap_column")
    assert geometry_eligible(body) is True
    assert geometry_eligible(caption) is False
    assert geometry_eligible(skin) is False
    status, name, residual, _edges_out, _chosen = _evaluate(body, load_catalog())
    assert status == "matched"
    assert name == "both/wider_below"
    assert residual < 48.0
    recorded = [[float(x0), float(x1), float(y0)] for x0, x1, y0 in _CROTCH]
    for item in load_catalog():
        score = item.claim(_edges(body), recorded)
        if item.name != "both/wider_below":
            assert score is None or score > item.threshold


def _level(left, right, top):
    return ContourLevel(left, right, top)


def test_left_indent_holds_for_the_door_and_not_for_hang_or_a_right_step():
    door = (
        _level(100, 280, 400),
        _level(100, 280, 384),
        _level(100, 280, 368),
        _level(200, 280, 352),
        _level(200, 280, 336),
    )
    assert left_indent_holds(door, 100, 280, 200, 280) is True
    assert left_indent_holds(door, 100, 280, 100, 280) is False
    hang = (
        _level(80, 400, 400),
        _level(120, 390, 384),
        _level(120, 370, 368),
    )
    assert left_indent_holds(hang, 80, 400, 120, 390) is False
    repeated = (
        _level(100, 400, 400),
        _level(230, 400, 384),
        _level(100, 400, 368),
        _level(230, 400, 352),
    )
    assert left_indent_holds(repeated, 100, 400, 230, 400) is False
    assert left_indent_holds(door, 100, 280, 200, 360) is False


def _glyph(text, width=30.0):
    box = Box(x=0, y=0, x2=width, y2=12)
    char = PdfCharacter(
        char_unicode=text,
        box=box,
        visual_bbox=VisualBbox(box=Box(x=0, y=0, x2=width, y2=12)),
        pdf_style=PdfStyle(font_id="base", font_size=12.0, graphic_state=None),
    )
    return TypesettingUnit(char=char)


def _typesetting():
    return Typesetting(
        TranslationConfig(
            translator=FixedMapTranslator(),
            input_file="indent.pdf",
            lang_in="en",
            lang_out="zh-CN",
            doc_layout_model=MagicMock(),
            auto_extract_glossary=False,
        )
    )


def _paragraph(box, text):
    return PdfParagraph(
        box=box,
        pdf_style=PdfStyle(font_id="base", font_size=12.0, graphic_state=None),
        pdf_paragraph_composition=[],
        unicode=text,
        first_line_indent=0.0,
        alignment="left",
    )


def _lines_of(placed):
    grouped: dict[float, list] = {}
    for unit in placed:
        grouped.setdefault(round(unit.box.y, 1), []).append(unit)
    return [
        grouped[key]
        for key in sorted(grouped, reverse=True)
    ]


def _text(units):
    return "".join(unit.try_get_unicode() or "" for unit in units)


def test_a_sentence_starts_on_the_indented_line_without_spreading():
    text = "甲乙丙丁戊己庚辛壬癸子丑按摩。试想一下。"
    link = LineEdgeLink(
        "door",
        (
            (100.0, 280.0, 400.0),
            (100.0, 280.0, 384.0),
            (100.0, 280.0, 368.0),
            (160.0, 280.0, 352.0),
            (160.0, 280.0, 336.0),
        ),
        "left",
    )
    setter = _typesetting()
    setter._line_edges = link
    setter._pocket_link = None
    box = Box(x=40, y=200, x2=500, y2=408)
    placed, ok = setter._layout_typesetting_units(
        [_glyph(char) for char in text],
        box,
        1.0,
        1.2,
        _paragraph(box, text),
        use_english_line_break=False,
    )
    assert ok is True
    lines = _lines_of(placed)
    texts = [_text(line) for line in lines]
    assert "试" not in texts[2]
    assert texts[2].endswith("。")
    assert texts[3].startswith("试想一下")
    assert lines[3][0].box.x == 160.0
    stop = lines[2][-1]
    assert stop.box.x2 < 220.0


def test_a_figure_pocket_starts_the_sentence_on_the_indented_line():
    text = "甲乙丙丁戊己庚辛壬癸子丑按摩。试想一下。"
    box = Box(x=40, y=200, x2=500, y2=408)
    paragraph = _paragraph(box, text)
    paragraph.layout_intent = LayoutIntent(
        role=LayoutIntentRole.BODY,
        design_box=box,
        top_inset=0.0,
        bottom_inset=0.0,
        paradigm_mark=ParadigmMark(
            PlacementParadigm.RECT_REFLOW, 0.9, "stable_column"
        ),
    )
    setter = _typesetting()
    setter._line_edges = None
    setter._pocket_link = PocketLink(
        region_id="door",
        free_side="left",
        pin_edge=280.0,
        line_widths=(180.0,),
        opening=180.0,
        slices=((200.0, 356.0, 160.0),),
        edge_gap=0.0,
    )
    placed, ok = setter._layout_typesetting_units(
        [_glyph(char) for char in text],
        box,
        1.0,
        1.2,
        paragraph,
        use_english_line_break=False,
    )
    assert ok is True
    lines = _lines_of(placed)
    texts = [_text(line) for line in lines]
    closed = next(line for line in lines if _text(line).endswith("。") and "试" not in _text(line))
    assert _text(closed).endswith("。")
    opened = lines[lines.index(closed) + 1]
    assert _text(opened).startswith("试想一下")
    assert opened[0].box.x == 160.0
    assert closed[-1].box.x2 < 220.0
    assert "试" not in texts[lines.index(closed)]
    gaps = [
        opened[i + 1].box.x - opened[i].box.x2
        for i in range(len(opened) - 1)
    ]
    assert gaps
    assert max(gaps) < 2.0


def test_a_right_column_does_not_leave_one_character_and_a_left_column_stays():
    text = "环境的干扰。"
    edges = (
        (100.0, 180.0, 400.0),
        (100.0, 180.0, 384.0),
    )
    box = Box(x=40, y=200, x2=500, y2=408)
    units = [_glyph(char, width=20.0) for char in text]

    right = _typesetting()
    right._line_edges = LineEdgeLink("quote", edges, "right")
    right._pocket_link = None
    placed, ok = right._layout_typesetting_units(
        units,
        box,
        1.0,
        1.2,
        _paragraph(box, text),
        use_english_line_break=False,
    )
    assert ok is True
    texts = [_text(line) for line in _lines_of(placed)]
    assert texts[-2:] == ["环境的", "干扰。"]

    fresh = [_glyph(char, width=20.0) for char in text]
    left = _typesetting()
    left._line_edges = LineEdgeLink("body", edges, "left")
    left._pocket_link = None
    placed_left, ok_left = left._layout_typesetting_units(
        fresh,
        box,
        1.0,
        1.2,
        _paragraph(box, text),
        use_english_line_break=False,
    )
    assert ok_left is True
    assert _text(_lines_of(placed_left)[-1]) == "扰。"
