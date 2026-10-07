"""Placement paradigm selection from role and line geometry."""

from __future__ import annotations

from babeldoc.format.pdf.document_il.utils.layout_intent import LayoutIntentRole
from babeldoc.format.pdf.document_il.utils.layout_intent import WrapMode
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


def test_no_lines_is_low_confidence_rect():
    mark = select_paradigm(LayoutIntentRole.BODY, None, [])
    assert mark.paradigm is PlacementParadigm.RECT_REFLOW
    assert mark.confidence == 0.4
    assert mark.reason == "no_lines"
