"""Line-advance floor for mixed Latin/CJK (v0.6.4)."""

from __future__ import annotations

from babeldoc.format.pdf.document_il.midend.typesetting import contour_line_skip
from babeldoc.format.pdf.document_il.midend.typesetting import contour_scale_floor
from babeldoc.format.pdf.document_il.midend.typesetting import line_advance_distance
from babeldoc.format.pdf.document_il.midend.typesetting import sentence_line_skip
from babeldoc.format.pdf.document_il.utils.layout_plan.model import ContourLevel
from babeldoc.format.pdf.document_il.utils.layout_plan.model import LineEdgeLink


class TestLineAdvanceDistance:
    def test_latin_short_glyphs_do_not_undersize_skip(self):
        # All-Latin line: mode/max glyph box ~ half a CJK em
        font_size = 10.0
        scale = 1.0
        line_skip = 1.3
        mode_height = 5.0
        max_height = 5.5
        adv = line_advance_distance(
            font_size, scale, line_skip, mode_height, max_height
        )
        # Must be at least em * line_skip, not just short glyph height
        assert adv >= font_size * scale * line_skip - 1e-9
        assert adv > mode_height * line_skip

    def test_tall_glyph_still_wins(self):
        adv = line_advance_distance(
            font_size=10.0,
            scale=1.0,
            line_skip=1.3,
            mode_height=12.0,
            max_height=20.0,
        )
        assert adv == max(10.0 * 1.3, 12.0 * 1.3, 20.0 * 1.05)

    def test_scale_scales_em_floor(self):
        full = line_advance_distance(10.0, 1.0, 1.5, 4.0, 4.0)
        half = line_advance_distance(10.0, 0.5, 1.5, 2.0, 2.0)
        assert full == 10.0 * 1.5
        assert half == 10.0 * 0.5 * 1.5


def test_sentence_skip_follows_the_source_pitch():
    edges = tuple((96.0, 300.0, 200.0 - index * 15.0) for index in range(9))
    assert sentence_line_skip(edges, 12.0) == 15.0 / 12.0
    loose = tuple((96.0, 300.0, 200.0 - index * 20.0) for index in range(4))
    assert sentence_line_skip(loose, 12.0) == 1.5
    tight = tuple((96.0, 300.0, 200.0 - index * 10.0) for index in range(4))
    assert sentence_line_skip(tight, 12.0) == 1.05
    assert sentence_line_skip(((96.0, 300.0),), 12.0) is None
    assert sentence_line_skip(edges, 0.0) is None


def test_a_contour_uses_the_sample_pitch_and_keeps_the_readable_floor():
    levels = tuple(
        ContourLevel(102.0, 400.0 - index, 200.0 - index * 15.0, "observed")
        for index in range(9)
    )
    link = LineEdgeLink("body", tuple((102.0, 400.0) for _ in levels), "left", "edge", levels)
    assert contour_line_skip(link, 12.0) == 15.0 / 12.0
    assert contour_scale_floor(0.55, pinned=True, on_contour=True) == 0.55
    assert contour_scale_floor(0.55, pinned=True, on_contour=False) == 0.35
    assert contour_scale_floor(0.55, pinned=False, on_contour=False) == 0.55
