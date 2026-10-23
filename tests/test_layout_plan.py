"""LayoutPlan slice: facts, three plugins, resolver, one consumer.

rect_flow column order is flow_next_id, not above_id / below_id.
list order is its own flow_next_id, not above_id / below_id.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pymupdf
from babeldoc.format.pdf.document_il.midend.typesetting import Typesetting
from babeldoc.format.pdf.document_il.utils.layout_helper import composition_characters
from babeldoc.format.pdf.document_il.utils.layout_plan.compose import build_plan
from babeldoc.format.pdf.document_il.utils.layout_plan.consume import (
    consume_layout_plan,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.corpus import EXPECTED_PDF_COUNT
from babeldoc.format.pdf.document_il.utils.layout_plan.corpus import (
    EXPECTED_TOP_LEVEL_DIRECTORIES,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.corpus import build_manifest
from babeldoc.format.pdf.document_il.utils.layout_plan.corpus import count_errors
from babeldoc.format.pdf.document_il.utils.layout_plan.corpus import lock_errors
from babeldoc.format.pdf.document_il.utils.layout_plan.facts import SourceBlock
from babeldoc.format.pdf.document_il.utils.layout_plan.facts import build_facts
from babeldoc.format.pdf.document_il.utils.layout_plan.marker import first_marker
from babeldoc.format.pdf.document_il.utils.layout_plan.marker import marker_from_glyph
from babeldoc.format.pdf.document_il.utils.layout_plan.model import Evidence
from babeldoc.format.pdf.document_il.utils.layout_plan.model import FigureBox
from babeldoc.format.pdf.document_il.utils.layout_plan.model import LayoutPlan
from babeldoc.format.pdf.document_il.utils.layout_plan.model import LineBox
from babeldoc.format.pdf.document_il.utils.layout_plan.model import PlanContribution
from babeldoc.format.pdf.document_il.utils.layout_plan.model import PocketLink
from babeldoc.format.pdf.document_il.utils.layout_plan.model import RegionDecision
from babeldoc.format.pdf.document_il.utils.layout_plan.model import make_region_id
from babeldoc.format.pdf.document_il.utils.layout_plan.paragraph_gap import (
    scanned_paragraph_gap,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.pdf_scan import scan_pdf
from babeldoc.format.pdf.document_il.utils.layout_plan.pocket_chain import (
    scanned_edge_gap,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.resolver import resolve
from babeldoc.format.pdf.document_il.utils.line_raster import hides_translated_line
from babeldoc.format.pdf.document_il.utils.list_flow_stack import assign_list_boxes
from babeldoc.format.pdf.document_il.utils.list_flow_stack import pack_list_items
from babeldoc.format.pdf.document_il.utils.mixed_column_split import (
    split_mixed_column_wraps,
)
from babeldoc.format.pdf.document_il.utils.paragraph_gap_stack import (
    pack_body_paragraphs,
)
from babeldoc.format.pdf.document_il.utils.rect_flow_stack import _channels_are_ink
from babeldoc.format.pdf.document_il.utils.rect_flow_stack import _figures_of
from babeldoc.format.pdf.document_il.utils.rect_flow_stack import _ink_span
from babeldoc.format.pdf.document_il.utils.rect_flow_stack import assign_rect_flow_boxes
from babeldoc.format.pdf.document_il.utils.rect_flow_stack import attach_layout_plans
from babeldoc.format.pdf.document_il.utils.rect_flow_stack import column_gap_for
from babeldoc.format.pdf.document_il.utils.rect_flow_stack import figure_gap_tops
from babeldoc.format.pdf.document_il.utils.rect_flow_stack import line_slots
from babeldoc.format.pdf.document_il.utils.rect_flow_stack import (
    moved_figure_gap_paragraphs,
)
from babeldoc.format.pdf.document_il.utils.rect_flow_stack import pack_offsets
from babeldoc.format.pdf.document_il.utils.rect_flow_stack import pack_rect_flow
from babeldoc.format.pdf.document_il.utils.rect_flow_stack import run_legacy_column_flow
from babeldoc.format.pdf.document_il.utils.shaped_pocket_stack import (
    _push_overlaps_down,
)
from babeldoc.format.pdf.document_il.utils.shaped_pocket_stack import align_frame_line
from babeldoc.format.pdf.document_il.utils.shaped_pocket_stack import (
    assign_shaped_boxes,
)
from babeldoc.format.pdf.document_il.utils.shaped_pocket_stack import (
    interval_for_pocket,
)
from babeldoc.format.pdf.document_il.utils.shaped_pocket_stack import (
    pack_shaped_pockets,
)

_GOLD = Path(__file__).parent / "golden" / "layout_plan"
_SCHEMA_ONLY_KINDS = {"corpus", "shaped_review", "paradigm_samples"}
_PACKAGE = (
    Path(__file__).parents[1]
    / "babeldoc"
    / "format"
    / "pdf"
    / "document_il"
    / "utils"
    / "layout_plan"
)


def _plan_for(lines, *, role="body", gate="single_page", on_photo=False):
    facts = build_facts(
        source_fingerprint="synthetic",
        page_index=0,
        page_width=612.0,
        page_height=792.0,
        input_gate=gate,
        text_health=0.9,
        blocks=[_block(lines, role=role, on_photo=on_photo)],
    )
    return facts, build_plan(facts)


def test_gold_labels_select_the_named_strategy():
    synthetic = [
        path
        for path in sorted(_GOLD.glob("*.json"))
        if json.loads(path.read_text(encoding="utf-8")).get("kind")
        not in _SCHEMA_ONLY_KINDS
    ]
    assert {path.name for path in synthetic} == {
        "rect_flow.json",
        "shaped_pocket.json",
    }
    for path in synthetic:
        gold = json.loads(path.read_text(encoding="utf-8"))
        lines = [tuple(line) for line in gold["lines"]]
        facts, plan = _plan_for(lines, role=gold["role"])
        decision = plan.decisions[0]
        assert decision.base_strategy == gold["expected_base"], path.name
        assert list(decision.modifiers) == gold["expected_modifiers"]
        assert decision.region_id == facts.regions[0].region_id


def test_corpus_visual_gold_is_schema_only():
    """Record looked-at labels. Do not require the live plugins to match."""
    paths = sorted(_GOLD.glob("corpus-*.json"))
    assert len(paths) == 22
    bases = {"rect_flow", "shaped_pocket", "list", "preserve"}
    gates = {"single_page", "spread", "image_only", "bad_encoding"}
    for path in paths:
        gold = json.loads(path.read_text(encoding="utf-8"))
        assert gold["kind"] == "corpus", path.name
        assert len(gold["source_pdf_hash"]) == 64
        assert isinstance(gold["page"], int) and gold["page"] >= 0
        assert gold["relpath"] and not gold["relpath"].startswith("/")
        assert gold["predicted_base"] in bases
        assert gold["predicted_gate"] in gates
        assert gold["expected_modifiers"] == []
        assert gold["reason"]
        for text in _strings(gold):
            assert not text.startswith("/")
        if gold["shape_judged"]:
            assert gold["expected_base"] in bases
            assert gold["expected_gate"] == "single_page"
            assert gold["region_id"]
            assert gold["lines"]
        else:
            assert gold["expected_gate"] in gates
            assert gold["expected_base"] in {None, "preserve"}


def test_short_taper_and_hanging_indent_preserve():
    short = [(100.0 + 12.0 * i, 570.0, 160.0 - 15.0 * i) for i in range(3)]
    _facts, plan = _plan_for(short)
    assert plan.decisions[0].base_strategy == "preserve"
    assert plan.decisions[0].fallback == "no_confident_base"

    hanging: list[tuple[float, float, float]] = []
    y = 400.0
    for _ in range(3):
        hanging.append((56.0, 540.0, y))
        y -= 16.0
        hanging.append((92.0, 540.0, y))
        y -= 16.0
        hanging.append((74.0, 220.0, y))
        y -= 16.0
        hanging.append((92.0, 540.0, y))
        y -= 20.0
    _facts, plan = _plan_for(hanging)
    assert plan.decisions[0].base_strategy == "preserve"


def test_kept_role_and_photo_text_preserve():
    lines = [(102.0, 570.0, 200.0 - 15.0 * i) for i in range(5)]
    for role in ("title", "list", "pull_quote", "chrome"):
        _facts, plan = _plan_for(lines, role=role)
        assert plan.decisions[0].base_strategy == "preserve"
    _facts, plan = _plan_for(lines, on_photo=True)
    assert plan.decisions[0].base_strategy == "preserve"


def test_spread_gate_does_not_classify():
    lines = [(102.0, 570.0, 200.0 - 15.0 * i) for i in range(5)]
    _facts, plan = _plan_for(lines, gate="spread")
    assert plan.decisions[0].base_strategy == "preserve"
    assert plan.decisions[0].fallback == "spread"
    assert plan.decisions[0].rejected[0].reason == "input_gate"


def test_region_id_is_stable_and_not_object_identity():
    lines = ((102.0, 570.0, 200.0), (102.0, 570.0, 185.0))
    first = make_region_id("abc", 1, 0, _boxes(lines))
    second = make_region_id("abc", 1, 0, _boxes(lines))
    shifted = make_region_id("abc", 1, 1, _boxes(lines))
    assert first == second
    assert first != shifted
    assert " " not in first


def test_same_column_relation_does_not_merge_groups():
    facts = build_facts(
        source_fingerprint="synthetic",
        page_index=0,
        page_width=612.0,
        page_height=792.0,
        input_gate="single_page",
        text_health=0.9,
        blocks=[
            _block([(102.0, 570.0, 400.0), (102.0, 570.0, 385.0)]),
            _block([(102.0, 570.0, 200.0), (102.0, 570.0, 185.0)]),
        ],
    )
    assert len(facts.regions) == 2
    assert facts.regions[0].below_id == facts.regions[1].region_id
    assert facts.regions[1].above_id == facts.regions[0].region_id
    assert facts.regions[1].region_id in facts.regions[0].same_column_ids


def test_tie_preserves_and_records_both_sides():
    facts, _plan = _plan_for([(102.0, 570.0, 200.0)])
    region_id = facts.regions[0].region_id
    contributions = [
        _base("plugin_a", region_id, "rect_flow", priority=10),
        _base("plugin_b", region_id, "shaped_pocket", priority=10),
    ]
    plan = resolve(facts, contributions)
    decision = plan.decisions[0]
    assert decision.base_strategy == "preserve"
    assert decision.fallback == "conflict_tie"
    assert {item.plugin_id for item in decision.rejected} == {"plugin_a", "plugin_b"}


def test_modifier_conflict_drops_both_values():
    facts, _plan = _plan_for([(102.0, 570.0, 200.0 - 15.0 * i) for i in range(5)])
    region_id = facts.regions[0].region_id
    extras = [
        _modifier(region_id, "avoid_figure:left"),
        _modifier(region_id, "avoid_figure:right"),
    ]
    plan = resolve(facts, [*_plugins_of(facts), *extras])
    decision = plan.decisions[0]
    assert decision.base_strategy == "rect_flow"
    assert decision.modifiers == ()
    assert any(item.reason == "modifier_conflict" for item in decision.rejected)


def test_consumer_reads_only_the_frozen_decision():
    _facts, plan = _plan_for([(102.0, 570.0, 200.0 - 15.0 * i) for i in range(5)])
    seen = consume_layout_plan(plan, plan.decisions[0].region_id)
    assert seen.base_strategy == "rect_flow"
    missing = consume_layout_plan(plan, "absent")
    assert missing.base_strategy == "preserve"
    assert missing.fallback == "missing_region"
    signature = inspect.signature(consume_layout_plan)
    assert list(signature.parameters) == ["plan", "region_id"]
    assert Typesetting.consume_layout_plan(plan, "absent").fallback == "missing_region"


def test_slice_sources_do_not_import_rect_reflow():
    paths = list(_PACKAGE.rglob("*.py"))
    paths.append(_PACKAGE.parent / "mixed_column_split.py")
    paths.append(_PACKAGE.parent / "rect_flow_stack.py")
    paths.append(_PACKAGE.parent / "list_flow_stack.py")
    paths.append(_PACKAGE.parent / "shaped_pocket_stack.py")
    paths.append(_PACKAGE.parent / "line_raster.py")
    for path in paths:
        text = path.read_text(encoding="utf-8")
        assert "rect_column_reflow" not in text
        assert "id(paragraph)" not in text
        assert "id(page)" not in text


def test_held_spans_belong_to_one_call_on_one_page():
    """A note stays on the page that stored it.

    A second page does not see it. A repeated note replaces the first.
    A legacy call that raises restores the paragraph list and drops the
    note before the next call.
    """
    import pytest
    from babeldoc.format.pdf.document_il.utils.layout_plan.model import LayoutPlan
    from babeldoc.format.pdf.document_il.utils.layout_plan.model import LineEdgeLink
    from babeldoc.format.pdf.document_il.utils.rect_flow_stack import clear_held_spans
    from babeldoc.format.pdf.document_il.utils.rect_flow_stack import (
        guard_rect_flow_paragraphs,
    )
    from babeldoc.format.pdf.document_il.utils.rect_flow_stack import held_column_spans
    from babeldoc.format.pdf.document_il.utils.rect_flow_stack import note_held_spans

    def _para(y, y2):
        box = type("Box", (), {"x": 10.0, "y": y, "x2": 40.0, "y2": y2})()
        return type("Paragraph", (), {"layout_region_id": "kept", "box": box})()

    def _page(paragraph):
        page = type("Page", (), {})()
        page.pdf_paragraph = [paragraph]
        page.layout_plan = LayoutPlan(
            "t",
            0,
            "single_page",
            (),
            line_edge_links=(LineEdgeLink("kept", ((10.0, 40.0),)),),
        )
        return page

    first = _para(10.0, 20.0)
    second = _para(30.0, 40.0)
    page_a = _page(first)
    page_b = _page(second)
    note_held_spans(page_a, [first])
    note_held_spans(page_b, [second])
    assert held_column_spans(page_a) == ((10.0, 20.0, 10.0, 40.0),)
    assert held_column_spans(page_b) == ((30.0, 40.0, 10.0, 40.0),)
    note_held_spans(page_a, [second])
    assert held_column_spans(page_a) == ((30.0, 40.0, 10.0, 40.0),)
    assert held_column_spans(page_b) == ((30.0, 40.0, 10.0, 40.0),)
    clear_held_spans(page_a)
    assert held_column_spans(page_a) == ()
    assert held_column_spans(page_b) == ((30.0, 40.0, 10.0, 40.0),)
    clear_held_spans(page_b)

    page = _page(first)
    with pytest.raises(RuntimeError):
        with guard_rect_flow_paragraphs(page):
            assert page.pdf_paragraph == []
            assert held_column_spans(page) == ((10.0, 20.0, 10.0, 40.0),)
            raise RuntimeError("stop")
    assert page.pdf_paragraph == [first]
    assert held_column_spans(page) == ()
    with guard_rect_flow_paragraphs(page):
        assert held_column_spans(page) == ((10.0, 20.0, 10.0, 40.0),)
    assert held_column_spans(page) == ()


def test_manifest_counts_and_lock_roundtrip(tmp_path: Path):
    root = tmp_path / "corpus"
    (root / "Book").mkdir(parents=True)
    _write_pdf(root / "Book" / "a.pdf", "A stable column of English words here.")
    manifest = build_manifest(root)
    assert manifest["pdf_count"] == 1
    assert manifest["files"][0]["path"] == "Book/a.pdf"
    assert not str(manifest["files"][0]["path"]).startswith("/")
    assert count_errors(manifest)
    copied = json.loads(json.dumps(manifest))
    assert lock_errors(manifest, copied) == []
    copied["files"][0]["sha256"] = "0" * 64
    assert any(item.startswith("changed ") for item in lock_errors(manifest, copied))


def test_pdf_scan_of_one_text_page_is_read_only(tmp_path: Path):
    path = tmp_path / "page.pdf"
    _write_pdf(path, "This is a readable English sentence for the gate.")
    before = path.read_bytes()
    records = scan_pdf(path, "abc")
    assert path.read_bytes() == before
    assert records[0]["input_gate"] == "single_page"
    assert records[0]["regions"]
    region = records[0]["regions"][0]
    assert "readable English sentence" in region["source_text"]
    assert region["marker"]["text"] == "T"
    assert region["marker"]["is_bullet"] is False


def test_text_and_marker_do_not_change_region_id():
    lines = [(102.0, 570.0, 400.0), (102.0, 400.0, 385.0)]
    bare = _facts_with(lines)
    marked = _facts_with(
        lines,
        text="A plain sentence with no marker.",
        marker=marker_from_glyph("A", "Times-Roman"),
    )
    assert bare.regions[0].region_id == marked.regions[0].region_id
    assert marked.regions[0].source_text == "A plain sentence with no marker."
    assert marked.regions[0].marker.is_bullet is False
    assert marked.regions[0].to_dict()["marker"]["font"] == "Times-Roman"
    with_relation = _facts_with(
        lines,
        text="Above.",
        marker=marker_from_glyph("A", "Times-Roman"),
        extra=[(102.0, 570.0, 200.0)],
        extra_text="Below.",
        extra_marker=marker_from_glyph("B", "Times-Roman"),
    )
    assert with_relation.regions[0].source_text == "Above."
    assert with_relation.regions[1].marker.text == "B"
    assert with_relation.regions[0].below_id == with_relation.regions[1].region_id


def test_marker_evidence_sees_bullets_and_empty_dingbats():
    bullet = marker_from_glyph("• Hello", "Times-Roman")
    assert bullet.text == "•"
    assert bullet.is_bullet is True
    webdings = marker_from_glyph("Q", "Webdings")
    assert webdings.text == "Q"
    assert webdings.is_bullet is True
    empty = marker_from_glyph("", "Wingdings-Regular")
    assert empty.text == ""
    assert empty.is_bullet is True
    letter = marker_from_glyph("A", "Times-Roman")
    assert letter.text == "A"
    assert letter.is_bullet is False
    dingbat_word = marker_from_glyph("Hello", "Webdings")
    assert dingbat_word.text == "H"
    assert dingbat_word.is_bullet is False
    spaced = marker_from_glyph("  Hello", "Times-Roman")
    assert spaced.text == "H"
    assert spaced.is_bullet is False
    leading = first_marker(
        [
            {"spans": [{"text": "", "font": "Webdings"}]},
            {"spans": [{"text": "Hello", "font": "Times-Roman"}]},
        ]
    )
    assert leading is not None
    assert leading.text == ""
    assert leading.is_bullet is True
    assert first_marker([{"spans": [{"text": "  ", "font": "Times-Roman"}]}]) is None


def test_hanging_indent_without_a_marker_stays_preserve():
    hanging: list[tuple[float, float, float]] = []
    y = 400.0
    for _ in range(3):
        hanging.append((56.0, 540.0, y))
        y -= 16.0
        hanging.append((92.0, 540.0, y))
        y -= 16.0
        hanging.append((74.0, 220.0, y))
        y -= 16.0
        hanging.append((92.0, 540.0, y))
        y -= 20.0
    facts = _facts_with(
        hanging,
        text="The sentence continues without a bullet or a number.",
        marker=marker_from_glyph("T", "Times-Roman"),
    )
    plan = build_plan(facts)
    assert facts.regions[0].marker.is_bullet is False
    assert plan.decisions[0].base_strategy == "preserve"


def test_numbered_column_is_list_and_not_rect_flow():
    lines = [(102.0, 570.0, 400.0 - 16.0 * index) for index in range(6)]
    facts = _facts_with(
        lines,
        text="1. Warm up before the first exercise.",
        marker=marker_from_glyph(
            "1. Warm up before the first exercise.", "Times-Roman"
        ),
    )
    decision = build_plan(facts).decisions[0]
    assert decision.base_strategy == "list"
    assert decision.plugin_id == "list_flow"
    assert [item.value for item in _plugins_of(facts)] == ["list"]


def test_bullet_and_empty_dingbat_are_list():
    lines = [(102.0, 570.0, 400.0 - 16.0 * index) for index in range(4)]
    bullet = _facts_with(
        lines,
        text="• Hold the stretch.",
        marker=marker_from_glyph("• Hold the stretch.", "Times-Roman"),
    )
    assert build_plan(bullet).decisions[0].base_strategy == "list"
    empty = _facts_with(
        lines,
        text="",
        marker=marker_from_glyph("", "Wingdings-Regular"),
    )
    assert build_plan(empty).decisions[0].base_strategy == "list"
    word = _facts_with(
        lines,
        text="Hello from a dingbat face.",
        marker=marker_from_glyph("Hello", "Webdings"),
    )
    decision = build_plan(word).decisions[0]
    assert word.regions[0].marker.is_bullet is False
    assert decision.base_strategy == "rect_flow"


def test_bullet_on_a_stair_stays_preserve():
    """A bullet does not beat a real stair, and the stair does not beat the bullet."""
    stair = [
        (100.0, 570.0, 160.0),
        (112.0, 570.0, 145.0),
        (124.0, 570.0, 130.0),
        (136.0, 570.0, 115.0),
    ]
    facts = _facts_with(
        stair,
        text="• The free edge steps inward.",
        marker=marker_from_glyph("• The free edge steps inward.", "Times-Roman"),
    )
    decision = build_plan(facts).decisions[0]
    assert decision.base_strategy == "preserve"
    assert decision.fallback == "list_and_shaped"
    assert {item.plugin_id for item in decision.rejected} == {
        "list_flow",
        "shaped_pocket",
    }
    assert {item.reason for item in decision.rejected} == {"list_and_shaped"}


def test_shaped_review_gold_records_eight_keeps_and_twenty_rejects():
    """The 8/20 visual list. The live plugin is not required to match it.

    Line boxes do not separate the eight keeps from the twenty rejects.
    A cutoff fitted to this file is not a rule. Figure boxes come later.
    """
    path = _GOLD / "shaped_review.json"
    gold = json.loads(path.read_text(encoding="utf-8"))
    assert gold["kind"] == "shaped_review"
    items = gold["items"]
    assert len(items) == 28
    keeps = [item for item in items if item["expected_shaped_pocket"] is True]
    rejects = [item for item in items if item["expected_shaped_pocket"] is False]
    assert len(keeps) == 8
    assert len(rejects) == 20
    region_ids = [item["region_id"] for item in items]
    assert len(region_ids) == len(set(region_ids))
    for item in items:
        assert len(item["source_pdf_hash"]) == 64
        assert item["relpath"] and not item["relpath"].startswith("/")
        assert isinstance(item["page"], int) and item["page"] >= 0
        assert isinstance(item["box"], int) and item["box"] >= 1
        assert isinstance(item["source_order"], int)
        assert item["lines"]
        assert item["reason"]
        for text in _strings(item):
            assert not text.startswith("/")
        rebuilt = make_region_id(
            item["source_pdf_hash"],
            item["page"],
            item["source_order"],
            tuple(LineBox(*line) for line in item["lines"]),
        )
        assert rebuilt == item["region_id"]


def test_expected_corpus_counts_are_the_source_walk():
    assert EXPECTED_PDF_COUNT == 131
    assert EXPECTED_TOP_LEVEL_DIRECTORIES == 101


def test_derived_translations_are_left_out_of_the_manifest(tmp_path: Path):
    from babeldoc.format.pdf.document_il.utils.layout_plan.corpus import (
        is_derived_translation,
    )
    from babeldoc.format.pdf.document_il.utils.layout_plan.corpus import list_pdfs

    root = tmp_path / "corpus"
    book = root / "Book"
    book.mkdir(parents=True)
    names = (
        "Book.pdf",
        "Book.zh.pdf",
        "Book.zh-CN.mono.pdf",
        "Book.no_watermark.zh-CN.dual.pdf",
    )
    for name in names:
        (book / name).write_bytes(b"%PDF-1.4\n")
    listed = list_pdfs(root)
    assert [path.name for path in listed] == ["Book.pdf"]
    assert is_derived_translation(book / "Book.zh.pdf")
    assert not is_derived_translation(book / "Book.pdf")


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def _boxes(lines):
    return tuple(LineBox(*line) for line in lines)


def _block(lines, *, role=None, on_photo=False, text="", marker=None) -> SourceBlock:
    return SourceBlock(
        lines=tuple(LineBox(*line) for line in lines),
        role=role,
        text_on_photo=on_photo,
        source_text=text,
        marker=marker,
    )


def _facts_with(
    lines,
    *,
    text="",
    marker=None,
    extra=None,
    extra_text="",
    extra_marker=None,
):
    blocks = [_block(lines, text=text, marker=marker)]
    if extra:
        blocks.append(_block(extra, text=extra_text, marker=extra_marker))
    return build_facts(
        source_fingerprint="synthetic",
        page_index=0,
        page_width=612.0,
        page_height=792.0,
        input_gate="single_page",
        text_health=0.9,
        blocks=blocks,
    )


def _base(plugin_id: str, region_id: str, value: str, *, priority: int):
    return PlanContribution(
        plugin_id=plugin_id,
        plugin_version="1",
        target_region_id=region_id,
        kind="base_strategy",
        value=value,
        confidence=0.9,
        priority=priority,
        evidence=(Evidence("test", value),),
        fallback="preserve",
    )


def _modifier(region_id: str, value: str):
    return PlanContribution(
        plugin_id="modifier_test",
        plugin_version="1",
        target_region_id=region_id,
        kind="modifier",
        value=value,
        confidence=0.9,
        priority=1,
        evidence=(Evidence("test", value),),
        fallback=None,
    )


def _column_lines(x0, x1, top):
    return [(float(x0), float(x1), float(top - 15.0 * i)) for i in range(4)]


def _facts_blocks(blocks):
    return build_facts(
        source_fingerprint="synthetic",
        page_index=0,
        page_width=612.0,
        page_height=792.0,
        input_gate="single_page",
        text_health=0.9,
        blocks=blocks,
    )


def _links_by_id(plan):
    return {link.region_id: link for link in plan.column_links}


def _list_links_by_id(plan):
    return {link.region_id: link for link in plan.list_links}


def _bullet_block(lines, text="• Hold the stretch."):
    return _block(
        lines,
        role="body",
        text=text,
        marker=marker_from_glyph(text, "Times-Roman"),
    )


def _number_block(lines, text="2. The next item sits under the first."):
    return _block(
        lines,
        role="body",
        text=text,
        marker=marker_from_glyph(text, "Times-Roman"),
    )


def test_sidebar_does_not_join_the_rect_chain():
    """0.35 overlap still points at the sidebar. The rect chain does not."""
    upper = _column_lines(72, 400, 500)
    sidebar = _column_lines(330, 470, 420)
    lower = _column_lines(72, 400, 300)
    facts = _facts_blocks(
        [
            _block(upper, role="body"),
            _block(sidebar, role="body"),
            _block(lower, role="body"),
        ]
    )
    plan = build_plan(facts)
    upper_id = facts.regions[0].region_id
    sidebar_id = facts.regions[1].region_id
    lower_id = facts.regions[2].region_id
    assert facts.regions[0].below_id == sidebar_id
    links = _links_by_id(plan)
    assert links[upper_id].flow_next_id == lower_id
    assert links[sidebar_id].flow_next_id is None
    assert links[upper_id].column_chain_id == links[lower_id].column_chain_id
    assert links[sidebar_id].column_chain_id != links[upper_id].column_chain_id
    assert links[upper_id].column_left == 72.0
    assert links[upper_id].column_right == 400.0
    assert links[sidebar_id].column_right == 470.0


def test_quote_and_title_break_the_rect_chain():
    upper = _column_lines(72, 400, 500)
    lower = _column_lines(72, 400, 300)
    between = _column_lines(72, 400, 400)
    beside = _column_lines(430, 560, 400)
    for role in ("pull_quote", "title"):
        facts = _facts_blocks(
            [
                _block(upper, role="body"),
                _block(between, role=role),
                _block(lower, role="body"),
            ]
        )
        plan = build_plan(facts)
        links = _links_by_id(plan)
        upper_id = facts.regions[0].region_id
        lower_id = facts.regions[2].region_id
        assert facts.regions[0].below_id == facts.regions[1].region_id
        assert facts.regions[1].region_id not in links
        assert links[upper_id].flow_next_id is None
        assert links[upper_id].column_chain_id != links[lower_id].column_chain_id

    open_facts = _facts_blocks(
        [_block(upper, role="body"), _block(lower, role="body")]
    )
    open_plan = build_plan(open_facts)
    open_links = _links_by_id(open_plan)
    assert (
        open_links[open_facts.regions[0].region_id].flow_next_id
        == open_facts.regions[1].region_id
    )
    assert (
        open_links[open_facts.regions[0].region_id].column_chain_id
        == open_links[open_facts.regions[1].region_id].column_chain_id
    )

    side_facts = _facts_blocks(
        [
            _block(upper, role="body"),
            _block(beside, role="pull_quote"),
            _block(lower, role="body"),
        ]
    )
    side_plan = build_plan(side_facts)
    side_links = _links_by_id(side_plan)
    assert (
        side_links[side_facts.regions[0].region_id].flow_next_id
        == side_facts.regions[2].region_id
    )
    assert (
        side_links[side_facts.regions[0].region_id].column_chain_id
        == side_links[side_facts.regions[2].region_id].column_chain_id
    )


def test_two_rect_paragraphs_pack_without_stretching_leading():
    assert pack_offsets(
        [("a", 400.0, 360.0), ("a", 200.0, 160.0)], 6.0
    ) == [0.0, 154.0]
    assert pack_offsets(
        [("a", 400.0, 360.0), ("b", 200.0, 160.0)], 6.0
    ) == [0.0, 0.0]
    assert line_slots(328.0, 3) == [328.0, 328.0, 328.0]

    upper = _column_lines(72, 400, 500)
    lower = _column_lines(72, 400, 300)
    facts = _facts_blocks(
        [_block(upper, role="body"), _block(lower, role="body")]
    )
    plan = build_plan(facts)
    linked = _links_by_id(plan)
    assert linked[facts.regions[0].region_id].paragraph_gap == 0.0
    assert linked[facts.regions[1].region_id].paragraph_gap == 140.0
    first = _placed_paragraph(
        facts.regions[0].region_id,
        box=_Box(80, 360, 300, 420),
        chars=[_Char(360, 378)],
        widths=[400.0, 400.0, 80.0],
    )
    second_chars = [_Char(182, 200), _Char(164, 182)]
    second = _placed_paragraph(
        facts.regions[1].region_id,
        box=_Box(90, 160, 280, 200),
        chars=second_chars,
        widths=[400.0, 400.0, 80.0],
    )
    page = _Page([first, second], plan)
    assign_rect_flow_boxes(page)
    assert first.box.x == 72.0
    assert first.box.x2 == 400.0
    assert second.box.x == 72.0
    assert second.box.x2 == 400.0
    assert first.alignment == "left"
    assert second.alignment == "left"
    assert first.reference_metrics.per_line_widths == [328.0, 328.0, 328.0]
    assert 80.0 not in second.reference_metrics.per_line_widths

    pack_rect_flow(page, paragraph_gap=6.0)
    assert second.box.y2 == 354.0
    assert second_chars[0].box.y2 == 354.0
    assert second_chars[1].box.y2 == 336.0
    assert second_chars[0].box.y2 - second_chars[1].box.y2 == 18.0
    assert first.box.y == 360.0


def test_a_paragraph_break_keeps_the_scanned_white():
    upper = [(56.0, 400.0, 100.0), (56.0, 400.0, 85.0), (56.0, 400.0, 70.0)]
    lower = [(56.0, 400.0, 47.0), (56.0, 400.0, 32.0), (56.0, 400.0, 17.0)]
    assert scanned_paragraph_gap(_boxes(upper), _boxes(lower)) == 8.0
    tight = [(56.0, 400.0, 55.0), (56.0, 400.0, 40.0), (56.0, 400.0, 25.0)]
    assert scanned_paragraph_gap(_boxes(upper), _boxes(tight)) == 0.0

    facts = _facts_blocks([_block(upper, role="body"), _block(lower, role="body")])
    plan = build_plan(facts)
    linked = _links_by_id(plan)
    assert linked[facts.regions[1].region_id].paragraph_gap == 8.0
    first = _placed_paragraph(
        facts.regions[0].region_id,
        box=_Box(56, 360, 400, 378),
        chars=[_Char(360, 378)],
    )
    second_chars = [_Char(182, 200), _Char(164, 182)]
    second = _placed_paragraph(
        facts.regions[1].region_id,
        box=_Box(56, 160, 400, 200),
        chars=second_chars,
    )
    pack_rect_flow(_Page([first, second], plan))
    assert second.box.y2 == 352.0
    assert second_chars[0].box.y2 - second_chars[1].box.y2 == 18.0

    tight_facts = _facts_blocks(
        [_block(upper, role="body"), _block(tight, role="body")]
    )
    tight_plan = build_plan(tight_facts)
    assert (
        _links_by_id(tight_plan)[tight_facts.regions[1].region_id].paragraph_gap
        == 0.0
    )
    tight_second = _placed_paragraph(
        tight_facts.regions[1].region_id,
        box=_Box(56, 160, 400, 200),
        chars=[_Char(182, 200)],
    )
    tight_first = _placed_paragraph(
        tight_facts.regions[0].region_id,
        box=_Box(56, 360, 400, 378),
        chars=[_Char(360, 378)],
    )
    pack_rect_flow(_Page([tight_first, tight_second], tight_plan))
    assert tight_second.box.y2 == 357.0

    # The glyph box is shorter than the line step. The break is one step
    # plus the scanned white, measured from line top to line top.
    short_upper = _placed_paragraph(
        facts.regions[0].region_id,
        box=_Box(56, 380, 400, 400),
        chars=[_Char(396, 400), _Char(380, 384)],
    )
    short_lower = _placed_paragraph(
        facts.regions[1].region_id,
        box=_Box(56, 196, 400, 200),
        chars=[_Char(196, 200)],
    )
    pack_rect_flow(_Page([short_upper, short_lower], plan))
    assert short_lower.box.y2 == 360.0


def _wandering(top: float) -> list[tuple[float, float, float]]:
    """Three lines whose left edge walks, so the column plugins leave them."""
    return [
        (56.0, 400.0, top),
        (70.0, 400.0, top - 15.0),
        (90.0, 380.0, top - 30.0),
    ]


def test_an_unmatched_body_keeps_the_scanned_paragraph_white():
    """Preserve bodies in one column use the same scanned white as a rect chain."""
    upper = _wandering(100.0)
    lower = _wandering(47.0)
    assert scanned_paragraph_gap(_boxes(upper), _boxes(lower)) == 8.0
    facts = _facts_blocks([_block(upper, role="body"), _block(lower, role="body")])
    plan = build_plan(facts)
    assert plan.decisions[0].base_strategy == "preserve"
    assert plan.decisions[1].base_strategy == "preserve"
    assert plan.column_links == ()
    assert plan.paragraph_gap_links[0].region_id == facts.regions[1].region_id
    assert plan.paragraph_gap_links[0].above_id == facts.regions[0].region_id
    assert plan.paragraph_gap_links[0].paragraph_gap == 8.0
    first = _placed_paragraph(
        facts.regions[0].region_id,
        box=_Box(56, 360, 400, 378),
        chars=[_Char(360, 378)],
    )
    second_chars = [_Char(182, 200), _Char(164, 182)]
    second = _placed_paragraph(
        facts.regions[1].region_id,
        box=_Box(56, 160, 400, 200),
        chars=second_chars,
    )
    page = _Page([first, second], plan)
    pack_rect_flow(page)
    assert second.box.y2 == 200.0
    pack_body_paragraphs(page)
    assert second.box.y2 == 352.0
    assert second_chars[0].box.y2 - second_chars[1].box.y2 == 18.0


def test_a_tight_unmatched_break_uses_the_three_point_fallback():
    upper = _wandering(100.0)
    tight = _wandering(55.0)
    assert scanned_paragraph_gap(_boxes(upper), _boxes(tight)) == 0.0
    facts = _facts_blocks([_block(upper, role="body"), _block(tight, role="body")])
    plan = build_plan(facts)
    assert plan.paragraph_gap_links[0].paragraph_gap == 0.0
    second = _placed_paragraph(
        facts.regions[1].region_id,
        box=_Box(56, 160, 400, 200),
        chars=[_Char(182, 200)],
    )
    first = _placed_paragraph(
        facts.regions[0].region_id,
        box=_Box(56, 360, 400, 378),
        chars=[_Char(360, 378)],
    )
    pack_body_paragraphs(_Page([first, second], plan))
    assert second.box.y2 == 357.0


def test_a_title_keeps_the_next_body_on_its_box():
    upper = _wandering(100.0)
    between = [(56.0, 400.0, 60.0)]
    lower = _wandering(47.0)
    facts = _facts_blocks(
        [
            _block(upper, role="body"),
            _block(between, role="title"),
            _block(lower, role="body"),
        ]
    )
    plan = build_plan(facts)
    assert plan.paragraph_gap_links == ()
    second = _placed_paragraph(
        facts.regions[2].region_id,
        box=_Box(56, 160, 400, 200),
        chars=[_Char(182, 200)],
    )
    pack_body_paragraphs(_Page([second], plan))
    assert second.box.y2 == 200.0


def test_an_outdented_title_keeps_the_next_body_on_its_box():
    upper = [(102.0, 540.0, 200.0), (116.0, 500.0, 185.0), (130.0, 480.0, 170.0)]
    title = [(78.0, 302.0, 140.0)]
    lower = [(102.0, 540.0, 100.0), (116.0, 500.0, 85.0), (130.0, 480.0, 70.0)]
    facts = _facts_blocks(
        [
            _block(upper, role="body"),
            _block(title, role="title"),
            _block(lower, role="body"),
        ]
    )
    plan = build_plan(facts)
    assert plan.paragraph_gap_links == ()
    second = _placed_paragraph(
        facts.regions[2].region_id,
        box=_Box(102, 160, 540, 200),
        chars=[_Char(182, 200)],
    )
    pack_body_paragraphs(_Page([second], plan))
    assert second.box.y2 == 200.0


def test_a_side_title_off_the_column_keeps_the_paragraph_gap():
    upper = [(102.0, 400.0, 200.0), (116.0, 380.0, 185.0), (130.0, 360.0, 170.0)]
    side = [(430.0, 560.0, 140.0)]
    lower = [(102.0, 400.0, 100.0), (116.0, 380.0, 85.0), (130.0, 360.0, 70.0)]
    facts = _facts_blocks(
        [
            _block(upper, role="body"),
            _block(side, role="title"),
            _block(lower, role="body"),
        ]
    )
    plan = build_plan(facts)
    assert len(plan.paragraph_gap_links) == 1
    assert plan.paragraph_gap_links[0].region_id == facts.regions[2].region_id
    assert plan.paragraph_gap_links[0].above_id == facts.regions[0].region_id


def test_a_rect_follower_is_not_seated_twice():
    upper = [(56.0, 400.0, 100.0), (56.0, 400.0, 85.0), (56.0, 400.0, 70.0)]
    lower = [(56.0, 400.0, 47.0), (56.0, 400.0, 32.0), (56.0, 400.0, 17.0)]
    facts = _facts_blocks([_block(upper, role="body"), _block(lower, role="body")])
    plan = build_plan(facts)
    assert plan.decisions[0].base_strategy == "rect_flow"
    assert plan.paragraph_gap_links == ()
    second_chars = [_Char(182, 200)]
    second = _placed_paragraph(
        facts.regions[1].region_id,
        box=_Box(56, 160, 400, 200),
        chars=second_chars,
    )
    first = _placed_paragraph(
        facts.regions[0].region_id,
        box=_Box(56, 360, 400, 378),
        chars=[_Char(360, 378)],
    )
    page = _Page([first, second], plan)
    pack_rect_flow(page)
    assert second.box.y2 == 352.0
    pack_body_paragraphs(page)
    assert second.box.y2 == 352.0


def test_a_rect_column_under_an_unmatched_body_moves_together():
    """The rect chain keeps its own gap. The whole chain drops by the body gap."""
    upper = _wandering(200.0)
    mid = [(56.0, 400.0, 147.0), (56.0, 400.0, 132.0), (56.0, 400.0, 117.0)]
    tail = [(56.0, 400.0, 94.0), (56.0, 400.0, 79.0), (56.0, 400.0, 64.0)]
    facts = _facts_blocks(
        [
            _block(upper, role="body"),
            _block(mid, role="body"),
            _block(tail, role="body"),
        ]
    )
    plan = build_plan(facts)
    assert plan.decisions[0].base_strategy == "preserve"
    assert plan.decisions[1].base_strategy == "rect_flow"
    assert plan.decisions[2].base_strategy == "rect_flow"
    assert len(plan.paragraph_gap_links) == 1
    assert plan.paragraph_gap_links[0].region_id == facts.regions[1].region_id
    assert plan.paragraph_gap_links[0].paragraph_gap == 8.0
    head_chars = [_Char(182, 200)]
    tail_chars = [_Char(100, 118)]
    head = _placed_paragraph(
        facts.regions[1].region_id,
        box=_Box(56, 182, 400, 200),
        chars=head_chars,
    )
    follower = _placed_paragraph(
        facts.regions[2].region_id,
        box=_Box(56, 100, 400, 118),
        chars=tail_chars,
    )
    above = _placed_paragraph(
        facts.regions[0].region_id,
        box=_Box(56, 360, 400, 378),
        chars=[_Char(360, 378)],
    )
    page = _Page([above, head, follower], plan)
    pack_rect_flow(page)
    assert head.box.y2 == 200.0
    assert follower.box.y2 == 174.0
    pack_body_paragraphs(page)
    assert head.box.y2 == 352.0
    assert follower.box.y2 == 326.0
    assert head_chars[0].box.y2 - tail_chars[0].box.y2 == 26.0


def test_a_pocket_does_not_pull_a_rect_through_a_body_gap():
    """The body gap seats the column. The later pocket pull leaves it there."""
    dy = 400.0
    stair = [(x0, x1, y + dy) for x0, x1, y in _STAIR]
    figures = tuple(
        FigureBox(item.x0, item.y0 + dy, item.x1, item.y1 + dy)
        for item in _STAIR_FIGURES
    )
    upper = _wandering(470.0)
    column = [(56.0, 400.0, 400.0), (56.0, 400.0, 385.0), (56.0, 400.0, 370.0)]
    assert scanned_paragraph_gap(_boxes(upper), _boxes(column)) == 25.0
    facts = build_facts(
        source_fingerprint="synthetic",
        page_index=0,
        page_width=612.0,
        page_height=792.0,
        input_gate="single_page",
        text_health=0.9,
        blocks=[
            _block(stair),
            _block(upper, role="body"),
            _block(column, role="body"),
        ],
        figures=figures,
    )
    plan = build_plan(facts)
    assert [item.base_strategy for item in plan.decisions] == [
        "shaped_pocket",
        "preserve",
        "rect_flow",
    ]
    assert plan.pocket_links
    assert len(plan.paragraph_gap_links) == 1
    assert plan.paragraph_gap_links[0].region_id == facts.regions[2].region_id
    assert plan.paragraph_gap_links[0].above_id == facts.regions[1].region_id
    assert plan.paragraph_gap_links[0].paragraph_gap == 25.0
    pocket = _placed_paragraph(
        facts.regions[0].region_id,
        box=_Box(150.0, 500.0, 570.0, 520.0),
        chars=[_Char(500.0, 520.0)],
    )
    above = _placed_paragraph(
        facts.regions[1].region_id,
        box=_Box(56.0, 360.0, 400.0, 378.0),
        chars=[_Char(360.0, 378.0)],
    )
    head = _placed_paragraph(
        facts.regions[2].region_id,
        box=_Box(56.0, 182.0, 400.0, 200.0),
        chars=[_Char(182.0, 200.0)],
    )
    page = _Page([pocket, above, head], plan)
    pack_rect_flow(page)
    pack_body_paragraphs(page)
    assert head.box.y2 == 335.0
    pack_shaped_pockets(page)
    # Pocket ink bottom 500 and the 3pt fallback would land this column at 497.
    assert head.box.y2 == 335.0


def _shelf(*rights: float, left: float = 50.0, top: float = 400.0, pitch: float = 15.0):
    from babeldoc.format.pdf.document_il.utils.layout_plan.model import ContourLevel

    return tuple(
        ContourLevel(left, right, top - index * pitch, "observed")
        for index, right in enumerate(rights)
    )


def test_a_narrow_pack_continues_down_onto_the_wide_lines():
    from unittest.mock import MagicMock

    from babeldoc.format.pdf.document_il.il_version_1 import Box
    from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter
    from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
    from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
    from babeldoc.format.pdf.document_il.il_version_1 import VisualBbox
    from babeldoc.format.pdf.document_il.midend.typesetting import Typesetting
    from babeldoc.format.pdf.document_il.midend.typesetting import TypesettingUnit
    from babeldoc.format.pdf.document_il.utils.layout_plan.model import LineEdgeLink
    from babeldoc.format.pdf.translation_config import TranslationConfig
    from babeldoc.translator.fixed_map_translator import FixedMapTranslator

    levels = _shelf(*([150.0] * 6), *([450.0] * 3))
    link = LineEdgeLink(
        "step",
        tuple((level.left, level.right, level.top) for level in levels),
        "left",
        "edge",
        levels,
    )
    host = Box(x=50, y=0, x2=450, y2=500)
    paragraph = PdfParagraph(
        box=host,
        pdf_style=PdfStyle(font_id="base", font_size=12, graphic_state=None),
        pdf_paragraph_composition=[],
        unicode="测试",
        debug_id="shelf",
    )

    def _glyph() -> TypesettingUnit:
        glyph = Box(x=0, y=0, x2=10, y2=12)
        char = PdfCharacter(
            char_unicode="中",
            box=glyph,
            visual_bbox=VisualBbox(box=Box(x=0, y=0, x2=10, y2=12)),
            pdf_style=PdfStyle(font_id="base", font_size=12, graphic_state=None),
        )
        return TypesettingUnit(char=char)

    ts = Typesetting(
        TranslationConfig(
            translator=FixedMapTranslator(),
            input_file="shelf.pdf",
            lang_in="en",
            lang_out="zh-CN",
            doc_layout_model=MagicMock(),
            auto_extract_glossary=False,
        )
    )
    ts._line_edges = link
    ts._pocket_link = None
    fitted, fitted_ok = ts._layout_typesetting_units(
        [_glyph() for _ in range(100)],
        host,
        1.0,
        1.05,
        paragraph,
        use_english_line_break=False,
    )
    assert fitted_ok is True
    assert len(fitted) == 100
    lines: dict[float, list] = {}
    for unit in fitted:
        lines.setdefault(round(unit.box.y, 1), []).append(unit)
    tops = sorted(lines, reverse=True)
    gaps = [tops[index] - tops[index + 1] for index in range(len(tops) - 1)]
    assert max(gaps) < 20.0
    # One full wide line, then a short last line. The column stays up.
    wide = [
        top
        for top in tops
        if max(unit.box.x2 for unit in lines[top]) > 400.0
    ]
    assert wide == [tops[-2]]
    assert tops[0] > 340.0
    last = lines[tops[-1]]
    assert max(unit.box.x2 for unit in last) < 360.0
    assert min(unit.box.x for unit in last) == 50.0
    estimated = ts._estimate_line_widths(
        [_glyph() for _ in range(100)],
        host,
        1.0,
        12.0,
        1.2,
        paragraph=paragraph,
        font_size=12.0,
    )
    wide_at = next(index for index, width in enumerate(estimated) if width > 300.0)
    assert estimated[0] < 150.0
    assert wide_at <= 5


def test_a_short_last_line_on_the_lower_shelf_meets_the_right_edge():
    from unittest.mock import MagicMock

    from babeldoc.format.pdf.document_il.il_version_1 import Box
    from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter
    from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
    from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
    from babeldoc.format.pdf.document_il.il_version_1 import VisualBbox
    from babeldoc.format.pdf.document_il.midend.typesetting import Typesetting
    from babeldoc.format.pdf.document_il.midend.typesetting import TypesettingUnit
    from babeldoc.format.pdf.document_il.utils.layout_plan.line_edges import shelf_drop
    from babeldoc.format.pdf.document_il.utils.layout_plan.model import LineEdgeLink
    from babeldoc.format.pdf.translation_config import TranslationConfig
    from babeldoc.translator.fixed_map_translator import FixedMapTranslator

    straight = _shelf(*([150.0] * 6), *([450.0] * 3))
    # Tail is 1.5 wide lines. One narrow line holds the rest.
    assert shelf_drop(straight, [10.0] * 65) == 400.0 - 5 * 15.0
    assert shelf_drop(straight, [10.0] * 150) is None
    wobble = _shelf(160, 150, 168, 155, 170, 152, 450, 450, 450)
    assert shelf_drop(wobble, [10.0] * 65) is None
    inset = _shelf(*([450.0] * 4), *([250.0] * 3), *([450.0] * 3))
    assert shelf_drop(inset, [10.0] * 65) is None
    spur = _shelf(*([150.0] * 6), 450.0)
    assert shelf_drop(spur, [10.0] * 65) is None

    link = LineEdgeLink(
        "step",
        tuple((level.left, level.right, level.top) for level in straight),
        "left",
        "edge",
        straight,
    )
    host = Box(x=50, y=0, x2=450, y2=500)
    paragraph = PdfParagraph(
        box=host,
        pdf_style=PdfStyle(font_id="base", font_size=12, graphic_state=None),
        pdf_paragraph_composition=[],
        unicode="测试",
        debug_id="shelf-last",
    )

    def _glyph() -> TypesettingUnit:
        glyph = Box(x=0, y=0, x2=10, y2=12)
        char = PdfCharacter(
            char_unicode="中",
            box=glyph,
            visual_bbox=VisualBbox(box=Box(x=0, y=0, x2=10, y2=12)),
            pdf_style=PdfStyle(font_id="base", font_size=12, graphic_state=None),
        )
        return TypesettingUnit(char=char)

    ts = Typesetting(
        TranslationConfig(
            translator=FixedMapTranslator(),
            input_file="shelf.pdf",
            lang_in="en",
            lang_out="zh-CN",
            doc_layout_model=MagicMock(),
            auto_extract_glossary=False,
        )
    )
    ts._line_edges = link
    ts._pocket_link = None
    fitted, fitted_ok = ts._layout_typesetting_units(
        [_glyph() for _ in range(65)],
        host,
        1.0,
        1.05,
        paragraph,
        use_english_line_break=False,
    )
    assert fitted_ok is True
    lines: dict[float, list] = {}
    for unit in fitted:
        lines.setdefault(round(unit.box.y, 1), []).append(unit)
    tops = sorted(lines, reverse=True)
    assert tops[-2] - tops[-1] < 20.0
    assert max(unit.box.x2 for unit in lines[tops[-2]]) > 400.0
    last = sorted(lines[tops[-1]], key=lambda unit: unit.box.x)
    assert max(unit.box.x2 for unit in last) < 320.0
    steps = [
        last[index].box.x - last[index - 1].box.x
        for index in range(1, len(last))
    ]
    assert max(steps) < 15.0


def test_a_long_narrow_run_stays_high_and_leaves_a_short_tail():
    from babeldoc.format.pdf.document_il.utils.layout_plan.line_edges import shelf_drop

    long = _shelf(*([150.0] * 12), *([450.0] * 3))
    # Tail is 600. Ten narrow lines hold the rest, so the column
    # starts at sample 2 rather than handing those lines to the shelf.
    assert shelf_drop(long, [10.0] * 160) == 400.0 - 2 * 15.0
    assert shelf_drop(long, [10.0] * 400) is None


def test_a_dropped_column_keeps_the_heading_on_its_gap():
    from babeldoc.format.pdf.document_il.utils.paragraph_gap_stack import (
        seat_dropped_headings,
    )

    def _para(lines):
        chars = [_ink_char(x, y, x2, y2) for x, x2, y, y2 in lines]
        composition = type(
            "_Comp",
            (),
            {
                "pdf_line": type(
                    "_Line",
                    (),
                    {"box": None, "pdf_character": chars},
                )(),
                "pdf_formula": None,
                "pdf_character": None,
                "pdf_same_style_characters": None,
            },
        )()
        paragraph = type("_Para", (), {})()
        paragraph.box = _Box(lines[0][0], lines[-1][2], lines[0][1], lines[0][3])
        paragraph.pdf_paragraph_composition = [composition]
        return paragraph

    body = _para(((66, 211, 418, 430), (66, 211, 403, 415)))
    heading = _para(((114, 162, 550, 562),))
    bar = _para(((66, 500, 476, 488),))
    header = _para(((66, 160, 736, 748),))
    page = type("_Page", (), {"pdf_paragraph": [header, heading, bar, body]})()
    seat_dropped_headings(page, {id(body): 120.0})
    assert heading.box.y2 == 442.0
    glyph = heading.pdf_paragraph_composition[0].pdf_line.pdf_character[0]
    assert glyph.box.y2 == 442.0
    assert bar.box.y2 == 488.0
    assert header.box.y2 == 748.0
    assert body.box.y2 == 430.0
    stayed = _para(((114, 162, 550, 562),))
    seat_dropped_headings(
        type("_Page", (), {"pdf_paragraph": [stayed, body]})(),
        {id(body): 4.0},
    )
    assert stayed.box.y2 == 562.0


def test_a_stair_without_a_figure_is_not_a_body_gap():
    """No figure link yet. The stair stays put, and so does the rect under it."""
    dx = 56.0 - _STAIR[0][0]
    stair = [(x0 + dx, x1 + dx, y) for x0, x1, y in _STAIR]
    upper = [(56.0, 400.0, 200.0), (70.0, 400.0, 185.0), (90.0, 380.0, 170.0)]
    column = [(56.0, 400.0, 80.0), (56.0, 400.0, 65.0), (56.0, 400.0, 50.0)]
    above_facts = build_facts(
        source_fingerprint="synthetic",
        page_index=0,
        page_width=612.0,
        page_height=792.0,
        input_gate="single_page",
        text_health=0.9,
        blocks=[_block(upper, role="body"), _block(stair)],
        figures=(),
    )
    above_plan = build_plan(above_facts)
    assert above_plan.decisions[1].base_strategy == "shaped_pocket"
    assert above_plan.pocket_links == ()
    assert above_plan.paragraph_gap_links == ()
    under_facts = build_facts(
        source_fingerprint="synthetic",
        page_index=0,
        page_width=612.0,
        page_height=792.0,
        input_gate="single_page",
        text_health=0.9,
        blocks=[_block(stair), _block(column, role="body")],
        figures=(),
    )
    under_plan = build_plan(under_facts)
    assert under_plan.decisions[0].base_strategy == "shaped_pocket"
    assert under_plan.decisions[1].base_strategy == "rect_flow"
    assert under_plan.pocket_links == ()
    assert under_plan.paragraph_gap_links == ()


def test_a_list_does_not_take_a_body_paragraph_gap():
    bullet = [(72.0, 400.0, 500.0)]
    number = [(72.0, 400.0, 300.0)]
    facts = _facts_blocks([_bullet_block(bullet), _number_block(number)])
    plan = build_plan(facts)
    assert plan.paragraph_gap_links == ()


def test_legacy_flow_does_not_see_a_body_gap_paragraph():
    upper = _wandering(100.0)
    lower = _wandering(47.0)
    facts = _facts_blocks([_block(upper, role="body"), _block(lower, role="body")])
    plan = build_plan(facts)
    planned = _placed_paragraph(
        facts.regions[1].region_id, box=_Box(56, 160, 400, 200)
    )
    other = _placed_paragraph(None, box=_Box(56, 40, 400, 80))
    page = _Page([planned, other], plan)
    seen = []

    def flow(paragraphs):
        seen.extend(paragraphs)

    run_legacy_column_flow(page, flow)
    assert seen == [other]
    assert page.pdf_paragraph == [planned, other]


def test_a_later_push_keeps_the_scanned_white():
    """Glyphs that fill the line leave less than 3pt of ink. The push stays."""
    upper = [(56.0, 400.0, 100.0), (56.0, 400.0, 85.0), (56.0, 400.0, 70.0)]
    lower = [(56.0, 400.0, 53.0), (56.0, 400.0, 38.0), (56.0, 400.0, 23.0)]
    assert scanned_paragraph_gap(_boxes(upper), _boxes(lower)) == 2.0
    facts = _facts_blocks([_block(upper, role="body"), _block(lower, role="body")])
    plan = build_plan(facts)
    assert _links_by_id(plan)[facts.regions[1].region_id].paragraph_gap == 2.0
    first = _placed_paragraph(
        facts.regions[0].region_id,
        box=_Box(56, 368, 400, 400),
        chars=[_Char(384, 400), _Char(368, 384)],
    )
    second_chars = [_Char(184, 200)]
    second = _placed_paragraph(
        facts.regions[1].region_id,
        box=_Box(56, 184, 400, 200),
        chars=second_chars,
    )
    page = _Page([first, second], plan)
    pack_rect_flow(page)
    assert second_chars[0].box.y2 == 366.0
    _push_overlaps_down(page, 3.0)
    assert second_chars[0].box.y2 == 366.0


def test_a_side_quote_is_not_pushed_under_the_union():
    """The wide line is lower. The quote sits beside the narrow lines."""
    narrow = _ink_char(102, 500, 340, 514)
    wide = _ink_char(102, 360, 420, 374)
    body = _placed_paragraph(
        "body", box=_Box(102, 360, 420, 514), chars=[narrow, wide]
    )
    quote_char = _ink_char(380, 490, 562, 508)
    quote = _placed_paragraph(
        "quote", box=_Box(378, 470, 562, 520), chars=[quote_char]
    )
    page = _Page([body, quote], LayoutPlan("synthetic", 0, "single_page", ()))
    _push_overlaps_down(page, 3.0)
    assert quote_char.box.y2 == 508


def test_a_paragraph_that_runs_through_the_ink_still_moves_down():
    upper_char = _ink_char(100, 200, 400, 214)
    upper = _placed_paragraph(
        "upper", box=_Box(100, 200, 400, 214), chars=[upper_char]
    )
    lower_char = _ink_char(120, 190, 380, 204)
    lower = _placed_paragraph(
        "lower", box=_Box(120, 190, 380, 204), chars=[lower_char]
    )
    page = _Page([upper, lower], LayoutPlan("synthetic", 0, "single_page", ()))
    _push_overlaps_down(page, 3.0)
    assert lower_char.box.y2 == 197


def test_legacy_flow_does_not_see_planned_paragraphs():
    _facts, plan = _plan_for(_column_lines(72, 400, 500))
    planned = _placed_paragraph(plan.decisions[0].region_id, box=_Box(72, 300, 400, 500))
    other = _placed_paragraph(None, box=_Box(72, 100, 400, 200))
    page = _Page([planned, other], plan)
    seen = []

    def flow(paragraphs):
        seen.extend(paragraphs)

    run_legacy_column_flow(page, flow)
    assert seen == [other]
    assert page.pdf_paragraph == [planned, other]

    bare = _Page([planned, other], None)
    seen.clear()
    run_legacy_column_flow(bare, flow)
    assert seen == [planned, other]


def test_attach_layout_plans_chains_two_bodies():
    text = "This is a readable English sentence for the straight column. "
    upper = _il_paragraph(_column_lines(72, 400, 500), text)
    lower = _il_paragraph(_column_lines(72, 400, 300), text)
    page = _il_page([upper, lower])
    assert attach_layout_plans(_Docs([page])) is True
    links = _links_by_id(page.layout_plan)
    assert links[upper.layout_region_id].flow_next_id == lower.layout_region_id
    assert (
        links[upper.layout_region_id].column_chain_id
        == links[lower.layout_region_id].column_chain_id
    )
    again = upper.layout_region_id
    assert attach_layout_plans(_Docs([page])) is True
    assert upper.layout_region_id == again


def test_two_list_items_pack_under_each_other():
    """A bullet and a number share one chain. One line is enough to join."""
    bullet = [(72.0, 400.0, 500.0)]
    number = [(72.0, 400.0, 300.0)]
    facts = _facts_blocks([_bullet_block(bullet), _number_block(number)])
    plan = build_plan(facts)
    assert [item.base_strategy for item in plan.decisions] == ["list", "list"]
    first_id = facts.regions[0].region_id
    second_id = facts.regions[1].region_id
    links = _list_links_by_id(plan)
    assert links[first_id].flow_next_id == second_id
    assert links[first_id].list_chain_id == links[second_id].list_chain_id
    assert links[first_id].marker_left == 72.0
    assert links[first_id].column_right == 400.0
    assert not plan.column_links

    first = _placed_paragraph(
        first_id,
        box=_Box(80, 360, 300, 420),
        chars=[_Char(360, 378)],
        widths=[400.0, 80.0],
    )
    second_chars = [_Char(182, 200), _Char(164, 182)]
    second = _placed_paragraph(
        second_id,
        box=_Box(90, 160, 280, 200),
        chars=second_chars,
        widths=[400.0, 80.0],
    )
    page = _Page([first, second], plan)
    assign_list_boxes(page)
    assert first.box.x == 72.0
    assert first.box.x2 == 400.0
    assert second.box.x == 72.0
    assert second.alignment == "left"
    assert first.reference_metrics.per_line_widths == [328.0, 328.0]
    assert 80.0 not in second.reference_metrics.per_line_widths

    pack_list_items(page, paragraph_gap=6.0)
    assert second.box.y2 == 354.0
    assert second_chars[0].box.y2 == 354.0
    assert second_chars[1].box.y2 == 336.0
    assert second_chars[0].box.y2 - second_chars[1].box.y2 == 18.0
    assert first.box.y == 360.0


_STAIR = [
    (100.0, 570.0, 160.0),
    (112.0, 570.0, 145.0),
    (124.0, 570.0, 130.0),
    (136.0, 570.0, 115.0),
]

# Figure on the left. Each band meets one stair line. The gap is
# pin 570 minus the figure's right edge, which is not the English width.
_STAIR_FIGURES = (
    FigureBox(0.0, 153.0, 150.0, 170.0),
    FigureBox(0.0, 138.0, 190.0, 152.0),
    FigureBox(0.0, 123.0, 230.0, 137.0),
    FigureBox(0.0, 100.0, 270.0, 122.0),
)
_STAIR_GAPS = (420.0, 380.0, 340.0, 300.0)


def _stair_facts(figures=_STAIR_FIGURES):
    return build_facts(
        source_fingerprint="synthetic",
        page_index=0,
        page_width=612.0,
        page_height=792.0,
        input_gate="single_page",
        text_health=0.9,
        blocks=[_block(_STAIR)],
        figures=figures,
    )


def test_figure_gap_narrows_and_does_not_fill_a_rectangle():
    """Chinese line widths follow the figure, not the English lines."""
    facts = _stair_facts()
    plan = build_plan(facts)
    assert plan.decisions[0].base_strategy == "shaped_pocket"
    link = plan.pocket_links[0]
    english = [line[1] - line[0] for line in _STAIR]
    assert link.free_side == "left"
    assert link.pin_edge == 570.0
    assert link.line_widths == _STAIR_GAPS
    assert list(link.line_widths) != english
    assert len(set(link.line_widths)) == len(link.line_widths)
    assert link.line_widths == tuple(sorted(link.line_widths, reverse=True))

    paragraph = _placed_paragraph(
        facts.regions[0].region_id,
        box=_Box(40.0, 100.0, 200.0, 180.0),
        widths=english,
    )
    page = _Page([paragraph], plan)
    assign_shaped_boxes(page)
    assert paragraph.alignment == "right"
    assert paragraph.box.x2 == 570.0
    # A line above the figure uses the opening, so the box has to hold it.
    assert paragraph.box.x == 570.0 - link.opening
    assert paragraph.reference_metrics.per_line_widths == list(_STAIR_GAPS)
    assert paragraph.first_line_indent == 0
    assert interval_for_pocket(link, 0) == (150.0, 570.0)
    assert interval_for_pocket(link, 3) == (270.0, 570.0)
    assert interval_for_pocket(link, 9) == (270.0, 570.0)


def test_chinese_line_uses_the_gap_at_its_height():
    """The Chinese line reads the figure at its own height, not its index.

    These English lines already cross the figure, so the scan passes no
    extra gutter. The line stops on the figure edge.
    """
    facts = _stair_facts()
    link = build_plan(facts).pocket_links[0]
    assert link.edge_gap == 0.0
    assert interval_for_pocket(link, 0) == (150.0, 570.0)
    assert interval_for_pocket(link, 0, 100.0, 122.0) == (270.0, 570.0)
    assert interval_for_pocket(link, 3, 153.0, 170.0) == (150.0, 570.0)
    # The figure top is 170. A line just above it follows that curve.
    # Farther up, the width is the opening. The next stair step is not borrowed.
    assert interval_for_pocket(link, 3, 174.0, 186.0) == (150.0, 570.0)
    assert interval_for_pocket(link, 3, 190.0, 200.0) == (100.0, 570.0)


class _FrameGlyph:
    def __init__(self, x: float, x2: float, space: bool = False):
        self.box = type("Box", (), {"x": x, "x2": x2})()
        self.is_space = space

    def shift_x(self, dx: float) -> None:
        self.box.x += dx
        self.box.x2 += dx


def test_a_short_line_meets_the_frame_edge():
    """Fill the scanned frame, then align. The last glyph meets the edge."""
    units = [_FrameGlyph(0, 12), _FrameGlyph(12, 24), _FrameGlyph(24, 36)]
    align_frame_line(units, 60)
    assert units[0].box.x == 0
    assert units[-1].box.x2 == 60
    gaps = [units[i + 1].box.x - units[i].box.x2 for i in range(2)]
    assert gaps[0] == gaps[1]


def test_one_glyph_stays_on_the_pin():
    units = [_FrameGlyph(10, 22)]
    align_frame_line(units, 80)
    assert units[0].box.x == 10
    assert units[0].box.x2 == 22


def test_a_line_already_on_the_frame_stays():
    units = [_FrameGlyph(0, 12), _FrameGlyph(12, 24)]
    align_frame_line(units, 24)
    assert units[1].box.x == 12
    assert units[1].box.x2 == 24


def test_punctuation_meets_the_frame_and_does_not_pass_it():
    """A comma is a glyph. It stops on the frame instead of hanging past it."""
    units = [_FrameGlyph(0, 12), _FrameGlyph(12, 24)]
    align_frame_line(units, 40)
    assert units[-1].box.x2 == 40
    overflowing = [_FrameGlyph(0, 12), _FrameGlyph(12, 42)]
    align_frame_line(overflowing, 40)
    assert overflowing[-1].box.x2 == 42


def test_a_line_above_the_body_uses_the_curve_just_below():
    """No edge at the line, so the rising curve below sets the width.

    A closer curve further down does not. A line that already meets a
    curve keeps that edge. A tighter curve below belongs to the next line.
    """
    link = PocketLink(
        region_id="rise",
        free_side="right",
        pin_edge=100.0,
        line_widths=(200.0,),
        opening=450.0,
        slices=(
            (250.0, 262.0, 400.0),
            (180.0, 192.0, 280.0),
        ),
    )
    assert interval_for_pocket(link, 0, 270.0, 288.0) == (100.0, 400.0)
    assert interval_for_pocket(link, 0, 250.0, 264.0) == (100.0, 400.0)
    assert interval_for_pocket(link, 0, 320.0, 336.0) == (100.0, 550.0)
    continued = PocketLink(
        region_id="rise",
        free_side="right",
        pin_edge=100.0,
        line_widths=(200.0,),
        opening=450.0,
        slices=(
            (250.0, 264.0, 400.0),
            (236.0, 248.0, 370.0),
        ),
    )
    assert interval_for_pocket(continued, 0, 250.0, 264.0) == (100.0, 400.0)
    other = PocketLink(
        region_id="rise",
        free_side="right",
        pin_edge=100.0,
        line_widths=(200.0,),
        opening=450.0,
        slices=(
            (250.0, 264.0, 400.0),
            (236.0, 248.0, 280.0),
        ),
    )
    held = PocketLink(
        region_id="rise",
        free_side="right",
        pin_edge=100.0,
        line_widths=(200.0,),
        opening=450.0,
        slices=((250.0, 264.0, 400.0),),
        edge_gap=18.0,
    )
    assert interval_for_pocket(held, 0, 250.0, 264.0) == (100.0, 382.0)
    assert interval_for_pocket(other, 0, 250.0, 264.0) == (100.0, 400.0)


def test_scanned_edge_gap_skips_the_short_last_line():
    """The gutter is the body lines. The short last line is not the edge."""
    lines = (
        LineBox(56, 200, 100),
        LineBox(56, 280, 130),
        LineBox(56, 300, 160),
        LineBox(56, 290, 190),
    )
    slices = ((90.0, 200.0, 320.0),)
    assert scanned_edge_gap(lines, slices, "right", 56.0) == 30.0


def test_scanned_edge_gap_is_zero_when_text_already_crosses():
    lines = (LineBox(100, 570, 160), LineBox(112, 570, 145))
    slices = ((140.0, 170.0, 150.0),)
    assert scanned_edge_gap(lines, slices, "left", 570.0) == 0.0


def test_the_paragraph_last_line_stays_at_its_own_length():
    """Frame lines meet the edge. The last line of the paragraph does not."""
    setter = Typesetting.__new__(Typesetting)
    setter._pocket_link = object()
    assert setter._alignment_in_frame("left") == "justify"
    assert setter._alignment_in_frame("left", last=True) == "left"
    setter._pocket_link = None
    assert setter._alignment_in_frame("left") == "left"


def test_a_band_keeps_ink_that_enters_between_its_ends():
    """A contour inside the band sets the edge. The end rows miss it."""
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 8, 5))
    pix.set_rect(pix.irect, (255, 255, 255))
    pix.set_pixel(6, 0, (210, 160, 140))
    pix.set_pixel(2, 3, (210, 160, 140))
    left, right = _ink_span(pix, 0, 4)
    assert left == 2
    assert right == 6


def test_near_white_and_gray_are_not_skin():
    """JPEG sheet and gray are not the body. Pale warm skin and black are."""
    for pixel in ((251, 251, 251), (247, 247, 247), (254, 250, 247), (200, 200, 200)):
        assert _channels_are_ink(*pixel) is False
    for pixel in (
        (255, 246, 239),
        (255, 249, 243),
        (253, 245, 241),
        (239, 202, 173),
        (212, 174, 155),
        (0, 0, 0),
    ):
        assert _channels_are_ink(*pixel) is True


def _facts_with_figure(lines, figure):
    return build_facts(
        source_fingerprint="synthetic",
        page_index=0,
        page_width=612.0,
        page_height=792.0,
        input_gate="single_page",
        text_health=0.9,
        blocks=[_block(lines, role="body")],
        figures=(figure,),
    )


def test_a_flat_column_beside_a_figure_uses_that_gap():
    """The scanned white stays. A distant figure does not pull the line onto it."""
    lines = _column_lines(113, 229, 140)
    near = build_plan(_facts_with_figure(lines, FigureBox(340, 80, 400, 150)))
    link = near.column_links[0]
    assert link.column_left == 113.0
    assert link.column_right == 229.0
    assert link.free_side == "right"
    assert link.edge_gap == 111.0
    paragraph = _placed_paragraph(
        link.region_id,
        box=_Box(113.0, 80.0, 229.0, 150.0),
        widths=[116.0, 116.0, 116.0, 116.0],
    )
    pocket = column_gap_for(_Page([paragraph], near), paragraph)
    assert pocket is not None
    assert pocket.edge_gap == 111.0
    x0, x1 = interval_for_pocket(pocket, 0, 100.0, 116.0)
    assert x0 == 113.0
    assert x1 == 229.0

    far = build_plan(_facts_with_figure(lines, FigureBox(500, 80, 580, 150)))
    far_link = far.column_links[0]
    assert far_link.column_right == 229.0
    assert far_link.gap_slices == ()
    assert far_link.free_side == ""
    far_paragraph = _placed_paragraph(
        far_link.region_id,
        box=_Box(113.0, 80.0, 229.0, 150.0),
        widths=[116.0, 116.0, 116.0, 116.0],
    )
    assert column_gap_for(_Page([far_paragraph], far), far_paragraph) is None

    tight = build_plan(_facts_with_figure(lines, FigureBox(200, 80, 260, 150)))
    tight_link = tight.column_links[0]
    assert tight_link.column_right == 229.0
    tight_paragraph = _placed_paragraph(
        tight_link.region_id,
        box=_Box(113.0, 80.0, 229.0, 150.0),
        widths=[116.0, 116.0, 116.0, 116.0],
    )
    tight_pocket = column_gap_for(_Page([tight_paragraph], tight), tight_paragraph)
    assert tight_link.edge_gap == 0.0
    _x0, tight_x1 = interval_for_pocket(tight_pocket, 0, 100.0, 116.0)
    assert tight_x1 == 200.0


def test_a_side_display_keeps_the_body_on_its_own_right():
    """The chain's widest line does not cross a quote beside one member.

    The member above the quote, and a short member below it, keep the
    shared right. The member beside the quote stops at its own ink.
    """
    beside = [(230.0, 399.0, 400.0 - 15.0 * index) for index in range(6)]
    above = [(230.0, 417.0, 500.0 - 15.0 * index) for index in range(4)]
    below = [(230.0, 360.0, 200.0 - 15.0 * index) for index in range(4)]
    quote = [
        (424.0, 507.0, 410.0),
        (418.0, 526.0, 385.0),
        (414.0, 548.0, 360.0),
        (415.0, 523.0, 335.0),
        (417.0, 552.0, 310.0),
        (425.0, 532.0, 285.0),
    ]
    plan = build_plan(
        _facts_blocks(
            [
                _block(beside),
                _block(above),
                _block(below),
                _block(quote),
            ]
        )
    )
    links = _links_by_id(plan)
    by_right = {
        round(max(line[1] for line in lines), 1): links[region_id]
        for lines, region_id in (
            (beside, plan.decisions[0].region_id),
            (above, plan.decisions[1].region_id),
            (below, plan.decisions[2].region_id),
        )
    }
    assert by_right[399.0].column_right == 399.0
    assert by_right[417.0].column_right == 417.0
    assert by_right[360.0].column_right == 417.0
    assert plan.decisions[3].base_strategy != "rect_flow"


def test_a_pulled_gap_column_is_measured_at_its_new_height():
    """A tight figure beside the English lines, and a wider one above.

    Both stay in the slices once the side is right. After the box moves
    up, the line at the new height uses the wide edge and the line at the
    old height stays tight. An unmoved gap column and a column with no
    slices are not selected.
    """
    facts = build_facts(
        source_fingerprint="synthetic",
        page_index=0,
        page_width=612.0,
        page_height=792.0,
        input_gate="single_page",
        text_health=0.9,
        blocks=[
            _block(_column_lines(113, 229, 140), role="body"),
            _block(_column_lines(36, 100, 460), role="body"),
        ],
        figures=(
            FigureBox(250.0, 80.0, 360.0, 150.0),
            FigureBox(400.0, 160.0, 520.0, 230.0),
        ),
    )
    plan = build_plan(facts)
    assert {item.base_strategy for item in plan.decisions} == {"rect_flow"}
    gap_link = next(link for link in plan.column_links if link.column_left == 113.0)
    plain_link = next(link for link in plan.column_links if link.column_left == 36.0)
    assert gap_link.free_side == "right"
    assert {edge for _bottom, _top, edge in gap_link.gap_slices} >= {250.0, 400.0}
    assert plain_link.gap_slices == ()
    gap = _placed_paragraph(
        gap_link.region_id,
        box=_Box(113.0, 80.0, 229.0, 140.0),
        widths=[116.0, 116.0, 116.0, 116.0],
    )
    plain = _placed_paragraph(
        plain_link.region_id,
        box=_Box(36.0, 400.0, 100.0, 460.0),
        widths=[64.0, 64.0, 64.0, 64.0],
    )
    page = _Page([gap, plain], plan)
    tops = figure_gap_tops(page)
    assert tops == {gap_link.region_id: 140.0}
    assert moved_figure_gap_paragraphs(page, tops) == []
    plain.box.y2 = 500.0
    assert moved_figure_gap_paragraphs(page, tops) == []
    gap.box.y2 = 220.0
    assert moved_figure_gap_paragraphs(page, tops) == [gap]
    pocket = column_gap_for(page, gap)
    assert pocket is not None
    assert pocket.edge_gap == 21.0
    _old_x0, old_x1 = interval_for_pocket(pocket, 0, 100.0, 116.0)
    _new_x0, new_x1 = interval_for_pocket(pocket, 0, 180.0, 196.0)
    assert old_x1 == 229.0
    assert new_x1 == 379.0


def test_a_letter_strip_past_the_line_is_not_a_figure():
    """A short image that starts in the paragraph is the line painted again."""
    sentence = "This is a readable English sentence beside the figure. "
    paragraph = _il_paragraph(_STAIR, sentence)
    page = _il_page([paragraph])
    page.pdf_figure = []
    page.pdf_form = [_image_form(200.0, 148.0, 600.0, 160.0)]
    assert _figures_of(page, 612.0, 792.0) == ()


def test_stair_without_a_figure_is_not_given_english_widths():
    facts = _stair_facts(())
    plan = build_plan(facts)
    assert plan.decisions[0].base_strategy == "shaped_pocket"
    assert plan.pocket_links == ()


def test_straight_column_does_not_enter_the_pocket_path():
    lines = _column_lines(72, 400, 500)
    facts = build_facts(
        source_fingerprint="synthetic",
        page_index=0,
        page_width=612.0,
        page_height=792.0,
        input_gate="single_page",
        text_health=0.9,
        blocks=[_block(lines)],
        figures=(FigureBox(420.0, 430.0, 560.0, 520.0),),
    )
    plan = build_plan(facts)
    assert plan.decisions[0].base_strategy == "rect_flow"
    assert plan.pocket_links == ()
    paragraph = _placed_paragraph(
        facts.regions[0].region_id,
        box=_Box(72.0, 440.0, 400.0, 500.0),
        widths=[328.0, 328.0, 90.0],
    )
    assign_shaped_boxes(_Page([paragraph], plan))
    assert paragraph.reference_metrics.per_line_widths == [328.0, 328.0, 90.0]
    assert paragraph.alignment == "center"


def test_white_of_a_photo_tile_follows_the_skin_not_the_english_widths():
    """English widths jump out, then back. The skin only steps in.

    The photo tile covers the column, so the paragraph is marked on the
    photo. The glyphs sit in the white. The line stops at the skin.
    """
    lines = [
        (113.0, 332.0, 400.0),
        (113.0, 306.0, 370.0),
        (113.0, 238.0, 340.0),
        (113.0, 249.0, 310.0),
        (113.0, 220.0, 280.0),
        (113.0, 200.0, 250.0),
    ]
    edges = (360.0, 340.0, 300.0, 270.0, 240.0, 210.0)
    sentence = "This is a readable English sentence beside the figure. "
    paragraph = _il_paragraph(lines, sentence, role="wrap_column")
    paragraph.layout_intent.text_on_photo = True
    page = _il_page([paragraph])
    page.pdf_figure = []
    page.pdf_form = [
        _image_form(edge, y - 16.0, 560.0, y + 4.0)
        for (_x0, _x1, y), edge in zip(lines, edges, strict=True)
    ]
    assert attach_layout_plans(_Docs([page])) is True
    assert page.layout_plan.decisions[0].base_strategy == "rect_flow"
    pocket = column_gap_for(page, paragraph)
    assert pocket is not None
    assert pocket.edge_gap == 28.0
    widths = []
    for (_x0, _x1, y), edge in zip(lines, edges, strict=True):
        x0, x1 = interval_for_pocket(pocket, 0, y - 2.0, y + 2.0)
        assert x0 == 113.0
        assert x1 == edge - pocket.edge_gap
        widths.append(x1 - x0)
    assert widths[2] > 125.0
    assert widths[3] < widths[2]
    assert all(widths[i] >= widths[i + 1] for i in range(len(widths) - 1))


def test_glyphs_on_the_skin_stay_on_the_photo():
    lines = [
        (113.0, 332.0, 400.0),
        (113.0, 306.0, 370.0),
        (113.0, 238.0, 340.0),
        (113.0, 249.0, 310.0),
        (113.0, 220.0, 280.0),
        (113.0, 200.0, 250.0),
    ]
    sentence = "This is a readable English sentence beside the figure. "
    paragraph = _il_paragraph(lines, sentence, role="wrap_column")
    paragraph.layout_intent.text_on_photo = True
    page = _il_page([paragraph])
    page.pdf_figure = []
    page.pdf_form = [_image_form(90.0, 200.0, 560.0, 450.0)]
    assert attach_layout_plans(_Docs([page])) is True
    assert page.layout_plan.decisions[0].base_strategy == "preserve"
    assert column_gap_for(page, paragraph) is None


def test_a_pocket_seats_the_rect_with_the_scanned_white():
    """The pull uses the scanned white. The passed 6 is only the fallback."""
    column = [(100.0, 400.0, 80.0 - 15.0 * i) for i in range(4)]
    facts = build_facts(
        source_fingerprint="synthetic",
        page_index=0,
        page_width=612.0,
        page_height=792.0,
        input_gate="single_page",
        text_health=0.9,
        blocks=[_block(_STAIR), _block(column)],
        figures=_STAIR_FIGURES,
    )
    plan = build_plan(facts)
    assert [item.base_strategy for item in plan.decisions] == [
        "shaped_pocket",
        "rect_flow",
    ]
    assert plan.paragraph_gap_links == ()
    head = _links_by_id(plan)[facts.regions[1].region_id]
    assert head.flow_next_id is None
    assert head.paragraph_gap == 20.0
    pocket = _placed_paragraph(
        facts.regions[0].region_id,
        box=_Box(150.0, 140.0, 570.0, 160.0),
        chars=[_Char(140.0, 155.0)],
    )
    column_chars = [_Char(60.0, 78.0), _Char(42.0, 60.0)]
    body = _placed_paragraph(
        facts.regions[1].region_id,
        box=_Box(100.0, 40.0, 400.0, 80.0),
        chars=column_chars,
    )
    page = _Page([pocket, body], plan)
    pack_rect_flow(page)
    assert column_chars[0].box.y2 == 78.0
    pack_shaped_pockets(page, paragraph_gap=6.0)
    # Pocket line top 155, rendered step 18, scanned white 20.
    assert column_chars[0].box.y2 == 117.0
    assert column_chars[0].box.y2 - column_chars[1].box.y2 == 18.0
    assert pocket.box.y == 140.0


def test_shorter_pocket_pulls_the_rect_column_up():
    column = _column_lines(72, 400, 80)
    facts = build_facts(
        source_fingerprint="synthetic",
        page_index=0,
        page_width=612.0,
        page_height=792.0,
        input_gate="single_page",
        text_health=0.9,
        blocks=[_block(_STAIR), _block(column)],
        figures=_STAIR_FIGURES,
    )
    plan = build_plan(facts)
    assert [item.base_strategy for item in plan.decisions] == [
        "shaped_pocket",
        "rect_flow",
    ]
    pocket = _placed_paragraph(
        facts.regions[0].region_id,
        box=_Box(150.0, 140.0, 570.0, 160.0),
        chars=[_Char(140.0, 155.0)],
    )
    column_chars = [_Char(60.0, 78.0), _Char(42.0, 60.0)]
    body = _placed_paragraph(
        facts.regions[1].region_id,
        box=_Box(72.0, 40.0, 400.0, 80.0),
        chars=column_chars,
    )
    page = _Page([pocket, body], plan)
    pack_shaped_pockets(page, paragraph_gap=6.0)
    # Pocket line top 155, rendered step 18, passed white 6.
    assert column_chars[0].box.y2 == 131.0
    assert column_chars[0].box.y2 - column_chars[1].box.y2 == 18.0
    assert pocket.box.y == 140.0


def test_longer_pocket_pushes_the_next_body_down():
    """Two pockets share ink. The lower one moves down by the caller's gap."""
    upper_char = _ink_char(113, 140, 400, 160)
    lower_char = _ink_char(113, 120, 400, 148)
    side_char = _ink_char(450, 120, 560, 148)
    upper = _placed_paragraph("upper", box=_Box(113, 140, 400, 170), chars=[upper_char])
    lower = _placed_paragraph("lower", box=_Box(113, 120, 400, 155), chars=[lower_char])
    side = _placed_paragraph("side", box=_Box(450, 120, 560, 155), chars=[side_char])
    footer_char = _ink_char(113, 120, 400, 148)
    footer = _placed_paragraph("foot", box=_Box(113, 120, 400, 155), chars=[footer_char])
    footer.layout_label = "footer"
    footer.unicode = "12"
    page = _Page([upper, lower, side, footer], _pocket_plan("upper", "lower"))
    pack_shaped_pockets(page, paragraph_gap=6.0)
    assert lower_char.box.y2 == 134.0
    assert upper_char.box.y2 == 160.0
    assert side_char.box.y2 == 148.0
    assert footer_char.box.y2 == 148.0


def test_preserve_below_a_pocket_is_not_pulled_up():
    pocket_char = _ink_char(113, 140, 400, 160)
    kept_char = _ink_char(113, 80, 400, 100)
    pocket = _placed_paragraph("pocket", box=_Box(113, 140, 400, 170), chars=[pocket_char])
    kept = _placed_paragraph("kept", box=_Box(113, 80, 400, 110), chars=[kept_char])
    page = _Page([pocket, kept], _pocket_plan("pocket"))
    pack_shaped_pockets(page, paragraph_gap=6.0)
    assert kept_char.box.y2 == 100.0
    assert pocket_char.box.y == 140.0


def test_overlap_push_stops_at_the_page_bottom():
    upper_char = _ink_char(113, 20, 400, 40)
    lower_char = _ink_char(113, 4, 400, 28)
    upper = _placed_paragraph("upper", box=_Box(113, 20, 400, 40), chars=[upper_char])
    lower = _placed_paragraph("lower", box=_Box(113, 4, 400, 28), chars=[lower_char])
    page = _Page([upper, lower], _pocket_plan("upper", "lower"))
    page.cropbox = type("_Holder", (), {"box": _Box(0, 0, 612, 792)})()
    pack_shaped_pockets(page, paragraph_gap=6.0)
    assert lower_char.box.y2 == 28.0


def test_overlap_without_a_pocket_stays_put():
    upper_char = _ink_char(113, 140, 400, 160)
    lower_char = _ink_char(113, 120, 400, 148)
    upper = _placed_paragraph("upper", box=_Box(113, 140, 400, 170), chars=[upper_char])
    lower = _placed_paragraph("lower", box=_Box(113, 120, 400, 155), chars=[lower_char])
    plan = LayoutPlan(
        "synthetic",
        0,
        "single_page",
        (_region_decision("upper", "rect_flow"), _region_decision("lower", "rect_flow")),
    )
    pack_shaped_pockets(_Page([upper, lower], plan), paragraph_gap=6.0)
    assert lower_char.box.y2 == 148.0
    assert upper_char.box.y2 == 160.0


def test_hides_a_short_image_over_translated_body():
    pocket = _text_paragraph("pocket", _Box(113, 200, 221.7, 230), "会阴")
    column = _text_paragraph("column", _Box(36, 400, 500, 480), "阴阜")
    title = _text_paragraph("title", _Box(40, 640, 560, 670), "她的私密部位")
    english = _text_paragraph("english", _Box(113, 80, 221.7, 110), "perineum")
    page = _Page(
        [pocket, column, title, english],
        _pocket_plan(
            "pocket",
            "english",
            extra=(
                _region_decision("column", "rect_flow"),
                _region_decision("title", "preserve"),
            ),
        ),
    )
    strip = _image_form(222.0, 202.0, 360.0, 214.0)
    assert hides_translated_line(strip, page)
    assert hides_translated_line(_image_form(40.0, 420.0, 200.0, 432.0), page)
    assert not hides_translated_line(_image_form(222.0, 180.0, 500.0, 320.0), page)
    assert not hides_translated_line(_image_form(462.0, 650.0, 550.0, 661.0), page)
    assert not hides_translated_line(
        _image_form(222.0, 202.0, 360.0, 214.0, form_type="path"), page
    )
    # The pocket ink stops. The English line continues past it.
    assert hides_translated_line(_image_form(240.0, 202.0, 360.0, 214.0), page)
    assert hides_translated_line(_image_form(230.0, 202.0, 234.0, 214.0), page)
    # A badge beside a straight column shares the height and not the ink.
    assert not hides_translated_line(_image_form(520.0, 420.0, 600.0, 432.0), page)
    # One body line below the ink still counts. Further down stays.
    assert not hides_translated_line(_image_form(113.0, 160.0, 221.0, 176.0), page)
    assert not hides_translated_line(_image_form(222.0, 82.0, 360.0, 94.0), page)


def test_a_letter_image_on_preserved_body_is_hidden():
    """The line end is painted again as a narrow image. Preserve still drops it."""
    body = _text_paragraph("kept", _Box(113.0, 63.0, 221.2, 138.0), "尽管这因女性和女性而异")
    page = _Page(
        [body],
        _pocket_plan(extra=(_region_decision("kept", "preserve"),)),
    )
    assert hides_translated_line(_image_form(221.9, 93.4, 226.7, 104.8), page)
    assert hides_translated_line(_image_form(221.9, 78.7, 228.6, 89.9), page)
    assert not hides_translated_line(_image_form(420.0, 90.0, 560.0, 104.0), page)
    short = _text_paragraph("short", _Box(113.0, 108.0, 209.2, 120.0), "而且在很大")
    short_page = _Page(
        [short],
        _pocket_plan(extra=(_region_decision("short", "preserve"),)),
    )
    assert hides_translated_line(_image_form(221.9, 110.9, 224.9, 119.9), short_page)


def test_image_form_sets_the_pocket_gap():
    """A photo is an image form. A path form is not a figure."""
    sentence = "This is a readable English sentence beside the figure. "
    paragraph = _il_paragraph(_STAIR, sentence)
    page = _il_page([paragraph])
    page.pdf_figure = []
    page.pdf_form = [
        _image_form(0.0, 153.0, 150.0, 170.0),
        _image_form(0.0, 138.0, 190.0, 152.0),
        _image_form(0.0, 123.0, 230.0, 137.0),
        _image_form(0.0, 100.0, 270.0, 122.0),
        _image_form(0.0, 153.0, 400.0, 170.0, form_type="path"),
    ]
    assert attach_layout_plans(_Docs([page])) is True
    assert page.layout_plan.decisions[0].base_strategy == "shaped_pocket"
    link = page.layout_plan.pocket_links[0]
    assert link.free_side == "left"
    assert link.pin_edge == 570.0
    assert link.line_widths == _STAIR_GAPS


def test_same_style_stair_keeps_the_figure_gap():
    """Styles folds the lines into one run. The plan still reads each line."""
    sentence = "This is a readable English sentence beside the figure. "
    paragraph = _same_style_paragraph(_STAIR, sentence)
    page = _il_page([paragraph])
    page.pdf_figure = []
    page.pdf_form = [
        _image_form(0.0, 153.0, 150.0, 170.0),
        _image_form(0.0, 138.0, 190.0, 152.0),
        _image_form(0.0, 123.0, 230.0, 137.0),
        _image_form(0.0, 100.0, 270.0, 122.0),
    ]
    assert attach_layout_plans(_Docs([page])) is True
    assert page.layout_plan.decisions[0].base_strategy == "shaped_pocket"
    link = page.layout_plan.pocket_links[0]
    assert link.free_side == "left"
    assert link.pin_edge == 570.0
    assert link.line_widths == _STAIR_GAPS
    english = [line[1] - line[0] for line in _STAIR]
    assert list(link.line_widths) != english


def test_same_style_column_does_not_enter_the_pocket_path():
    lines = _column_lines(72, 400, 500)
    paragraph = _same_style_paragraph(
        lines, "This is a readable English sentence in a straight column. "
    )
    page = _il_page([paragraph])
    page.pdf_figure = []
    page.pdf_form = [_image_form(420.0, 430.0, 560.0, 520.0)]
    assert attach_layout_plans(_Docs([page])) is True
    assert page.layout_plan.decisions[0].base_strategy == "rect_flow"
    assert page.layout_plan.pocket_links == ()


def test_same_style_bullet_on_a_stair_stays_preserve():
    paragraph = _same_style_paragraph(
        _STAIR, "• The free edge steps inward beside the figure here."
    )
    page = _il_page([paragraph])
    page.pdf_figure = []
    page.pdf_form = [
        _image_form(0.0, 153.0, 150.0, 170.0),
        _image_form(0.0, 138.0, 190.0, 152.0),
        _image_form(0.0, 123.0, 230.0, 137.0),
        _image_form(0.0, 100.0, 270.0, 122.0),
    ]
    assert attach_layout_plans(_Docs([page])) is True
    decision = page.layout_plan.decisions[0]
    assert decision.base_strategy == "preserve"
    assert decision.fallback == "list_and_shaped"
    assert page.layout_plan.pocket_links == ()


def test_legacy_flow_does_not_see_a_figure_pocket():
    """Close and settle see nothing on a pocket page, including the leftover."""
    facts = _stair_facts()
    plan = build_plan(facts)
    planned = _placed_paragraph(
        facts.regions[0].region_id, box=_Box(150.0, 100.0, 570.0, 170.0)
    )
    other = _placed_paragraph(None, box=_Box(72.0, 20.0, 400.0, 80.0))
    page = _Page([planned, other], plan)
    seen = []
    run_legacy_column_flow(page, seen.extend)
    assert seen == []
    assert page.pdf_paragraph == [planned, other]


def test_list_items_keep_a_blank_line():
    """The gap is one rendered line. A marker a few points low is not a line."""
    bullet = [(72.0, 400.0, 500.0)]
    number = [(72.0, 400.0, 300.0)]
    facts = _facts_blocks([_bullet_block(bullet), _number_block(number)])
    plan = build_plan(facts)
    first_id = facts.regions[0].region_id
    second_id = facts.regions[1].region_id
    first_chars = [_Char(400, 418), _Char(397, 415)]
    second_chars = [_Char(200, 218), _Char(182, 200)]
    first = _placed_paragraph(
        first_id, box=_Box(72, 397, 400, 418), chars=first_chars
    )
    second = _placed_paragraph(
        second_id, box=_Box(72, 182, 400, 218), chars=second_chars
    )
    pack_list_items(_Page([first, second], plan))
    assert second_chars[0].box.y2 == 397 - 18
    assert second_chars[0].box.y2 - second_chars[1].box.y2 == 18
    assert first_chars[0].box.y2 == 418


def test_list_wrap_starts_to_the_right_of_the_marker():
    """Continuation edge is right of the marker. The box stays on the marker."""
    lines = [(72.0, 400.0, 300.0), (96.0, 360.0, 285.0)]
    text = "2. The next item wraps under its own words."
    facts = _facts_blocks([_number_block(lines, text)])
    plan = build_plan(facts)
    link = plan.list_links[0]
    assert plan.decisions[0].base_strategy == "list"
    assert link.marker_left == 72.0
    assert link.body_left == 96.0
    assert link.body_left > link.marker_left
    assert plan.to_dict()["list_links"][0]["body_left"] == 96.0

    item = _placed_paragraph(
        facts.regions[0].region_id,
        box=_Box(200, 260, 280, 300),
        widths=[400.0, 80.0],
    )
    assign_list_boxes(_Page([item], plan))
    assert item.box.x == link.marker_left
    assert item.box.x != link.body_left
    assert item.box.x2 == 400.0
    assert getattr(item, "first_line_indent", None) is None

    numbered = type("_Para", (), {"unicode": text})()
    units = [_Unit("2", 8.0), _Unit(".", 4.0), _Unit(" ", 4.0), _Unit("下", 12.0)]
    hang = Typesetting._numbered_list_hang_inset(
        numbered,
        units,
        1.0,
        line_idx=1,
        alignment="left",
        ocr_workaround=False,
        pocket_span=400.0,
    )
    assert hang > 0.5
    assert link.marker_left + hang > link.marker_left
    assert (
        Typesetting._numbered_list_hang_inset(
            numbered,
            units,
            1.0,
            line_idx=1,
            alignment="center",
            ocr_workaround=False,
            pocket_span=400.0,
        )
        == 0.0
    )
    assert (
        Typesetting._numbered_list_hang_inset(
            numbered,
            units,
            1.0,
            line_idx=0,
            alignment="left",
            ocr_workaround=False,
            pocket_span=400.0,
        )
        == 0.0
    )
    bullet = type("_Para", (), {"unicode": "• Hold the stretch."})()
    bullet_hang = Typesetting._numbered_list_hang_inset(
        bullet,
        [_Unit("•", 10.0), _Unit("Hold", 40.0)],
        1.0,
        line_idx=1,
        alignment="left",
        ocr_workaround=False,
        pocket_span=400.0,
    )
    assert bullet_hang > 0.5


def test_formula_bullet_uses_the_existing_hang():
    """A bullet stored as a formula still hangs by that unit's width."""
    glyph = type(
        "_Glyph",
        (),
        {
            "char_unicode": "•",
            "pdf_style": type("_Style", (), {"font_id": "Times-Roman"})(),
        },
    )()
    space = type(
        "_Glyph",
        (),
        {
            "char_unicode": " ",
            "pdf_style": type("_Style", (), {"font_id": "Times-Roman"})(),
        },
    )()
    formula = type("_Formula", (), {"pdf_character": [glyph, space]})()
    bullet = type(
        "_Unit",
        (),
        {"formular": formula, "char": None, "width": 7.5, "is_space": False},
    )()
    bullet.try_get_unicode = lambda: None
    paragraph = type("_Para", (), {"unicode": "• Hold the stretch."})()
    hang = Typesetting._numbered_list_hang_inset(
        paragraph,
        [bullet, _Unit("外", 12.0)],
        1.0,
        line_idx=1,
        alignment="left",
        ocr_workaround=False,
        pocket_span=400.0,
    )
    assert hang == 7.5
    word = type(
        "_Glyph",
        (),
        {
            "char_unicode": "E",
            "pdf_style": type("_Style", (), {"font_id": "Times-Roman"})(),
        },
    )()
    equation = type("_Formula", (), {"pdf_character": [word]})()
    other = type(
        "_Unit",
        (),
        {"formular": equation, "char": None, "width": 10.0, "is_space": False},
    )()
    other.try_get_unicode = lambda: None
    assert (
        Typesetting._numbered_list_hang_inset(
            paragraph,
            [other, _Unit("外", 12.0)],
            1.0,
            line_idx=1,
            alignment="left",
            ocr_workaround=False,
            pocket_span=400.0,
        )
        == 0.0
    )


def test_short_list_item_is_not_centered():
    facts = _facts_blocks([_bullet_block([(72.0, 400.0, 500.0)])])
    plan = build_plan(facts)
    item = _placed_paragraph(
        facts.regions[0].region_id,
        box=_Box(200, 400, 280, 420),
        widths=[80.0],
    )
    assert item.alignment == "center"
    assign_list_boxes(_Page([item], plan))
    assert item.alignment == "left"
    assert item.box.x == 72.0
    assert item.box.x2 == 400.0
    assert item.reference_metrics.per_line_widths == [328.0]
    assert 80.0 not in item.reference_metrics.per_line_widths


def test_sidebar_list_does_not_join_the_list_chain():
    """0.35 overlap still points at the sidebar. The list chain does not."""
    upper = [(72.0, 400.0, 500.0)]
    sidebar = [(330.0, 470.0, 420.0)]
    lower = [(72.0, 400.0, 300.0)]
    facts = _facts_blocks(
        [
            _bullet_block(upper),
            _bullet_block(sidebar),
            _bullet_block(lower),
        ]
    )
    plan = build_plan(facts)
    upper_id = facts.regions[0].region_id
    sidebar_id = facts.regions[1].region_id
    lower_id = facts.regions[2].region_id
    assert facts.regions[0].below_id == sidebar_id
    links = _list_links_by_id(plan)
    assert links[upper_id].flow_next_id == lower_id
    assert links[sidebar_id].flow_next_id is None
    assert links[upper_id].list_chain_id == links[lower_id].list_chain_id
    assert links[sidebar_id].list_chain_id != links[upper_id].list_chain_id
    assert links[upper_id].marker_left == 72.0
    assert links[upper_id].column_right == 400.0
    assert links[sidebar_id].marker_left == 330.0
    assert links[sidebar_id].column_right == 470.0


def test_quote_title_and_body_break_the_list_chain():
    upper = [(72.0, 400.0, 500.0)]
    between = [(72.0, 400.0, 400.0)]
    lower = [(72.0, 400.0, 300.0)]
    beside = [(430.0, 560.0, 400.0)]
    for role in ("pull_quote", "title"):
        facts = _facts_blocks(
            [
                _bullet_block(upper),
                _block(between, role=role),
                _bullet_block(lower),
            ]
        )
        plan = build_plan(facts)
        links = _list_links_by_id(plan)
        upper_id = facts.regions[0].region_id
        lower_id = facts.regions[2].region_id
        assert facts.regions[0].below_id == facts.regions[1].region_id
        assert facts.regions[1].region_id not in links
        assert links[upper_id].flow_next_id is None
        assert links[upper_id].list_chain_id != links[lower_id].list_chain_id

    side_facts = _facts_blocks(
        [
            _bullet_block(upper),
            _bullet_block(beside),
            _bullet_block(lower),
        ]
    )
    side_plan = build_plan(side_facts)
    side_links = _list_links_by_id(side_plan)
    assert (
        side_links[side_facts.regions[0].region_id].flow_next_id
        == side_facts.regions[2].region_id
    )
    assert (
        side_links[side_facts.regions[1].region_id].list_chain_id
        != side_links[side_facts.regions[0].region_id].list_chain_id
    )

    body = _column_lines(72, 400, 420)
    split = _facts_blocks(
        [
            _bullet_block(upper),
            _block(body, role="body"),
            _bullet_block(lower),
        ]
    )
    split_plan = build_plan(split)
    split_links = _list_links_by_id(split_plan)
    assert split.regions[1].region_id not in split_links
    assert split_links[split.regions[0].region_id].flow_next_id is None
    assert split.regions[1].region_id in _links_by_id(split_plan)

    rect_upper = _column_lines(72, 400, 500)
    rect_lower = _column_lines(72, 400, 280)
    blocked = _facts_blocks(
        [
            _block(rect_upper, role="body"),
            _bullet_block([(72.0, 400.0, 400.0)]),
            _block(rect_lower, role="body"),
        ]
    )
    blocked_plan = build_plan(blocked)
    rect_links = _links_by_id(blocked_plan)
    assert blocked.regions[1].region_id not in rect_links
    assert rect_links[blocked.regions[0].region_id].flow_next_id is None
    assert (
        rect_links[blocked.regions[0].region_id].column_chain_id
        != rect_links[blocked.regions[2].region_id].column_chain_id
    )
    assert blocked.regions[1].region_id in _list_links_by_id(blocked_plan)


def test_legacy_flow_does_not_see_planned_list_items():
    facts = _facts_blocks([_bullet_block([(72.0, 400.0, 500.0)])])
    plan = build_plan(facts)
    assert plan.decisions[0].base_strategy == "list"
    assert not plan.column_links
    planned = _placed_paragraph(
        plan.decisions[0].region_id, box=_Box(72, 300, 400, 500)
    )
    other = _placed_paragraph(None, box=_Box(72, 100, 400, 200))
    page = _Page([planned, other], plan)
    seen = []

    def flow(paragraphs):
        seen.extend(paragraphs)

    run_legacy_column_flow(page, flow)
    assert seen == [other]
    assert page.pdf_paragraph == [planned, other]


def test_attach_layout_plans_keeps_list_region_id():
    sentence = "This is a readable English sentence for the list item. "
    upper = _il_paragraph([(72.0, 400.0, 500.0)], "1. " + sentence)
    lower = _il_paragraph([(72.0, 400.0, 300.0)], "2. " + sentence)
    page = _il_page([upper, lower])
    assert attach_layout_plans(_Docs([page])) is True
    links = _list_links_by_id(page.layout_plan)
    assert links[upper.layout_region_id].flow_next_id == lower.layout_region_id
    assert (
        links[upper.layout_region_id].list_chain_id
        == links[lower.layout_region_id].list_chain_id
    )
    again = upper.layout_region_id
    assert attach_layout_plans(_Docs([page])) is True
    assert upper.layout_region_id == again


def test_formula_tagged_bullet_still_chains():
    """Styles wraps the bullet in a formula. The item is still a list."""
    sentence = "This is a readable English sentence for the list item. "
    upper = _bullet_formula_paragraph([(72.0, 400.0, 500.0)], "• " + sentence)
    lower = _bullet_formula_paragraph([(72.0, 400.0, 300.0)], "• " + sentence)
    plain = _il_paragraph(
        [(72.0, 400.0, 200.0)],
        "This is a readable English sentence and not a list item. ",
        role="formula",
    )
    page = _il_page([upper, lower, plain])
    assert attach_layout_plans(_Docs([page])) is True
    assert [item.base_strategy for item in page.layout_plan.decisions] == [
        "list",
        "list",
        "preserve",
    ]
    links = _list_links_by_id(page.layout_plan)
    assert links[upper.layout_region_id].flow_next_id == lower.layout_region_id
    assert plain.layout_region_id not in links
    assert page.layout_plan.column_links == ()


def test_bullet_on_a_stair_is_not_stacked():
    stair = [
        (100.0, 570.0, 160.0),
        (112.0, 570.0, 145.0),
        (124.0, 570.0, 130.0),
        (136.0, 570.0, 115.0),
    ]
    facts = _facts_with(
        stair,
        text="• The free edge steps inward.",
        marker=marker_from_glyph("• The free edge steps inward.", "Times-Roman"),
    )
    plan = build_plan(facts)
    assert plan.decisions[0].base_strategy == "preserve"
    assert plan.decisions[0].fallback == "list_and_shaped"
    assert plan.list_links == ()
    assert plan.column_links == ()


def test_a_mid_sentence_stair_stays_one_paragraph():
    """The straight run still ends with ``are``. Cutting there sticks the next line out."""
    lines = [(102.0, 510.0, 500.0 - 15.0 * i) for i in range(4)]
    lines.extend((102.0, 480.0 - 50.0 * i, 440.0 - 15.0 * i) for i in range(5))
    pieces = _body_pieces(9)
    pieces[3] = "when their nipples are "
    page = _il_page([_folded_paragraph(lines, pieces)])
    split_mixed_column_wraps(page)
    assert len(page.pdf_paragraph) == 1


def test_full_lines_then_a_stair_split_into_column_and_wrap():
    """A wide run glued to a stair becomes two paragraphs. Each keeps its glyphs."""
    lines = [(102.0, 510.0, 500.0 - 15.0 * i) for i in range(4)]
    lines.extend((102.0, 480.0 - 50.0 * i, 440.0 - 15.0 * i) for i in range(5))
    pieces = _body_pieces(9)
    mixed = _folded_paragraph(lines, pieces)
    below = _folded_paragraph(
        [(102.0, 510.0, 200.0 - 15.0 * i) for i in range(4)],
        _body_pieces(4),
    )
    page = _il_page([mixed, below])
    split_mixed_column_wraps(page)
    assert [len(_glyphs(paragraph)) for paragraph in page.pdf_paragraph] == [4, 5, 4]
    assert attach_layout_plans(_Docs([page])) is True
    assert [item.base_strategy for item in page.layout_plan.decisions] == [
        "rect_flow",
        "shaped_pocket",
        "rect_flow",
    ]
    assert _glyph_text(page.pdf_paragraph[0]) == "".join(pieces[:4])
    assert _glyph_text(page.pdf_paragraph[1]) == "".join(pieces[4:])


def test_stair_then_full_lines_splits_the_straight_run_off():
    lines = [(102.0, 510.0 - 40.0 * i, 500.0 - 15.0 * i) for i in range(4)]
    lines.extend((102.0, 510.0, 440.0 - 15.0 * i) for i in range(4))
    pieces = _body_pieces(8)
    page = _il_page([_folded_paragraph(lines, pieces)])
    split_mixed_column_wraps(page)
    assert attach_layout_plans(_Docs([page])) is True
    assert [item.base_strategy for item in page.layout_plan.decisions] == [
        "shaped_pocket",
        "rect_flow",
    ]
    assert _glyph_text(page.pdf_paragraph[1]) == "".join(pieces[4:])


def test_straight_column_is_not_split():
    lines = [(102.0, 510.0, 400.0 - 15.0 * i) for i in range(8)]
    page = _il_page([_folded_paragraph(lines, _body_pieces(8))])
    split_mixed_column_wraps(page)
    assert len(page.pdf_paragraph) == 1
    assert attach_layout_plans(_Docs([page])) is True
    assert page.layout_plan.decisions[0].base_strategy == "rect_flow"


def test_pure_stair_is_not_split():
    lines = [(102.0, 510.0 - 30.0 * i, 400.0 - 15.0 * i) for i in range(8)]
    page = _il_page([_folded_paragraph(lines, _body_pieces(8))])
    split_mixed_column_wraps(page)
    assert len(page.pdf_paragraph) == 1
    assert attach_layout_plans(_Docs([page])) is True
    assert page.layout_plan.decisions[0].base_strategy == "shaped_pocket"


def test_flat_tip_of_a_stair_stays_with_the_wrap():
    lines = [(102.0, 510.0 - 30.0 * i, 400.0 - 15.0 * i) for i in range(6)]
    lines.extend((102.0, 330.0, 310.0 - 15.0 * i) for i in range(2))
    page = _il_page([_folded_paragraph(lines, _body_pieces(8))])
    split_mixed_column_wraps(page)
    assert len(page.pdf_paragraph) == 1
    assert attach_layout_plans(_Docs([page])) is True
    assert page.layout_plan.decisions[0].base_strategy == "shaped_pocket"


def test_bullet_on_a_mixed_stair_stays_one_paragraph():
    lines = [(102.0, 510.0, 500.0 - 15.0 * i) for i in range(4)]
    lines.extend((102.0, 480.0 - 50.0 * i, 440.0 - 15.0 * i) for i in range(5))
    pieces = _body_pieces(9)
    pieces[0] = "• " + pieces[0]
    paragraph = _folded_paragraph(lines, pieces)
    page = _il_page([paragraph])
    split_mixed_column_wraps(page)
    assert page.pdf_paragraph == [paragraph]
    assert attach_layout_plans(_Docs([page])) is True
    assert page.layout_plan.decisions[0].base_strategy == "preserve"
    assert page.layout_plan.decisions[0].fallback == "list_and_shaped"


def test_ragged_full_lines_then_a_stair_still_split():
    """A full run may rag by more than one shared edge, then the wrap drops away."""
    rights = (490.5, 486.8, 479.5, 488.2)
    lines = [(113.0, right, 500.0 - 15.0 * i) for i, right in enumerate(rights)]
    lines.extend((113.0, 370.0 - 30.0 * i, 440.0 - 15.0 * i) for i in range(5))
    pieces = _body_pieces(9)
    page = _il_page([_folded_paragraph(lines, pieces)])
    split_mixed_column_wraps(page)
    assert [len(_glyphs(paragraph)) for paragraph in page.pdf_paragraph] == [4, 5]
    assert attach_layout_plans(_Docs([page])) is True
    assert [item.base_strategy for item in page.layout_plan.decisions] == [
        "rect_flow",
        "shaped_pocket",
    ]


def test_two_wide_lines_on_a_stair_stay_with_the_wrap():
    """The top of a circle is a little wider. Those lines are still the wrap."""
    lines = [(161.0, 504.0, 500.0), (161.0, 506.5, 485.0)]
    lines.extend((161.0, 440.0 - 20.0 * i, 470.0 - 15.0 * i) for i in range(6))
    page = _il_page([_folded_paragraph(lines, _body_pieces(8))])
    split_mixed_column_wraps(page)
    assert len(page.pdf_paragraph) == 1
    assert attach_layout_plans(_Docs([page])) is True
    assert page.layout_plan.decisions[0].base_strategy == "shaped_pocket"


def test_reviewed_stairs_stay_one_paragraph():
    gold_path = Path("tests/golden/layout_plan/shaped_review.json")
    gold = json.loads(gold_path.read_text())
    kept = [item for item in gold["items"] if item["expected_shaped_pocket"]]
    assert kept
    for item in kept:
        lines = [(x0, x1, y) for x0, x1, y in item["lines"]]
        page = _il_page([_folded_paragraph(lines, _body_pieces(len(lines)))])
        split_mixed_column_wraps(page)
        assert len(page.pdf_paragraph) == 1, item["sample_id"]


def _body_pieces(count: int) -> list[str]:
    sentence = "This is a readable English sentence for the body column. "
    return [sentence for _ in range(count)]


def _folded_paragraph(lines, pieces, role="body"):
    paragraph = _same_style_paragraph(lines, "", role=role)
    chars = _glyphs(paragraph)
    for char, piece in zip(chars, pieces, strict=True):
        char.char_unicode = piece
    paragraph.unicode = "".join(pieces)
    paragraph.layout_id = None
    return paragraph


def _glyph_text(paragraph) -> str:
    return "".join(getattr(char, "char_unicode", None) or "" for char in _glyphs(paragraph))


def _glyphs(paragraph):
    found = []
    for composition in paragraph.pdf_paragraph_composition:
        found.extend(composition_characters(composition))
    return found


class _Unit:
    def __init__(self, text, width):
        self.width = width
        self.is_space = text == " "
        self.char = None
        self._text = text

    def try_get_unicode(self):
        return self._text


class _Box:
    def __init__(self, x, y, x2, y2):
        self.x = x
        self.y = y
        self.x2 = x2
        self.y2 = y2


class _Char:
    def __init__(self, y, y2):
        self.box = _Box(72, y, 90, y2)


class _Metrics:
    def __init__(self, widths):
        self.per_line_widths = list(widths)
        self.line_count = len(widths)


class _Page:
    def __init__(self, paragraphs, plan):
        self.pdf_paragraph = paragraphs
        self.layout_plan = plan


class _Docs:
    def __init__(self, pages):
        self.page = pages


def _region_decision(region_id, strategy):
    return RegionDecision(
        region_id=region_id,
        base_strategy=strategy,
        modifiers=(),
        confidence=0.9,
        plugin_id=strategy,
        plugin_version="1",
        evidence=(),
        fallback=None,
        rejected=(),
    )


def _pocket_plan(*region_ids, extra=()):
    decisions = [_region_decision(region_id, "shaped_pocket") for region_id in region_ids]
    return LayoutPlan(
        "synthetic",
        0,
        "single_page",
        tuple(decisions) + tuple(extra),
        pocket_links=tuple(
            PocketLink(region_id, "right", 113.0, (100.0,)) for region_id in region_ids
        ),
    )


def _ink_char(x, y, x2, y2):
    return type("_Glyph", (), {"char_unicode": "文", "box": _Box(x, y, x2, y2)})()


def _text_paragraph(region_id, box, text):
    paragraph = type("_Para", (), {})()
    paragraph.layout_region_id = region_id
    paragraph.box = box
    paragraph.unicode = text
    paragraph.layout_label = None
    paragraph.pdf_paragraph_composition = []
    return paragraph


def _placed_paragraph(region_id, *, box, chars=None, widths=None):
    line = _Box(box.x, box.y, box.x2, box.y2)
    composition = type(
        "_Comp",
        (),
        {
            "pdf_line": type(
                "_Line",
                (),
                {"box": line, "pdf_character": list(chars or [])},
            )(),
            "pdf_formula": None,
            "pdf_character": None,
            "pdf_same_style_characters": None,
        },
    )()
    paragraph = type("_Para", (), {})()
    paragraph.layout_region_id = region_id
    paragraph.box = box
    paragraph.alignment = "center"
    paragraph.reference_metrics = _Metrics(widths or [400.0, 80.0])
    paragraph.pdf_paragraph_composition = [composition]
    return paragraph


def _bullet_formula_paragraph(lines, text):
    paragraph = _il_paragraph(lines, text, role="formula")
    glyph = type(
        "_Glyph",
        (),
        {
            "char_unicode": "•",
            "pdf_style": type("_Style", (), {"font_id": "ZapfDingbats"})(),
        },
    )()
    space = type(
        "_Glyph",
        (),
        {
            "char_unicode": " ",
            "pdf_style": type("_Style", (), {"font_id": "Times-Roman"})(),
        },
    )()
    formula = type("_Formula", (), {"pdf_character": [glyph, space]})()
    formula_comp = type(
        "_Comp",
        (),
        {
            "pdf_line": None,
            "pdf_character": None,
            "pdf_formula": formula,
            "pdf_same_style_characters": None,
        },
    )()
    paragraph.pdf_paragraph_composition = [
        formula_comp,
        *paragraph.pdf_paragraph_composition,
    ]
    return paragraph


def _same_style_paragraph(lines, text, role="body"):
    """Styles folds every source line into one run. The glyphs keep their boxes."""
    chars = []
    for index, (x0, x1, y) in enumerate(lines):
        chars.append(
            type(
                "_Glyph",
                (),
                {
                    "char_unicode": text if index == 0 else "",
                    "pdf_style": type("_Style", (), {"font_id": "Times-Roman"})(),
                    "box": _Box(x0, y - 10, x1, y),
                },
            )()
        )
    same = type(
        "_Same",
        (),
        {"box": _Box(lines[0][0], lines[-1][2] - 10, lines[0][1], lines[0][2]), "pdf_character": chars},
    )()
    composition = type(
        "_Comp",
        (),
        {
            "pdf_line": None,
            "pdf_character": None,
            "pdf_formula": None,
            "pdf_same_style_characters": same,
        },
    )()
    paragraph = _il_paragraph(lines, text, role=role)
    paragraph.pdf_paragraph_composition = [composition]
    return paragraph


def _il_paragraph(lines, text, role="body"):
    compositions = []
    for x0, x1, y in lines:
        compositions.append(
            type(
                "_Comp",
                (),
                {
                    "pdf_line": type(
                        "_Line",
                        (),
                        {
                            "box": _Box(x0, y - 10, x1, y),
                            "pdf_character": [],
                        },
                    )(),
                    "pdf_character": None,
                    "pdf_formula": None,
                    "pdf_same_style_characters": None,
                },
            )()
        )
    paragraph = type("_Para", (), {})()
    paragraph.box = _Box(lines[0][0], lines[-1][2] - 10, lines[0][1], lines[0][2])
    paragraph.unicode = text
    paragraph.layout_label = None
    paragraph.layout_intent = type(
        "_Intent",
        (),
        {
            "role": type("_Role", (), {"value": role})(),
            "text_on_photo": False,
        },
    )()
    paragraph.pdf_paragraph_composition = compositions
    paragraph.layout_region_id = None
    return paragraph


def _image_form(x0, y0, x1, y1, form_type="image"):
    form = type("_Form", (), {})()
    form.box = _Box(x0, y0, x1, y1)
    form.form_type = form_type
    return form


def _il_page(paragraphs):
    box = _Box(0, 0, 612, 792)
    page = type("_Page", (), {})()
    page.page_number = 3
    page.cropbox = type("_Holder", (), {"box": box})()
    page.mediabox = page.cropbox
    page.pdf_paragraph = paragraphs
    page.layout_plan = None
    return page


def _plugins_of(facts):
    from babeldoc.format.pdf.document_il.utils.layout_plan.plugins import (
        DEFAULT_PLUGINS,
    )

    found = []
    for plugin in DEFAULT_PLUGINS:
        found.extend(plugin.analyze(facts))
    return found


def _write_pdf(path: Path, text: str) -> None:
    document = pymupdf.open()
    page = document.new_page(width=612, height=792)
    page.insert_text((72, 72), text, fontsize=12)
    document.save(path)
    document.close()
