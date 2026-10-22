"""Put a sliced line-end back on the line it continues.

A glyph run sometimes becomes its own paragraph while still sitting on
the same baseline, with its left edge touching the line it was cut from.
The plan then sees a short line and misses the real right edge. This
puts those glyphs back. A gap stays two paragraphs. This does not name
a paradigm.
"""

from __future__ import annotations

from babeldoc.format.pdf.document_il.utils.layout_helper import get_paragraph_unicode

_SAME_BASELINE = 0.8
_TOUCH = 2.0


def stitch_abutting_line_tails(page) -> None:
    """Absorb a paragraph whose every line continues another line."""
    paragraphs = list(getattr(page, "pdf_paragraph", None) or [])
    if len(paragraphs) < 2:
        return
    hosts = _line_index(paragraphs)
    remove: set[int] = set()
    touched: set[int] = set()
    for paragraph in paragraphs:
        lines = _pure_lines(paragraph)
        if not lines:
            continue
        targets = _targets(lines, hosts, paragraph)
        if targets is None:
            continue
        for line, host_line in zip(lines, targets, strict=True):
            _splice(host_line, line)
            touched.add(id(host_line))
        remove.add(id(paragraph))
    if not remove:
        return
    page.pdf_paragraph = [
        paragraph for paragraph in paragraphs if id(paragraph) not in remove
    ]
    for paragraph in page.pdf_paragraph:
        own = _pure_lines(paragraph) or []
        if any(id(line) in touched for line in own):
            _fit_paragraph(paragraph)
            _rewrite_unicode(paragraph)


def _targets(lines, hosts, paragraph):
    found = []
    for line in lines:
        host = _host_for(line, hosts, paragraph)
        if host is None:
            return None
        found.append(host)
    return found


def _line_index(paragraphs):
    indexed = []
    for paragraph in paragraphs:
        for line in _pure_lines(paragraph) or []:
            indexed.append((paragraph, line))
    return indexed


def _pure_lines(paragraph):
    """Line boxes only. A formula or loose glyph keeps the paragraph whole."""
    found = []
    for composition in getattr(paragraph, "pdf_paragraph_composition", None) or []:
        line = getattr(composition, "pdf_line", None)
        box = getattr(line, "box", None) if line is not None else None
        if box is not None and None not in (box.x, box.x2, box.y2):
            found.append(line)
            continue
        if _loose_glyphs(composition):
            return None
    return found


def _loose_glyphs(composition) -> bool:
    formula = getattr(composition, "pdf_formula", None)
    if formula is not None and getattr(formula, "pdf_character", None):
        return True
    character = getattr(composition, "pdf_character", None)
    if character is not None:
        return True
    same = getattr(composition, "pdf_same_style_characters", None)
    return bool(same is not None and getattr(same, "pdf_character", None))


def _host_for(line, hosts, paragraph):
    box = line.box
    best = None
    best_gap = None
    for host_paragraph, host_line in hosts:
        if host_paragraph is paragraph:
            continue
        host = host_line.box
        if abs(float(host.y2) - float(box.y2)) > _SAME_BASELINE:
            continue
        if float(box.x) <= float(host.x) + 8.0:
            continue
        gap = float(box.x) - float(host.x2)
        if gap < -_TOUCH or gap > _TOUCH:
            continue
        if best_gap is None or abs(gap) < best_gap:
            best = host_line
            best_gap = abs(gap)
    return best


def _splice(host_line, tail_line) -> None:
    host_chars = list(getattr(host_line, "pdf_character", None) or [])
    tail_chars = list(getattr(tail_line, "pdf_character", None) or [])
    if tail_chars:
        host_chars.extend(tail_chars)
        host_chars.sort(key=_char_x)
        host_line.pdf_character = host_chars
    host = host_line.box
    tail = tail_line.box
    host.x = min(float(host.x), float(tail.x))
    host.x2 = max(float(host.x2), float(tail.x2))
    host.y = min(float(host.y), float(tail.y))
    host.y2 = max(float(host.y2), float(tail.y2))
    xs = [float(host.x2)]
    ys = [float(host.y), float(host.y2)]
    x0s = [float(host.x)]
    for char in host_chars:
        for box in _char_boxes(char):
            x0s.append(float(box.x))
            xs.append(float(box.x2))
            if box.y is not None and box.y2 is not None:
                ys.append(float(box.y))
                ys.append(float(box.y2))
    host.x = min(x0s)
    host.x2 = max(xs)
    host.y = min(ys)
    host.y2 = max(ys)


def _char_boxes(char):
    boxes = []
    raw = getattr(char, "box", None)
    visual = getattr(getattr(char, "visual_bbox", None), "box", None)
    for box in (raw, visual):
        if box is None or box.x is None or box.x2 is None:
            continue
        boxes.append(box)
    return boxes


def _char_x(char) -> float:
    boxes = _char_boxes(char)
    if not boxes:
        return 0.0
    return min(float(box.x) for box in boxes)


def _fit_paragraph(paragraph) -> None:
    lines = _pure_lines(paragraph) or []
    box = getattr(paragraph, "box", None)
    if box is None or not lines:
        return
    box.x = min(float(line.box.x) for line in lines)
    box.x2 = max(float(line.box.x2) for line in lines)
    box.y = min(min(float(line.box.y), float(line.box.y2)) for line in lines)
    box.y2 = max(max(float(line.box.y), float(line.box.y2)) for line in lines)


def _rewrite_unicode(paragraph) -> None:
    chars = []
    for composition in getattr(paragraph, "pdf_paragraph_composition", None) or []:
        line = getattr(composition, "pdf_line", None)
        if line is None:
            continue
        chars.extend(getattr(line, "pdf_character", None) or [])
    if not chars:
        return
    paragraph.unicode = get_paragraph_unicode(paragraph)
