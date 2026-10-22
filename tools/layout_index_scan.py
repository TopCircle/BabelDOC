"""Seal source pages and score each block into the paradigm index.

Read-only. Does not translate, render, or rewrite the corpus page file.
A filename containing ``.zh`` or ``no_watermark`` is skipped.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import pymupdf
from babeldoc.format.pdf.document_il.utils.layout_plan.corpus import EXPECTED_PDF_COUNT
from babeldoc.format.pdf.document_il.utils.layout_plan.corpus import (
    is_derived_translation,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.gates import input_gate
from babeldoc.format.pdf.document_il.utils.layout_plan.marker import first_marker
from babeldoc.format.pdf.document_il.utils.layout_plan.measure import measure_region
from babeldoc.format.pdf.document_il.utils.layout_plan.model import LineBox
from babeldoc.format.pdf.document_il.utils.layout_plan.model import Region
from babeldoc.format.pdf.document_il.utils.layout_plan.model import geometry_digest
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms import (
    index as index_module,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.contract import (
    BlockEdges,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.index import index_row
from babeldoc.format.pdf.document_il.utils.layout_plan.seal import seal_lines

_SAMPLES = {
    "bfada19375a1da0f": "rect/full_column",
    "3d3a1a86e2a93d9c": "rect/full_column",
    "ad9a5d79c6255148": "taper/left_pin",
    "d074caa0495697de": "taper/left_pin",
    "e66ad1dbf852edd0": "taper/right_pin",
    "81858d74f14146aa": "taper/right_pin",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    root = args.root.expanduser().resolve()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if manifest.get("pdf_count") != EXPECTED_PDF_COUNT:
        print(
            f"pdf_count {manifest.get('pdf_count')} != {EXPECTED_PDF_COUNT}",
            file=sys.stderr,
        )
        return 2
    _pin_module_list()
    rows_path = args.out / "blocks.jsonl"
    partial = args.out / "blocks.jsonl.partial"
    args.out.mkdir(parents=True, exist_ok=True)
    status_counts: Counter[str] = Counter()
    paradigm_counts: Counter[str] = Counter()
    gate_counts: Counter[str] = Counter()
    samples: dict[str, list[dict[str, object]]] = {key: [] for key in _SAMPLES}
    gate_examples: dict[str, dict[str, object]] = {}
    pages = 0
    files = manifest["files"]
    with partial.open("w", encoding="utf-8") as handle:
        for number, row in enumerate(files, start=1):
            rel = row["path"]
            path = root / rel
            if is_derived_translation(path):
                print(f"skip derived {rel}", file=sys.stderr)
                continue
            try:
                page_rows = scan_pdf(path, row["sha256"], rel)
            except Exception as exc:
                print(f"FAILED {rel} {type(exc).__name__}: {exc}", file=sys.stderr)
                return 1
            for _gate, record in page_rows:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                status_counts[str(record["status"])] += 1
                paradigm_counts[str(record["paradigm"])] += 1
                seen = samples.get(str(record["block_id"]))
                if seen is not None:
                    seen.append(
                        {
                            "relpath": rel,
                            "page_index": record["page_index"],
                            "status": record["status"],
                            "paradigm": record["paradigm"],
                        }
                    )
            page_gates = _page_gates(page_rows)
            pages += len(page_gates)
            gate_counts.update(page_gates)
            for gate in page_gates:
                if gate == "single_page" or gate in gate_examples:
                    continue
                page_index = next(
                    record["page_index"]
                    for item_gate, record in page_rows
                    if item_gate == gate
                )
                gate_examples[gate] = {
                    "relpath": rel,
                    "page_index": page_index,
                    "statuses": sorted(
                        {
                            str(record["status"])
                            for item_gate, record in page_rows
                            if item_gate == gate and record["page_index"] == page_index
                        }
                    ),
                }
            print(
                f"{number}/{len(files)} {rel} pages={pages} blocks={sum(status_counts.values())}",
                flush=True,
            )
    partial.replace(rows_path)
    summary = {
        "pdf_count": len(files),
        "page_count": pages,
        "block_count": sum(status_counts.values()),
        "by_status": dict(status_counts),
        "by_paradigm": dict(paradigm_counts),
        "by_gate": dict(gate_counts),
        "gate_examples": gate_examples,
        "samples": {
            block_id: {"expected": _SAMPLES[block_id], "found": found}
            for block_id, found in samples.items()
        },
    }
    (args.out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"DONE pages={pages} blocks={sum(status_counts.values())} "
        f"status={dict(status_counts)} paradigm={dict(paradigm_counts)} "
        f"gates={dict(gate_counts)}"
    )
    return 0


def scan_pdf(
    path: Path, fingerprint: str, relpath: str
) -> list[tuple[str, dict[str, object]]]:
    """One ``(page gate, index row)`` per sealed block. The PDF is not written."""
    found: list[tuple[str, dict[str, object]]] = []
    document = pymupdf.open(path)
    try:
        for index, page in enumerate(document):
            found.extend(_scan_page(page, index, fingerprint, relpath))
    finally:
        document.close()
    return found


def _scan_page(page, index: int, fingerprint: str, relpath: str):
    records = _line_records(page)
    texts = [text for _box, text, _marker in records]
    gate, _health = input_gate(float(page.rect.width), texts)
    if not records:
        edges = BlockEdges(0, 0.0, 0.0, 1.0, 1.0, "none")
        row = index_row(
            fingerprint,
            relpath,
            index,
            geometry_digest(()),
            [],
            edges,
            gate,
        )
        return [(gate, row)]
    boxes = [box for box, _text, _marker in records]
    text_of = {id(box): (text, marker) for box, text, marker in records}
    rows = []
    for block in seal_lines(boxes):
        edges = _edges(block.lines, text_of, index)
        row = index_row(
            fingerprint,
            relpath,
            index,
            block.block_id,
            [(line.x0, line.x1, line.y0) for line in block.lines],
            edges,
            gate,
        )
        rows.append((gate, row))
    return rows


def _line_records(page):
    height = float(page.rect.height)
    found = []
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        for raw in block.get("lines") or []:
            spans = raw.get("spans") or []
            text = "".join(span.get("text", "") for span in spans).strip()
            if not text or not spans:
                continue
            x0 = min(float(span["bbox"][0]) for span in spans)
            x1 = max(float(span["bbox"][2]) for span in spans)
            y_down = min(float(span["bbox"][1]) for span in spans)
            found.append((LineBox(x0, x1, height - y_down), text, first_marker([raw])))
    return found


def _edges(lines: tuple[LineBox, ...], text_of: dict, page_index: int) -> BlockEdges:
    pieces: list[str] = []
    first_marker_evidence = None
    for line in lines:
        text, marker = text_of[id(line)]
        pieces.append(text)
        if first_marker_evidence is None:
            first_marker_evidence = marker
    bullet = (
        first_marker_evidence
        if first_marker_evidence is not None and first_marker_evidence.is_bullet
        else None
    )
    measured = measure_region(
        Region(
            region_id="scan",
            page_index=page_index,
            source_order=0,
            role="body",
            lines=lines,
            source_text=" ".join(pieces),
            marker=bullet,
        )
    )
    return BlockEdges(
        full_count=measured.full_count,
        left_range=measured.left_range,
        right_range=measured.right_range,
        left_monotone=measured.left_monotone,
        right_monotone=measured.right_monotone,
        marker=measured.marker,
    )


def _page_gates(page_rows: list[tuple[str, dict[str, object]]]) -> list[str]:
    """One gate per page. Several blocks on a page share that gate."""
    seen: dict[object, str] = {}
    for gate, record in page_rows:
        seen.setdefault(record["page_index"], gate)
    return list(seen.values())


def _pin_module_list() -> None:
    """Load the catalog once. This run does not add a module."""
    loaded = index_module.load_catalog()
    index_module.load_catalog = lambda: loaded


if __name__ == "__main__":
    raise SystemExit(main())
