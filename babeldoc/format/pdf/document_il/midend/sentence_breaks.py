"""Break inside one frame on sentences, not on each English line width.

A rag stores the scanned edges as a frame. Chinese keeps its own word
order. A sentence end is a break. An English line that itself ends on
punctuation is a break at the matching Chinese punctuation. Anything
wider than the frame wraps at a legal point.
"""

from __future__ import annotations

from collections.abc import Sequence

_CLASS = {
    "。": "stop",
    "．": "stop",
    ".": "stop",
    "？": "stop",
    "?": "stop",
    "！": "stop",
    "!": "stop",
    "；": "stop",
    ";": "stop",
    "，": "comma",
    ",": "comma",
    "、": "comma",
    "：": "colon",
    ":": "colon",
}
_DASH = "—–‑"
_QUOTES = " \t\"'“”‘’「」『』"
_STRONG = frozenset({"stop"})
# A wrap that is one or two characters short of these ends on the mark.
_CLOSE = frozenset("。．.？?！!；;，,、：:")
_SKIP = frozenset(" \t\"'“”‘’「」『』）】》〉〕］｝")


def source_lines_of(paragraph) -> tuple[str, ...]:
    """English lines captured before translation, blanks dropped."""
    metrics = getattr(paragraph, "reference_metrics", None)
    texts = getattr(metrics, "line_texts", None) if metrics is not None else None
    if not texts:
        return ()
    return tuple(text.strip() for text in texts if text and text.strip())


def next_line_starts(breaks: Sequence[int] | None, count: int) -> list[int] | None:
    """First unit of each following line.

    ``breaks`` names the last unit of a line. The placer breaks before
    the index it is given. Passing the period itself starts the next
    line on that period, and the line-start rule then pulls the
    character before it down.
    """
    if not breaks or count <= 1:
        return None
    starts = [index + 1 for index in breaks if 0 <= index < count - 1]
    return starts or None


def sentence_line_breaks(
    units: Sequence,
    frame_width: float,
    scale: float,
    source_lines: Sequence[str] = (),
    decorative_tracking: float = 0.0,
) -> list[int] | None:
    """Unit indexes to break after. None when the frame holds one line."""
    if frame_width <= 0 or len(units) <= 1:
        return None
    widths, can_break, chars = _specs(units, scale, decorative_tracking)
    marks = _marks(chars)
    stops = set(_strong_breaks(marks))
    stops.update(_aligned_breaks(source_lines, marks))
    ordered = [index for index in sorted(stops) if 0 <= index < len(units) - 1]
    points = [-1, *ordered, len(units) - 1]
    cuts: list[int] = []
    for start_at, stop_at in zip(points, points[1:], strict=False):
        start = start_at + 1
        cuts.extend(
            _wrap(widths, can_break, chars, start, stop_at, frame_width)
        )
        if stop_at < len(units) - 1:
            cuts.append(stop_at)
    return cuts or None


def _specs(units, scale, tracking):
    widths = []
    can_break = []
    chars = []
    for unit in units:
        width = float(unit.width) * scale
        if tracking and not unit.is_space:
            width += tracking
        widths.append(width)
        can_break.append(bool(unit.can_break_line))
        text = unit.try_get_unicode() or ""
        chars.append(text)
    return widths, can_break, chars


def _marks(chars: Sequence[str]) -> list[tuple[str, int]]:
    found = []
    for index, char in enumerate(chars):
        kind = _CLASS.get(char)
        if kind is None and char in _DASH:
            kind = "dash"
        if kind is not None:
            found.append((kind, index))
    return found


def _strong_breaks(marks: Sequence[tuple[str, int]]) -> list[int]:
    return [index for kind, index in marks if kind in _STRONG]


def _aligned_breaks(
    source_lines: Sequence[str], marks: Sequence[tuple[str, int]]
) -> list[int]:
    """Breaks where an English line ended on punctuation."""
    cursor = 0
    breaks = []
    for line in source_lines:
        tokens = _punctuation(line)
        if not tokens:
            continue
        found = _find_tokens(marks, cursor, tokens)
        if found is None:
            continue
        last, cursor = found
        if _ends_on_punctuation(line):
            breaks.append(last)
    return breaks


def _find_tokens(
    marks: Sequence[tuple[str, int]], cursor: int, tokens: Sequence[str]
) -> tuple[int, int] | None:
    """Match one line's punctuation. Return the last unit and the next cursor."""
    limit = min(len(marks), cursor + 6)
    for origin in range(cursor, limit):
        pos = origin
        last = None
        matched = True
        for token in tokens:
            hit = _next_mark(marks, pos, token)
            if hit is None:
                matched = False
                break
            last = marks[hit][1]
            pos = hit + 1
        if matched and last is not None:
            return last, pos
    return None


def _next_mark(
    marks: Sequence[tuple[str, int]], pos: int, token: str
) -> int | None:
    end = min(len(marks), pos + 4)
    for index in range(pos, end):
        if _compatible(token, marks[index][0]):
            return index
    return None


def _compatible(left: str, right: str) -> bool:
    if left == right:
        return True
    return {left, right} <= {"dash", "comma"}


def _punctuation(text: str) -> list[str]:
    tokens: list[str] = []
    index = 0
    while index < len(text):
        if text.startswith("...", index) or text.startswith("…", index):
            index += 3 if text.startswith("...", index) else 1
            continue
        if text.startswith("--", index):
            tokens.append("dash")
            index += 2
            continue
        char = text[index]
        if char in _DASH:
            if not tokens or tokens[-1] != "dash":
                tokens.append("dash")
            index += 1
            continue
        kind = _CLASS.get(char)
        if kind is not None:
            tokens.append(kind)
        index += 1
    return tokens


def _ends_on_punctuation(text: str) -> bool:
    stripped = text.rstrip(_QUOTES)
    if not stripped or stripped.endswith("...") or stripped.endswith("…"):
        return False
    if stripped.endswith("--") or stripped[-1] in _DASH:
        return True
    return stripped[-1] in _CLASS


def close_ahead(
    chars: Sequence[str],
    index: int,
    stop: int | None = None,
    max_content: int = 2,
) -> int | None:
    """Index of a 。 or ， within ``max_content`` characters of ``index``.

    The line is short by one or two characters. The returned index is
    the punctuation, plus a quote sitting on it, so the line can end there.
    """
    if stop is None:
        stop = len(chars) - 1
    if index < 0 or index > stop or max_content < 0:
        return None
    content = 0
    cursor = index
    while cursor <= stop:
        char = chars[cursor]
        if not char or char in _SKIP:
            cursor += 1
            continue
        if char in _CLOSE:
            end = cursor
            nxt = cursor + 1
            while nxt <= stop and (
                not chars[nxt] or chars[nxt] in _SKIP or chars[nxt] in _CLOSE
            ):
                end = nxt
                nxt += 1
            return end
        content += 1
        if content > max_content:
            return None
        cursor += 1
    return None


def _previous_close(chars: Sequence[str], start: int, before: int) -> int | None:
    """A 。 or ， already on this line, before the character that does not fit."""
    cursor = before - 1
    while cursor > start:
        if chars[cursor] in _CLOSE:
            end = cursor
            nxt = cursor + 1
            while nxt < before and (
                not chars[nxt] or chars[nxt] in _SKIP
            ):
                end = nxt
                nxt += 1
            return end
        cursor -= 1
    return None


def _wrap(
    widths, can_break, chars, start: int, stop: int, limit: float
) -> list[int]:
    """Legal cuts inside one segment that is wider than the frame.

    A cut that would leave one or two characters in front of 。 or ，
    moves onto that mark instead.
    """
    cuts = []
    index = start
    guard = 0
    while index <= stop and guard <= len(widths):
        guard += 1
        used = 0.0
        last_cut = None
        filled = index
        cursor = index
        overflow = False
        while cursor <= stop:
            if cursor > index and used + widths[cursor] > limit:
                overflow = True
                break
            used += widths[cursor]
            if can_break[cursor]:
                last_cut = cursor
            filled = cursor
            cursor += 1
        if not overflow or filled >= stop:
            break
        close = close_ahead(chars, cursor, stop)
        if close is not None:
            if close >= stop:
                break
            cut = close
        else:
            earlier = _previous_close(chars, index, cursor)
            if earlier is not None and earlier > index:
                cut = earlier
            else:
                cut = last_cut if last_cut is not None else filled
        if cut < index:
            cut = index
        if cut >= stop:
            break
        cuts.append(cut)
        index = cut + 1
    return cuts
