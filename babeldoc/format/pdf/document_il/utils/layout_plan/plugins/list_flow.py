"""list plugin.

Claims a body block whose first glyph is a bullet or whose text starts
with a serial. Bullets and numbers are one strategy. A hanging indent
with neither is not a list.

Does not look at titles, quotes, chrome, or photo text. When the block
is also a shaped pocket, this plugin still emits. The resolver then
keeps the block, because a bullet on a real stair is not enough to win.

Emits base strategy ``list`` at confidence 0.9, priority 30.
"""

from __future__ import annotations

from babeldoc.format.pdf.document_il.utils.layout_plan.geometry import geometry_eligible
from babeldoc.format.pdf.document_il.utils.layout_plan.model import Evidence
from babeldoc.format.pdf.document_il.utils.layout_plan.model import LayoutFacts
from babeldoc.format.pdf.document_il.utils.layout_plan.model import PlanContribution
from babeldoc.format.pdf.document_il.utils.layout_plan.model import Region
from babeldoc.format.pdf.document_il.utils.list_marker_repair import LIST_MARKER_RE

PLUGIN_ID = "list_flow"
PLUGIN_VERSION = "1"


def has_list_evidence(region: Region) -> bool:
    """True for a bullet glyph or a leading serial. This does not check shape."""
    marker = region.marker
    if marker is not None and getattr(marker, "is_bullet", False):
        return True
    text = region.source_text.replace("\xa0", " ").replace("\u2009", " ").lstrip()
    return bool(LIST_MARKER_RE.match(text))


def analyze(facts: LayoutFacts) -> list[PlanContribution]:
    found: list[PlanContribution] = []
    for region in facts.regions:
        if not geometry_eligible(region) or not has_list_evidence(region):
            continue
        bullet = region.marker is not None and region.marker.is_bullet
        detail = "bullet" if bullet else "serial"
        found.append(
            PlanContribution(
                plugin_id=PLUGIN_ID,
                plugin_version=PLUGIN_VERSION,
                target_region_id=region.region_id,
                kind="base_strategy",
                value="list",
                confidence=0.9,
                priority=30,
                evidence=(Evidence("list_marker", detail),),
                fallback="preserve",
            )
        )
    return found
