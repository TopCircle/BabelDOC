"""Glossary protect across style markers (book titles after rich wrap)."""

from __future__ import annotations

from babeldoc.glossary import Glossary
from babeldoc.glossary import GlossaryEntry


def test_protect_book_title_through_style_markers():
    g = Glossary(
        "day6",
        [
            GlossaryEntry(
                "The Passion Prescription",
                "《激情处方》",
                "zh-CN",
            ),
            GlossaryEntry(
                "The G Spot: And Other Discoveries About Human Sexuality",
                "《G点及其他人类性学发现》",
                "zh-CN",
            ),
        ],
    )
    text = (
        'says Laura Berman, author of 〖B0〗The Passion Prescription〖/B0〗. '
        "coauthor of 〖B1〗The G Spot: And Other Discoveries About Human "
        "Sexuality〖/B1〗."
    )
    # markers inside phrase
    text2 = "author of 〖B0〗The〖/B0〗 〖B1〗Passion Prescription〖/B1〗."
    for src in (text, text2):
        protected, mapping = g.protect_terms_for_mt(src)
        restored = Glossary.restore_protected_terms(protected, mapping)
        assert "《激情处方》" in restored
        assert "Passion Prescription" not in restored


def test_protect_author_names():
    g = Glossary(
        "day6",
        [
            GlossaryEntry("Beverly Whipple", "Beverly Whipple", "zh-CN"),
            GlossaryEntry("Laura Berman", "Laura Berman", "zh-CN"),
        ],
    )
    text = "says Beverly Whipple, coauthor. says Laura Berman, author."
    protected, mapping = g.protect_terms_for_mt(text)
    assert "⟦G" in protected
    restored = Glossary.restore_protected_terms(protected, mapping)
    assert "Beverly Whipple" in restored
    assert "Laura Berman" in restored
