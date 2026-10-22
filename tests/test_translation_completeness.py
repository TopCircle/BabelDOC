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


class TestSentenceSplit:
    def test_quote_between_period_and_the_next_sentence(self):
        text = (
            'called the "vulva." The vulva is the external part. '
            "In fact, many people know."
        )
        parts = ILTranslator.split_sentences(text)
        assert parts == [
            'called the "vulva."',
            "The vulva is the external part.",
            "In fact, many people know.",
        ]

    def test_decimal_stays_one_sentence(self):
        assert ILTranslator.split_sentences("Use version 3.14 carefully.") == [
            "Use version 3.14 carefully."
        ]

    def test_a_digit_after_the_stop_is_the_next_sentence(self):
        assert ILTranslator.split_sentences("End. 3 days later she left.") == [
            "End.",
            "3 days later she left.",
        ]
        assert ILTranslator.split_sentences("结束。3天后她离开了。") == [
            "结束。",
            "3天后她离开了。",
        ]

    def test_a_numbered_item_stays_one_sentence(self):
        assert ILTranslator.split_sentences("1. Place the oil here.") == [
            "1. Place the oil here."
        ]


class TestSentenceRebuild:
    def test_each_sentence_is_translated_and_joined(self):
        class Engine:
            def translate(self, text, ignore_cache=False, rate_limit_params=None):
                return {
                    "Well, vagina is the vulva.": "阴道这个词常被用来指外阴。",
                    "In fact, many people would not know.": "事实上，很多人不知道。",
                }[text]

        helper = ILTranslator.__new__(ILTranslator)
        helper.translate_engine = Engine()
        source = "Well, vagina is the vulva. In fact, many people would not know."
        assert helper._translate_each_sentence(source) == (
            "阴道这个词常被用来指外阴。事实上，很多人不知道。"
        )
