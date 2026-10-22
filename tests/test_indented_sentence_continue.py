"""A sentence split beside a figure continues on the open line."""

from __future__ import annotations

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import Page
from babeldoc.format.pdf.document_il.il_version_1 import PdfFigure
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraphComposition
from babeldoc.format.pdf.document_il.il_version_1 import PdfSameStyleUnicodeCharacters
from babeldoc.format.pdf.document_il.il_version_1 import ReferenceMetrics
from babeldoc.format.pdf.document_il.utils.indented_sentence_continue import (
    continue_indented_sentences,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.model import LayoutPlan
from babeldoc.format.pdf.document_il.utils.layout_plan.model import LineEdgeLink

_EM = 10.0


def _glyphs(paragraph):
    text = paragraph.pdf_paragraph_composition[0].pdf_same_style_unicode_characters.unicode
    return [(char, _EM) for char in text]


def _para(text: str, *, x: float, y: float, x2: float, y2: float) -> PdfParagraph:
    return PdfParagraph(
        box=Box(x=x, y=y, x2=x2, y2=y2),
        unicode=text,
        pdf_paragraph_composition=[
            PdfParagraphComposition(
                pdf_same_style_unicode_characters=PdfSameStyleUnicodeCharacters(
                    unicode=text,
                ),
            ),
        ],
    )


def _page(*paragraphs, figure=True) -> Page:
    figures = []
    if figure:
        figures.append(PdfFigure(box=Box(x=0, y=337, x2=210, y2=472)))
    return Page(page_number=0, pdf_paragraph=list(paragraphs), pdf_figure=figures)


def _pair(upper_text: str, lower_text: str):
    # 10em measure. Fifteen glyphs use two lines; five fit on the open line.
    # The lower left sits just past the figure at x=210.
    upper = _para(upper_text, x=102, y=488, x2=202, y2=518)
    lower = _para(lower_text, x=200, y=443, x2=202, y2=488)
    return upper, lower


def test_the_open_line_takes_the_words_that_fit():
    upper, lower = _pair("然后将双手移到这里还差五个字啊", "在她的上腿顶部然后向下")
    page = _page(upper, lower)
    assert continue_indented_sentences(page, _glyphs) == 1
    assert upper.unicode.endswith("在她的上腿")
    assert lower.unicode == "顶部然后向下"
    assert upper.box.x == 102
    assert lower.box.x == 200
    assert lower.box.y2 == 488


def test_a_closing_mark_stays_on_the_open_line():
    upper, lower = _pair("然后将双手移到这里还差五个字啊", "在她的上腿，然后向下")
    page = _page(upper, lower)
    assert continue_indented_sentences(page, _glyphs) == 1
    assert upper.unicode.endswith("在她的上腿，")
    assert lower.unicode == "然后向下"


def test_a_time_character_that_does_not_fit_stays_below():
    upper, lower = _pair("然后将双手移到这里还差五个字啊", "在她的上腿时然后向下")
    page = _page(upper, lower)
    assert continue_indented_sentences(page, _glyphs) == 1
    assert upper.unicode.endswith("在她的上腿")
    assert lower.unicode.startswith("时")


def test_a_finished_sentence_stays_apart():
    upper, lower = _pair("然后将双手移开。", "在她的上腿顶部然后向下")
    page = _page(upper, lower)
    assert continue_indented_sentences(page, _glyphs) == 0
    assert lower.unicode.startswith("在她的")


def test_a_step_without_a_figure_stays_apart():
    upper, lower = _pair("然后将双手移到这里还差五个字啊", "在她的上腿顶部然后向下")
    page = _page(upper, lower, figure=False)
    assert continue_indented_sentences(page, _glyphs) == 0


def test_a_full_page_image_is_not_the_indent():
    upper, lower = _pair("然后将双手移到这里还差五个字啊", "在她的上腿顶部然后向下")
    page = _page(upper, lower, figure=False)
    page.pdf_figure = [PdfFigure(box=Box(x=0, y=0, x2=612, y2=792))]
    assert continue_indented_sentences(page, _glyphs) == 0


def test_a_full_width_contour_fills_its_open_line():
    upper, lower = _pair("然后将双手移到这里还差五个字啊", "在她的上腿顶部然后向下")
    upper.layout_region_id = "kept"
    page = _page(upper, lower)
    page.layout_plan = LayoutPlan(
        source_fingerprint="t",
        page_index=0,
        input_gate="single_page",
        decisions=(),
        line_edge_links=(
            LineEdgeLink("kept", ((102.0, 202.0), (102.0, 202.0))),
        ),
    )
    assert continue_indented_sentences(page, _glyphs) == 1
    assert upper.unicode.endswith("在她的上腿")
    assert lower.unicode == "顶部然后向下"


def test_a_narrow_contour_tail_stays():
    upper, lower = _pair("然后将双手移到这里还差五个字啊", "在她的上腿顶部然后向下")
    upper.layout_region_id = "kept"
    page = _page(upper, lower)
    page.layout_plan = LayoutPlan(
        source_fingerprint="t",
        page_index=0,
        input_gate="single_page",
        decisions=(),
        line_edge_links=(
            LineEdgeLink("kept", ((102.0, 202.0), (102.0, 182.0))),
        ),
    )
    assert continue_indented_sentences(page, _glyphs) == 0
    assert lower.unicode.startswith("在她的")


def test_a_contour_below_is_not_stolen():
    upper, lower = _pair("然后将双手移到这里还差五个字啊", "在她的上腿顶部然后向下")
    lower.layout_region_id = "kept"
    page = _page(upper, lower)
    page.layout_plan = LayoutPlan(
        source_fingerprint="t",
        page_index=0,
        input_gate="single_page",
        decisions=(),
        line_edge_links=(LineEdgeLink("kept", ((200.0, 300.0),)),),
    )
    assert continue_indented_sentences(page, _glyphs) == 0
    assert lower.unicode.startswith("在她的")


def test_a_wide_gap_stays_apart():
    upper, lower = _pair("然后将双手移到这里还差五个字啊", "在她的上腿顶部然后向下")
    lower.box.y2 = 450
    page = _page(upper, lower)
    assert continue_indented_sentences(page, _glyphs) == 0


def test_two_halves_of_one_step_fill_that_frame():
    # The calf step: two full lines, then the photo indent, short last line.
    upper, lower = _pair(
        "多做几次，然后将双手移到",
        "在她的上腿顶部。重复此动作数次。",
    )
    upper.box.x2 = 512.65
    lower.box.x = 231.0
    lower.box.x2 = 512.66
    lower.box.y = 400
    lower.box.y2 = 488
    upper.reference_metrics = _metrics([410.65, 410.65])
    lower.reference_metrics = _metrics([281.66, 281.59, 281.59, 153.42])
    upper.layout_region_id = "top"
    upper.source_line_edges = ((102.0, 512.65), (102.0, 512.65))
    lower.source_line_edges = (
        (231.0, 512.66),
        (231.0, 512.59),
        (231.0, 512.59),
        (231.0, 384.42),
    )
    page = _page(upper, lower)
    page.layout_plan = LayoutPlan(
        source_fingerprint="t",
        page_index=0,
        input_gate="single_page",
        decisions=(),
        line_edge_links=(
            LineEdgeLink("top", ((102.0, 512.65), (102.0, 512.65))),
            LineEdgeLink("other", ((10.0, 30.0), (10.0, 30.0))),
        ),
    )
    _freeze_shared(
        page,
        list(upper.source_line_edges) + list(lower.source_line_edges),
    )

    assert continue_indented_sentences(page, _glyphs) == 1
    assert page.pdf_paragraph == [upper]
    assert upper.unicode == "多做几次，然后将双手移到在她的上腿顶部。重复此动作数次。"
    assert upper.layout_region_id == "top"
    assert upper.box.x == 102.0
    assert upper.box.y == 400
    assert upper.box.y2 == 518
    assert upper.optimal_scale == 1.0
    links = {link.region_id: link for link in page.layout_plan.line_edge_links}
    assert set(links) == {"top", "other"}
    assert links["other"].edges == ((10.0, 30.0), (10.0, 30.0))
    edges = links["top"].edges
    assert edges[0] == (102.0, 512.65)
    assert edges[1] == (102.0, 512.65)
    assert edges[2][0] == 231.0
    assert abs(edges[-1][0] - 231.0) < 0.01
    assert abs(edges[-1][1] - 384.42) < 0.01
    assert len(edges) == 6


def _metrics(widths: list[float]) -> ReferenceMetrics:
    average = sum(widths) / len(widths)
    return ReferenceMetrics(
        line_count=len(widths),
        avg_line_width=average,
        last_line_width=widths[-1],
        last_line_ratio=widths[-1] / average,
        font_size=12.0,
        per_line_widths=widths,
    )


def test_a_sentence_flow_upper_keeps_its_frame():
    upper, lower = _calf_halves()
    upper.layout_region_id = "verse"
    page = _page(upper, lower)
    page.layout_plan = _plan(
        LineEdgeLink(
            "verse",
            ((102.0, 512.0), (102.0, 512.0)),
            flow="sentence",
        ),
    )
    assert continue_indented_sentences(page, _glyphs) == 0
    assert lower.unicode.startswith("在她的")
    assert upper.box.y == 488
    assert page.layout_plan.line_edge_links[0].flow == "sentence"


def test_a_narrow_tip_with_source_edges_stays():
    upper, lower = _calf_halves()
    upper.layout_region_id = "tip"
    page = _page(upper, lower)
    page.layout_plan = _plan(
        LineEdgeLink("tip", ((102.0, 512.0), (102.0, 400.0))),
    )
    assert continue_indented_sentences(page, _glyphs) == 0
    assert lower.unicode.startswith("在她的")
    assert upper.box.y == 488
    assert page.layout_plan.line_edge_links[0].edges[-1] == (102.0, 400.0)


def test_an_unmatched_contour_stays_two_paragraphs():
    upper, lower = _pair("甲" * 20, "在她的上腿顶部然后向下")
    upper.source_line_edges = ((100.0, 400.0), (100.0, 400.0))
    lower.source_line_edges = ((100.0, 400.0), (100.0, 400.0))
    page = _page(upper, lower)
    assert continue_indented_sentences(page, _glyphs) == 0
    assert upper.unicode == "甲" * 20
    assert lower.unicode.startswith("在她的")
    assert page.layout_plan is None


def test_saved_widths_do_not_invent_a_left():
    upper, lower = _calf_halves()
    upper.source_line_edges = None
    lower.source_line_edges = None
    upper.reference_metrics = _metrics([410.65, 410.65])
    lower.reference_metrics = _metrics([281.66, 281.59, 281.59, 153.42])
    page = _page(upper, lower)
    continue_indented_sentences(page, _glyphs)
    assert upper.box.y == 488
    assert upper.optimal_scale is None
    assert page.layout_plan is None


def test_a_closed_gate_does_not_take_the_frame():
    upper, lower = _calf_halves()
    page = _page(upper, lower)
    page.layout_plan = LayoutPlan(
        source_fingerprint="t",
        page_index=0,
        input_gate="spread",
        decisions=(),
    )
    continue_indented_sentences(page, _glyphs)
    assert upper.box.y == 488
    assert upper.optimal_scale is None
    assert page.layout_plan.input_gate == "spread"
    assert page.layout_plan.line_edge_links == ()


def test_two_fills_without_ids_keep_two_frames():
    upper_a, lower_a = _calf_halves()
    upper_b = _para("再往下继续摩擦她的小腿", x=40, y=480, x2=300, y2=510)
    lower_b = _para("然后移到大腿内侧停住", x=120, y=400, x2=300, y2=480)
    upper_b.source_line_edges = ((40.0, 300.0), (40.0, 300.0))
    lower_b.source_line_edges = (
        (120.0, 300.1),
        (120.0, 300.0),
        (120.0, 300.0),
        (120.0, 180.0),
    )
    page = Page(
        page_number=0,
        pdf_paragraph=[upper_a, lower_a, upper_b, lower_b],
        pdf_figure=[PdfFigure(box=Box(x=0, y=300, x2=120, y2=760))],
    )
    _freeze_shared(
        page,
        list(upper_a.source_line_edges) + list(lower_a.source_line_edges),
        list(upper_b.source_line_edges) + list(lower_b.source_line_edges),
    )
    assert continue_indented_sentences(page, _glyphs) == 2
    assert page.pdf_paragraph == [upper_a, upper_b]
    links = {link.region_id: link for link in page.layout_plan.line_edge_links}
    assert upper_a.layout_region_id != upper_b.layout_region_id
    assert set(links) == {upper_a.layout_region_id, upper_b.layout_region_id}
    assert links[upper_a.layout_region_id].edges[0] == (102.0, 512.65)
    assert links[upper_b.layout_region_id].edges[0] == (40.0, 300.0)
    assert links[upper_b.layout_region_id].edges[-1] == (120.0, 180.0)


def _calf_halves():
    upper, lower = _pair(
        "多做几次，然后将双手移到",
        "在她的上腿顶部。重复此动作数次。",
    )
    upper.box.x2 = 512.65
    lower.box.x = 231.0
    lower.box.x2 = 512.66
    lower.box.y = 400
    lower.box.y2 = 488
    upper.source_line_edges = ((102.0, 512.65), (102.0, 512.65))
    lower.source_line_edges = (
        (231.0, 512.66),
        (231.0, 512.59),
        (231.0, 512.59),
        (231.0, 384.42),
    )
    return upper, lower


def _freeze_shared(page, *edge_groups) -> None:
    """Store the plan-time contour. Typesetting only looks it up."""
    from dataclasses import replace

    from babeldoc.format.pdf.document_il.utils.layout_plan.line_edges import (
        shared_contour_for,
    )

    contours = []
    for edges in edge_groups:
        contour = shared_contour_for(edges)
        assert contour is not None
        contours.append(contour)
    plan = page.layout_plan
    if plan is None:
        plan = LayoutPlan(
            source_fingerprint="t",
            page_index=0,
            input_gate="single_page",
            decisions=(),
        )
    page.layout_plan = replace(plan, shared_contours=tuple(contours))


def test_a_frozen_frame_does_not_claim_again(monkeypatch):
    upper, lower = _calf_halves()
    upper.layout_region_id = "top"
    page = _page(upper, lower)
    page.layout_plan = _plan()
    _freeze_shared(
        page,
        list(upper.source_line_edges) + list(lower.source_line_edges),
    )

    def boom(*_args, **_kwargs):
        raise AssertionError("typeset claimed a paradigm")

    monkeypatch.setattr(
        "babeldoc.format.pdf.document_il.utils.layout_plan.line_edges.load_catalog",
        boom,
    )
    monkeypatch.setattr(
        "babeldoc.format.pdf.document_il.utils.layout_plan.line_edges.shared_contour_for",
        boom,
    )
    assert continue_indented_sentences(page, _glyphs) == 1
    assert page.pdf_paragraph == [upper]


def _plan(*links) -> LayoutPlan:
    return LayoutPlan(
        source_fingerprint="t",
        page_index=0,
        input_gate="single_page",
        decisions=(),
        line_edge_links=links,
    )


def test_a_short_box_uses_the_smaller_advance():
    # Ten glyphs of 12. A 100pt line holds eight at a full em, nine once
    # the box is too short for that em and the advance steps to 0.90.
    upper, lower = _pair("一二三四五六七八九十", "甲乙丙丁戊己庚辛壬癸")
    upper.box.y2 = upper.box.y + 27.2

    def widths(paragraph):
        text = paragraph.pdf_paragraph_composition[0].pdf_same_style_unicode_characters.unicode
        return [(char, 12.0) for char in text]

    page = _page(upper, lower)
    assert continue_indented_sentences(page, widths) == 1
    assert upper.unicode.endswith("甲乙丙丁戊己庚辛")
    assert lower.unicode == "壬癸"
