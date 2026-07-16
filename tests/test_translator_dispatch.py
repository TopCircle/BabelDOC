"""PR-02: translator_supports_llm dispatch and FixedMap non-LLM path.

Mirrors production probe in ``babeldoc.format.pdf.high_level.translator_supports_llm``:
not merely “missing llm_translate attribute”, but calling ``do_llm_translate(None)``
and treating ``NotImplementedError`` as non-LLM.
"""

from __future__ import annotations

from babeldoc.format.pdf.document_il.midend.il_translator import ILTranslator
from babeldoc.format.pdf.document_il.midend.il_translator_llm_only import (
    ILTranslatorLLMOnly,
)
from babeldoc.format.pdf.high_level import translator_supports_llm
from babeldoc.translator.fixed_map_translator import FixedMapTranslator


class _RaisesNotImplemented:
    """Duck-typed DeepLX / CLI style engine (no BaseTranslator inheritance)."""

    name = "deeplxstub"
    lang_in = "en"
    lang_out = "zh-CN"
    ignore_cache = True

    def do_llm_translate(self, text, rate_limit_params=None):
        raise NotImplementedError

    def translate(self, text, ignore_cache=False, rate_limit_params=None):
        return text

    def get_formular_placeholder(self, placeholder_id):
        return f"<b{placeholder_id}>"

    def get_rich_text_left_placeholder(self, placeholder_id):
        return f"<b{placeholder_id}>"

    def get_rich_text_right_placeholder(self, placeholder_id):
        return f"</b{placeholder_id}>"


class _LlmOk:
    name = "llmsstub"
    lang_in = "en"
    lang_out = "zh-CN"

    def do_llm_translate(self, text, rate_limit_params=None):
        # Probe passes None and expects no NotImplementedError
        return "ok" if text is not None else None

    def translate(self, text, ignore_cache=False, rate_limit_params=None):
        return text


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
        assert translator_supports_llm(_RaisesNotImplemented()) is False

    def test_fixed_map_is_non_llm(self):
        assert translator_supports_llm(FixedMapTranslator()) is False

    def test_successful_probe_is_true(self):
        assert translator_supports_llm(_LlmOk()) is True

    def test_other_exception_is_false(self):
        # Defensive: unexpected errors must not claim LLM support
        assert translator_supports_llm(_LlmOtherError()) is False


class TestDispatchChoosesIlTranslatorClass:
    """Same branch condition as _do_translate_single (no full pipeline)."""

    def _choose(self, engine):
        if translator_supports_llm(engine):
            return ILTranslatorLLMOnly
        return ILTranslator

    def test_fixed_map_selects_il_translator(self):
        assert self._choose(FixedMapTranslator()) is ILTranslator

    def test_deeplx_stub_selects_il_translator(self):
        assert self._choose(_RaisesNotImplemented()) is ILTranslator

    def test_llm_ok_selects_llm_only(self):
        assert self._choose(_LlmOk()) is ILTranslatorLLMOnly
