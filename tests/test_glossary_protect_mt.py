"""Non-LLM glossary protection (DeepLX path)."""

from __future__ import annotations

from babeldoc.glossary import Glossary
from babeldoc.glossary import GlossaryEntry


def test_protect_and_restore_trigasm():
    g = Glossary(
        "day6",
        [
            GlossaryEntry("trigasm", "三重高潮", "zh-CN"),
            GlossaryEntry("TAKE CHARGE", "主动掌控型", "zh-CN"),
            GlossaryEntry("Blended G-gasm", "混合G点高潮", "zh-CN"),
        ],
    )
    text = "The ultra-rare trigasm and TAKE CHARGE style plus Blended G-gasm."
    protected, mapping = g.protect_terms_for_mt(text)
    assert "trigasm" not in protected.lower() or "⟦G" in protected
    assert "⟦G" in protected
    # Simulate MT leaving placeholders intact
    restored = Glossary.restore_protected_terms(protected, mapping)
    assert "三重高潮" in restored
    assert "主动掌控型" in restored
    assert "混合G点高潮" in restored
