"""Edge record and the choice among residuals.

A match is a residual strictly under that module's own threshold.
Two matches conflict. A category name is never returned.
"""

from __future__ import annotations

from collections.abc import Callable
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BlockEdges:
    """Six numbers a claim module is allowed to read."""

    full_count: int
    left_range: float
    right_range: float
    left_monotone: float
    right_monotone: float
    marker: str


@dataclass(frozen=True, slots=True)
class Paradigm:
    """One layout mode, system-defined or passed in later.

    A paradigm is maintained on its own. The pipeline only receives this
    object. It does not grow a branch when a new mode is added.
    ``name`` is a path such as ``rect/full_column``. A category is not a name.
    ``fill`` is optional. A module without one still claims. Only the
    matched object's own fill writes line edges.
    ``alignment`` is ``left``, ``center``, or ``right``. ``flow`` is ``edge`` or
    ``sentence``. Typesetting reads both from the link and does not name
    the paradigm.
    """

    name: str
    threshold: float
    claim: Callable[[BlockEdges, Sequence[Sequence[float]]], float | None]
    fill: (
        Callable[
            [Sequence[Sequence[float]]],
            tuple[tuple[float, float], ...],
        ]
        | None
    ) = None
    alignment: str = "left"
    flow: str = "edge"

    def __post_init__(self) -> None:
        parts = self.name.split("/")
        if len(parts) < 2 or any(part == "" for part in parts):
            raise ValueError(f"{self.name} is not a paradigm path")
        if isinstance(self.threshold, bool) or not isinstance(
            self.threshold, (int, float)
        ):
            raise TypeError(f"{self.name} threshold must be a float")
        if not callable(self.claim):
            raise TypeError(f"{self.name} claim must be callable")
        if self.fill is not None and not callable(self.fill):
            raise TypeError(f"{self.name} fill must be callable")
        if self.alignment not in ("left", "center", "right"):
            raise ValueError(f"{self.name} alignment must be left, center, or right")
        if self.flow not in ("edge", "sentence"):
            raise ValueError(f"{self.name} flow must be edge or sentence")


def one_direction(values: Sequence[float]) -> bool:
    """True when the edge never reverses.

    A step may stay, or keep moving the same way. One step the other
    way is a fold. An empty edge is not one direction.
    """
    if len(values) == 0:
        return False
    deltas = [values[index + 1] - values[index] for index in range(len(values) - 1)]
    forward = any(delta > 0.0 for delta in deltas)
    back = any(delta < 0.0 for delta in deltas)
    return not (forward and back)


def pick(
    results: Sequence[tuple[str, float | None, float]],
) -> tuple[str, str, float | None]:
    """Return ``(status, paradigm, residual)``.

    ``None`` residuals are not candidates. A float matches only when it
    is strictly under its own threshold. More than one match conflicts
    and clears the paradigm. No nearest module is attached.
    """
    scored = [
        (paradigm, residual, threshold)
        for paradigm, residual, threshold in results
        if residual is not None
    ]
    under = [
        (paradigm, residual)
        for paradigm, residual, threshold in scored
        if residual < threshold
    ]
    if len(under) == 1:
        paradigm, residual = under[0]
        return "matched", paradigm, residual
    if len(under) > 1:
        residual = min(item[1] for item in under)
        return "conflict", "", residual
    if not scored:
        return "unmatched", "", None
    residual = min(item[1] for item in scored)
    return "unmatched", "", residual


FOUNDING_PARADIGMS = frozenset(
    {
        "rect/full_column",
        "taper/left_pin",
        "taper/right_pin",
    }
)


def stand_down(
    results: Sequence[tuple[str, float | None, float]],
) -> tuple[tuple[str, float | None, float], ...]:
    """Clear later shapes when a founding paradigm is under its threshold.

    This is the only place a shape yields. A claim does not call another claim.
    """
    owned = any(
        name in FOUNDING_PARADIGMS and residual is not None and residual < threshold
        for name, residual, threshold in results
    )
    if not owned:
        return tuple(results)
    return tuple(
        (name, residual if name in FOUNDING_PARADIGMS else None, threshold)
        for name, residual, threshold in results
    )
