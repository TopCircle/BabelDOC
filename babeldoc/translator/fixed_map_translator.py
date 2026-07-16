"""Deterministic map-based translator for dual-quality harnesses.

Duck-typed for BabelDOC midend and PDFMathTranslate-next CLI engines
(not a subclass of ``BaseTranslator`` — avoids peewee cache coupling).

Implements the surface ``ILTranslator`` actually calls:
``translate``, placeholder helpers, and ``do_llm_translate`` →
``NotImplementedError`` so ``translator_supports_llm`` selects the
non-LLM path.
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

    def add_cache_impact_parameters(self, k: str, v) -> None:  # noqa: ARG002
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
        """Force non-LLM pipeline branch (``translator_supports_llm`` probe)."""
        raise NotImplementedError(
            "FixedMapTranslator is non-LLM; use ILTranslator path"
        )

    # Same defaults as BaseTranslator — required by ILTranslator midend.
    def get_rich_text_left_placeholder(self, placeholder_id: int | str) -> str:
        return f"<b{placeholder_id}>"

    def get_rich_text_right_placeholder(self, placeholder_id: int | str) -> str:
        return f"</b{placeholder_id}>"

    def get_formular_placeholder(self, placeholder_id: int | str) -> str:
        return self.get_rich_text_left_placeholder(placeholder_id)
