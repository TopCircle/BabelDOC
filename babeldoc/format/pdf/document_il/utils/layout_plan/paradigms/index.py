"""One index row per sealed block.

A gate other than ``single_page`` is stored as ``gate`` and is not sent
through the modules. ``nearest`` is not a field.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms import load_catalog
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


def index_row(
    source_fingerprint: str,
    relpath: str,
    page_index: int,
    block_id: str,
    lines: Sequence[Sequence[float]],
    edges: BlockEdges,
    input_gate: str,
    *,
    catalog: Sequence[Paradigm] | None = None,
) -> dict[str, object]:
    """Build one JSON-ready row. Do not call the modules on a closed gate.

    The default catalog is the system list. A caller passes ``catalog``
    to add a paradigm. This function does not branch on a paradigm name.
    """
    recorded = [[float(line[0]), float(line[1]), float(line[2])] for line in lines]
    if input_gate != "single_page":
        status, paradigm, residual = "gate", "", None
    else:
        items = load_catalog() if catalog is None else catalog
        results = stand_down(
            tuple(
                (item.name, item.claim(edges, recorded), item.threshold)
                for item in items
            )
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
