"""Claim modules score a sealed block. The index stores the winner only."""

import json
from pathlib import Path

from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms import load_modules
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.contract import (
    BlockEdges,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.contract import pick
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.index import (
    append_index,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.index import index_row

_GOLD = Path(__file__).parent / "golden" / "layout_plan" / "paradigm_samples.json"
_MODULES = {
    "rect/full_column",
    "taper/left_pin",
    "taper/right_pin",
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
    return tuple(
        (path, module.claim(edges, lines), module.THRESHOLD)
        for path, module in load_modules()
    )


def test_loaded_modules_are_the_three_named_paradigms():
    modules = dict(load_modules())
    assert set(modules) == _MODULES
    assert modules["rect/full_column"].THRESHOLD == 1.0
    assert modules["taper/left_pin"].THRESHOLD == 8.0
    assert modules["taper/right_pin"].THRESHOLD == 8.0
    for module in modules.values():
        assert callable(module.claim)


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


def test_bullet_on_a_stable_rectangle_is_unmatched():
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
    assert status == "unmatched"
    assert paradigm == ""
    assert residual is None
    serial = _edges(4, 0.0, 0.2, marker="serial")
    status, paradigm, residual = pick(_results(serial, lines))
    assert status == "unmatched"
    assert paradigm == ""
    assert residual is None


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
