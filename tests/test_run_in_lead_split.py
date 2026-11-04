"""Tests for line_fills_differ with run-in leads and list item justification."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import GraphicState
from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter
from babeldoc.format.pdf.document_il.il_version_1 import PdfLine
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
from babeldoc.format.pdf.document_il.il_version_1 import VisualBbox
from babeldoc.format.pdf.document_il.midend.typesetting import Typesetting
from babeldoc.format.pdf.document_il.utils.paragraph_split_policy import (
    line_fills_differ,
)


def _char_with_gs(ch: str, gs_cmd: str | None) -> PdfCharacter:
    box = Box(x=0.0, y=0.0, x2=10.0, y2=10.0)
    gs = (
        GraphicState(passthrough_per_char_instruction=gs_cmd)
        if gs_cmd is not None
        else None
    )
    return PdfCharacter(
        char_unicode=ch,
        box=box,
        visual_bbox=VisualBbox(box=box),
        pdf_style=PdfStyle(font_id="f0", font_size=10.0, graphic_state=gs),
    )


def test_line_fills_differ_inline_run_in_lead():
    """A line with colored run-in lead transitioning to black tail matches next black line."""
    # Line 1: purple lead ("• Title: "), black tail ("body text...")
    chars_l1 = [_char_with_gs("•", "0.37 0.34 0.55 rg")] + [
        _char_with_gs("A", "0.37 0.34 0.55 rg") for _ in range(6)
    ]
    chars_l1 += [_char_with_gs("B", "0 0 0 rg") for _ in range(10)]
    line1 = PdfLine(box=Box(x=0, y=100, x2=200, y2=112), pdf_character=chars_l1)

    # Line 2: entirely black
    chars_l2 = [_char_with_gs("C", "0 0 0 rg") for _ in range(15)]
    line2 = PdfLine(box=Box(x=0, y=85, x2=200, y2=97), pdf_character=chars_l2)

    # Should not split because tail of line 1 matches line 2
    assert not line_fills_differ(line1, line2)


def test_line_fills_differ_banner_title():
    """A banner line whose entire text is colored/white differs from black body line."""
    # Line 1: entirely white/purple
    chars_l1 = [_char_with_gs("H", "1 1 1 rg") for _ in range(10)]
    line1 = PdfLine(box=Box(x=0, y=100, x2=200, y2=112), pdf_character=chars_l1)

    # Line 2: entirely black
    chars_l2 = [_char_with_gs("B", "0 0 0 rg") for _ in range(15)]
    line2 = PdfLine(box=Box(x=0, y=85, x2=200, y2=97), pdf_character=chars_l2)

    # Must split
    assert line_fills_differ(line1, line2)


def test_alignment_in_frame_for_list_item():
    """List item paragraph intermediate lines justify; tail line stays left."""
    cfg = MagicMock()
    cfg.primary_font_family = "sans-serif"
    ts = Typesetting(cfg)
    page = SimpleNamespace(page_id="p1")
    ts._current_page = page

    para = PdfParagraph(layout_region_id="list_item_1")

    # Mock list_links_on to contain list_item_1
    with (
        unittest_mock_list_links({"list_item_1"}, set()),
    ):
        # Intermediate line -> justify
        assert (
            ts._alignment_in_frame("left", last=False, paragraph=para)
            == "justify"
        )
        # Tail line -> left
        assert (
            ts._alignment_in_frame("left", last=True, paragraph=para) == "left"
        )


def unittest_mock_list_links(list_links, rect_links):
    from unittest.mock import patch

    p1 = patch(
        "babeldoc.format.pdf.document_il.utils.rect_flow_stack.list_links_on",
        return_value=list_links,
    )
    p2 = patch(
        "babeldoc.format.pdf.document_il.utils.rect_flow_stack._rect_links",
        return_value=rect_links,
    )

    class CombinedMock:
        def __enter__(self):
            p1.__enter__()
            p2.__enter__()
            return self

        def __exit__(self, *args):
            p2.__exit__(*args)
            p1.__exit__(*args)

    return CombinedMock()


def test_multi_line_run_in_lead_does_not_split():
    """Multi-line heading run-in lead (e.g. bold heading wrapping to line 2 before body) does not split."""
    from babeldoc.format.pdf.document_il.utils.paragraph_split_policy import (
        multi_line_run_in_continues,
    )
    from babeldoc.format.pdf.document_il.utils.paragraph_split_policy import (
        should_split_line_pair,
    )

    def mk_line(text, font_id, x=100.0, y=500.0):
        chars = [
            PdfCharacter(
                char_unicode=c,
                box=Box(x=x + i * 6, y=y, x2=x + (i + 1) * 6, y2=y + 10),
                pdf_style=PdfStyle(font_id=font_id, font_size=10.0),
            )
            for i, c in enumerate(text)
        ]
        return PdfLine(
            box=Box(x=x, y=y, x2=x + len(text) * 6, y2=y + 10),
            pdf_character=chars,
        )

    # Line 0: bold numbered title
    l0 = mk_line(
        "3. SIT DOWN WITH YOUR LADY ONCE A DAY AND DISCUSS WHAT'S",
        "BoldFont",
    )
    # Line 1: finishes bold title, continues with body text
    chars_l1 = [
        PdfCharacter(
            char_unicode=c,
            box=Box(x=100 + i * 6, y=485, x2=100 + (i + 1) * 6, y2=495),
            pdf_style=PdfStyle(font_id="BoldFont", font_size=10.0),
        )
        for i, c in enumerate("GOING ON WITH HER. ")
    ] + [
        PdfCharacter(
            char_unicode=c,
            box=Box(x=214 + i * 6, y=485, x2=214 + (i + 1) * 6, y2=495),
            pdf_style=PdfStyle(font_id="BodyFont", font_size=10.0),
        )
        for i, c in enumerate("This means talking about what she feels...")
    ]
    l1 = PdfLine(box=Box(x=100, y=485, x2=500, y2=495), pdf_character=chars_l1)

    assert multi_line_run_in_continues(l0, l1)
    assert not should_split_line_pair(
        l0,
        l1,
        median_width=400,
        split_short_lines=True,
        short_line_split_factor=0.6,
    )

