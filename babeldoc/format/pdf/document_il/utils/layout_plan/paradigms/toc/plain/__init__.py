"""Table of Contents / Directory plain layout paradigm.

A table of contents block has structured directory lines that must not
be treated as regular body paragraphs or reflow-merged.
"""

from __future__ import annotations

from collections.abc import Sequence

from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.contract import (
    BlockEdges,
)

THRESHOLD: float = 8.0
FLOW = "edge"
ALIGNMENT = "left"


def claim(edges: BlockEdges, lines: Sequence[Sequence[float]]) -> float | None:
    """Claim when the edges marker indicates a table of contents."""
    if edges.marker != "toc":
        return None
    if len(lines) < 2:
        return None
    return 0.0


def fill(lines: Sequence[Sequence[float]]) -> tuple[tuple[float, ...], ...]:
    """Keep each TOC entry at its scanned line position with top coordinate."""
    edges = []
    for line in lines:
        edge = [float(line[0]), float(line[1])]
        if len(line) >= 3:
            edge.append(float(line[2]))
        edges.append(tuple(edge))
    return tuple(edges)
