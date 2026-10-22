"""shaped_pocket plugin.

Claims a body or wrap column when the shared taper test matches.
The test is the public reader. This module does not add a second
line-box cutoff. The 8 kept and 20 rejected stairs are a visual
record in ``shaped_review.json``. Line boxes do not separate them,
and a cutoff fitted to that file is not a rule. Figure boxes are
facts for the gap. They do not add a second line-box cutoff here.

Does not look at titles, quotes, chrome, or photo text. When the
block is also a list, this plugin still emits. The resolver then
keeps the block, because a bullet on a stair is not enough to win.

Emits base strategy ``shaped_pocket`` at confidence 0.9, priority 20.
Fallback is ``preserve``.

Gold for this plugin is ``tests/golden/layout_plan/shaped_pocket.json``.
"""

from __future__ import annotations

from babeldoc.format.pdf.document_il.utils.layout_plan.geometry import free_side
from babeldoc.format.pdf.document_il.utils.layout_plan.geometry import geometry_eligible
from babeldoc.format.pdf.document_il.utils.layout_plan.geometry import is_taper
from babeldoc.format.pdf.document_il.utils.layout_plan.model import Evidence
from babeldoc.format.pdf.document_il.utils.layout_plan.model import LayoutFacts
from babeldoc.format.pdf.document_il.utils.layout_plan.model import PlanContribution
from babeldoc.format.pdf.document_il.utils.placement_paradigm import PlacementParadigm

PLUGIN_ID = "shaped_pocket"
PLUGIN_VERSION = "1"


def analyze(facts: LayoutFacts) -> list[PlanContribution]:
    found: list[PlanContribution] = []
    for region in facts.regions:
        if not geometry_eligible(region) or not is_taper(region):
            continue
        found.append(
            PlanContribution(
                plugin_id=PLUGIN_ID,
                plugin_version=PLUGIN_VERSION,
                target_region_id=region.region_id,
                kind="base_strategy",
                value="shaped_pocket",
                confidence=0.9,
                priority=20,
                evidence=(
                    Evidence(
                        "taper",
                        (
                            f"free_side={free_side(region)} "
                            f"legacy={PlacementParadigm.SHAPED_POCKET.value}"
                        ),
                    ),
                ),
                fallback="preserve",
            )
        )
    return found
