"""PR-02 follow-up: single dispatch site + watermark method name.

Production entry:
- ``translator_supports_llm`` — probe ``do_llm_translate(None)``
- ``create_paragraph_translator`` — only place that picks IL vs LLM midend
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from babeldoc.format.pdf.document_il.midend.il_translator import ILTranslator
from babeldoc.format.pdf.document_il.midend.il_translator_llm_only import (
    ILTranslatorLLMOnly,
)
from babeldoc.format.pdf.document_il.midend.typesetting import Typesetting
from babeldoc.format.pdf.high_level import create_paragraph_translator
from babeldoc.format.pdf.high_level import generate_first_page_with_watermark
from babeldoc.format.pdf.high_level import translator_supports_llm
from babeldoc.format.pdf.translation_config import TranslationConfig
from babeldoc.translator.fixed_map_translator import FixedMapTranslator


def _minimal_config(translator) -> TranslationConfig:
    return TranslationConfig(
        translator=translator,
        input_file="dispatch_test.pdf",
        lang_in="en",
        lang_out="zh-CN",
        doc_layout_model=MagicMock(),
        auto_extract_glossary=False,
    )


class _LlmOk:
    """Duck-typed engine that passes the LLM probe."""

    name = "llmsstub"
    lang_in = "en"
    lang_out = "zh-CN"
    ignore_cache = True

    def do_llm_translate(self, text, rate_limit_params=None):
        return None

    def translate(self, text, ignore_cache=False, rate_limit_params=None):
        return text

    def llm_translate(self, text, ignore_cache=False, rate_limit_params=None):
        return text

    def get_formular_placeholder(self, placeholder_id):
        return f"<b{placeholder_id}>"

    def get_rich_text_left_placeholder(self, placeholder_id):
        return f"<b{placeholder_id}>"

    def get_rich_text_right_placeholder(self, placeholder_id):
        return f"</b{placeholder_id}>"


class _NoLlmMethod:
    name = "nolmmethod"


class _LlmOtherError:
    name = "llmerr"

    def do_llm_translate(self, text, rate_limit_params=None):
        raise RuntimeError("backend down")


class TestTranslatorSupportsLlm:
    def test_none_is_false(self):
        assert translator_supports_llm(None) is False

    def test_missing_method_is_false(self):
        assert translator_supports_llm(_NoLlmMethod()) is False

    def test_not_implemented_is_false(self):
        assert translator_supports_llm(FixedMapTranslator()) is False

    def test_successful_probe_is_true(self):
        assert translator_supports_llm(_LlmOk()) is True

    def test_other_exception_is_false(self):
        assert translator_supports_llm(_LlmOtherError()) is False


class TestCreateParagraphTranslator:
    """Lock the production factory used by ``_do_translate_single``."""

    def test_fixed_map_builds_il_translator(self):
        engine = FixedMapTranslator()
        cfg = _minimal_config(engine)
        mid = create_paragraph_translator(engine, cfg)
        assert type(mid) is ILTranslator

    def test_llm_engine_builds_llm_only(self):
        engine = _LlmOk()
        cfg = _minimal_config(engine)
        mid = create_paragraph_translator(engine, cfg)
        assert type(mid) is ILTranslatorLLMOnly


class TestWatermarkTypesettingMethodName:
    def test_generate_first_page_calls_typesetting_document(self, monkeypatch):
        """Regression: typsetting_document typo must not return."""
        called: list = []

        def _capture(self, document):
            called.append(document)

        monkeypatch.setattr(Typesetting, "typesetting_document", _capture)

        # Fail fast if old typo is reintroduced
        if hasattr(Typesetting, "typsetting_document"):
            pytest.fail("typo method typsetting_document still exists")

        # Avoid full PDFCreater/write path
        class _FakeCreater:
            def __init__(self, *a, **k):
                pass

            def write(self, config):
                r = MagicMock()
                r.mono_pdf_path = None
                r.dual_pdf_path = None
                return r

        monkeypatch.setattr(
            "babeldoc.format.pdf.high_level.PDFCreater",
            _FakeCreater,
        )
        monkeypatch.setattr(
            "babeldoc.format.pdf.high_level.safe_save",
            lambda *a, **k: None,
        )

        import pymupdf
        from babeldoc.format.pdf.document_il import il_version_1

        mupdf = pymupdf.open()
        mupdf.new_page()
        page = il_version_1.Page(page_number=0, pdf_paragraph=[])
        doc_il = il_version_1.Document(page=[page], total_pages=1)
        cfg = _minimal_config(FixedMapTranslator())
        cfg.progress_monitor = MagicMock()
        cfg.progress_monitor.disable = False
        cfg.get_working_file_path = MagicMock(return_value=MagicMock(as_posix=lambda: "x.pdf"))

        generate_first_page_with_watermark(mupdf, cfg, doc_il, mediabox_data=None)
        mupdf.close()

        assert len(called) == 1
