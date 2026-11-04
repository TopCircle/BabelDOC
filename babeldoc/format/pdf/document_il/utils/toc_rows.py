"""Directory rows: detect, split, and seat them on the source line.

Line-pair splitting stays in ``paragraph_split_policy``. This module owns
the directory predicate, the row cut, and the one restore after typesetting.
"""

from __future__ import annotations

import re

from babeldoc.format.pdf.document_il import Box
from babeldoc.format.pdf.document_il import PdfLine
from babeldoc.format.pdf.document_il import PdfParagraph
from babeldoc.format.pdf.document_il import PdfParagraphComposition
from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter
from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
from babeldoc.format.pdf.document_il.il_version_1 import VisualBbox
from babeldoc.format.pdf.document_il.utils.paragraph_split_policy import _box_from_chars
from babeldoc.format.pdf.document_il.utils.paragraph_split_policy import (
    line_ends_sentence,
)
from babeldoc.format.pdf.document_il.utils.paragraph_split_policy import line_text
from babeldoc.format.pdf.document_il.utils.paragraph_split_policy import (
    paragraph_line_chars,
)
from babeldoc.format.pdf.document_il.utils.paragraph_split_policy import (
    text_ends_sentence,
)

# A directory row closes with a leader, a page number alone, or a wide gap
# before the page number. Two dots are enough: some rows stop at 19.
_TOC_ENTRY_TAIL_RE = re.compile(
    r"(?:"
    r"\.{2,}|…+|·{2,}|_{2,}|\-{3,}|\.(?:\s*\.){2,}|\s{2,}"
    r")\s*\d{1,4}\s*$"
)
_TOC_PAGE_ONLY_RE = re.compile(r"\d{1,4}")
_TOC_HEADER_RE = re.compile(
    r"\b(table\s+of\s+contents|contents|directory|table\s+des\s+mati[èe]res|inhaltsverzeichnis|目录)\b",
    re.IGNORECASE,
)
# A page-wide switch. A sentence that only says "contents" is not one.
_TOC_PAGE_HEADER_RE = re.compile(
    r"\b(table\s+of\s+contents|table\s+des\s+mati[èe]res|inhaltsverzeichnis|目录)\b",
    re.IGNORECASE,
)
_TOC_PAGE_GAP = 24.0
# Two directory rows painted into one paragraph. A wrapped body line is closer.
_BASELINE_SPLIT = 8.0
# One numbered row plus several short untitled rows is still a directory.
# A body line is longer than this, so a citation does not open the stack.
_TOC_SHORT_LINE = 64
# A contents row the detector called a title. A real chapter head stays a title.
_CHAPTER_HEAD_RE = re.compile(
    r"^(chapter\s+\d+\b|第\s*[0-9０-９一二三四五六七八九十]+\s*章)",
    re.IGNORECASE,
)
_TOC_KEEP_LABELS = frozenset(
    {
        "title",
        "section_header",
        "figure_caption",
        "figure_title",
        "figure_text",
        "table_caption",
    }
)

def _ink_box(char: PdfCharacter):
    visual = getattr(char, "visual_bbox", None)
    box = getattr(visual, "box", None) if visual is not None else None
    if box is None or box.x is None:
        box = getattr(char, "box", None)
    return box


def _chars_left_to_right(chars) -> list:
    def _x(char) -> float:
        box = _ink_box(char)
        if box is None or box.x is None:
            return 0.0
        return float(box.x)

    return sorted(chars or [], key=_x)


def _page_number_start(chars) -> int | None:
    """Index, in left-to-right order, of a 1–4 digit tail at least 24pt to the right.

    Spaces between the title and the number stay with the title. A year that
    sits one space after a word is not a tail.
    """
    ordered = _chars_left_to_right(chars)
    if len(ordered) < 2:
        return None
    end = len(ordered)
    while end > 0 and not (ordered[end - 1].char_unicode or "").strip():
        end -= 1
    start = end
    while start > 0:
        text = ordered[start - 1].char_unicode or ""
        if len(text) == 1 and text.isascii() and text.isdigit():
            start -= 1
            continue
        break
    count = end - start
    if not 1 <= count <= 4 or start == 0:
        return None
    prev = start - 1
    while prev >= 0 and not (ordered[prev].char_unicode or "").strip():
        prev -= 1
    if prev < 0:
        return None
    prev_box = _ink_box(ordered[prev])
    page_box = _ink_box(ordered[start])
    if (
        prev_box is None
        or page_box is None
        or prev_box.x2 is None
        or page_box.x is None
    ):
        return None
    if float(page_box.x) - float(prev_box.x2) >= _TOC_PAGE_GAP:
        return start
    # Leaders run up to the digits, so the gap is small. The tail is still
    # a page number. A year after one space does not match this tail.
    text = "".join(char.char_unicode or "" for char in ordered)
    if _TOC_ENTRY_TAIL_RE.search(text):
        return start
    return None


def _page_number_gap(line: PdfLine | None) -> bool:
    """True when a 1–4 digit run sits at least 24pt right of the previous glyph."""
    if line is None:
        return False
    return _page_number_start(line.pdf_character) is not None


def is_toc_entry_line(line: PdfLine | None) -> bool:
    """One directory row: leader, bare page number, or a number in the right margin."""
    text = line_text(line).strip()
    if not text:
        return False
    if _TOC_PAGE_ONLY_RE.fullmatch(text):
        return True
    if _TOC_ENTRY_TAIL_RE.search(text):
        return True
    return _page_number_gap(line)


def is_toc_header_text(text: str | None) -> bool:
    """True for a short 'Table of Contents' line, not a sentence that mentions one."""
    raw = (text or "").strip()
    if not raw or len(raw.split()) > 8:
        return False
    return bool(_TOC_HEADER_RE.search(raw))


def is_chapter_heading(text: str | None) -> bool:
    """A chapter line stays a title. A contents entry that merely says 'chapter' does too."""
    raw = (text or "").strip()
    if not raw:
        return False
    return bool(_CHAPTER_HEAD_RE.match(raw))


def is_toc_page_header(text: str | None) -> bool:
    """True for a contents heading. A passing mention of 'contents' is not one."""
    raw = (text or "").strip()
    if not raw or len(raw.split()) > 8:
        return False
    lowered = raw.lower()
    if lowered.startswith(
        ("go to", "back to", "return to", "link to", "click here", "see the")
    ):
        return False
    return bool(_TOC_PAGE_HEADER_RE.search(raw))


def is_toc_row(line: PdfLine | None) -> bool:
    """One directory row: a page number, a leader, or a short title with neither.

    A sentence, a web address, and a long body line are not rows.
    """
    if is_toc_entry_line(line):
        return True
    text = line_text(line).strip()
    if not text or len(text) > _TOC_SHORT_LINE:
        return False
    if text_ends_sentence(text):
        return False
    lowered = text.lower()
    if lowered.startswith("www.") or "://" in lowered:
        return False
    first = text[0]
    return first.isupper() or first.isdigit()


def all_toc_rows(lines: list[PdfLine | None]) -> bool:
    """True when every real line is a directory row."""
    real = [line for line in lines if line is not None and line_text(line).strip()]
    return bool(real) and all(is_toc_row(line) for line in real)


def _starts_like_label(line: PdfLine) -> bool:
    text = line_text(line).lstrip()
    if not text:
        return False
    first = text[0]
    return first.isupper() or first.isdigit()


def _short_label_stack(lines: list[PdfLine]) -> bool:
    """Untitled directory rows: short, capitalized, and not sentences."""
    if len(lines) < 4:
        return False
    if any(len(line_text(line).strip()) > _TOC_SHORT_LINE for line in lines):
        return False
    open_lines = [line for line in lines if not line_ends_sentence(line)]
    if len(open_lines) < 0.8 * len(lines):
        return False
    labels = [line for line in lines if _starts_like_label(line)]
    return len(labels) >= 0.8 * len(lines)


def is_toc_stack(lines: list[PdfLine | None], *, on_toc_page: bool = False) -> bool:
    """True when these lines are directory rows, not a prose paragraph.

    Two page-number rows are enough. One page-number row still counts when
    the other rows are short and do not end a sentence. On a contents page,
    a run of short capitalized rows with no page numbers is the same kind of
    list. A prose paragraph that merely cites a page stays one paragraph.
    """
    real = [line for line in lines if line is not None and line_text(line).strip()]
    if len(real) < 3:
        return False
    entries = [line for line in real if is_toc_entry_line(line)]
    if len(entries) >= 2:
        return True
    if on_toc_page and _short_label_stack(real):
        return True
    if len(entries) != 1:
        return False
    others = [line for line in real if not is_toc_entry_line(line)]
    if len(others) < 2:
        return False
    if any(len(line_text(line).strip()) > _TOC_SHORT_LINE for line in others):
        return False
    open_lines = [line for line in others if not line_ends_sentence(line)]
    if len(open_lines) < 2:
        return False
    return len(open_lines) >= 0.6 * len(others)


def toc_label_stays(label: str | None) -> bool:
    """Titles and captions are not directory rows, even on a contents page."""
    return (label or "").strip().lower() in _TOC_KEEP_LABELS


def is_toc_paragraph(paragraph: PdfParagraph) -> bool:
    """True when this paragraph is a directory row and must not be joined."""
    label = (getattr(paragraph, "layout_label", None) or "").strip().lower()
    if label == "toc":
        return True
    intent = getattr(paragraph, "layout_intent", None)
    role = getattr(intent, "role", None) if intent is not None else None
    role_val = getattr(role, "value", role) if role is not None else None
    if role_val == "toc":
        return True
    text = (getattr(paragraph, "unicode", None) or "").strip()
    if text and (
        _TOC_PAGE_ONLY_RE.fullmatch(text) or _TOC_ENTRY_TAIL_RE.search(text)
    ):
        return True
    for comp in getattr(paragraph, "pdf_paragraph_composition", None) or []:
        line = getattr(comp, "pdf_line", None)
        if line is not None and is_toc_entry_line(line):
            return True
    return False


def _y_center(char) -> float | None:
    box = _ink_box(char)
    if box is None or box.y is None or box.y2 is None:
        return None
    return (float(box.y) + float(box.y2)) / 2.0


def _baseline_clusters(chars) -> list[list]:
    """Groups ordered top to bottom. A step over 8pt opens a new row."""
    ranked = []
    for char in chars:
        center = _y_center(char)
        if center is None:
            continue
        ranked.append((center, char))
    if not ranked:
        return []
    ranked.sort(key=lambda item: -item[0])
    clusters = [[ranked[0][1]]]
    anchor = ranked[0][0]
    for center, char in ranked[1:]:
        if abs(anchor - center) > _BASELINE_SPLIT:
            clusters.append([char])
            anchor = center
            continue
        clusters[-1].append(char)
    return clusters


def _line_from_chars(chars) -> PdfLine:
    ordered = sorted(
        chars,
        key=lambda char: float(getattr(_ink_box(char), "x", 0.0) or 0.0),
    )
    return PdfLine(pdf_character=ordered, box=_box_from_chars(ordered))


def _install_chars(paragraph: PdfParagraph, chars) -> None:
    line = _line_from_chars(chars)
    paragraph.pdf_paragraph_composition = [
        PdfParagraphComposition(pdf_line=line),
    ]
    paragraph.box = line.box
    paragraph.unicode = "".join(char.char_unicode or "" for char in line.pdf_character)


def _paragraph_of_chars(
    host: PdfParagraph,
    chars,
    *,
    new_debug_id: str,
    label: str | None,
) -> PdfParagraph:
    line = _line_from_chars(chars)
    return PdfParagraph(
        box=line.box,
        pdf_paragraph_composition=[PdfParagraphComposition(pdf_line=line)],
        unicode="".join(char.char_unicode or "" for char in line.pdf_character),
        debug_id=new_debug_id,
        layout_label=label,
        layout_id=getattr(host, "layout_id", None),
        xobj_id=getattr(host, "xobj_id", None),
        pdf_style=getattr(host, "pdf_style", None),
    )


def _directory_baselines(clusters: list[list]) -> bool:
    """True when each baseline is a directory row and one of them carries a page number."""
    if len(clusters) < 2:
        return False
    lines = [_line_from_chars(cluster) for cluster in clusters]
    if not any(is_toc_entry_line(line) for line in lines):
        return False
    return all(is_toc_row(line) for line in lines)


def _detach_page_number(paragraph: PdfParagraph, new_debug_id_factory) -> list[PdfParagraph]:
    """Lift a right-margin page number off its title. A year in the sentence stays."""
    ordered = _chars_left_to_right(paragraph_line_chars(paragraph))
    start = _page_number_start(ordered)
    if start is None:
        return [paragraph]
    title = ordered[:start]
    number = [char for char in ordered[start:] if (char.char_unicode or "").strip()]
    if not title or not number:
        return [paragraph]
    _install_chars(paragraph, title)
    return [
        paragraph,
        _paragraph_of_chars(
            paragraph,
            number,
            new_debug_id=new_debug_id_factory(),
            label="toc",
        ),
    ]


def separate_glued_directory_rows(paragraphs, *, new_debug_id_factory) -> None:
    """Give each directory row its own paragraph, and its page number too.

    A section rule and the next entry can land in one paragraph when their
    boxes touch. A title and its page number can land on one line. Body
    text that merely wraps, or a year inside a sentence, stays put.
    """
    if not paragraphs:
        return
    index = 0
    while index < len(paragraphs):
        paragraph = paragraphs[index]
        chars = paragraph_line_chars(paragraph)
        clusters = _baseline_clusters(chars)
        pieces = [paragraph]
        if _directory_baselines(clusters):
            host_label = getattr(paragraph, "layout_label", None)
            _install_chars(paragraph, clusters[0])
            pieces = [paragraph]
            for cluster in clusters[1:]:
                label = "toc" if is_toc_row(_line_from_chars(cluster)) else host_label
                if toc_label_stays(host_label):
                    label = "toc"
                pieces.append(
                    _paragraph_of_chars(
                        paragraph,
                        cluster,
                        new_debug_id=new_debug_id_factory(),
                        label=label,
                    )
                )
        detached: list[PdfParagraph] = []
        for piece in pieces:
            detached.extend(_detach_page_number(piece, new_debug_id_factory))
        if len(detached) == 1:
            index += 1
            continue
        paragraphs[index : index + 1] = detached
        index += len(detached)


def toc_page_number_on_the_right(number: PdfParagraph, body: PdfParagraph) -> bool:
    """True when *number* sits in the right margin, not the left line-number gutter."""
    number_box = getattr(number, "box", None)
    body_box = getattr(body, "box", None)
    if (
        number_box is None
        or body_box is None
        or number_box.x is None
        or body_box.x is None
    ):
        return False
    return float(number_box.x) >= float(body_box.x) + _TOC_PAGE_GAP


_LEADER = re.compile(
    r"(?:_{2,}|\.{2,}|…+|·{2,}|-{3,})"
)
_LEADER_CHAR = frozenset("_.…·-")
_TRAILING_NUMBER = re.compile(r"\s+\d{1,4}\s*$")
_DIGITS = re.compile(r"^\d{1,4}$")


def leader_title_text(text: str | None) -> str | None:
    """Words of a directory row, without the leader or the page number.

    A year inside a sentence is not a leader row.
    """
    raw = (text or "").strip()
    if not raw or not _LEADER.search(raw):
        return None
    without = _LEADER.sub(" ", raw)
    without = _TRAILING_NUMBER.sub("", without)
    title = " ".join(without.split())
    return title or None


def _formula_text(formula) -> str:
    return "".join(
        getattr(char, "char_unicode", None) or ""
        for char in (getattr(formula, "pdf_character", None) or [])
    )


def formula_digit_text(formula) -> str | None:
    """The formula body when it is only a page number."""
    text = _formula_text(formula).strip()
    if _DIGITS.match(text):
        return text
    return None


def paragraph_leader_title(paragraph) -> str | None:
    """Title words from unicode, or from the characters if unicode still has the leader."""
    title = leader_title_text(getattr(paragraph, "unicode", None))
    if title:
        return title
    parts: list[str] = []
    for composition in getattr(paragraph, "pdf_paragraph_composition", None) or []:
        formula = getattr(composition, "pdf_formula", None)
        if formula is not None:
            parts.append(_formula_text(formula))
            continue
        line = getattr(composition, "pdf_line", None)
        chars = getattr(line, "pdf_character", None) if line is not None else None
        if chars:
            parts.append("".join(getattr(c, "char_unicode", None) or "" for c in chars))
    return leader_title_text("".join(parts))


def _char_text(char) -> str:
    return getattr(char, "char_unicode", None) or ""


def _char_x(char) -> float:
    box = _ink_box(char)
    if box is None or box.x is None:
        return 0.0
    return float(box.x)


def _has_leader_run(chars) -> bool:
    ordered = sorted(chars, key=_char_x)
    return bool(_LEADER.search("".join(_char_text(char) for char in ordered)))


def _is_leader_glyph(char) -> bool:
    text = _char_text(char)
    return bool(text) and all(ch in _LEADER_CHAR for ch in text)


def _trailing_page_digits(ordered) -> list:
    """Digits that sit directly behind the leader, not a year in the words."""
    end = len(ordered)
    while end > 0 and not _char_text(ordered[end - 1]).strip():
        end -= 1
    start = end
    while start > 0:
        piece = _char_text(ordered[start - 1]).strip()
        if piece.isascii() and piece.isdigit():
            start -= 1
            continue
        break
    digits = ordered[start:end]
    text = "".join(_char_text(char).strip() for char in digits)
    if not _DIGITS.match(text):
        return []
    prev = start - 1
    while prev >= 0 and not _char_text(ordered[prev]).strip():
        prev -= 1
    if prev < 0 or not _is_leader_glyph(ordered[prev]):
        return []
    return digits


def _strip_leader_formula(formula):
    """Drop the leader and return (leftover chars, page-number chars).

    None when this formula is not a leader row. A digits-only formula
    is not one. Whitespace left after the leader is not a character.
    """
    chars = list(getattr(formula, "pdf_character", None) or [])
    if not _has_leader_run(chars):
        return None
    ordered = sorted(chars, key=_char_x)
    digits = _trailing_page_digits(ordered)
    digit_ids = {id(char) for char in digits}
    remain = [
        char
        for char in chars
        if id(char) not in digit_ids and not _is_leader_glyph(char)
    ]
    if remain and all(not _char_text(char).strip() for char in remain):
        remain = []
    if not digits and len(remain) == len(chars):
        return None
    return remain, digits


def _fit_formula_box(formula, chars) -> None:
    """Shrink a leftover formula to its ink. Never move x left or grow x2."""
    box = getattr(formula, "box", None)
    if box is None:
        return
    xs: list[float] = []
    x2s: list[float] = []
    for char in chars:
        char_box = _ink_box(char)
        if char_box is None or char_box.x is None:
            continue
        xs.append(float(char_box.x))
        x2s.append(float(char_box.x2 if char_box.x2 is not None else char_box.x))
    if not xs:
        return
    ink_x = min(xs)
    ink_x2 = max(x2s)
    if box.x is None or ink_x >= float(box.x):
        box.x = ink_x
    current_x2 = float(box.x2) if box.x2 is not None else None
    if current_x2 is None or ink_x2 < current_x2:
        if box.x is None or ink_x2 >= float(box.x):
            box.x2 = ink_x2


def _line_unicode(paragraph) -> str:
    parts: list[str] = []
    for comp in getattr(paragraph, "pdf_paragraph_composition", None) or []:
        line = getattr(comp, "pdf_line", None)
        if line is None:
            continue
        parts.append("".join(_char_text(char) for char in (line.pdf_character or [])))
    return "".join(parts)


def _rewrite_unicode(paragraph) -> None:
    raw = getattr(paragraph, "unicode", None)
    title = leader_title_text(raw)
    if title:
        paragraph.unicode = title
        return
    if not raw or not _LEADER.search(raw):
        return
    paragraph.unicode = _line_unicode(paragraph)


def _shrink_host_x2(paragraph) -> None:
    """Pull x2 in to the title ink. Never move x, and never grow x2."""
    box = getattr(paragraph, "box", None)
    if box is None or box.x2 is None:
        return
    edges: list[float] = []
    for comp in getattr(paragraph, "pdf_paragraph_composition", None) or []:
        line = getattr(comp, "pdf_line", None)
        formula = getattr(comp, "pdf_formula", None)
        chars = []
        if line is not None and line.pdf_character:
            chars.extend(line.pdf_character)
        if formula is not None and formula.pdf_character:
            chars.extend(formula.pdf_character)
        for char in chars:
            char_box = _ink_box(char)
            if char_box is None or char_box.x2 is None:
                continue
            edges.append(float(char_box.x2))
    if not edges:
        return
    ink = max(edges)
    if ink < float(box.x2) and (box.x is None or ink >= float(box.x)):
        box.x2 = ink


def _detach_one(paragraph, new_debug_id_factory) -> list:
    compositions = list(getattr(paragraph, "pdf_paragraph_composition", None) or [])
    if not compositions:
        return []
    kept = []
    siblings = []
    changed = False
    for comp in compositions:
        formula = getattr(comp, "pdf_formula", None)
        if formula is None:
            kept.append(comp)
            continue
        stripped = _strip_leader_formula(formula)
        if stripped is None:
            kept.append(comp)
            continue
        remain, digits = stripped
        changed = True
        if digits:
            siblings.append(
                _paragraph_of_chars(
                    paragraph,
                    digits,
                    new_debug_id=new_debug_id_factory(),
                    label="toc",
                )
            )
        if not remain:
            continue
        formula.pdf_character = remain
        _fit_formula_box(formula, remain)
        kept.append(comp)
    if not changed:
        return []
    paragraph.pdf_paragraph_composition = kept
    _rewrite_unicode(paragraph)
    _shrink_host_x2(paragraph)
    return siblings


def detach_leader_page_numbers(paragraphs, *, new_debug_id_factory) -> None:
    """Lift a page number out of a leader formula and drop the leader.

    The number is the next paragraph. It is not written back onto the
    title. A formula that is only digits, and a year with no leader, stay.
    """
    if not paragraphs:
        return
    index = 0
    while index < len(paragraphs):
        siblings = _detach_one(paragraphs[index], new_debug_id_factory)
        if not siblings:
            index += 1
            continue
        paragraphs[index + 1 : index + 1] = siblings
        index += 1 + len(siblings)


_BANG = frozenset("!！")
_RESTORE_SLACK = 1.0
_DIGIT_BOX = 16.0
# Cleared at the start of each document. Keyed by debug_id, which survives
# the render. Object ids do not.
_SOURCE: dict[str, float] = {}
# One source leader glyph per directory row, copied into the gap after typesetting.
_LEADERS: dict[str, dict] = {}


def _row_key(paragraph) -> str | None:
    debug_id = getattr(paragraph, "debug_id", None)
    if debug_id:
        return str(debug_id)
    # Synthetic tests build paragraphs with no debug id.
    return f"id:{id(paragraph)}"


def clear_toc_source() -> None:
    """Drop the previous document's source lines and leader glyphs."""
    _SOURCE.clear()
    _LEADERS.clear()


def _on_contents_page(paragraphs) -> bool:
    for paragraph in paragraphs or []:
        if is_toc_paragraph(paragraph) or is_toc_page_header(_text(paragraph)):
            return True
    return False


def _hold(paragraph, on_contents: bool) -> bool:
    """A directory row, or a chapter line on a contents page."""
    if is_toc_paragraph(paragraph):
        return True
    return bool(on_contents and is_chapter_heading(_text(paragraph)))


def _ink_top(paragraph) -> float | None:
    from babeldoc.format.pdf.document_il.utils.rect_flow_stack import ink_lines

    lines = ink_lines(paragraph)
    if not lines:
        return None
    return float(lines[0][0])


def _shift_y(paragraph, dy: float) -> None:
    """Move a row in y, including the visual boxes ``shift_paragraph`` skips."""
    if not dy:
        return
    from babeldoc.format.pdf.document_il.utils.rect_flow_stack import shift_paragraph

    shift_paragraph(paragraph, dy)
    for composition in getattr(paragraph, "pdf_paragraph_composition", None) or []:
        holders = [
            getattr(composition, "pdf_line", None),
            getattr(composition, "pdf_formula", None),
            getattr(composition, "pdf_same_style_characters", None),
        ]
        character = getattr(composition, "pdf_character", None)
        if character is not None:
            holders.append(character)
        for holder in holders:
            if holder is None:
                continue
            chars = [holder] if holder is character else (
                getattr(holder, "pdf_character", None) or []
            )
            for char in chars:
                visual = getattr(char, "visual_bbox", None)
                box = getattr(visual, "box", None) if visual is not None else None
                if box is None or box.y is None or box.y2 is None:
                    continue
                box.y = float(box.y) + dy
                box.y2 = float(box.y2) + dy


def _is_lone_bang(paragraph) -> bool:
    text = _text(paragraph)
    return len(text) == 1 and text in _BANG


def _text(paragraph) -> str:
    return (getattr(paragraph, "unicode", None) or "").strip()


def _drop_bang_chars(paragraph) -> None:
    """The contents bang is its own styled glyph. It is not part of the title."""
    kept = []
    for composition in getattr(paragraph, "pdf_paragraph_composition", None) or []:
        line = getattr(composition, "pdf_line", None)
        if line is not None and getattr(line, "pdf_character", None):
            line.pdf_character = [
                char
                for char in line.pdf_character
                if _char_text(char).strip() not in _BANG
            ]
            if line.pdf_character:
                kept.append(composition)
            continue
        same = getattr(composition, "pdf_same_style_characters", None)
        if same is not None and getattr(same, "pdf_character", None):
            same.pdf_character = [
                char
                for char in same.pdf_character
                if _char_text(char).strip() not in _BANG
            ]
            if same.pdf_character:
                kept.append(composition)
            continue
        character = getattr(composition, "pdf_character", None)
        if character is not None and _char_text(character).strip() in _BANG:
            continue
        kept.append(composition)
    paragraph.pdf_paragraph_composition = kept


def join_or_drop_header_bang(paragraphs) -> None:
    """On a contents page, drop the bang. The header words stay."""
    if not paragraphs:
        return
    headers = [p for p in paragraphs if is_toc_page_header(_text(p))]
    if not headers:
        return
    for header in headers:
        stripped = _text(header).rstrip("!！").rstrip()
        if stripped != _text(header):
            header.unicode = stripped
        _drop_bang_chars(header)
    paragraphs[:] = [p for p in paragraphs if not _is_lone_bang(p)]


def _word_edges(paragraph) -> tuple[float, float] | None:
    """Left and right of the words. Leader glyphs do not count."""
    xs: list[float] = []
    x2s: list[float] = []
    for composition in getattr(paragraph, "pdf_paragraph_composition", None) or []:
        chars = []
        line = getattr(composition, "pdf_line", None)
        formula = getattr(composition, "pdf_formula", None)
        if line is not None and line.pdf_character:
            chars.extend(line.pdf_character)
        if formula is not None and formula.pdf_character:
            chars.extend(formula.pdf_character)
        for char in chars:
            text = _char_text(char).strip()
            if not text or all(ch in _LEADER_CHAR for ch in text):
                continue
            box = _ink_box(char)
            if box is None or box.x is None or box.x2 is None:
                continue
            xs.append(float(box.x))
            x2s.append(float(box.x2))
    if not xs:
        return None
    return min(xs), max(x2s)


def fit_directory_boxes(paragraphs) -> None:
    """Seat each directory row on its own words before typesetting.

    The box is the title, or the page number. Typesetting left-aligns that
    box. A later pass does not have to drag the glyphs out of the leader.
    """
    on_contents = _on_contents_page(paragraphs)
    for paragraph in paragraphs or []:
        if not _hold(paragraph, on_contents):
            continue
        paragraph.alignment = "left"
        box = getattr(paragraph, "box", None)
        if box is None or box.x is None or box.x2 is None:
            continue
        edges = _word_edges(paragraph)
        if edges is not None:
            box.x = edges[0]
            box.x2 = edges[1]
        text = _text(paragraph)
        if text.isdigit() and float(box.x2) - float(box.x) < _DIGIT_BOX:
            box.x2 = float(box.x) + _DIGIT_BOX


def remember_toc_source(paragraphs) -> None:
    """Snapshot the source top after the last directory split."""
    on_contents = _on_contents_page(paragraphs)
    for paragraph in paragraphs or []:
        if not _hold(paragraph, on_contents):
            continue
        key = _row_key(paragraph)
        top = _ink_top(paragraph)
        if key is None or top is None:
            continue
        _SOURCE[key] = top


def _composition_chars(paragraph) -> list:
    chars: list = []
    for composition in getattr(paragraph, "pdf_paragraph_composition", None) or []:
        line = getattr(composition, "pdf_line", None)
        formula = getattr(composition, "pdf_formula", None)
        same = getattr(composition, "pdf_same_style_characters", None)
        if line is not None and line.pdf_character:
            chars.extend(line.pdf_character)
        if formula is not None and formula.pdf_character:
            chars.extend(formula.pdf_character)
        if same is not None and same.pdf_character:
            chars.extend(same.pdf_character)
        character = getattr(composition, "pdf_character", None)
        if character is not None:
            chars.append(character)
    return chars


def _ink_x_span(paragraph) -> tuple[float, float] | None:
    xs: list[float] = []
    x2s: list[float] = []
    for char in _composition_chars(paragraph):
        box = getattr(char, "box", None)
        if box is None or box.x is None or box.x2 is None:
            continue
        xs.append(float(box.x))
        x2s.append(float(box.x2))
    if not xs:
        return None
    return min(xs), max(x2s)


def capture_toc_leaders(paragraphs) -> None:
    """Keep one source leader glyph so the gap can be filled after translation.

    The glyph is not sent to translation. Dots stay dots, underscores stay
    a rule. A row with no leader is left empty.
    """
    for paragraph in paragraphs or []:
        if _DIGITS.match(_text(paragraph)):
            continue
        leaders = [
            char for char in _composition_chars(paragraph) if _is_leader_glyph(char)
        ]
        leader_count = sum(max(1, len(_char_text(char))) for char in leaders)
        # A labeled directory row can be two dots. A rule that was split
        # off its title is not labeled, so it needs a real run.
        if leader_count < 2 or (
            not is_toc_paragraph(paragraph) and leader_count < 4
        ):
            continue
        sample = min(leaders, key=_char_x)
        box = _ink_box(sample)
        text = _char_text(sample)
        if (
            box is None
            or box.x is None
            or box.x2 is None
            or box.y is None
            or box.y2 is None
            or not text
            or getattr(sample, "pdf_style", None) is None
            or getattr(sample, "pdf_character_id", None) is None
        ):
            continue
        glyph = text[0]
        width = (float(box.x2) - float(box.x)) / max(1, len(text))
        if width < 0.8:
            continue
        pitch = _leader_pitch(leaders) or width
        key = _row_key(paragraph)
        if key is None:
            continue
        words = [
            char
            for char in _composition_chars(paragraph)
            if not _is_leader_glyph(char) and _char_text(char).strip()
        ]
        _LEADERS[key] = {
            "unicode": glyph,
            "style": sample.pdf_style,
            "character_id": sample.pdf_character_id,
            "y": float(box.y),
            "y2": float(box.y2),
            "width": width,
            "pitch": pitch,
            "xobj_id": getattr(sample, "xobj_id", None),
            "vertical": getattr(sample, "vertical", None),
            "top": float(
                sample.box.y2
                if getattr(sample, "box", None) is not None
                and sample.box.y2 is not None
                else box.y2
            ),
            "left": min(_char_x(char) for char in words) if words else _char_x(sample),
            "leader_x": _char_x(sample),
        }


def _leader_pitch(leaders) -> float | None:
    """Distance from one leader glyph to the next, not the ink width.

    A period's box is narrower than the gap the English line leaves
    before the next period. Stepping by the box packs the dots.
    """
    ordered = sorted(leaders, key=_char_x)
    steps = []
    for prev, nxt in zip(ordered, ordered[1:], strict=False):
        dx = _char_x(nxt) - _char_x(prev)
        if dx >= 0.8:
            steps.append(dx)
    if not steps:
        return None
    steps.sort()
    return steps[len(steps) // 2]


def _same_line(title, number) -> bool:
    title_top = _ink_top(title)
    number_top = _ink_top(number)
    if title_top is None or number_top is None:
        return False
    return abs(title_top - number_top) <= 6.0


def _leader_only(paragraph) -> bool:
    """A rule that was split off the title. The title paints the gap."""
    visible = [
        char
        for char in _composition_chars(paragraph)
        if _char_text(char).strip()
    ]
    if not visible:
        return False
    return all(
        _is_leader_glyph(char) or _char_text(char).strip().isdigit()
        for char in visible
    )


def _stamp_for(paragraph):
    """The source leader for this row.

    debug_id is the usual key. A row whose id changed still matches the
    source top recorded before typesetting.
    """
    key = _row_key(paragraph)
    if key is not None and key in _LEADERS:
        return _LEADERS[key]
    top = _ink_top(paragraph)
    span = _ink_x_span(paragraph)
    if top is None or span is None:
        return None
    best = None
    best_dy = 12.0
    for stamp in _LEADERS.values():
        dy = abs(float(stamp["top"]) - top)
        if dy >= best_dy:
            continue
        leader_x = float(stamp.get("leader_x", stamp["left"]))
        # The title sits to the left of the rule. A rule that was split
        # into its own paragraph still belongs to that title.
        if span[1] > leader_x + 8.0 or span[0] > leader_x:
            continue
        best = stamp
        best_dy = dy
    return best


def _gap_before_page_number(paragraph, numbers):
    """Right edge of the title and left edge of its page number.

    The number is its own paragraph, or the trailing digits of this one
    when they sit at least 24pt to the right of the words.
    """
    chars = [
        char
        for char in _composition_chars(paragraph)
        if _ink_box(char) is not None and not _is_leader_glyph(char)
    ]
    chars.sort(key=_char_x)
    title_right = None
    number_left = None
    end = len(chars)
    while end > 0 and not _char_text(chars[end - 1]).strip():
        end -= 1
    start = end
    while start > 0 and _char_text(chars[start - 1]).strip().isdigit():
        start -= 1
    digits = chars[start:end]
    digit_text = "".join(_char_text(char).strip() for char in digits)
    if _DIGITS.match(digit_text) and start > 0:
        prev = _ink_box(chars[start - 1])
        first = _ink_box(digits[0])
        if (
            prev is not None
            and first is not None
            and prev.x2 is not None
            and first.x is not None
            and float(first.x) - float(prev.x2) >= _TOC_PAGE_GAP
        ):
            rights = [
                float(_ink_box(char).x2)
                for char in chars[:start]
                if _ink_box(char) is not None and _ink_box(char).x2 is not None
            ]
            if rights:
                title_right = max(rights)
                number_left = float(first.x)
    span = _ink_x_span(paragraph)
    if title_right is None and span is not None:
        title_right = span[1]
    if number_left is None and title_right is not None:
        for candidate in numbers:
            edge = _ink_x_span(candidate)
            if edge is None or not _same_line(paragraph, candidate):
                continue
            if edge[0] <= title_right:
                continue
            if number_left is None or edge[0] < number_left:
                number_left = edge[0]
    if title_right is None or number_left is None:
        return None
    return title_right, number_left


_ELLIPSIS = frozenset("…⋯")
_ONE_DOT = frozenset(".·∙•")


def _period_step(stamps) -> float | None:
    """Step of a real period leader, so an ellipsis row can match it."""
    steps = [
        float(stamp.get("pitch") or stamp["width"])
        for stamp in stamps
        if stamp.get("unicode") == "." and float(stamp.get("pitch") or stamp["width"]) >= 0.8
    ]
    if not steps:
        return None
    return min(steps)


def _paint_glyph(stamp, period_step: float | None) -> tuple[str, float]:
    """Draw every dot leader as a period.

    An ellipsis is one source glyph standing in for several periods.
    Painting it as itself makes that row a different, wider dot.
    """
    glyph = stamp["unicode"]
    step = float(stamp.get("pitch") or stamp["width"])
    if glyph not in _ELLIPSIS and glyph not in _ONE_DOT:
        return glyph, step
    if period_step is not None:
        return ".", period_step
    if glyph in _ELLIPSIS:
        return ".", max(0.8, step / 3.0)
    return ".", step


def paint_toc_leaders(paragraphs, glyph_for=None) -> None:
    """Repeat the source leader from the title to the page number.

    Each glyph is its own character composition. The PDF writer does not
    emit a line composition, so a line of dots never reaches the page.
    ``glyph_for`` maps the leader onto the font the title is already
    drawn with. Without it, the source glyph is used.
    """
    if not paragraphs or not _LEADERS:
        return
    numbers = [p for p in paragraphs if _DIGITS.match(_text(p))]
    period_step = _period_step(_LEADERS.values())
    added = []
    used = set()
    for paragraph in list(paragraphs):
        if _DIGITS.match(_text(paragraph)) or _leader_only(paragraph):
            continue
        stamp = _stamp_for(paragraph)
        if stamp is None:
            continue
        stamp_id = id(stamp)
        if stamp_id in used:
            continue
        gap = _gap_before_page_number(paragraph, numbers)
        if gap is None:
            continue
        title_right, number_left = gap
        glyph, width = _paint_glyph(stamp, period_step)
        start = title_right + width
        stop = number_left - width
        if stop - start < width:
            continue
        style = stamp["style"]
        character_id = stamp["character_id"]
        anchor = next(
            (
                char
                for char in _composition_chars(paragraph)
                if _ink_box(char) is not None and not _is_leader_glyph(char)
            ),
            None,
        )
        anchor_box = _ink_box(anchor) if anchor is not None else None
        baseline = float(anchor_box.y) if anchor_box is not None else float(stamp["y"])
        height = max(0.8, float(stamp["y2"]) - float(stamp["y"]))
        if glyph_for is not None and anchor is not None and anchor.pdf_style is not None:
            mapped = glyph_for(anchor.pdf_style.font_id, glyph)
            if mapped is not None:
                style = PdfStyle(
                    font_id=mapped[0],
                    font_size=anchor.pdf_style.font_size or style.font_size,
                    graphic_state=style.graphic_state or anchor.pdf_style.graphic_state,
                )
                character_id = mapped[1]
        chars = []
        x = start
        guard = 0
        while x + width <= stop + 0.2 and guard < 240:
            box = Box(x=x, y=baseline, x2=x + width, y2=baseline + height)
            chars.append(
                PdfCharacter(
                    pdf_style=style,
                    box=box,
                    visual_bbox=VisualBbox(box=Box(x=x, y=baseline, x2=x + width, y2=baseline + height)),
                    char_unicode=glyph,
                    pdf_character_id=character_id,
                    vertical=False,
                ),
            )
            x += width
            guard += 1
        if not chars:
            continue
        used.add(stamp_id)
        line_box = Box(
            x=chars[0].box.x,
            y=baseline,
            x2=chars[-1].box.x2,
            y2=baseline + height,
        )
        added.append(
            PdfParagraph(
                box=line_box,
                pdf_paragraph_composition=[
                    PdfParagraphComposition(pdf_character=char) for char in chars
                ],
                unicode=glyph * len(chars),
                layout_label="toc",
                pdf_style=style,
                debug_id=f"{_row_key(paragraph)}-leader",
            ),
        )
    paragraphs.extend(added)


def pin_toc_row_baselines(paragraphs) -> None:
    """Put each contents row back on the source line recorded before typesetting."""
    on_contents = _on_contents_page(paragraphs)
    for paragraph in paragraphs or []:
        if not _hold(paragraph, on_contents) or paragraph.box is None:
            continue
        key = _row_key(paragraph)
        top = _ink_top(paragraph)
        source = _SOURCE.get(key) if key is not None else None
        if source is None or top is None:
            continue
        delta = float(source) - top
        if abs(delta) <= _RESTORE_SLACK:
            continue
        _shift_y(paragraph, delta)
