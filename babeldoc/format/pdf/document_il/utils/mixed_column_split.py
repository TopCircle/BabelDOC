"""Split one bad cut: a straight run glued to a figure wrap.

The two parts become two paragraphs before the layout plan is frozen, so
the straight run can be a column and the wrap can be a pocket. This does
not merge paragraphs, and it does not special-case a sample id. A bullet
stays one paragraph. A pure column and a pure stair stay one paragraph.
"""

from __future__ import annotations

import logging

from babeldoc.format.pdf.document_il import Box
from babeldoc.format.pdf.document_il import PdfParagraphComposition
from babeldoc.format.pdf.document_il import PdfSameStyleCharacters
from babeldoc.format.pdf.document_il.il_version_1 import ReferenceMetrics
from babeldoc.format.pdf.document_il.midend.paragraph_finder import generate_base58_id
from babeldoc.format.pdf.document_il.utils.layout_helper import composition_characters
from babeldoc.format.pdf.document_il.utils.layout_plan.geometry import free_side
from babeldoc.format.pdf.document_il.utils.layout_plan.geometry import geometry_eligible
from babeldoc.format.pdf.document_il.utils.layout_plan.geometry import is_stable_column
from babeldoc.format.pdf.document_il.utils.layout_plan.geometry import is_taper
from babeldoc.format.pdf.document_il.utils.layout_plan.model import LineBox
from babeldoc.format.pdf.document_il.utils.layout_plan.model import Region
from babeldoc.format.pdf.document_il.utils.layout_plan.plugins.list_flow import (
    has_list_evidence,
)
from babeldoc.format.pdf.document_il.utils.paragraph_split_policy import (
    split_paragraph_at,
)
from babeldoc.format.pdf.document_il.utils.paragraph_split_policy import (
    text_ends_sentence,
)
from babeldoc.format.pdf.document_il.utils.placement_paradigm import shares_column_left
from babeldoc.format.pdf.document_il.utils.rect_flow_stack import _SAME_LINE_TOP
from babeldoc.format.pdf.document_il.utils.rect_flow_stack import _line_chars
from babeldoc.format.pdf.document_il.utils.rect_flow_stack import _lines_of
from babeldoc.format.pdf.document_il.utils.rect_flow_stack import _marker_of
from babeldoc.format.pdf.document_il.utils.rect_flow_stack import _on_photo
from babeldoc.format.pdf.document_il.utils.rect_flow_stack import _opens_as_list
from babeldoc.format.pdf.document_il.utils.rect_flow_stack import _role_of
from babeldoc.format.pdf.document_il.utils.rect_flow_stack import _source_text

logger = logging.getLogger(__name__)

_LINE_MATCH = 0.05


def split_mixed_column_wraps(page) -> None:
    """Replace a glued column-and-wrap with two paragraphs, when the cut is one line."""
    paragraphs = list(getattr(page, "pdf_paragraph", None) or [])
    if not paragraphs:
        return
    rewritten = []
    for paragraph in paragraphs:
        rewritten.extend(_split_one(paragraph))
    page.pdf_paragraph = rewritten


def _split_one(paragraph) -> list:
    try:
        return _split_one_at(paragraph)
    except Exception:
        logger.warning("mixed column split skipped a paragraph", exc_info=True)
        return [paragraph]


def _split_one_at(paragraph) -> list:
    if getattr(paragraph, "box", None) is None or not _may_split(paragraph):
        return [paragraph]
    compositions = list(getattr(paragraph, "pdf_paragraph_composition", None) or [])
    if not compositions or _has_formula(compositions):
        return [paragraph]
    lines = _lines_of(paragraph)
    cut = _cut_index(lines)
    # Cutting "nipples are | touched" makes the straight part end early
    # and the next line stick out into the figure. A finished sentence
    # can still split. Missing text keeps the geometric cut.
    if cut is None or not _cut_keeps_a_sentence(paragraph, cut):
        return [paragraph]
    if _pure_line_compositions(compositions, lines):
        if not _top_first(lines):
            return [paragraph]
        return _commit(paragraph, compositions, cut, lines[:cut], lines[cut:])
    rebuilt, index = _cleave_folded(compositions, lines, cut)
    if index is None:
        return [paragraph]
    return _commit(paragraph, rebuilt, index, lines[:cut], lines[cut:])


def _may_split(paragraph) -> bool:
    """Body or wrap text only. A bullet stays whole so it cannot become a stack."""
    region = Region(
        region_id="probe",
        page_index=0,
        source_order=0,
        role=_role_of(paragraph),
        lines=(),
        text_on_photo=_on_photo(paragraph),
        source_text=_source_text(paragraph),
        marker=_marker_of(paragraph),
    )
    if not geometry_eligible(region):
        return False
    return not (has_list_evidence(region) or _opens_as_list(paragraph))


def _cut_keeps_a_sentence(paragraph, cut: int) -> bool:
    """False only when the line above the cut is still mid-sentence."""
    texts = _visual_line_texts(paragraph)
    if not texts or cut > len(texts):
        return True
    return text_ends_sentence(texts[cut - 1])


def _visual_line_texts(paragraph) -> list[str]:
    """Glyph text of each source line, top first, matching ``_lines_of``."""
    placed: list[tuple[float, float, str]] = []
    for composition in getattr(paragraph, "pdf_paragraph_composition", None) or []:
        for char in _line_chars(composition):
            box = getattr(char, "box", None)
            if box is None or box.y2 is None or box.x is None:
                continue
            placed.append(
                (float(box.y2), float(box.x), getattr(char, "char_unicode", None) or "")
            )
    if not placed:
        return []
    placed.sort(key=lambda item: (-item[0], item[1]))
    groups: list[list[tuple[float, float, str]]] = [[placed[0]]]
    for item in placed[1:]:
        if abs(groups[-1][0][0] - item[0]) <= _SAME_LINE_TOP:
            groups[-1].append(item)
            continue
        groups.append([item])
    texts = []
    for group in groups:
        group.sort(key=lambda item: item[1])
        texts.append("".join(item[2] for item in group))
    return texts


def _cut_index(lines: tuple[LineBox, ...]) -> int | None:
    """One boundary where a wide straight run meets a stair.

    The straight run has to be the wide end, and the wrap has to clear
    that run rather than take the next step of the same stair. A flat
    tip of a stair is narrower than the peak and stays with the wrap.
    The public taper test is applied to each part on its own.
    """
    if len(lines) < 6 or not is_taper(_probe(lines)):
        return None
    peak = _peak(lines)
    prefix = []
    suffix = []
    for index in range(1, len(lines)):
        head, tail = lines[:index], lines[index:]
        if (
            _is_wide_rectangle(head, peak)
            and is_taper(_probe(tail))
            and _wrap_leaves(head, tail, straight_above=True)
        ):
            prefix.append(index)
        if (
            is_taper(_probe(head))
            and _is_wide_rectangle(tail, peak)
            and _wrap_leaves(tail, head, straight_above=False)
        ):
            suffix.append(index)
    straight_prefix = max(prefix) if prefix else None
    straight_suffix = min(suffix) if suffix else None
    if straight_prefix is None:
        return straight_suffix
    if straight_suffix is None:
        return straight_prefix
    prefix_lines = straight_prefix
    suffix_lines = len(lines) - straight_suffix
    if prefix_lines == suffix_lines:
        return None
    if prefix_lines > suffix_lines:
        return straight_prefix
    return straight_suffix


def _is_wide_rectangle(lines: tuple[LineBox, ...], peak: float) -> bool:
    """The wide end of the block, long enough to be its own column.

    Two or three lines at the top of a circle are still that wrap. They
    are wider only because the curve has not reached them yet.
    """
    if len(lines) < 4 or not is_stable_column(_probe(lines)):
        return False
    return shares_column_left(_peak(lines), peak)


def _wrap_leaves(straight: tuple[LineBox, ...], wrap: tuple[LineBox, ...], *, straight_above: bool) -> bool:
    """True when the wrap's edge clears the straight run's whole rag."""
    side = free_side(_probe(wrap))
    if side not in ("left", "right"):
        return False
    straight_edge = _edge(straight, side)
    wrap_edge = _edge(wrap, side)
    if straight_above:
        gap = abs(wrap_edge[0] - straight_edge[-1])
    else:
        gap = abs(straight_edge[0] - wrap_edge[-1])
    span = max(straight_edge) - min(straight_edge)
    return gap > span and not shares_column_left(gap, span)


def _edge(lines: tuple[LineBox, ...], side: str) -> list[float]:
    if side == "right":
        return [line.x1 for line in lines]
    return [line.x0 for line in lines]


def _probe(lines: tuple[LineBox, ...]) -> Region:
    return Region(
        region_id="probe",
        page_index=0,
        source_order=0,
        role="body",
        lines=tuple(lines),
    )


def _peak(lines: tuple[LineBox, ...]) -> float:
    return max(line.x1 - line.x0 for line in lines)


def _has_formula(compositions) -> bool:
    return any(getattr(composition, "pdf_formula", None) is not None for composition in compositions)


def _pure_line_compositions(compositions, lines) -> bool:
    if len(compositions) != len(lines):
        return False
    for composition in compositions:
        line = getattr(composition, "pdf_line", None)
        box = getattr(line, "box", None) if line is not None else None
        if box is None or None in (box.x, box.x2, box.y2):
            return False
        if _line_chars(composition) and getattr(composition, "pdf_same_style_characters", None):
            return False
    return all(getattr(composition, "pdf_same_style_characters", None) is None for composition in compositions)


def _top_first(lines: tuple[LineBox, ...]) -> bool:
    return all(
        lines[index].y0 + _SAME_LINE_TOP >= lines[index + 1].y0
        for index in range(len(lines) - 1)
    )


def _cleave_folded(compositions, lines, cut: int):
    """Return compositions in order and the index where the tail starts."""
    rebuilt = []
    split_at = None
    for composition in compositions:
        chars = _line_chars(composition)
        if not chars:
            index = _line_index_of_box(composition, lines)
            if index is None:
                return None, None
            rebuilt.append(composition)
            if index >= cut and split_at is None:
                split_at = len(rebuilt) - 1
            continue
        indexes = [_line_index(char, lines) for char in chars]
        if any(index is None for index in indexes):
            return None, None
        if all(index < cut for index in indexes):
            rebuilt.append(composition)
            continue
        if all(index >= cut for index in indexes):
            if split_at is None:
                split_at = len(rebuilt)
            rebuilt.append(composition)
            continue
        same = getattr(composition, "pdf_same_style_characters", None)
        if same is None:
            return None, None
        head_chars = [char for char, index in zip(chars, indexes, strict=True) if index < cut]
        tail_chars = [char for char, index in zip(chars, indexes, strict=True) if index >= cut]
        if not head_chars or not tail_chars:
            return None, None
        style = getattr(same, "pdf_style", None)
        rebuilt.append(_same_style(style, head_chars))
        if split_at is None:
            split_at = len(rebuilt)
        rebuilt.append(_same_style(style, tail_chars))
    if split_at is None or split_at == 0 or split_at == len(rebuilt):
        return None, None
    return rebuilt, split_at


def _line_index(char, lines) -> int | None:
    box = getattr(char, "box", None)
    if box is None or box.y2 is None:
        return None
    return _y_index(float(box.y2), lines)


def _line_index_of_box(composition, lines) -> int | None:
    line = getattr(composition, "pdf_line", None)
    box = getattr(line, "box", None) if line is not None else None
    if box is None or box.y2 is None:
        return None
    return _y_index(float(box.y2), lines)


def _y_index(y: float, lines) -> int | None:
    found = None
    for index, line in enumerate(lines):
        if abs(y - line.y0) <= _SAME_LINE_TOP:
            found = index
            break
    return found


def _same_style(style, chars) -> PdfParagraphComposition:
    return PdfParagraphComposition(
        pdf_same_style_characters=PdfSameStyleCharacters(
            box=_box_of(chars),
            pdf_style=style,
            pdf_character=list(chars),
        )
    )


def _commit(paragraph, compositions, index: int, head_lines, tail_lines) -> list:
    saved = list(getattr(paragraph, "pdf_paragraph_composition", None) or [])
    saved_unicode = getattr(paragraph, "unicode", None)
    saved_box = getattr(paragraph, "box", None)
    saved_metrics = getattr(paragraph, "reference_metrics", None)
    paragraph.pdf_paragraph_composition = list(compositions)
    try:
        tail = _split_at(paragraph, index)
    except Exception:
        logger.warning("mixed column split failed", exc_info=True)
        _restore(paragraph, saved, saved_unicode, saved_box, saved_metrics)
        return [paragraph]
    if tail is None:
        return [paragraph]
    if not _same_lines(_lines_of(paragraph), head_lines) or not _same_lines(
        _lines_of(tail), tail_lines
    ):
        _restore(paragraph, saved, saved_unicode, saved_box, saved_metrics)
        return [paragraph]
    logger.info(
        "split a straight run off a wrap: %s lines and %s lines",
        len(head_lines),
        len(tail_lines),
    )
    return [paragraph, tail]


def _split_at(paragraph, index: int):
    compositions = paragraph.pdf_paragraph_composition
    if index <= 0 or index >= len(compositions):
        return None
    if not hasattr(paragraph, "layout_id"):
        paragraph.layout_id = None
    if not hasattr(paragraph, "layout_label"):
        paragraph.layout_label = None
    tail = split_paragraph_at(
        paragraph,
        index,
        new_debug_id=generate_base58_id(),
    )
    _copy_runtime(paragraph, tail)
    _refresh(paragraph)
    _refresh(tail)
    return tail


def _restore(paragraph, compositions, unicode, box, metrics) -> None:
    paragraph.pdf_paragraph_composition = compositions
    paragraph.unicode = unicode
    paragraph.box = box
    paragraph.reference_metrics = metrics


def _copy_runtime(head, tail) -> None:
    for name in ("layout_intent", "pdf_style", "xobj_id", "vertical", "alignment"):
        if hasattr(head, name):
            setattr(tail, name, getattr(head, name))
    metrics = getattr(head, "reference_metrics", None)
    if metrics is None:
        return
    head.reference_metrics = _metrics_for(metrics, _lines_of(head))
    tail.reference_metrics = _metrics_for(metrics, _lines_of(tail))


def _metrics_for(metrics, lines: tuple[LineBox, ...]) -> ReferenceMetrics | None:
    widths = [line.x1 - line.x0 for line in lines]
    if not widths:
        return None
    average = sum(widths) / len(widths)
    last = widths[-1]
    return ReferenceMetrics(
        line_count=len(widths),
        avg_line_width=average,
        last_line_width=last,
        last_line_ratio=(last / average) if average else 1.0,
        font_size=float(getattr(metrics, "font_size", 0.0) or 0.0),
        per_line_widths=widths,
    )


def _refresh(paragraph) -> None:
    text = _unicode_from_chars(paragraph)
    if text:
        paragraph.unicode = text
    box = _paragraph_box(paragraph)
    if box is not None:
        paragraph.box = box


def _unicode_from_chars(paragraph) -> str:
    parts = []
    for composition in getattr(paragraph, "pdf_paragraph_composition", None) or []:
        for char in composition_characters(composition):
            parts.append(getattr(char, "char_unicode", None) or "")
    return "".join(parts)


def _paragraph_box(paragraph):
    chars = []
    for composition in getattr(paragraph, "pdf_paragraph_composition", None) or []:
        found = composition_characters(composition)
        chars.extend(found)
        box = _box_of(found)
        if box is None:
            continue
        same = getattr(composition, "pdf_same_style_characters", None)
        if same is not None:
            same.box = box
        line = getattr(composition, "pdf_line", None)
        if line is not None and found:
            line.box = box
    box = _box_of(chars)
    if box is not None:
        return box
    boxes = []
    for composition in getattr(paragraph, "pdf_paragraph_composition", None) or []:
        line = getattr(composition, "pdf_line", None)
        line_box = getattr(line, "box", None) if line is not None else None
        if line_box is not None and None not in (line_box.x, line_box.y, line_box.x2, line_box.y2):
            boxes.append(line_box)
    return _box_of_boxes(boxes)


def _box_of(chars):
    boxes = []
    for char in chars:
        box = getattr(char, "box", None)
        if box is not None and None not in (box.x, box.y, box.x2, box.y2):
            boxes.append(box)
    return _box_of_boxes(boxes)


def _box_of_boxes(boxes):
    if not boxes:
        return None
    return Box(
        min(float(box.x) for box in boxes),
        min(float(box.y) for box in boxes),
        max(float(box.x2) for box in boxes),
        max(float(box.y2) for box in boxes),
    )


def _same_lines(got, expected) -> bool:
    if len(got) != len(expected):
        return False
    for left, right in zip(got, expected, strict=True):
        if abs(left.x0 - right.x0) > _LINE_MATCH:
            return False
        if abs(left.x1 - right.x1) > _LINE_MATCH:
            return False
        if abs(left.y0 - right.y0) > _LINE_MATCH:
            return False
    return True
