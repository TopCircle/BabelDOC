"""One index row per sealed block.

A gate other than ``single_page`` is stored as ``gate`` and is not sent
through the modules. ``nearest`` is not a field.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms import load_modules
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.contract import (
    BlockEdges,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.contract import pick


def index_row(
    source_fingerprint: str,
    relpath: str,
    page_index: int,
    block_id: str,
    lines: Sequence[Sequence[float]],
    edges: BlockEdges,
    input_gate: str,
) -> dict[str, object]:
    """Build one JSON-ready row. Do not call the modules on a closed gate."""
    recorded = [[float(line[0]), float(line[1]), float(line[2])] for line in lines]
    if input_gate != "single_page":
        status, paradigm, residual = "gate", "", None
    else:
        results = tuple(
            (path, module.claim(edges, recorded), module.THRESHOLD)
            for path, module in load_modules()
        )
        status, paradigm, residual = pick(results)
    return {
        "source_fingerprint": source_fingerprint,
        "relpath": relpath,
        "page_index": page_index,
        "block_id": block_id,
        "lines": recorded,
        "measurement": {
            "full_count": edges.full_count,
            "left_range": edges.left_range,
            "right_range": edges.right_range,
            "left_monotone": edges.left_monotone,
            "right_monotone": edges.right_monotone,
            "marker": edges.marker,
        },
        "status": status,
        "paradigm": paradigm,
        "residual": residual,
    }


def append_index(path: str | Path, row: dict[str, object]) -> None:
    """Append one JSON object and a newline."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
