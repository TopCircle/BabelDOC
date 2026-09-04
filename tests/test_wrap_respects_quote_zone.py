
"""OA p91: wrap pin must still carve left callout exclusion."""

from types import SimpleNamespace

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.midend.exclusion_zone import ExclusionZone
from babeldoc.format.pdf.document_il.midend.exclusion_zone import ExclusionZoneIndex
from babeldoc.format.pdf.document_il.midend.exclusion_zone import ZONE_QUOTE
from babeldoc.format.pdf.document_il.utils.layout_intent import LayoutIntent
from babeldoc.format.pdf.document_il.utils.layout_intent import LayoutIntentRole
from babeldoc.format.pdf.document_il.utils.layout_intent import WrapMode
from babeldoc.format.pdf.document_il.utils.line_interval_plan import LayoutAttempt
from babeldoc.format.pdf.document_il.utils.line_interval_plan import resolve_line_interval_plan


def test_wrap_pocket_carves_left_quote_zone():
    """LEFT_FIXED wrap over full body must not paint over x≈54-212 callout."""
    para = PdfParagraph()
    para.layout_intent = LayoutIntent(
        role=LayoutIntentRole.BODY,
        design_box=Box(x=102.0, y=300.0, x2=573.0, y2=520.0),
        top_inset=0.0,
        bottom_inset=0.0,
        wrap_shape=[(0.0, 471.0)],
        wrap_mode=WrapMode.LEFT_FIXED,
    )
    quote = ExclusionZone(
        box=Box(x=42.0, y=318.0, x2=224.0, y2=422.0),
        kind=ZONE_QUOTE,
        priority=20,
        margins=None,
    )
    idx = ExclusionZoneIndex(zones=[quote])
    layout = Box(x=102.0, y=300.0, x2=573.0, y2=520.0)
    plan = resolve_line_interval_plan(
        para,
        layout,
        attempt=LayoutAttempt.PRIMARY,
        wrap_enabled=True,
        zone_index=idx,
    )
    intervals = plan.intervals_at(350.0, 365.0, line_idx=0)
    assert intervals, intervals
    assert intervals[0][0] >= 220.0, intervals
    assert intervals[0][0] > 102.0, intervals
