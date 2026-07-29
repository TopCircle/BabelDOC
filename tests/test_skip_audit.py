"""PR-C1: skip_report reason enum + JSON (zero MT behavior)."""

from __future__ import annotations

import json
from pathlib import Path

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import Page
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
from babeldoc.format.pdf.document_il.utils.side_callout_skip import (
    should_skip_side_callout_mt,
)
from babeldoc.format.pdf.document_il.utils.skip_audit import PREVIEW_MAX
from babeldoc.format.pdf.document_il.utils.skip_audit import SkipReason
from babeldoc.format.pdf.document_il.utils.skip_audit import SkipReport
from babeldoc.format.pdf.document_il.utils.skip_audit import side_callout_skip_reason
from babeldoc.format.pdf.document_il.utils.skip_audit import unicode_preview


def _para(
    text: str,
    *,
    x: float = 100.0,
    x2: float = 500.0,
    y: float = 100.0,
    y2: float | None = None,
    layout_label: str | None = "plain text",
    debug_id: str | None = "p1",
) -> PdfParagraph:
    top = y2 if y2 is not None else y + 40
    p = PdfParagraph(
        box=Box(x=x, y=y, x2=x2, y2=top),
        pdf_style=PdfStyle(font_id="base", font_size=12.0, graphic_state=None),
        pdf_paragraph_composition=[],
        unicode=text,
    )
    if layout_label is not None:
        p.layout_label = layout_label
    p.debug_id = debug_id
    return p


def _page(*paras: PdfParagraph, page_number: int = 0) -> Page:
    p = Page(
        page_number=page_number,
        mediabox=Box(x=0, y=0, x2=612, y2=792),
        cropbox=Box(x=0, y=0, x2=612, y2=792),
    )
    p.pdf_paragraph = list(paras)
    return p


def test_skip_reason_stable_values():
    assert SkipReason.FIGURE_TEXT.value == "figure_text"
    assert SkipReason.HEADER.value == "header"
    assert SkipReason.FOOTER.value == "footer"
    assert SkipReason.ULTRA_NARROW.value == "ultra_narrow"
    assert SkipReason.PULLQUOTE.value == "pullquote"
    assert SkipReason.PURE_NUMERIC.value == "pure_numeric"
    assert SkipReason.PLACEHOLDER_ONLY.value == "placeholder_only"
    assert SkipReason.TOO_SHORT.value == "too_short"
    assert SkipReason.VERTICAL.value == "vertical"
    assert SkipReason.EMPTY_COMPOSITION.value == "empty_composition"


def test_unicode_preview_truncates():
    long = "a" * (PREVIEW_MAX + 20)
    prev = unicode_preview(long)
    assert len(prev) == PREVIEW_MAX
    assert prev.endswith("…")
    assert unicode_preview("short") == "short"
    assert unicode_preview(None) == ""


def test_skip_report_record_and_json(tmp_path: Path):
    report = SkipReport()
    page = _page(page_number=7)
    para = _para("testicles massaged along the perineum", debug_id="abc")
    report.record(
        page=page,
        paragraph=para,
        reason=SkipReason.ULTRA_NARROW,
    )
    report.record(
        page_number=8,
        paragraph_id="def",
        reason=SkipReason.HEADER,
        unicode="Learn The Trigasm",
        layout_label="section_header",
    )
    assert report.counts_by_reason() == {
        "ultra_narrow": 1,
        "header": 1,
    }
    data = report.to_dict()
    assert data["schema_version"] == 1
    assert data["total"] == 2
    assert data["events"][0]["page_number"] == 7
    assert data["events"][0]["paragraph_id"] == "abc"
    assert data["events"][0]["reason"] == "ultra_narrow"
    assert "testicles" in data["events"][0]["unicode_preview"]

    out = report.write_json(tmp_path / "skip_report.json")
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["total"] == 2
    assert loaded["counts_by_reason"]["header"] == 1


def test_side_callout_reason_matches_skip_predicate():
    quote = (
        "Since her orgasm is essentially an intense contraction of her PC and "
        "pelvic floor muscles, strengthening them increases blood flow to the "
        "area and enables her to experience a deeper pleasure sensation and a "
        "repeated series of pulses"
    )
    body = _para(
        f'"{quote}," says Laura Berman.',
        x=102,
        x2=360,
    )
    callout = _para(quote, x=360, x2=560)
    page = _page(body, callout)
    assert should_skip_side_callout_mt(callout, page) is True
    assert side_callout_skip_reason(callout, page) == SkipReason.PULLQUOTE
    assert side_callout_skip_reason(body, page) is None

    # Ultra-narrow tall strip (OA-style right callout ~80pt)
    narrow = _para(
        "x" * 40,
        x=480,
        x2=560,
        y=200,
        y2=400,
        layout_label="plain text",
    )
    page2 = _page(narrow)
    assert should_skip_side_callout_mt(narrow, page2) is True
    assert side_callout_skip_reason(narrow, page2) == SkipReason.ULTRA_NARROW


def test_side_callout_reason_none_when_not_skipped():
    body = _para("Normal body paragraph about anatomy and technique.", x=100, x2=500)
    page = _page(body)
    assert should_skip_side_callout_mt(body, page) is False
    assert side_callout_skip_reason(body, page) is None


def test_region_skip_reason_header_band():
    """Header band skip classifies as header; title layout is never skipped."""
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from babeldoc.format.pdf.document_il.midend.il_translator import ILTranslator

    cfg = MagicMock()
    cfg.skip_header = True
    cfg.skip_footer = False
    cfg.header_height = 50.0
    cfg.footer_height = 40.0
    cfg.ocr_workaround = False
    cfg.translate_figure_text = True  # disable figure path

    tr = object.__new__(ILTranslator)
    tr.translation_config = cfg
    tr.skip_report = SkipReport()

    # Page crop 0..792; header band y >= 742 — cropbox.box like real IL
    page = Page(
        page_number=3,
        mediabox=Box(x=0, y=0, x2=612, y2=792),
        cropbox=SimpleNamespace(box=Box(x=0, y=0, x2=612, y2=792)),
    )
    # Short chrome — still header-skipped (PR-C2)
    header = _para(
        "Learn The Trigasm", y=750, y2=780, layout_label="plain text"
    )
    title = _para("Love and Sex", y=750, y2=780, layout_label="title")
    body = _para("Body text in the middle.", y=400, y2=440, layout_label="plain text")

    assert tr.region_skip_reason(page, header) == SkipReason.HEADER
    assert tr.should_skip_region_paragraph(page, header) is True
    assert tr.region_skip_reason(page, title) is None
    assert tr.should_skip_region_paragraph(page, title) is False
    assert tr.region_skip_reason(page, body) is None
