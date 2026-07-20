"""Phase A: searchable dual-layer PDF detection → auto OCR workaround.

No paragraph-split or typesetting changes — detect + flag only.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pymupdf
import pytest

from babeldoc.format.pdf.document_il.midend.detect_scanned_file import (
    enable_ocr_workaround_for_searchable_image,
    is_searchable_image_pdf,
    page_has_fullpage_image,
    page_has_invisible_text_layer,
)
from babeldoc.format.pdf.translation_config import TranslationConfig
from babeldoc.translator.fixed_map_translator import FixedMapTranslator

GOLDEN = Path(__file__).resolve().parent / "golden"


def _config(**kwargs) -> TranslationConfig:
    return TranslationConfig(
        translator=FixedMapTranslator(),
        input_file="x.pdf",
        lang_in="en",
        lang_out="zh-CN",
        doc_layout_model=MagicMock(),
        auto_extract_glossary=False,
        ocr_workaround=False,
        **kwargs,
    )


class TestSearchableImageDetection:
    def test_font_unknown_is_searchable_image(self):
        path = GOLDEN / "translate.cli.font.unknown.pdf"
        if not path.exists():
            pytest.skip("golden font.unknown missing")
        doc = pymupdf.open(path)
        page = doc[0]
        assert page_has_fullpage_image(page)
        assert page_has_invisible_text_layer(doc, page)
        assert is_searchable_image_pdf(doc) is True
        doc.close()

    def test_plain_text_is_not_searchable_image(self):
        path = GOLDEN / "translate.cli.plain.text.pdf"
        if not path.exists():
            pytest.skip("golden plain.text missing")
        doc = pymupdf.open(path)
        assert is_searchable_image_pdf(doc) is False
        assert page_has_fullpage_image(doc[0]) is False
        doc.close()

    def test_figure_pdf_not_dual_layer(self):
        """Figure XObject alone must not trigger OCR white-fill for whole doc."""
        path = GOLDEN / "translate.cli.text.with.figure.pdf"
        if not path.exists():
            pytest.skip("golden figure missing")
        doc = pymupdf.open(path)
        assert is_searchable_image_pdf(doc) is False
        doc.close()

    def test_enable_ocr_workaround_sets_flags(self):
        path = GOLDEN / "translate.cli.font.unknown.pdf"
        if not path.exists():
            pytest.skip("golden font.unknown missing")
        doc = pymupdf.open(path)
        cfg = _config()
        assert cfg.ocr_workaround is False
        assert enable_ocr_workaround_for_searchable_image(cfg, doc) is True
        assert cfg.ocr_workaround is True
        assert (
            cfg.shared_context_cross_split_part.auto_enabled_ocr_workaround is True
        )
        assert cfg.disable_rich_text_translate is True
        assert cfg.skip_scanned_detection is True
        # Second call is a no-op once already enabled
        assert enable_ocr_workaround_for_searchable_image(cfg, doc) is False
        doc.close()

    def test_enable_skips_plain(self):
        path = GOLDEN / "translate.cli.plain.text.pdf"
        if not path.exists():
            pytest.skip("golden plain.text missing")
        doc = pymupdf.open(path)
        cfg = _config()
        assert enable_ocr_workaround_for_searchable_image(cfg, doc) is False
        assert cfg.ocr_workaround is False
        assert cfg.skip_scanned_detection is False
        doc.close()

    def test_enable_skips_figure(self):
        path = GOLDEN / "translate.cli.text.with.figure.pdf"
        if not path.exists():
            pytest.skip("golden figure missing")
        doc = pymupdf.open(path)
        cfg = _config()
        assert enable_ocr_workaround_for_searchable_image(cfg, doc) is False
        assert cfg.ocr_workaround is False
        doc.close()

    def test_empty_doc_is_not_searchable(self):
        assert is_searchable_image_pdf(None) is False
        doc = pymupdf.open()
        try:
            assert is_searchable_image_pdf(doc) is False
            cfg = _config()
            assert enable_ocr_workaround_for_searchable_image(cfg, doc) is False
        finally:
            doc.close()
