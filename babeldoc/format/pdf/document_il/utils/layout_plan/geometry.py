"""Shared column geometry. Thresholds stay in ``placement_paradigm``."""

from __future__ import annotations

from babeldoc.format.pdf.document_il.utils.layout_plan.model import Region
from babeldoc.format.pdf.document_il.utils.placement_paradigm import (
    features_are_stable_column,
)
from babeldoc.format.pdf.document_il.utils.placement_paradigm import features_are_taper
from babeldoc.format.pdf.document_il.utils.placement_paradigm import (
    read_column_features,
)
from babeldoc.format.pdf.document_il.utils.placement_paradigm import taper_free_side

# Scanner blocks have no role yet. Known non-body roles stay preserve.
_GEOMETRY_ROLES = frozenset({None, "body", "wrap_column"})


def geometry_eligible(region: Region) -> bool:
    """True when a column plugin may look at this region."""
    if region.text_on_photo:
        return False
    return region.role in _GEOMETRY_ROLES


def feature_lines(region: Region):
    boxes = [(line.x0, line.x1, line.y0) for line in region.lines]
    return read_column_features(boxes)


def is_taper(region: Region) -> bool:
    if not region.lines:
        return False
    return features_are_taper(feature_lines(region))


def is_stable_column(region: Region) -> bool:
    if len(region.lines) < 2:
        return False
    return features_are_stable_column(feature_lines(region))


def free_side(region: Region) -> str | None:
    if not region.lines:
        return None
    return taper_free_side(feature_lines(region))
