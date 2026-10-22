"""Measurements of one sealed text block.

The numbers are edges, a marker, and figure overlap. This module does
not name a paradigm and does not build a layout plan.
"""

from __future__ import annotations

from dataclasses import dataclass

from babeldoc.format.pdf.document_il.utils.layout_plan.geometry import feature_lines
from babeldoc.format.pdf.document_il.utils.layout_plan.model import FigureBox
from babeldoc.format.pdf.document_il.utils.layout_plan.model import Region
from babeldoc.format.pdf.document_il.utils.layout_plan.plugins.list_flow import (
    has_list_evidence,
)


@dataclass(frozen=True, slots=True)
class BlockMeasure:
    """Edges of every line, plus the shared column features of the full lines."""

    full_count: int
    left_range: float
    right_range: float
    left_monotone: float
    right_monotone: float
    marker: str
    figures: int
    left: tuple[float, float]
    right: tuple[float, float]
    y: tuple[float, float]


def measure_region(
    region: Region, figures: tuple[FigureBox, ...] = ()
) -> BlockMeasure:
    """Read one region. Short lines stay in the edge span.

    Column ranges come from the shared feature reader. They are not a
    paradigm name, and they do not drop lines from the block.
    """
    lines = region.lines
    lefts = [line.x0 for line in lines]
    rights = [line.x1 for line in lines]
    tops = [line.y0 for line in lines]
    features = feature_lines(region)
    return BlockMeasure(
        full_count=features.full_count,
        left_range=features.left_range,
        right_range=features.right_range,
        left_monotone=features.left_monotone,
        right_monotone=features.right_monotone,
        marker=_marker(region),
        figures=_figures_on(lines, figures),
        left=_ends(lefts),
        right=_ends(rights),
        y=_ends(tops),
    )


def _marker(region: Region) -> str:
    marker = region.marker
    if marker is not None and marker.is_bullet:
        return "bullet"
    if has_list_evidence(region):
        return "serial"
    return "none"


def _figures_on(lines, figures: tuple[FigureBox, ...]) -> int:
    if not lines:
        return 0
    left = min(line.x0 for line in lines)
    right = max(line.x1 for line in lines)
    low = min(line.y0 for line in lines)
    high = max(line.y0 for line in lines)
    count = 0
    for figure in figures:
        if figure.x1 < left or figure.x0 > right:
            continue
        if figure.y1 < low or figure.y0 > high:
            continue
        count += 1
    return count


def _ends(values: list[float]) -> tuple[float, float]:
    if not values:
        return (0.0, 0.0)
    return (min(values), max(values))
