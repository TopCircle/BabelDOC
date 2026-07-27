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


def test_protect_toc_title_trigasm_dash_actually():
    """Full TOC phrase after soft-hyphen fix: protect term, keep dash/space."""
    g = Glossary(
        "day6",
        [
            GlossaryEntry("trigasm", "三重高潮", "zh-CN"),
            GlossaryEntry(
                "Trigasm- actually, make hers triple, please!",
                "三重高潮——让她也来个三重的，拜托！",
                "zh-CN",
            ),
        ],
    )
    text = "4. Trigasm- actually, make hers triple, please!"
    protected, mapping = g.protect_terms_for_mt(text)
    restored = Glossary.restore_protected_terms(protected, mapping)
    assert "三重高潮" in restored
    assert "TrigasMac" not in restored
    assert "trigasmactually" not in restored.lower()
