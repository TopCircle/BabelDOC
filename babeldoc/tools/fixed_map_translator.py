"""Deterministic map-based translator for dual-quality harnesses.

Duck-typed for PDFMathTranslate-next style engines (not necessarily a
subclass of ``babeldoc.translator.BaseTranslator``). Raises
``NotImplementedError`` from ``do_llm_translate`` so production dispatch
selects the non-LLM ``ILTranslator`` path.
"""

from __future__ import annotations


class FixedMapTranslator:
    """Translate by exact dict lookup; unmapped strings pass through.

    ``name`` must stay ≤ 20 chars (translation cache CharField limit).
    """

    name = "fixedmap"

    def __init__(
        self,
        mapping: dict[str, str] | None = None,
        lang_in: str = "en",
        lang_out: str = "zh-CN",
        *,
        ignore_cache: bool = True,
    ):
        self.lang_in = lang_in
        self.lang_out = lang_out
        self.ignore_cache = ignore_cache
        self._map = dict(mapping or {})

    def add_cache_impact_parameters(self, k: str, v) -> None:
        # No-op: harness ignores cache
        return None

    def translate(
        self,
        text: str,
        ignore_cache: bool = False,  # noqa: ARG002
        rate_limit_params: dict | None = None,  # noqa: ARG002
    ) -> str:
        if text is None:
            return ""
        return self._map.get(text, text)

    def do_translate(
        self,
        text: str,
        rate_limit_params: dict | None = None,  # noqa: ARG002
    ) -> str:
        return self.translate(text)

    def do_llm_translate(
        self,
        text,  # noqa: ARG002
        rate_limit_params: dict | None = None,  # noqa: ARG002
    ):
        """Force non-LLM pipeline branch (same probe as ``translator_supports_llm``)."""
        raise NotImplementedError(
            "FixedMapTranslator is non-LLM; use ILTranslator path"
        )
