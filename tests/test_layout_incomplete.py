"""Final contour placement must fail closed instead of committing a short line."""

from __future__ import annotations

import hashlib
import json
import pickle
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from unittest.mock import patch

import pymupdf
import pytest
from babeldoc.babeldoc_exception.LayoutIncompleteError import LayoutIncompleteError
from babeldoc.quality import QualityReport
from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import Cropbox
from babeldoc.format.pdf.document_il.il_version_1 import Document
from babeldoc.format.pdf.document_il.il_version_1 import Mediabox
from babeldoc.format.pdf.document_il.il_version_1 import Page
from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter
from babeldoc.format.pdf.document_il.il_version_1 import PdfFormula
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraphComposition
from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
from babeldoc.format.pdf.document_il.il_version_1 import VisualBbox
from babeldoc.format.pdf.document_il.midend.typesetting import Typesetting
from babeldoc.format.pdf.document_il.midend.typesetting import TypesettingUnit
from babeldoc.format.pdf.document_il.utils.layout_plan.model import ContourLevel
from babeldoc.format.pdf.document_il.utils.layout_plan.model import LineEdgeLink
from babeldoc.format.pdf.high_level import do_translate
from babeldoc.format.pdf.high_level import get_translation_stage
from babeldoc.format.pdf.translation_config import TranslationConfig
from babeldoc.format.pdf.translation_config import WatermarkOutputMode
from babeldoc.progress_monitor import ProgressMonitor
from babeldoc.translator.fixed_map_translator import FixedMapTranslator


def _cjk_glyph(width: float = 10.0, text: str = "中") -> TypesettingUnit:
    glyph = Box(x=0, y=0, x2=width, y2=12)
    char = PdfCharacter(
        char_unicode=text,
        box=glyph,
        visual_bbox=VisualBbox(box=Box(x=0, y=0, x2=width, y2=12)),
        pdf_style=PdfStyle(font_id="base", font_size=12, graphic_state=None),
    )
    return TypesettingUnit(char=char)


def _typesetter() -> Typesetting:
    ts = Typesetting(
        TranslationConfig(
            translator=FixedMapTranslator(),
            input_file="contour-scale.pdf",
            lang_in="en",
            lang_out="zh-CN",
            doc_layout_model=MagicMock(),
            auto_extract_glossary=False,
        )
    )
    ts._wrap_enabled = False
    ts._pocket_link = None
    ts._rect_fill_active = False
    return ts


def _probe_link() -> LineEdgeLink:
    """Two 100pt samples. Copied from the offline contour probe, not imported."""
    return LineEdgeLink(
        "probe",
        ((100.0, 200.0), (100.0, 200.0)),
        "left",
        "edge",
        (
            ContourLevel(100.0, 200.0, 400.0, "observed"),
            ContourLevel(100.0, 200.0, 382.0, "observed"),
        ),
    )


def _contour_case(
    unit_count: int,
) -> tuple[Typesetting, PdfParagraph, Page, list[TypesettingUnit]]:
    ts = _typesetter()
    ts._line_edges = _probe_link()
    paragraph = PdfParagraph(
        box=Box(x=100, y=0, x2=200, y2=400),
        pdf_style=PdfStyle(font_id="base", font_size=12, graphic_state=None),
        unicode="中" * unit_count,
        debug_id="review-overflow",
        pdf_paragraph_composition=[],
    )
    page = Page(page_number=0)
    units = [_cjk_glyph() for _ in range(unit_count)]
    return ts, paragraph, page, units


def _apply(ts, paragraph, page, units, *, apply_layout: bool):
    return ts._find_optimal_scale_and_layout_inner(
        paragraph,
        page,
        units,
        1.0,
        use_english_line_break=False,
        apply_layout=apply_layout,
        wrap_enabled=False,
        drop_figure_zones=True,
    )


def _rendered_text(paragraph: PdfParagraph) -> str:
    return "".join(
        composition.pdf_character.char_unicode
        for composition in paragraph.pdf_paragraph_composition
        if composition.pdf_character is not None
        and composition.pdf_character.char_unicode
    )


def test_exhausted_contour_raises_before_committing_partial_composition():
    ts, paragraph, page, units = _contour_case(400)
    before = deepcopy(paragraph.pdf_paragraph_composition)
    with pytest.raises(LayoutIncompleteError) as caught:
        _apply(ts, paragraph, page, units, apply_layout=True)
    assert caught.value.reason == "contour_exhausted"
    assert caught.value.requested_units == 400
    assert caught.value.placed_units < 400
    assert paragraph.pdf_paragraph_composition == before
    assert "中" not in caught.value.args[0]
    assert len(caught.value.args) == 1


def test_failed_apply_keeps_a_nonempty_composition_and_page_graphics():
    ts, paragraph, page, units = _contour_case(400)
    stale = PdfParagraphComposition(pdf_character=_cjk_glyph(text="旧").char)
    sentinel = object()
    paragraph.pdf_paragraph_composition = [stale]
    page.pdf_curve.append(sentinel)
    page.pdf_form.append(sentinel)
    before = deepcopy(paragraph.pdf_paragraph_composition)
    box = (paragraph.box.x, paragraph.box.y, paragraph.box.x2, paragraph.box.y2)
    with pytest.raises(LayoutIncompleteError) as caught:
        _apply(ts, paragraph, page, units, apply_layout=True)
    assert caught.value.reason == "contour_exhausted"
    assert paragraph.pdf_paragraph_composition == before
    assert paragraph.pdf_paragraph_composition[0].pdf_character.char_unicode == "旧"
    assert (paragraph.box.x, paragraph.box.y, paragraph.box.x2, paragraph.box.y2) == box
    assert page.pdf_curve == [sentinel]
    assert page.pdf_form == [sentinel]


def test_sufficient_contour_commits_complete_text():
    ts, paragraph, page, units = _contour_case(8)
    _apply(ts, paragraph, page, units, apply_layout=True)
    assert _rendered_text(paragraph) == "中" * 8


def test_probe_failure_does_not_change_composition_or_raise():
    ts, paragraph, page, units = _contour_case(400)
    stale = PdfParagraphComposition(pdf_character=_cjk_glyph(text="旧").char)
    paragraph.pdf_paragraph_composition = [stale]
    before = deepcopy(paragraph.pdf_paragraph_composition)
    scale, placed = _apply(ts, paragraph, page, units, apply_layout=False)
    assert paragraph.pdf_paragraph_composition == before
    assert placed is None
    assert scale is not None


def test_early_scale_miss_then_fit_does_not_raise():
    """A scale that cannot hold the line must not poison a later scale that can."""
    ts, paragraph, page, units = _contour_case(36)
    _apply(ts, paragraph, page, units, apply_layout=True)
    assert _rendered_text(paragraph) == "中" * 36


def test_glyph_wider_than_positive_interval_is_not_force_committed():
    ts = _typesetter()
    ts._line_edges = LineEdgeLink(
        "probe",
        ((100.0, 108.0),),
        "left",
        "edge",
        (ContourLevel(100.0, 108.0, 400.0, "observed"),),
    )
    paragraph = PdfParagraph(
        box=Box(x=100, y=0, x2=108, y2=400),
        pdf_style=PdfStyle(font_id="base", font_size=12, graphic_state=None),
        unicode="中",
        debug_id="too-wide",
        pdf_paragraph_composition=[
            PdfParagraphComposition(pdf_character=_cjk_glyph(text="旧").char)
        ],
    )
    page = Page(page_number=2)
    before = deepcopy(paragraph.pdf_paragraph_composition)
    curves = list(page.pdf_curve)
    forms = list(page.pdf_form)
    with pytest.raises(LayoutIncompleteError) as caught:
        _apply(ts, paragraph, page, [_cjk_glyph(width=20.0)], apply_layout=True)
    assert caught.value.reason == "contour_glyph_too_wide"
    assert caught.value.requested_units == 1
    # The attempt can still hold the overflowing glyph. Count is not fitness.
    assert caught.value.placed_units == caught.value.requested_units
    assert paragraph.pdf_paragraph_composition == before
    assert page.pdf_curve == curves
    assert page.pdf_form == forms
    assert caught.value.page_index == 2
    assert caught.value.paragraph_id == "too-wide"


def test_legal_space_and_formula_do_not_raise():
    ts, paragraph, page, _units = _contour_case(0)
    space = _cjk_glyph(width=4.0, text=" ")
    body = [_cjk_glyph() for _ in range(4)]
    formula_char = _cjk_glyph(width=10.0, text="式").char
    formula = PdfFormula(
        box=Box(x=0, y=0, x2=10, y2=12),
        pdf_character=[formula_char],
        x_offset=0.0,
        y_offset=0.0,
        x_advance=10.0,
    )
    units = [space, *body, TypesettingUnit(formular=formula)]
    _apply(ts, paragraph, page, units, apply_layout=True)
    # The leading space is a real unit and is not painted. The formula is one
    # unit whose glyph is committed. Neither difference is missing body text.
    assert _rendered_text(paragraph) == ("中" * 4) + "式"


def test_depth_limit_apply_raises_without_committing():
    ts, paragraph, page, units = _contour_case(8)
    stale = PdfParagraphComposition(pdf_character=_cjk_glyph(text="旧").char)
    paragraph.pdf_paragraph_composition = [stale]
    before = deepcopy(paragraph.pdf_paragraph_composition)
    with pytest.raises(LayoutIncompleteError) as caught:
        ts._find_optimal_scale_and_layout_inner(
            paragraph,
            page,
            units,
            1.0,
            use_english_line_break=False,
            apply_layout=True,
            wrap_enabled=False,
            drop_figure_zones=True,
            _depth=5,
        )
    assert caught.value.reason == "layout_depth_exhausted"
    assert caught.value.requested_units == 8
    assert caught.value.placed_units == 0
    assert caught.value.page_index == 0
    assert caught.value.paragraph_id == "review-overflow"
    assert paragraph.pdf_paragraph_composition == before


def test_legal_depth_scale_search_propagates_nested_depth_abort():
    """Depth 4 may enter the scale loop. The fitting sample's FULL_MEASURE is depth 5."""
    ts = _typesetter()
    ts._line_edges = None
    ts._pocket_link = None
    # Direct inner entry does not assign an attempt. None is not FULL_MEASURE.
    ts._layout_attempt = None
    paragraph = PdfParagraph(
        box=Box(x=72, y=72, x2=500, y2=700),
        pdf_style=PdfStyle(font_id="base", font_size=12, graphic_state=None),
        unicode="中" * 4,
        debug_id="depth-scale",
        pdf_paragraph_composition=[
            PdfParagraphComposition(pdf_character=_cjk_glyph(text="旧").char)
        ],
    )
    page = Page(page_number=4)
    units = [_cjk_glyph() for _ in range(4)]
    before = deepcopy(paragraph.pdf_paragraph_composition)

    def abandon(
        paragraph,
        box,
        typeset_units,
        *,
        all_units_fit,
        wrap_enabled,
        drop_figure_zones,
    ):
        # The floor FULL_MEASURE is outside this try and passes fit=False.
        # Only a fitting sample takes the in-loop return.
        if paragraph is None or box is None or typeset_units is None:
            return False
        if wrap_enabled and drop_figure_zones:
            return False
        return bool(all_units_fit)

    ts._cjk_should_abandon_narrow_column = abandon
    with pytest.raises(LayoutIncompleteError) as caught:
        ts._find_optimal_scale_and_layout_inner(
            paragraph,
            page,
            units,
            1.0,
            use_english_line_break=False,
            apply_layout=True,
            wrap_enabled=False,
            drop_figure_zones=False,
            _depth=4,
        )
    assert caught.value.reason == "layout_depth_exhausted"
    assert caught.value.requested_units == 4
    assert caught.value.placed_units == 0
    assert caught.value.page_index == 4
    assert caught.value.paragraph_id == "depth-scale"
    assert paragraph.pdf_paragraph_composition == before
    assert paragraph.pdf_paragraph_composition[0].pdf_character.char_unicode == "旧"


def test_layout_incomplete_error_pickles_without_document_payload():
    error = LayoutIncompleteError(
        page_index=2,
        paragraph_id="review-overflow",
        reason="contour_exhausted",
        requested_units=400,
        placed_units=64,
    )
    restored = pickle.loads(pickle.dumps(error))  # noqa: S301
    assert restored.to_dict() == error.to_dict()
    assert restored.to_dict() == {
        "page_index": 2,
        "paragraph_id": "review-overflow",
        "reason": "contour_exhausted",
        "requested_units": 400,
        "placed_units": 64,
    }
    assert len(error.args) == 1
    assert isinstance(error.args[0], str)
    assert "中" not in error.args[0]


def test_retypeset_helpers_roll_back_and_mark_without_raising():
    for helper_name in ("retypeset_paragraph", "_retypeset_paragraphs_at_box"):
        ts, paragraph, page, units = _contour_case(400)
        report = QualityReport(run_id=f"retypeset-{helper_name}")
        ts.translation_config.shared_context_cross_split_part.quality_report = report
        paragraph.pdf_paragraph_composition = [
            PdfParagraphComposition(pdf_character=unit.char) for unit in units
        ]
        paragraph.layout_region_id = "probe"
        page.page_number = 5
        page.layout_plan = SimpleNamespace(
            decisions=(),
            line_edge_links=(ts._line_edges,),
        )
        page.cropbox = Cropbox(box=Box(x=0, y=0, x2=612, y2=792))
        before = deepcopy(paragraph.pdf_paragraph_composition)
        box = (paragraph.box.x, paragraph.box.y, paragraph.box.x2, paragraph.box.y2)
        if helper_name == "retypeset_paragraph":
            assert ts.retypeset_paragraph(paragraph, page) is False
        else:
            ts._retypeset_paragraphs_at_box(page, {}, [paragraph])
        assert paragraph.pdf_paragraph_composition == before, helper_name
        assert (
            paragraph.box.x,
            paragraph.box.y,
            paragraph.box.x2,
            paragraph.box.y2,
        ) == box, helper_name
        issue = report.to_dict()["issues"][0]
        assert issue["code"] == "layout_incomplete", helper_name
        assert issue["details"]["reason"] == "contour_exhausted", helper_name
        assert issue["page_index"] == 5, helper_name
        assert "中" not in json.dumps(report.to_dict(), ensure_ascii=False)


def _page_with_text(page_number: int, unit_count: int, link: LineEdgeLink) -> Page:
    units = [_cjk_glyph() for _ in range(unit_count)]
    paragraph = PdfParagraph(
        box=Box(x=100, y=0, x2=200, y2=400),
        pdf_style=PdfStyle(font_id="base", font_size=12, graphic_state=None),
        unicode="中" * unit_count,
        debug_id=f"page-{page_number}",
        layout_region_id=link.region_id,
        pdf_paragraph_composition=[
            PdfParagraphComposition(pdf_character=unit.char) for unit in units
        ],
    )
    page = Page(
        page_number=page_number,
        cropbox=Cropbox(box=Box(x=0, y=0, x2=612, y2=792)),
        mediabox=Mediabox(box=Box(x=0, y=0, x2=612, y2=792)),
        pdf_paragraph=[paragraph],
    )
    page.layout_plan = SimpleNamespace(decisions=(), line_edge_links=(link,))
    return page


def _pdf_names(directory: Path) -> list[str]:
    return sorted(path.name for path in directory.glob("*.pdf"))


def test_render_paragraph_marks_one_failure_and_typesets_the_next():
    link = _probe_link()
    ts = _typesetter()
    report = QualityReport(run_id="mark-para")
    ts.translation_config.shared_context_cross_split_part.quality_report = report
    bad_units = [_cjk_glyph() for _ in range(400)]
    good_units = [_cjk_glyph() for _ in range(8)]
    bad = PdfParagraph(
        box=Box(x=100, y=0, x2=200, y2=400),
        pdf_style=PdfStyle(font_id="base", font_size=12, graphic_state=None),
        unicode="中" * 400,
        debug_id="failed-part",
        layout_region_id=link.region_id,
        pdf_paragraph_composition=[
            PdfParagraphComposition(pdf_character=unit.char) for unit in bad_units
        ],
    )
    good = PdfParagraph(
        box=Box(x=100, y=0, x2=200, y2=400),
        pdf_style=PdfStyle(font_id="base", font_size=12, graphic_state=None),
        unicode="中" * 8,
        debug_id="kept-part",
        layout_region_id=link.region_id,
        pdf_paragraph_composition=[
            PdfParagraphComposition(pdf_character=unit.char) for unit in good_units
        ],
    )
    page = Page(
        page_number=4,
        cropbox=Cropbox(box=Box(x=0, y=0, x2=612, y2=792)),
        pdf_paragraph=[bad, good],
    )
    page.layout_plan = SimpleNamespace(decisions=(), line_edge_links=(link,))
    before_bad = deepcopy(bad.pdf_paragraph_composition)

    ts.render_paragraph(bad, page, {})
    ts.render_paragraph(good, page, {})

    assert bad.pdf_paragraph_composition == before_bad
    assert len(bad.pdf_paragraph_composition) == 400
    assert _rendered_text(good) == "中" * 8
    payload = report.to_dict()
    assert payload["status"] == "failed"
    assert len(payload["issues"]) == 1
    issue = payload["issues"][0]
    assert issue["paragraph_id"] == "failed-part"
    assert issue["page_index"] == 4
    assert issue["severity"] == "error"
    assert issue["details"]["reason"] == "contour_exhausted"
    assert issue["details"]["placed_units"] < issue["details"]["requested_units"]
    assert "中" not in json.dumps(payload, ensure_ascii=False)


@pytest.mark.parametrize(
    "mode",
    [
        WatermarkOutputMode.Both,
        WatermarkOutputMode.Watermarked,
        WatermarkOutputMode.NoWatermark,
    ],
)
def test_later_page_layout_failure_still_finishes_and_marks_that_page(tmp_path, mode):
    final_dir = tmp_path / "final"
    final_dir.mkdir()
    sentinel = final_dir / "already-delivered.pdf"
    sentinel.write_bytes(b"%PDF-1.4 sentinel\n")
    sentinel_hash = hashlib.sha256(sentinel.read_bytes()).hexdigest()
    before_pdfs = _pdf_names(final_dir)

    source = tmp_path / "input.pdf"
    blank = pymupdf.open()
    blank.new_page()
    blank.new_page()
    blank.save(source)
    blank.close()

    link = _probe_link()
    il_doc = Document(
        total_pages=2,
        page=[
            _page_with_text(0, 8, link),
            _page_with_text(1, 400, link),
        ],
    )
    config = TranslationConfig(
        translator=FixedMapTranslator(),
        input_file=source,
        lang_in="en",
        lang_out="zh-CN",
        doc_layout_model=MagicMock(),
        output_dir=final_dir,
        working_dir=tmp_path / "work",
        watermark_output_mode=mode,
        auto_extract_glossary=False,
        skip_translation=True,
        skip_scanned_detection=True,
        enable_post_layout_optimization=False,
        debug=False,
    )
    events: list[dict] = []
    monitor = ProgressMonitor(
        get_translation_stage(config),
        finish_callback=lambda **kwargs: events.append(kwargs),
    )
    recorded: list[Path] = []

    def spy_write(self, translation_config, check_font_exists=False):  # noqa: ARG001
        output_dir = Path(translation_config.output_dir).resolve()
        recorded.append(output_dir)
        written = output_dir / "spy-prewrite.pdf"
        blank = pymupdf.open()
        blank.new_page()
        blank.save(written)
        blank.close()
        return SimpleNamespace(
            mono_pdf_path=written,
            dual_pdf_path=None,
            no_watermark_mono_pdf_path=written,
            no_watermark_dual_pdf_path=None,
        )

    with (
        patch(
            "babeldoc.format.pdf.new_parser.native_parse.parse_prepared_pdf_with_new_parser_to_legacy_ir",
            return_value=il_doc,
        ),
        patch(
            "babeldoc.format.pdf.high_level.LayoutParser.process",
            lambda self, docs, *args, **kwargs: docs,
        ),
        patch(
            "babeldoc.format.pdf.high_level.ParagraphFinder.process",
            lambda self, docs, *args, **kwargs: None,
        ),
        patch(
            "babeldoc.format.pdf.high_level.StylesAndFormulas.process",
            lambda self, docs, *args, **kwargs: None,
        ),
        patch(
            "babeldoc.format.pdf.high_level.PDFCreater.write",
            spy_write,
        ),
        # Stacked probe glyphs are not two 100pt lines. Rebuilding the
        # plan would drop the contour this case is about.
        patch(
            "babeldoc.format.pdf.document_il.utils.rect_flow_stack.attach_layout_plans",
            return_value=False,
        ),
    ):
        result = do_translate(monitor, config)

    assert result is not None
    finish_events = [event for event in events if event.get("type") == "finish"]
    assert finish_events
    assert not any(event.get("type") == "error" for event in events)
    assert hashlib.sha256(sentinel.read_bytes()).hexdigest() == sentinel_hash
    final_resolved = final_dir.resolve()
    assert final_resolved in recorded
    for output_dir in recorded:
        if output_dir != final_resolved:
            assert final_resolved not in output_dir.parents
            assert not output_dir.exists()
    reports = list(final_dir.glob("*.quality.json"))
    assert len(reports) == 1
    payload = json.loads(reports[0].read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    issue = payload["issues"][0]
    assert issue["code"] == "layout_incomplete"
    assert issue["paragraph_id"] == "page-1"
    assert issue["page_index"] == 1
    assert issue["details"]["reason"] == "contour_exhausted"
    assert "中" not in json.dumps(payload, ensure_ascii=False)
    failed = il_doc.page[1].pdf_paragraph[0]
    assert len(failed.pdf_paragraph_composition) == 400
    assert _rendered_text(il_doc.page[0].pdf_paragraph[0]) == "中" * 8
    assert sentinel.name in _pdf_names(final_dir)
    assert _pdf_names(final_dir) != before_pdfs
