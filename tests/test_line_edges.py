"""Line edges written by the modules that fill. The rest stay claim-only."""

from __future__ import annotations

import inspect

from babeldoc.format.pdf.document_il.utils.layout_plan.column_chain import (
    with_column_links,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.compose import build_plan
from babeldoc.format.pdf.document_il.utils.layout_plan.facts import SourceBlock
from babeldoc.format.pdf.document_il.utils.layout_plan.facts import build_facts
from babeldoc.format.pdf.document_il.utils.layout_plan.line_edges import (
    assign_line_edge_boxes,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.line_edges import (
    interval_for_line_edges,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.list_chain import with_list_links
from babeldoc.format.pdf.document_il.utils.layout_plan.model import ContourLevel
from babeldoc.format.pdf.document_il.utils.layout_plan.model import LineBox
from babeldoc.format.pdf.document_il.utils.layout_plan.model import LineEdgeLink
from babeldoc.format.pdf.document_il.utils.layout_plan.model import MarkerEvidence
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms import load_catalog
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.both.wider_below import (
    fill,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.bow.right_bulge import (
    fill as right_bulge_fill,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.bow.right_inset import (
    fill as right_inset_fill,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.contract import (
    Paradigm,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.hang.deep import (
    fill as deep_fill,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.hang.repeated import (
    fill as repeated_fill,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.hang.shallow import (
    fill as shallow_fill,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.mark.bullet_hang import (
    fill as bullet_hang_fill,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.mark.bullet_plain import (
    fill as bullet_plain_fill,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.mark.bullet_repeated import (
    fill as bullet_repeated_fill,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.mark.serial_hang import (
    fill as serial_hang_fill,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.mark.serial_plain import (
    fill as serial_plain_fill,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.mark.serial_repeated import (
    fill as serial_repeated_fill,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.rag.deep_right import (
    fill as deep_right_fill,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.rag.left_edge import (
    fill as left_edge_fill,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.rag.right_edge import (
    fill as right_edge_fill,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.rect.full_column import (
    fill as full_column_fill,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.rect.light_column import (
    fill as light_column_fill,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.step.right_lower_wide import (
    fill as lower_wide_fill,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.step.right_spur import (
    fill as spur_fill,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.step.right_upper_wide import (
    fill as upper_wide_fill,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.taper.left_pin import (
    fill as left_pin_fill,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.taper.right_pin import (
    fill as right_pin_fill,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.pocket_chain import (
    with_pocket_links,
)
from babeldoc.format.pdf.document_il.utils.rect_flow_stack import _planned_ids


def _opening_lines():
    return [
        [140.0 - index * 8.0, 360.0 + index * 8.0, 200.0 - index * 16.0]
        for index in range(6)
    ]


def _facts(lines, gate="single_page", marker=None, source_text=""):
    return build_facts(
        source_fingerprint="synthetic",
        page_index=0,
        page_width=612.0,
        page_height=792.0,
        input_gate=gate,
        text_health=0.9,
        blocks=[
            SourceBlock(
                lines=tuple(LineBox(*line) for line in lines),
                marker=marker,
                source_text=source_text,
            )
        ],
    )


def test_wider_below_fill_is_each_lines_own_edge():
    source = inspect.getsource(fill)
    assert "scanned_edge_gap" not in source
    pairs = fill(_opening_lines())
    assert pairs[0] == (140.0, 360.0)
    assert pairs[-1] == (100.0, 400.0)
    assert len(pairs) == 6


def test_wider_below_fill_omits_a_short_tail_that_keeps_opening():
    lines = [
        [224.016, 406.644, 245.069],
        [222.012, 409.644, 230.069],
        [219.012, 410.016, 215.069],
        [215.016, 416.628, 200.069],
        [211.020, 420.648, 185.069],
        [207.024, 425.676, 170.069],
        [202.020, 430.668, 155.069],
        [196.020, 436.644, 140.069],
        [190.020, 443.700, 125.069],
        [183.024, 447.996, 110.069],
        [175.020, 458.664, 95.069],
        [167.016, 467.664, 80.069],
        [158.016, 223.500, 65.069],
    ]
    pairs = fill(lines)
    assert len(pairs) == 12
    assert pairs[-1] == (167.016, 467.664)
    plan = build_plan(_facts(lines))
    assert len(plan.line_edge_links) == 1
    link = plan.line_edge_links[0]
    assert link.edges == pairs
    # The omitted tail is not a sample. A line far below the scan does
    # not inherit the last kept English edge.
    assert len(link.levels) == len(pairs)
    assert link.levels[-1].top == lines[-2][2]
    assert interval_for_line_edges(link, 99, 0.0, 10.0) is None


def test_only_wired_modules_carry_a_fill():
    catalog = {item.name: item for item in load_catalog()}
    wired = {
        "both/wider_below",
        "bow/right_bulge",
        "bow/right_inset",
        "center/axis",
        "hang/deep",
        "hang/repeated",
        "hang/shallow",
        "mark/bullet_hang",
        "mark/bullet_plain",
        "mark/bullet_repeated",
        "mark/serial_hang",
        "mark/serial_plain",
        "mark/serial_repeated",
        "rag/right_edge",
        "rag/left_edge",
        "rag/deep_right",
        "rect/full_column",
        "rect/light_column",
        "step/right_lower_wide",
        "step/right_spur",
        "step/right_upper_wide",
        "taper/left_pin",
        "taper/right_pin",
        "toc/plain",
    }
    for name in wired:
        assert callable(catalog[name].fill)
    for name, item in catalog.items():
        if name in wired:
            continue
        assert item.fill is None
    added = Paradigm("custom/one_line", 8.0, lambda _edges, _lines: None)
    assert added.fill is None


def test_right_inset_fill_keeps_each_scanned_right():
    source = inspect.getsource(right_inset_fill)
    assert "scanned_edge_gap" not in source
    lines = [
        [100.0, 400.0 - (4.0 * step), 200.0 - index * 16.0]
        for index, step in enumerate([0, 5, 9, 11, 13, 15, 14, 11, 8, 7])
    ]
    pairs = right_inset_fill(lines)
    assert pairs == tuple((line[0], line[1]) for line in lines)
    plan = build_plan(_facts(lines))
    assert len(plan.line_edge_links) == 1
    link = plan.line_edge_links[0]
    assert plan.decisions[0].contour_plugin == "bow/right_inset"
    assert plan.decisions[0].contour_status == "matched"
    assert link.alignment == "left"
    assert link.edges == pairs
    assert all(level.kind == "observed" for level in link.levels)
    assert interval_for_line_edges(link, 0, 190.0, 198.0) == (100.0, 400.0)
    assert interval_for_line_edges(link, 4, 112.0, 118.0) == (100.0, 340.0)


def test_right_bulge_fill_keeps_each_scanned_right():
    source = inspect.getsource(right_bulge_fill)
    assert "scanned_edge_gap" not in source
    lines = [
        [100.0, 400.0 - (4.0 * step), 200.0 - index * 16.0]
        for index, step in enumerate([20, 17, 16, 4, 0, 3, 4, 8, 7])
    ]
    pairs = right_bulge_fill(lines)
    assert pairs == tuple((line[0], line[1]) for line in lines)
    plan = build_plan(_facts(lines))
    assert len(plan.line_edge_links) == 1
    link = plan.line_edge_links[0]
    assert plan.decisions[0].contour_plugin == "bow/right_bulge"
    assert plan.decisions[0].contour_status == "matched"
    assert link.alignment == "left"
    assert link.edges == pairs
    assert all(level.kind == "observed" for level in link.levels)
    assert interval_for_line_edges(link, 0, 190.0, 198.0) == (100.0, 320.0)
    assert interval_for_line_edges(link, 4, 126.0, 134.0) == (100.0, 400.0)
    # The baseline sits on the wide sample. Clipping the narrow sample
    # above it must not pull the line back to that sample's right.
    assert interval_for_line_edges(link, 0, 132.0, 148.0) == (100.0, 400.0)


def test_right_edge_fill_is_each_lines_own_edge():
    source = inspect.getsource(right_edge_fill)
    assert "scanned_edge_gap" not in source
    lines = [
        [100.0, 200.0, 200.0],
        [100.0, 160.0, 184.0],
        [100.0, 190.0, 168.0],
        [100.0, 155.0, 152.0],
        [100.0, 180.0, 136.0],
    ]
    pairs = right_edge_fill(lines)
    assert pairs == tuple((line[0], line[1]) for line in lines)
    plan = build_plan(_facts(lines))
    assert len(plan.line_edge_links) == 1
    link = plan.line_edge_links[0]
    assert link.edges == pairs
    assert link.flow == "edge"
    # The old assertion used line_idx 1, so a Chinese line inherited the
    # second English width. The same height must answer the same x for
    # every index, and an index alone is not a width.
    assert all(level.kind == "observed" for level in link.levels)
    assert interval_for_line_edges(link, 1) is None
    assert interval_for_line_edges(link, 0, 172.0, 180.0) == (100.0, 160.0)
    assert interval_for_line_edges(link, 99, 172.0, 180.0) == (100.0, 160.0)


def test_left_edge_fill_is_each_lines_own_edge():
    source = inspect.getsource(left_edge_fill)
    assert "scanned_edge_gap" not in source
    lines = [
        [300.0, 500.0, 200.0],
        [250.0, 500.0, 184.0],
        [270.0, 500.0, 168.0],
        [220.0, 500.0, 152.0],
        [180.0, 500.0, 136.0],
    ]
    pairs = left_edge_fill(lines)
    assert pairs == tuple((line[0], line[1]) for line in lines)
    plan = build_plan(_facts(lines))
    assert len(plan.line_edge_links) == 1
    link = plan.line_edge_links[0]
    assert link.edges == pairs
    assert link.flow == "edge"
    # line_idx 1 used to mean the second English edge. Query the height
    # of that source line instead.
    assert all(level.kind == "observed" for level in link.levels)
    assert interval_for_line_edges(link, 0, 172.0, 180.0) == (250.0, 500.0)
    assert interval_for_line_edges(link, 99, 172.0, 180.0) == (250.0, 500.0)


def test_shallow_hang_fill_keeps_each_line_and_its_top():
    lines = [
        [100.0, 360.0, 200.0],
        [120.0, 400.0, 184.0],
        [120.0, 400.0, 168.0],
        [120.0, 380.0, 152.0],
    ]
    edges = shallow_fill(lines)
    assert edges[0] == (100.0, 360.0, 200.0)
    assert edges[1] == (120.0, 400.0, 184.0)
    plan = build_plan(_facts(lines))
    assert len(plan.line_edge_links) == 1
    link = plan.line_edge_links[0]
    assert plan.decisions[0].contour_plugin == "hang/shallow"
    assert plan.decisions[0].contour_status == "matched"
    assert link.alignment == "left"
    assert link.flow == "edge"
    assert link.edges == edges
    assert all(level.kind == "observed" for level in link.levels)
    assert interval_for_line_edges(link, 0, 190.0, 198.0) == (100.0, 360.0)
    assert interval_for_line_edges(link, 1, 170.0, 180.0) == (120.0, 400.0)
    assert interval_for_line_edges(link, 99, 170.0, 180.0) == (120.0, 400.0)


def test_deep_hang_fill_keeps_each_line_and_its_top():
    lines = [
        [100.0, 360.0, 200.0],
        [164.0, 400.0, 184.0],
        [164.0, 400.0, 168.0],
        [164.0, 380.0, 152.0],
    ]
    edges = deep_fill(lines)
    assert edges[0] == (100.0, 360.0, 200.0)
    assert edges[1] == (164.0, 400.0, 184.0)
    plan = build_plan(_facts(lines))
    assert len(plan.line_edge_links) == 1
    link = plan.line_edge_links[0]
    assert plan.decisions[0].contour_plugin == "hang/deep"
    assert plan.decisions[0].contour_status == "matched"
    assert link.alignment == "left"
    assert link.flow == "edge"
    assert link.edges == edges
    assert all(level.kind == "observed" for level in link.levels)
    assert interval_for_line_edges(link, 0, 190.0, 198.0) == (100.0, 360.0)
    assert interval_for_line_edges(link, 1, 170.0, 180.0) == (164.0, 400.0)
    assert interval_for_line_edges(link, 99, 170.0, 180.0) == (164.0, 400.0)


def test_repeated_hang_fill_keeps_each_line_and_its_top():
    lines = [
        [100.0, 360.0, 200.0],
        [118.0, 400.0, 184.0],
        [118.0, 400.0, 168.0],
        [100.0, 380.0, 152.0],
        [118.0, 390.0, 136.0],
        [118.0, 370.0, 120.0],
    ]
    edges = repeated_fill(lines)
    assert edges[0] == (100.0, 360.0, 200.0)
    assert edges[1] == (118.0, 400.0, 184.0)
    assert edges[3] == (100.0, 380.0, 152.0)
    plan = build_plan(_facts(lines))
    assert len(plan.line_edge_links) == 1
    link = plan.line_edge_links[0]
    assert plan.decisions[0].contour_plugin == "hang/repeated"
    assert plan.decisions[0].contour_status == "matched"
    assert link.alignment == "left"
    assert link.flow == "edge"
    assert link.edges == edges
    assert all(level.kind == "observed" for level in link.levels)
    assert interval_for_line_edges(link, 0, 190.0, 198.0) == (100.0, 360.0)
    assert interval_for_line_edges(link, 1, 170.0, 180.0) == (118.0, 400.0)
    assert interval_for_line_edges(link, 3, 140.0, 150.0) == (100.0, 380.0)


def test_full_column_fill_keeps_each_line_and_its_top():
    lines = [
        [36.0, 578.8, 443.5],
        [36.0, 578.7, 425.5],
        [36.0, 578.8, 407.5],
        [36.0, 578.8, 389.5],
        [36.0, 578.6, 371.5],
        [36.0, 222.5, 353.5],
    ]
    edges = full_column_fill(lines)
    assert edges[0] == (36.0, 578.8, 443.5)
    assert edges[1] == (36.0, 578.7, 425.5)
    assert edges[-1] == (36.0, 222.5, 353.5)
    plan = build_plan(_facts(lines))
    assert len(plan.line_edge_links) == 1
    link = plan.line_edge_links[0]
    assert plan.decisions[0].contour_plugin == "rect/full_column"
    assert plan.decisions[0].contour_status == "matched"
    assert link.alignment == "left"
    assert link.flow == "edge"
    assert link.edges == edges
    assert all(level.kind == "observed" for level in link.levels)
    assert interval_for_line_edges(link, 0, 435.0, 445.0) == (36.0, 578.8)
    assert interval_for_line_edges(link, 1, 417.0, 427.0) == (36.0, 578.7)
    assert interval_for_line_edges(link, 5, 345.0, 355.0) == (36.0, 222.5)


def test_deep_right_fill_keeps_each_line_and_its_top():
    lines = [
        [100.0, 400.0, 200.0],
        [100.0, 300.0, 184.0],
        [100.0, 360.0, 168.0],
        [100.0, 340.0, 152.0],
        [100.0, 250.0, 136.0],
    ]
    pairs = deep_right_fill(lines)
    assert pairs[0] == (100.0, 400.0, 200.0)
    plan = build_plan(_facts(lines))
    assert len(plan.line_edge_links) == 1
    link = plan.line_edge_links[0]
    assert link.edges == pairs
    assert link.flow == "edge"
    assert interval_for_line_edges(link, 0, 192.0, 200.0) == (100.0, 400.0)
    assert interval_for_line_edges(link, 0, 168.5, 183.0) == (100.0, 300.0)
    assert interval_for_line_edges(link, 1) is None


def test_bullet_hang_fill_keeps_each_line_and_its_top():
    bullet = MarkerEvidence(text="•", font="Test", is_bullet=True)
    lines = [
        [100.0, 360.0, 200.0],
        [118.0, 400.0, 184.0],
        [118.0, 400.0, 168.0],
        [118.0, 380.0, 152.0],
    ]
    edges = bullet_hang_fill(lines)
    assert edges[0] == (100.0, 360.0, 200.0)
    assert edges[1] == (118.0, 400.0, 184.0)
    plan = build_plan(_facts(lines, marker=bullet))
    assert len(plan.line_edge_links) == 1
    link = plan.line_edge_links[0]
    assert plan.decisions[0].contour_plugin == "mark/bullet_hang"
    assert plan.decisions[0].contour_status == "matched"
    assert link.alignment == "left"
    assert link.flow == "edge"
    assert link.edges == edges
    assert all(level.kind == "observed" for level in link.levels)
    assert interval_for_line_edges(link, 0, 190.0, 198.0) == (100.0, 360.0)
    assert interval_for_line_edges(link, 1, 170.0, 180.0) == (118.0, 400.0)


def test_bullet_plain_fill_keeps_each_line_and_its_top():
    bullet = MarkerEvidence(text="•", font="Test", is_bullet=True)
    lines = [
        [100.0, 360.0, 200.0],
        [100.0, 400.0, 184.0],
        [100.0, 400.0, 168.0],
        [100.0, 380.0, 152.0],
    ]
    edges = bullet_plain_fill(lines)
    assert edges[0] == (100.0, 360.0, 200.0)
    assert edges[1] == (100.0, 400.0, 184.0)
    plan = build_plan(_facts(lines, marker=bullet))
    assert len(plan.line_edge_links) == 1
    link = plan.line_edge_links[0]
    assert plan.decisions[0].contour_plugin == "mark/bullet_plain"
    assert plan.decisions[0].contour_status == "matched"
    assert link.alignment == "left"
    assert link.flow == "edge"
    assert link.edges == edges
    assert all(level.kind == "observed" for level in link.levels)
    assert interval_for_line_edges(link, 0, 190.0, 198.0) == (100.0, 360.0)
    assert interval_for_line_edges(link, 1, 170.0, 180.0) == (100.0, 400.0)


def test_bullet_repeated_fill_keeps_each_line_and_its_top():
    bullet = MarkerEvidence(text="•", font="Test", is_bullet=True)
    lines = [
        [100.0, 360.0, 200.0],
        [118.0, 400.0, 184.0],
        [118.0, 400.0, 168.0],
        [100.0, 380.0, 152.0],
        [118.0, 390.0, 136.0],
        [118.0, 370.0, 120.0],
    ]
    edges = bullet_repeated_fill(lines)
    assert edges[0] == (100.0, 360.0, 200.0)
    assert edges[1] == (118.0, 400.0, 184.0)
    assert edges[3] == (100.0, 380.0, 152.0)
    plan = build_plan(_facts(lines, marker=bullet))
    assert len(plan.line_edge_links) == 1
    link = plan.line_edge_links[0]
    assert plan.decisions[0].contour_plugin == "mark/bullet_repeated"
    assert plan.decisions[0].contour_status == "matched"
    assert link.alignment == "left"
    assert link.flow == "edge"
    assert link.edges == edges
    assert all(level.kind == "observed" for level in link.levels)
    assert interval_for_line_edges(link, 0, 190.0, 198.0) == (100.0, 360.0)
    assert interval_for_line_edges(link, 1, 170.0, 180.0) == (118.0, 400.0)
    assert interval_for_line_edges(link, 3, 140.0, 150.0) == (100.0, 380.0)


def test_serial_hang_fill_keeps_each_line_and_its_top():
    lines = [
        [100.0, 360.0, 200.0],
        [118.0, 400.0, 184.0],
        [118.0, 400.0, 168.0],
        [118.0, 380.0, 152.0],
    ]
    edges = serial_hang_fill(lines)
    assert edges[0] == (100.0, 360.0, 200.0)
    assert edges[1] == (118.0, 400.0, 184.0)
    plan = build_plan(_facts(lines, source_text="1. Item"))
    assert len(plan.line_edge_links) == 1
    link = plan.line_edge_links[0]
    assert plan.decisions[0].contour_plugin == "mark/serial_hang"
    assert plan.decisions[0].contour_status == "matched"
    assert link.alignment == "left"
    assert link.flow == "edge"
    assert link.edges == edges
    assert all(level.kind == "observed" for level in link.levels)
    assert interval_for_line_edges(link, 0, 190.0, 198.0) == (100.0, 360.0)
    assert interval_for_line_edges(link, 1, 170.0, 180.0) == (118.0, 400.0)


def test_serial_plain_fill_keeps_each_line_and_its_top():
    lines = [
        [100.0, 360.0, 200.0],
        [100.0, 400.0, 184.0],
        [100.0, 400.0, 168.0],
        [100.0, 380.0, 152.0],
    ]
    edges = serial_plain_fill(lines)
    assert edges[0] == (100.0, 360.0, 200.0)
    assert edges[1] == (100.0, 400.0, 184.0)
    plan = build_plan(_facts(lines, source_text="1. Item"))
    assert len(plan.line_edge_links) == 1
    link = plan.line_edge_links[0]
    assert plan.decisions[0].contour_plugin == "mark/serial_plain"
    assert plan.decisions[0].contour_status == "matched"
    assert link.alignment == "left"
    assert link.flow == "edge"
    assert link.edges == edges
    assert all(level.kind == "observed" for level in link.levels)
    assert interval_for_line_edges(link, 0, 190.0, 198.0) == (100.0, 360.0)
    assert interval_for_line_edges(link, 1, 170.0, 180.0) == (100.0, 400.0)


def test_serial_repeated_fill_keeps_each_line_and_its_top():
    lines = [
        [100.0, 360.0, 200.0],
        [118.0, 400.0, 184.0],
        [118.0, 400.0, 168.0],
        [100.0, 380.0, 152.0],
        [118.0, 390.0, 136.0],
        [118.0, 370.0, 120.0],
    ]
    edges = serial_repeated_fill(lines)
    assert edges[0] == (100.0, 360.0, 200.0)
    assert edges[1] == (118.0, 400.0, 184.0)
    assert edges[3] == (100.0, 380.0, 152.0)
    plan = build_plan(_facts(lines, source_text="1. Item"))
    assert len(plan.line_edge_links) == 1
    link = plan.line_edge_links[0]
    assert plan.decisions[0].contour_plugin == "mark/serial_repeated"
    assert plan.decisions[0].contour_status == "matched"
    assert link.alignment == "left"
    assert link.flow == "edge"
    assert link.edges == edges
    assert all(level.kind == "observed" for level in link.levels)
    assert interval_for_line_edges(link, 0, 190.0, 198.0) == (100.0, 360.0)
    assert interval_for_line_edges(link, 1, 170.0, 180.0) == (118.0, 400.0)
    assert interval_for_line_edges(link, 3, 140.0, 150.0) == (100.0, 380.0)



def test_lower_wide_fill_keeps_the_step_and_opens_the_tail():
    source = inspect.getsource(lower_wide_fill)
    assert "scanned_edge_gap" not in source
    lines = [
        [102.0, 335.7, 160.0],
        [102.0, 335.6, 145.0],
        [102.0, 335.6, 130.0],
        [102.0, 512.7, 115.0],
        [102.0, 512.7, 100.0],
        [102.0, 512.7, 85.0],
        [102.0, 512.7, 70.0],
        [102.0, 292.5, 55.0],
    ]
    pairs = lower_wide_fill(lines)
    assert pairs[0] == (102.0, 335.7, 160.0)
    assert pairs[3] == (102.0, 512.7, 115.0)
    assert pairs[-1] == (102.0, 512.7, 55.0)
    plan = build_plan(_facts(lines))
    link = plan.line_edge_links[0]
    assert link.flow == "edge"
    assert interval_for_line_edges(link, 0, 150.0, 160.0)[1] == 335.7
    assert interval_for_line_edges(link, 0, 70.0, 85.0)[1] == 512.7


def test_upper_wide_fill_keeps_the_step_and_the_narrow_tail():
    source = inspect.getsource(upper_wide_fill)
    assert "scanned_edge_gap" not in source
    lines = [
        [78.0, 537.0, 500.0],
        [78.0, 534.0, 485.0],
        [78.0, 537.0, 470.0],
        [78.0, 534.0, 455.0],
        [78.0, 375.0, 440.0],
        [78.0, 375.0, 425.0],
        [78.0, 375.1, 410.0],
        [78.0, 375.0, 395.0],
        [78.0, 337.0, 380.0],
    ]
    pairs = upper_wide_fill(lines)
    assert pairs[0] == (78.0, 537.0, 500.0)
    assert pairs[4] == (78.0, 375.0, 440.0)
    assert pairs[-1] == (78.0, 375.0, 380.0)
    plan = build_plan(_facts(lines))
    assert len(plan.line_edge_links) == 1
    link = plan.line_edge_links[0]
    assert link.edges == pairs
    assert link.flow == "edge"
    assert interval_for_line_edges(link, 0, 458.0, 468.0)[1] == 537.0
    assert interval_for_line_edges(link, 0, 428.0, 438.0)[1] == 375.0
    assert interval_for_line_edges(link, 0, 372.0, 382.0)[1] == 375.0


def test_spur_fill_keeps_the_wide_line_and_the_narrow_tail():
    source = inspect.getsource(spur_fill)
    assert "scanned_edge_gap" not in source
    lines = [
        [102.0, 371.6, 500.0],
        [102.0, 371.6, 485.0],
        [102.0, 371.6, 470.0],
        [102.0, 371.7, 455.0],
        [102.0, 512.7, 440.0],
        [102.0, 200.0, 425.0],
    ]
    pairs = spur_fill(lines)
    assert pairs[0] == (102.0, 371.6, 500.0)
    assert pairs[4] == (102.0, 512.7, 440.0)
    assert pairs[-1] == (102.0, 371.7, 425.0)
    plan = build_plan(_facts(lines))
    assert len(plan.line_edge_links) == 1
    link = plan.line_edge_links[0]
    assert link.edges == pairs
    assert link.flow == "edge"
    assert interval_for_line_edges(link, 0, 462.0, 472.0)[1] == 371.6
    assert interval_for_line_edges(link, 0, 428.0, 438.0)[1] == 512.7


def test_left_pin_fill_is_each_lines_own_edge():
    source = inspect.getsource(left_pin_fill)
    assert "scanned_edge_gap" not in source
    lines = [
        [100.0, 400.0 - (18.0 * index / 5.0), 200.0 - index * 16.0]
        for index in range(6)
    ]
    pairs = left_pin_fill(lines)
    assert pairs == tuple((line[0], line[1]) for line in lines)
    plan = build_plan(_facts(lines))
    assert len(plan.line_edge_links) == 1
    link = plan.line_edge_links[0]
    assert link.edges == pairs
    assert link.flow == "edge"
    # line_idx 1 repeated pairs[1] even when the Chinese line sat elsewhere.
    assert all(level.kind == "observed" for level in link.levels)
    assert interval_for_line_edges(link, 0, 172.0, 180.0) == pairs[1]
    assert interval_for_line_edges(link, 99, 172.0, 180.0) == pairs[1]


def test_right_pin_fill_is_each_lines_own_edge():
    source = inspect.getsource(right_pin_fill)
    assert "scanned_edge_gap" not in source
    lines = [
        [300.0 - index * 4.0, 578.0, 400.0 - index * 16.0] for index in range(6)
    ]
    pairs = right_pin_fill(lines)
    assert pairs == tuple((line[0], line[1]) for line in lines)
    plan = build_plan(_facts(lines))
    assert len(plan.line_edge_links) == 1
    assert plan.line_edge_links[0].edges == pairs


def test_light_column_fill_uses_the_outer_edge_inside_the_wall():
    source = inspect.getsource(light_column_fill)
    assert "scanned_edge_gap" not in source
    lines = [
        [100.0, 400.0, 200.0],
        [116.0, 384.0, 184.0],
        [108.0, 392.0, 168.0],
    ]
    assert light_column_fill(lines) == ((100.0, 400.0), (100.0, 400.0), (100.0, 400.0))


def test_light_column_fill_keeps_a_one_way_left_walk():
    lines = [
        [221.0, 512.0, 400.0],
        [221.0, 512.0, 384.0],
        [220.0, 512.0, 368.0],
        [217.0, 512.0, 352.0],
        [215.0, 472.0, 336.0],
    ]
    pairs = light_column_fill(lines)
    assert [pair[0] for pair in pairs] == [221.0, 221.0, 220.0, 217.0, 215.0]
    assert pairs[-1] == (215.0, 512.0)
    assert pairs[0][1] == 512.0


def test_light_column_fill_keeps_a_two_line_left_step():
    lines = [[162.0, 512.0, 100.0], [153.0, 512.0, 84.0]]
    assert light_column_fill(lines) == ((162.0, 512.0), (153.0, 512.0))


def test_light_column_fill_keeps_a_middle_line_past_the_wall():
    lines = [
        [100.0, 400.0, 200.0],
        [116.01, 400.0, 184.0],
        [100.0, 383.99, 168.0],
        [100.0, 400.0, 152.0],
    ]
    assert light_column_fill(lines) == (
        (100.0, 400.0),
        (116.01, 400.0),
        (100.0, 383.99),
        (100.0, 400.0),
    )


def test_light_column_fill_puts_the_last_line_on_the_outer_edge():
    lines = [
        [100.0, 400.0, 200.0],
        [100.0, 400.0, 184.0],
        [140.0, 300.0, 168.0],
    ]
    assert light_column_fill(lines) == (
        (100.0, 400.0),
        (100.0, 400.0),
        (100.0, 400.0),
    )


def test_light_column_fill_keeps_one_dip_that_comes_back():
    rights = [
        322.7,
        315.8,
        308.7,
        308.8,
        311.8,
        311.7,
        309.8,
        308.6,
        314.8,
        321.7,
        318.7,
        315.6,
        314.7,
        319.7,
        176.1,
    ]
    lines = [
        [36.0, right, 500.0 - index * 18.0] for index, right in enumerate(rights)
    ]
    pairs = light_column_fill(lines)
    assert pairs[-1] == (36.0, 322.7)
    assert pairs[:-1] == tuple((36.0, right) for right in rights[:-1])


def test_light_column_fill_still_flattens_two_dips():
    rights = [322.0, 308.0, 321.0, 309.0, 320.0, 322.0]
    lines = [
        [36.0, right, 200.0 - index * 18.0] for index, right in enumerate(rights)
    ]
    assert light_column_fill(lines) == tuple((36.0, 322.0) for _ in rights)


def test_light_column_fill_still_flattens_a_one_line_notch():
    rights = [400.0, 400.0, 388.0, 400.0, 400.0]
    lines = [
        [100.0, right, 200.0 - index * 18.0] for index, right in enumerate(rights)
    ]
    assert light_column_fill(lines) == tuple((100.0, 400.0) for _ in rights)


def test_a_real_light_column_writes_its_line_edges():
    lines = [[100.0, 400.0, 200.0 - index * 16.0] for index in range(8)]
    lines[3] = [101.0, 340.0, lines[3][2]]
    plan = build_plan(_facts(lines))
    assert len(plan.line_edge_links) == 1
    link = plan.line_edge_links[0]
    assert link.edges == light_column_fill(lines)
    # The deep dip keeps its own ink. Its sample is that line's top.
    assert link.levels[3].kind == "observed"
    assert link.levels[3].top == lines[3][2]


def test_a_light_column_wall_is_available_space_not_that_lines_ink():
    lines = [[100.0, 400.0, 200.0 - index * 16.0] for index in range(6)]
    lines[2] = [108.0, 392.0, lines[2][2]]
    plan = build_plan(_facts(lines))
    assert len(plan.line_edge_links) == 1
    link = plan.line_edge_links[0]
    assert link.levels[0].kind == "observed"
    assert link.levels[2].kind == "available"
    assert (link.levels[2].left, link.levels[2].right) == (100.0, 400.0)
    assert link.levels[2].top == lines[2][2]


def test_a_real_opening_writes_its_line_edges():
    lines = _opening_lines()
    plan = build_plan(_facts(lines))
    assert len(plan.line_edge_links) == 1
    link = plan.line_edge_links[0]
    assert link.edges == tuple((line[0], line[1]) for line in lines)
    assert plan.to_dict()["line_edge_links"][0]["edges"][0] == [140.0, 360.0]
    for copied in (
        with_column_links(_facts(lines), plan),
        with_list_links(_facts(lines), plan),
        with_pocket_links(_facts(lines), plan),
    ):
        assert copied.line_edge_links == plan.line_edge_links


def test_a_straight_column_and_a_short_block_get_no_line_edges():
    straight = [[100.0, 400.0, 200.0 - index * 16.0] for index in range(4)]
    short = [[100.0, 180.0, 200.0], [140.0, 220.0, 184.0]]
    # A straight column is a full column with straight edges.
    assert len(build_plan(_facts(straight)).line_edge_links) == 1
    assert build_plan(_facts(short)).line_edge_links == ()
    assert build_plan(_facts(_opening_lines(), gate="spread")).line_edge_links == ()


def test_a_height_query_does_not_reuse_an_unmeasured_edge():
    """Two samples that share no x are unplaceable across both.

    A line that sits on one sample keeps that sample. A line past the
    last sample does not repeat it. Tuple length is not the switch:
    these edges are pairs, and the height is on the levels.
    """
    levels = (
        ContourLevel(100.0, 180.0, 200.0, "observed"),
        ContourLevel(300.0, 400.0, 120.0, "available"),
    )
    link = LineEdgeLink(
        "cross",
        ((100.0, 180.0), (300.0, 400.0)),
        "left",
        "edge",
        levels,
    )
    assert interval_for_line_edges(link, 0, 190.0, 199.0) == (100.0, 180.0)
    assert interval_for_line_edges(link, 4, 190.0, 199.0) == (100.0, 180.0)
    assert interval_for_line_edges(link, 0, 50.0, 100.0) == (300.0, 400.0)
    assert interval_for_line_edges(link, 0, 50.0, 200.0) is None
    assert interval_for_line_edges(link, 99, 0.0, 10.0) is None


def test_an_unplaceable_contour_does_not_become_the_full_box():
    from babeldoc.format.pdf.document_il.midend.typesetting import Typesetting

    link = LineEdgeLink(
        "body",
        ((100.0, 200.0),),
        "left",
        "edge",
        (ContourLevel(100.0, 200.0, 400.0, "observed"),),
    )
    setter = Typesetting.__new__(Typesetting)
    setter._line_edges = link
    setter._pocket_link = None
    setter.translation_config = type("Config", (), {"ocr_workaround": False})()
    box = type("Box", (), {"x": 36.0, "x2": 560.0, "y": 40.0, "y2": 700.0})()
    missed = setter._resolve_line_intervals(
        10.0,
        20.0,
        box,
        paragraph=None,
        line_idx=3,
        reference_widths=[400.0],
    )
    assert missed == [(36.0, 36.0)]
    capacity, intervals = setter._line_capacity_like_place(
        box=box,
        y_bottom=10.0,
        y_top=20.0,
        line_idx=3,
        reference_widths=[400.0],
        alignment="left",
        paragraph=None,
        typesetting_units=[],
        scale=1.0,
    )
    assert capacity == 0.0
    assert intervals == [(36.0, 36.0)]
    placed = setter._resolve_line_intervals(
        390.0,
        400.0,
        box,
        paragraph=None,
        line_idx=7,
        reference_widths=None,
    )
    assert placed == [(100.0, 200.0)]

    from unittest.mock import MagicMock

    from babeldoc.format.pdf.document_il.il_version_1 import Box
    from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter
    from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
    from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
    from babeldoc.format.pdf.document_il.il_version_1 import VisualBbox
    from babeldoc.format.pdf.document_il.midend.typesetting import TypesettingUnit
    from babeldoc.format.pdf.translation_config import TranslationConfig
    from babeldoc.translator.fixed_map_translator import FixedMapTranslator

    def _glyph(width: float) -> TypesettingUnit:
        glyph = Box(x=0, y=0, x2=width, y2=12)
        char = PdfCharacter(
            char_unicode="中",
            box=glyph,
            visual_bbox=VisualBbox(box=Box(x=0, y=0, x2=width, y2=12)),
            pdf_style=PdfStyle(font_id="base", font_size=12, graphic_state=None),
        )
        return TypesettingUnit(char=char)

    def _para(host: Box, debug_id: str) -> PdfParagraph:
        return PdfParagraph(
            box=host,
            pdf_style=PdfStyle(font_id="base", font_size=12, graphic_state=None),
            pdf_paragraph_composition=[],
            unicode="测试",
            debug_id=debug_id,
        )

    ts = Typesetting(
        TranslationConfig(
            translator=FixedMapTranslator(),
            input_file="contour-unplaceable.pdf",
            lang_in="en",
            lang_out="zh-CN",
            doc_layout_model=MagicMock(),
            auto_extract_glossary=False,
        )
    )
    ts._line_edges = link
    ts._pocket_link = None

    on_contour = Box(x=36, y=380, x2=560, y2=412)
    fitted, fitted_ok = ts._layout_typesetting_units(
        [_glyph(10) for _ in range(4)],
        on_contour,
        1.0,
        1.05,
        _para(on_contour, "on-contour"),
        use_english_line_break=False,
    )
    assert fitted_ok is True
    assert len(fitted) == 4
    assert ts._unplaceable_lines == []
    assert [unit.box.x for unit in fitted] == [100.0, 110.0, 120.0, 130.0]

    wide, _wide_ok = ts._layout_typesetting_units(
        [_glyph(150)],
        on_contour,
        1.0,
        1.05,
        _para(on_contour, "wide"),
        use_english_line_break=False,
    )
    # A positive interval still paints, including a glyph wider than it.
    # That path must not be reported as an unplaceable contour.
    assert len(wide) == 1
    assert wide[0].box.x == 100.0
    assert ts._unplaceable_lines == []

    below = Box(x=36, y=0, x2=560, y2=30)
    empty, empty_ok = ts._layout_typesetting_units(
        [_glyph(10) for _ in range(8)],
        below,
        1.0,
        1.05,
        _para(below, "below"),
        use_english_line_break=False,
    )
    assert empty == []
    assert empty_ok is False
    assert ts._unplaceable_lines == [
        {
            "reason": "unplaceable_contour",
            "y": 18.0,
            "anchor": 36.0,
            "debug_id": "below",
        }
    ]

    walked, walked_ok = ts._layout_typesetting_units(
        [_glyph(10) for _ in range(40)],
        Box(x=36, y=0, x2=560, y2=412),
        1.0,
        1.05,
        _para(Box(x=36, y=0, x2=560, y2=412), "walk"),
        use_english_line_break=False,
    )
    assert walked
    assert walked_ok is False
    assert len(walked) < 40
    assert min(unit.box.x for unit in walked) >= 100.0
    assert max(unit.box.x2 for unit in walked) <= 200.0 + 0.1
    assert len(ts._unplaceable_lines) == 1
    assert ts._unplaceable_lines[0]["reason"] == "unplaceable_contour"
    assert ts._unplaceable_lines[0]["anchor"] == 36.0
    assert ts._unplaceable_lines[0]["debug_id"] == "walk"
    assert min(unit.box.y for unit in walked) > ts._unplaceable_lines[0]["y"]


def test_a_pen_above_the_contour_opens_on_the_first_line():
    from unittest.mock import MagicMock

    from babeldoc.format.pdf.document_il.il_version_1 import Box
    from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter
    from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
    from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
    from babeldoc.format.pdf.document_il.il_version_1 import VisualBbox
    from babeldoc.format.pdf.document_il.midend.typesetting import Typesetting
    from babeldoc.format.pdf.document_il.midend.typesetting import TypesettingUnit
    from babeldoc.format.pdf.translation_config import TranslationConfig
    from babeldoc.translator.fixed_map_translator import FixedMapTranslator

    link = LineEdgeLink(
        "bow",
        ((36.0, 366.0), (36.0, 330.0), (36.0, 360.0)),
        "left",
        "edge",
        (
            ContourLevel(36.0, 366.0, 268.0, "observed"),
            ContourLevel(36.0, 330.0, 250.0, "observed"),
            ContourLevel(36.0, 360.0, 232.0, "observed"),
        ),
    )
    host = Box(x=36, y=80, x2=366, y2=336)
    paragraph = PdfParagraph(
        box=host,
        pdf_style=PdfStyle(font_id="base", font_size=12, graphic_state=None),
        pdf_paragraph_composition=[],
        unicode="测试",
        debug_id="above",
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
            input_file="contour-above.pdf",
            lang_in="en",
            lang_out="zh-CN",
            doc_layout_model=MagicMock(),
            auto_extract_glossary=False,
        )
    )
    ts._line_edges = link
    ts._pocket_link = None
    fitted, fitted_ok = ts._layout_typesetting_units(
        [_glyph() for _ in range(4)],
        host,
        1.0,
        1.05,
        paragraph,
        use_english_line_break=False,
    )
    assert fitted_ok is True
    assert len(fitted) == 4
    assert ts._unplaceable_lines == []
    assert [unit.box.x for unit in fitted] == [36.0, 46.0, 56.0, 66.0]
    assert [unit.box.y for unit in fitted] == [256.0, 256.0, 256.0, 256.0]
    assert host.y2 == 268.0
    assert host.y == 80.0


def _contour_typesetter():
    from unittest.mock import MagicMock

    from babeldoc.format.pdf.document_il.midend.typesetting import Typesetting
    from babeldoc.format.pdf.translation_config import TranslationConfig
    from babeldoc.translator.fixed_map_translator import FixedMapTranslator

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


def _cjk_glyph(width: float = 10.0):
    from babeldoc.format.pdf.document_il.il_version_1 import Box
    from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter
    from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
    from babeldoc.format.pdf.document_il.il_version_1 import VisualBbox
    from babeldoc.format.pdf.document_il.midend.typesetting import TypesettingUnit

    glyph = Box(x=0, y=0, x2=width, y2=12)
    char = PdfCharacter(
        char_unicode="中",
        box=glyph,
        visual_bbox=VisualBbox(box=Box(x=0, y=0, x2=width, y2=12)),
        pdf_style=PdfStyle(font_id="base", font_size=12, graphic_state=None),
    )
    return TypesettingUnit(char=char)


def test_a_missed_contour_does_not_lock_the_readable_floor():
    from babeldoc.format.pdf.document_il.il_version_1 import Box
    from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
    from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle

    link = LineEdgeLink(
        "bow",
        ((36.0, 366.0), (36.0, 330.0)),
        "left",
        "edge",
        (
            ContourLevel(36.0, 366.0, 268.0, "observed"),
            ContourLevel(36.0, 330.0, 250.0, "observed"),
        ),
    )
    host = Box(x=36, y=10, x2=366, y2=40)
    paragraph = PdfParagraph(
        box=host,
        pdf_style=PdfStyle(font_id="base", font_size=12, graphic_state=None),
        pdf_paragraph_composition=[],
        unicode="测试",
        debug_id="miss",
    )
    ts = _contour_typesetter()
    ts._line_edges = link
    scale, _units = ts._find_optimal_scale_and_layout_inner(
        paragraph,
        None,
        [_cjk_glyph(), _cjk_glyph()],
        1.0,
        use_english_line_break=False,
        apply_layout=False,
    )
    assert scale == 1.0
    assert host.y2 == 40.0
    assert ts._unplaceable_lines


def test_a_contour_tail_that_does_not_fit_keeps_the_readable_floor():
    from babeldoc.format.pdf.document_il.il_version_1 import Box
    from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
    from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
    from babeldoc.format.pdf.document_il.midend.typesetting import Typesetting

    link = LineEdgeLink(
        "bow",
        ((36.0, 76.0),),
        "left",
        "edge",
        (ContourLevel(36.0, 76.0, 280.0, "observed"),),
    )
    host = Box(x=36, y=200, x2=76, y2=280)
    paragraph = PdfParagraph(
        box=host,
        pdf_style=PdfStyle(font_id="base", font_size=12, graphic_state=None),
        pdf_paragraph_composition=[],
        unicode="测试",
        debug_id="tail",
    )
    ts = _contour_typesetter()
    ts._line_edges = link
    scale, _units = ts._find_optimal_scale_and_layout_inner(
        paragraph,
        None,
        [_cjk_glyph() for _ in range(12)],
        1.0,
        use_english_line_break=False,
        apply_layout=False,
    )
    assert scale == Typesetting.MIN_READABLE_SCALE


def test_a_short_box_still_uses_the_lower_samples_at_body_size():
    """The paragraph box may cover only the first lines of a bulge.

    Body size stays. Later glyphs use the wider samples below that box.
    """
    from babeldoc.format.pdf.document_il.il_version_1 import Box
    from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
    from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle

    tops = (200.0, 185.0, 170.0, 155.0)
    rights = (160.0, 170.0, 240.0, 260.0)
    link = LineEdgeLink(
        "bow",
        tuple((100.0, right) for right in rights),
        "left",
        "edge",
        tuple(
            ContourLevel(100.0, right, top, "observed")
            for right, top in zip(rights, tops, strict=False)
        ),
    )
    host = Box(x=100, y=175, x2=170, y2=200)
    paragraph = PdfParagraph(
        box=host,
        pdf_style=PdfStyle(font_id="base", font_size=12, graphic_state=None),
        pdf_paragraph_composition=[],
        unicode="测试",
        debug_id="bulge",
    )
    ts = _contour_typesetter()
    ts._line_edges = link
    units = [_cjk_glyph() for _ in range(16)]
    scale, _ = ts._find_optimal_scale_and_layout_inner(
        paragraph,
        None,
        units,
        1.0,
        use_english_line_break=False,
        apply_layout=False,
    )
    assert scale == 1.0
    fresh = Box(x=100, y=175, x2=170, y2=200)
    laid, ok = ts._layout_typesetting_units(
        [_cjk_glyph() for _ in range(16)],
        fresh,
        1.0,
        1.5,
        paragraph,
        False,
    )
    assert ok is True
    assert len(laid) == 16
    lows = [unit for unit in laid if unit.box.y < fresh.y]
    assert lows
    assert max(unit.box.x2 for unit in lows) > 150.0


def test_a_left_contour_wraps_the_last_glyphs_inside_the_scan():
    from babeldoc.format.pdf.document_il.il_version_1 import Box
    from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
    from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle

    link = LineEdgeLink(
        "bow",
        ((36.0, 60.0), (36.0, 80.0)),
        "left",
        "edge",
        (
            ContourLevel(36.0, 60.0, 268.0, "observed"),
            ContourLevel(36.0, 80.0, 250.0, "observed"),
        ),
    )
    host = Box(x=36, y=80, x2=80, y2=268)
    paragraph = PdfParagraph(
        box=host,
        pdf_style=PdfStyle(font_id="base", font_size=12, graphic_state=None),
        pdf_paragraph_composition=[],
        unicode="测试",
        debug_id="orphan",
    )
    ts = _contour_typesetter()
    ts._line_edges = link
    fitted, _fitted_ok = ts._layout_typesetting_units(
        [_cjk_glyph(), _cjk_glyph(), _cjk_glyph()],
        host,
        1.0,
        1.5,
        paragraph,
        use_english_line_break=False,
    )
    assert fitted
    assert all(unit.box.x2 <= 60.0 + 0.1 for unit in fitted)
    assert fitted[-1].box.y < fitted[0].box.y


def test_an_opening_pen_does_not_invert_a_box_above_the_contour():
    from babeldoc.format.pdf.document_il.il_version_1 import Box
    from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
    from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle

    link = LineEdgeLink(
        "bow",
        ((36.0, 366.0),),
        "left",
        "edge",
        (ContourLevel(36.0, 366.0, 268.0, "observed"),),
    )
    host = Box(x=36, y=300, x2=366, y2=400)
    paragraph = PdfParagraph(
        box=host,
        pdf_style=PdfStyle(font_id="base", font_size=12, graphic_state=None),
        pdf_paragraph_composition=[],
        unicode="测试",
        debug_id="invert",
    )
    ts = _contour_typesetter()
    ts._line_edges = link
    ts._layout_typesetting_units(
        [_cjk_glyph()],
        host,
        1.0,
        1.05,
        paragraph,
        use_english_line_break=False,
    )
    assert host.y == 300.0
    assert host.y2 == 400.0


def test_the_scale_search_seats_a_contour_before_it_measures():
    from babeldoc.format.pdf.document_il.il_version_1 import Box
    from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter
    from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
    from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraphComposition
    from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
    from babeldoc.format.pdf.document_il.il_version_1 import VisualBbox

    link = LineEdgeLink(
        "bow",
        ((36.0, 366.0), (36.0, 330.0)),
        "left",
        "edge",
        (
            ContourLevel(36.0, 366.0, 268.0, "observed"),
            ContourLevel(36.0, 330.0, 250.0, "observed"),
        ),
    )
    glyph = Box(x=0, y=0, x2=10, y2=12)
    char = PdfCharacter(
        char_unicode="中",
        box=glyph,
        visual_bbox=VisualBbox(box=Box(x=0, y=0, x2=10, y2=12)),
        pdf_style=PdfStyle(font_id="base", font_size=12, graphic_state=None),
    )
    host = Box(x=36, y=10, x2=366, y2=40)
    paragraph = PdfParagraph(
        box=host,
        pdf_style=PdfStyle(font_id="base", font_size=12, graphic_state=None),
        pdf_paragraph_composition=[PdfParagraphComposition(pdf_character=char)],
        unicode="中",
        debug_id="seat",
        layout_region_id="bow",
    )
    page = type("Page", (), {})()
    page.pdf_font = []
    page.pdf_xobject = []
    page.pdf_paragraph = [paragraph]
    page.cropbox = type("Crop", (), {"box": Box(x=0, y=0, x2=612, y2=792)})()
    page.layout_plan = type(
        "Plan",
        (),
        {"line_edge_links": (link,), "decisions": ()},
    )()
    document = type("Doc", (), {"page": [page]})()
    ts = _contour_typesetter()
    ts.preprocess_document(document, None, build_zone_index=False)
    assert host.y2 == 268.0
    assert host.y < 268.0
    assert paragraph.optimal_scale == 1.0


def test_line_edges_are_held_and_the_box_is_their_union():
    plan = build_plan(_facts(_opening_lines()))
    link = plan.line_edge_links[0]
    # line_idx 0 used to be the first English edge, and line_idx 99
    # repeated the last one past the contour. A Chinese line outside
    # the scan is unplaceable. The same in-range height ignores the index.
    assert interval_for_line_edges(link, 0) is None
    assert interval_for_line_edges(link, 0, 190.0, 199.0) == (140.0, 360.0)
    assert interval_for_line_edges(link, 99, 190.0, 199.0) == (140.0, 360.0)
    assert interval_for_line_edges(link, 99, 0.0, 10.0) is None

    class _Box:
        def __init__(self):
            self.x = 0.0
            self.x2 = 1.0

    class _Paragraph:
        def __init__(self):
            self.layout_region_id = link.region_id
            self.box = _Box()
            self.alignment = "right"
            self.first_line_indent = 12.0

    page = type("_Page", (), {})()
    page.layout_plan = plan
    page.pdf_paragraph = [_Paragraph()]
    assign_line_edge_boxes(page)
    box = page.pdf_paragraph[0].box
    assert box.x == min(edge[0] for edge in link.edges)
    assert box.x2 == max(edge[1] for edge in link.edges)
    assert page.pdf_paragraph[0].alignment == "left"
    assert page.pdf_paragraph[0].first_line_indent == 0
    assert link.region_id in _planned_ids(page)


def test_sentence_flow_raises_the_box_to_the_first_line_and_keeps_the_bottom():
    edges = (
        (96.0, 368.0, 662.4),
        (96.0, 220.0, 542.4),
    )
    link = LineEdgeLink("verse", edges, "left", "sentence")

    class _Box:
        def __init__(self, y2):
            self.x = 0.0
            self.x2 = 1.0
            self.y = 528.1
            self.y2 = y2

    class _Paragraph:
        def __init__(self, y2):
            self.layout_region_id = link.region_id
            self.box = _Box(y2)
            self.alignment = "left"
            self.first_line_indent = 0.0

    short = _Paragraph(630.0)
    tall = _Paragraph(700.0)
    page = type("_Page", (), {})()
    page.layout_plan = type("_Plan", (), {"line_edge_links": (link,)})()
    page.pdf_paragraph = [short, tall]
    assign_line_edge_boxes(page)
    assert short.box.y2 == 662.4
    assert short.box.y == 528.1
    assert tall.box.y2 == 700.0
    assert tall.box.y == 528.1

    edge_link = LineEdgeLink("tip", edges, "left", "edge")
    tip = _Paragraph(630.0)
    tip.layout_region_id = edge_link.region_id
    page.layout_plan = type("_Plan", (), {"line_edge_links": (edge_link,)})()
    page.pdf_paragraph = [tip]
    assign_line_edge_boxes(page)
    assert tip.box.y2 == 630.0
    assert tip.box.y == 528.1


def test_an_edge_box_above_the_contour_starts_on_the_first_line():
    edges = (
        (36.0, 366.0, 268.0),
        (36.0, 330.0, 250.0),
        (36.0, 360.0, 232.0),
    )
    link = LineEdgeLink("bow", edges, "left", "edge")

    class _Box:
        def __init__(self, y, y2):
            self.x = 0.0
            self.x2 = 1.0
            self.y = y
            self.y2 = y2

    class _Paragraph:
        def __init__(self, y, y2):
            self.layout_region_id = link.region_id
            self.box = _Box(y, y2)
            self.alignment = "left"
            self.first_line_indent = 0.0

    above = _Paragraph(80.0, 336.0)
    page = type("_Page", (), {})()
    page.layout_plan = type("_Plan", (), {"line_edge_links": (link,)})()
    page.pdf_paragraph = [above]
    assign_line_edge_boxes(page)
    assert above.box.y2 == 268.0
    assert above.box.y == 80.0


def test_a_box_pushed_under_a_quote_returns_to_the_contour():
    """A rectangle moved entirely under the contour is seated on the scan.

    A box that still meets the scanned tops stays, even when its top is
    below the first line. Edges without a height do not invent one.
    """
    rights = (537.0, 534.0, 537.0, 534.0, 375.0, 375.0, 375.0, 375.0, 375.0, 337.0)
    edges = tuple(
        (78.0, right, 467.0 - index * 15.0) for index, right in enumerate(rights)
    )
    link = LineEdgeLink("metal", edges, "left", "edge")

    class _Box:
        def __init__(self, y, y2):
            self.x = 0.0
            self.x2 = 1.0
            self.y = y
            self.y2 = y2

    class _Paragraph:
        def __init__(self, y, y2):
            self.layout_region_id = link.region_id
            self.box = _Box(y, y2)
            self.alignment = "right"
            self.first_line_indent = 8.0

    pushed = _Paragraph(149.5, 299.1)
    meeting = _Paragraph(340.0, 420.0)
    page = type("_Page", (), {})()
    page.layout_plan = type("_Plan", (), {"line_edge_links": (link,)})()
    page.pdf_paragraph = [pushed, meeting]
    assign_line_edge_boxes(page)
    assert pushed.box.y2 == 467.0
    assert pushed.box.y == 317.0
    assert pushed.box.x == 78.0
    assert pushed.box.x2 == 537.0
    assert meeting.box.y2 == 420.0
    assert meeting.box.y == 340.0

    flat = LineEdgeLink("flat", ((78.0, 537.0), (78.0, 375.0)), "left", "edge")
    bare = _Paragraph(100.0, 200.0)
    bare.layout_region_id = flat.region_id
    page.layout_plan = type("_Plan", (), {"line_edge_links": (flat,)})()
    page.pdf_paragraph = [bare]
    assign_line_edge_boxes(page)
    assert bare.box.y2 == 200.0
    assert bare.box.y == 100.0


def test_a_side_quote_does_not_stop_the_lower_lines():
    """A quote that misses the lower edges does not cap downward growth."""
    from babeldoc.format.pdf.document_il.midend.typesetting import Typesetting
    from babeldoc.format.pdf.document_il.utils.layout_plan.line_edges import (
        lower_edge_span,
    )

    edges = (
        (199.0, 512.6),
        (203.0, 512.6),
        (207.0, 512.6),
        (211.0, 512.6),
        (214.0, 512.6),
        (216.0, 512.6),
        (218.0, 512.6),
        (220.0, 427.9),
    )
    assert lower_edge_span(edges)[0] == 214.0
    assert lower_edge_span(()) is None

    class _Box:
        def __init__(self, x, y, x2, y2):
            self.x = x
            self.y = y
            self.x2 = x2
            self.y2 = y2

    current = _Box(199.0, 398.2, 512.6, 503.2)
    page = type("_Page", (), {})()
    page.cropbox = type("_Crop", (), {"box": _Box(0.0, 0.0, 612.0, 792.0)})()
    page.pdf_paragraph = [
        type("_Para", (), {"box": current})(),
        type("_Para", (), {"box": _Box(215.0, 253.2, 512.6, 373.2)})(),
    ]
    page.pdf_character = [
        type("_Char", (), {"box": _Box(60.0, 360.0, 207.0, 391.0)})(),
    ]
    page.pdf_figure = []
    zone = type("_Zone", (), {"box": _Box(55.8, 300.0, 206.0, 390.0)})()
    setter = object.__new__(Typesetting)
    setter._line_edges = type("_Link", (), {"edges": edges})()
    setter._current_zone_index = type("_Zones", (), {"zones": [zone]})()
    assert Typesetting.get_max_bottom_space(setter, current, page) == 373.2

    page.pdf_character = [
        type("_Char", (), {"box": _Box(60.0, 360.0, 230.0, 391.0)})(),
    ]
    setter._line_edges = type("_Link", (), {"edges": edges})()
    assert Typesetting.get_max_bottom_space(setter, current, page) == 391.0

    setter._line_edges = None


def test_a_column_quote_zone_does_not_stop_the_lower_lines():
    """A quote tag across the column is not the floor. The paragraph is."""
    from babeldoc.format.pdf.document_il.midend.typesetting import Typesetting
    from babeldoc.format.pdf.document_il.utils.layout_plan.line_edges import (
        covers_lower_span,
    )

    assert covers_lower_span(204.0, 523.6, 214.0, 511.6)
    assert not covers_lower_span(55.8, 206.0, 214.0, 511.6)

    class _Box:
        def __init__(self, x, y, x2, y2):
            self.x = x
            self.y = y
            self.x2 = x2
            self.y2 = y2

    edges = (
        (199.0, 512.6),
        (203.0, 512.6),
        (207.0, 512.6),
        (211.0, 512.6),
        (214.0, 512.6),
        (216.0, 512.6),
        (218.0, 512.6),
        (220.0, 427.9),
    )
    current = _Box(199.0, 439.5, 511.6, 503.2)
    page = type("_Page", (), {})()
    page.cropbox = type("_Crop", (), {"box": _Box(0.0, 0.0, 612.0, 792.0)})()
    page.pdf_paragraph = [
        type("_Para", (), {"box": current})(),
        type("_Para", (), {"box": _Box(216.0, 238.2, 511.6, 373.2)})(),
    ]
    page.pdf_character = []
    page.pdf_figure = []
    column = type(
        "_Zone",
        (),
        {"kind": "quote", "box": _Box(204.0, 226.0, 523.6, 385.2)},
    )()
    side = type(
        "_Zone",
        (),
        {"kind": "quote", "box": _Box(55.8, 194.0, 254.0, 449.0)},
    )()
    setter = object.__new__(Typesetting)
    setter._line_edges = type("_Link", (), {"edges": edges})()
    setter._current_zone_index = type(
        "_Zones", (), {"zones": [column, side]}
    )()
    assert Typesetting.get_max_bottom_space(setter, current, page) == 373.2

    setter._line_edges = None
    assert Typesetting.get_max_bottom_space(setter, current, page) == 385.2


def test_toc_plain_matches_directory_block():
    lines = [
        [36.0, 300.0, 500.0],
        [36.0, 300.0, 480.0],
        [36.0, 300.0, 460.0],
    ]
    facts = _facts(lines, source_text="Table of Contents\nPart 1\nPart 2")
    plan = build_plan(facts)
    assert plan.decisions[0].contour_status == "matched"
    assert plan.decisions[0].contour_plugin == "toc/plain"
    assert plan.decisions[0].contour_residual == 0.0
    link = plan.line_edge_links[0]
    assert link.edges == ((36.0, 300.0, 500.0), (36.0, 300.0, 480.0), (36.0, 300.0, 460.0))

