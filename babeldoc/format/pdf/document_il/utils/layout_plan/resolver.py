"""Pick one base strategy per region and record every rejection."""

from __future__ import annotations

from dataclasses import replace

from babeldoc.format.pdf.document_il.utils.layout_plan.model import Evidence
from babeldoc.format.pdf.document_il.utils.layout_plan.model import LayoutFacts
from babeldoc.format.pdf.document_il.utils.layout_plan.model import LayoutPlan
from babeldoc.format.pdf.document_il.utils.layout_plan.model import PlanContribution
from babeldoc.format.pdf.document_il.utils.layout_plan.model import RegionDecision
from babeldoc.format.pdf.document_il.utils.layout_plan.model import Rejection

MIN_CONFIDENCE = 0.6
_CLASSIFY_GATE = "single_page"


def resolve(
    facts: LayoutFacts, contributions: list[PlanContribution]
) -> LayoutPlan:
    by_region: dict[str, list[PlanContribution]] = {
        region.region_id: [] for region in facts.regions
    }
    ignored: list[Rejection] = []
    for item in contributions:
        if item.target_region_id not in by_region:
            ignored.append(_rejection(item, "unknown_region"))
            continue
        by_region[item.target_region_id].append(item)
    decisions = tuple(
        _decide(region.region_id, by_region[region.region_id], facts.input_gate)
        for region in facts.regions
    )
    if ignored:
        decisions = _attach_ignored(decisions, ignored)
    return LayoutPlan(
        source_fingerprint=facts.source_fingerprint,
        page_index=facts.page_index,
        input_gate=facts.input_gate,
        decisions=decisions,
        identity_scope=facts.identity_scope,
    )


def _decide(
    region_id: str, items: list[PlanContribution], gate: str
) -> RegionDecision:
    if gate != _CLASSIFY_GATE:
        rejected = tuple(_rejection(item, "input_gate") for item in items)
        return _preserve(region_id, rejected, gate)
    rejected: list[Rejection] = []
    bases: list[PlanContribution] = []
    modifiers: list[PlanContribution] = []
    for item in items:
        if item.confidence < MIN_CONFIDENCE:
            rejected.append(_rejection(item, "below_confidence"))
            continue
        if item.kind == "base_strategy":
            bases.append(item)
        elif item.kind == "modifier":
            modifiers.append(item)
        else:
            rejected.append(_rejection(item, "unknown_kind"))
    chosen, base_rejected = _choose_base(bases)
    rejected.extend(base_rejected)
    kept_modifiers, modifier_rejected = _merge_modifiers(modifiers)
    rejected.extend(modifier_rejected)
    if chosen is None:
        reasons = {item.reason for item in base_rejected}
        if "list_and_shaped" in reasons:
            fallback = "list_and_shaped"
        elif _tied(bases):
            fallback = "conflict_tie"
        else:
            fallback = "no_confident_base"
        return _preserve(region_id, tuple(rejected), fallback)
    return RegionDecision(
        region_id=region_id,
        base_strategy=chosen.value,
        modifiers=tuple(kept_modifiers),
        confidence=chosen.confidence,
        plugin_id=chosen.plugin_id,
        plugin_version=chosen.plugin_version,
        evidence=chosen.evidence,
        fallback=chosen.fallback,
        rejected=tuple(rejected),
    )


def _choose_base(
    bases: list[PlanContribution],
) -> tuple[PlanContribution | None, list[Rejection]]:
    if not bases:
        return None, []
    values = {item.value for item in bases}
    if "list" in values and "shaped_pocket" in values:
        return None, [_rejection(item, "list_and_shaped") for item in bases]
    if _tied(bases):
        return None, [_rejection(item, "conflict_tie") for item in bases]
    ordered = sorted(
        bases,
        key=lambda item: (-item.priority, -item.confidence, item.plugin_id),
    )
    chosen = ordered[0]
    rejected = [
        _rejection(item, "lost_to")
        for item in ordered[1:]
        if item.value != chosen.value or item.plugin_id != chosen.plugin_id
    ]
    return chosen, rejected


def _tied(bases: list[PlanContribution]) -> bool:
    if len(bases) < 2:
        return False
    ordered = sorted(
        bases,
        key=lambda item: (-item.priority, -item.confidence, item.plugin_id),
    )
    top = ordered[0]
    return any(
        item.priority == top.priority
        and item.confidence == top.confidence
        and item.value != top.value
        for item in ordered[1:]
    )


def _merge_modifiers(
    modifiers: list[PlanContribution],
) -> tuple[list[str], list[Rejection]]:
    """Same modifier value agrees. Different values of one key are dropped."""
    by_key: dict[str, list[PlanContribution]] = {}
    for item in modifiers:
        key = item.value.split(":", 1)[0]
        by_key.setdefault(key, []).append(item)
    kept: list[str] = []
    rejected: list[Rejection] = []
    for group in by_key.values():
        values = {item.value for item in group}
        if len(values) == 1:
            kept.append(group[0].value)
            continue
        rejected.extend(_rejection(item, "modifier_conflict") for item in group)
    kept.sort()
    return kept, rejected


def _preserve(
    region_id: str, rejected: tuple[Rejection, ...] | list[Rejection], fallback: str
) -> RegionDecision:
    return RegionDecision(
        region_id=region_id,
        base_strategy="preserve",
        modifiers=(),
        confidence=0.0,
        plugin_id=None,
        plugin_version=None,
        evidence=(Evidence("fallback", fallback),),
        fallback=fallback,
        rejected=tuple(rejected),
    )


def _rejection(item: PlanContribution, reason: str) -> Rejection:
    return Rejection(
        plugin_id=item.plugin_id,
        plugin_version=item.plugin_version,
        value=item.value,
        confidence=item.confidence,
        reason=reason,
    )


def _attach_ignored(
    decisions: tuple[RegionDecision, ...], ignored: list[Rejection]
) -> tuple[RegionDecision, ...]:
    if not decisions:
        return decisions
    first = decisions[0]
    return (
        replace(first, rejected=first.rejected + tuple(ignored)),
    ) + decisions[1:]
