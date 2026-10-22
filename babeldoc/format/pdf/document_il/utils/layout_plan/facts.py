"""Build layout facts from source blocks. This does not read or write the IL."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace

from babeldoc.format.pdf.document_il.utils.layout_plan.model import FigureBox
from babeldoc.format.pdf.document_il.utils.layout_plan.model import LayoutFacts
from babeldoc.format.pdf.document_il.utils.layout_plan.model import LineBox
from babeldoc.format.pdf.document_il.utils.layout_plan.model import MarkerEvidence
from babeldoc.format.pdf.document_il.utils.layout_plan.model import Region
from babeldoc.format.pdf.document_il.utils.layout_plan.model import make_region_id

_X_OVERLAP = 0.35


@dataclass(frozen=True, slots=True)
class SourceBlock:
    """One source text block before ids and relations are assigned."""

    lines: tuple[LineBox, ...]
    role: str | None = None
    text_on_photo: bool = False
    source_text: str = ""
    marker: MarkerEvidence | None = None


def build_facts(
    *,
    source_fingerprint: str,
    page_index: int,
    page_width: float,
    page_height: float,
    input_gate: str,
    text_health: float | None,
    blocks: list[SourceBlock],
    figures: tuple[FigureBox, ...] = (),
    identity_scope: str = "unscoped",
) -> LayoutFacts:
    """One block is one source region. Blocks are not merged.

    Text and marker evidence are not part of the region id.
    """
    drafted: list[Region] = []
    for order, block in enumerate(blocks):
        drafted.append(
            Region(
                region_id=make_region_id(
                    source_fingerprint, page_index, order, block.lines
                ),
                page_index=page_index,
                source_order=order,
                role=block.role,
                lines=block.lines,
                text_on_photo=block.text_on_photo,
                source_text=block.source_text,
                marker=block.marker,
            )
        )
    regions = tuple(_with_relations(drafted))
    return LayoutFacts(
        source_fingerprint=source_fingerprint,
        page_index=page_index,
        page_width=page_width,
        page_height=page_height,
        input_gate=input_gate,
        text_health=text_health,
        regions=regions,
        figures=tuple(figures),
        identity_scope=identity_scope,
    )


def _with_relations(regions: list[Region]) -> list[Region]:
    linked: list[Region] = []
    for region in regions:
        same = tuple(
            other.region_id
            for other in regions
            if other.region_id != region.region_id and _x_overlap(region, other)
        )
        above = _vertical_neighbor(region, regions, higher=True)
        below = _vertical_neighbor(region, regions, higher=False)
        linked.append(
            replace(
                region,
                same_column_ids=same,
                above_id=None if above is None else above.region_id,
                below_id=None if below is None else below.region_id,
            )
        )
    return linked


def _span(region: Region) -> tuple[float, float, float, float]:
    if not region.lines:
        return (0.0, 0.0, 0.0, 0.0)
    return (
        min(line.x0 for line in region.lines),
        max(line.x1 for line in region.lines),
        min(line.y0 for line in region.lines),
        max(line.y0 for line in region.lines),
    )


def _x_overlap(left: Region, right: Region) -> bool:
    ax0, ax1, _ay0, _ay1 = _span(left)
    bx0, bx1, _by0, _by1 = _span(right)
    overlap = min(ax1, bx1) - max(ax0, bx0)
    narrow = max(1.0, min(ax1 - ax0, bx1 - bx0))
    return overlap >= _X_OVERLAP * narrow


def _vertical_neighbor(
    region: Region, regions: list[Region], *, higher: bool
) -> Region | None:
    _x0, _x1, y0, y1 = _span(region)
    best: Region | None = None
    best_gap = None
    for other in regions:
        if other.region_id == region.region_id or not _x_overlap(region, other):
            continue
        _ox0, _ox1, oy0, oy1 = _span(other)
        if higher:
            if oy0 < y1:
                continue
            gap = oy0 - y1
        else:
            if oy1 > y0:
                continue
            gap = y0 - oy1
        if best_gap is None or gap < best_gap:
            best = other
            best_gap = gap
    return best
