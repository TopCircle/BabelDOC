"""Placement paradigm selection from role and line geometry."""

from __future__ import annotations

from types import SimpleNamespace

from babeldoc.format.pdf.document_il import il_version_1
from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter
from babeldoc.format.pdf.document_il.il_version_1 import PdfLine
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraphComposition
from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
from babeldoc.format.pdf.document_il.il_version_1 import VisualBbox
from babeldoc.format.pdf.document_il.utils.figure_wrap import taper_prefix_widths
from babeldoc.format.pdf.document_il.utils.layout_intent import LayoutIntent
from babeldoc.format.pdf.document_il.utils.layout_intent import LayoutIntentRole
from babeldoc.format.pdf.document_il.utils.layout_intent import WrapMode
from babeldoc.format.pdf.document_il.utils.layout_intent_extractor import (
    LayoutIntentExtractor,
)
from babeldoc.format.pdf.document_il.utils.line_interval_plan import effective_wrap_mode
from babeldoc.format.pdf.document_il.utils.line_interval_plan import (
    resolve_line_interval_plan,
)
from babeldoc.format.pdf.document_il.utils.placement_paradigm import PlacementParadigm
from babeldoc.format.pdf.document_il.utils.placement_paradigm import select_paradigm


def _taper_boxes() -> list[tuple[float, float, float]]:
    # Higher y is higher on the page. Left edge steps in going downward.
    return [(100.0 + 12.0 * i, 570.0, 160.0 - 15.0 * i) for i in range(4)]


def _stable_boxes() -> list[tuple[float, float, float]]:
    return [(102.0, 570.0, 200.0 - 15.0 * i) for i in range(5)]


def test_stable_column_is_rect_reflow():
    mark = select_paradigm(LayoutIntentRole.BODY, None, _stable_boxes())
    assert mark.paradigm is PlacementParadigm.RECT_REFLOW
    assert mark.confidence >= 0.8
    assert mark.reason == "stable_column"


def test_four_line_taper_is_shaped_pocket():
    mark = select_paradigm(LayoutIntentRole.BODY, WrapMode.NONE, _taper_boxes())
    assert mark.paradigm is PlacementParadigm.SHAPED_POCKET
    assert mark.reason == "taper"


def test_three_line_inset_is_too_short():
    boxes = [(100.0 + 12.0 * i, 570.0, 160.0 - 15.0 * i) for i in range(3)]
    mark = select_paradigm(LayoutIntentRole.BODY, None, boxes)
    assert mark.paradigm is PlacementParadigm.RECT_REFLOW
    assert mark.reason == "taper_too_short"


def test_hanging_indents_are_not_taper():
    boxes: list[tuple[float, float, float]] = []
    y = 400.0
    for _ in range(3):
        boxes.append((56.0, 540.0, y))
        y -= 16.0
        boxes.append((92.0, 540.0, y))
        y -= 16.0
        boxes.append((74.0, 220.0, y))
        y -= 16.0
        boxes.append((92.0, 540.0, y))
        y -= 20.0
    mark = select_paradigm(LayoutIntentRole.BODY, None, boxes)
    assert mark.paradigm is PlacementParadigm.RECT_REFLOW
    assert mark.reason == "not_taper"


def test_kept_roles_are_not_shaped():
    boxes = _taper_boxes()
    for role in (
        LayoutIntentRole.PULL_QUOTE,
        LayoutIntentRole.LIST,
        LayoutIntentRole.CHROME,
        LayoutIntentRole.TITLE,
    ):
        mark = select_paradigm(role, None, boxes)
        assert mark.paradigm is PlacementParadigm.KEEP_CURRENT


def test_right_fixed_without_taper_stays_rect():
    mark = select_paradigm(LayoutIntentRole.BODY, WrapMode.RIGHT_FIXED, _stable_boxes())
    assert mark.paradigm is PlacementParadigm.RECT_REFLOW
    assert mark.reason == "shape_not_taper"


def test_left_fixed_taper_stays_shaped():
    mark = select_paradigm(LayoutIntentRole.BODY, WrapMode.LEFT_FIXED, _taper_boxes())
    assert mark.paradigm is PlacementParadigm.SHAPED_POCKET


def _left_pin_stepping_right_boxes() -> list[tuple[float, float, float]]:
    """Left edge pinned, right edge steps. Higher y is higher on the page.

    Spans are the OA p59 wrap body. They are evidence for the mirror of a
    right-edge pin, not thresholds.
    """
    spans = (
        (101.87, 333.64),
        (102.53, 340.67),
        (102.00, 342.65),
        (102.91, 333.62),
        (102.28, 325.63),
        (102.22, 322.61),
        (102.13, 320.65),
    )
    return [(x0, x1, 400.0 - 16.0 * index) for index, (x0, x1) in enumerate(spans)]


def test_left_edge_pin_with_stepping_right_is_shaped_pocket():
    mark = select_paradigm(
        LayoutIntentRole.BODY,
        WrapMode.LEFT_FIXED,
        _left_pin_stepping_right_boxes(),
    )
    assert mark.paradigm is PlacementParadigm.SHAPED_POCKET
    assert mark.reason == "taper"


def test_three_line_left_pin_is_too_short():
    boxes = [(102.0, 340.0 - 30.0 * index, 200.0 - 16.0 * index) for index in range(3)]
    mark = select_paradigm(LayoutIntentRole.BODY, None, boxes)
    assert mark.paradigm is PlacementParadigm.RECT_REFLOW
    assert mark.reason == "taper_too_short"


def test_no_lines_is_low_confidence_rect():
    mark = select_paradigm(LayoutIntentRole.BODY, None, [])
    assert mark.paradigm is PlacementParadigm.RECT_REFLOW
    assert mark.confidence == 0.4
    assert mark.reason == "no_lines"


def _extract(paragraph: il_version_1.PdfParagraph) -> None:
    page = il_version_1.Page(
        cropbox=il_version_1.Cropbox(box=Box(x=0, y=0, x2=612, y2=792)),
        mediabox=il_version_1.Mediabox(box=Box(x=0, y=0, x2=612, y2=792)),
        pdf_paragraph=[paragraph],
        page_number=1,
    )
    document = il_version_1.Document(page=[page], total_pages=1)
    LayoutIntentExtractor(SimpleNamespace(debug=False)).extract(document)


def test_extract_marks_rect_body():
    # One visual glyph, like test_insets_from_visual_bbox. The box is a body
    # column: a 200pt box is a callout and would keep the current placement.
    char = PdfCharacter(
        char_unicode="a",
        box=Box(x=72, y=5, x2=82, y2=95),
        visual_bbox=VisualBbox(box=Box(x=72, y=10, x2=82, y2=90)),
        pdf_style=PdfStyle(font_id="base", font_size=12.0, graphic_state=None),
    )
    paragraph = il_version_1.PdfParagraph(
        box=Box(x=72, y=0, x2=540, y2=100),
        unicode="a",
        pdf_style=PdfStyle(font_id="base", font_size=12.0, graphic_state=None),
        pdf_paragraph_composition=[PdfParagraphComposition(pdf_character=char)],
    )
    _extract(paragraph)
    intent = paragraph.layout_intent
    assert intent.role is LayoutIntentRole.BODY
    assert intent.paradigm_mark.paradigm is PlacementParadigm.RECT_REFLOW
    assert intent.wrap_mode is WrapMode.NONE


def test_extract_marks_chrome_keep_current():
    # Same construction as test_role_chrome: a footer line stays chrome.
    line = PdfLine(
        box=Box(x=10, y=10, x2=100, y2=30),
        pdf_character=[
            PdfCharacter(
                char_unicode="a",
                box=Box(x=10, y=10, x2=100, y2=30),
                pdf_style=PdfStyle(font_id="base", font_size=12.0, graphic_state=None),
            )
        ],
    )
    paragraph = il_version_1.PdfParagraph(
        box=Box(x=10, y=10, x2=600, y2=30),
        unicode="text",
        layout_label="footer",
        pdf_style=PdfStyle(font_id="base", font_size=12.0, graphic_state=None),
        pdf_paragraph_composition=[PdfParagraphComposition(pdf_line=line)],
    )
    _extract(paragraph)
    intent = paragraph.layout_intent
    assert intent.role is LayoutIntentRole.CHROME
    assert intent.paradigm_mark.paradigm is PlacementParadigm.KEEP_CURRENT
    assert intent.paradigm_mark.reason == "keep_role"


def _marked_paragraph(mark, wrap_mode: WrapMode) -> il_version_1.PdfParagraph:
    design = Box(x=102.0, y=100.0, x2=570.0, y2=400.0)
    paragraph = il_version_1.PdfParagraph(
        box=design,
        pdf_paragraph_composition=[],
        unicode="x",
    )
    paragraph.layout_intent = LayoutIntent(
        role=LayoutIntentRole.BODY,
        design_box=design,
        top_inset=0.0,
        bottom_inset=0.0,
        wrap_mode=wrap_mode,
        wrap_shape=[(0.0, 468.0)],
        paradigm_mark=mark,
    )
    return paragraph


def test_rect_reflow_wrap_mode_ignores_shape():
    boxes = [(102.0, 570.0, 200.0 - 15.0 * index) for index in range(4)]
    mark = select_paradigm(LayoutIntentRole.BODY, WrapMode.NONE, boxes)
    assert mark.paradigm is PlacementParadigm.RECT_REFLOW
    paragraph = _marked_paragraph(mark, WrapMode.NONE)
    assert effective_wrap_mode(paragraph, shape_present=True) is WrapMode.NONE


def test_shaped_pocket_wrap_mode_stays_right_fixed():
    mark = select_paradigm(
        LayoutIntentRole.BODY, WrapMode.RIGHT_FIXED, _taper_boxes()
    )
    assert mark.paradigm is PlacementParadigm.SHAPED_POCKET
    paragraph = _marked_paragraph(mark, WrapMode.RIGHT_FIXED)
    assert effective_wrap_mode(paragraph, shape_present=True) is WrapMode.RIGHT_FIXED


def test_missing_mark_wrap_mode_stays_right_fixed():
    paragraph = _marked_paragraph(None, WrapMode.NONE)
    assert effective_wrap_mode(paragraph, shape_present=True) is WrapMode.RIGHT_FIXED


def test_rect_reflow_wrap_mode_keeps_prior_alignment():
    from babeldoc.format.pdf.document_il.utils.line_interval_plan import (
        apply_wrap_flush,
    )

    boxes = [(102.0, 570.0, 200.0 - 15.0 * index) for index in range(4)]
    mark = select_paradigm(LayoutIntentRole.BODY, WrapMode.NONE, boxes)
    paragraph = _marked_paragraph(mark, WrapMode.NONE)
    assert apply_wrap_flush(paragraph, "center") == "center"


def test_missing_mark_wrap_mode_still_flushes_right():
    from babeldoc.format.pdf.document_il.utils.line_interval_plan import (
        apply_wrap_flush,
    )

    paragraph = _marked_paragraph(None, WrapMode.NONE)
    assert apply_wrap_flush(paragraph, "left") == "right"


def test_left_edge_cone_keeps_left_fixed_pocket():
    boxes = _left_pin_stepping_right_boxes()
    mark = select_paradigm(LayoutIntentRole.BODY, WrapMode.LEFT_FIXED, boxes)
    design = Box(x=101.87, y=80.0, x2=342.65, y2=420.0)
    paragraph = il_version_1.PdfParagraph(
        box=design,
        pdf_paragraph_composition=[],
        unicode="x",
    )
    paragraph.layout_intent = LayoutIntent(
        role=LayoutIntentRole.BODY,
        design_box=design,
        top_inset=0.0,
        bottom_inset=0.0,
        wrap_mode=WrapMode.LEFT_FIXED,
        wrap_shape=[(0.0, x1 - x0) for x0, x1, _y in boxes],
        paradigm_mark=mark,
    )
    assert effective_wrap_mode(paragraph, shape_present=True) is WrapMode.LEFT_FIXED
    plan = resolve_line_interval_plan(paragraph, design)
    assert plan.wrap_active is True
    assert plan.wrap_mode is WrapMode.LEFT_FIXED
    x1, _x2 = plan.intervals_at(300.0, 312.0, line_idx=0)[0]
    assert abs(x1 - 101.87) < 1e-6


def test_rect_explicit_left_fixed_keeps_wrap_pocket():
    boxes = [(102.0, 340.0, 200.0 - 15.0 * index) for index in range(5)]
    mark = select_paradigm(LayoutIntentRole.BODY, WrapMode.LEFT_FIXED, boxes)
    assert mark.paradigm is PlacementParadigm.RECT_REFLOW
    assert mark.reason == "shape_not_taper"
    paragraph = _marked_paragraph(mark, WrapMode.LEFT_FIXED)
    assert effective_wrap_mode(paragraph, shape_present=True) is WrapMode.LEFT_FIXED
    plan = resolve_line_interval_plan(paragraph, paragraph.box)
    assert plan.wrap_active is True
    assert plan.wrap_mode is WrapMode.LEFT_FIXED
    x1, _x2 = plan.intervals_at(200.0, 212.0, line_idx=0)[0]
    assert abs(x1 - 102.0) < 1e-6


def _line(x: float, x2: float, y: float) -> SimpleNamespace:
    return SimpleNamespace(x=x, x2=x2, y=y)


def test_clustered_right_pin_scores_cleaned_cone():
    """Raw zigzag is not a taper. The stored cone is. The mark must follow it."""
    raw = [
        252.7, 244.1, 227.8, 239.3, 202.3, 228.3, 133.7, 193.6,
        155.6, 174.1, 114.5, 142.6, 51.6, 86.6, 99.6,
    ]
    cleaned = taper_prefix_widths(raw)
    right = 570.0
    lines = [
        _line(right - width, right, 400.0 - 16.0 * index)
        for index, width in enumerate(raw)
    ]
    design = Box(x=right - max(raw), y=0.0, x2=right, y2=500.0)
    intent = LayoutIntent(
        role=LayoutIntentRole.WRAP_COLUMN,
        design_box=design,
        top_inset=0.0,
        bottom_inset=0.0,
        wrap_mode=WrapMode.RIGHT_FIXED,
        wrap_shape=[(0.0, width) for width in cleaned],
    )
    LayoutIntentExtractor(SimpleNamespace(debug=False))._attach_paradigm_mark(
        intent, {"lines": lines}
    )
    assert intent.paradigm_mark.paradigm is PlacementParadigm.SHAPED_POCKET
    paragraph = il_version_1.PdfParagraph(
        box=design, pdf_paragraph_composition=[], unicode="x"
    )
    paragraph.layout_intent = intent
    from babeldoc.format.pdf.document_il.utils.line_interval_plan import (
        apply_wrap_flush,
    )

    assert apply_wrap_flush(paragraph, "left") == "right"


def test_clustered_left_pin_scores_cleaned_cone():
    raw = [
        213.6, 227.6, 157.8, 204.6, 235.0, 218.8, 237.5, 212.1,
        227.9, 206.9, 219.8, 204.3, 217.6, 179.2, 214.6, 198.3,
        213.9, 191.6, 213.0, 89.1, 181.6, 210.0, 167.7, 193.1,
    ]
    cleaned = taper_prefix_widths(raw)
    left = 102.0
    lines = [
        _line(left, left + width, 500.0 - 16.0 * index)
        for index, width in enumerate(raw)
    ]
    design = Box(x=left, y=0.0, x2=left + max(raw), y2=600.0)
    intent = LayoutIntent(
        role=LayoutIntentRole.WRAP_COLUMN,
        design_box=design,
        top_inset=0.0,
        bottom_inset=0.0,
        wrap_mode=WrapMode.LEFT_FIXED,
        wrap_shape=[(0.0, width) for width in cleaned],
    )
    LayoutIntentExtractor(SimpleNamespace(debug=False))._attach_paradigm_mark(
        intent, {"lines": lines}
    )
    assert intent.paradigm_mark.paradigm is PlacementParadigm.SHAPED_POCKET
    assert intent.paradigm_mark.reason == "taper"


def test_rect_explicit_right_fixed_keeps_intervals_without_right_flush():
    from babeldoc.format.pdf.document_il.utils.line_interval_plan import (
        apply_wrap_flush,
    )

    mark = select_paradigm(LayoutIntentRole.BODY, WrapMode.RIGHT_FIXED, _stable_boxes())
    assert mark.paradigm is PlacementParadigm.RECT_REFLOW
    paragraph = _marked_paragraph(mark, WrapMode.RIGHT_FIXED)
    assert effective_wrap_mode(paragraph, shape_present=True) is WrapMode.RIGHT_FIXED
    plan = resolve_line_interval_plan(paragraph, paragraph.box)
    assert plan.wrap_active is True
    assert apply_wrap_flush(paragraph, "left") == "left"
