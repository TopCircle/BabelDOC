"""Edge record and the choice among residuals.

A match is a residual strictly under that module's own threshold.
Two matches conflict. A category name is never returned.
"""

from __future__ import annotations

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


def one_direction(values: Sequence[float]) -> bool:
    """True when the min and the max both sit on an end index.

    Equal values keep the earlier index.
    """
    count = len(values)
    if count == 0:
        return False
    lowest = min(range(count), key=lambda index: values[index])
    highest = max(range(count), key=lambda index: values[index])
    return {lowest, highest} <= {0, count - 1}


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
