"""Separate decorative giant quote glyphs and tall margin counters from body text.

Some editorial layouts place a giant opening quotation mark (e.g. 100pt ``“``)
to the left of an 18pt pull-quote, or a tall standalone step numeral (e.g.
30pt ``1``..``6``) at the left gutter of each list step.  When PDF grouping
folds those ornaments into an adjacent text paragraph:

- A 100pt quote glyph bridges multiple lines vertically during line grouping,
  inflates the pull-quote's ``max_font_size`` to 100pt, triggers `` hang ``
  indent misdetection, and suppresses quote exclusion zones.
- A tall margin counter glued onto the bottom of the previous step shatters the
  layout under TOC stack heuristics and pulls the remaining counters out of
  baseline alignment with their step bodies.

Detaching giant quote glyphs before line grouping and margin counters before
independent-paragraph heuristics preserves both the pull-quote typography and
side-by-side step alignment.
"""

from __future__ import annotations

import re
import statistics
from collections.abc import Callable

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraphComposition
from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
from babeldoc.format.pdf.document_il.utils.layout_helper import composition_characters

_DECORATIVE_QUOTE_MARKS = frozenset("“”‘’«»„‟\"'")
_COUNTER_RE = re.compile(r"\d{1,2}")
_QUOTE_FONT_RATIO = 2.0
_COUNTER_FONT_RATIO = 1.8
_COUNTER_MAX_GAP_X = 30.0
_COUNTER_MIN_GAP_X = -2.0
_COUNTER_Y_SLACK = 4.0
_DECORATIVE_MIN_FONT_PT = 36.0


def _comp_text(comp: PdfParagraphComposition) -> str:
    return "".join(
        char.char_unicode or "" for char in composition_characters(comp)
    ).strip()


def _comp_font_size(comp: PdfParagraphComposition) -> float | None:
    sizes = [
        float(char.pdf_style.font_size)
        for char in composition_characters(comp)
        if char.char_unicode
        and not char.char_unicode.isspace()
        and char.pdf_style
        and char.pdf_style.font_size is not None
        and float(char.pdf_style.font_size) > 0
    ]
    if not sizes:
        return None
    return statistics.median(sizes)


def _comp_style(comp: PdfParagraphComposition) -> PdfStyle | None:
    for char in composition_characters(comp):
        if char.char_unicode and not char.char_unicode.isspace() and char.pdf_style:
            return char.pdf_style
    for char in composition_characters(comp):
        if char.pdf_style:
            return char.pdf_style
    return None


def _bounding_box(boxes: list[Box]) -> Box | None:
    if not boxes:
        return None
    return Box(
        x=min(float(box.x) for box in boxes),
        y=min(float(box.y) for box in boxes),
        x2=max(float(box.x2) for box in boxes),
        y2=max(float(box.y2) for box in boxes),
    )


def _comp_box(comp: PdfParagraphComposition) -> Box | None:
    boxes: list[Box] = []
    for char in composition_characters(comp):
        visual = getattr(char, "visual_bbox", None)
        box = getattr(visual, "box", None) if visual is not None else None
        if box is None:
            box = getattr(char, "box", None)
        if box is None or None in (box.x, box.y, box.x2, box.y2):
            continue
        boxes.append(box)
    if not boxes:
        line = getattr(comp, "pdf_line", None)
        box = getattr(line, "box", None) if line is not None else None
        if box is None or None in (box.x, box.y, box.x2, box.y2):
            return None
        return _bounding_box([box])
    return _bounding_box(boxes)


def _union_box(comps: list[PdfParagraphComposition]) -> Box | None:
    return _bounding_box(
        [box for comp in comps if (box := _comp_box(comp)) is not None]
    )


def _paragraph_text(paragraph: PdfParagraph) -> str:
    text = (getattr(paragraph, "unicode", None) or "").strip()
    if text:
        return text
    return "".join(
        _comp_text(comp) for comp in (paragraph.pdf_paragraph_composition or [])
    ).strip()


def _paragraph_font_size(paragraph: PdfParagraph) -> float | None:
    sizes: list[float] = []
    for comp in paragraph.pdf_paragraph_composition or []:
        fs = _comp_font_size(comp)
        if fs is not None:
            sizes.append(fs)
    if sizes:
        return statistics.median(sizes)
    style = getattr(paragraph, "pdf_style", None)
    fs = getattr(style, "font_size", None) if style is not None else None
    return float(fs) if fs is not None and float(fs) > 0 else None


def _paragraph_box(paragraph: PdfParagraph) -> Box | None:
    box = getattr(paragraph, "box", None)
    if box is not None and None not in (box.x, box.y, box.x2, box.y2):
        return box
    return _union_box(list(paragraph.pdf_paragraph_composition or []))


def _first_nonempty_comp_box(paragraph: PdfParagraph) -> Box | None:
    for comp in paragraph.pdf_paragraph_composition or []:
        if not _comp_text(comp):
            continue
        box = _comp_box(comp)
        if box is not None:
            return box
    return _paragraph_box(paragraph)


def _is_quote_text(text: str) -> bool:
    return 1 <= len(text) <= 2 and all(
        ch in _DECORATIVE_QUOTE_MARKS for ch in text
    )


def _is_bare_counter_text(text: str) -> bool:
    return bool(_COUNTER_RE.fullmatch(text))


def _join_comp_texts(comps: list[PdfParagraphComposition]) -> str:
    if any(getattr(comp, "pdf_line", None) is not None for comp in comps):
        return " ".join(
            text for comp in comps if (text := _comp_text(comp))
        ).strip()
    return "".join(_comp_text(comp) for comp in comps).strip()


def _make_paragraph(
    source: PdfParagraph,
    comps: list[PdfParagraphComposition],
    *,
    debug_id: str | None,
) -> PdfParagraph:
    style = _comp_style(comps[0]) if comps else None
    return PdfParagraph(
        box=_union_box(comps),
        pdf_style=style or source.pdf_style,
        pdf_paragraph_composition=comps,
        xobj_id=source.xobj_id,
        unicode=_join_comp_texts(comps),
        scale=source.scale,
        optimal_scale=source.optimal_scale,
        vertical=source.vertical,
        layout_label=source.layout_label,
        layout_id=source.layout_id,
        debug_id=debug_id,
    )


def _split_by_flags(
    paragraphs: list[PdfParagraph],
    flag_fn: Callable[[PdfParagraph], list[bool]],
    *,
    new_debug_id_factory: Callable[[], str],
    on_update: Callable[[PdfParagraph], None] | None,
) -> None:
    expanded: list[PdfParagraph] = []
    for paragraph in list(paragraphs):
        flags = flag_fn(paragraph)
        if not any(flags):
            expanded.append(paragraph)
            continue

        comps = list(paragraph.pdf_paragraph_composition or [])
        reused_source = False
        idx = 0
        while idx < len(comps):
            if flags[idx]:
                detached = _make_paragraph(
                    paragraph,
                    [comps[idx]],
                    debug_id=new_debug_id_factory(),
                )
                if on_update is not None:
                    on_update(detached)
                expanded.append(detached)
                idx += 1
                continue

            run: list[PdfParagraphComposition] = []
            while idx < len(comps) and not flags[idx]:
                run.append(comps[idx])
                idx += 1
            if not reused_source:
                paragraph.pdf_paragraph_composition = run
                paragraph.box = _union_box(run)
                paragraph.unicode = _join_comp_texts(run)
                if on_update is not None:
                    on_update(paragraph)
                expanded.append(paragraph)
                reused_source = True
            else:
                tail_para = _make_paragraph(
                    paragraph,
                    run,
                    debug_id=new_debug_id_factory(),
                )
                if on_update is not None:
                    on_update(tail_para)
                expanded.append(tail_para)
    paragraphs[:] = expanded


def _oversized_token_flags(
    paragraph: PdfParagraph,
    predicate: Callable[[str], bool],
    min_ratio: float,
) -> list[bool]:
    """Flag components matching *predicate* whose font is >= *min_ratio* of body median."""
    comps = list(paragraph.pdf_paragraph_composition or [])
    if len(comps) < 2:
        return [False] * len(comps)
    texts = [_comp_text(comp) for comp in comps]
    sizes = [_comp_font_size(comp) for comp in comps]
    body_sizes = [
        fs
        for text, fs in zip(texts, sizes, strict=True)
        if fs is not None and text and not predicate(text)
    ]
    if not body_sizes:
        return [False] * len(comps)
    body_med = statistics.median(body_sizes)
    return [
        bool(text and fs is not None and predicate(text) and fs >= min_ratio * body_med)
        for text, fs in zip(texts, sizes, strict=True)
    ]


def _oversized_quote_flags(paragraph: PdfParagraph) -> list[bool]:
    return _oversized_token_flags(paragraph, _is_quote_text, _QUOTE_FONT_RATIO)


def _margin_counter_flags(paragraph: PdfParagraph) -> list[bool]:
    return _oversized_token_flags(paragraph, _is_bare_counter_text, _COUNTER_FONT_RATIO)


def _pair_margin_counters(paragraphs: list[PdfParagraph]) -> None:
    for counter_para in paragraphs:
        if not _is_bare_counter_text(_paragraph_text(counter_para)):
            continue
        c_fs = _paragraph_font_size(counter_para)
        c_box = _paragraph_box(counter_para)
        if c_fs is None or c_box is None:
            continue

        best_step: PdfParagraph | None = None
        best_gap: float | None = None
        for other in paragraphs:
            if other is counter_para:
                continue
            if _is_bare_counter_text(_paragraph_text(other)):
                continue
            other_fs = _paragraph_font_size(other)
            if other_fs is None or c_fs < _COUNTER_FONT_RATIO * other_fs:
                continue
            first_box = _first_nonempty_comp_box(other)
            if first_box is None:
                continue
            gap_x = float(first_box.x) - float(c_box.x2)
            if gap_x < _COUNTER_MIN_GAP_X or gap_x > _COUNTER_MAX_GAP_X:
                continue
            y_overlap = min(float(c_box.y2), float(first_box.y2)) - max(
                float(c_box.y), float(first_box.y)
            )
            if y_overlap < -_COUNTER_Y_SLACK:
                continue
            if best_gap is None or gap_x < best_gap:
                best_step = other
                best_gap = gap_x

        if best_step is not None:
            counter_para.layout_label = "list"
            best_step.layout_label = "list"


def is_decorative_quote_ornament(paragraph: PdfParagraph) -> bool:
    """Return True for a standalone oversized decorative quotation glyph."""
    text = _paragraph_text(paragraph)
    if not _is_quote_text(text):
        return False
    fs = _paragraph_font_size(paragraph)
    return fs is not None and fs >= _DECORATIVE_MIN_FONT_PT


def detach_oversized_quote_chars(
    paragraphs: list[PdfParagraph],
    *,
    new_debug_id_factory: Callable[[], str],
    on_update: Callable[[PdfParagraph], None] | None = None,
) -> None:
    """Split oversized decorative quote glyphs out before line grouping.

    Must run before ``_split_paragraph_into_lines`` so a tall 100pt quote mark
    does not vertically bridge multiple 18pt body lines into a single line.
    """
    if not paragraphs:
        return
    _split_by_flags(
        paragraphs,
        _oversized_quote_flags,
        new_debug_id_factory=new_debug_id_factory,
        on_update=on_update,
    )


def detach_decorative_quotes_and_margin_counters(
    paragraphs: list[PdfParagraph],
    *,
    new_debug_id_factory: Callable[[], str],
    on_update: Callable[[PdfParagraph], None] | None = None,
) -> None:
    """Split oversized quote marks / margin counters and label step pairs."""
    if not paragraphs:
        return
    _split_by_flags(
        paragraphs,
        _oversized_quote_flags,
        new_debug_id_factory=new_debug_id_factory,
        on_update=on_update,
    )
    _split_by_flags(
        paragraphs,
        _margin_counter_flags,
        new_debug_id_factory=new_debug_id_factory,
        on_update=on_update,
    )
    _pair_margin_counters(paragraphs)
