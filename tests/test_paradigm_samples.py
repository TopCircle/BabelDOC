"""Named outlines are keyed by the geometry digest of the sealed lines.

A book page in seen_in records where a person looked. It is not a match rule.
"""

import json
from pathlib import Path

from babeldoc.format.pdf.document_il.utils.layout_plan.model import LineBox
from babeldoc.format.pdf.document_il.utils.layout_plan.model import geometry_digest

_GOLD = Path(__file__).parent / "golden" / "layout_plan" / "paradigm_samples.json"
_MODULES = frozenset({"rect/full_column", "taper/left_pin", "taper/right_pin"})


def _extreme_indexes(values: list[float]) -> tuple[int, int]:
    low = min(range(len(values)), key=values.__getitem__)
    high = max(range(len(values)), key=values.__getitem__)
    return low, high


def test_each_sample_is_a_module_path_keyed_by_its_geometry():
    gold = json.loads(_GOLD.read_text(encoding="utf-8"))
    assert gold["kind"] == "paradigm_samples"
    by_book: dict[str, set[str]] = {}
    for sample in gold["samples"]:
        paradigm = sample["paradigm"]
        assert paradigm in _MODULES
        lines = tuple(LineBox(*row) for row in sample["lines"])
        assert sample["block_id"] == geometry_digest(lines)
        assert len(sample["block_id"]) == 16
        measure = sample["measure"]
        assert measure["line_count"] == len(lines)
        assert measure["line_count"] >= 4
        assert "nearest" not in sample
        seen = sample["seen_in"]
        assert seen["relpath"] and not str(seen["relpath"]).startswith("/")
        by_book.setdefault(paradigm, set()).add(seen["relpath"])
        if paradigm == "rect/full_column":
            assert measure["left_range"] <= 8
            assert measure["right_range"] <= 8
        elif paradigm == "taper/left_pin":
            assert measure["full_count"] >= 4
            assert measure["left_range"] <= 8
            assert measure["right_range"] >= 18
            low, high = _extreme_indexes([line.x1 for line in lines])
            assert {low, high} <= {0, len(lines) - 1}
        else:
            assert measure["full_count"] >= 4
            assert measure["left_range"] > 8
            assert measure["right_range"] <= 8
            low, high = _extreme_indexes([line.x0 for line in lines])
            assert {low, high} <= {0, len(lines) - 1}
    assert set(by_book) == _MODULES
    for books in by_book.values():
        assert len(books) >= 2
    for item in gold["withheld"]:
        assert item["where"] and item["reason"]
        assert "block_id" not in item
