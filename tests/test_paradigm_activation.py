"""Production fills follow the closed allowlist. Claims stay on."""

from __future__ import annotations

import pytest
from babeldoc.format.pdf.document_il.utils.layout_plan.compose import build_plan
from babeldoc.format.pdf.document_il.utils.layout_plan.facts import SourceBlock
from babeldoc.format.pdf.document_il.utils.layout_plan.facts import build_facts
from babeldoc.format.pdf.document_il.utils.layout_plan.line_edges import (
    shared_contour_for,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.line_edges import (
    with_line_edge_links,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.model import LineBox
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms import load_catalog
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.activation import (
    ENABLED_SYSTEM_FILLS,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.contract import (
    Paradigm,
)

# The closed set from the 2026-11-04 status. Not derived by scanning fills.
_CLOSED = frozenset(
    {
        "both/wider_below",
        "bow/left_bulge",
        "bow/left_inset",
        "bow/right_bulge",
        "bow/right_inset",
        "center/axis",
        "hang/deep",
        "hang/shallow",
        "indent/first_line",
        "mark/bullet_hang",
        "mark/bullet_plain",
        "mark/bullet_repeated",
        "mark/serial_hang",
        "mark/serial_plain",
        "mark/serial_repeated",
        "rag/deep_right",
        "rag/left_edge",
        "rag/right_edge",
        "rect/full_column",
        "rect/light_column",
        "step/left_lower_wide",
        "step/left_spur",
        "step/left_upper_wide",
        "step/right_lower_wide",
        "step/right_spur",
        "step/right_upper_wide",
        "taper/left_pin",
        "taper/right_pin",
        "toc/plain",
    }
)
_REPEATED = (
    [100.0, 360.0, 200.0],
    [118.0, 400.0, 184.0],
    [118.0, 400.0, 168.0],
    [100.0, 380.0, 152.0],
    [118.0, 390.0, 136.0],
    [118.0, 370.0, 120.0],
)


def _facts(groups, *, role=None):
    return build_facts(
        source_fingerprint="synthetic",
        page_index=0,
        page_width=612.0,
        page_height=792.0,
        input_gate="single_page",
        text_health=0.9,
        blocks=[
            SourceBlock(
                lines=tuple(LineBox(*line) for line in group),
                role=role,
            )
            for group in groups
        ],
    )


def _custom_fill(lines):
    return tuple((float(line[0]), float(line[1])) for line in lines)


def _custom_claim(_edges, lines):
    if len(lines) == 1:
        return 0.0
    return None


@pytest.fixture
def repeated_facts():
    return _facts((_REPEATED,))


def test_paused_repeated_hang_is_recorded_without_contour(repeated_facts):
    plan = build_plan(repeated_facts)
    decision = plan.decisions[0]
    assert decision.contour_plugin == "hang/repeated"
    assert decision.contour_status == "recorded"
    assert plan.line_edge_links == ()
    assert plan.shared_contours == ()


def test_catalog_keeps_identification_but_limits_default_fills():
    catalog = load_catalog()
    assert len(catalog) == 30
    assert sum(item.fill is not None for item in catalog) == 29
    filled = {item.name for item in catalog if item.fill is not None}
    assert filled == _CLOSED
    assert "hang/repeated" in {item.name for item in catalog}
    assert ENABLED_SYSTEM_FILLS == _CLOSED


def test_explicit_catalog_enables_repeated_hang_fill(repeated_facts):
    catalog = load_catalog(enabled_fills=_CLOSED | {"hang/repeated"})
    enabled = next(item for item in catalog if item.name == "hang/repeated")
    assert enabled.fill is not None
    paused = next(item for item in load_catalog() if item.name == "hang/repeated")
    assert paused.fill is None
    assert sum(item.fill is not None for item in load_catalog()) == 29
    plan = with_line_edge_links(
        repeated_facts,
        build_plan(repeated_facts),
        catalog=catalog,
    )
    decision = plan.decisions[0]
    assert decision.contour_plugin == "hang/repeated"
    assert decision.contour_status == "matched"
    assert len(plan.line_edge_links) == 1
    assert plan.shared_contours
    assert {item.plugin for item in plan.shared_contours} == {"hang/repeated"}


def test_shared_contour_does_not_reload_a_paused_fill():
    assert shared_contour_for(_REPEATED) is None
    catalog = load_catalog(enabled_fills=_CLOSED | {"hang/repeated"})
    contour = shared_contour_for(_REPEATED, catalog)
    assert contour is not None
    assert contour.plugin == "hang/repeated"


def test_a_paused_pair_does_not_reuse_the_module_fill():
    lower = [[x0, x1, top - 140.0] for x0, x1, top in _REPEATED]
    facts = _facts((_REPEATED, lower))
    assert facts.regions[0].below_id == facts.regions[1].region_id
    plan = build_plan(facts)
    assert [item.contour_plugin for item in plan.decisions] == [
        "hang/repeated",
        "hang/repeated",
    ]
    assert [item.contour_status for item in plan.decisions] == [
        "recorded",
        "recorded",
    ]
    assert plan.line_edge_links == ()
    assert all(item.plugin != "hang/repeated" for item in plan.shared_contours)


def test_custom_extra_fill_stays_off_unless_named():
    added = Paradigm("custom/one_line", 8.0, _custom_claim, _custom_fill)
    catalog = load_catalog((added,))
    item = next(item for item in catalog if item.name == "custom/one_line")
    assert item.fill is None
    assert next(item.fill is not None for item in catalog if item.name == "toc/plain")
    enabled = load_catalog(
        (added,),
        enabled_fills=_CLOSED | {"custom/one_line"},
    )
    item = next(item for item in enabled if item.name == "custom/one_line")
    assert item.fill is _custom_fill
    assert sum(item.fill is not None for item in enabled) == 30


def test_unknown_enabled_fill_is_rejected():
    with pytest.raises(ValueError, match="no/such"):
        load_catalog(enabled_fills=frozenset({"rect/full_column", "no/such"}))


def test_protected_role_still_has_no_links():
    for role in ("title", "pull_quote", "chrome"):
        plan = build_plan(_facts((_REPEATED,), role=role))
        decision = plan.decisions[0]
        assert decision.contour_status == "refused", role
        assert decision.contour_reason == "protected_role", role
        assert plan.line_edge_links == (), role
        assert plan.shared_contours == (), role
