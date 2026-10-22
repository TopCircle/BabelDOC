"""Run the default plugins and freeze one page plan."""

from __future__ import annotations

from babeldoc.format.pdf.document_il.utils.layout_plan.column_chain import (
    with_column_links,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.line_edges import (
    with_line_edge_links,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.list_chain import with_list_links
from babeldoc.format.pdf.document_il.utils.layout_plan.model import LayoutFacts
from babeldoc.format.pdf.document_il.utils.layout_plan.model import LayoutPlan
from babeldoc.format.pdf.document_il.utils.layout_plan.paragraph_gap import (
    with_paragraph_gap_links,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.plugins import DEFAULT_PLUGINS
from babeldoc.format.pdf.document_il.utils.layout_plan.pocket_chain import (
    with_pocket_links,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.resolver import resolve


def build_plan(facts: LayoutFacts, plugins=DEFAULT_PLUGINS) -> LayoutPlan:
    """Plugins only return contributions. The resolver freezes the plan."""
    contributions = []
    for plugin in plugins:
        contributions.extend(plugin.analyze(facts))
    linked = with_column_links(facts, resolve(facts, contributions))
    linked = with_list_links(facts, linked)
    linked = with_pocket_links(facts, linked)
    linked = with_line_edge_links(facts, linked)
    return with_paragraph_gap_links(facts, linked)
