"""Rectangular columns share one left and right edge before typesetting."""

from babeldoc.format.pdf.document_il import il_version_1
from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraphComposition
from babeldoc.format.pdf.document_il.il_version_1 import PdfSameStyleUnicodeCharacters
from babeldoc.format.pdf.document_il.il_version_1 import ReferenceMetrics
from babeldoc.format.pdf.document_il.utils.layout_intent import LayoutIntent
from babeldoc.format.pdf.document_il.utils.layout_intent import LayoutIntentRole
from babeldoc.format.pdf.document_il.utils.layout_intent import WrapMode
from babeldoc.format.pdf.document_il.utils.placement_paradigm import ParadigmMark
from babeldoc.format.pdf.document_il.utils.placement_paradigm import PlacementParadigm
from babeldoc.format.pdf.document_il.utils.rect_column_reflow import (
    absorb_short_continuations,
)
from babeldoc.format.pdf.document_il.utils.rect_column_reflow import assign_rect_columns
from babeldoc.format.pdf.document_il.utils.rect_column_reflow import (
    close_rect_column_gaps,
)
from babeldoc.format.pdf.document_il.utils.rect_column_reflow import (
    drop_below_display_band,
)
from babeldoc.format.pdf.document_il.utils.rect_column_reflow import flow_rect_columns
from babeldoc.format.pdf.document_il.utils.rect_column_reflow import (
    forget_display_bands,
)
from babeldoc.format.pdf.document_il.utils.rect_column_reflow import is_gutter_display
from babeldoc.format.pdf.document_il.utils.rect_column_reflow import (
    keep_gutter_displays,
)
from babeldoc.format.pdf.document_il.utils.rect_column_reflow import mark_display_bands
from babeldoc.format.pdf.document_il.utils.rect_column_reflow import (
    prepare_rect_columns,
)
from babeldoc.format.pdf.document_il.utils.rect_column_reflow import settle_rect_columns
from babeldoc.format.pdf.document_il.utils.rect_column_reflow import source_profile
from babeldoc.format.pdf.document_il.utils.rect_column_reflow import (
    uses_rect_column_fill,
)
from babeldoc.format.pdf.document_il.utils.rect_column_reflow import (
    yield_to_display_bands,
)
from babeldoc.format.pdf.document_il.utils.rect_flow_stack import clear_held_spans
from babeldoc.format.pdf.document_il.utils.rect_flow_stack import note_held_spans


def _para(x, x2, paradigm, role=LayoutIntentRole.BODY):
    box = Box(x=x, y=100.0, x2=x2, y2=200.0)
    intent = LayoutIntent(
        role=role,
        design_box=Box(x=x, y=100.0, x2=x2, y2=200.0),
        top_inset=0.0,
        bottom_inset=0.0,
        paradigm_mark=ParadigmMark(paradigm, 0.9, "test"),
    )
    paragraph = il_version_1.PdfParagraph(
        box=box, pdf_paragraph_composition=[], unicode="正文"
    )
    paragraph.layout_intent = intent
    paragraph.alignment = "center"
    return paragraph


def test_narrow_rect_opens_to_the_column_and_stays_left():
    wide = _para(300.0, 560.0, PlacementParadigm.RECT_REFLOW)
    narrow = _para(340.0, 480.0, PlacementParadigm.RECT_REFLOW)
    assign_rect_columns([wide, narrow])
    assert narrow.alignment == "left"
    assert narrow.box.x == 300.0
    assert narrow.box.x2 == 560.0
    assert wide.box.x == 300.0
    assert wide.box.x2 == 560.0


def test_left_and_right_columns_stay_apart():
    left = _para(40.0, 250.0, PlacementParadigm.RECT_REFLOW)
    right = _para(320.0, 560.0, PlacementParadigm.RECT_REFLOW)
    assign_rect_columns([left, right])
    assert left.box.x2 == 250.0
    assert right.box.x == 320.0


def test_shaped_body_line_inside_a_column_opens():
    pocket = _para(320.0, 420.0, PlacementParadigm.SHAPED_POCKET)
    neighbour = _para(300.0, 560.0, PlacementParadigm.RECT_REFLOW)
    assign_rect_columns([pocket, neighbour])
    assert uses_rect_column_fill(pocket)
    assert pocket.alignment == "left"
    assert pocket.box.x == 300.0
    assert pocket.box.x2 == 560.0


def _write(paragraph, text, y, y2):
    paragraph.box.y = y
    paragraph.box.y2 = y2
    paragraph.unicode = text
    styled = PdfSameStyleUnicodeCharacters(unicode=text)
    paragraph.pdf_paragraph_composition = [
        PdfParagraphComposition(pdf_same_style_unicode_characters=styled)
    ]
    return paragraph


def test_stacked_source_lines_become_one_column_run():
    first = _write(
        _para(36.0, 350.0, PlacementParadigm.RECT_REFLOW),
        "这显然会造成许多不同的问题",
        300.0,
        314.0,
    )
    second = _write(
        _para(36.0, 168.0, PlacementParadigm.RECT_REFLOW),
        "在关系中，例如",
        282.0,
        296.0,
    )
    page = [first, second]
    flow_rect_columns(page)
    assert page == [first]
    assert first.unicode == "这显然会造成许多不同的问题在关系中，例如"
    assert first.alignment == "left"
    assert first.box.x == 36.0
    assert first.box.x2 == 350.0
    assert first.layout_intent.wrap_mode.value == "none"
    assert first.layout_intent.paradigm_mark.paradigm is PlacementParadigm.RECT_REFLOW


def test_paragraph_gap_stays_two_runs():
    first = _write(
        _para(36.0, 350.0, PlacementParadigm.RECT_REFLOW),
        "上一句",
        300.0,
        314.0,
    )
    second = _write(
        _para(36.0, 350.0, PlacementParadigm.RECT_REFLOW),
        "下一句",
        270.0,
        284.0,
    )
    page = [first, second]
    flow_rect_columns(page)
    assert first.unicode == "上一句"
    assert second.unicode == "下一句"


def test_narrowing_cone_stays_put():
    cone = _para(300.0, 520.0, PlacementParadigm.SHAPED_POCKET)
    cone.layout_intent.wrap_shape = [
        (0.0, 220.0),
        (0.0, 150.0),
        (0.0, 100.0),
        (0.0, 50.0),
    ]
    neighbour = _para(300.0, 560.0, PlacementParadigm.RECT_REFLOW)
    assign_rect_columns([cone, neighbour])
    assert not uses_rect_column_fill(cone)
    assert cone.box.x2 == 520.0
    assert neighbour.box.x2 == 560.0


def test_deeper_photo_inset_keeps_its_left():
    upper = _para(238.0, 578.0, PlacementParadigm.RECT_REFLOW)
    lower = _para(344.0, 560.0, PlacementParadigm.RECT_REFLOW)
    assign_rect_columns([upper, lower])
    assert lower.box.x == 344.0
    assert lower.box.x2 == 578.0
    assert lower.alignment == "left"
    assert upper.box.x == 238.0


def _font(paragraph, size):
    paragraph.reference_metrics = ReferenceMetrics(
        line_count=1,
        avg_line_width=100.0,
        last_line_width=100.0,
        last_line_ratio=1.0,
        font_size=size,
    )
    return paragraph


def test_body_sized_callout_joins_the_sentence():
    first = _write(
        _para(36.0, 350.0, PlacementParadigm.RECT_REFLOW),
        "这显然会造成许多不同的问题",
        300.0,
        314.0,
    )
    second = _font(
        _write(
            _para(
                36.0,
                168.0,
                PlacementParadigm.KEEP_CURRENT,
                LayoutIntentRole.CALLOUT,
            ),
            "在关系中，例如",
            282.0,
            296.0,
        ),
        12.0,
    )
    page = [first, second]
    flow_rect_columns(page)
    assert page == [first]
    assert first.unicode == "这显然会造成许多不同的问题在关系中，例如"
    assert first.layout_intent.wrap_mode.value == "none"


def test_display_pull_quote_stays_out_of_the_column():
    quote = _font(
        _write(
            _para(
                80.0,
                400.0,
                PlacementParadigm.KEEP_CURRENT,
                LayoutIntentRole.PULL_QUOTE,
            ),
            "大段引语",
            300.0,
            340.0,
        ),
        24.0,
    )
    body = _write(
        _para(36.0, 360.0, PlacementParadigm.RECT_REFLOW),
        "正文一行",
        260.0,
        274.0,
    )
    page = [quote, body]
    flow_rect_columns(page)
    assert quote.unicode == "大段引语"
    assert not uses_rect_column_fill(quote)
    assert len(page) == 2
    assert body.unicode == "正文一行"


def test_lowercase_body_joins_across_a_pull_quote():
    upper = _write(
        _para(36.0, 540.0, PlacementParadigm.RECT_REFLOW),
        "the external part of the female",
        500.0,
        518.0,
    )
    quote = _font(
        _write(
            _para(
                90.0,
                520.0,
                PlacementParadigm.KEEP_CURRENT,
                LayoutIntentRole.PULL_QUOTE,
            ),
            "stimulation of the clitoris may be",
            360.0,
            470.0,
        ),
        30.0,
    )
    lower = _write(
        _para(36.0, 540.0, PlacementParadigm.RECT_REFLOW),
        "genitalia, including the lips",
        250.0,
        340.0,
    )
    page = _sheet([upper, quote, lower])
    docs = type("Docs", (), {"page": [page]})()
    try:
        prepare_rect_columns(docs)
        assert quote.unicode == "stimulation of the clitoris may be"
        assert upper.unicode == (
            "the external part of the female genitalia, including the lips"
        )
        assert lower not in page.pdf_paragraph
    finally:
        forget_display_bands(page.pdf_paragraph, page)


def test_new_sentence_under_a_pull_quote_stays_separate():
    upper = _write(
        _para(36.0, 540.0, PlacementParadigm.RECT_REFLOW),
        "the external part of the female",
        500.0,
        518.0,
    )
    quote = _font(
        _write(
            _para(
                90.0,
                520.0,
                PlacementParadigm.KEEP_CURRENT,
                LayoutIntentRole.PULL_QUOTE,
            ),
            "stimulation of the clitoris may be",
            360.0,
            470.0,
        ),
        30.0,
    )
    lower = _write(
        _para(36.0, 540.0, PlacementParadigm.RECT_REFLOW),
        "The vagina is the internal part",
        250.0,
        340.0,
    )
    page = _sheet([upper, quote, lower])
    docs = type("Docs", (), {"page": [page]})()
    try:
        prepare_rect_columns(docs)
        assert upper.unicode == "the external part of the female"
        assert lower.unicode == "The vagina is the internal part"
        assert quote in page.pdf_paragraph
    finally:
        forget_display_bands(page.pdf_paragraph, page)


def test_reflow_steps_over_a_quote_between_the_halves():
    upper = _write(
        _para(36.0, 400.0, PlacementParadigm.RECT_REFLOW),
        "the female",
        500.0,
        518.0,
    )
    quote = _font(
        _write(
            _para(
                90.0,
                380.0,
                PlacementParadigm.KEEP_CURRENT,
                LayoutIntentRole.PULL_QUOTE,
            ),
            "a displayed quote line",
            360.0,
            470.0,
        ),
        30.0,
    )
    lower = _write(
        _para(36.0, 400.0, PlacementParadigm.RECT_REFLOW),
        "genitalia continues in the column",
        250.0,
        340.0,
    )
    chars = []
    for index in range(40):
        chars.append(
            PdfCharacter(
                box=Box(x=40.0, y=500.0 - index, x2=76.0, y2=512.0 - index),
                char_unicode="文",
            )
        )
    page = _sheet([upper, quote, lower])
    docs = type("Docs", (), {"page": [page]})()
    try:
        prepare_rect_columns(docs)
        upper.pdf_paragraph_composition = [
            PdfParagraphComposition(pdf_character=char) for char in chars
        ]
        settle_rect_columns(page.pdf_paragraph, page)
        mids = [(float(char.box.y) + float(char.box.y2)) / 2.0 for char in chars]
        assert any(mid > 470.0 for mid in mids)
        assert any(mid < 342.0 for mid in mids)
        assert all(mid > 470.0 or mid < 342.0 for mid in mids)
    finally:
        forget_display_bands(page.pdf_paragraph, page)


def test_photo_shoulder_continuation_joins():
    upper = _write(
        _para(273.0, 578.0, PlacementParadigm.RECT_REFLOW),
        "女性的高潮时间通常比男人会",
        300.0,
        314.0,
    )
    lower = _font(
        _write(
            _para(
                326.0,
                548.0,
                PlacementParadigm.KEEP_CURRENT,
                LayoutIntentRole.PULL_QUOTE,
            ),
            "这些有趣的事实和数字是",
            282.0,
            296.0,
        ),
        12.0,
    )
    page = [upper, lower]
    flow_rect_columns(page)
    assert page == [upper]
    assert upper.unicode.endswith("这些有趣的事实和数字是")
    assert upper.alignment == "left"


def test_far_step_stays_its_own_run():
    upper = _write(
        _para(238.0, 578.0, PlacementParadigm.RECT_REFLOW),
        "上一句铺满整栏",
        300.0,
        314.0,
    )
    lower = _font(
        _write(
            _para(
                360.0,
                548.0,
                PlacementParadigm.KEEP_CURRENT,
                LayoutIntentRole.PULL_QUOTE,
            ),
            "下一句",
            282.0,
            296.0,
        ),
        12.0,
    )
    page = [upper, lower]
    flow_rect_columns(page)
    assert lower.unicode == "下一句"
    assert lower.box.x == 360.0
    assert lower.alignment == "left"
    assert uses_rect_column_fill(lower)


def _place(paragraph, y, y2):
    paragraph.box.y = y
    paragraph.box.y2 = y2
    return paragraph


def test_early_column_pulls_the_next_block_up():
    upper = _place(_para(36.0, 360.0, PlacementParadigm.RECT_REFLOW), 500.0, 640.0)
    lower = _place(_para(36.0, 360.0, PlacementParadigm.RECT_REFLOW), 300.0, 420.0)
    glyph = Box(x=40.0, y=300.0, x2=52.0, y2=420.0)
    lower.pdf_paragraph_composition = [
        PdfParagraphComposition(pdf_character=type("C", (), {"box": glyph})())
    ]
    close_rect_column_gaps([upper, lower])
    assert lower.box.y2 == 482.0
    assert glyph.y2 == 482.0


def test_ordinary_column_gap_stays():
    upper = _place(_para(36.0, 360.0, PlacementParadigm.RECT_REFLOW), 500.0, 520.0)
    lower = _place(_para(36.0, 360.0, PlacementParadigm.RECT_REFLOW), 460.0, 480.0)
    close_rect_column_gaps([upper, lower])
    assert lower.box.y2 == 480.0


def test_deeper_inset_keeps_its_vertical_band():
    upper = _place(_para(36.0, 360.0, PlacementParadigm.RECT_REFLOW), 500.0, 640.0)
    lower = _place(_para(120.0, 360.0, PlacementParadigm.RECT_REFLOW), 280.0, 400.0)
    close_rect_column_gaps([upper, lower])
    assert lower.box.y2 == 400.0


def test_block_in_the_gap_is_not_crossed():
    upper = _place(_para(36.0, 360.0, PlacementParadigm.RECT_REFLOW), 500.0, 640.0)
    lower = _place(_para(36.0, 360.0, PlacementParadigm.RECT_REFLOW), 280.0, 400.0)
    quote = _font(
        _place(
            _para(
                80.0,
                300.0,
                PlacementParadigm.KEEP_CURRENT,
                LayoutIntentRole.PULL_QUOTE,
            ),
            430.0,
            470.0,
        ),
        24.0,
    )
    close_rect_column_gaps([upper, quote, lower])
    assert lower.box.y2 == 400.0


def test_list_items_in_a_column_open_together():
    item = _para(
        360.0, 470.0, PlacementParadigm.KEEP_CURRENT, LayoutIntentRole.LIST
    )
    body = _para(320.0, 560.0, PlacementParadigm.RECT_REFLOW)
    assign_rect_columns([item, body])
    assert uses_rect_column_fill(item)
    assert item.box.x == 320.0
    assert item.box.x2 == 560.0
    assert item.alignment == "left"


def test_text_on_photo_stays_out_of_the_column():
    para = _para(36.0, 200.0, PlacementParadigm.RECT_REFLOW)
    para.layout_intent.text_on_photo = True
    assert not uses_rect_column_fill(para)


def test_a_profile_outside_the_box_is_not_placed():
    from babeldoc.format.pdf.document_il.utils import rect_column_reflow as column

    para = _para(36.0, 400.0, PlacementParadigm.RECT_REFLOW)
    outside = [
        (400.0, 420.0, 36.0, 400.0),
        (380.0, 400.0, 36.0, 400.0),
    ]
    inside = [
        (120.0, 140.0, 36.0, 400.0),
        (100.0, 120.0, 36.0, 360.0),
    ]
    page = object()
    column._PROFILES[id(para)] = outside
    column._PAGE_BANDS[id(page)] = [(300.0, 360.0, 0.0, 500.0)]
    try:
        assert column._group_samples([para]) == []
        assert source_profile(para) == []
        assert column._spans_display_band([(para, [])], page) is False
        column._PROFILES[id(para)] = inside
        assert column._group_samples([para]) == inside
        assert source_profile(para) == inside
    finally:
        column._PROFILES.pop(id(para), None)
        column._PAGE_BANDS.pop(id(page), None)


def test_source_profile_keeps_the_line_taper():
    para = _write(_para(36.0, 400.0, PlacementParadigm.RECT_REFLOW), "正文", 200.0, 360.0)
    para.reference_metrics = ReferenceMetrics(
        line_count=4,
        avg_line_width=300.0,
        last_line_width=80.0,
        last_line_ratio=0.2,
        font_size=12.0,
        per_line_widths=[360.0, 300.0, 240.0, 80.0],
    )
    flow_rect_columns([para])
    profile = source_profile(para)
    assert len(profile) == 4
    assert profile[0][3] - profile[0][2] == 360.0
    assert profile[2][3] - profile[2][2] < 260.0


def test_another_page_does_not_wipe_the_column_profile():
    para = _write(
        _para(36.0, 400.0, PlacementParadigm.RECT_REFLOW), "正文", 200.0, 360.0
    )
    para.reference_metrics = ReferenceMetrics(
        line_count=4,
        avg_line_width=300.0,
        last_line_width=80.0,
        last_line_ratio=0.2,
        font_size=12.0,
        per_line_widths=[360.0, 300.0, 240.0, 80.0],
    )
    flow_rect_columns([para])
    other = _write(
        _para(36.0, 200.0, PlacementParadigm.RECT_REFLOW), "另一页", 500.0, 540.0
    )
    other.reference_metrics = ReferenceMetrics(
        line_count=2,
        avg_line_width=95.0,
        last_line_width=90.0,
        last_line_ratio=0.9,
        font_size=12.0,
        per_line_widths=[100.0, 90.0],
    )
    flow_rect_columns([other])
    assert para.reference_metrics.per_line_widths is None
    flow_rect_columns([para])
    profile = source_profile(para)
    assert len(profile) == 4
    assert profile[2][3] - profile[2][2] < 260.0


def _glyphs(paragraph, count, y, y2):
    chars = []
    for index in range(count):
        x = 36.0 + index * 20.0
        chars.append(
            PdfCharacter(
                box=Box(x=x, y=y, x2=x + 18.0, y2=y2),
                char_unicode="文",
            )
        )
    paragraph.pdf_paragraph_composition = [
        PdfParagraphComposition(pdf_character=char) for char in chars
    ]
    return chars


def test_short_column_opens_down_and_follows_the_taper():
    para = _write(
        _para(36.0, 240.0, PlacementParadigm.RECT_REFLOW),
        "文" * 40,
        200.0,
        400.0,
    )
    para.reference_metrics = ReferenceMetrics(
        line_count=6,
        avg_line_width=160.0,
        last_line_width=100.0,
        last_line_ratio=0.6,
        font_size=12.0,
        per_line_widths=[200.0, 180.0, 160.0, 140.0, 120.0, 100.0],
    )
    flow_rect_columns([para])
    chars = _glyphs(para, 48, 370.0, 388.0)
    settle_rect_columns([para])
    assert min(char.box.y for char in chars) < 230.0
    low_edge = max(char.box.x2 for char in chars if char.box.y < 250.0)
    assert low_edge <= 36.0 + 160.0


def test_open_stops_at_the_band_bottom():
    para = _write(
        _para(36.0, 240.0, PlacementParadigm.RECT_REFLOW),
        "文" * 40,
        200.0,
        400.0,
    )
    para.reference_metrics = ReferenceMetrics(
        line_count=8,
        avg_line_width=150.0,
        last_line_width=100.0,
        last_line_ratio=0.6,
        font_size=12.0,
        per_line_widths=[200.0, 190.0, 180.0, 170.0, 160.0, 150.0, 140.0, 130.0],
    )
    flow_rect_columns([para])
    chars = _glyphs(para, 40, 370.0, 388.0)
    settle_rect_columns([para])
    lowest = min(char.box.y for char in chars)
    assert lowest >= 199.0
    assert lowest < 280.0


def test_column_that_already_fills_the_band_stays():
    upper = _write(_para(36.0, 300.0, PlacementParadigm.RECT_REFLOW), "上", 360.0, 380.0)
    lower = _write(_para(36.0, 300.0, PlacementParadigm.RECT_REFLOW), "下", 300.0, 320.0)
    flow_rect_columns([upper, lower])
    upper_char = PdfCharacter(
        box=Box(x=36.0, y=360.0, x2=80.0, y2=378.0), char_unicode="上"
    )
    lower_char = PdfCharacter(
        box=Box(x=36.0, y=302.0, x2=80.0, y2=320.0), char_unicode="下"
    )
    upper.pdf_paragraph_composition = [
        PdfParagraphComposition(pdf_character=upper_char)
    ]
    lower.pdf_paragraph_composition = [
        PdfParagraphComposition(pdf_character=lower_char)
    ]
    settle_rect_columns([upper, lower])
    assert lower_char.box.y == 302.0


def _metrics(size: float):
    return ReferenceMetrics(
        line_count=1,
        avg_line_width=100.0,
        last_line_width=100.0,
        last_line_ratio=1.0,
        font_size=size,
    )


def _sheet(paras, curves=None):
    frame = Box(x=0.0, y=0.0, x2=612.0, y2=792.0)
    return il_version_1.Page(
        cropbox=il_version_1.Cropbox(box=frame),
        mediabox=il_version_1.Mediabox(
            box=Box(x=0.0, y=0.0, x2=612.0, y2=792.0)
        ),
        pdf_paragraph=list(paras),
        pdf_curve=list(curves or []),
    )


def _filled_bar(x, y, x2, y2):
    return il_version_1.PdfCurve(
        box=Box(x=x, y=y, x2=x2, y2=y2),
        graphic_state=None,
        fill_background=True,
        debug_info="a",
    )


def test_text_on_a_bar_stays_out_and_body_moves_below():
    title = _para(36.0, 220.0, PlacementParadigm.RECT_REFLOW)
    title.box.y = 400.0
    title.box.y2 = 424.0
    beside = _para(230.0, 500.0, PlacementParadigm.RECT_REFLOW)
    beside.box.y = 400.0
    beside.box.y2 = 422.0
    bar = _filled_bar(30.0, 396.0, 250.0, 446.0)
    page = _sheet([title, beside], [bar])
    try:
        mark_display_bands(page)
        yield_to_display_bands(page)
        assert not uses_rect_column_fill(title)
        assert title.box.x2 == 250.0
        assert title.alignment == "left"
        assert beside.box.y2 <= 396.0
        assert uses_rect_column_fill(beside)
    finally:
        forget_display_bands([title, beside])


def test_wide_heading_box_locks_to_the_bar_and_stays_left():
    title = _place(_para(36.0, 520.0, PlacementParadigm.RECT_REFLOW), 400.0, 428.0)
    bar = _filled_bar(36.0, 396.0, 280.0, 446.0)
    page = _sheet([title], [bar])
    try:
        mark_display_bands(page)
        assert title.box.x == 36.0
        assert title.box.x2 == 280.0
        assert title.box.y == 396.0
        assert title.alignment == "left"
        assert not uses_rect_column_fill(title)
    finally:
        forget_display_bands([title], page)


def test_tall_glyphs_reserve_a_band_when_the_stored_font_is_body():
    title = _font(
        _place(_para(36.0, 500.0, PlacementParadigm.RECT_REFLOW), 240.0, 360.0),
        16.0,
    )
    _glyphs(title, 4, 254.0, 292.0)
    body = _place(_para(36.0, 500.0, PlacementParadigm.RECT_REFLOW), 260.0, 278.0)
    page = _sheet([title, body])
    try:
        mark_display_bands(page)
        yield_to_display_bands(page)
        assert not uses_rect_column_fill(title)
        assert body.box.y2 <= 254.0
    finally:
        forget_display_bands([title, body], page)


def test_body_font_in_a_tall_box_does_not_own_a_band():
    quote = _font(
        _place(_para(36.0, 400.0, PlacementParadigm.RECT_REFLOW), 200.0, 300.0),
        12.0,
    )
    _glyphs(quote, 6, 270.0, 284.0)
    page = _sheet([quote])
    try:
        mark_display_bands(page)
        assert uses_rect_column_fill(quote)
    finally:
        forget_display_bands([quote], page)


def test_bar_title_that_sits_on_the_right_moves_flush_left():
    title = _place(
        _para(36.0, 280.0, PlacementParadigm.RECT_REFLOW, LayoutIntentRole.TITLE),
        396.0,
        446.0,
    )
    chars = _glyphs(title, 4, 400.0, 424.0)
    for char in chars:
        char.box.x += 80.0
        char.box.x2 += 80.0
    bar = _filled_bar(36.0, 396.0, 280.0, 446.0)
    page = _sheet([title], [bar])
    try:
        mark_display_bands(page)
        settle_rect_columns([title], page)
        assert min(char.box.x for char in chars) <= 42.0
        assert max(char.box.x2 for char in chars) <= 280.0
    finally:
        forget_display_bands([title], page)


def test_line_under_a_large_title_clears_the_painted_letters():
    title = _font(
        _place(
            _para(36.0, 500.0, PlacementParadigm.RECT_REFLOW, LayoutIntentRole.TITLE),
            500.0,
            536.0,
        ),
        36.0,
    )
    body = _place(_para(36.0, 500.0, PlacementParadigm.RECT_REFLOW), 460.0, 500.0)
    chars = _glyphs(body, 4, 478.0, 496.0)
    page = _sheet([title, body])
    try:
        mark_display_bands(page)
        settle_rect_columns([title, body], page)
        assert max(char.box.y2 for char in chars) <= 482.5
        assert max(char.box.y2 for char in chars) >= 478.0
    finally:
        forget_display_bands([title, body], page)


def test_body_line_flush_under_a_bar_keeps_a_gap():
    title = _place(
        _para(36.0, 388.0, PlacementParadigm.RECT_REFLOW, LayoutIntentRole.TITLE),
        396.0,
        424.0,
    )
    body = _place(_para(36.0, 388.0, PlacementParadigm.RECT_REFLOW), 360.0, 396.0)
    chars = _glyphs(body, 6, 378.0, 396.0)
    bar = _filled_bar(36.0, 396.0, 388.0, 424.0)
    page = _sheet([title, body], [bar])
    try:
        mark_display_bands(page)
        settle_rect_columns([title, body], page)
        top = max(char.box.y2 for char in chars)
        assert top <= 396.0 - 10.0
        assert top >= 396.0 - 14.0
        assert title.box.y == 396.0
    finally:
        forget_display_bands([title, body], page)


def test_narrow_quotation_mark_does_not_own_a_band():
    mark = _place(_para(36.0, 70.0, PlacementParadigm.RECT_REFLOW), 320.0, 400.0)
    _glyphs(mark, 1, 330.0, 400.0)
    body = _place(_para(36.0, 500.0, PlacementParadigm.RECT_REFLOW), 340.0, 360.0)
    page = _sheet([mark, body])
    try:
        mark_display_bands(page)
        yield_to_display_bands(page)
        assert uses_rect_column_fill(mark)
        assert body.box.y2 == 360.0
    finally:
        forget_display_bands([mark, body], page)


def test_giant_quote_mark_does_not_swallow_the_line_above():
    upper = _write(
        _para(36.0, 540.0, PlacementParadigm.RECT_REFLOW),
        "the female",
        560.0,
        596.0,
    )
    mark = _font(
        _place(_para(36.0, 86.0, PlacementParadigm.RECT_REFLOW), 400.0, 580.0),
        100.0,
    )
    quote = _font(
        _write(
            _para(
                98.0,
                540.0,
                PlacementParadigm.KEEP_CURRENT,
                LayoutIntentRole.PULL_QUOTE,
            ),
            "stimulation of the clitoris may be",
            420.0,
            530.0,
        ),
        30.0,
    )
    lower = _write(
        _para(36.0, 540.0, PlacementParadigm.RECT_REFLOW),
        "genitalia, including the lips",
        250.0,
        390.0,
    )
    chars = []
    for index in range(72):
        chars.append(
            PdfCharacter(
                box=Box(x=40.0, y=560.0 - index, x2=76.0, y2=572.0 - index),
                char_unicode="文",
            )
        )
    page = _sheet([upper, mark, quote, lower])
    docs = type("Docs", (), {"page": [page]})()
    try:
        prepare_rect_columns(docs)
        assert not uses_rect_column_fill(mark)
        assert upper.box.y2 == 596.0
        upper.pdf_paragraph_composition = [
            PdfParagraphComposition(pdf_character=char) for char in chars
        ]
        settle_rect_columns(page.pdf_paragraph, page)
        mids = [(float(char.box.y) + float(char.box.y2)) / 2.0 for char in chars]
        assert any(mid > 530.0 for mid in mids)
        assert any(mid < 402.0 for mid in mids)
        assert all(mid > 530.0 or mid < 402.0 for mid in mids)
        assert mark.box.y2 == 580.0
    finally:
        forget_display_bands(page.pdf_paragraph, page)


def test_short_top_above_a_quote_is_not_clipped():
    quote = _font(
        _place(
            _para(
                98.0,
                520.0,
                PlacementParadigm.KEEP_CURRENT,
                LayoutIntentRole.PULL_QUOTE,
            ),
            420.0,
            530.0,
        ),
        30.0,
    )
    body = _place(_para(36.0, 540.0, PlacementParadigm.RECT_REFLOW), 250.0, 600.0)
    page = _sheet([quote, body])
    try:
        mark_display_bands(page)
        yield_to_display_bands(page)
        assert body.box.y == 250.0
        assert body.box.y2 == 600.0
    finally:
        forget_display_bands([quote, body], page)


def test_paragraph_spanning_a_band_is_not_sliced():
    title = _para(36.0, 400.0, PlacementParadigm.RECT_REFLOW, LayoutIntentRole.TITLE)
    title.box.y = 300.0
    title.box.y2 = 340.0
    body = _para(36.0, 500.0, PlacementParadigm.RECT_REFLOW)
    body.box.y = 200.0
    body.box.y2 = 460.0
    page = _sheet([title, body])
    try:
        mark_display_bands(page)
        yield_to_display_bands(page)
        assert body.box.y == 200.0
        assert body.box.y2 == 460.0
    finally:
        forget_display_bands([title, body])


def test_left_gutter_quote_holds_the_hole():
    """The quote stays. A line through it drops. A line on the indent stays."""
    quote = _place(_para(54.0, 274.0, PlacementParadigm.RECT_REFLOW), 330.2, 390.2)
    quote.reference_metrics = _metrics(13.0)
    hang = _place(_para(102.0, 569.0, PlacementParadigm.RECT_REFLOW), 303.5, 423.5)
    page = _sheet([quote, hang])
    try:
        mark_display_bands(page)
        yield_to_display_bands(page)
        assert not uses_rect_column_fill(quote)
        assert hang.box.y == 303.5
        assert hang.box.y2 == 423.5
        beside = drop_below_display_band(hang, 360.0, 14.0, page, (294.0, 560.0))
        through = drop_below_display_band(hang, 360.0, 14.0, page, (102.0, 560.0))
        assert beside == 360.0
        assert through < 330.2
    finally:
        forget_display_bands(page.pdf_paragraph, page)


def test_wrap_column_gutter_quote_holds_the_hole():
    """A side quote labeled as a wrap column still keeps its box."""
    quote = _place(
        _para(54.0, 269.8, PlacementParadigm.RECT_REFLOW, LayoutIntentRole.WRAP_COLUMN),
        313.3,
        390.2,
    )
    quote.reference_metrics = _metrics(13.0)
    hang = _place(_para(102.0, 569.0, PlacementParadigm.RECT_REFLOW), 303.5, 423.5)
    page = _sheet([quote, hang])
    try:
        mark_display_bands(page)
        through = drop_below_display_band(hang, 360.0, 14.0, page, (102.0, 560.0))
        beside = drop_below_display_band(hang, 360.0, 14.0, page, (294.0, 560.0))
        assert through < 313.3
        assert beside == 360.0
        assert hang.box.y2 == 423.5
    finally:
        forget_display_bands(page.pdf_paragraph, page)


def test_body_sized_quote_and_side_callout_still_fill():
    quote = _para(
        36.0, 220.0, PlacementParadigm.RECT_REFLOW, LayoutIntentRole.PULL_QUOTE
    )
    quote.reference_metrics = _metrics(12.0)
    gutter = _para(
        40.0, 160.0, PlacementParadigm.RECT_REFLOW, LayoutIntentRole.CALLOUT
    )
    gutter.reference_metrics = _metrics(12.0)
    page = _sheet([quote, gutter])
    try:
        mark_display_bands(page)
        assert uses_rect_column_fill(quote)
        assert uses_rect_column_fill(gutter)
    finally:
        forget_display_bands([quote, gutter])


def test_gap_closer_crosses_a_band_in_the_other_column():
    upper = _place(_para(36.0, 200.0, PlacementParadigm.RECT_REFLOW), 500.0, 640.0)
    lower = _place(_para(36.0, 200.0, PlacementParadigm.RECT_REFLOW), 300.0, 380.0)
    title = _place(_para(400.0, 560.0, PlacementParadigm.RECT_REFLOW), 396.0, 446.0)
    bar = _filled_bar(400.0, 396.0, 560.0, 446.0)
    page = _sheet([upper, lower, title], [bar])
    try:
        mark_display_bands(page)
        close_rect_column_gaps([upper, lower, title], page)
        assert lower.box.y2 == 482.0
    finally:
        forget_display_bands([upper, lower, title], page)


def test_margin_mark_stays_beside_the_quote():
    quote = _place(
        _para(
            120.0,
            520.0,
            PlacementParadigm.RECT_REFLOW,
            LayoutIntentRole.PULL_QUOTE,
        ),
        300.0,
        420.0,
    )
    quote.reference_metrics = _metrics(30.0)
    mark = _place(_para(36.0, 80.0, PlacementParadigm.RECT_REFLOW), 320.0, 400.0)
    char = PdfCharacter(
        box=Box(x=40.0, y=330.0, x2=70.0, y2=400.0), char_unicode="“"
    )
    mark.pdf_paragraph_composition = [PdfParagraphComposition(pdf_character=char)]
    page = _sheet([quote, mark])
    try:
        mark_display_bands(page)
        yield_to_display_bands(page)
        settle_rect_columns([quote, mark], page)
        assert mark.box.y2 == 400.0
        assert char.box.y2 == 400.0
    finally:
        forget_display_bands([quote, mark], page)


def test_list_lead_overlapping_the_body_joins_in_front():
    lead = _font(
        _write(
            _para(
                51.0,
                200.0,
                PlacementParadigm.KEEP_CURRENT,
                LayoutIntentRole.FORMULA,
            ),
            "Of the women who aren't",
            132.0,
            146.0,
        ),
        12.0,
    )
    body = _write(
        _para(66.0, 560.0, PlacementParadigm.RECT_REFLOW),
        "orgasming, 50% said they were close",
        96.0,
        148.0,
    )
    page = [lead, body]
    flow_rect_columns(page)
    assert page == [lead]
    assert lead.unicode.startswith("Of the women who aren't")
    assert "50%" in lead.unicode


def test_same_x_overlap_stays_two_runs():
    upper = _write(
        _para(36.0, 400.0, PlacementParadigm.RECT_REFLOW),
        "上一句还没写完",
        140.0,
        154.0,
    )
    lower = _write(
        _para(36.0, 400.0, PlacementParadigm.RECT_REFLOW),
        "另一句叠在上面",
        130.0,
        160.0,
    )
    page = [upper, lower]
    flow_rect_columns(page)
    assert upper.unicode == "上一句还没写完"
    assert lower.unicode == "另一句叠在上面"


def test_split_bullet_above_a_title_joins_and_keeps_its_left():
    lead = _font(
        _write(
            _para(
                51.0,
                426.0,
                PlacementParadigm.KEEP_CURRENT,
                LayoutIntentRole.FORMULA,
            ),
            "\x12 Women generally. That doesn't",
            618.6,
            633.0,
        ),
        12.0,
    )
    mid = _write(
        _para(67.0, 578.0, PlacementParadigm.RECT_REFLOW),
        "mean you need to last 20 minutes, but it does mean",
        600.7,
        633.0,
    )
    tail = _write(
        _para(66.5, 578.0, PlacementParadigm.RECT_REFLOW),
        "you need foreplay if you want her to cum.",
        564.7,
        597.0,
    )
    title = _font(
        _place(
            _para(36.0, 510.0, PlacementParadigm.RECT_REFLOW, LayoutIntentRole.TITLE),
            503.0,
            540.0,
        ),
        36.0,
    )
    nxt = _write(
        _para(36.0, 578.0, PlacementParadigm.RECT_REFLOW),
        "First things first, you need to learn.",
        420.0,
        450.0,
    )
    page = [lead, mid, tail, title, nxt]
    flow_rect_columns(page)
    assert mid not in page
    assert tail not in page
    assert nxt in page
    assert title in page
    assert lead.unicode.startswith("\x12 Women generally")
    assert "foreplay" in lead.unicode
    assert "First" not in lead.unicode
    assert lead.box.y >= title.box.y2
    assert lead.box.x == 51.0
    assert lead.box.x2 == 578.0


def test_a_line_short_of_a_quote_keeps_its_place():
    """The union box reaches the quote. This line's own width does not."""
    quote = _font(
        _write(
            _para(
                392.0,
                574.0,
                PlacementParadigm.KEEP_CURRENT,
                LayoutIntentRole.PULL_QUOTE,
            ),
            "引言",
            299.0,
            399.0,
        ),
        17.0,
    )
    body = _place(_para(78.0, 537.0, PlacementParadigm.RECT_REFLOW), 317.0, 467.0)
    page = _sheet([quote, body])
    try:
        mark_display_bands(page)
        dropped = drop_below_display_band(body, 370.0, 18.0, page)
        stayed = drop_below_display_band(body, 370.0, 18.0, page, (78.0, 375.0))
        reached = drop_below_display_band(body, 370.0, 18.0, page, (78.0, 537.0))
        above = drop_below_display_band(body, 420.0, 18.0, page, (78.0, 537.0))
        assert dropped == 281.0
        assert stayed == 370.0
        assert reached == 281.0
        assert above == 420.0
    finally:
        forget_display_bands([quote, body], page)


def test_line_above_a_title_is_not_sent_under_it():
    title = _font(
        _place(
            _para(36.0, 500.0, PlacementParadigm.RECT_REFLOW, LayoutIntentRole.TITLE),
            500.0,
            536.0,
        ),
        36.0,
    )
    body = _place(_para(66.0, 560.0, PlacementParadigm.RECT_REFLOW), 560.0, 620.0)
    page = _sheet([title, body])
    try:
        mark_display_bands(page)
        landed = drop_below_display_band(body, 520.0, 16.0, page)
        assert landed >= 510.0
    finally:
        forget_display_bands([title, body], page)


def _glyph(text, x, width, y=370.0, font="SourceHan"):
    return PdfCharacter(
        box=Box(x=x, y=y, x2=x + width, y2=y + 16.0),
        char_unicode=text,
        pdf_style=il_version_1.PdfStyle(
            font_id=font,
            font_size=12.0,
            graphic_state=None,
        ),
    )


def _run(specs, left=36.0, right=136.0):
    from babeldoc.format.pdf.document_il.utils.rect_column_reflow import (
        _place_paragraph,
    )

    chars = []
    x = left
    for text, width, font in specs:
        chars.append(_glyph(text, x, width, font=font))
        x += width
    measure = [(0.0, 500.0, left, right)]
    lines, _y = _place_paragraph(chars, measure, 480.0, 20.0)
    return lines


def _line_text(line) -> str:
    return "".join(char.char_unicode or "" for char, _advance, _width in line[2])


def test_reflow_keeps_a_percent_with_its_digits():
    body = "请让我分析一下。"
    specs = [(ch, 10.0, "SourceHan") for ch in body]
    specs.extend(
        [
            ("5", 7.0, "SourceHan"),
            ("7", 7.0, "SourceHan"),
            ("%", 11.0, "SourceHan"),
            ("的", 10.0, "SourceHan"),
            ("女", 10.0, "SourceHan"),
            ("性", 10.0, "SourceHan"),
        ]
    )
    lines = _run(specs)
    assert len(lines) >= 2
    for line in lines:
        assert not _line_text(line).startswith("%")
    percent_line = next(line for line in lines if "%" in _line_text(line))
    assert "57%" in _line_text(percent_line)


def test_reflow_keeps_a_percent_across_a_nbsp():
    body = "请让我分析一下。"
    specs = [(ch, 10.0, "SourceHan") for ch in body]
    specs.extend(
        [
            ("5", 7.0, "SourceHan"),
            ("7", 7.0, "SourceHan"),
            ("\u00a0", 3.0, "SourceHan"),
            ("%", 11.0, "SourceHan"),
            ("的", 10.0, "SourceHan"),
        ]
    )
    lines = _run(specs)
    assert len(lines) >= 2
    for line in lines:
        assert not _line_text(line).lstrip("\u00a0").startswith("%")
    percent_line = next(line for line in lines if "%" in _line_text(line))
    assert "7\u00a0%" in _line_text(percent_line)


def test_reflow_does_not_split_a_number_before_the_percent():
    body = "请让我分析一下。"
    specs = [(ch, 10.0, "SourceHan") for ch in body]
    specs.extend(
        [
            ("5", 7.0, "SourceHan"),
            ("7", 7.0, "SourceHan"),
            ("%", 11.0, "SourceHan"),
            ("的", 10.0, "SourceHan"),
        ]
    )
    lines = _run(specs, left=36.0, right=126.0)
    assert len(lines) >= 2
    for line in lines:
        text = _line_text(line).lstrip(" \u00a0")
        assert not text.startswith("%")
        assert not text.startswith("7%")
    percent_line = next(line for line in lines if "%" in _line_text(line))
    assert "57%" in _line_text(percent_line)


def test_reflow_hangs_to_the_word_after_a_blank_glyph():
    specs = [("", 12.0, "Webdings"), ("", 3.0, "SourceHan")]
    specs.extend((ch, 12.0, "SourceHan") for ch in "女性一般比男性需要更长的时间来高潮")
    lines = _run(specs, left=51.0, right=231.0)
    assert len(lines) >= 2
    assert lines[0][1] == 51.0
    assert lines[1][1] == 66.0


def test_reflow_can_open_a_line_with_a_whole_percent():
    body = "请让我来分析一下。"
    specs = [(ch, 10.0, "SourceHan") for ch in body]
    specs.extend(
        [
            (" ", 4.0, "SourceHan"),
            ("3", 7.0, "SourceHan"),
            ("0", 7.0, "SourceHan"),
            ("%", 11.0, "SourceHan"),
            ("的", 10.0, "SourceHan"),
        ]
    )
    lines = _run(specs)
    percent_line = next(line for line in lines if "%" in _line_text(line))
    assert _line_text(percent_line).startswith("30%")


def test_reflow_does_not_glue_a_percent_to_the_previous_word():
    body = "请让我来分析一下。"
    specs = [(ch, 10.0, "SourceHan") for ch in body]
    specs.extend([("%", 11.0, "SourceHan"), ("的", 10.0, "SourceHan")])
    lines = _run(specs)
    assert len(lines) >= 2
    assert _line_text(lines[0]).endswith("。")
    assert _line_text(lines[1]).startswith("%")


def test_reflow_hangs_a_webdings_bullet_under_the_text():
    specs = [("", 12.0, "Webdings"), (" ", 3.0, "SourceHan")]
    specs.extend((ch, 12.0, "SourceHan") for ch in "女性一般比男性需要更长的时间来高潮")
    lines = _run(specs, left=51.0, right=231.0)
    assert len(lines) >= 2
    assert lines[0][1] == 51.0
    assert lines[1][1] == 66.0
    assert not _line_text(lines[1]).startswith("%")


def test_reflow_does_not_hang_a_wide_dingbat():
    specs = [("", 80.0, "Webdings")]
    specs.extend((ch, 12.0, "SourceHan") for ch in "女性一般比男性需要更长的时间")
    lines = _run(specs, left=51.0, right=231.0)
    assert len(lines) >= 2
    assert lines[1][1] == 51.0


def test_gutter_quote_stays_beside_the_column():
    body = _write(
        _para(199.0, 512.0, PlacementParadigm.RECT_REFLOW),
        "Be sure to spend",
        383.0,
        503.0,
    )
    quote = _font(
        _write(
            _para(
                57.0,
                205.0,
                PlacementParadigm.RECT_REFLOW,
                LayoutIntentRole.WRAP_COLUMN,
            ),
            "don't just focus",
            211.0,
            438.0,
        ),
        22.0,
    )
    quote.layout_intent.wrap_shape = [(0.0, 148.0)]
    quote.layout_intent.wrap_mode = WrapMode.NONE
    quote.layout_intent.expansion_policy = ("right", "down")
    page = _sheet([body, quote])
    try:
        keep_gutter_displays(page)
        assert quote.layout_intent.wrap_shape is None
        assert quote.layout_intent.expansion_policy == ()
        assert is_gutter_display(quote)
        mark_display_bands(page)
        yield_to_display_bands(page)
        flow_rect_columns(page.pdf_paragraph)
        assert quote in page.pdf_paragraph
        assert quote.box.x == 57.0
        assert body.box.x == 199.0
        assert body.box.x2 == 512.0
        assert body.box.y == 383.0
        assert "don't" not in body.unicode
        assert not uses_rect_column_fill(quote)
    finally:
        forget_display_bands(page.pdf_paragraph, page)


def test_page_banner_does_not_pull_the_column_to_the_margin():
    banner = _font(
        _place(_para(42.0, 544.0, PlacementParadigm.RECT_REFLOW), 650.0, 666.0),
        15.0,
    )
    body = _place(
        _para(200.0, 512.0, PlacementParadigm.RECT_REFLOW),
        380.0,
        520.0,
    )
    flow_rect_columns([banner, body])
    assert body.box.x == 200.0
    assert body.box.x2 == 512.0
    assert banner.box.x == 42.0
    assert banner.box.x2 == 544.0
    assert uses_rect_column_fill(banner)


def test_short_line_on_the_column_still_shares_its_edge():
    intro = _place(_para(200.0, 544.0, PlacementParadigm.RECT_REFLOW), 530.0, 546.0)
    body = _place(_para(200.0, 512.0, PlacementParadigm.RECT_REFLOW), 380.0, 500.0)
    flow_rect_columns([intro, body])
    assert body.box.x == 200.0
    assert body.box.x2 == 544.0
    assert intro.box.x == 200.0
    assert intro.box.x2 == 544.0


def test_held_column_blocks_the_rise():
    upper = _place(_para(200.0, 512.0, PlacementParadigm.RECT_REFLOW), 500.0, 640.0)
    lower = _place(_para(200.0, 512.0, PlacementParadigm.RECT_REFLOW), 300.0, 420.0)
    obstacle = _place(_para(144.0, 511.0, PlacementParadigm.RECT_REFLOW), 430.0, 490.0)
    page = _sheet([upper, lower])
    try:
        note_held_spans(page, [obstacle])
        close_rect_column_gaps([upper, lower], page)
        assert lower.box.y2 == 420.0
    finally:
        clear_held_spans(page)
    upper_b = _place(_para(36.0, 200.0, PlacementParadigm.RECT_REFLOW), 500.0, 640.0)
    lower_b = _place(_para(36.0, 200.0, PlacementParadigm.RECT_REFLOW), 300.0, 420.0)
    aside = _place(_para(400.0, 560.0, PlacementParadigm.RECT_REFLOW), 430.0, 490.0)
    other = _sheet([upper_b, lower_b])
    try:
        note_held_spans(other, [aside])
        close_rect_column_gaps([upper_b, lower_b], other)
        assert lower_b.box.y2 == 482.0
    finally:
        clear_held_spans(other)


def test_short_lowercase_line_joins_the_line_above():
    host = _write(
        _para(153.0, 512.0, PlacementParadigm.RECT_REFLOW),
        "into the palms",
        68.0,
        98.0,
    )
    tail = _write(
        _para(143.0, 213.0, PlacementParadigm.RECT_REFLOW),
        "of your hands.",
        53.0,
        67.0,
    )
    capital = _write(
        _para(143.0, 400.0, PlacementParadigm.RECT_REFLOW),
        "Another way to add",
        30.0,
        44.0,
    )
    page = type("Page", (), {"pdf_paragraph": [host, tail, capital]})()
    absorb_short_continuations(page)
    assert tail not in page.pdf_paragraph
    assert "of your hands." in host.unicode
    assert capital in page.pdf_paragraph
    assert capital.unicode == "Another way to add"


def test_short_box_grows_down_to_its_character_lines():
    body = _write(
        _para(199.0, 512.0, PlacementParadigm.RECT_REFLOW),
        "Be sure to spend",
        400.0,
        460.0,
    )
    char = PdfCharacter(
        box=Box(x=210.0, y=340.0, x2=400.0, y2=354.0),
        char_unicode="e",
    )
    styled = il_version_1.PdfSameStyleCharacters(
        box=Box(x=199.0, y=340.0, x2=400.0, y2=460.0),
        pdf_style=il_version_1.PdfStyle(
            font_id="f",
            font_size=12.0,
            graphic_state=None,
        ),
        pdf_character=[char],
    )
    body.pdf_paragraph_composition.append(
        PdfParagraphComposition(pdf_same_style_characters=styled)
    )
    flow_rect_columns([body])
    assert body.box.y == 340.0
    assert body.box.y2 == 460.0
    assert body.box.x == 199.0


def test_visual_ink_below_a_clipped_box_grows_it():
    body = _write(
        _para(199.0, 512.0, PlacementParadigm.RECT_REFLOW),
        "Be sure to spend",
        440.0,
        503.0,
    )
    body.layout_intent.design_box = Box(x=199.0, y=440.0, x2=512.0, y2=503.0)
    char = PdfCharacter(
        box=Box(x=210.0, y=450.0, x2=400.0, y2=462.0),
        visual_bbox=il_version_1.VisualBbox(
            box=Box(x=210.0, y=383.0, x2=400.0, y2=397.0)
        ),
        char_unicode="e",
    )
    styled = il_version_1.PdfSameStyleCharacters(
        box=Box(x=199.0, y=383.0, x2=400.0, y2=503.0),
        pdf_style=il_version_1.PdfStyle(
            font_id="f",
            font_size=12.0,
            graphic_state=None,
        ),
        pdf_character=[char],
    )
    body.pdf_paragraph_composition.append(
        PdfParagraphComposition(pdf_same_style_characters=styled)
    )
    flow_rect_columns([body])
    assert body.box.y == 383.0
    assert body.box.y2 == 503.0
    assert body.box.x == 199.0


def test_lifted_bottom_comes_back_from_the_covered_ink():
    body = _write(
        _para(199.0, 512.0, PlacementParadigm.RECT_REFLOW),
        "Be sure to spend",
        440.5,
        503.2,
    )
    body.layout_intent.design_box = Box(x=199.0, y=383.2, x2=512.0, y2=503.2)
    flow_rect_columns([body])
    assert body.box.y == 383.2
    assert body.box.y2 == 503.2
    assert body.box.x == 199.0
    assert body.box.x2 == 512.0
    moved = _write(
        _para(199.0, 512.0, PlacementParadigm.RECT_REFLOW),
        "Be sure to spend",
        500.0,
        600.0,
    )
    moved.layout_intent.design_box = Box(x=199.0, y=383.2, x2=512.0, y2=503.2)
    flow_rect_columns([moved])
    assert moved.box.y == 500.0
    assert moved.box.y2 == 600.0


def test_body_glyphs_inside_a_bar_move_below_it():
    title = _place(_para(36.0, 250.0, PlacementParadigm.RECT_REFLOW), 396.0, 446.0)
    body = _place(_para(36.0, 400.0, PlacementParadigm.RECT_REFLOW), 300.0, 390.0)
    chars = _glyphs(body, 6, 420.0, 438.0)
    bar = _filled_bar(30.0, 396.0, 250.0, 446.0)
    page = _sheet([title, body], [bar])
    try:
        mark_display_bands(page)
        settle_rect_columns([title, body], page)
        assert max(char.box.y2 for char in chars) <= 396.5
    finally:
        forget_display_bands([title, body], page)
