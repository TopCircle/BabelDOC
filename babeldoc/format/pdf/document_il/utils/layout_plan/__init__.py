"""Frozen layout plan. Plugins propose. Typesetting only reads the plan."""

from babeldoc.format.pdf.document_il.utils.layout_plan.compose import build_plan
from babeldoc.format.pdf.document_il.utils.layout_plan.consume import (
    consume_layout_plan,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.model import BaseStrategy
from babeldoc.format.pdf.document_il.utils.layout_plan.model import LayoutFacts
from babeldoc.format.pdf.document_il.utils.layout_plan.model import LayoutPlan

__all__ = [
    "BaseStrategy",
    "LayoutFacts",
    "LayoutPlan",
    "build_plan",
    "consume_layout_plan",
]
