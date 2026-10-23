"""Join paragraphs the seal already keeps in one block.

The cut is the same one the frame uses. This does not name a paradigm
and does not change the seal. A leader stays its own paragraph. A block
the seal opened apart stays apart.
"""

from __future__ import annotations

import re

from babeldoc.format.pdf.document_il import Box
from babeldoc.format.pdf.document_il.utils.layout_plan.seal import seal_lines
from babeldoc.format.pdf.document_il.utils.rect_flow_stack import _lines_of

_TOC_LEADER_RE = re.compile(
    r"(?:\.{3,}|_{3,}|\-{3,}|\.(?:\s*\.){3,})\s*\d+",
    re.MULTILINE,
)
_HEADING_PATTERN = re.compile(
    r"^(?:part|chapter|section|technique|step|volume|book|act|appendix|bonus)\s+\d+[:\s\.]",
    re.IGNORECASE,
)


def _has_list_marker(paragraph) -> bool:
    from babeldoc.format.pdf.document_il.utils.layout_helper import BULLET_POINT_PATTERN
    from babeldoc.format.pdf.document_il.utils.list_marker_repair import LIST_MARKER_RE
    from babeldoc.format.pdf.document_il.utils.paragraph_split_policy import (
        paragraph_starts_with_list_marker,
    )
    from babeldoc.format.pdf.document_il.utils.rect_flow_stack import _marker_of

    m = _marker_of(paragraph)
    if m is not None and getattr(m, "is_bullet", False):
        return True
    if paragraph_starts_with_list_marker(paragraph):
        return True
    text = (getattr(paragraph, "unicode", None) or "").strip()
    if text:
        if BULLET_POINT_PATTERN.match(text[0]):
            return True
        if LIST_MARKER_RE.match(text):
            return True
    return False


def _is_toc(paragraph) -> bool:
    intent = getattr(paragraph, "layout_intent", None)
    role = getattr(intent, "role", None) if intent is not None else None
    role_val = getattr(role, "value", role) if role is not None else None
    if role_val == "toc" or getattr(paragraph, "layout_label", None) == "toc":
        return True
    text = (getattr(paragraph, "unicode", None) or "").strip()
    if bool(_TOC_LEADER_RE.search(text)):
        return True
    return False


def _role_of_para(paragraph) -> str | None:
    intent = getattr(paragraph, "layout_intent", None)
    role = getattr(intent, "role", None) if intent is not None else None
    return getattr(role, "value", role) if role is not None else getattr(paragraph, "layout_label", None)


def _should_not_join(prev, curr) -> bool:
    if _is_toc(prev) or _is_toc(curr):
        return True
    if _has_list_marker(curr):
        return True
    t_prev = (getattr(prev, "unicode", None) or "").strip()
    t_curr = (getattr(curr, "unicode", None) or "").strip()
    if bool(_HEADING_PATTERN.match(t_curr)) or bool(_HEADING_PATTERN.match(t_prev)):
        return True
    role_prev = _role_of_para(prev)
    role_curr = _role_of_para(curr)
    if role_prev != role_curr and (role_prev is not None or role_curr is not None):
        return True
    if role_prev in (
        "title",
        "heading",
        "toc",
        "chrome",
        "caption",
        "pull_quote",
        "callout",
        "formula",
    ):
        return True
    return False


def join_sealed_paragraphs(page) -> None:
    """Make each sealed block one paragraph before the plan is frozen."""
    paragraphs = list(getattr(page, "pdf_paragraph", None) or [])
    if len(paragraphs) < 2:
        return
    records, pool = _records(paragraphs)
    if len(pool) < 2:
        return
    block_of = _body_blocks(pool)
    grouped: dict[str, list] = {}
    for paragraph, lines in records:
        block_id = _own_block(lines, block_of)
        if block_id is None:
            continue
        grouped.setdefault(block_id, []).append(paragraph)
    remove: set[int] = set()
    for group in grouped.values():
        if len(group) < 2:
            continue
        ordered = sorted(group, key=lambda item: _top(item, records), reverse=True)
        chunks: list[list] = [[ordered[0]]]
        for nxt in ordered[1:]:
            if _should_not_join(chunks[-1][-1], nxt):
                chunks.append([nxt])
            else:
                chunks[-1].append(nxt)
        for chunk in chunks:
            if len(chunk) < 2:
                continue
            _absorb(chunk[0], chunk[1:])
            remove.update(id(item) for item in chunk[1:])
    if not remove:
        return
    page.pdf_paragraph = [
        paragraph for paragraph in paragraphs if id(paragraph) not in remove
    ]


def _records(paragraphs):
    records = []
    pool = []
    for paragraph in paragraphs:
        lines = _lines_of(paragraph)
        records.append((paragraph, lines))
        pool.extend(lines)
    return records, pool


def _body_blocks(pool) -> dict[int, str]:
    found: dict[int, str] = {}
    for block in seal_lines(pool):
        for line in block.lines:
            found[id(line)] = block.block_id
    return found


def _own_block(lines, block_of) -> str | None:
    """The one sealed block that owns this paragraph's body lines."""
    found = [block_of[id(line)] for line in lines if id(line) in block_of]
    if not found or any(item != found[0] for item in found):
        return None
    return found[0]


def _top(paragraph, records) -> float:
    for item, lines in records:
        if item is paragraph and lines:
            return max(line.y0 for line in lines)
    return float("-inf")


def _absorb(host, others) -> None:
    compositions = list(getattr(host, "pdf_paragraph_composition", None) or [])
    texts = [getattr(host, "unicode", None) or ""]
    boxes = []
    if getattr(host, "box", None) is not None:
        boxes.append(host.box)
    for other in others:
        compositions.extend(getattr(other, "pdf_paragraph_composition", None) or [])
        texts.append(getattr(other, "unicode", None) or "")
        if getattr(other, "box", None) is not None:
            boxes.append(other.box)
    host.pdf_paragraph_composition = compositions
    host.unicode = _join_text(texts)
    if boxes:
        host.box = Box(
            min(float(box.x) for box in boxes),
            min(float(box.y) for box in boxes),
            max(float(box.x2) for box in boxes),
            max(float(box.y2) for box in boxes),
        )


def _join_text(parts) -> str:
    text = ""
    for part in parts:
        piece = (part or "").strip()
        if not piece:
            continue
        if not text:
            text = piece
            continue
        if text[-1].isspace() or piece[0].isspace():
            text += piece
            continue
        text = f"{text} {piece}"
    return text
