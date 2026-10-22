"""Plain log of a sealed block and the paradigm that matched it.

SCAN is measurements only. MATCH is the decision. Neither line changes
the plan, and a fixed confidence is not written as a residual.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from babeldoc.format.pdf.document_il.utils.layout_plan.measure import measure_region
from babeldoc.format.pdf.document_il.utils.layout_plan.model import LayoutFacts
from babeldoc.format.pdf.document_il.utils.layout_plan.model import LayoutPlan
from babeldoc.format.pdf.document_il.utils.layout_plan.model import Region
from babeldoc.format.pdf.document_il.utils.layout_plan.model import RegionDecision
from babeldoc.format.pdf.document_il.utils.layout_plan.model import geometry_digest

logger = logging.getLogger("babeldoc.layout_plan")

_CONFLICT = frozenset({"list_and_shaped", "conflict_tie"})


def emit(
    facts: LayoutFacts,
    plan: LayoutPlan,
    log_path: Path | None = None,
    *,
    console: bool = False,
) -> list[dict]:
    """Append one JSON object per line. Return the same records."""
    rows = records(facts, plan)
    if log_path is not None and rows:
        path = Path(log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    if console:
        for row in rows:
            if row["kind"] == "PAGE" or row.get("status") == "unmatched":
                logger.info(row["line"])
    return rows


def records(facts: LayoutFacts, plan: LayoutPlan) -> list[dict]:
    """SCAN, MATCH, then PAGE. An empty plan still yields the page total."""
    if len(facts.regions) != len(plan.decisions):
        logger.warning("layout log region count drifted")
        return []
    page = facts.page_index + 1
    rows: list[dict] = []
    counts = {"matched": 0, "unmatched": 0, "gate": 0, "conflict": 0}
    for order, (region, decision) in enumerate(
        zip(facts.regions, plan.decisions, strict=True)
    ):
        scan = _scan(facts, region, page, order)
        match = _match(facts, region, decision, page, scan["block"])
        counts[match["status"]] += 1
        rows.append(scan)
        rows.append(match)
    summary = {
        "kind": "PAGE",
        "page": page,
        "page_index": facts.page_index,
        "blocks": len(facts.regions),
        "matched": counts["matched"],
        "unmatched": counts["unmatched"],
        "gate": counts["gate"],
        "conflict": counts["conflict"],
    }
    summary["line"] = (
        f"PAGE page={page} blocks={summary['blocks']} "
        f"matched={summary['matched']} unmatched={summary['unmatched']} "
        f"gate={summary['gate']} conflict={summary['conflict']}"
    )
    rows.append(summary)
    return rows


def _scan(facts: LayoutFacts, region: Region, page: int, order: int) -> dict:
    measured = measure_region(region, facts.figures)
    block = geometry_digest(region.lines)[:6]
    row = {
        "kind": "SCAN",
        "page": page,
        "page_index": facts.page_index,
        "block": block,
        "region_id": region.region_id,
        "lines": len(region.lines),
        "order": order,
        "marker": measured.marker,
        "gate": facts.input_gate,
        "left": [round(measured.left[0], 1), round(measured.left[1], 1)],
        "right": [round(measured.right[0], 1), round(measured.right[1], 1)],
        "y": [round(measured.y[0], 1), round(measured.y[1], 1)],
        "figs": measured.figures,
        "full_count": measured.full_count,
        "left_range": round(measured.left_range, 1),
        "right_range": round(measured.right_range, 1),
        "left_monotone": round(measured.left_monotone, 2),
        "right_monotone": round(measured.right_monotone, 2),
        "source_fingerprint": facts.source_fingerprint,
        "identity_scope": _scope(facts),
    }
    if row["identity_scope"] == "unscoped":
        row["identity_note"] = "region ids are not comparable across documents"
    row["line"] = (
        f"SCAN page={page} block={block} lines={row['lines']} "
        f"order={order} marker={measured.marker} gate={facts.input_gate} "
        f"left={_span(measured.left)} right={_span(measured.right)} "
        f"y={_span(measured.y)} figs={measured.figures} "
        f"full={measured.full_count} "
        f"left_range={measured.left_range:.1f} "
        f"right_range={measured.right_range:.1f} "
        f"identity={row['identity_scope']}"
    )
    return row


def _match(
    facts: LayoutFacts,
    region: Region,
    decision: RegionDecision,
    page: int,
    block: str,
) -> dict:
    status, paradigm, claims = _status(facts, decision)
    residual = _logged_residual(status, decision)
    row = {
        "kind": "MATCH",
        "page": page,
        "page_index": facts.page_index,
        "block": block,
        "region_id": region.region_id,
        "status": status,
        "paradigm": paradigm,
        "residual": residual,
        "nearest": "",
        "gate": facts.input_gate if status == "gate" else "",
        "claims": claims,
    }
    text = (
        f"MATCH page={page} block={block} status={status} "
        f"paradigm={paradigm} residual="
    )
    if residual is not None:
        text += _format_residual(residual)
        if decision.contour_threshold is not None:
            text += " threshold=" + _format_residual(decision.contour_threshold)
    if status == "unmatched":
        text += " nearest="
        if decision.contour_reason:
            text += f" reason={decision.contour_reason}"
    elif status == "gate":
        text += f" gate={facts.input_gate}"
    elif status == "conflict":
        text += " claims=" + ",".join(claims)
    row["line"] = text
    return row


def _logged_residual(status: str, decision: RegionDecision) -> float | None:
    """The granted contour residual. Confidence is never written here."""
    if status != "matched" or decision.contour_status != "matched":
        return None
    if not decision.contour_plugin:
        return None
    return decision.contour_residual


def _format_residual(value: float) -> str:
    return f"{float(value):.4f}".rstrip("0").rstrip(".")


def _scope(facts: LayoutFacts) -> str:
    return getattr(facts, "identity_scope", None) or "unscoped"


def _status(
    facts: LayoutFacts, decision: RegionDecision
) -> tuple[str, str, list[str]]:
    if facts.input_gate != "single_page":
        return "gate", "", []
    if decision.contour_status == "conflict":
        return "conflict", "", list(decision.contour_claims)
    if decision.fallback in _CONFLICT:
        claims = sorted({item.value for item in decision.rejected if item.value})
        return "conflict", "", claims
    if decision.contour_status == "matched" and decision.contour_plugin:
        return "matched", decision.contour_plugin, []
    if decision.base_strategy == "preserve":
        return "unmatched", "", []
    return "matched", decision.base_strategy, []


def _span(pair: tuple[float, float]) -> str:
    return f"{pair[0]:.1f}..{pair[1]:.1f}"
