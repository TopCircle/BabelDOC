"""Shared column geometry. Thresholds stay in ``placement_paradigm``."""

from __future__ import annotations

import re

from babeldoc.format.pdf.document_il.utils.layout_plan.model import Region
from babeldoc.format.pdf.document_il.utils.placement_paradigm import (
    features_are_stable_column,
)
from babeldoc.format.pdf.document_il.utils.placement_paradigm import features_are_taper
from babeldoc.format.pdf.document_il.utils.placement_paradigm import (
    read_column_features,
)
from babeldoc.format.pdf.document_il.utils.placement_paradigm import taper_free_side

_TOC_HEADER_RE = re.compile(
    r"\b(table\s+of\s+contents|contents|directory|table\s+des\s+mati[èe]res|inhaltsverzeichnis|目录)\b",
    re.IGNORECASE,
)
_TOC_LEADER_RE = re.compile(
    r"(?:\.{3,}|_{3,}|\-{3,}|\.(?:\s*\.){3,})\s*\d+",
    re.MULTILINE,
)

# Scanner blocks have no role yet. Known non-body roles stay preserve.
_GEOMETRY_ROLES = frozenset({None, "body", "wrap_column", "toc"})
# A photo caption stays out. A body may be claimed only when both
# edges have already opened by this much. The claim still decides.
_PHOTO_BODY_LINES = 5
_PHOTO_OPEN = 24.0


def is_toc_region(facts, region: Region) -> bool:
    """True when the region belongs to a Table of Contents / Directory."""
    if region.role == "toc":
        return True
    text = (region.source_text or "").strip()
    if not text:
        return False
    if _TOC_LEADER_RE.search(text):
        return True
    if _TOC_HEADER_RE.search(text):
        return True
    for r in getattr(facts, "regions", ()) or ():
        r_text = (r.source_text or "").strip()
        if _TOC_HEADER_RE.search(r_text) and len(r_text.split()) <= 6:
            if len(region.lines) >= 2:
                return True
    return False


def geometry_eligible(region: Region) -> bool:
    """True when a column plugin may look at this region."""
    if region.text_on_photo and not _opens_on_photo(region):
        return False
    return region.role in _GEOMETRY_ROLES


def _opens_on_photo(region: Region) -> bool:
    """A backdrop body whose edges open downward.

    A caption, a column that only narrows, and text sitting on the
    figure stay out. The short last line is not the opening.
    """
    lines = region.lines
    if region.role not in _GEOMETRY_ROLES or len(lines) < _PHOTO_BODY_LINES:
        return False
    body = lines[:-1]
    left0 = float(lines[0].x0)
    right0 = float(lines[0].x1)
    if min(float(line.x0) for line in body) > left0 - _PHOTO_OPEN:
        return False
    if max(float(line.x1) for line in body) < right0 + _PHOTO_OPEN:
        return False
    return True


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
