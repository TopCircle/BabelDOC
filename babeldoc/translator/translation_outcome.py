"""Translation content and delivery metadata cross the provider boundary together."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from typing import runtime_checkable


@dataclass(frozen=True, slots=True)
class TranslationOutcome:
    text: str
    warnings: tuple[str, ...] = ()

    @property
    def cacheable(self) -> bool:
        return not self.warnings


@runtime_checkable
class ProviderOutcome(Protocol):
    """Public structural contract, independent of a provider's class identity."""

    @property
    def text(self) -> str: ...

    @property
    def warnings(self) -> tuple[str, ...]: ...


def as_translation_outcome(value: str | ProviderOutcome) -> TranslationOutcome:
    if isinstance(value, str):
        return TranslationOutcome(value)
    if isinstance(value, ProviderOutcome):
        return TranslationOutcome(value.text, tuple(value.warnings))
    raise TypeError("translation must be text or a provider outcome")


class Translator(Protocol):
    def translate(self, text: str, **kwargs) -> str | ProviderOutcome: ...
    def llm_translate(self, text: str, **kwargs) -> str | ProviderOutcome: ...


def translate_outcome(
    engine: Translator, text: str, *, llm: bool = False, **kwargs
) -> TranslationOutcome:
    """Adapt legacy text providers; metadata-aware providers expose an explicit API.

    Only this compatibility boundary probes for the optional provider capability.
    Text cleanup never needs to know how a provider represented its metadata.
    """
    method = "llm_translate" if llm else "translate"
    operation = getattr(engine, method + "_with_metadata", None)
    if operation is None:
        operation = engine.llm_translate if llm else engine.translate
    return as_translation_outcome(operation(text, **kwargs))
