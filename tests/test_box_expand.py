"""Shared box expansion policy (narrow column / OCR down-first)."""

from __future__ import annotations

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.utils.box_expand import NARROW_COLUMN_MAX_WIDTH
from babeldoc.format.pdf.document_il.utils.box_expand import content_expand_ratio_need
from babeldoc.format.pdf.document_il.utils.box_expand import expand_axis_order
from babeldoc.format.pdf.document_il.utils.box_expand import is_left_gutter_bar
from babeldoc.format.pdf.document_il.utils.box_expand import is_narrow_column
from babeldoc.format.pdf.document_il.utils.box_expand import is_right_blocked
from babeldoc.format.pdf.document_il.utils.box_expand import prefer_expand_down
from babeldoc.format.pdf.document_il.utils.box_expand import try_expand_axis
from babeldoc.format.pdf.document_il.utils.box_expand import try_expand_down
from babeldoc.format.pdf.document_il.utils.box_expand import try_expand_right
from babeldoc.format.pdf.document_il.utils.box_expand import try_pre_expand_for_content


def _box(x=100.0, y=100.0, x2=200.0, y2=200.0) -> Box:
    return Box(x=x, y=y, x2=x2, y2=y2)


def test_is_narrow_column_threshold():
    from babeldoc.format.pdf.document_il.utils.box_expand import RATIO_ULTRA_NARROW
    from babeldoc.format.pdf.document_il.utils.box_expand import (
        ULTRA_NARROW_COLUMN_MAX_WIDTH,
    )
    from babeldoc.format.pdf.document_il.utils.box_expand import is_ultra_narrow_column

    assert is_narrow_column(_box(x=0, x2=NARROW_COLUMN_MAX_WIDTH - 1))
    assert not is_narrow_column(_box(x=0, x2=NARROW_COLUMN_MAX_WIDTH))
    assert not is_narrow_column(_box(x=0, x2=300))
    assert is_ultra_narrow_column(_box(x=429, x2=509))  # 80pt OA p8
    assert not is_ultra_narrow_column(
        _box(x=0, x2=ULTRA_NARROW_COLUMN_MAX_WIDTH)
    )
    assert content_expand_ratio_need("long zh text", "plain text", _box(x=429, x2=509)) == (
        RATIO_ULTRA_NARROW
    )


def test_ultra_narrow_prefer_down_and_pre_expand():
    """PR-D: ultra-narrow prefer down-first even if a few pt free on right."""
    from babeldoc.format.pdf.document_il.utils.box_expand import (
        try_pre_expand_for_content,
    )

    narrow = _box(x=429, y=361, x2=509, y2=481)  # 80×120
    assert prefer_expand_down(
        narrow, ocr_mode=False, get_max_right=lambda b: b.x2 + 8
    )
    # content slightly over box width → expand down when bottom free
    expanded = try_pre_expand_for_content(
        narrow,
        content_w=90.0,  # > 80 * 1.05
        text="x" * 40,
        layout_label="plain text",
        get_max_right=lambda b: b.x2,  # blocked right
        get_max_bottom=lambda b: 200.0,  # free below
    )
    assert expanded is not None
    assert expanded.y < narrow.y


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


def test_callout_left_expand_capped_not_page_wide():
    """Right-side callout must not left-expand to page margin (0.6.4.48 dual)."""
    from babeldoc.format.pdf.document_il.utils.box_expand import try_expand_left

    # OA-like tip on the right over a figure
    box = _box(x=420, y=200, x2=500, y2=320)  # 80pt
    # get_max_left claims free all the way to page margin
    out = try_expand_left(
        box,
        lambda b: 40.0,
        need_width=150.0,
        max_expand=100.0,
    )
    assert out is not None
    # need 150 → desired x = 500-150 = 350; cap at 420-100 = 320 → max(40, 320, 350) = 350
    assert out.x == 350.0
    assert out.x2 == 500.0
    # Must not reach page-left free edge
    assert out.x > 100.0


def test_medium_width_left_body_not_force_callout_left():
    """Short left body line (width<230) must not force left expand path."""
    # 200pt wide body fragment on the left — right has room
    box = _box(x=50, y=400, x2=250, y2=420)
    out = try_pre_expand_for_content(
        box,
        content_w=280.0,  # slightly over
        text="short body",
        layout_label="plain text",
        get_max_right=lambda b: 500,
        get_max_bottom=lambda b: 40,
        get_max_left=lambda b: 10.0,
    )
    # Should expand right, not jump left to margin
    assert out is not None
    assert out.x == box.x
    assert out.x2 > box.x2


def test_left_gutter_callout_expands_down_not_off_bar():
    """OA p91 red bar (x≈54, ~157pt): do not left-expand off the painted box."""
    bar = _box(x=54.18, y=375.99, x2=211.635, y2=450.99)
    out = try_pre_expand_for_content(
        bar,
        content_w=400.0,
        text="这本书主要是教你新技巧" * 3,
        layout_label="plain text",
        get_max_right=lambda b: 102.0,  # body column blocks right
        get_max_bottom=lambda b: 348.0,
        get_max_left=lambda b: 5.0,
    )
    assert out is not None
    assert out.x == bar.x
    assert out.y < bar.y
    assert out.x2 == bar.x2


def test_left_gutter_callout_does_not_right_expand_into_wrap():
    """OA p91: body wrap ink at x≈246 must not pull the red bar right.

    get_max_right often returns the wrap column left edge. Right-expanding
    the callout into that gap paints CJK over the carved body residual while
    the exclusion zone still tracks design_box (~223).
    """
    bar = _box(x=54.18, y=375.99, x2=211.635, y2=450.99)
    out = try_pre_expand_for_content(
        bar,
        content_w=400.0,
        text="这本书主要是教你新技巧" * 3,
        layout_label="plain text",
        get_max_right=lambda b: 246.0,  # EN wrap left looks "free"
        get_max_bottom=lambda b: 348.0,
        get_max_left=lambda b: 5.0,
    )
    assert out is not None
    assert out.x == bar.x
    assert out.x2 == bar.x2  # deepen only — never widen into wrap
    assert out.y < bar.y


def test_left_gutter_prefers_expand_down():
    """OA p91: wrap ink at x≈246 must not make mid-loop choose right first."""
    bar = _box(x=54.18, y=375.99, x2=211.635, y2=450.99)
    assert is_left_gutter_bar(bar)
    assert prefer_expand_down(
        bar, ocr_mode=False, get_max_right=lambda b: 246.0
    )
    assert expand_axis_order(prefer_down=True)[0] == "down"
