"""The only typesetting-facing reader of a frozen plan."""

from __future__ import annotations

from dataclasses import dataclass

from babeldoc.format.pdf.document_il.utils.layout_plan.model import LayoutPlan


@dataclass(frozen=True, slots=True)
class PlanConsumption:
    """What typesetting is allowed to see. No role and no geometry."""

    region_id: str
    base_strategy: str
    modifiers: tuple[str, ...]
    confidence: float
    fallback: str | None


def consume_layout_plan(plan: LayoutPlan, region_id: str) -> PlanConsumption:
    """Read one region. A missing id conservatively preserves.

    rect_flow and list placement both start from this result. This
    function does not move boxes.
    """
    for decision in plan.decisions:
        if decision.region_id == region_id:
            return PlanConsumption(
                region_id=decision.region_id,
                base_strategy=decision.base_strategy,
                modifiers=decision.modifiers,
                confidence=decision.confidence,
                fallback=decision.fallback,
            )
    return PlanConsumption(
        region_id=region_id,
        base_strategy="preserve",
        modifiers=(),
        confidence=0.0,
        fallback="missing_region",
    )
