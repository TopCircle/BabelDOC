"""Keep margin vector-icon curves aligned with their anchored paragraph's first line."""

from __future__ import annotations

from dataclasses import dataclass

from babeldoc.format.pdf.document_il.utils.region_skip import is_chrome_paragraph
from babeldoc.format.pdf.document_il.utils.same_baseline import _composition_chars

_MAX_ICON_SIZE_PT = 40.0
_MIN_ICON_SIZE_PT = 2.0
_MAX_VERTICAL_DIST_PT = 16.0
_LEFT_GUTTER_REACH_PT = 48.0
_MARKER_ZONE_RIGHT_PT = 44.0
_PAGE_ANCHORS: dict[int, tuple[object, list[IconCurveAnchor]]] = {}


@dataclass
class IconCurveAnchor:
    """Pairs a paragraph's baseline first-line midpoint with bound vector-icon curves."""

    paragraph: object
    baseline_mid_y: float
    curves: list[object]
    applied_dy: float = 0.0


def _estimated_first_line_height(paragraph, box_height: float) -> float:
    metrics = getattr(paragraph, "reference_metrics", None)
    font_size = getattr(metrics, "font_size", None)
    if font_size is None:
        style = getattr(paragraph, "pdf_style", None)
        font_size = getattr(style, "font_size", None)
    try:
        fs = float(font_size) if font_size is not None else 11.0
    except (TypeError, ValueError):
        fs = 11.0
    if fs <= 1.0:
        fs = 11.0
    return min(box_height, fs * 1.25)


def _paragraph_first_line_span(paragraph) -> tuple[float, float, float, float] | None:
    """Return ``(mid_y, top_y, bottom_y, left_x)`` of *paragraph*'s highest line."""
    raw: list[tuple[float, float, float]] = []
    for comp in getattr(paragraph, "pdf_paragraph_composition", None) or []:
        for char in _composition_chars(comp):
            box = getattr(char, "box", None)
            if box is None or None in (box.x, box.y, box.y2):
                continue
            if float(box.y2) - float(box.y) <= 1.0:
                continue
            raw.append((float(box.x), float(box.y), float(box.y2)))
    if not raw:
        box = getattr(paragraph, "box", None)
        if box is None or None in (box.x, box.y, box.y2):
            return None
        top_y = float(box.y2)
        box_y = float(box.y)
        box_h = top_y - box_y
        if box_h <= 1.0:
            return None
        line_h = _estimated_first_line_height(paragraph, box_h)
        bottom_y = top_y - line_h
        return top_y - line_h / 2.0, top_y, bottom_y, float(box.x)
    top_y = max(item[2] for item in raw)
    first_line = [item for item in raw if top_y - item[2] <= 2.0]
    bottom_y = min(item[1] for item in first_line)
    left_x = min(item[0] for item in first_line)
    return (top_y + bottom_y) / 2.0, top_y, bottom_y, left_x


def _is_candidate_icon_curve(curve) -> bool:
    """Return True if *curve* is a compact non-background vector icon."""
    if getattr(curve, "passthrough_paint", False):
        return False
    box = getattr(curve, "box", None)
    if box is None or None in (box.x, box.x2, box.y, box.y2):
        return False
    w = float(box.x2) - float(box.x)
    h = float(box.y2) - float(box.y)
    return (
        _MIN_ICON_SIZE_PT <= w <= _MAX_ICON_SIZE_PT
        and _MIN_ICON_SIZE_PT <= h <= _MAX_ICON_SIZE_PT
    )


def _icon_match_distance(curve, span: tuple[float, float, float, float]) -> float | None:
    """Return vertical distance if *curve* sits in *span*'s left margin or wraps its start."""
    line_mid_y, line_top, line_bottom, line_left = span
    box = curve.box
    cx, cx2, cy, cy2 = float(box.x), float(box.x2), float(box.y), float(box.y2)
    if cy > line_top + 6.0 or cy2 < line_bottom - 6.0:
        return None
    curve_mid_y = (cy + cy2) / 2.0
    dist = abs(curve_mid_y - line_mid_y)
    if dist > _MAX_VERTICAL_DIST_PT:
        return None
    if cx < line_left - _LEFT_GUTTER_REACH_PT or cx2 > line_left + _MARKER_ZONE_RIGHT_PT:
        return None
    in_left_gutter = cx2 <= line_left + 6.0
    wraps_leading_marker = cx <= line_left + 4.0
    if not (in_left_gutter or wraps_leading_marker):
        return None
    return dist


def capture_icon_curve_anchors(page) -> list[IconCurveAnchor]:
    """Bind standalone small bullet/badge curves on *page* to their source paragraph."""
    curves = list(getattr(page, "pdf_curve", None) or [])
    paragraphs = list(getattr(page, "pdf_paragraph", None) or [])
    if not curves or not paragraphs:
        return []

    para_spans: list[tuple[object, tuple[float, float, float, float]]] = []
    for paragraph in paragraphs:
        if is_chrome_paragraph(paragraph):
            continue
        span = _paragraph_first_line_span(paragraph)
        if span is not None:
            para_spans.append((paragraph, span))
    if not para_spans:
        return []

    by_para: dict[int, IconCurveAnchor] = {}
    for curve in curves:
        if not _is_candidate_icon_curve(curve):
            continue
        curve_xobj = getattr(curve, "xobj_id", None)
        best_para = None
        best_span = None
        best_dist = None
        tied = False
        for paragraph, span in para_spans:
            if getattr(paragraph, "xobj_id", None) != curve_xobj:
                continue
            dist = _icon_match_distance(curve, span)
            if dist is None:
                continue
            if best_dist is None or dist < best_dist - 0.5:
                best_para = paragraph
                best_span = span
                best_dist = dist
                tied = False
            elif abs(dist - best_dist) <= 0.5:
                tied = True
        if best_para is None or best_span is None or tied:
            continue
        pid = id(best_para)
        anchor = by_para.get(pid)
        if anchor is None:
            anchor = IconCurveAnchor(
                paragraph=best_para,
                baseline_mid_y=best_span[0],
                curves=[],
            )
            by_para[pid] = anchor
        anchor.curves.append(curve)

    return list(by_para.values())


def _shift_curve_y(curve, dy: float) -> None:
    """Translate *curve* vertically in page coordinates by *dy* pt."""
    if abs(dy) < 1e-6:
        return
    rt = list(getattr(curve, "relocation_transform", None) or [])
    if len(rt) == 6:
        rt[5] = float(rt[5]) + dy
    else:
        rt = [1.0, 0.0, 0.0, 1.0, 0.0, float(dy)]
    curve.relocation_transform = rt
    box = getattr(curve, "box", None)
    if box is not None:
        if box.y is not None:
            box.y = float(box.y) + dy
        if box.y2 is not None:
            box.y2 = float(box.y2) + dy


def sync_icon_curve_anchors(anchors: list[IconCurveAnchor]) -> None:
    """Shift each bound vector icon to follow its paragraph's final first-line Y."""
    for anchor in anchors:
        span = _paragraph_first_line_span(anchor.paragraph)
        if span is None:
            continue
        total_dy = span[0] - anchor.baseline_mid_y
        step_dy = total_dy - anchor.applied_dy
        if abs(step_dy) < 0.5:
            continue
        for curve in anchor.curves:
            _shift_curve_y(curve, step_dy)
        anchor.applied_dy = total_dy


def register_page_icon_anchors(page, anchors: list[IconCurveAnchor]) -> None:
    """Store *anchors* for post-layout resync when *page* moves further."""
    if anchors:
        _PAGE_ANCHORS[id(page)] = (page, anchors)


def resync_page_icon_curves(page, *, release: bool = False) -> None:
    """Re-apply icon-curve alignment for *page* after post-typeset paragraph shifts."""
    entry = _PAGE_ANCHORS.pop(id(page), None) if release else _PAGE_ANCHORS.get(id(page))
    if entry is None or entry[0] is not page:
        return
    sync_icon_curve_anchors(entry[1])
