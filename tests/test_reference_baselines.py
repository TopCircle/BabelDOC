"""Source char.box.y baselines drive typesetting y when snap is on."""

from __future__ import annotations

from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import Cropbox
from babeldoc.format.pdf.document_il.il_version_1 import Page
from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter
from babeldoc.format.pdf.document_il.il_version_1 import PdfLine
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraphComposition
from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
from babeldoc.format.pdf.document_il.il_version_1 import ReferenceMetrics
from babeldoc.format.pdf.document_il.il_version_1 import VisualBbox
from babeldoc.format.pdf.document_il.midend.typesetting import Typesetting
from babeldoc.format.pdf.document_il.midend.typesetting import TypesettingUnit
from babeldoc.format.pdf.document_il.midend.typesetting import line_advance_distance
from babeldoc.format.pdf.document_il.utils.layout_helper import (
    compute_reference_metrics,
)
from babeldoc.format.pdf.document_il.utils.vertical_gap import enforce_title_body_gaps
from babeldoc.format.pdf.translation_config import TranslationConfig
from babeldoc.translator.fixed_map_translator import FixedMapTranslator


def _typesetting() -> Typesetting:
    cfg = TranslationConfig(
        translator=FixedMapTranslator(),
        input_file="baselines.pdf",
        lang_in="en",
        lang_out="zh-CN",
        doc_layout_model=MagicMock(),
        auto_extract_glossary=False,
    )
    return Typesetting(cfg)


def _style(size: float) -> PdfStyle:
    return PdfStyle(font_id="base", font_size=size, graphic_state=None)


def _char(
    ch: str,
    x: float,
    y: float,
    *,
    w: float = 10.0,
    h: float = 12.0,
    size: float = 12.0,
) -> PdfCharacter:
    box = Box(x=x, y=y, x2=x + w, y2=y + h)
    return PdfCharacter(
        char_unicode=ch,
        box=box,
        visual_bbox=VisualBbox(box=Box(x=box.x, y=box.y, x2=box.x2, y2=box.y2)),
        pdf_style=_style(size),
    )


def _unit(ch: str = "中", *, width: float = 20.0, height: float = 12.0, size: float = 12.0):
    return TypesettingUnit(char=_char(ch, 0.0, 0.0, w=width, h=height, size=size))


def _metrics(**kwargs) -> ReferenceMetrics:
    base = {
        "line_count": 1,
        "avg_line_width": 200.0,
        "last_line_width": 200.0,
        "last_line_ratio": 1.0,
        "font_size": 12.0,
        "per_line_widths": [200.0],
    }
    base.update(kwargs)
    return ReferenceMetrics(**base)


def _para(box: Box, *, baselines: list[float] | None, applied: bool = False) -> PdfParagraph:
    para = PdfParagraph(
        box=box,
        pdf_style=_style(12.0),
        pdf_paragraph_composition=[],
        unicode="正文",
        first_line_indent=0.0,
        alignment="left",
    )
    para.reference_metrics = _metrics(
        per_line_baselines=baselines,
        baselines_applied=applied,
        line_count=len(baselines or []) or 1,
    )
    return para


def _place(ts, para, units, box, *, line_skip=1.50, scale=1.0):
    placed, _fit = ts._layout_typesetting_units(
        units,
        box,
        scale=scale,
        line_skip=line_skip,
        paragraph=para,
        use_english_line_break=False,
        reference_widths=[],
    )
    return placed


def _line_ys(placed) -> list[float]:
    ys: list[float] = []
    for unit in placed:
        y = unit.box.y
        if not ys or abs(y - ys[-1]) > 0.4:
            ys.append(y)
    return ys


def test_first_line_uses_baseline_when_box_top_disagrees():
    ts = _typesetting()
    box = Box(x=50, y=100, x2=400, y2=500)
    para = _para(box, baselines=[450.0])
    placed = _place(ts, para, [_unit(height=12.0)], box)
    assert placed[0].box.y == pytest.approx(450.0)
    assert placed[0].box.y != pytest.approx(500.0 - 12.0)
    assert para.reference_metrics.baselines_applied is True


def test_bottom_up_compositions_first_line_uses_largest_y():
    bottom_y, top_y = 100.0, 130.0
    bottom = []
    x = 40.0
    for ch in "底行更宽":
        bottom.append(_char(ch, x, bottom_y, w=20.0, h=10.0, size=10.0))
        x += 20.0
    top = [_char("顶", 40.0, top_y, w=20.0, h=10.0, size=10.0)]
    para = PdfParagraph(
        box=Box(x=40, y=90, x2=200, y2=160),
        pdf_style=_style(10.0),
        unicode="底行更宽顶",
        alignment="left",
        pdf_paragraph_composition=[
            PdfParagraphComposition(
                pdf_line=PdfLine(
                    box=Box(x=40, y=bottom_y, x2=x, y2=bottom_y + 10),
                    pdf_character=bottom,
                )
            ),
            PdfParagraphComposition(
                pdf_line=PdfLine(
                    box=Box(x=40, y=top_y, x2=60, y2=top_y + 10),
                    pdf_character=top,
                )
            ),
        ],
    )
    compute_reference_metrics(para)
    rm = para.reference_metrics
    assert rm.per_line_widths == pytest.approx([x - 40.0, 20.0])
    assert rm.per_line_baselines == pytest.approx([top_y, bottom_y])
    para.alignment = "left"
    ts = _typesetting()
    placed = _place(ts, para, [_unit(width=10.0, height=10.0, size=10.0)], para.box)
    assert placed[0].box.y == pytest.approx(top_y)


def test_second_line_uses_source_y_when_leading_tighter_than_skip():
    ts = _typesetting()
    box = Box(x=0, y=100, x2=60, y2=500)
    # font*1.50 = 30; source step is 8.
    para = _para(box, baselines=[400.0, 392.0])
    units = [_unit(width=20.0, height=8.0, size=20.0) for _ in range(6)]
    placed = _place(ts, para, units, box)
    ys = _line_ys(placed)
    assert len(ys) >= 2
    assert ys[0] == pytest.approx(400.0)
    assert ys[1] == pytest.approx(392.0)
    advance = line_advance_distance(20.0, 1.0, 1.50, 8.0, 8.0)
    assert advance > 8.0
    assert ys[1] != pytest.approx(400.0 - advance)


def test_line_past_source_count_uses_median_positive_step():
    ts = _typesetting()
    box = Box(x=0, y=50, x2=60, y2=500)
    para = _para(box, baselines=[400.0, 388.0, 376.0])
    units = [_unit(width=20.0, height=8.0, size=20.0) for _ in range(12)]
    placed = _place(ts, para, units, box)
    ys = _line_ys(placed)
    assert len(ys) >= 4
    assert ys[3] == pytest.approx(376.0 - 12.0)
    advance = line_advance_distance(20.0, 1.0, 1.50, 8.0, 8.0)
    assert ys[3] != pytest.approx(376.0 - advance)


def test_line_past_source_count_without_positive_step_uses_line_advance():
    ts = _typesetting()
    box = Box(x=0, y=50, x2=60, y2=500)
    para = _para(box, baselines=[400.0])
    units = [_unit(width=20.0, height=8.0, size=20.0) for _ in range(6)]
    placed = _place(ts, para, units, box)
    ys = _line_ys(placed)
    advance = line_advance_distance(20.0, 1.0, 1.50, 8.0, 8.0)
    assert len(ys) >= 2
    assert ys[1] == pytest.approx(400.0 - advance)


def _drawn(x, y, x2, y2) -> PdfParagraph:
    ch = _char("已", x, y, w=x2 - x, h=y2 - y, size=12.0)
    return PdfParagraph(
        box=Box(x=x, y=y, x2=x2, y2=y2),
        pdf_style=_style(12.0),
        pdf_paragraph_composition=[PdfParagraphComposition(pdf_character=ch)],
        unicode="已",
        render_order=0,
        xobj_id=0,
        layout_label="plain text",
    )


def test_xy_overlap_aborts_snap_even_when_height_ratio_near_3():
    """Height ratio ~3 is not same-baseline, but any x+y hit still aborts."""
    ts = _typesetting()
    box = Box(x=50, y=100, x2=250, y2=500)
    para = _para(box, baselines=[400.0])
    # Predicted first line is y=400, h=max(12, 10)=12 → y2=412.
    # Drawn h=36, ratio 3, overlaps that band in both x and y.
    drawn = _drawn(60, 388, 200, 424)
    assert (424 - 388) / 12 == pytest.approx(3.0)
    ts._current_page = Page(page_number=1, pdf_paragraph=[drawn, para])
    placed = _place(ts, para, [_unit(width=10.0, height=12.0, size=10.0)], box)
    assert placed[0].box.y == pytest.approx(500.0 - 12.0)
    assert para.reference_metrics.baselines_applied is False


def test_x_overlap_without_y_overlap_still_snaps():
    ts = _typesetting()
    box = Box(x=50, y=100, x2=250, y2=500)
    para = _para(box, baselines=[400.0])
    drawn = _drawn(60, 200, 200, 230)
    ts._current_page = Page(page_number=1, pdf_paragraph=[drawn, para])
    placed = _place(ts, para, [_unit(width=10.0, height=12.0, size=10.0)], box)
    assert placed[0].box.y == pytest.approx(400.0)
    assert para.reference_metrics.baselines_applied is True


def test_estimate_line_widths_query_y_matches_baseline():
    ts = _typesetting()
    box = Box(x=50, y=100, x2=400, y2=500)
    para = _para(box, baselines=[450.0, 438.0])
    units = [_unit(width=10.0, height=12.0, size=10.0)]
    seen: list[float] = []
    orig = ts._line_capacity_like_place

    def _spy(**kwargs):
        seen.append(kwargs["y_bottom"])
        return orig(**kwargs)

    ts._line_capacity_like_place = _spy
    ts._estimate_line_widths(
        units,
        box,
        scale=1.0,
        avg_height=12.0,
        line_skip=1.50,
        paragraph=para,
        reference_widths=[],
    )
    assert seen
    assert seen[0] == pytest.approx(450.0)
    assert seen[0] != pytest.approx(500.0 - 12.0)


def test_overlap_retypeset_uses_shrunk_box_not_source_baseline():
    ts = _typesetting()
    em = 12.0
    source_baseline = 520.0
    keep = _drawn(40, 500, 250, 560)
    keep.render_order = 0
    move_chars = [
        _char(ch, 60 + i * em, 490, w=em, h=em, size=em) for i, ch in enumerate("中中中")
    ]
    move = PdfParagraph(
        box=Box(x=50, y=400, x2=450, y2=560),
        pdf_style=_style(em),
        pdf_paragraph_composition=[
            PdfParagraphComposition(
                pdf_line=PdfLine(
                    box=Box(x=60, y=490, x2=60 + 3 * em, y2=490 + em),
                    pdf_character=move_chars,
                )
            )
        ],
        unicode="中中中",
        alignment="left",
        render_order=1,
        xobj_id=0,
        layout_label="plain text",
        optimal_scale=1.0,
    )
    move.reference_metrics = _metrics(
        per_line_baselines=[source_baseline],
        baselines_applied=True,
        font_size=em,
    )
    page = Page(
        page_number=2,
        cropbox=Cropbox(box=Box(x=0, y=0, x2=612, y2=792)),
        pdf_paragraph=[keep, move],
    )
    ts.fix_overlapping_paragraphs_post_typesetting(page)
    assert move.reference_metrics.baselines_applied is False
    assert ts._suppress_baseline_snap is False
    first = move.pdf_paragraph_composition[0].pdf_character
    assert first is not None and first.box is not None
    assert source_baseline > move.box.y2
    assert first.box.y == pytest.approx(move.box.y2 - em)
    assert first.box.y != pytest.approx(source_baseline)


def test_retypeset_failure_restores_baselines_applied():
    ts = _typesetting()
    keep = _drawn(40, 500, 250, 560)
    move_chars = [
        _char(ch, 60 + i * 12, 490, w=12, h=12, size=12) for i, ch in enumerate("中中中")
    ]
    move = PdfParagraph(
        box=Box(x=50, y=400, x2=450, y2=560),
        pdf_style=_style(12.0),
        pdf_paragraph_composition=[
            PdfParagraphComposition(
                pdf_line=PdfLine(
                    box=Box(x=60, y=490, x2=96, y2=502),
                    pdf_character=move_chars,
                )
            )
        ],
        unicode="中中中",
        render_order=1,
        xobj_id=0,
        layout_label="plain text",
        optimal_scale=1.0,
    )
    move.reference_metrics = _metrics(
        per_line_baselines=[520.0],
        baselines_applied=True,
    )
    page = Page(
        page_number=2,
        cropbox=Cropbox(box=Box(x=0, y=0, x2=612, y2=792)),
        pdf_paragraph=[keep, move],
    )

    def _boom(*_args, **_kwargs):
        raise RuntimeError("retypeset failed")

    ts.retypeset_with_precomputed_scale = _boom
    ts.fix_overlapping_paragraphs_post_typesetting(page)
    assert move.reference_metrics.baselines_applied is True
    assert ts._suppress_baseline_snap is False
    restored = move.pdf_paragraph_composition[0].pdf_line.pdf_character
    assert restored[0] is move_chars[0]


def test_title_flag_does_not_block_body_shift():
    from babeldoc.format.pdf.document_il.utils.vertical_gap import ink_box

    title_chars = [
        _char(c, 50 + i * 40, 580, w=38.0, h=50.0, size=56.0) for i, c in enumerate("标题字")
    ]
    body_chars = [
        _char(c, 100 + i * 12, 578, w=11.0, h=11.0, size=12.0)
        for i, c in enumerate("正文开始在这里足够长")
    ]
    title = PdfParagraph(
        box=Box(x=50, y=560, x2=200, y2=630),
        pdf_style=_style(56.0),
        layout_label="title",
        unicode="标题字",
        pdf_paragraph_composition=[
            PdfParagraphComposition(pdf_character=c) for c in title_chars
        ],
    )
    body = PdfParagraph(
        box=Box(x=100, y=540, x2=250, y2=590),
        pdf_style=_style(12.0),
        layout_label="plain text",
        unicode="正文开始在这里足够长",
        pdf_paragraph_composition=[
            PdfParagraphComposition(pdf_character=c) for c in body_chars
        ],
    )
    title.reference_metrics = _metrics(baselines_applied=True, per_line_baselines=[580.0])
    body.reference_metrics = _metrics(baselines_applied=False, per_line_baselines=[578.0])
    page = Page(page_number=0, pdf_paragraph=[title, body])
    assert ink_box(title) is not None and ink_box(body) is not None
    with patch(
        "babeldoc.format.pdf.document_il.utils.vertical_gap.shift_paragraph_y"
    ) as shift:
        enforce_title_body_gaps(page)
    shifted = [call.args[0] for call in shift.call_args_list]
    assert body in shifted
    assert title not in shifted


def _line_paragraph(box: Box, *, baseline: float, chars: list[PdfCharacter]) -> PdfParagraph:
    para = PdfParagraph(
        box=box,
        pdf_style=_style(12.0),
        pdf_paragraph_composition=[
            PdfParagraphComposition(
                pdf_line=PdfLine(
                    box=Box(
                        x=chars[0].box.x,
                        y=chars[0].box.y,
                        x2=chars[-1].box.x2,
                        y2=chars[0].box.y2,
                    ),
                    pdf_character=chars,
                )
            )
        ],
        unicode="中中中",
        alignment="left",
        render_order=1,
        xobj_id=0,
        layout_label="plain text",
        optimal_scale=1.0,
    )
    para.reference_metrics = _metrics(
        per_line_baselines=[baseline],
        baselines_applied=True,
        font_size=12.0,
    )
    return para


def _retypeset_page(para: PdfParagraph) -> Page:
    return Page(
        page_number=2,
        cropbox=Cropbox(box=Box(x=0, y=0, x2=612, y2=792)),
        pdf_paragraph=[para],
    )


def test_shrunk_retypeset_paragraph_places_from_box_not_baseline():
    """Post-layout shrink has no _current_page, so snap must stay off."""
    ts = _typesetting()
    em = 12.0
    source_baseline = 520.0
    chars = [
        _char(ch, 60 + i * em, 490, w=em, h=em, size=em)
        for i, ch in enumerate("中中中")
    ]
    old_box = Box(x=50, y=400, x2=450, y2=560)
    para = _line_paragraph(old_box, baseline=source_baseline, chars=chars)
    para.box = Box(x=50, y=400, x2=450, y2=499)
    assert getattr(ts, "_current_page", None) is None
    assert ts.retypeset_paragraph(para, _retypeset_page(para), previous_box=old_box)
    assert ts._suppress_baseline_snap is False
    assert para.reference_metrics.baselines_applied is False
    first = para.pdf_paragraph_composition[0].pdf_character
    assert first is not None and first.box is not None
    assert source_baseline > para.box.y2
    assert first.box.y == pytest.approx(para.box.y2 - em)
    assert first.box.y != pytest.approx(source_baseline)


def test_retypeset_paragraph_keeps_snap_when_top_does_not_move_down():
    ts = _typesetting()
    em = 12.0
    source_baseline = 520.0
    # Ink sticks out above the box. That is not a top shrink.
    chars = [
        _char(ch, 60 + i * em, 510, w=em, h=em, size=em)
        for i, ch in enumerate("中中中")
    ]
    old_box = Box(x=50, y=400, x2=450, y2=500)
    para = _line_paragraph(old_box, baseline=source_baseline, chars=chars)
    para.box = Box(x=50, y=430, x2=450, y2=500)
    assert ts.retypeset_paragraph(para, _retypeset_page(para), previous_box=old_box)
    assert ts._suppress_baseline_snap is False
    assert para.reference_metrics.baselines_applied is True
    first = para.pdf_paragraph_composition[0].pdf_character
    assert first is not None and first.box is not None
    assert first.box.y == pytest.approx(source_baseline)
    assert first.box.y != pytest.approx(para.box.y2 - em)


def test_retypeset_paragraph_failure_restores_baselines_applied():
    ts = _typesetting()
    chars = [
        _char(ch, 60 + i * 12, 490, w=12, h=12, size=12)
        for i, ch in enumerate("中中中")
    ]
    old_box = Box(x=50, y=400, x2=450, y2=560)
    para = _line_paragraph(old_box, baseline=520.0, chars=chars)
    para.box = Box(x=50, y=400, x2=450, y2=499)

    def _boom(*_args, **_kwargs):
        raise RuntimeError("retypeset failed")

    ts.retypeset_with_precomputed_scale = _boom
    assert ts.retypeset_paragraph(para, _retypeset_page(para), previous_box=old_box) is False
    assert para.reference_metrics.baselines_applied is True
    assert ts._suppress_baseline_snap is False
    restored = para.pdf_paragraph_composition[0].pdf_line.pdf_character
    assert restored[0] is chars[0]


def test_tied_font_size_advance_matches_sorted_mode():
    """A tie must not let the estimator advance on a different mode than placement."""
    ts = _typesetting()
    box = Box(x=0, y=50, x2=60, y2=500)
    para = _para(box, baselines=[400.0])
    # 20 is seen first. Both sizes occur three times, so the sorted mode is 12.
    units = [
        _unit(width=20.0, height=8.0, size=size)
        for size in (20.0, 12.0, 20.0, 12.0, 20.0, 12.0)
    ]
    assert ts._dominant_font_size([]) == pytest.approx(10.0)
    assert ts._dominant_font_size(units) == pytest.approx(12.0)
    placed = _place(ts, para, units, box)
    ys = _line_ys(placed)
    advance = line_advance_distance(12.0, 1.0, 1.50, 8.0, 8.0)
    other = line_advance_distance(20.0, 1.0, 1.50, 8.0, 8.0)
    assert advance != pytest.approx(other)
    assert len(ys) >= 2
    assert ys[1] == pytest.approx(400.0 - advance)
    assert ys[1] != pytest.approx(400.0 - other)

    seen: list[float] = []
    orig = ts._line_capacity_like_place

    def _spy(**kwargs):
        seen.append(kwargs["y_bottom"])
        return orig(**kwargs)

    ts._line_capacity_like_place = _spy
    ts._estimate_line_widths(
        units,
        box,
        scale=1.0,
        avg_height=8.0,
        line_skip=1.50,
        paragraph=para,
        reference_widths=[],
    )
    assert len(seen) >= 2
    assert seen[1] == pytest.approx(400.0 - advance)


def test_body_baseline_flag_skips_shift():
    title_chars = [
        _char(c, 50 + i * 40, 580, w=38.0, h=50.0, size=56.0) for i, c in enumerate("标题字")
    ]
    body_chars = [
        _char(c, 100 + i * 12, 578, w=11.0, h=11.0, size=12.0)
        for i, c in enumerate("正文开始在这里足够长")
    ]
    title = PdfParagraph(
        box=Box(x=50, y=560, x2=200, y2=630),
        pdf_style=_style(56.0),
        layout_label="title",
        unicode="标题字",
        pdf_paragraph_composition=[
            PdfParagraphComposition(pdf_character=c) for c in title_chars
        ],
    )
    body = PdfParagraph(
        box=Box(x=100, y=540, x2=250, y2=590),
        pdf_style=_style(12.0),
        layout_label="plain text",
        unicode="正文开始在这里足够长",
        pdf_paragraph_composition=[
            PdfParagraphComposition(pdf_character=c) for c in body_chars
        ],
    )
    title.reference_metrics = _metrics(baselines_applied=False)
    body.reference_metrics = _metrics(baselines_applied=True, per_line_baselines=[578.0])
    page = Page(page_number=0, pdf_paragraph=[title, body])
    y0 = body_chars[0].box.y
    with patch(
        "babeldoc.format.pdf.document_il.utils.vertical_gap.shift_paragraph_y"
    ) as shift:
        enforce_title_body_gaps(page)
    assert shift.call_count == 0
    assert body_chars[0].box.y == y0
