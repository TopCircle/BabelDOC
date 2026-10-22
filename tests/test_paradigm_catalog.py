"""Claim modules score a sealed block. The index stores the winner only."""

import json
from pathlib import Path

import pytest
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms import load_catalog
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms import load_modules
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.contract import (
    BlockEdges,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.contract import (
    Paradigm,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.contract import pick
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.contract import (
    stand_down,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.index import (
    append_index,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.index import index_row
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.outline import (
    wider_below,
)

_GOLD = Path(__file__).parent / "golden" / "layout_plan" / "paradigm_samples.json"
_ORIGINAL = {
    "rect/full_column",
    "taper/left_pin",
    "taper/right_pin",
}
_OUTLINES = {
    "rect/light_column",
    "rag/right_edge",
    "rag/deep_right",
    "rag/left_edge",
    "step/right_upper_wide",
    "step/right_lower_wide",
    "step/right_spur",
    "bow/right_inset",
    "bow/right_bulge",
    "hang/shallow",
    "hang/deep",
    "hang/repeated",
    "mark/bullet_hang",
    "mark/bullet_plain",
    "mark/bullet_repeated",
    "mark/serial_hang",
    "mark/serial_plain",
    "mark/serial_repeated",
    "both/wider_below",
    "center/axis",
}


def _fail_claim(*_args, **_kwargs):
    raise AssertionError("claim ran")


def _edges(
    full_count: int,
    left_range: float,
    right_range: float,
    *,
    marker: str = "none",
    left_monotone: float = 1.0,
    right_monotone: float = 1.0,
) -> BlockEdges:
    return BlockEdges(
        full_count=full_count,
        left_range=left_range,
        right_range=right_range,
        left_monotone=left_monotone,
        right_monotone=right_monotone,
        marker=marker,
    )


def _results(edges: BlockEdges, lines: list[list[float]]):
    return stand_down(
        tuple(
            (path, module.claim(edges, lines), module.THRESHOLD)
            for path, module in load_modules()
        )
    )


def _named(results):
    return ((path, residual) for path, residual, _threshold in results)


def test_loaded_modules_keep_the_original_three_and_the_outline_claims():
    modules = dict(load_modules())
    assert set(modules) == _ORIGINAL | _OUTLINES
    assert modules["rect/full_column"].THRESHOLD == 1.0
    assert modules["taper/left_pin"].THRESHOLD == 8.0
    assert modules["taper/right_pin"].THRESHOLD == 8.0
    assert "rag" not in modules
    assert "mark" not in modules
    for module in modules.values():
        assert callable(module.claim)


def _one_line_claim(edges: BlockEdges, lines: list[list[float]]) -> float | None:
    if edges.marker == "none" and len(lines) == 1:
        return 0.0
    return None


def test_a_passed_in_paradigm_joins_the_system_catalog():
    added = Paradigm("custom/one_line", 8.0, _one_line_claim)
    catalog = load_catalog((added,))
    names = {item.name for item in catalog}
    assert "custom/one_line" in names
    assert "rect/full_column" in names
    edges = _edges(1, 0.0, 0.0)
    lines = [[35.0, 200.0, 100.0]]
    row = index_row(
        "fp",
        "Book/Book.pdf",
        0,
        "cccccccccccccccc",
        lines,
        edges,
        "single_page",
        catalog=catalog,
    )
    assert row["status"] == "matched"
    assert row["paradigm"] == "custom/one_line"
    assert row["residual"] == 0.0
    untouched = index_row(
        "fp",
        "Book/Book.pdf",
        0,
        "cccccccccccccccc",
        lines,
        edges,
        "single_page",
    )
    assert untouched["paradigm"] == ""
    assert untouched["residual"] is None


def test_a_paradigm_name_is_a_path_and_cannot_replace_a_system_one():
    with pytest.raises(ValueError):
        Paradigm("rag", 8.0, _one_line_claim)
    system = next(item for item in load_catalog() if item.name == "rect/full_column")
    with pytest.raises(ValueError):
        load_catalog((system,))


def test_each_sample_matches_only_its_own_paradigm():
    gold = json.loads(_GOLD.read_text(encoding="utf-8"))
    assert len(gold["samples"]) == 6
    for sample in gold["samples"]:
        measure = sample["measure"]
        edges = _edges(
            measure["full_count"],
            measure["left_range"],
            measure["right_range"],
            left_monotone=measure["left_monotone"],
            right_monotone=measure["right_monotone"],
        )
        results = _results(edges, sample["lines"])
        matched = [
            path
            for path, residual, threshold in results
            if residual is not None and residual < threshold
        ]
        status, paradigm, residual = pick(results)
        assert matched == [sample["paradigm"]]
        assert status == "matched"
        assert paradigm == sample["paradigm"]
        assert residual is not None
        row = index_row(
            "sample",
            sample["seen_in"]["relpath"],
            sample["seen_in"]["page_index"],
            sample["block_id"],
            sample["lines"],
            edges,
            "single_page",
        )
        assert row["status"] == "matched"
        assert row["paradigm"] == sample["paradigm"]
        assert row["residual"] == residual
        assert row["lines"] == sample["lines"]
        assert row["measurement"]["marker"] == "none"
        assert row["measurement"]["full_count"] == measure["full_count"]
        assert "line_count" not in row["measurement"]
        assert "nearest" not in row


def test_one_line_block_is_unmatched():
    edges = _edges(1, 0.0, 0.0)
    lines = [[35.0, 200.0, 100.0]]
    status, paradigm, residual = pick(_results(edges, lines))
    assert status == "unmatched"
    assert paradigm == ""
    assert residual is None


def test_bow_is_unmatched_and_not_a_right_pin():
    lines = [
        [100.0, 400.0, 200.0],
        [90.0, 400.0, 180.0],
        [70.0, 400.0, 160.0],
        [90.0, 400.0, 140.0],
        [100.0, 400.0, 120.0],
    ]
    edges = _edges(5, 30.0, 0.2)
    results = _results(edges, lines)
    by_path = {path: residual for path, residual, _threshold in results}
    assert by_path["taper/right_pin"] is None
    status, paradigm, residual = pick(results)
    assert status == "unmatched"
    assert paradigm == ""
    assert paradigm != "taper/right_pin"
    assert residual == 30.0


def test_shallow_free_edge_is_not_a_pin():
    left_lines = [
        [100.0, 400.0 - (10.1 * index / 5.0), 200.0 - index * 16.0]
        for index in range(6)
    ]
    left = _results(_edges(6, 0.0, 10.1), left_lines)
    assert dict(_named(left))["taper/left_pin"] is None
    status, paradigm, residual = pick(left)
    assert status == "matched"
    assert paradigm == "rect/light_column"
    assert abs(residual - 10.1) < 1e-9
    right_lines = [
        [300.0 - (10.1 * index / 5.0), 500.0, 200.0 - index * 16.0]
        for index in range(6)
    ]
    right = _results(_edges(6, 10.1, 0.0), right_lines)
    assert dict(_named(right))["taper/right_pin"] is None
    status, paradigm, residual = pick(right)
    assert status == "matched"
    assert paradigm == "rect/light_column"
    assert abs(residual - 10.1) < 1e-9


def test_free_edge_of_18_matches_on_the_pinned_range():
    lines = [
        [100.0, 400.0 - (18.0 * index / 5.0), 200.0 - index * 16.0]
        for index in range(6)
    ]
    status, paradigm, residual = pick(_results(_edges(6, 0.0, 18.0), lines))
    assert status == "matched"
    assert paradigm == "taper/left_pin"
    assert residual == 0.0


def test_a_3pt_step_back_on_an_outward_run_stays_a_left_pin():
    rights = [300.0, 297.0, 305.0, 313.0, 321.0, 329.0]
    lines = [
        [36.0, right, 400.0 - index * 16.0] for index, right in enumerate(rights)
    ]
    status, paradigm, residual = pick(_results(_edges(6, 0.0, 32.0), lines))
    assert status == "matched"
    assert paradigm == "taper/left_pin"
    assert residual == 0.0
    dipped = [
        [value, 500.0, 400.0 - index * 16.0] for index, value in enumerate(rights)
    ]
    right = _results(_edges(6, 32.0, 0.0), dipped)
    assert dict(_named(right))["taper/right_pin"] is None


def test_a_20pt_run_with_one_line_inside_is_not_a_pin():
    lines = [
        [36.0, 300.0, 400.0],
        [36.0, 310.0, 384.0],
        [36.0, 320.0, 368.0],
        [36.0, 317.0, 352.0],
    ]
    results = _results(_edges(4, 0.0, 20.0), lines)
    assert dict(_named(results))["taper/left_pin"] is None


def test_a_free_edge_step_past_4pt_is_still_a_fold():
    lines = [
        [36.0, 320.0, 400.0],
        [36.0, 314.9, 384.0],
        [36.0, 322.0, 368.0],
        [36.0, 330.0, 352.0],
        [36.0, 338.0, 336.0],
        [36.0, 346.0, 320.0],
    ]
    results = _results(_edges(6, 0.0, 31.1), lines)
    assert dict(_named(results))["taper/left_pin"] is None


def test_a_short_last_line_on_a_straight_run_stays_a_pin():
    lines = [
        [36.0, 400.0, 400.0],
        [36.0, 400.0, 384.0],
        [36.0, 400.0, 368.0],
        [36.0, 330.0, 352.0],
    ]
    status, paradigm, residual = pick(_results(_edges(4, 0.0, 70.0), lines))
    assert status == "matched"
    assert paradigm == "taper/left_pin"
    assert residual == 0.0


def test_a_short_last_line_with_a_tiny_opposite_step_stays_off_the_pin():
    lines = [
        [36.0, 400.0, 400.0],
        [36.0, 400.02, 384.0],
        [36.0, 399.9, 368.0],
        [36.0, 360.0, 352.0],
    ]
    results = _results(_edges(4, 0.0, 40.02), lines)
    assert dict(_named(results))["taper/left_pin"] is None


def test_a_fold_in_the_free_edge_is_not_a_pin():
    lines = [
        [100.0, 400.0, 200.0],
        [100.0, 300.0, 184.0],
        [100.0, 360.0, 168.0],
        [100.0, 340.0, 152.0],
        [100.0, 250.0, 136.0],
    ]
    results = _results(_edges(5, 0.0, 150.0), lines)
    assert dict(_named(results))["taper/left_pin"] is None
    status, paradigm, residual = pick(results)
    assert status == "matched"
    assert paradigm == "rag/deep_right"
    assert residual == 0.0
    right_lines = [
        [300.0, 500.0, 200.0],
        [250.0, 500.0, 184.0],
        [270.0, 500.0, 168.0],
        [220.0, 500.0, 152.0],
        [180.0, 500.0, 136.0],
    ]
    right = _results(_edges(5, 120.0, 0.0), right_lines)
    assert dict(_named(right))["taper/right_pin"] is None
    status, paradigm, residual = pick(right)
    assert status == "matched"
    assert paradigm == "rag/left_edge"
    assert residual == 0.0


def test_widening_and_a_flat_step_still_match():
    widening = [
        [100.0, 250.0 + (40.0 * index), 200.0 - index * 16.0] for index in range(6)
    ]
    status, paradigm, residual = pick(_results(_edges(6, 0.0, 200.0), widening))
    assert status == "matched"
    assert paradigm == "taper/left_pin"
    assert residual == 0.0
    flat = [
        [100.0, 400.0, 200.0],
        [100.0, 360.0, 184.0],
        [100.0, 360.0, 168.0],
        [100.0, 320.0, 152.0],
        [100.0, 280.0, 136.0],
        [100.0, 240.0, 120.0],
    ]
    status, paradigm, residual = pick(_results(_edges(6, 0.0, 160.0), flat))
    assert status == "matched"
    assert paradigm == "taper/left_pin"
    assert residual == 0.0


def test_pinned_edge_past_the_threshold_stays_unmatched():
    lines = [[100.0, 400.0 - (8.0 * index), 200.0 - index * 16.0] for index in range(6)]
    results = _results(_edges(6, 9.0, 40.0), lines)
    assert dict(_named(results))["taper/left_pin"] == 9.0
    status, paradigm, residual = pick(results)
    assert status == "unmatched"
    assert paradigm == ""
    assert residual == 9.0


def test_bullet_on_a_stable_rectangle_is_a_plain_marker():
    lines = [
        [35.0, 400.0, 120.0],
        [35.0, 400.0, 100.0],
        [35.0, 400.0, 80.0],
        [35.0, 400.0, 60.0],
    ]
    plain = _edges(4, 0.0, 0.2)
    status, paradigm, _residual = pick(_results(plain, lines))
    assert status == "matched"
    assert paradigm == "rect/full_column"
    marked = _edges(4, 0.0, 0.2, marker="bullet")
    status, paradigm, residual = pick(_results(marked, lines))
    assert status == "matched"
    assert paradigm == "mark/bullet_plain"
    assert residual == 0.0
    serial = _edges(4, 0.0, 0.2, marker="serial")
    status, paradigm, residual = pick(_results(serial, lines))
    assert status == "matched"
    assert paradigm == "mark/serial_plain"
    assert residual == 0.0


def test_residual_equal_to_its_threshold_stays_unmatched():
    status, paradigm, residual = pick((("rect/full_column", 1.0, 1.0),))
    assert status == "unmatched"
    assert paradigm == ""
    assert residual == 1.0


def test_two_under_threshold_results_conflict():
    status, paradigm, residual = pick(
        (
            ("taper/right_pin", None, 8.0),
            ("taper/left_pin", 3.0, 8.0),
            ("rect/full_column", 0.4, 1.0),
        )
    )
    assert status == "conflict"
    assert paradigm == ""
    assert residual == 0.4


def test_spread_gate_does_not_claim(monkeypatch):
    for _path, module in load_modules():
        monkeypatch.setattr(module, "claim", _fail_claim)
    row = index_row(
        "fp",
        "Book/Book.pdf",
        3,
        "aaaaaaaaaaaaaaaa",
        [(35.0, 400.0, 100.0), (35.0, 400.0, 80.0)],
        _edges(6, 0.0, 0.2),
        "spread",
    )
    assert row["status"] == "gate"
    assert row["paradigm"] == ""
    assert row["residual"] is None
    assert "nearest" not in row


def test_written_row_has_no_nearest(tmp_path):
    row = index_row(
        "fp",
        "Book/Book.pdf",
        1,
        "bbbbbbbbbbbbbbbb",
        [(1.0, 2.0, 3.0)],
        _edges(1, 0.0, 0.0),
        "single_page",
    )
    assert "nearest" not in row
    path = tmp_path / "blocks.jsonl"
    append_index(path, row)
    text = path.read_text(encoding="utf-8")
    assert "nearest" not in text
    assert text.endswith("\n")
    assert len(text.splitlines()) == 1
    saved = json.loads(text)
    assert "nearest" not in saved
    assert set(saved) == {
        "source_fingerprint",
        "relpath",
        "page_index",
        "block_id",
        "lines",
        "measurement",
        "status",
        "paradigm",
        "residual",
    }
    assert saved["status"] == "unmatched"
    assert saved["residual"] is None
    assert saved["lines"] == [[1.0, 2.0, 3.0]]
    assert saved["measurement"]["marker"] == "none"


def test_rect_full_column_source_does_not_name_taper():
    modules = dict(load_modules())
    text = Path(modules["rect/full_column"].__file__).read_text(encoding="utf-8")
    folded = text.lower()
    assert "taper" not in folded
    assert "is_taper" not in folded


def test_a_one_way_step_the_pin_already_owns_stays_a_pin():
    lines = [[100.0, 400.0, 200.0 - index * 16.0] for index in range(3)]
    lines += [[100.0, 300.0, 152.0 - index * 16.0] for index in range(3)]
    edges = _edges(6, 0.0, 100.0)
    step = dict(load_modules())["step/right_upper_wide"]
    assert step.claim(edges, lines) == 0.0
    status, paradigm, residual = pick(_results(edges, lines))
    assert status == "matched"
    assert paradigm == "taper/left_pin"
    assert residual == 0.0


def test_a_two_width_right_edge_with_few_full_lines_is_a_step():
    lines = [
        [100.0, 400.0, 200.0],
        [100.0, 400.0, 184.0],
        [100.0, 398.0, 168.0],
        [100.0, 280.0, 152.0],
        [100.0, 280.0, 136.0],
        [100.0, 278.0, 120.0],
    ]
    status, paradigm, residual = pick(_results(_edges(3, 0.0, 9.0), lines))
    assert status == "matched"
    assert paradigm == "step/right_upper_wide"
    assert residual == 0.0


def test_a_figure_step_is_not_stolen_by_the_flat_full_lines():
    lines = [
        [102.0, 335.7, 160.0],
        [102.0, 335.6, 145.0],
        [102.0, 335.6, 130.0],
        [102.0, 512.7, 115.0],
        [102.0, 512.6, 100.0],
        [102.0, 512.7, 85.0],
        [102.0, 512.6, 70.0],
        [102.0, 292.5, 55.0],
    ]
    status, paradigm, residual = pick(_results(_edges(4, 0.0, 0.2), lines))
    assert status == "matched"
    assert paradigm == "step/right_lower_wide"
    assert residual == 0.0


def test_a_short_last_line_stays_a_full_column():
    lines = [
        [100.0, 400.0, 200.0],
        [100.0, 400.0, 184.0],
        [100.0, 400.0, 168.0],
        [100.0, 220.0, 152.0],
    ]
    status, paradigm, residual = pick(_results(_edges(3, 0.0, 0.2), lines))
    assert status == "matched"
    assert paradigm == "rect/full_column"
    assert residual == 0.2


def test_a_lower_wide_step_and_a_single_spur_stay_apart():
    lower = [
        [100.0, 280.0, 200.0],
        [100.0, 280.0, 184.0],
        [100.0, 400.0, 168.0],
        [100.0, 400.0, 152.0],
    ]
    status, paradigm, _residual = pick(_results(_edges(2, 0.0, 120.0), lower))
    assert status == "matched"
    assert paradigm == "step/right_lower_wide"
    spur = [
        [100.0, 280.0, 200.0],
        [100.0, 280.0, 184.0],
        [100.0, 280.0, 168.0],
        [100.0, 280.0, 152.0],
        [100.0, 400.0, 136.0],
    ]
    status, paradigm, _residual = pick(_results(_edges(1, 0.0, 0.0), spur))
    assert status == "matched"
    assert paradigm == "step/right_spur"


def test_one_deep_right_turn_is_a_bow_and_a_left_bow_stays_open():
    inset = [
        [100.0, 400.0 - (4.0 * step), 200.0 - index * 16.0]
        for index, step in enumerate([0, 5, 9, 11, 13, 15, 14, 11, 8, 7])
    ]
    status, paradigm, residual = pick(_results(_edges(10, 0.0, 60.0), inset))
    assert status == "matched"
    assert paradigm == "bow/right_inset"
    assert residual == 0.0
    bulge = [
        [100.0, 400.0 - (4.0 * step), 200.0 - index * 16.0]
        for index, step in enumerate([20, 17, 16, 4, 0, 3, 4, 8, 7])
    ]
    status, paradigm, _residual = pick(_results(_edges(9, 0.0, 80.0), bulge))
    assert paradigm == "bow/right_bulge"


def test_a_middle_spike_on_a_flat_shelf_is_a_spur():
    lines = [
        [100.0, 300.0, 200.0],
        [100.0, 300.0, 184.0],
        [100.0, 360.0, 168.0],
        [100.0, 300.0, 152.0],
        [100.0, 300.0, 136.0],
        [100.0, 300.0, 120.0],
    ]
    edges = _edges(6, 0.0, 60.0)
    modules = dict(load_modules())
    assert modules["bow/right_bulge"].claim(edges, lines) is None
    assert modules["step/right_spur"].claim(edges, lines) == 0.0
    status, paradigm, residual = pick(_results(edges, lines))
    assert status == "matched"
    assert paradigm == "step/right_spur"
    assert residual == 0.0


def test_plain_hanging_indent_splits_on_depth_and_repetition():
    shallow = [
        [100.0, 400.0, 200.0],
        [114.0, 360.0, 184.0],
        [114.0, 340.0, 168.0],
        [114.0, 380.0, 152.0],
    ]
    status, paradigm, residual = pick(_results(_edges(4, 14.0, 60.0), shallow))
    assert status == "matched"
    assert paradigm == "hang/shallow"
    assert residual == 0.0
    deep = [[100.0, 400.0, 200.0]]
    deep += [[164.0, 400.0, 184.0 - index * 16.0] for index in range(4)]
    status, paradigm, _residual = pick(_results(_edges(1, 0.0, 0.0), deep))
    assert paradigm == "hang/deep"
    repeated = [
        [100.0, 400.0, 200.0],
        [136.0, 360.0, 184.0],
        [100.0, 400.0, 168.0],
        [136.0, 360.0, 152.0],
        [136.0, 360.0, 136.0],
    ]
    status, paradigm, _residual = pick(_results(_edges(5, 36.0, 40.0), repeated))
    assert paradigm == "hang/repeated"


def test_a_hanging_bullet_is_not_a_plain_marker():
    lines = [
        [100.0, 400.0, 200.0],
        [116.0, 360.0, 184.0],
        [116.0, 340.0, 168.0],
        [116.0, 380.0, 152.0],
    ]
    status, paradigm, _residual = pick(
        _results(_edges(4, 16.0, 60.0, marker="bullet"), lines)
    )
    assert status == "matched"
    assert paradigm == "mark/bullet_hang"


def test_a_full_last_line_that_stops_short_stays_a_right_pin():
    steps = (0.0, 4.0, 8.0, 12.0, 15.0, 17.0, 19.0, 21.0)
    lines = [
        [199.0 + step, 512.6, 400.0 - index * 15.0]
        for index, step in enumerate(steps)
    ]
    lines[-1] = [220.0, 427.9, lines[-1][2]]
    status, paradigm, residual = pick(_results(_edges(8, 21.0, 84.7), lines))
    assert status == "matched"
    assert paradigm == "taper/right_pin"
    assert residual is not None
    assert residual < 8


def test_a_hang_with_a_short_tail_stays_a_hang():
    lines = [
        [186.0, 572.6, 200.0],
        [198.0, 572.7, 184.0],
        [204.0, 572.6, 168.0],
        [208.0, 494.7, 152.0],
    ]
    status, paradigm, _residual = pick(_results(_edges(4, 22.0, 78.0), lines))
    assert status == "matched"
    assert paradigm == "hang/shallow"


def test_one_line_outside_the_wall_stays_a_light_column():
    lines = [
        [205.0, 512.7, 200.0],
        [200.0, 512.6, 184.0],
        [196.0, 510.0, 168.0],
        [191.0, 510.0, 152.0],
        [185.0, 430.6, 136.0],
    ]
    status, paradigm, _residual = pick(_results(_edges(5, 20.0, 82.1), lines))
    assert status == "matched"
    assert paradigm == "rect/light_column"


def test_a_hang_the_right_pin_already_owns_stays_a_pin():
    lines = [[100.0, 400.0, 200.0]]
    lines += [[120.0, 400.0, 184.0 - index * 16.0] for index in range(4)]
    edges = _edges(5, 20.0, 0.0)
    shelf = dict(load_modules())["hang/shallow"]
    assert shelf.claim(edges, lines) == 0.0
    status, paradigm, residual = pick(_results(edges, lines))
    assert status == "matched"
    assert paradigm == "taper/right_pin"
    assert residual == 0.0


def test_both_edges_opening_downward_match_wider_below():
    lines = [
        [140.0 - index * 8.0, 360.0 + index * 8.0, 200.0 - index * 16.0]
        for index in range(6)
    ]
    status, paradigm, residual = pick(_results(_edges(6, 40.0, 40.0), lines))
    assert status == "matched"
    assert paradigm == "both/wider_below"
    assert residual == 0.0


def test_a_short_tail_that_keeps_opening_stays_wider_below():
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
    edges = _edges(12, 57.0, 61.02)
    module = dict(load_modules())["both/wider_below"]
    assert wider_below(edges, lines) is None
    status, paradigm, residual = pick(_results(edges, lines))
    assert status == "matched"
    assert paradigm == "both/wider_below"
    assert residual == module.claim(edges, lines)
    assert residual == wider_below(edges, lines[:-1])


def test_wider_below_without_a_short_tail_keeps_its_residual():
    module = dict(load_modules())["both/wider_below"]
    opening = [
        [140.0 - index * 8.0, 360.0 + index * 8.0, 200.0 - index * 16.0]
        for index in range(6)
    ]
    page = [
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
    ]
    day = [
        [274.09, 318.76, 450.99],
        [267.00, 362.58, 437.67],
        [260.00, 370.59, 422.67],
        [253.00, 375.58, 407.67],
        [246.00, 381.57, 392.68],
        [239.01, 389.60, 377.68],
        [232.01, 397.57, 362.68],
    ]
    for lines in (opening, page, day):
        edges = _edges(len(lines), 40.0, 40.0)
        assert module.claim(edges, lines) == wider_below(edges, lines)


def test_a_far_left_jump_on_the_last_line_is_not_a_short_tail():
    lines = [
        [140.0 - index * 8.0, 360.0 + index * 8.0, 200.0 - index * 16.0]
        for index in range(6)
    ]
    lines.append([lines[-1][0] - 40.0, lines[-1][1] - 200.0, lines[-1][2] - 16.0])
    module = dict(load_modules())["both/wider_below"]
    edges = _edges(len(lines), 80.0, 80.0)
    assert module.claim(edges, lines) is None
    assert module.claim(edges, lines) == wider_below(edges, lines)


def test_one_outward_jump_stays_with_its_own_shape():
    dipped = [
        [140.0, 280.0, 200.0],
        [100.0, 360.0, 184.0],
        [100.0, 360.0, 168.0],
        [100.0, 360.0, 152.0],
        [100.0, 360.0, 136.0],
    ]
    edges = _edges(5, 40.0, 80.0)
    modules = dict(load_modules())
    assert modules["both/wider_below"].claim(edges, dipped) is None
    status, paradigm, residual = pick(_results(edges, dipped))
    assert status == "matched"
    assert paradigm == "rect/light_column"
    assert residual == 0.0
    shelf = [
        [140.0, 280.0, 200.0],
        [140.0, 280.0, 184.0],
        [140.0, 280.0, 168.0],
        [100.0, 280.0, 152.0],
        [100.0, 360.0, 136.0],
    ]
    edges = _edges(5, 40.0, 80.0)
    assert modules["both/wider_below"].claim(edges, shelf) is None
    status, paradigm, residual = pick(_results(edges, shelf))
    assert status == "matched"
    assert paradigm == "hang/repeated"
    assert residual == 0.0
    short = [
        [124.0, 376.0, 200.0],
        [112.0, 388.0, 184.0],
        [100.0, 400.0, 168.0],
        [100.0, 400.0, 152.0],
        [100.0, 400.0, 136.0],
    ]
    edges = _edges(5, 24.0, 24.0)
    assert modules["both/wider_below"].claim(edges, short) is None
    status, paradigm, residual = pick(_results(edges, short))
    assert status == "matched"
    assert paradigm == "rect/light_column"
    assert residual == 12.0


def test_a_narrow_indent_band_stays_a_repeated_hang():
    lines = [
        [129.0, 340.0, 200.0],
        [122.0, 356.0, 184.0],
        [122.0, 372.0, 168.0],
        [100.0, 388.0, 152.0],
        [100.0, 400.0, 136.0],
    ]
    edges = _edges(5, 29.0, 60.0)
    modules = dict(load_modules())
    assert modules["both/wider_below"].claim(edges, lines) is None
    assert modules["hang/repeated"].claim(edges, lines) == 7.0
    status, paradigm, residual = pick(_results(edges, lines))
    assert status == "matched"
    assert paradigm == "hang/repeated"
    assert residual == 7.0


def test_a_sixteen_point_wall_stays_under_the_light_threshold():
    lines = [
        [100.0, 400.0, 200.0],
        [116.0, 400.0, 184.0],
        [108.0, 400.0, 168.0],
        [116.0, 400.0, 152.0],
    ]
    edges = _edges(4, 16.0, 0.0)
    light = dict(load_modules())["rect/light_column"]
    assert light.claim(edges, lines) == 16.0
    status, paradigm, _residual = pick(_results(edges, lines))
    assert status == "unmatched"
    assert paradigm == ""


def test_one_short_line_stays_light_and_a_stacked_hang_stays_a_hang():
    dipped = [[100.0, 400.0, 200.0 - index * 16.0] for index in range(8)]
    dipped[3] = [101.0, 340.0, dipped[3][2]]
    status, paradigm, _residual = pick(_results(_edges(8, 1.0, 60.0), dipped))
    assert status == "matched"
    assert paradigm == "rect/light_column"
    ragged = [
        [100.0, 400.0, 200.0],
        [100.0, 250.0, 184.0],
        [100.0, 390.0, 168.0],
        [100.0, 310.0, 152.0],
        [100.0, 280.0, 136.0],
        [100.0, 360.0, 120.0],
    ]
    status, paradigm, _residual = pick(_results(_edges(6, 0.0, 150.0), ragged))
    assert status == "matched"
    assert paradigm == "rag/deep_right"
    shallow = pick(_results(_edges(6, 0.0, 22.6), ragged))
    assert shallow[0] == "matched"
    assert shallow[1] == "rag/right_edge"
    deep_hit = [
        path
        for path, residual, threshold in _results(_edges(6, 0.0, 150.0), ragged)
        if residual is not None and residual < threshold
    ]
    assert deep_hit == ["rag/deep_right"]
    stacked = [
        [100.0, 400.0, 200.0],
        [136.0, 400.0, 184.0],
        [100.0, 400.0, 168.0],
        [136.0, 398.0, 152.0],
        [136.0, 400.0, 136.0],
    ]
    status, paradigm, residual = pick(_results(_edges(5, 36.0, 2.0), stacked))
    assert status == "matched"
    assert paradigm == "hang/repeated"
    assert residual == 0.0
