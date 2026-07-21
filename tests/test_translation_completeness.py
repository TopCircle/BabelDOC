"""Sentence-completeness checks for EN→CJK body (All Tied Up intro drop)."""

from __future__ import annotations

from babeldoc.format.pdf.document_il.midend.il_translator import ILTranslator


class TestCountSentenceEnds:
    def test_en_three_questions(self):
        en = (
            "How long have you been wondering about bondage? "
            "Is it something that you have fantasized about for ages? "
            "Or a new thought brought on by the 50 Shades of Grey phenomenon?"
        )
        assert ILTranslator.count_sentence_ends(en) == 3

    def test_zh_incomplete_two(self):
        zh = "您想知道捆绑有多久了？这是您幻想已久的事情？"
        assert ILTranslator.count_sentence_ends(zh) == 2

    def test_zh_complete_three(self):
        zh = (
            "你对束缚感到好奇多久了？这是你多年来一直幻想的事情吗？"
            "还是五十度灰现象带来的新想法？"
        )
        assert ILTranslator.count_sentence_ends(zh) == 3

    def test_decimal_not_sentence(self):
        assert ILTranslator.count_sentence_ends("Use version 3.14 carefully.") == 1


class TestTranslationDropsSentences:
    def test_atu_intro_incomplete(self):
        en = (
            "How long have you been wondering about bondage? "
            "Is it something that you have fantasized about for ages? "
            "Or a new thought brought on by the 50 Shades of Grey phenomenon?"
        )
        zh_bad = "您想知道捆绑有多久了？这是您幻想已久的事情？"
        assert ILTranslator.translation_drops_sentences(en, zh_bad)

    def test_complete_ok(self):
        en = (
            "How long have you been wondering about bondage? "
            "Is it something that you have fantasized about for ages? "
            "Or a new thought brought on by the 50 Shades of Grey phenomenon?"
        )
        zh_ok = (
            "你对束缚感到好奇多久了？这是你多年来一直幻想的事情吗？"
            "还是五十度灰现象带来的新想法？"
        )
        assert not ILTranslator.translation_drops_sentences(en, zh_ok)

    def test_single_sentence_not_flagged(self):
        assert not ILTranslator.translation_drops_sentences(
            "Hello world.", "你好世界。"
        )
