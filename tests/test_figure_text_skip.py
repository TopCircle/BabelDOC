"""Skip MT for in-figure labels when translate_figure_text is off."""

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
from babeldoc.format.pdf.translation_config import TranslationConfig
from babeldoc.translator.fixed_map_translator import FixedMapTranslator


def _style() -> PdfStyle:
    return PdfStyle(font_id="f0", font_size=10.0, graphic_state=None)


def _para(
    text: str,
    *,
    label: str | None = None,
    box: Box | None = None,
) -> PdfParagraph:
    return PdfParagraph(
        box=box or Box(x=320, y=560, x2=350, y2=575),
        pdf_style=_style(),
        pdf_paragraph_composition=[],
        unicode=text,
        layout_label=label,
        debug_id="fig",
    )


def _page_with_figure() -> Page:
    fig = PageLayout(
        id=1,
        conf=1.0,
        class_name="figure",
        box=Box(x=300, y=500, x2=560, y2=720),
    )
    return Page(
        page_number=0,
        page_layout=[fig],
        pdf_paragraph=[],
        cropbox=SimpleNamespace(box=Box(x=0, y=0, x2=612, y2=792)),
    )


def _config(*, translate_figure_text: bool = False) -> TranslationConfig:
    return TranslationConfig(
        translator=FixedMapTranslator(),
        input_file="fig.pdf",
        lang_in="en",
        lang_out="zh-CN",
        doc_layout_model=MagicMock(),
        auto_extract_glossary=False,
        translate_figure_text=translate_figure_text,
    )


class TestIsFigureTextParagraph:
    def test_label_figure_text(self):
        assert is_figure_text_paragraph(_para("Ancilla", label="figure_text"))

    def test_caption_not_matched(self):
        assert not is_figure_text_paragraph(
            _para("Figure 1. A long caption about QEC.", label="figure_caption")
        )

    def test_spatial_short_label_in_figure(self):
        page = _page_with_figure()
        p = _para("Data A", label="text", box=Box(x=320, y=570, x2=345, y2=585))
        assert is_figure_text_paragraph(p, page, overlap_threshold=0.3)

    def test_long_body_in_figure_box_not_matched(self):
        page = _page_with_figure()
        long = "x" * 80
        p = _para(long, label="text", box=Box(x=310, y=510, x2=550, y2=700))
        assert not is_figure_text_paragraph(p, page, overlap_threshold=0.3)


class TestSkipInTranslator:
    def test_default_skips_figure_text(self):
        cfg = _config(translate_figure_text=False)
        tr = ILTranslator(cfg.translator, cfg)
        page = _page_with_figure()
        assert tr.should_skip_region_paragraph(
            page, _para("Ancilla", label="figure_text")
        )

    def test_opt_in_translates_figure_text(self):
        cfg = _config(translate_figure_text=True)
        tr = ILTranslator(cfg.translator, cfg)
        page = _page_with_figure()
        assert not tr.should_skip_region_paragraph(
            page, _para("Ancilla", label="figure_text")
        )
