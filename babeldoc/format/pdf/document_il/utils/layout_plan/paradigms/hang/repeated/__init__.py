"""Plain lines return to the left edge more than once, at one indent."""

from __future__ import annotations

from collections.abc import Sequence

from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.contract import (
    BlockEdges,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.outline import hang

THRESHOLD: float = 8.0


def claim(edges: BlockEdges, lines: Sequence[Sequence[float]]) -> float | None:
    """Residual from this walk."""
    return hang(edges, lines, "repeated")
