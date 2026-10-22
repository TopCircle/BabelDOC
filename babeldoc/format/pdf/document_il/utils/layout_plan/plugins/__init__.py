"""First-slice plugins. Each detector lives in its own module."""

from babeldoc.format.pdf.document_il.utils.layout_plan.plugins import list_flow
from babeldoc.format.pdf.document_il.utils.layout_plan.plugins import rect_flow
from babeldoc.format.pdf.document_il.utils.layout_plan.plugins import shaped_pocket

DEFAULT_PLUGINS = (list_flow, shaped_pocket, rect_flow)
