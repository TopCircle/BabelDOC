"""LayoutIntentExtractor unit tests (Layout-First P0, extractor worker).

Covers role classification (§1.4 strict 9-rule order), design-box deep copy,
visual-bbox insets, wrap_shape, gap_contract (stub/chrome exclusion +
stack-bottom only), text_on_photo IoU, silent failure isolation, --debug
dump, and the fingerprint invariant (runtime intent must not change the
geometry fingerprint).
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from babeldoc.format.pdf.document_il import il_version_1
from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter
from babeldoc.format.pdf.document_il.il_version_1 import PdfLine
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraphComposition
from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
from babeldoc.format.pdf.document_il.il_version_1 import VisualBbox
from babeldoc.format.pdf.document_il.utils import layout_intent_extractor
from babeldoc.format.pdf.document_il.utils.il_layout_fingerprint import (
    il_layout_fingerprint,
)
from babeldoc.format.pdf.document_il.utils.layout_intent import LayoutIntentRole

PAGE_WIDTH = 612.0
PAGE_HEIGHT = 792.0


# ---------------------------------------------------------------- builders


def _style(font_size: float = 12.0) -> PdfStyle:
    return PdfStyle(font_id="base", font_size=font_size, graphic_state=None)


def _char(
    x: float,
    x2: float,
    y: float,
    y2: float,
    *,
    font_size: float = 12.0,
    visual: Box | None = None,
) -> PdfCharacter:
    return PdfCharacter(
        char_unicode="a",
        box=Box(x=x, y=y, x2=x2, y2=y2),
        visual_bbox=VisualBbox(box=visual) if visual is not None else None,
        pdf_style=_style(font_size),
    )


def _line(
    x: float,
    x2: float,
    y: float,
    y2: float,
    *,
    font_size: float = 12.0,
) -> PdfLine:
    return PdfLine(
        box=Box(x=x, y=y, x2=x2, y2=y2),
        pdf_character=[_char(x, x2, y, y2, font_size=font_size)],
    )


def _para(
    box: Box | None = None,
    *,
    label: str | None = None,
    unicode_: str = "text",
    debug_id: str | None = None,
    lines: list[PdfLine] | None = None,
    chars: list[PdfCharacter] | None = None,
    font_size: float = 12.0,
) -> PdfParagraph:
    p = il_version_1.PdfParagraph(
        box=box,
        unicode=unicode_,
        layout_label=label,
        debug_id=debug_id,
        pdf_style=_style(font_size),
    )
    if lines is not None:
        p.pdf_paragraph_composition = [
            PdfParagraphComposition(pdf_line=line) for line in lines
        ]
    elif chars is not None:
        p.pdf_paragraph_composition = [
            PdfParagraphComposition(pdf_character=ch) for ch in chars
        ]
    return p


def _page(
    paras: list[PdfParagraph],
    *,
    page_number: int = 1,
    figures: list | None = None,
    forms: list | None = None,
) -> il_version_1.Page:
    return il_version_1.Page(
        cropbox=il_version_1.Cropbox(
            box=Box(x=0, y=0, x2=PAGE_WIDTH, y2=PAGE_HEIGHT)
        ),
        mediabox=il_version_1.Mediabox(
            box=Box(x=0, y=0, x2=PAGE_WIDTH, y2=PAGE_HEIGHT)
        ),
        pdf_paragraph=paras,
        pdf_figure=figures or [],
        pdf_form=forms or [],
        page_number=page_number,
        base_operations=il_version_1.BaseOperations(value=""),
        unit="pt",
    )


def _config(workdir: Path | None = None, *, debug: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        debug=debug,
        get_working_file_path=lambda name: Path(workdir) / name if workdir else None,
    )


def _extract(page: il_version_1.Page, workdir: Path | None = None, *, debug: bool = False):
    doc = il_version_1.Document(page=[page], total_pages=1)
    extractor = layout_intent_extractor.LayoutIntentExtractor(
        _config(workdir, debug=debug)
    )
    extractor.extract(doc)
    return extractor


# ------------------------------------------------------------------- roles


def test_role_chrome():
    para = _para(
        Box(x=10, y=10, x2=600, y2=30),
        label="footer",
        lines=[_line(10, 100, 10, 30)],
    )
    _extract(_page([para]))
    intent = para.layout_intent
    assert intent.role is LayoutIntentRole.CHROME
    assert intent.is_chrome is True
    # CHROME projects no expansion axes and no photo signal.
    assert intent.expansion_policy == ()
    assert intent.text_on_photo is False


def test_role_wrap_column_single_source(monkeypatch):
    """WRAP_COLUMN comes only from is_figure_wrap_paragraph (single source)."""
    para = _para(
        Box(x=100, y=0, x2=300, y2=40),
        lines=[_line(104, 300, 20, 40), _line(110, 300, 0, 20)],
    )
    monkeypatch.setattr(
        layout_intent_extractor, "is_figure_wrap_paragraph", lambda _p: True
    )
    _extract(_page([para]))
    assert para.layout_intent.role is LayoutIntentRole.WRAP_COLUMN

    not_wrap = _para(
        Box(x=100, y=0, x2=300, y2=40),
        lines=[_line(104, 300, 20, 40), _line(110, 300, 0, 20)],
    )
    monkeypatch.setattr(
        layout_intent_extractor, "is_figure_wrap_paragraph", lambda _p: False
    )
    _extract(_page([not_wrap]))
    assert not_wrap.layout_intent.role is not LayoutIntentRole.WRAP_COLUMN


def test_role_subtitle_overlay():
    title = _para(
        Box(x=0, y=90, x2=400, y2=130),
        label="title",
        debug_id="t1",
        lines=[_line(0, 400, 90, 130, font_size=56)],
        font_size=56,
    )
    subtitle = _para(
        Box(x=0, y=95, x2=400, y2=115),
        label="text",
        debug_id="s1",
        lines=[_line(0, 400, 95, 115, font_size=15)],
        font_size=15,
    )
    _extract(_page([title, subtitle]))
    assert title.layout_intent.role is LayoutIntentRole.TITLE
    assert subtitle.layout_intent.role is LayoutIntentRole.SUBTITLE_OVERLAY
    assert subtitle.layout_intent.overlays_band == "t1"


def test_role_pull_quote_single_source(monkeypatch):
    """PULL_QUOTE comes only from is_quote_block (P0 single source)."""
    para = _para(
        Box(x=50, y=50, x2=150, y2=70),
        lines=[_line(50, 150, 50, 70)],
    )
    monkeypatch.setattr(layout_intent_extractor, "is_quote_block", lambda _p, _w: True)
    _extract(_page([para]))
    assert para.layout_intent.role is LayoutIntentRole.PULL_QUOTE

    not_quote = _para(
        Box(x=50, y=50, x2=150, y2=70),
        lines=[_line(50, 150, 50, 70)],
    )
    monkeypatch.setattr(layout_intent_extractor, "is_quote_block", lambda _p, _w: False)
    _extract(_page([not_quote]))
    assert not_quote.layout_intent.role is not LayoutIntentRole.PULL_QUOTE


def test_role_debug_stub_is_body_not_callout(monkeypatch):
    """LayoutParser stubs stay BODY even when callout/quote heuristics fire."""
    # Narrow box would otherwise look like a callout column.
    stub = _para(
        Box(x=47, y=38.9, x2=153, y2=46),
        unicode_="abandon",
        lines=[_line(47, 153, 38.9, 46, font_size=4)],
        font_size=4,
    )
    # Force both heuristics true — stub short-circuit must win first.
    monkeypatch.setattr(layout_intent_extractor, "is_quote_block", lambda _p, _w: True)
    monkeypatch.setattr(
        layout_intent_extractor, "is_callout_column", lambda _b: True
    )
    _extract(_page([stub]))
    assert stub.layout_intent.role is LayoutIntentRole.BODY
    assert stub.layout_intent.is_chrome is False
    assert stub.layout_intent.text_on_photo is False


# ------------------------------------------------------------ intent fields


def test_design_box_is_deep_copy():
    box = Box(x=10, y=10, x2=200, y2=40)
    para = _para(box, lines=[_line(10, 200, 10, 40)])
    _extract(_page([para]))
    # Mutating the source box (and para.box) must not touch the snapshot.
    box.x = 999
    para.box.x2 = 999
    assert para.layout_intent.design_box.x == 10
    assert para.layout_intent.design_box.x2 == 200


def test_insets_from_visual_bbox():
    # Char box includes leading; visual bbox is the tighter rendered ink.
    char = _char(10, 20, y=5, y2=95, visual=Box(x=10, y=10, x2=20, y2=90))
    para = _para(Box(x=0, y=0, x2=200, y2=100), chars=[char])
    _extract(_page([para]))
    intent = para.layout_intent
    # top = design.y2 - visual.y2 (100-90); bottom = visual.y - design.y (10-0).
    assert intent.top_inset == pytest.approx(10.0)
    assert intent.bottom_inset == pytest.approx(10.0)


def test_wrap_shape_left_offset_width(monkeypatch):
    monkeypatch.setattr(
        layout_intent_extractor, "is_figure_wrap_paragraph", lambda _p: True
    )
    para = _para(
        Box(x=100, y=0, x2=300, y2=40),
        lines=[_line(104, 300, 20, 40), _line(110, 300, 0, 20)],
    )
    _extract(_page([para]))
    assert para.layout_intent.wrap_shape == [(4.0, 196.0), (10.0, 190.0)]


# ------------------------------------------------------ gap / stack / photo


def test_gap_contract_excludes_stub_chrome():
    body = _para(
        Box(x=0, y=100, x2=200, y2=120),
        label="text",
        lines=[_line(0, 200, 100, 120)],
    )
    chrome = _para(
        Box(x=0, y=70, x2=200, y2=90),
        label="footer",
        debug_id="footer",
        lines=[_line(0, 200, 70, 90)],
    )
    # Debug stub (unicode == layout class name) defaults to BODY but must not
    # be used as a gap candidate.
    stub = _para(
        Box(x=0, y=80, x2=400, y2=95),
        unicode_="fallback_line",
        debug_id="stub",
        lines=[_line(0, 400, 80, 95)],
    )
    below = _para(
        Box(x=0, y=30, x2=200, y2=50),
        label="text",
        lines=[_line(0, 200, 30, 50)],
    )
    _extract(_page([body, chrome, stub, below]))
    assert stub.layout_intent.role is LayoutIntentRole.BODY
    assert chrome.layout_intent.is_chrome is True
    # The nearest chrome (y2=90) and stub (y2=95) are excluded: gap must be
    # measured against the real body below (y2=50), not them.
    assert body.layout_intent.gap_contract == pytest.approx(50.0)
    assert chrome.layout_intent.gap_contract is None
    assert below.layout_intent.gap_contract is None


def test_gap_contract_stack_bottom_only():
    upper = _para(
        Box(x=0, y=90, x2=200, y2=130),
        label="text",
        lines=[_line(0, 200, 90, 130)],
    )
    lower = _para(
        Box(x=0, y=80, x2=200, y2=120),
        label="text",
        lines=[_line(0, 200, 80, 120)],
    )
    third = _para(
        Box(x=0, y=40, x2=200, y2=60),
        label="text",
        lines=[_line(0, 200, 40, 60)],
    )
    _extract(_page([upper, lower, third]))
    assert upper.layout_intent.stack == lower.layout_intent.stack
    assert lower.layout_intent.stack != third.layout_intent.stack
    # Only the stack bottom (lower) carries a gap_contract.
    assert upper.layout_intent.gap_contract is None
    assert lower.layout_intent.gap_contract == pytest.approx(20.0)
    assert third.layout_intent.gap_contract is None


def test_text_on_photo_iou():
    photo = il_version_1.PdfFigure(box=Box(x=0, y=0, x2=200, y2=200))
    on_photo = _para(
        Box(x=0, y=0, x2=200, y2=200),
        label="text",
        lines=[_line(0, 200, 0, 200)],
    )
    off_photo = _para(
        Box(x=300, y=300, x2=400, y2=400),
        label="text",
        lines=[_line(300, 400, 300, 400)],
    )
    chrome_on_photo = _para(
        Box(x=0, y=0, x2=200, y2=200),
        label="footer",
        lines=[_line(0, 200, 0, 200)],
    )
    stub_on_photo = _para(
        Box(x=0, y=0, x2=200, y2=200),
        unicode_="fallback_line",
        lines=[_line(0, 200, 0, 200)],
    )
    _extract(
        _page(
            [on_photo, off_photo, chrome_on_photo, stub_on_photo],
            figures=[photo],
        )
    )
    assert on_photo.layout_intent.text_on_photo is True
    assert off_photo.layout_intent.text_on_photo is False
    assert chrome_on_photo.layout_intent.text_on_photo is False
    assert stub_on_photo.layout_intent.role is LayoutIntentRole.BODY
    assert stub_on_photo.layout_intent.text_on_photo is False


def test_non_image_form_not_photo_zone():
    """Only form_type=='image' forms count as photo boxes (exclusion_zone parity)."""
    image_form = il_version_1.PdfForm(
        box=Box(x=0, y=0, x2=200, y2=200),
        form_type="image",
        graphic_state=None,
        pdf_matrix=None,
        pdf_affine_transform=None,
        pdf_form_subtype=None,
    )
    other_form = il_version_1.PdfForm(
        box=Box(x=300, y=300, x2=500, y2=500),
        form_type="form",
        graphic_state=None,
        pdf_matrix=None,
        pdf_affine_transform=None,
        pdf_form_subtype=None,
    )
    on_image = _para(
        Box(x=0, y=0, x2=200, y2=200),
        label="text",
        lines=[_line(0, 200, 0, 200)],
    )
    on_other = _para(
        Box(x=300, y=300, x2=500, y2=500),
        label="text",
        lines=[_line(300, 500, 300, 500)],
    )
    _extract(
        _page([on_image, on_other], forms=[image_form, other_form])
    )
    assert on_image.layout_intent.text_on_photo is True
    assert on_other.layout_intent.text_on_photo is False


# ------------------------------------------------------- robustness / dump


def test_extract_failure_is_silent(monkeypatch):
    p1 = _para(Box(x=0, y=0, x2=100, y2=20), debug_id="p1", lines=[_line(0, 100, 0, 20)])
    p2 = _para(Box(x=0, y=0, x2=100, y2=20), debug_id="p2", lines=[_line(0, 100, 0, 20)])
    doc = il_version_1.Document(
        page=[_page([p1], page_number=1), _page([p2], page_number=2)]
    )
    extractor = layout_intent_extractor.LayoutIntentExtractor(_config())
    original = layout_intent_extractor.LayoutIntentExtractor._extract_page

    def flaky(self, page):
        if page.page_number == 1:
            raise RuntimeError("boom")
        return original(self, page)

    monkeypatch.setattr(
        layout_intent_extractor.LayoutIntentExtractor, "_extract_page", flaky
    )
    extractor.extract(doc)  # must not raise
    assert extractor.audit["pages_skipped"] == 1
    assert p2.layout_intent is not None


def test_dump_only_debug(tmp_path):
    para = _para(
        Box(x=0, y=0, x2=400, y2=20),
        debug_id="p1",
        lines=[_line(0, 400, 0, 20)],
    )
    page = _page([para])
    doc = il_version_1.Document(page=[page])
    dump_path = tmp_path / "layout_intent.json"

    layout_intent_extractor.LayoutIntentExtractor(_config(tmp_path, debug=False)).extract(
        doc
    )
    assert not dump_path.exists()

    layout_intent_extractor.LayoutIntentExtractor(_config(tmp_path, debug=True)).extract(
        doc
    )
    assert dump_path.exists()
    data = json.loads(dump_path.read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert "pages" in data and "audit" in data
    assert data["pages"]["1"]["p1"]["role"] == "body"
    assert data["audit"]["no_box"] == 0
    assert data["audit"]["pages_skipped"] == 0


def test_fingerprint_ignores_layout_intent():
    para = _para(
        Box(x=0, y=0, x2=200, y2=20),
        label="text",
        lines=[_line(0, 200, 0, 20)],
    )
    doc = il_version_1.Document(page=[_page([para])])
    before = il_layout_fingerprint(doc)
    layout_intent_extractor.LayoutIntentExtractor(_config()).extract(doc)
    after = il_layout_fingerprint(doc)
    assert before == after


def test_extract_does_not_mutate_paragraph_geometry():
    """Direct behavior-invariance: extract is read-only on box/composition."""
    line = _line(10, 200, 10, 40)
    para = _para(Box(x=10, y=10, x2=200, y2=40), lines=[line])
    box_before = (para.box.x, para.box.y, para.box.x2, para.box.y2)
    line_before = (line.box.x, line.box.y, line.box.x2, line.box.y2)
    ch = line.pdf_character[0]
    ch_before = (ch.box.x, ch.box.y, ch.box.x2, ch.box.y2)
    _extract(_page([para]))
    assert (para.box.x, para.box.y, para.box.x2, para.box.y2) == box_before
    assert (line.box.x, line.box.y, line.box.x2, line.box.y2) == line_before
    assert (ch.box.x, ch.box.y, ch.box.x2, ch.box.y2) == ch_before
    assert para.layout_intent is not None


def test_gap_contract_skips_drop_cap_line():
    """gap_contract measures to the first *regular* line, not the drop cap.

    p19 regression: the EN body below the 56pt title starts with an oversized
    drop-cap initial whose top (~11pt below the title) made the contract
    ~11.2pt instead of the first-body-line clearance (~18pt) the P1
    acceptance tool uses. The drop-cap glyph must be excluded.
    """
    title = _para(
        Box(x=0, y=90, x2=300, y2=130),
        label="title",
        debug_id="t1",
        lines=[_line(0, 300, 90, 130, font_size=56)],
        font_size=56,
    )
    # Body with an oversized drop-cap "I" (33.7pt) followed by regular 12.5pt
    # text. Drop-cap top (y2=90) sits well above the regular first-line top
    # (y2=80); the contract must measure to the regular line (10pt), not the
    # drop cap (0pt).
    drop_cap = _char(0, 20, 40, 90, font_size=33.7)
    regular = [
        _char(22, 40, 50, 80, font_size=12.5),
        _char(42, 60, 50, 80, font_size=12.5),
    ]
    body = _para(
        Box(x=0, y=40, x2=300, y2=90),
        label="text",
        chars=[drop_cap, *regular],
        font_size=12.5,
    )
    _extract(_page([title, body]))
    # title ink bottom = 90; regular first line top = 80 -> contract 10.
    assert body.layout_intent.gap_contract is None
    assert title.layout_intent.gap_contract == pytest.approx(10.0)


def test_gap_contract_unchanged_without_drop_cap():
    """Paragraphs without oversized glyphs keep the raw ink-top contract."""
    upper = _para(
        Box(x=0, y=90, x2=300, y2=130),
        label="text",
        lines=[_line(0, 300, 90, 130)],
    )
    below = _para(
        Box(x=0, y=40, x2=300, y2=60),
        label="text",
        lines=[_line(0, 300, 40, 60)],
    )
    _extract(_page([upper, below]))
    # gap = upper ink bottom (90) - below ink top (60) = 30.
    assert upper.layout_intent.gap_contract == pytest.approx(90.0 - 60.0)
    assert below.layout_intent.gap_contract is None
