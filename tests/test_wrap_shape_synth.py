
"""OA p59: BODY + photo LEFT_FIXED must resolve a wrap_shape so pin path fires."""

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.utils.layout_intent import LayoutIntent
from babeldoc.format.pdf.document_il.utils.layout_intent import LayoutIntentRole
from babeldoc.format.pdf.document_il.utils.layout_intent import WrapMode
from babeldoc.format.pdf.document_il.utils.line_interval_plan import LayoutAttempt
from babeldoc.format.pdf.document_il.utils.line_interval_plan import attempt_chain_for_paragraph
from babeldoc.format.pdf.document_il.utils.wrap_shape import resolve_wrap_shape


def test_body_left_fixed_without_shape_synths_design_width():
    para = PdfParagraph()
    para.layout_intent = LayoutIntent(
        role=LayoutIntentRole.BODY,
        design_box=Box(x=102.0, y=228.0, x2=340.0, y2=393.0),
        top_inset=0.0,
        bottom_inset=0.0,
        wrap_shape=None,
        wrap_mode=WrapMode.LEFT_FIXED,
    )
    shape = resolve_wrap_shape(para)
    assert shape is not None
    assert shape[0][1] == 238.0
    assert attempt_chain_for_paragraph(para, is_cjk=True) == [LayoutAttempt.PRIMARY]
