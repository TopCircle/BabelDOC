"""Fill one sentence the seal split beside a figure.

When the two halves together match a contour, the words go into that
contour and the typesetter fills it from the top. Otherwise only the
words that fit on the open line move up, and the indented box stays.
A finished sentence stays put. A narrower contour tip stays put. A
block that already has its own contour stays put. A column, list, or
pocket stays put. This does not name a paradigm and does not change
the seal.
"""

from __future__ import annotations

import logging

from babeldoc.format.pdf.document_il.utils.cjk_kinsoku import is_cjk_line_end_forbidden
from babeldoc.format.pdf.document_il.utils.paragraph_split_policy import (
    text_ends_sentence,
)

logger = logging.getLogger(__name__)

# One body line, plus a little slack for a box that ends on the baseline.
_MAX_GAP = 22.0
_MIN_GAP = -4.0
# Same step and skip the typesetter uses once a box is too short for 1.0.
_LINE_SKIP = 1.5
_SCALE_STEP = 0.05
_MIN_SCALE = 0.55
# The existing same-column joiner already accepts 8pt. This is a step.
_MIN_STEP = 24.0
_RIGHT_SLACK = 36.0
_FIGURE_SLACK = 16.0
_MIN_OVERLAP = 8.0
_FULL_PAGE = 0.85
# Marks the typesetter may paint past the measure without opening a line.
# 时/年 are line-start forbidden too, but they are not hung: pulling one
# that does not fit wraps a new line onto the paragraph below.
_HUNG_PUNCT = frozenset(
    "，。．、：；！？‼⁇"
    "”’」』"
    ")]}）〕〉】〗］｝"
    "》"
    "～-–—·・‧/／⁄"
)


def continue_indented_sentences(page, glyph_widths) -> int:
    """Move a prefix of the indented paragraph onto the open line above it."""
    paragraphs = list(getattr(page, "pdf_paragraph", None) or [])
    figures = _side_figures(page)
    if len(paragraphs) < 2 or not figures:
        return 0
    # A straight contour may still fill its open last line. A column,
    # list, or pocket stays put. The paragraph below stays put when it
    # already has its own contour.
    fixed = _column_ids(page)
    anchored = _anchored(page)
    used: set[int] = set()
    emptied: set[int] = set()
    moved = 0
    filled = 0
    ordered = sorted(
        (item for item in paragraphs if _has_box(item)),
        key=lambda item: -float(item.box.y2),
    )
    for upper in ordered:
        if id(upper) in used or not _open_sentence(upper, fixed):
            continue
        lower = _nearest_indent(upper, paragraphs, anchored, figures, used)
        if lower is None:
            continue
        if _fill_shared_frame(page, upper, lower):
            used.add(id(upper))
            used.add(id(lower))
            emptied.add(id(lower))
            filled += 1
            continue
        if not _move_prefix(upper, lower, glyph_widths, page):
            continue
        used.add(id(upper))
        used.add(id(lower))
        moved += 1
        if not _visible_text(lower):
            emptied.add(id(lower))
    if emptied:
        page.pdf_paragraph = [
            item for item in paragraphs if id(item) not in emptied
        ]
    if filled:
        logger.info("filled %s shared frame(s)", filled)
    if moved:
        logger.info("continued %s indented sentence(s)", moved)
    return moved + filled


def _fill_shared_frame(page, upper, lower) -> bool:
    """Put both halves into the contour the plan already granted.

    This does not call claim. The contour was frozen with the source
    x pairs. A refused half stays two paragraphs.
    """
    if _closed_gate(page):
        return False
    if _has_line_edges(page, lower) or _upper_contour_blocks(page, upper):
        return False
    if _refused(page, upper) or _refused(page, lower):
        return False
    edges = _joined_edges(upper, lower)
    if edges is None:
        return False
    found = _shared_contour(page, edges)
    if found is None or not found.edges:
        return False
    if not _take_all(upper, lower):
        return False
    _cover(upper, lower, found.edges)
    _install_frame(page, upper, found)
    return True


def _refused(page, paragraph) -> bool:
    plan = getattr(page, "layout_plan", None)
    region_id = getattr(paragraph, "layout_region_id", None)
    if plan is None or not region_id:
        return False
    for decision in getattr(plan, "decisions", ()) or ():
        if decision.region_id != region_id:
            continue
        return getattr(decision, "contour_status", "") == "refused"
    return False


def _shared_contour(page, edges):
    from babeldoc.format.pdf.document_il.utils.layout_plan.model import edge_digest

    plan = getattr(page, "layout_plan", None)
    if plan is None:
        return None
    digest = edge_digest(edges)
    for contour in getattr(plan, "shared_contours", ()) or ():
        if contour.digest == digest:
            return contour
    return None


def _has_line_edges(page, paragraph) -> bool:
    from babeldoc.format.pdf.document_il.utils.layout_plan.line_edges import (
        line_edges_for,
    )

    link = line_edges_for(page, paragraph)
    return bool(link is not None and link.edges)


def _joined_edges(upper, lower) -> list[tuple[float, float]] | None:
    """Source line edges, top half then the indented half."""
    above = _source_edges(upper)
    below = _source_edges(lower)
    if above is None or below is None:
        return None
    return above + below


def _upper_contour_blocks(page, paragraph) -> bool:
    """A sentence-flow frame or a narrow tip is already its own contour."""
    from babeldoc.format.pdf.document_il.utils.layout_plan.line_edges import (
        line_edges_for,
    )

    link = line_edges_for(page, paragraph)
    edges = getattr(link, "edges", None) if link is not None else None
    if not edges:
        return False
    if getattr(link, "flow", "edge") == "sentence":
        return True
    caps = [float(edge[1]) - float(edge[0]) for edge in edges]
    return caps[-1] < max(caps) - 8.0


def _closed_gate(page) -> bool:
    """A spread, image-only, or bad-encoding page is not classified.

    A page that never got a plan is still open. Attach is what closes it.
    """
    plan = getattr(page, "layout_plan", None)
    if plan is None:
        return False
    gate = getattr(plan, "input_gate", None)
    return bool(gate) and gate != "single_page"


def _source_edges(paragraph) -> list[tuple[float, float]] | None:
    """Scanned line edges, top first.

    Saved widths are lengths. Anchoring them at the box left pulls a
    line that starts further right across the figure.
    """
    stored = getattr(paragraph, "source_line_edges", None)
    if not stored:
        return None
    return _pairs(stored)


def _pairs(items) -> list[tuple[float, float]] | None:
    edges: list[tuple[float, float]] = []
    for item in items:
        left = float(item[0])
        right = float(item[1])
        if right <= left + 1.0:
            return None
        edges.append((left, right))
    return edges or None


def _take_all(upper, lower) -> bool:
    upper_text = _visible_text(upper)
    lower_text = _visible_text(lower)
    if not upper_text or not lower_text:
        return False
    _set_visible(upper, upper_text + lower_text)
    return _visible_text(upper) == upper_text + lower_text


def _cover(upper, lower, edges) -> None:
    """The box holds every source line. The scale search starts at full size."""
    upper.box.x = min(float(edge[0]) for edge in edges)
    upper.box.x2 = max(float(edge[1]) for edge in edges)
    upper.box.y = min(float(upper.box.y), float(lower.box.y))
    upper.box.y2 = max(float(upper.box.y2), float(lower.box.y2))
    upper.first_line_indent = 0
    upper.optimal_scale = 1.0
    _remember_widths(upper, edges)


def _remember_widths(paragraph, edges) -> None:
    metrics = getattr(paragraph, "reference_metrics", None)
    if metrics is None:
        return
    widths = [float(edge[1]) - float(edge[0]) for edge in edges]
    average = sum(widths) / len(widths)
    metrics.per_line_widths = widths
    metrics.line_count = len(widths)
    metrics.avg_line_width = average
    metrics.last_line_width = widths[-1]
    metrics.last_line_ratio = widths[-1] / average if average else 1.0


def _install_frame(page, paragraph, found) -> None:
    from dataclasses import replace

    from babeldoc.format.pdf.document_il.utils.layout_plan.model import LayoutPlan
    from babeldoc.format.pdf.document_il.utils.layout_plan.model import LineEdgeLink

    previous = getattr(paragraph, "layout_region_id", None) or None
    region_id = previous or f"shared-frame-{id(paragraph)}"
    paragraph.layout_region_id = region_id
    paragraph.alignment = found.alignment
    plan = getattr(page, "layout_plan", None)
    if plan is None:
        plan = LayoutPlan(
            source_fingerprint="frame",
            page_index=int(getattr(page, "page_number", None) or 0),
            input_gate="single_page",
            decisions=(),
        )
    kept = [
        item
        for item in (getattr(plan, "line_edge_links", None) or ())
        if previous is None or item.region_id != previous
    ]
    decisions = _grant_shared(plan, region_id, found)
    page.layout_plan = replace(
        plan,
        decisions=decisions,
        line_edge_links=(
            *kept,
            LineEdgeLink(
                region_id,
                found.edges,
                found.alignment,
                found.flow,
                getattr(found, "levels", None),
            ),
        ),
    )


def _grant_shared(plan, region_id: str, found):
    """Record the frozen contour on the decision that owns this frame.

    Without this stamp, a reader that hides non-matched decisions would
    drop the link this function just installed.
    """
    from dataclasses import replace

    granted = []
    for decision in getattr(plan, "decisions", ()) or ():
        if decision.region_id != region_id:
            granted.append(decision)
            continue
        granted.append(
            replace(
                decision,
                contour_plugin=found.plugin,
                contour_version=found.version,
                contour_residual=found.residual,
                contour_threshold=found.threshold,
                contour_status="matched",
                contour_reason="shared_contour",
                contour_claims=(),
            )
        )
    return tuple(granted)


def _move_prefix(upper, lower, glyph_widths, page) -> bool:
    try:
        upper_glyphs = list(glyph_widths(upper) or [])
        lower_glyphs = list(glyph_widths(lower) or [])
    except Exception:
        logger.info("indented sentence widths failed", exc_info=True)
        return False
    if not _matches(upper, upper_glyphs) or not _matches(lower, lower_glyphs):
        logger.info("indented sentence glyph string mismatch")
        return False
    measure = _measure(upper)
    caps = _edge_caps(page, upper)
    if caps == []:
        logger.info("indented sentence contour tail stays")
        return False
    if measure < 24.0 and not caps:
        logger.info("indented sentence measure too narrow")
        return False
    indent = float(getattr(upper, "first_line_indent", 0) or 0)
    raw_widths = [width for _char, width in upper_glyphs]
    height = float(upper.box.y2) - float(upper.box.y)
    placed, scale = _at_placed_scale(
        raw_widths,
        measure,
        indent,
        caps,
        height,
        _median(raw_widths),
    )
    room = _room(placed, measure, indent, caps)
    median = _median(placed)
    if median <= 0.0 or room < 2.0 * median:
        logger.info("indented sentence open line has no room")
        return False
    fitting = (
        lower_glyphs
        if scale >= 1.0
        else [(char, width * scale) for char, width in lower_glyphs]
    )
    take = _prefix_count(fitting, room)
    if take < 2:
        logger.info("indented sentence prefix shorter than two glyphs")
        return False
    upper_text = "".join(char for char, _width in upper_glyphs)
    lower_text = "".join(char for char, _width in lower_glyphs)
    _set_visible(upper, upper_text + lower_text[:take])
    _set_visible(lower, lower_text[take:])
    return True


def _prefix_count(glyphs, room: float) -> int:
    """How many glyphs fit in ``room``, hanging one closing mark."""
    taken = 0
    used = 0.0
    for index, (_char, width) in enumerate(glyphs):
        if used + width > room + 1e-6:
            break
        taken = index + 1
        used += width
    taken = _hang_closing_mark(glyphs, taken)
    while taken > 0 and is_cjk_line_end_forbidden(glyphs[taken - 1][0]):
        taken -= 1
    return _hang_closing_mark(glyphs, taken)


def _hang_closing_mark(glyphs, taken: int) -> int:
    """Keep one comma or period on this line. Leave 时/年 below."""
    if taken <= 0 or taken >= len(glyphs):
        return taken
    if glyphs[taken][0] in _HUNG_PUNCT:
        return taken + 1
    return taken


def _at_placed_scale(widths, measure, indent, caps, height, em):
    """Widths at the scale whose last line still clears this box.

    The typesetter tries 1.0, then steps down by 0.05. A full em overfills
    a two-line body once the box bottom has been lifted off the paragraph
    below, and the open line is then wider than that em.
    """
    lines = _lines_used(widths, measure, indent, caps)
    scale = _advance_scale(height, em, lines)
    if scale >= 1.0:
        return widths, 1.0
    placed = [width * scale for width in widths]
    again = _lines_used(placed, measure, indent, caps)
    if again != lines:
        scale = _advance_scale(height, em, again)
        placed = [width * scale for width in widths]
    return placed, scale


def _advance_scale(height: float, em: float, lines: int) -> float:
    """Largest 0.05 step that keeps ``lines`` inside ``height``."""
    if height <= 0.0 or em <= 0.0 or lines < 1:
        return 1.0
    scale = 1.0
    while scale >= _MIN_SCALE:
        drop = em * scale * (1.0 + (lines - 1) * _LINE_SKIP)
        if drop <= height + 1e-6:
            return scale
        scale = round(scale - _SCALE_STEP, 2)
    return _MIN_SCALE


def _lines_used(widths, measure, indent, caps) -> int:
    """How many lines these widths need. One past the contour means stop."""
    limits = [float(cap) for cap in caps] if caps else None
    line = 0
    cap = _line_cap(limits, measure, line, indent)
    used = 0.0
    for width in widths:
        if used > 0.0 and used + width > cap + 1e-6:
            line += 1
            if limits is not None and line >= len(limits):
                return line
            cap = _line_cap(limits, measure, line, 0.0)
            used = 0.0
        used += width
    return line + 1


def _room(widths, measure: float, first_indent: float, caps=None) -> float:
    """Unused width on the last line. The first line keeps its indent.

    ``caps`` is one width per contour line. A paragraph that already
    needs more lines than that contour is left alone.
    """
    limits = [float(cap) for cap in caps] if caps else None
    line = 0
    cap = _line_cap(limits, measure, line, first_indent)
    used = 0.0
    for width in widths:
        if used > 0.0 and used + width > cap + 1e-6:
            line += 1
            if limits is not None and line >= len(limits):
                return 0.0
            cap = _line_cap(limits, measure, line, 0.0)
            used = 0.0
        used += width
    return max(0.0, cap - used)


def _line_cap(limits, measure: float, line: int, indent: float) -> float:
    width = measure if limits is None else limits[line]
    return width - max(0.0, indent)


def _edge_caps(page, paragraph) -> list[float] | None:
    """Per-line widths of a straight contour. Empty means do not borrow.

    A sentence-flow frame reflows inside itself. A last line that is
    narrower than the block is that contour's tip, not an open column.
    """
    from babeldoc.format.pdf.document_il.utils.layout_plan.line_edges import (
        line_edges_for,
    )

    link = line_edges_for(page, paragraph)
    edges = getattr(link, "edges", None) if link is not None else None
    if not edges:
        return None
    if getattr(link, "flow", "edge") == "sentence":
        return []
    caps = [float(edge[1]) - float(edge[0]) for edge in edges]
    if caps[-1] < max(caps) - 8.0:
        return []
    return caps


def _measure(paragraph) -> float:
    box = paragraph.box
    measure = float(box.x2) - float(box.x)
    metrics = getattr(paragraph, "reference_metrics", None)
    per_line = getattr(metrics, "per_line_widths", None) if metrics else None
    if not per_line:
        return measure
    peak = max((float(width) for width in per_line if width), default=0.0)
    if peak > 12.0:
        return min(measure, peak)
    return measure


def _median(widths) -> float:
    usable = sorted(width for width in widths if width > 0.0)
    if not usable:
        return 0.0
    return usable[len(usable) // 2]


def _open_sentence(paragraph, anchored: set[str]) -> bool:
    if getattr(paragraph, "layout_region_id", None) in anchored:
        return False
    if (getattr(paragraph, "layout_label", None) or "").lower() == "title":
        return False
    text = _visible_text(paragraph)
    if not text or text_ends_sentence(text):
        return False
    return not _opens_list(text)


def _nearest_indent(upper, paragraphs, anchored, figures, used: set[int]):
    best = None
    best_gap = None
    for lower in paragraphs:
        if lower is upper or id(lower) in used or not _has_box(lower):
            continue
        if not _can_indent(upper, lower, anchored, figures):
            continue
        gap = float(upper.box.y) - float(lower.box.y2)
        if best_gap is None or gap < best_gap:
            best = lower
            best_gap = gap
    return best


def _can_indent(upper, lower, anchored, figures) -> bool:
    if getattr(lower, "layout_region_id", None) in anchored:
        return False
    if (getattr(lower, "layout_label", None) or "").lower() == "title":
        return False
    text = _visible_text(lower)
    if not text or _opens_list(text):
        return False
    gap = float(upper.box.y) - float(lower.box.y2)
    if gap < _MIN_GAP or gap > _MAX_GAP:
        return False
    step = float(lower.box.x) - float(upper.box.x)
    if step < _MIN_STEP:
        return False
    if float(lower.box.x2) < float(upper.box.x2) - _RIGHT_SLACK:
        return False
    return any(_beside(figure, upper, lower) for figure in figures)


def _beside(figure, upper, lower) -> bool:
    if float(figure.x2) > float(lower.box.x) + _FIGURE_SLACK:
        return False
    if float(figure.x2) < float(upper.box.x) + _MIN_OVERLAP:
        return False
    overlap = min(float(figure.y2), float(lower.box.y2)) - max(
        float(figure.y), float(lower.box.y)
    )
    return overlap >= _MIN_OVERLAP


def _side_figures(page):
    width, height = _page_size(page)
    found = []
    for figure in getattr(page, "pdf_figure", None) or []:
        box = getattr(figure, "box", None)
        if _usable_figure(box, width, height):
            found.append(box)
    for form in getattr(page, "pdf_form", None) or []:
        if getattr(form, "form_type", None) != "image":
            continue
        box = getattr(form, "box", None)
        if _usable_figure(box, width, height):
            found.append(box)
    return found


def _usable_figure(box, page_width: float, page_height: float) -> bool:
    if box is None or None in (box.x, box.y, box.x2, box.y2):
        return False
    wide = float(box.x2) - float(box.x)
    tall = float(box.y2) - float(box.y)
    if wide >= page_width * _FULL_PAGE and tall >= page_height * _FULL_PAGE:
        return False
    return wide > 8.0 and tall > 8.0


def _page_size(page) -> tuple[float, float]:
    for name in ("cropbox", "mediabox"):
        holder = getattr(page, name, None)
        box = getattr(holder, "box", None) if holder is not None else None
        if box is not None and None not in (box.x, box.y, box.x2, box.y2):
            return float(box.x2) - float(box.x), float(box.y2) - float(box.y)
    return 612.0, 792.0


def _column_ids(page) -> set[str]:
    """Regions whose boxes a column, list, or pocket already owns."""
    from babeldoc.format.pdf.document_il.utils.rect_flow_stack import _rect_links
    from babeldoc.format.pdf.document_il.utils.rect_flow_stack import list_links_on
    from babeldoc.format.pdf.document_il.utils.shaped_pocket_stack import (
        pocket_links_on,
    )

    return (
        set(_rect_links(page))
        | set(list_links_on(page))
        | set(pocket_links_on(page))
    )


def _anchored(page) -> set[str]:
    from babeldoc.format.pdf.document_il.utils.layout_plan.line_edges import (
        line_edge_ids,
    )

    return line_edge_ids(page) | _column_ids(page)


def _matches(paragraph, glyphs) -> bool:
    text = _visible_text(paragraph)
    if text is None or not glyphs:
        return False
    return text == "".join(char for char, _width in glyphs)


def _visible_text(paragraph) -> str | None:
    parts: list[str] = []
    for composition in getattr(paragraph, "pdf_paragraph_composition", None) or []:
        styled = getattr(composition, "pdf_same_style_unicode_characters", None)
        if styled is not None:
            parts.append(_visible(getattr(styled, "unicode", None) or ""))
            continue
        if _other_glyphs(composition):
            return None
    return "".join(parts)


def _other_glyphs(composition) -> bool:
    if getattr(composition, "pdf_line", None) is not None:
        return True
    if getattr(composition, "pdf_character", None) is not None:
        return True
    if getattr(composition, "pdf_formula", None) is not None:
        return True
    same = getattr(composition, "pdf_same_style_characters", None)
    return bool(same is not None and getattr(same, "pdf_character", None))


def _set_visible(paragraph, text: str) -> None:
    runs = []
    for composition in paragraph.pdf_paragraph_composition or []:
        styled = getattr(composition, "pdf_same_style_unicode_characters", None)
        if styled is not None:
            runs.append(styled)
    if not runs:
        return
    if len(runs) == 1:
        runs[0].unicode = text
        paragraph.unicode = text
        return
    lengths = [_visible_len(run.unicode or "") for run in runs]
    cursor = 0
    for run, length in zip(runs, lengths[:-1], strict=False):
        run.unicode = text[cursor : cursor + length]
        cursor += length
    runs[-1].unicode = text[cursor:]
    paragraph.unicode = text


def _visible_len(text: str) -> int:
    return len(_visible(text))


def _visible(text: str) -> str:
    kept = []
    for char in text:
        if char in "\n\r\t":
            continue
        code = ord(char)
        if code < 32 or code == 127 or 0x80 <= code <= 0x9F:
            continue
        kept.append(char)
    return "".join(kept)


def _opens_list(text: str) -> bool:
    stripped = text.lstrip(" \t")
    return bool(stripped) and stripped[0] in "•·●▪◦►▸-*–—"


def _has_box(paragraph) -> bool:
    box = getattr(paragraph, "box", None)
    return box is not None and None not in (box.x, box.y, box.x2, box.y2)
