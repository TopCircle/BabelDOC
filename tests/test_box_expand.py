"""Shared box expansion policy (narrow column / OCR down-first)."""

from __future__ import annotations

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.utils.box_expand import (
    NARROW_COLUMN_MAX_WIDTH,
    content_expand_ratio_need,
    expand_axis_order,
    is_narrow_column,
    is_right_blocked,
    prefer_expand_down,
    try_expand_axis,
    try_expand_down,
    try_expand_right,
    try_pre_expand_for_content,
)


def _box(x=100.0, y=100.0, x2=200.0, y2=200.0) -> Box:
    return Box(x=x, y=y, x2=x2, y2=y2)


def test_is_narrow_column_threshold():
    assert is_narrow_column(_box(x=0, x2=NARROW_COLUMN_MAX_WIDTH - 1))
    assert not is_narrow_column(_box(x=0, x2=NARROW_COLUMN_MAX_WIDTH))
    assert not is_narrow_column(_box(x=0, x2=300))


def test_prefer_expand_down_ocr():
    assert prefer_expand_down(
        _box(), ocr_mode=True, get_max_right=lambda b: 999
    )


def test_prefer_expand_down_narrow_right_blocked():
    narrow = _box(x=102, x2=207, y=78, y2=168)  # w=105
    assert prefer_expand_down(
        narrow, ocr_mode=False, get_max_right=lambda b: b.x2  # blocked
    )
    assert not prefer_expand_down(
        narrow, ocr_mode=False, get_max_right=lambda b: 500  # room
    )


def test_prefer_expand_down_wide_even_if_right_blocked():
    wide = _box(x=50, x2=500)
    assert not prefer_expand_down(
        wide, ocr_mode=False, get_max_right=lambda b: b.x2
    )


def test_expand_axis_order():
    assert expand_axis_order(prefer_down=True) == ("down", "right")
    assert expand_axis_order(prefer_down=False) == ("right", "down")


def test_try_expand_right_and_down():
    box = _box(x=100, y=100, x2=200, y2=200)
    right = try_expand_right(box, lambda b: 400)
    assert right is not None and right.x2 == 395  # 400 - 5
    assert try_expand_right(box, lambda b: b.x2) is None

    down = try_expand_down(box, lambda b: 40)
    assert down is not None and down.y == 42  # 40 + 2
    assert try_expand_down(box, lambda b: b.y) is None


def test_try_expand_axis_dispatches():
    box = _box()
    r = try_expand_axis(
        box,
        "right",
        get_max_right=lambda b: 500,
        get_max_bottom=lambda b: 10,
    )
    assert r is not None and r.x2 > box.x2
    d = try_expand_axis(
        box,
        "down",
        get_max_right=lambda b: b.x2,
        get_max_bottom=lambda b: 10,
    )
    assert d is not None and d.y < box.y


def test_is_right_blocked():
    box = _box(x2=200)
    assert is_right_blocked(box, lambda b: b.x2)
    assert not is_right_blocked(box, lambda b: 400)


def test_content_ratio_need():
    narrow = _box(x=0, x2=100)
    wide = _box(x=0, x2=400)
    assert content_expand_ratio_need("short title", "title", wide) == 1.15
    assert content_expand_ratio_need("x" * 80, "plain text", narrow) == 1.2
    assert content_expand_ratio_need("x" * 80, "plain text", wide) == 1.5


def test_try_pre_expand_right_then_down():
    narrow = _box(x=102, y=78, x2=207, y2=168)
    # Right room wins
    out = try_pre_expand_for_content(
        narrow,
        content_w=400,
        text="body " * 20,
        layout_label="plain text",
        get_max_right=lambda b: 400,
        get_max_bottom=lambda b: 40,
    )
    assert out is not None and out.x2 > narrow.x2

    # Right blocked → down
    out2 = try_pre_expand_for_content(
        narrow,
        content_w=400,
        text="body " * 20,
        layout_label="plain text",
        get_max_right=lambda b: b.x2,
        get_max_bottom=lambda b: 40,
    )
    assert out2 is not None and out2.y == 42


def test_try_pre_expand_skips_when_content_fits():
    box = _box(x=0, x2=300)
    assert (
        try_pre_expand_for_content(
            box,
            content_w=100,
            text="hi",
            layout_label=None,
            get_max_right=lambda b: 500,
            get_max_bottom=lambda b: 0,
        )
        is None
    )
