"""PR-1: drop-cap / size outliers must not dominate paragraph base style."""

from __future__ import annotations

from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
from babeldoc.format.pdf.document_il.utils.style_base import (
    calculate_base_style,
    filter_styles_for_base,
    mode_value,
)


def _st(font_id: str, size: float) -> PdfStyle:
    return PdfStyle(font_id=font_id, font_size=size, graphic_state=None)


def test_mode_value_basic():
    assert mode_value([12.0, 12.0, 35.0]) == 12.0
    assert mode_value([]) is None


def test_drop_cap_excluded_from_base_size_and_font():
    """One Trajan 35pt I + many Myriad 12.5 → base is Myriad 12.5."""
    styles = [_st("Trajan", 35.0)] + [_st("Myriad", 12.5) for _ in range(40)]
    unicodes = ["I"] + ["x"] * 40
    base = calculate_base_style(styles, char_unicodes=unicodes)
    assert base is not None
    assert base.font_id == "Myriad"
    assert abs(base.font_size - 12.5) < 0.02


def test_without_unicode_still_filters_high_size_outliers():
    styles = [_st("Trajan", 35.0)] + [_st("Myriad", 12.5) for _ in range(40)]
    base = calculate_base_style(styles)
    assert base is not None
    assert base.font_id == "Myriad"
    assert abs(base.font_size - 12.5) < 0.02


def test_uniform_large_title_not_crushed():
    """All-title 32pt run: no body mode to strip against → stays large."""
    styles = [_st("Trajan", 32.0) for _ in range(12)]
    unicodes = list("CHAPTER THREE")
    base = calculate_base_style(
        styles, layout_label="title", char_unicodes=unicodes
    )
    assert base is not None
    assert abs(base.font_size - 32.0) < 0.02
    assert base.font_id == "Trajan"


def test_title_protects_multi_glyph_large_when_median_large():
    """title label: multi-char large runs kept; single-letter drop-cap still out."""
    # 20 @ 15pt body + 1 drop 40pt letter + 5 @ 28pt multi-char title tokens
    styles = (
        [_st("Body", 15.0) for _ in range(20)]
        + [_st("Drop", 40.0)]
        + [_st("Title", 28.0) for _ in range(5)]
    )
    unicodes = ["a"] * 20 + ["W"] + ["BE", "AN", "ACT", "ION", "MAN"]
    filtered = filter_styles_for_base(
        styles, layout_label="title", char_unicodes=unicodes
    )
    fonts = {s.font_id for s in filtered}
    assert "Drop" not in fonts
    assert "Body" in fonts
    assert "Title" in fonts


def test_too_many_outliers_aborts_filter():
    """If >15% would be removed, keep original (safety)."""
    # Half 12pt half 30pt → mode is tie-ish; many highs
    styles = [_st("A", 12.0) for _ in range(10)] + [_st("B", 30.0) for _ in range(10)]
    filtered = filter_styles_for_base(styles)
    # Should not aggressively drop half the paragraph
    assert len(filtered) == 20


def test_intersection_then_mode_on_filtered():
    styles = [_st("Myriad", 12.5) for _ in range(5)] + [_st("Myriad", 12.5)]
    styles[0] = _st("Other", 12.5)  # same size different font → intersection font None
    base = calculate_base_style(styles)
    assert base is not None
    assert base.font_id == "Myriad"
    assert abs(base.font_size - 12.5) < 0.02
