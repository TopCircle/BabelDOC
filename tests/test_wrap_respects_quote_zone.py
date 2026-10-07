
"""OA p91: wrap pin must still carve left callout exclusion."""

from types import SimpleNamespace

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import Cropbox
from babeldoc.format.pdf.document_il.il_version_1 import Mediabox
from babeldoc.format.pdf.document_il.il_version_1 import Page
from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraphComposition
from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
from babeldoc.format.pdf.document_il.midend.exclusion_zone import ExclusionZone
from babeldoc.format.pdf.document_il.midend.exclusion_zone import ExclusionZoneBuilder
from babeldoc.format.pdf.document_il.midend.exclusion_zone import ExclusionZoneIndex
from babeldoc.format.pdf.document_il.midend.exclusion_zone import ZONE_FIGURE
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


def test_wrap_pocket_ignores_figure_zone():
    """OA p19: figure residual must not flatten RIGHT_FIXED wrap_shape cone."""
    para = PdfParagraph()
    para.layout_intent = LayoutIntent(
        role=LayoutIntentRole.WRAP_COLUMN,
        design_box=Box(x=375.9, y=230.0, x2=569.5, y2=400.0),
        top_inset=0.0,
        bottom_inset=0.0,
        wrap_shape=[(0.0, 254.6), (0.0, 246.0), (0.0, 63.0)],
        wrap_mode=WrapMode.RIGHT_FIXED,
    )
    figure = ExclusionZone(
        box=Box(x=40.0, y=200.0, x2=433.0, y2=520.0),
        kind=ZONE_FIGURE,
        priority=20,
        margins=None,
    )
    idx = ExclusionZoneIndex(zones=[figure])
    layout = Box(x=375.9, y=230.0, x2=569.5, y2=400.0)
    plan = resolve_line_interval_plan(
        para,
        layout,
        attempt=LayoutAttempt.PRIMARY,
        wrap_enabled=True,
        zone_index=idx,
    )
    intervals = plan.intervals_at(460.0, 475.0, line_idx=0)
    assert intervals, intervals
    x1, x2 = intervals[0]
    assert abs(x2 - 569.5) < 1e-6
    assert abs((x2 - x1) - 254.6) < 1e-6
    assert x1 < 433.0


def _page(paragraphs: list[PdfParagraph], width: float = 612.0, height: float = 792.0) -> Page:
    return Page(
        page_number=0,
        pdf_paragraph=paragraphs,
        cropbox=Cropbox(box=Box(x=0, y=0, x2=width, y2=height)),
        mediabox=Mediabox(box=Box(x=0, y=0, x2=width, y2=height)),
    )


def _chars(text: str, box: Box, font_size: float) -> list[PdfParagraphComposition]:
    style = PdfStyle(font_id="q", font_size=font_size, graphic_state=None)
    return [
        PdfParagraphComposition(
            pdf_character=PdfCharacter(
                pdf_style=style,
                box=box,
                char_unicode=ch,
            )
        )
        for ch in text
    ]


def _callout(box: Box, text: str, font_size: float) -> PdfParagraph:
    para = PdfParagraph(
        box=box,
        pdf_paragraph_composition=_chars(text, box, font_size),
        unicode=text,
    )
    para.layout_intent = LayoutIntent(
        role=LayoutIntentRole.CALLOUT,
        design_box=box,
        top_inset=0.0,
        bottom_inset=0.0,
    )
    return para


def _body_plan(zone_index: ExclusionZoneIndex, box: Box):
    para = PdfParagraph(box=box, pdf_paragraph_composition=[], unicode="body")
    para.layout_intent = LayoutIntent(
        role=LayoutIntentRole.BODY,
        design_box=box,
        top_inset=0.0,
        bottom_inset=0.0,
    )
    return resolve_line_interval_plan(
        para,
        box,
        attempt=LayoutAttempt.PRIMARY,
        wrap_enabled=True,
        zone_index=zone_index,
    )


def _quote_index(paragraphs: list[PdfParagraph]) -> ExclusionZoneIndex:
    zones = [
        z
        for z in ExclusionZoneBuilder.build(_page(paragraphs))
        if z.kind == ZONE_QUOTE
    ]
    return ExclusionZoneIndex(zones)


def test_decorative_glyph_bands_outside_ink_keep_paragraph_left():
    """Query bands in the old y-pad, above and below the glyph, stay full width."""
    font_size = 80.0
    ink = Box(x=42.0, y=400.0, x2=58.0, y2=470.0)
    # Ink is 16pt wide, at most one em (font size 80).
    idx = _quote_index([_callout(ink, "“", font_size)])
    body = Box(x=36.0, y=300.0, x2=560.0, y2=640.0)
    plan = _body_plan(idx, body)
    # Old pad was max(font_size * 0.5, 12) = 40pt past the ink.
    above = plan.intervals_at(ink.y2 + 2.0, ink.y2 + 20.0, line_idx=0)
    below = plan.intervals_at(ink.y - 20.0, ink.y - 2.0, line_idx=0)
    assert above == [(body.x, body.x2)], above
    assert below == [(body.x, body.x2)], below


def test_decorative_glyph_line_stops_before_font_scaled_gap():
    """A line on the ink starts after x2 and before x2 + font_size * 2.2."""
    font_size = 80.0
    ink = Box(x=42.0, y=400.0, x2=58.0, y2=470.0)
    idx = _quote_index([_callout(ink, "“", font_size)])
    body = Box(x=36.0, y=300.0, x2=560.0, y2=640.0)
    plan = _body_plan(idx, body)
    intervals = plan.intervals_at(ink.y + 10.0, ink.y + 24.0, line_idx=0)
    assert intervals, intervals
    start = intervals[0][0]
    pad = max(font_size * 0.5, 12.0)
    assert start > ink.x2, start
    assert start < ink.x2 + font_size * 2.2, start
    assert abs(start - (ink.x2 + pad)) < 0.05, start


def test_text_bar_wider_than_em_keeps_en_like_right_gap():
    """x < 80 and wider than one em still gaps by max(2.2em, 5.5% page)."""
    font_size = 16.0
    page_width = 612.0
    ink = Box(x=54.18, y=375.99, x2=211.635, y2=450.99)
    assert ink.x < 80.0
    assert (ink.x2 - ink.x) > font_size
    para = _callout(ink, "quote", font_size)
    zones = [
        z
        for z in ExclusionZoneBuilder.build(_page([para], width=page_width))
        if z.kind == ZONE_QUOTE
    ]
    assert len(zones) == 1
    z = zones[0].box
    expected = max(font_size * 2.2, page_width * 0.055)
    assert abs((z.x2 - ink.x2) - expected) < 0.05, z.x2
    assert z.y == ink.y
    assert z.y2 == ink.y2
