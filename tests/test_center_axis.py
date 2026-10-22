"""A narrow display column folds around one axis. The fill keeps each line."""

from __future__ import annotations

import pytest
from babeldoc.format.pdf.document_il.utils.layout_plan.compose import build_plan
from babeldoc.format.pdf.document_il.utils.layout_plan.facts import SourceBlock
from babeldoc.format.pdf.document_il.utils.layout_plan.facts import build_facts
from babeldoc.format.pdf.document_il.utils.layout_plan.line_edges import (
    assign_line_edge_boxes,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.measure import measure_region
from babeldoc.format.pdf.document_il.utils.layout_plan.model import LineBox
from babeldoc.format.pdf.document_il.utils.layout_plan.model import Region
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms import load_catalog
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms import load_modules
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.center.axis import (
    claim,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.center.axis import fill
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.contract import (
    BlockEdges,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.contract import (
    Paradigm,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.contract import pick
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.contract import (
    stand_down,
)

# Both edges move, pitch is 25, the union is about 150pt, centers stay near 131.
_AXIS = [
    [70.0, 190.0, 500.0],
    [55.0, 200.0, 475.0],
    [80.0, 185.0, 450.0],
    [60.0, 205.0, 425.0],
    [90.0, 175.0, 400.0],
    [65.0, 195.0, 375.0],
]


def _edges(full_count, left_range, right_range, marker="none"):
    return BlockEdges(
        full_count=full_count,
        left_range=left_range,
        right_range=right_range,
        left_monotone=1.0,
        right_monotone=1.0,
        marker=marker,
    )


def _measured(lines):
    region = Region("m", 0, 0, None, tuple(LineBox(*line) for line in lines))
    measured = measure_region(region)
    return _edges(
        measured.full_count,
        measured.left_range,
        measured.right_range,
        measured.marker,
    )


def _facts(lines):
    return build_facts(
        source_fingerprint="synthetic",
        page_index=0,
        page_width=612.0,
        page_height=792.0,
        input_gate="single_page",
        text_health=0.9,
        blocks=[SourceBlock(lines=tuple(LineBox(*line) for line in lines))],
    )


def _winner(edges, lines):
    results = stand_down(
        tuple(
            (path, module.claim(edges, lines), module.THRESHOLD)
            for path, module in load_modules()
        )
    )
    return pick(results), results


def test_a_folded_display_column_matches_only_the_axis():
    edges = _edges(6, 35.0, 30.0)
    (status, paradigm, residual), results = _winner(edges, _AXIS)
    assert claim(edges, _AXIS) == residual
    assert residual < 24.0
    assert status == "matched"
    assert paradigm == "center/axis"
    matched = [
        path
        for path, score, threshold in results
        if score is not None and score < threshold
    ]
    assert matched == ["center/axis"]


def test_the_fill_keeps_each_scanned_line():
    pairs = fill(_AXIS)
    assert [edge[0] for edge in pairs] == pytest.approx(
        [line[0] for line in _AXIS]
    )
    assert [edge[1] for edge in pairs] == pytest.approx(
        [line[1] for line in _AXIS]
    )
    assert [edge[2] for edge in pairs] == [line[2] for line in _AXIS]
    plan = build_plan(_facts(_AXIS))
    assert len(plan.line_edge_links) == 1
    link = plan.line_edge_links[0]
    assert link.edges == pairs
    assert link.alignment == "right"
    assert link.to_dict()["alignment"] == "right"
    assert [level.top for level in link.levels] == [line[2] for line in _AXIS]
    assert [level.kind for level in link.levels] == ["observed"] * len(_AXIS)

    class _Box:
        def __init__(self):
            self.x = 0.0
            self.x2 = 1.0

    class _Paragraph:
        def __init__(self):
            self.layout_region_id = link.region_id
            self.box = _Box()
            self.alignment = "left"
            self.first_line_indent = 12.0

    page = type("_Page", (), {})()
    page.layout_plan = plan
    page.pdf_paragraph = [_Paragraph()]
    assign_line_edge_boxes(page)
    assert page.pdf_paragraph[0].alignment == "right"
    assert page.pdf_paragraph[0].box.x == pytest.approx(min(line[0] for line in _AXIS))
    assert page.pdf_paragraph[0].box.x2 == pytest.approx(max(line[1] for line in _AXIS))
    assert page.pdf_paragraph[0].first_line_indent == 0


def test_body_fills_stay_left_aligned():
    catalog = {item.name: item for item in load_catalog()}
    assert catalog["center/axis"].alignment == "right"
    for name, item in catalog.items():
        if name == "center/axis":
            continue
        assert item.alignment == "left"
    with pytest.raises(ValueError):
        Paradigm("custom/bad", 8.0, lambda _edges, _lines: None, alignment="justify")


def test_a_centered_contour_stays_centered_and_a_left_frame_meets_the_edge():
    from babeldoc.format.pdf.document_il.midend.typesetting import Typesetting

    setter = Typesetting.__new__(Typesetting)
    setter._pocket_link = None
    setter._line_edges = type("_Link", (), {"alignment": "center"})()
    assert setter._alignment_in_frame("center") == "center"
    assert setter._alignment_in_frame("center", last=True) == "center"
    assert setter._centered_contour() is True
    setter._line_edges = None
    assert setter._alignment_in_frame("center") == "center"
    assert setter._centered_contour() is False
    setter._line_edges = type("_Link", (), {"alignment": "right"})()
    assert setter._alignment_in_frame("right") == "right"
    assert setter._alignment_in_frame("right", last=True) == "right"
    setter._line_edges = type("_Link", (), {"alignment": "left"})()
    assert setter._alignment_in_frame("left") == "justify"
    assert setter._alignment_in_frame("left", last=True) == "left"
    assert setter._centered_contour() is False


def test_the_width_is_the_contour_at_that_height():
    from babeldoc.format.pdf.document_il.utils.layout_plan.line_edges import (
        interval_for_line_edges,
    )
    from babeldoc.format.pdf.document_il.utils.layout_plan.model import LineEdgeLink

    link = LineEdgeLink("quote", fill(_PAGE_22), "right")
    # Each height keeps that English line.
    assert interval_for_line_edges(link, 0, 440.0, 453.0) == pytest.approx(
        (424.0, 507.138)
    )
    assert interval_for_line_edges(link, 0, 290.0, 303.0) == pytest.approx(
        (417.004, 551.578)
    )
    # A band across two slabs stays inside their overlap.
    assert interval_for_line_edges(link, 0, 300.0, 310.0) == pytest.approx(
        (417.004, 520.932)
    )
    # These edges have no height. The old assertion still returned the
    # second English edge for a query at y 0–10, which is index 1, not
    # that height. Without a sample there is nothing to place.
    plain = LineEdgeLink("body", ((10.0, 100.0), (20.0, 90.0)), "left")
    assert interval_for_line_edges(plain, 1, 0.0, 10.0) is None
    assert interval_for_line_edges(plain, 0, 0.0, 10.0) is None


def test_a_pinned_rag_and_a_light_column_stay_out():
    rag = [
        [100.0, 400.0, 500.0],
        [100.0, 250.0, 475.0],
        [100.0, 390.0, 450.0],
        [100.0, 310.0, 425.0],
        [100.0, 280.0, 400.0],
        [100.0, 360.0, 375.0],
    ]
    assert claim(_edges(6, 6.0, 150.0), rag) is None
    (status, paradigm, _residual), _results = _winner(_edges(6, 6.0, 150.0), rag)
    assert paradigm == "rag/deep_right"
    assert status == "matched"

    light = [[100.0, 250.0, 400.0 - index * 25.0] for index in range(6)]
    light[2] = [112.0, 230.0, light[2][2]]
    assert claim(_edges(6, 12.0, 20.0), light) is None
    (status, paradigm, residual), _results = _winner(_edges(6, 12.0, 20.0), light)
    assert paradigm == "rect/light_column"
    assert status == "matched"
    assert residual < 16.0


def test_body_pitch_a_narrow_ornament_and_an_opening_trapezoid_stay_out():
    body = [[line[0], line[1], 500.0 - index * 15.0] for index, line in enumerate(_AXIS)]
    assert claim(_edges(6, 35.0, 30.0), body) is None

    ornament = [
        [100.0, 117.4, 500.0 - index * 25.0] for index in range(4)
    ]
    assert claim(_edges(4, 0.0, 0.0), ornament) is None

    opening = [
        [200.0 - index * 8.0, 300.0 + index * 8.0, 500.0 - index * 25.0]
        for index in range(6)
    ]
    assert claim(_edges(6, 40.0, 40.0), opening) is None
    (status, paradigm, _residual), _results = _winner(_edges(6, 40.0, 40.0), opening)
    assert status == "matched"
    assert paradigm == "both/wider_below"


def test_a_loose_axis_stays_unmatched():
    loose = [
        [40.0, 180.0, 500.0],
        [80.0, 200.0, 475.0],
        [20.0, 160.0, 450.0],
        [70.0, 190.0, 425.0],
        [30.0, 170.0, 400.0],
        [60.0, 200.0, 375.0],
    ]
    residual = claim(_edges(6, 60.0, 40.0), loose)
    assert residual == 30.0
    (status, paradigm, _residual), _results = _winner(_edges(6, 60.0, 40.0), loose)
    assert status == "unmatched"
    assert paradigm == ""


# Erotic Massage printed pages. Coordinates are the source line boxes.
_PAGE_72 = [
    [60.9338, 188.4018, 490.9480],
    [78.0938, 191.3938, 465.9560],
    [75.9158, 197.3998, 440.9640],
    [84.0118, 201.4038, 415.9720],
    [106.7378, 205.4078, 390.9800],
    [77.6978, 207.4098, 365.9880],
    [99.2138, 207.4098, 340.9960],
    [83.0438, 206.4198, 316.0040],
    [60.2738, 203.4278, 291.0119],
    [74.0018, 199.4238, 266.0200],
    [92.8778, 193.4178, 241.0280],
    [55.8298, 182.0218, 216.0360],
]
_PAGE_22 = [
    [424.0000, 507.1380, 453.4480],
    [421.9980, 525.0460, 428.4560],
    [417.9940, 525.7941, 403.4640],
    [415.0020, 547.5740, 378.4720],
    [414.0120, 523.4400, 353.4800],
    [415.0020, 520.9320, 328.4880],
    [417.0040, 551.5780, 303.4960],
    [419.9960, 518.9301, 278.5040],
    [424.9900, 531.9979, 253.5120],
]
_PAGE_15 = [
    [419.0000, 519.4080, 428.4480],
    [418.0100, 542.1121, 403.4560],
    [415.0180, 536.8760, 378.4640],
    [414.0280, 544.0920, 353.4720],
    [415.0180, 558.9420, 328.4800],
    [417.0200, 566.6420, 303.4880],
    [420.0120, 563.2761, 278.4960],
]
_PAGE_43 = [
    [89.5418, 202.4018, 428.4480],
    [62.4378, 203.3918, 403.4560],
    [84.1078, 206.3838, 378.4640],
    [48.4458, 207.3958, 353.4720],
    [87.5618, 206.4058, 328.4800],
    [65.1218, 204.4038, 303.4880],
    [50.0738, 201.4118, 278.4960],
]


def test_massage_quotes_match_the_axis_and_the_rags_stay_rags():
    for lines, expected in ((_PAGE_72, 20.7075), (_PAGE_22, 12.3970)):
        edges = _measured(lines)
        (status, paradigm, residual), results = _winner(edges, lines)
        assert claim(edges, lines) == pytest.approx(expected, abs=0.01)
        assert status == "matched"
        assert paradigm == "center/axis"
        assert residual == pytest.approx(expected, abs=0.01)
        matched = [
            path
            for path, score, threshold in results
            if score is not None and score < threshold
        ]
        assert matched == ["center/axis"]
        contour = fill(lines)
        assert [edge[0] for edge in contour] == pytest.approx(
            [line[0] for line in lines]
        )
        assert [edge[1] for edge in contour] == pytest.approx(
            [line[1] for line in lines]
        )

    for lines, name in ((_PAGE_15, "rag/right_edge"), (_PAGE_43, "rag/left_edge")):
        edges = _measured(lines)
        assert claim(edges, lines) is None
        (status, paradigm, _residual), _results = _winner(edges, lines)
        assert status == "matched"
        assert paradigm == name


class _Glyph:
    def __init__(self, text="字"):
        self.width = 22.0
        self.is_cjk_char = True
        self.is_space = False
        self.can_break_line = True
        self.is_hung_punctuation = False
        self.is_cannot_appear_in_line_end_punctuation = False
        self.mixed_character_blacklist = False
        self._text = text

    def try_get_unicode(self):
        return self._text


def _line_counts(breaks, count):
    points = [0, *(breaks or []), count]
    return [points[index + 1] - points[index] for index in range(len(points) - 1)]


def test_centered_breaks_share_the_column():
    from babeldoc.format.pdf.document_il.midend.line_break_optimizer import (
        centered_line_breaks,
    )

    # A shared column. One wide step must not take the long line.
    widths = [
        83.138,
        103.048,
        107.8,
        109.428,
        109.428,
        109.428,
        105.93,
        107.008,
        107.008,
    ]
    units = [_Glyph() for _ in range(31)]
    shared = centered_line_breaks(units, widths, 18.7 / 22.0)
    assert _line_counts(shared, 31) == [4, 5, 5, 5, 4, 4, 4]
    opened = centered_line_breaks(units, widths, 1.0)
    assert _line_counts(opened, 31) == [3, 4, 4, 4, 4, 4, 4, 4]


def test_a_word_slides_the_break_and_the_tail_stays_a_line():
    """「减少」cannot end on 减. The tail must not become 「扰。」."""
    from babeldoc.format.pdf.document_il.midend.line_break_optimizer import (
        centered_line_breaks,
    )
    from babeldoc.format.pdf.document_il.utils.cjk_dict import is_cjk_three_char_word
    from babeldoc.format.pdf.document_il.utils.cjk_dict import is_cjk_two_char_word
    from babeldoc.format.pdf.document_il.utils.cjk_kinsoku import (
        is_cjk_line_start_forbidden,
    )

    text = "一定要减少任何可能使你和伴侣无法拥有放松和感官撩人环境的干扰。"
    units = [_Glyph(char) for char in text]
    for index in range(1, len(text)):
        pair = text[index - 1 : index + 1]
        if is_cjk_two_char_word(pair) or is_cjk_line_start_forbidden(text[index]):
            units[index - 1].can_break_line = False
        if index >= 2 and is_cjk_three_char_word(text[index - 2 : index + 1]):
            units[index - 2].can_break_line = False
            units[index - 1].can_break_line = False
    # Live page-22 slabs at scale 0.8, after the column arc is smoothed.
    widths = [81.4, 100.9, 105.3, 106.5, 106.5, 105.6, 105.6]
    breaks = centered_line_breaks(units, widths, 0.8)
    counts = _line_counts(breaks, len(text))
    assert counts == [3, 4, 4, 5, 5, 6, 4]
    cursor = 0
    for count, slab in zip(counts, widths, strict=False):
        assert count * 22.0 * 0.8 <= slab + 0.05
        if cursor + count < len(text):
            assert units[cursor + count - 1].can_break_line
        cursor += count


def test_a_marker_and_a_short_block_stay_out():
    assert claim(_edges(6, 35.0, 30.0, marker="bullet"), _AXIS) is None
    assert claim(_edges(3, 35.0, 30.0), _AXIS[:3]) is None
    assert claim(_edges(6, 35.0, 30.0), [line[:2] for line in _AXIS]) is None
