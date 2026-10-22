"""Read PDF pages into facts and a frozen plan. The file is not written."""

from __future__ import annotations

from pathlib import Path

import pymupdf

from babeldoc.format.pdf.document_il.utils.layout_plan.compose import build_plan
from babeldoc.format.pdf.document_il.utils.layout_plan.facts import SourceBlock
from babeldoc.format.pdf.document_il.utils.layout_plan.facts import build_facts
from babeldoc.format.pdf.document_il.utils.layout_plan.gates import input_gate
from babeldoc.format.pdf.document_il.utils.layout_plan.log import emit
from babeldoc.format.pdf.document_il.utils.layout_plan.marker import first_marker
from babeldoc.format.pdf.document_il.utils.layout_plan.model import FigureBox
from babeldoc.format.pdf.document_il.utils.layout_plan.model import LineBox


def scan_pdf(
    path: Path, fingerprint: str, log_path: Path | None = None
) -> list[dict]:
    """One JSON-ready record per page. Opens the PDF read-only.

    ``log_path`` receives SCAN and MATCH lines. The plan itself is unchanged.
    """
    if log_path is not None:
        Path(log_path).write_text("", encoding="utf-8")
    document = pymupdf.open(path)
    try:
        records = []
        for index, page in enumerate(document):
            records.append(_scan_page(page, index, fingerprint, log_path))
        return records
    finally:
        document.close()


def _scan_page(page, index: int, fingerprint: str, log_path: Path | None) -> dict:
    blocks = _blocks(page)
    figures = _figures(page)
    gate, health = input_gate(
        float(page.rect.width),
        [block.source_text for block in blocks],
    )
    facts = build_facts(
        source_fingerprint=fingerprint,
        page_index=index,
        page_width=float(page.rect.width),
        page_height=float(page.rect.height),
        input_gate=gate,
        text_health=health,
        blocks=blocks,
        figures=figures,
        identity_scope="document",
    )
    plan = build_plan(facts)
    emit(facts, plan, log_path, console=False)
    return {
        "source_fingerprint": fingerprint,
        "page_index": index,
        "page_width": facts.page_width,
        "page_height": facts.page_height,
        "input_gate": gate,
        "text_health": health,
        "regions": [region.to_dict() for region in facts.regions],
        "figures": [figure.to_dict() for figure in facts.figures],
        "decisions": [decision.to_dict() for decision in plan.decisions],
    }


def _blocks(page) -> list[SourceBlock]:
    """One PDF text block is one region. Blocks are not joined.

    A leading empty dingbat stays on the marker. It does not add a line box,
    so the region id matches a scan that only stored geometry.
    """
    height = float(page.rect.height)
    blocks: list[SourceBlock] = []
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        lines: list[LineBox] = []
        parts: list[str] = []
        for line in block.get("lines") or []:
            spans = line.get("spans") or []
            text = "".join(span.get("text", "") for span in spans).strip()
            if not text or not spans:
                continue
            x0 = min(float(span["bbox"][0]) for span in spans)
            x1 = max(float(span["bbox"][2]) for span in spans)
            y_down = min(float(span["bbox"][1]) for span in spans)
            lines.append(LineBox(x0, x1, height - y_down))
            parts.append(text)
        if lines:
            blocks.append(
                SourceBlock(
                    lines=tuple(lines),
                    source_text=" ".join(parts),
                    marker=first_marker(block.get("lines") or []),
                )
            )
    return blocks


def _figures(page) -> tuple[FigureBox, ...]:
    """Image rectangles, y-up. An image that fills the page is not a figure."""
    height = float(page.rect.height)
    width = float(page.rect.width)
    found: list[FigureBox] = []
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 1:
            continue
        bbox = block.get("bbox")
        if not bbox or len(bbox) < 4:
            continue
        x0, top_down, x1, bottom_down = (float(value) for value in bbox[:4])
        top = height - top_down
        bottom = height - bottom_down
        if top < bottom:
            bottom, top = top, bottom
        if x1 < x0:
            x0, x1 = x1, x0
        if x1 - x0 <= 1.0 or top - bottom <= 1.0:
            continue
        if x0 <= 2.0 and bottom <= 2.0 and x1 >= width - 2.0 and top >= height - 2.0:
            continue
        found.append(FigureBox(x0, bottom, x1, top))
    return tuple(found)
