"""rect_flow plugin.

Applies when a body or wrap column has at least two full lines and the
left edge stays within the shared stable-column range.

Does not apply to titles, lists, quotes, chrome, photo text, one-line
blocks, short tapers, or hanging indents.

Emits base strategy ``rect_flow`` at confidence 0.9. Fallback is
``preserve``. Conflicts with ``shaped_pocket``: the taper plugin has
higher priority, and a tie of priority plus confidence becomes
``preserve``.

Gold: ``tests/golden/layout_plan/rect_flow.json``.
"""

from __future__ import annotations

from babeldoc.format.pdf.document_il.utils.layout_plan.geometry import feature_lines
from babeldoc.format.pdf.document_il.utils.layout_plan.geometry import geometry_eligible
from babeldoc.format.pdf.document_il.utils.layout_plan.geometry import is_stable_column
from babeldoc.format.pdf.document_il.utils.layout_plan.model import Evidence
from babeldoc.format.pdf.document_il.utils.layout_plan.model import LayoutFacts
from babeldoc.format.pdf.document_il.utils.layout_plan.model import PlanContribution
from babeldoc.format.pdf.document_il.utils.layout_plan.plugins.list_flow import (
    has_list_evidence,
)
from babeldoc.format.pdf.document_il.utils.placement_paradigm import PlacementParadigm

PLUGIN_ID = "rect_flow"
PLUGIN_VERSION = "1"


def analyze(facts: LayoutFacts) -> list[PlanContribution]:
    found: list[PlanContribution] = []
    for region in facts.regions:
        if not geometry_eligible(region) or has_list_evidence(region):
            continue
        if not is_stable_column(region):
            continue
        features = feature_lines(region)
        found.append(
            PlanContribution(
                plugin_id=PLUGIN_ID,
                plugin_version=PLUGIN_VERSION,
                target_region_id=region.region_id,
                kind="base_strategy",
                value="rect_flow",
                confidence=0.9,
                priority=10,
                evidence=(
                    Evidence(
                        "stable_column",
                        (
                            f"full_count={features.full_count} "
                            f"left_range={features.left_range:.2f} "
                            f"legacy={PlacementParadigm.RECT_REFLOW.value}"
                        ),
                    ),
                ),
                fallback="preserve",
            )
        )
    return found
