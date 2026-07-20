"""Line-advance floor for mixed Latin/CJK (v0.6.4)."""

from __future__ import annotations

from babeldoc.format.pdf.document_il.midend.typesetting import line_advance_distance


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
