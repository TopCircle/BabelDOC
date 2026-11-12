"""Regression tests for icon-curve anchoring and passthrough color state transitions."""

from __future__ import annotations

from babeldoc.format.pdf.document_il.frontend.il_creater_active_support import (
    EMPTY_PASSTHROUGH_SNAPSHOT,
)
from babeldoc.format.pdf.document_il.frontend.il_creater_active_support import (
    replace_first_passthrough_operator,
)
from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import Page
from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter
from babeldoc.format.pdf.document_il.il_version_1 import PdfCurve
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraphComposition
from babeldoc.format.pdf.document_il.il_version_1 import PdfSameStyleUnicodeCharacters
from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
from babeldoc.format.pdf.document_il.utils.icon_curve_anchor import (
    capture_icon_curve_anchors,
)
from babeldoc.format.pdf.document_il.utils.icon_curve_anchor import (
    register_page_icon_anchors,
)
from babeldoc.format.pdf.document_il.utils.icon_curve_anchor import (
    resync_page_icon_curves,
)
from babeldoc.format.pdf.document_il.utils.icon_curve_anchor import (
    sync_icon_curve_anchors,
)


def _para(x: float, y: float, x2: float, y2: float) -> PdfParagraph:
    return PdfParagraph(
        box=Box(x=x, y=y, x2=x2, y2=y2),
        pdf_paragraph_composition=[
            PdfParagraphComposition(
                pdf_character=PdfCharacter(
                    box=Box(x=x, y=y, x2=x2, y2=y2),
                    char_unicode="A",
                )
            )
        ],
    )


def _curve(x: float, y: float, x2: float, y2: float) -> PdfCurve:
    return PdfCurve(box=Box(x=x, y=y, x2=x2, y2=y2), debug_info="a")


def test_icon_anchors_track_gutter_cross_and_circled_badge_but_ignore_wide_box():
    """Left-gutter icons and small marker ovals follow paragraph shifts; wide callout boxes do not."""
    p1 = _para(70.0, 500.0, 300.0, 514.0)
    p2 = _para(70.0, 400.0, 300.0, 414.0)
    cross_x = _curve(48.0, 502.0, 56.0, 510.0)
    oval_2 = _curve(69.0, 398.0, 86.0, 415.0)
    wide_callout = _curve(50.0, 390.0, 260.0, 420.0)
    page = Page(pdf_paragraph=[p1, p2], pdf_curve=[cross_x, oval_2, wide_callout])

    anchors = capture_icon_curve_anchors(page)
    assert len(anchors) == 2

    # Simulate upward packing (+22pt) followed by a post-layout upward nudge (+5pt).
    p1.pdf_paragraph_composition[0].pdf_character.box.y += 22.0
    p1.pdf_paragraph_composition[0].pdf_character.box.y2 += 22.0
    p2.pdf_paragraph_composition[0].pdf_character.box.y += 12.0
    p2.pdf_paragraph_composition[0].pdf_character.box.y2 += 12.0

    sync_icon_curve_anchors(anchors)
    assert cross_x.relocation_transform == [1.0, 0.0, 0.0, 1.0, 0.0, 22.0]
    assert oval_2.relocation_transform == [1.0, 0.0, 0.0, 1.0, 0.0, 12.0]
    assert wide_callout.relocation_transform == []

    register_page_icon_anchors(page, anchors)
    p1.pdf_paragraph_composition[0].pdf_character.box.y += 5.0
    p1.pdf_paragraph_composition[0].pdf_character.box.y2 += 5.0
    resync_page_icon_curves(page, release=True)
    assert cross_x.relocation_transform == [1.0, 0.0, 0.0, 1.0, 0.0, 27.0]

    # Once released, subsequent resync calls must be a no-op.
    p1.pdf_paragraph_composition[0].pdf_character.box.y += 10.0
    p1.pdf_paragraph_composition[0].pdf_character.box.y2 += 10.0
    resync_page_icon_curves(page, release=True)
    assert cross_x.relocation_transform == [1.0, 0.0, 0.0, 1.0, 0.0, 27.0]


def test_icon_anchors_fallback_to_paragraph_box_before_render_paragraph():
    """Translated paragraphs only carry unicode text before render_paragraph populates char boxes."""
    pre_render_para = PdfParagraph(
        box=Box(x=92.0, y=408.0, x2=550.0, y2=548.4),
        pdf_style=PdfStyle(font_size=11.0),
        pdf_paragraph_composition=[
            PdfParagraphComposition(
                pdf_same_style_unicode_characters=PdfSameStyleUnicodeCharacters(
                    unicode="工作时饮酒"
                )
            )
        ],
    )
    cross_x = _curve(65.7, 536.0, 78.0, 548.3)
    page = Page(pdf_paragraph=[pre_render_para], pdf_curve=[cross_x])

    anchors = capture_icon_curve_anchors(page)
    assert len(anchors) == 1

    # Simulate render_paragraph + pack upward (+39pt) writing rendered glyphs.
    pre_render_para.pdf_paragraph_composition = [
        PdfParagraphComposition(
            pdf_character=PdfCharacter(
                box=Box(x=92.0, y=575.0, x2=140.0, y2=589.0),
                char_unicode="工",
            )
        )
    ]
    sync_icon_curve_anchors(anchors)
    dy = cross_x.relocation_transform[5]
    assert 38.0 < dy < 43.0


def test_passthrough_pattern_and_rgb_color_ordering():
    """Switching pattern name keeps scn right after cs; switching to rg drops stale cs."""
    snap = EMPTY_PASSTHROUGH_SNAPSHOT
    snap = replace_first_passthrough_operator(snap, "cs", ("cs", "/Pattern"))
    snap = replace_first_passthrough_operator(snap, "scn", ("scn", "/P0"))
    snap = replace_first_passthrough_operator(snap, "gs", ("gs", "/GS0"))

    snap_p1 = replace_first_passthrough_operator(snap, "scn", ("scn", "/P1"))
    assert snap_p1.to_tuple() == (
        ("cs", "/Pattern"),
        ("scn", "/P1"),
        ("gs", "/GS0"),
    )
    assert snap_p1.render() == "/Pattern cs /P1 scn /GS0 gs"

    snap_rgb = replace_first_passthrough_operator(
        snap_p1, "rg", ("rg", "0.2 0.2 0.2")
    )
    assert snap_rgb.to_tuple() == (
        ("gs", "/GS0"),
        ("rg", "0.2 0.2 0.2"),
    )
    assert snap_rgb.render() == "/GS0 gs 0.2 0.2 0.2 rg"
