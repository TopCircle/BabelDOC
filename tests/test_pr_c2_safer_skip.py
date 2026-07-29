"""PR-C2: safer header band + figure spatial skip bounds."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import Page
from babeldoc.format.pdf.document_il.il_version_1 import PageLayout
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
from babeldoc.format.pdf.document_il.midend.il_translator import ILTranslator
from babeldoc.format.pdf.document_il.utils.layout_helper import is_figure_text_paragraph
from babeldoc.format.pdf.document_il.utils.region_skip import is_header_chrome_exempt
from babeldoc.format.pdf.document_il.utils.region_skip import should_skip_header_footer
from babeldoc.format.pdf.translation_config import TranslationConfig
from babeldoc.translator.fixed_map_translator import FixedMapTranslator


def _style() -> PdfStyle:
    return PdfStyle(font_id="f0", font_size=10.0, graphic_state=None)


def _para(
    text: str,
    *,
    label: str | None = "plain text",
    box: Box | None = None,
) -> PdfParagraph:
    return PdfParagraph(
        box=box or Box(x=100, y=750, x2=500, y2=780),
        pdf_style=_style(),
        pdf_paragraph_composition=[],
        unicode=text,
        layout_label=label,
        debug_id="t",
    )


def _page() -> Page:
    return Page(
        page_number=0,
        cropbox=SimpleNamespace(box=Box(x=0, y=0, x2=612, y2=792)),
        page_layout=[],
        pdf_paragraph=[],
    )


def test_title_and_section_header_never_header_skipped():
    page = _page()
    title = _para("Love and Sex", label="title", box=Box(x=50, y=750, x2=400, y2=785))
    sec = _para(
        "Are You Lost at Sea?",
        label="section_header",
        box=Box(x=50, y=740, x2=400, y2=770),
    )
    assert is_header_chrome_exempt(title)
    assert is_header_chrome_exempt(sec)
    assert not should_skip_header_footer(
        page,
        title,
        skip_header=True,
        skip_footer=False,
        header_height=50,
        footer_height=40,
    )
    assert not should_skip_header_footer(
        page,
        sec,
        skip_header=True,
        skip_footer=False,
        header_height=50,
        footer_height=40,
    )


def test_short_running_header_still_skipped():
    page = _page()
    chrome = _para(
        "Learn The Trigasm",
        label="plain text",
        box=Box(x=200, y=760, x2=400, y2=780),
    )
    assert not is_header_chrome_exempt(chrome)
    assert should_skip_header_footer(
        page,
        chrome,
        skip_header=True,
        skip_footer=False,
        header_height=50,
        footer_height=40,
    )


def test_long_plain_text_in_header_band_not_skipped():
    """Plan: plain text body in header geometry must still MT."""
    page = _page()
    body = _para(
        "The testicles massaged along the perineum create a deep sensation "
        "that many people describe as profoundly relaxing.",
        label="plain text",
        box=Box(x=72, y=750, x2=520, y2=780),  # fully in 50pt band
    )
    assert is_header_chrome_exempt(body)
    assert not should_skip_header_footer(
        page,
        body,
        skip_header=True,
        skip_footer=False,
        header_height=50,
        footer_height=40,
    )


def test_tall_body_block_in_band_not_skipped():
    page = _page()
    body = _para(
        "Short but multi-line body start.",
        label="plain text",
        box=Box(x=72, y=740, x2=400, y2=780),  # h=40 ≥ 28
    )
    assert is_header_chrome_exempt(body)
    assert not should_skip_header_footer(
        page,
        body,
        skip_header=True,
        skip_footer=False,
        header_height=60,
        footer_height=40,
    )


def test_spatial_figure_rejects_body_prose():
    fig = PageLayout(
        id=1,
        conf=1.0,
        class_name="figure",
        box=Box(x=50, y=100, x2=560, y2=700),
    )
    page = Page(
        page_number=0,
        page_layout=[fig],
        cropbox=SimpleNamespace(box=Box(x=0, y=0, x2=612, y2=792)),
        pdf_paragraph=[],
    )
    prose = _para(
        "Women like different things when it comes to touch and timing.",
        label="text",
        box=Box(x=100, y=200, x2=250, y2=280),  # inside big figure, not huge width
    )
    assert is_figure_text_paragraph(prose, page) is False


def test_spatial_figure_still_matches_short_label():
    fig = PageLayout(
        id=1,
        conf=1.0,
        class_name="figure",
        box=Box(x=300, y=500, x2=560, y2=720),
    )
    page = Page(
        page_number=0,
        page_layout=[fig],
        cropbox=SimpleNamespace(box=Box(x=0, y=0, x2=612, y2=792)),
        pdf_paragraph=[],
    )
    label = _para(
        "Data A",
        label="text",
        box=Box(x=320, y=570, x2=345, y2=585),
    )
    assert is_figure_text_paragraph(label, page) is True


def test_translator_region_skip_uses_c2():
    cfg = TranslationConfig(
        translator=FixedMapTranslator(),
        input_file="c2.pdf",
        lang_in="en",
        lang_out="zh-CN",
        doc_layout_model=MagicMock(),
        auto_extract_glossary=False,
        skip_header=True,
        header_height=50,
    )
    tr = ILTranslator(cfg.translator, cfg)
    page = _page()
    chrome = _para(
        "Chapter 1",
        label="plain text",
        box=Box(x=40, y=760, x2=120, y2=780),
    )
    body = _para(
        "Scientific studies have shown that the pelvic floor responds to "
        "consistent practice over several weeks of training.",
        label="plain text",
        box=Box(x=72, y=745, x2=500, y2=780),
    )
    assert tr.should_skip_header_footer_paragraph(page, chrome) is True
    assert tr.region_skip_reason(page, chrome) is not None
    assert tr.should_skip_header_footer_paragraph(page, body) is False
    assert tr.region_skip_reason(page, body) is None
