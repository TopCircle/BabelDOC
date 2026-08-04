"""Unit tests for P1 dual ink-gap acceptance helper."""

from __future__ import annotations

from babeldoc.tools.p1_ink_gap_accept import find_title_body_gap
from babeldoc.tools.p1_ink_gap_accept import score_page


class _FakePage:
    def __init__(self, width: float, blocks: list):
        self.rect = type("R", (), {"width": width, "height": 792.0})()
        self._blocks = blocks

    def get_text(self, mode: str):
        assert mode == "dict"
        return {"blocks": self._blocks}


def _span(text: str, size: float, x0: float, y0: float, x1: float, y1: float):
    return {
        "type": 0,
        "lines": [
            {
                "spans": [
                    {
                        "text": text,
                        "size": size,
                        "bbox": [x0, y0, x1, y1],
                    }
                ]
            }
        ],
    }


def test_find_title_body_gap_visual_y_down():
    spans = [
        {
            "text": "Big Title",
            "size": 40.0,
            "bbox": [10, 100, 200, 150],
            "y0": 100,
            "y1": 150,
            "x0": 10,
            "x1": 200,
        },
        {
            "text": "Body text here",
            "size": 12.0,
            "bbox": [10, 170, 300, 190],
            "y0": 170,
            "y1": 190,
            "x0": 10,
            "x1": 300,
        },
    ]
    g = find_title_body_gap(spans)
    assert g is not None
    assert abs(g.gap_pt - 20.0) < 0.01
    assert "Big" in g.title_text


def test_score_page_pass_and_fail():
    # Dual: left ZH mid=612, right EN. Title+body both sides.
    # ZH gap 10, EN gap 25 → deficit large → fail (and likely clamped if >24)
    blocks = [
        _span("ZH标题", 40, 50, 100, 200, 150),
        _span("中文正文段落", 12, 50, 160, 400, 180),  # gap 10
        _span("EN Title", 40, 650, 100, 900, 150),
        _span("English body paragraph", 12, 650, 175, 1100, 195),  # gap 25
    ]
    page = _FakePage(1224.0, blocks)
    r = score_page(page, 1, eps=2.0, max_jump=24.0)
    assert r.zh_gap == 10.0
    assert r.en_gap == 25.0
    assert r.pass_eps is False
    assert r.deficit is not None and abs(r.deficit - 13.0) < 0.01  # 25-2-10
    assert r.likely_clamped is False  # 13 ≤ 24 → fail_short, not clamp-limited
    assert r.note == "fail_short"
    # en gap 50 → deficit 38 > 24 → clamp-limited
    blocks2 = [
        _span("ZH标题", 40, 50, 100, 200, 150),
        _span("中文正文段落", 12, 50, 160, 400, 180),
        _span("EN Title", 40, 650, 100, 900, 150),
        _span("English body paragraph", 12, 650, 200, 1100, 220),  # gap 50
    ]
    r2 = score_page(_FakePage(1224.0, blocks2), 2, eps=2.0, max_jump=24.0)
    assert r2.pass_eps is False
    assert r2.likely_clamped is True
    assert r2.note == "fail_clamped"

    # matched gaps within eps
    blocks3 = [
        _span("ZH标题", 40, 50, 100, 200, 150),
        _span("中文正文段落", 12, 50, 174, 400, 190),  # gap 24
        _span("EN Title", 40, 650, 100, 900, 150),
        _span("English body", 12, 650, 175, 1100, 195),  # gap 25
    ]
    r3 = score_page(_FakePage(1224.0, blocks3), 3, eps=2.0)
    assert r3.pass_eps is True
    assert r3.note == "pass"
