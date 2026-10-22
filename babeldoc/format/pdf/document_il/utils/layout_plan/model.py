"""Read-only facts, regions, contributions, and a frozen layout plan.

Nothing in this module writes an IL box or a glyph.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Literal

_GEOMETRY_DECIMALS = 2


class BaseStrategy(str, Enum):
    """Mutually exclusive strategy stored on a frozen plan."""

    RECT_FLOW = "rect_flow"
    SHAPED_POCKET = "shaped_pocket"
    LIST = "list"
    FIXED_BOX = "fixed_box"
    OVERLAY = "overlay"
    PRESERVE = "preserve"


@dataclass(frozen=True, slots=True)
class LineBox:
    """One source line. ``y0`` grows upward."""

    x0: float
    x1: float
    y0: float


@dataclass(frozen=True, slots=True)
class Evidence:
    name: str
    detail: str


@dataclass(frozen=True, slots=True)
class MarkerEvidence:
    """First glyph a scanner could see, including an empty ToUnicode."""

    text: str
    font: str
    is_bullet: bool

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "font": self.font,
            "is_bullet": self.is_bullet,
        }


@dataclass(frozen=True, slots=True)
class Region:
    """Stable wrapper around one source block. Relations are candidates."""

    region_id: str
    page_index: int
    source_order: int
    role: str | None
    lines: tuple[LineBox, ...]
    text_on_photo: bool = False
    same_column_ids: tuple[str, ...] = ()
    above_id: str | None = None
    below_id: str | None = None
    source_text: str = ""
    marker: MarkerEvidence | None = None

    def to_dict(self) -> dict:
        return {
            "region_id": self.region_id,
            "page_index": self.page_index,
            "source_order": self.source_order,
            "role": self.role,
            "text_on_photo": self.text_on_photo,
            "line_count": len(self.lines),
            "same_column_ids": list(self.same_column_ids),
            "above_id": self.above_id,
            "below_id": self.below_id,
            "source_text": self.source_text,
            "marker": None if self.marker is None else self.marker.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class FigureBox:
    """One image or figure rectangle. ``y0`` is the bottom and ``y1`` the top.

    Y grows upward, same as a line box.
    """

    x0: float
    y0: float
    x1: float
    y1: float

    def to_dict(self) -> dict:
        return {"x0": self.x0, "y0": self.y0, "x1": self.x1, "y1": self.y1}


@dataclass(frozen=True, slots=True)
class LayoutFacts:
    """Observable page facts. No placement action is stored here."""

    source_fingerprint: str
    page_index: int
    page_width: float
    page_height: float
    input_gate: str
    text_health: float | None
    regions: tuple[Region, ...]
    figures: tuple[FigureBox, ...] = ()
    # ``document`` means ``source_fingerprint`` is this file's id.
    # ``unscoped`` means the id is only the page label. Those region
    # ids are not comparable across documents.
    identity_scope: str = "unscoped"

    def to_dict(self) -> dict:
        return {
            "source_fingerprint": self.source_fingerprint,
            "page_index": self.page_index,
            "page_width": self.page_width,
            "page_height": self.page_height,
            "input_gate": self.input_gate,
            "text_health": self.text_health,
            "identity_scope": self.identity_scope,
            "regions": [region.to_dict() for region in self.regions],
            "figures": [figure.to_dict() for figure in self.figures],
        }


@dataclass(frozen=True, slots=True)
class PlanContribution:
    plugin_id: str
    plugin_version: str
    target_region_id: str
    kind: Literal["base_strategy", "modifier"]
    value: str
    confidence: float
    priority: int
    evidence: tuple[Evidence, ...]
    fallback: str | None = None


@dataclass(frozen=True, slots=True)
class Rejection:
    plugin_id: str
    plugin_version: str
    value: str
    confidence: float
    reason: str

    def to_dict(self) -> dict:
        return {
            "plugin_id": self.plugin_id,
            "plugin_version": self.plugin_version,
            "value": self.value,
            "confidence": self.confidence,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class RegionDecision:
    region_id: str
    base_strategy: str
    modifiers: tuple[str, ...]
    confidence: float
    plugin_id: str | None
    plugin_version: str | None
    evidence: tuple[Evidence, ...]
    fallback: str | None
    rejected: tuple[Rejection, ...]
    # The named-paradigm grant. Empty status means this decision was
    # built before that grant ran. A later reader must not treat that
    # as a refusal. ``contour_residual`` is the claim residual, never
    # the base plugin's confidence.
    contour_plugin: str | None = None
    contour_version: str | None = None
    contour_residual: float | None = None
    contour_threshold: float | None = None
    contour_status: str = ""
    contour_reason: str | None = None
    contour_claims: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "region_id": self.region_id,
            "base_strategy": self.base_strategy,
            "modifiers": list(self.modifiers),
            "confidence": self.confidence,
            "plugin_id": self.plugin_id,
            "plugin_version": self.plugin_version,
            "evidence": [
                {"name": item.name, "detail": item.detail} for item in self.evidence
            ],
            "fallback": self.fallback,
            "rejected": [item.to_dict() for item in self.rejected],
            "contour_plugin": self.contour_plugin,
            "contour_version": self.contour_version,
            "contour_residual": self.contour_residual,
            "contour_threshold": self.contour_threshold,
            "contour_status": self.contour_status,
            "contour_reason": self.contour_reason,
            "contour_claims": list(self.contour_claims),
        }


@dataclass(frozen=True, slots=True)
class ColumnLink:
    """One rect_flow region in a frozen column.

    ``above_id`` is not this. A sidebar that only overlaps in x stays out.
    """

    region_id: str
    column_chain_id: str
    flow_next_id: str | None
    column_left: float
    column_right: float
    # Set when a figure sits against this column. Empty for a plain column.
    # ``free_side`` matches a pocket: ``right`` means the left edge is pinned.
    free_side: str = ""
    gap_slices: tuple[tuple[float, float, float], ...] = ()
    # White between the original text and the figure, from this page's scan.
    edge_gap: float = 0.0
    # Extra white above this paragraph, past one source line step.
    # The first paragraph in a chain is 0. Wrap width does not read this.
    paragraph_gap: float = 0.0

    def to_dict(self) -> dict:
        return {
            "region_id": self.region_id,
            "column_chain_id": self.column_chain_id,
            "flow_next_id": self.flow_next_id,
            "column_left": self.column_left,
            "column_right": self.column_right,
            "free_side": self.free_side,
            "gap_slices": [list(item) for item in self.gap_slices],
            "edge_gap": self.edge_gap,
            "paragraph_gap": self.paragraph_gap,
        }


@dataclass(frozen=True, slots=True)
class ListLink:
    """One list region in a frozen item chain.

    ``above_id`` is not this. A sidebar that only overlaps in x stays out.
    Bullets and numbers use the same link. ``body_left`` is the continuation
    edge when wrap lines already start to the right of the marker.
    """

    region_id: str
    list_chain_id: str
    flow_next_id: str | None
    marker_left: float
    column_right: float
    body_left: float

    def to_dict(self) -> dict:
        return {
            "region_id": self.region_id,
            "list_chain_id": self.list_chain_id,
            "flow_next_id": self.flow_next_id,
            "marker_left": self.marker_left,
            "column_right": self.column_right,
            "body_left": self.body_left,
        }


@dataclass(frozen=True, slots=True)
class PocketLink:
    """One shaped pocket beside a figure.

    ``free_side`` is the taper reader's side, frozen here. ``line_widths``
    are the gaps beside the figure at each English line, top line first.
    They are not the English line widths. ``slices`` are the same figure
    edges, ``(bottom, top, edge)``, so a Chinese line uses the edge at its
    own height. ``opening`` is the gap where no figure meets that height.
    ``edge_gap`` is the white the original text left before the figure.
    Typesetting reads this link and does not guess.
    """

    region_id: str
    free_side: str
    pin_edge: float
    line_widths: tuple[float, ...]
    opening: float = 0.0
    slices: tuple[tuple[float, float, float], ...] = ()
    edge_gap: float = 0.0

    def to_dict(self) -> dict:
        return {
            "region_id": self.region_id,
            "free_side": self.free_side,
            "pin_edge": self.pin_edge,
            "line_widths": list(self.line_widths),
            "opening": self.opening,
            "slices": [list(item) for item in self.slices],
            "edge_gap": self.edge_gap,
        }


@dataclass(frozen=True, slots=True)
class ContourLevel:
    """One measured sample of a contour, in page coordinates, y-up.

    ``top`` is the source line's top. The sample covers the gap down to
    the next sample, or one line pitch below the last. ``observed`` is
    that line's ink. ``available`` is space a fill opened or closed on
    these lines. Neither kind is a photo edge.
    """

    left: float
    right: float
    top: float
    kind: str = "observed"

    def to_dict(self) -> dict:
        return {
            "left": self.left,
            "right": self.right,
            "top": self.top,
            "kind": self.kind,
        }


def levels_from_edges(edges: Sequence[Sequence[float]]) -> tuple[ContourLevel, ...]:
    """Turn a stored line top into a level.

    Some fills still put the line top in a third number. That is a
    sample, read from here once. A query uses ``levels`` and does not
    decide two-dimensional versus three-dimensional by tuple length.
    Edges that omit the top contribute nothing.
    """
    if not edges or any(len(edge) < 3 for edge in edges):
        return ()
    return tuple(
        ContourLevel(float(edge[0]), float(edge[1]), float(edge[2]), "observed")
        for edge in edges
    )


@dataclass(frozen=True, slots=True)
class LineEdgeLink:
    """Scanned contour of one matched block. Top line first.

    ``edges`` stay the fill's x pairs so a consumer can still see what
    the fill wrote. Height lives on ``levels``. ``alignment`` is how the
    Chinese sits in those edges. ``flow`` is ``edge`` (the levels are
    the contour) or ``sentence`` (the edges are only the frame).
    """

    region_id: str
    edges: tuple[tuple[float, ...], ...]
    alignment: str = "left"
    flow: str = "edge"
    levels: tuple[ContourLevel, ...] | None = None

    def __post_init__(self) -> None:
        if self.levels is None:
            object.__setattr__(self, "levels", levels_from_edges(self.edges))

    def to_dict(self) -> dict:
        return {
            "region_id": self.region_id,
            "edges": [list(edge) for edge in self.edges],
            "alignment": self.alignment,
            "flow": self.flow,
            "levels": [level.to_dict() for level in self.levels],
        }


@dataclass(frozen=True, slots=True)
class SharedContour:
    """One granted contour, frozen before typesetting.

    ``digest`` is the source x pairs, not the fill's output. A later
    split looks the joined source edges up by that digest and uses
    ``edges`` as written. It does not call claim again. ``levels`` are
    the page-y samples typesetting queries.
    """

    digest: str
    edges: tuple[tuple[float, ...], ...]
    alignment: str
    flow: str
    plugin: str
    version: str
    residual: float
    threshold: float
    levels: tuple[ContourLevel, ...] | None = None

    def __post_init__(self) -> None:
        if self.levels is None:
            object.__setattr__(self, "levels", levels_from_edges(self.edges))

    def to_dict(self) -> dict:
        return {
            "digest": self.digest,
            "edges": [list(edge) for edge in self.edges],
            "alignment": self.alignment,
            "flow": self.flow,
            "plugin": self.plugin,
            "version": self.version,
            "residual": self.residual,
            "threshold": self.threshold,
            "levels": [level.to_dict() for level in self.levels],
        }


@dataclass(frozen=True, slots=True)
class ParagraphGapLink:
    """Scanned extra white above one body paragraph.

    ``paragraph_gap`` is the source white past one line step. Zero means
    the break was only one line step. Typesetting adds the rendered
    leading itself. This is not a column edge and not a list blank line.
    """

    region_id: str
    above_id: str
    paragraph_gap: float = 0.0

    def to_dict(self) -> dict:
        return {
            "region_id": self.region_id,
            "above_id": self.above_id,
            "paragraph_gap": self.paragraph_gap,
        }


@dataclass(frozen=True, slots=True)
class LayoutPlan:
    """Immutable decisions for one page. Typesetting must not rebuild it."""

    source_fingerprint: str
    page_index: int
    input_gate: str
    decisions: tuple[RegionDecision, ...]
    column_links: tuple[ColumnLink, ...] = ()
    list_links: tuple[ListLink, ...] = ()
    pocket_links: tuple[PocketLink, ...] = ()
    line_edge_links: tuple[LineEdgeLink, ...] = ()
    paragraph_gap_links: tuple[ParagraphGapLink, ...] = ()
    identity_scope: str = "unscoped"
    shared_contours: tuple[SharedContour, ...] = ()

    def to_dict(self) -> dict:
        return {
            "source_fingerprint": self.source_fingerprint,
            "page_index": self.page_index,
            "input_gate": self.input_gate,
            "identity_scope": self.identity_scope,
            "decisions": [decision.to_dict() for decision in self.decisions],
            "column_links": [link.to_dict() for link in self.column_links],
            "list_links": [link.to_dict() for link in self.list_links],
            "pocket_links": [link.to_dict() for link in self.pocket_links],
            "line_edge_links": [link.to_dict() for link in self.line_edge_links],
            "paragraph_gap_links": [
                link.to_dict() for link in self.paragraph_gap_links
            ],
            "shared_contours": [item.to_dict() for item in self.shared_contours],
        }


def edge_digest(lines: Sequence[Sequence[float]]) -> str:
    """Identity of source x pairs. Y is not part of it.

    Typesetting stores ``(x0, x1)`` and looks a shared contour up with
    those pairs. The same pairs hash to the same digest with or without
    the line's height.
    """
    parts = [
        f"{float(line[0]):.{_GEOMETRY_DECIMALS}f},"
        f"{float(line[1]):.{_GEOMETRY_DECIMALS}f}"
        for line in lines
    ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def geometry_digest(lines: tuple[LineBox, ...]) -> str:
    parts = [
        f"{line.x0:.{_GEOMETRY_DECIMALS}f},"
        f"{line.x1:.{_GEOMETRY_DECIMALS}f},"
        f"{line.y0:.{_GEOMETRY_DECIMALS}f}"
        for line in lines
    ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def make_region_id(
    source_fingerprint: str,
    page_index: int,
    source_order: int,
    lines: tuple[LineBox, ...],
) -> str:
    """Stable id. The same geometry hashes to the same id across runs."""
    payload = f"{source_fingerprint}|{page_index}|{source_order}|{geometry_digest(lines)}"
    return hashlib.sha256(payload.encode()).hexdigest()[:32]
