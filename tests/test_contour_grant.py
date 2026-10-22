"""The named-contour grant is part of the plan, not a second claim."""

from babeldoc.format.pdf.document_il.utils.layout_plan.compose import build_plan
from babeldoc.format.pdf.document_il.utils.layout_plan.facts import SourceBlock
from babeldoc.format.pdf.document_il.utils.layout_plan.facts import build_facts
from babeldoc.format.pdf.document_il.utils.layout_plan.line_edges import (
    assign_line_edge_boxes,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.line_edges import line_edges_for
from babeldoc.format.pdf.document_il.utils.layout_plan.line_edges import (
    with_line_edge_links,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.log import records
from babeldoc.format.pdf.document_il.utils.layout_plan.model import LayoutPlan
from babeldoc.format.pdf.document_il.utils.layout_plan.model import LineBox
from babeldoc.format.pdf.document_il.utils.layout_plan.model import LineEdgeLink
from babeldoc.format.pdf.document_il.utils.layout_plan.model import RegionDecision
from babeldoc.format.pdf.document_il.utils.layout_plan.model import Rejection
from babeldoc.format.pdf.document_il.utils.layout_plan.model import edge_digest
from babeldoc.format.pdf.document_il.utils.layout_plan.model import make_region_id
from babeldoc.format.pdf.document_il.utils.rect_flow_stack import attach_layout_plans

_TAPER = [(100, 500 - i * 20, 700 - i * 15) for i in range(6)]
_CALF_UPPER = [(102.0, 512.65, 700.0), (102.0, 512.65, 680.0)]
_BODY_BELOW = [
    (231.0, 512.66, 600.0),
    (231.0, 512.59, 580.0),
    (231.0, 512.59, 560.0),
    (231.0, 384.42, 540.0),
]
_CALF_LOWER = [
    (231.0, 512.66, 640.0),
    (231.0, 512.59, 620.0),
    (231.0, 512.59, 600.0),
    (231.0, 384.42, 580.0),
]


def _facts(lines, *, role="body", gate="single_page", on_photo=False, fingerprint="doc"):
    return build_facts(
        source_fingerprint=fingerprint,
        page_index=0,
        page_width=612.0,
        page_height=792.0,
        input_gate=gate,
        text_health=1.0,
        blocks=[
            SourceBlock(
                lines=tuple(LineBox(*line) for line in lines),
                role=role,
                text_on_photo=on_photo,
            )
        ],
    )


def _plan(lines, **kwargs):
    facts = _facts(lines, **kwargs)
    return facts, build_plan(facts)


def _decision(region_id, *, fallback, reason=None, confidence=0.4):
    rejected = ()
    if reason is not None:
        rejected = (
            Rejection("rect_flow", "1", "rect_flow", confidence, reason),
        )
    return RegionDecision(
        region_id=region_id,
        base_strategy="preserve",
        modifiers=(),
        confidence=0.0,
        plugin_id=None,
        plugin_version=None,
        evidence=(),
        fallback=fallback,
        rejected=rejected,
    )


def test_a_protected_role_is_preserve_and_gets_no_fill():
    for role in ("title", "pull_quote", "chrome"):
        facts, plan = _plan(_TAPER, role=role)
        decision = plan.decisions[0]
        assert decision.base_strategy == "preserve", role
        assert decision.contour_status == "refused", role
        assert decision.contour_reason == "protected_role", role
        assert plan.line_edge_links == (), role
        assert plan.shared_contours == (), role


def test_an_unmatched_body_keeps_the_scanned_frame():
    lines = [
        (100.0, 400.0, 200.0),
        (106.0, 400.0, 184.0),
        (112.0, 400.0, 168.0),
        (118.0, 400.0, 152.0),
    ]
    facts = _facts(lines, role="body")
    plan = LayoutPlan(
        facts.source_fingerprint,
        facts.page_index,
        "single_page",
        (_decision(facts.regions[0].region_id, fallback="no_confident_base"),),
    )
    updated = with_line_edge_links(facts, plan, catalog=())
    decision = updated.decisions[0]
    assert decision.contour_status == "frame"
    assert decision.contour_plugin is None
    assert updated.shared_contours == ()
    assert len(updated.line_edge_links) == 1
    link = updated.line_edge_links[0]
    assert link.edges == tuple((line[0], line[1]) for line in lines)
    assert [level.top for level in link.levels] == [line[2] for line in lines]
    paragraph = type("Para", (), {})()
    paragraph.layout_region_id = facts.regions[0].region_id
    page = type("Page", (), {"layout_plan": updated})()
    assert line_edges_for(page, paragraph) is link


def test_a_rectangular_body_stays_the_union():
    lines = [(100.0, 400.0, 200.0 - index * 16.0) for index in range(4)]
    facts = _facts(lines, role="body")
    plan = LayoutPlan(
        facts.source_fingerprint,
        facts.page_index,
        "single_page",
        (_decision(facts.regions[0].region_id, fallback="no_confident_base"),),
    )
    updated = with_line_edge_links(facts, plan, catalog=())
    assert updated.line_edge_links == ()
    assert updated.decisions[0].contour_status == "unmatched"


def test_photo_text_gets_no_fill():
    _facts, plan = _plan(_TAPER, on_photo=True)
    assert plan.decisions[0].base_strategy == "preserve"
    assert plan.decisions[0].contour_reason == "protected_role"
    assert plan.line_edge_links == ()


def test_a_refused_link_does_not_move_the_box():
    facts, plan = _plan(_TAPER, role="title")
    region_id = facts.regions[0].region_id
    plan = LayoutPlan(
        plan.source_fingerprint,
        plan.page_index,
        plan.input_gate,
        plan.decisions,
        line_edge_links=(LineEdgeLink(region_id, ((100.0, 700.0),)),),
        identity_scope=plan.identity_scope,
    )
    box = type("Box", (), {"x": 10.0, "x2": 20.0, "y": 0.0, "y2": 12.0})()
    paragraph = type("Para", (), {})()
    paragraph.layout_region_id = region_id
    paragraph.box = box
    paragraph.alignment = "left"
    paragraph.first_line_indent = 4
    page = type("Page", (), {"layout_plan": plan, "pdf_paragraph": [paragraph]})()
    assign_line_edge_boxes(page)
    assert box.x == 10.0
    assert box.x2 == 20.0
    assert paragraph.first_line_indent == 4


def test_a_body_records_the_fill_residual_not_its_confidence():
    facts, plan = _plan(_TAPER, role="body")
    decision = plan.decisions[0]
    assert decision.confidence == 0.9
    assert decision.contour_status == "matched"
    assert decision.contour_plugin == "taper/left_pin"
    assert isinstance(decision.contour_residual, float)
    assert isinstance(decision.contour_threshold, float)
    assert decision.contour_residual != decision.confidence
    assert decision.contour_version == "1"
    rows = records(facts, plan)
    match = rows[1]
    assert match["paradigm"] == decision.contour_plugin
    assert match["residual"] == decision.contour_residual
    assert "0.9" not in match["line"]
    assert str(decision.confidence) not in match["line"]


def test_a_closed_gate_does_not_touch_the_catalog():
    facts = _facts(_TAPER, gate="spread")
    plan = LayoutPlan(
        facts.source_fingerprint,
        facts.page_index,
        "spread",
        (_decision(facts.regions[0].region_id, fallback="spread"),),
    )
    updated = with_line_edge_links(facts, plan, catalog=object())
    assert updated.line_edge_links == ()
    assert updated.shared_contours == ()
    assert updated.decisions[0].contour_status == "refused"
    assert updated.decisions[0].contour_reason == "spread"


def test_a_base_conflict_does_not_claim():
    facts = _facts(_TAPER)
    plan = LayoutPlan(
        facts.source_fingerprint,
        facts.page_index,
        "single_page",
        (_decision(facts.regions[0].region_id, fallback="conflict_tie"),),
    )
    updated = with_line_edge_links(facts, plan, catalog=object())
    assert updated.line_edge_links == ()
    assert updated.decisions[0].contour_status == "refused"
    assert updated.decisions[0].contour_reason == "conflict_tie"


def test_below_confidence_does_not_claim():
    facts = _facts(_TAPER)
    plan = LayoutPlan(
        facts.source_fingerprint,
        facts.page_index,
        "single_page",
        (
            _decision(
                facts.regions[0].region_id,
                fallback="no_confident_base",
                reason="below_confidence",
            ),
        ),
    )
    updated = with_line_edge_links(facts, plan, catalog=object())
    assert updated.line_edge_links == ()
    assert updated.decisions[0].contour_status == "refused"
    assert updated.decisions[0].contour_reason == "below_confidence"


def test_the_same_input_builds_the_same_plan():
    facts = _facts(_TAPER, role="title")
    assert build_plan(facts).to_dict() == build_plan(facts).to_dict()


def test_two_documents_do_not_share_a_region_id():
    lines = (LineBox(72.0, 400.0, 500.0),)
    assert make_region_id("doc-a", 0, 0, lines) != make_region_id("doc-b", 0, 0, lines)


def test_an_unscoped_attach_says_ids_are_not_cross_document():
    paragraph = _paragraph([(72.0, 400.0, 500.0), (72.0, 400.0, 480.0)])
    page = _page([paragraph])
    assert attach_layout_plans(_docs([page])) is True
    plan = page.layout_plan
    assert plan.identity_scope == "unscoped"
    assert plan.source_fingerprint.startswith("unscoped:")
    assert plan.source_fingerprint.endswith(":il")


def test_a_title_beside_a_body_has_no_shared_contour():
    facts = build_facts(
        source_fingerprint="doc",
        page_index=0,
        page_width=612.0,
        page_height=792.0,
        input_gate="single_page",
        text_health=1.0,
        blocks=[
            _block(_TAPER, "title"),
            _block(_BODY_BELOW, "body"),
        ],
    )
    assert facts.regions[0].below_id == facts.regions[1].region_id
    plan = build_plan(facts)
    joined = [(line[0], line[1]) for line in _TAPER + _BODY_BELOW]
    assert edge_digest(joined) not in {item.digest for item in plan.shared_contours}
    assert plan.decisions[0].contour_status == "refused"
    assert plan.line_edge_links == () or all(
        link.region_id != facts.regions[0].region_id for link in plan.line_edge_links
    )


def test_an_eligible_pair_stores_the_joined_digest():
    facts = build_facts(
        source_fingerprint="doc",
        page_index=0,
        page_width=612.0,
        page_height=792.0,
        input_gate="single_page",
        text_health=1.0,
        blocks=[_block(_CALF_UPPER, "body"), _block(_CALF_LOWER, "body")],
    )
    assert facts.regions[0].below_id == facts.regions[1].region_id
    plan = build_plan(facts)
    joined = [(line[0], line[1]) for line in _CALF_UPPER + _CALF_LOWER]
    digest = edge_digest(joined)
    found = [item for item in plan.shared_contours if item.digest == digest]
    assert len(found) == 1
    assert found[0].plugin
    assert isinstance(found[0].residual, float)
    assert isinstance(found[0].threshold, float)
    assert found[0].version == "1"
    # The claim step is synthetic. The stored samples are the source tops,
    # so a Chinese line at the page y still hits the contour.
    assert [level.top for level in found[0].levels] == [
        line[2] for line in _CALF_UPPER + _CALF_LOWER
    ]
    assert all(level.top < 900.0 for level in found[0].levels)


def _block(lines, role):
    return SourceBlock(
        lines=tuple(LineBox(*line) for line in lines),
        role=role,
    )


def _box(x, y, x2, y2):
    return type("Box", (), {"x": x, "y": y, "x2": x2, "y2": y2})()


def _paragraph(lines):
    text = "This is a readable English sentence for the straight column."
    compositions = []
    for x0, x1, y in lines:
        compositions.append(
            type(
                "Comp",
                (),
                {
                    "pdf_line": type(
                        "Line",
                        (),
                        {"box": _box(x0, y - 10, x1, y), "pdf_character": []},
                    )(),
                    "pdf_character": None,
                    "pdf_formula": None,
                    "pdf_same_style_characters": None,
                },
            )()
        )
    paragraph = type("Para", (), {})()
    paragraph.box = _box(lines[0][0], lines[-1][2] - 10, lines[0][1], lines[0][2])
    paragraph.unicode = text
    paragraph.layout_label = None
    paragraph.layout_intent = type(
        "Intent",
        (),
        {
            "role": type("Role", (), {"value": "body"})(),
            "text_on_photo": False,
        },
    )()
    paragraph.pdf_paragraph_composition = compositions
    paragraph.layout_region_id = None
    return paragraph


def _page(paragraphs):
    page = type("Page", (), {})()
    page.page_number = 3
    page.cropbox = type("Holder", (), {"box": _box(0, 0, 612, 792)})()
    page.mediabox = page.cropbox
    page.pdf_paragraph = paragraphs
    page.pdf_figure = []
    page.pdf_form = []
    page.layout_plan = None
    return page


def _docs(pages):
    return type("Docs", (), {"page": pages})()
