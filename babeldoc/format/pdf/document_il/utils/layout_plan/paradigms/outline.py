"""Edge walks used by the catalog claims.

Each walk judges its own geometry. It does not call another claim.
Steps under 4pt do not count as a turn. ``one_direction`` is unchanged.
"""

from __future__ import annotations

from collections.abc import Sequence

from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.contract import (
    BlockEdges,
)

_SLACK = 4.0
_WALL = 8.0
_COLUMN = 16.0
_LEG = 24.0
_STEP_GAP = 32.0
_STEP_INNER = 20.0
_HANG_MIN = 12.0
_HANG_DEEP = 48.0
_SHORT = 24.0


def light_column(edges: BlockEdges, lines: Sequence[Sequence[float]]) -> float | None:
    """Wider wall span. One line may miss a 16pt wall. A shelf is not a wall."""
    if edges.marker != "none" or edges.full_count < 2 or len(lines) < 2:
        return None
    if _hang_indent(lines) is not None or _repeated_indent(lines) is not None:
        return None
    lefts = _coord(lines, 0)
    rights = _coord(lines, 1)
    left_outer = min(lefts)
    right_outer = max(rights)
    left_miss = [value for value in lefts if value - left_outer > _COLUMN]
    right_miss = [value for value in rights if right_outer - value > _COLUMN]
    if len(left_miss) > 1 or len(right_miss) > 1:
        return None
    kept_left = [value for value in lefts if value - left_outer <= _COLUMN]
    kept_right = [value for value in rights if right_outer - value <= _COLUMN]
    if len(kept_left) < 2 or len(kept_right) < 2:
        return None
    return max(_span(kept_left), _span(kept_right))


def right_rag(edges: BlockEdges, lines: Sequence[Sequence[float]]) -> float | None:
    """Left-edge span. The right edge folds more than once and is not a step."""
    return _rag(edges, lines, free=1)


def left_rag(edges: BlockEdges, lines: Sequence[Sequence[float]]) -> float | None:
    """Right-edge span. The left edge folds more than once and is not a step."""
    return _rag(edges, lines, free=0)


def right_step(
    edges: BlockEdges, lines: Sequence[Sequence[float]], kind: str
) -> float | None:
    """Left-edge span when the right edge is the named two-width walk.

    The first line may sit to the right of a straight shelf. A first
    line to the left of that shelf is a hang, not this walk.
    """
    if edges.marker != "none":
        return None
    body = _strip_short_tail(lines)
    if len(body) < 4:
        return None
    lefts = _coord(body, 0)
    rights = _coord(body, 1)
    wall = _shelf_span(lefts)
    if wall is None:
        return None
    if _step_kind(rights) != kind:
        return None
    return wall


def right_bow(
    edges: BlockEdges, lines: Sequence[Sequence[float]], kind: str
) -> float | None:
    """Left-edge span when the right edge makes one deep turn."""
    if edges.marker != "none":
        return None
    body = _strip_short_tail(lines)
    lefts = _coord(body, 0)
    rights = _coord(body, 1)
    if _span(lefts) > _WALL or _off_wall(rights, off_is_low=True) < 2:
        return None
    if _bow_kind(rights) != kind:
        return None
    return _span(lefts)


def hang(
    edges: BlockEdges, lines: Sequence[Sequence[float]], band: str
) -> float | None:
    """Flatness of a plain hanging indent. ``band`` is shallow, deep, or repeated."""
    if edges.marker != "none":
        return None
    return _hang_band(lines, band)


def marked(
    edges: BlockEdges, lines: Sequence[Sequence[float]], marker: str, kind: str
) -> float | None:
    """Left-edge residual for one bullet or serial walk."""
    if edges.marker != marker:
        return None
    if kind == "plain":
        if _hang_indent(lines) is not None or _repeated_indent(lines) is not None:
            return None
        body = _strip_short_tail(lines)
        if len(body) < 3:
            return None
        lefts = _coord(body, 0)
        if _span(lefts) > _WALL:
            return None
        return _span(lefts)
    return _hang_band(lines, kind)


def wider_below(edges: BlockEdges, lines: Sequence[Sequence[float]]) -> float | None:
    """How far the two outward travels differ.

    Both edges open downward across at least two steps, and two lines on
    each edge clear the 16pt wall. One jump is not this shape. A repeated
    hang on the left is not this shape either.
    """
    if edges.marker != "none" or _repeated_indent(lines) is not None:
        return None
    body = _strip_short_tail(lines)
    if len(body) < 5:
        return None
    lefts = _coord(body, 0)
    rights = _coord(body, 1)
    if _turn_count(lefts) or _turn_count(rights):
        return None
    if not _opens_downward(lefts, decreasing=True):
        return None
    if not _opens_downward(rights, decreasing=False):
        return None
    left_travel = lefts[0] - lefts[-1]
    right_travel = rights[-1] - rights[0]
    if left_travel < _LEG or right_travel < _LEG:
        return None
    return abs(left_travel - right_travel)


def _outward_steps(values: Sequence[float], *, decreasing: bool) -> int:
    want = -1 if decreasing else 1
    return sum(sign == want for sign in _directions(values))


def _opens_downward(values: Sequence[float], *, decreasing: bool) -> bool:
    if _outward_steps(values, decreasing=decreasing) < 2:
        return False
    return _off_wall(values, off_is_low=not decreasing) >= 2


def _hang_band(lines: Sequence[Sequence[float]], band: str) -> float | None:
    repeated = _repeated_indent(lines)
    if band == "repeated":
        if repeated is None:
            return None
        return repeated
    if repeated is not None:
        return None
    indent = _hang_indent(lines)
    if indent is None:
        return None
    if band == "shallow" and indent >= _HANG_DEEP:
        return None
    if band == "deep" and indent < _HANG_DEEP:
        return None
    if band not in {"shallow", "deep", "any"}:
        return None
    return _plateau_span(lines)


def _rag(
    edges: BlockEdges, lines: Sequence[Sequence[float]], free: int
) -> float | None:
    if edges.marker != "none":
        return None
    if free == 0 and _repeated_indent(lines) is not None:
        return None
    body = _strip_short_tail(lines)
    if len(body) < 3:
        return None
    pinned = _coord(body, 1 - free)
    moving = _coord(body, free)
    if not _is_rag_edge(pinned, moving, stray_is_low=(free == 1)):
        return None
    return _span(pinned)


def _is_rag_edge(
    pinned: Sequence[float], moving: Sequence[float], *, stray_is_low: bool
) -> bool:
    if _span(pinned) > _WALL:
        return False
    if _span_without_one_stray(moving, stray_is_low=stray_is_low) <= _COLUMN:
        return False
    if _turn_count(moving) < 2:
        return False
    if _step_kind(moving) is not None or _bow_kind(moving) is not None:
        return False
    return True


def _span_without_one_stray(values: Sequence[float], *, stray_is_low: bool) -> float:
    if len(values) < 3:
        return _span(values)
    if stray_is_low:
        stray = min(range(len(values)), key=values.__getitem__)
    else:
        stray = max(range(len(values)), key=values.__getitem__)
    rest = [value for index, value in enumerate(values) if index != stray]
    return _span(rest)


def _off_wall(values: Sequence[float], *, off_is_low: bool) -> int:
    if len(values) == 0:
        return 0
    if off_is_low:
        outer = max(values)
        return sum(outer - value > _COLUMN for value in values)
    outer = min(values)
    return sum(value - outer > _COLUMN for value in values)


def _strip_short_tail(
    lines: Sequence[Sequence[float]],
) -> list[Sequence[float]]:
    kept = list(lines)
    dropped = 0
    while len(kept) >= 3 and dropped < 2:
        last = kept[-1]
        previous = kept[-2]
        right_inset = float(previous[1]) - float(last[1])
        left_out = float(previous[0]) - float(last[0])
        if right_inset >= _SHORT and left_out <= _WALL:
            kept.pop()
            dropped += 1
            continue
        break
    return kept


def _coord(lines: Sequence[Sequence[float]], index: int) -> list[float]:
    return [float(line[index]) for line in lines]


def _span(values: Sequence[float]) -> float:
    if len(values) == 0:
        return 0.0
    return max(values) - min(values)


def _shelf_span(lefts: Sequence[float]) -> float | None:
    """Span of a straight left wall.

    One opening line may sit to the right. The shelf is the rest. A
    first line left of the shelf, or a shelf that walks, is not straight.
    """
    if _span(lefts) <= _WALL:
        return _span(lefts)
    if len(lefts) < 2:
        return None
    shelf = lefts[1:]
    if _span(shelf) > _WALL:
        return None
    if lefts[0] < min(shelf) - _SLACK:
        return None
    return _span(shelf)


def _median(values: Sequence[float]) -> float:
    ordered = sorted(values)
    return ordered[len(ordered) // 2]


def _directions(values: Sequence[float]) -> list[int]:
    signs: list[int] = []
    for index in range(len(values) - 1):
        delta = values[index + 1] - values[index]
        if abs(delta) <= _SLACK:
            continue
        signs.append(1 if delta > 0.0 else -1)
    return signs


def _turn_count(values: Sequence[float]) -> int:
    signs = _directions(values)
    return sum(1 for index in range(1, len(signs)) if signs[index] != signs[index - 1])


def _step_kind(values: Sequence[float]) -> str | None:
    levels = _two_levels(values)
    if levels is not None:
        return levels
    if _spur(values):
        return "spur"
    return None


def _two_levels(values: Sequence[float]) -> str | None:
    if len(values) < 4:
        return None
    for cut in range(2, len(values) - 1):
        head = values[:cut]
        tail = values[cut:]
        if _span(head) > _STEP_INNER or _span(tail) > _STEP_INNER:
            continue
        gap = _median(head) - _median(tail)
        if gap >= _STEP_GAP:
            return "upper_wide"
        if -gap >= _STEP_GAP:
            return "lower_wide"
    return None


def _spur(values: Sequence[float]) -> bool:
    if len(values) < 4:
        return False
    outer = max(values)
    sticking = [index for index, value in enumerate(values) if value >= outer - _SLACK]
    if len(sticking) != 1:
        return False
    rest = [value for index, value in enumerate(values) if index not in sticking]
    if len(rest) < 3 or _span(rest) > _STEP_INNER:
        return False
    return outer - max(rest) >= _STEP_GAP


def _bow_kind(values: Sequence[float]) -> str | None:
    """One deep turn. One line off a flat shelf is a spur, not a bulge."""
    if len(values) < 6 or _turn_count(values) != 1:
        return None
    low = min(range(len(values)), key=values.__getitem__)
    high = max(range(len(values)), key=values.__getitem__)
    if _deep_turn(values, low, extreme_is_min=True):
        return "inset"
    if _spur(values):
        return None
    if _deep_turn(values, high, extreme_is_min=False):
        return "bulge"
    return None


def _deep_turn(values: Sequence[float], index: int, *, extreme_is_min: bool) -> bool:
    if index < 2 or index > len(values) - 3:
        return False
    if extreme_is_min:
        left = max(values[: index + 1]) - values[index]
        right = max(values[index:]) - values[index]
    else:
        left = values[index] - min(values[: index + 1])
        right = values[index] - min(values[index:])
    return left >= _LEG and right >= _LEG


def _hang_indent(lines: Sequence[Sequence[float]]) -> float | None:
    body = _strip_short_tail(lines)
    if len(body) < 3:
        return None
    lefts = _coord(body, 0)
    if lefts[0] > min(lefts) + _SLACK:
        return None
    rest = lefts[1:]
    if _span(rest) > _WALL:
        return None
    indent = min(rest) - lefts[0]
    if indent < _HANG_MIN:
        return None
    return indent


def _repeated_indent(lines: Sequence[Sequence[float]]) -> float | None:
    body = _strip_short_tail(lines)
    lefts = _coord(body, 0)
    if len(lefts) < 5:
        return None
    floor = min(lefts)
    floors = [index for index, value in enumerate(lefts) if value <= floor + _SLACK]
    indented = [value for value in lefts if value >= floor + _HANG_MIN]
    if len(floors) < 2 or len(indented) < 3 or _span(indented) > _WALL:
        return None
    seen = False
    for value in lefts:
        if value >= floor + _HANG_MIN:
            seen = True
        elif seen and value <= floor + _SLACK:
            return _span(indented)
    return None


def _plateau_span(lines: Sequence[Sequence[float]]) -> float:
    body = _strip_short_tail(lines)
    lefts = _coord(body, 0)
    return _span(lefts[1:])
