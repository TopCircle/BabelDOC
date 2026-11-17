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


class TestGetTranslateInputWithUnicodeCharacters:
    def _create_translator(self):
        from unittest.mock import MagicMock

        import regex
        translator = ILTranslator.__new__(ILTranslator)
        translator.translation_config = MagicMock()
        translator.translation_config.disable_rich_text_translate = True
        translator.support_llm_translate = False
        translator.TranslateInput = ILTranslator.TranslateInput
        translator._formula_placeholder_pattern = regex.compile(r"\{\s*v\s*\d+\s*\}")
        translator._style_left_placeholder_pattern = regex.compile(r"<\s*style\s*id\s*=\s*'\s*\d+\s*'\s*>")
        translator._style_right_placeholder_pattern = regex.compile(r"</\s*style\s*>")
        return translator

    def test_single_real_unicode_characters_composition(self):
        from babeldoc.format.pdf.document_il import PdfParagraph
        from babeldoc.format.pdf.document_il import PdfParagraphComposition
        from babeldoc.format.pdf.document_il import PdfSameStyleUnicodeCharacters
        from babeldoc.format.pdf.document_il import PdfStyle

        translator = self._create_translator()
        style = PdfStyle(font_id="base", font_size=12.0)
        para = PdfParagraph(
            unicode="Technique 1: Cooling down",
            pdf_style=style,
            pdf_paragraph_composition=[
                PdfParagraphComposition(
                    pdf_same_style_unicode_characters=PdfSameStyleUnicodeCharacters(
                        unicode="Technique 1: Cooling down",
                        pdf_style=style,
                        debug_info=False,
                    )
                )
            ],
        )
        res = translator.get_translate_input(para, {}, disable_rich_text_translate=True)
        assert res is not None
        assert res.unicode == "Technique 1: Cooling down"

    def test_multi_composition_with_debug_stub_ignored(self):
        from babeldoc.format.pdf.document_il import Box
        from babeldoc.format.pdf.document_il import PdfCharacter
        from babeldoc.format.pdf.document_il import PdfParagraph
        from babeldoc.format.pdf.document_il import PdfParagraphComposition
        from babeldoc.format.pdf.document_il import PdfSameStyleCharacters
        from babeldoc.format.pdf.document_il import PdfSameStyleUnicodeCharacters
        from babeldoc.format.pdf.document_il import PdfStyle

        translator = self._create_translator()
        style = PdfStyle(font_id="base", font_size=12.0)
        c1 = PdfCharacter(char_unicode="H", box=Box(x=0, y=0, x2=10, y2=12))
        c2 = PdfCharacter(char_unicode="i", box=Box(x=10, y=0, x2=15, y2=12))
        para = PdfParagraph(
            unicode="Hi",
            pdf_style=style,
            pdf_paragraph_composition=[
                PdfParagraphComposition(
                    pdf_same_style_characters=PdfSameStyleCharacters(
                        pdf_style=style,
                        pdf_character=[c1, c2],
                    )
                ),
                PdfParagraphComposition(
                    pdf_same_style_unicode_characters=PdfSameStyleUnicodeCharacters(
                        unicode="fallback_line",
                        pdf_style=style,
                        debug_info=True,
                    )
                ),
            ],
        )
        res = translator.get_translate_input(para, {"base": style}, disable_rich_text_translate=True)
        assert res is not None
        assert res.unicode == "Hi"

    def test_multi_composition_with_real_list_marker(self):
        from babeldoc.format.pdf.document_il import Box
        from babeldoc.format.pdf.document_il import PdfCharacter
        from babeldoc.format.pdf.document_il import PdfParagraph
        from babeldoc.format.pdf.document_il import PdfParagraphComposition
        from babeldoc.format.pdf.document_il import PdfSameStyleCharacters
        from babeldoc.format.pdf.document_il import PdfSameStyleUnicodeCharacters
        from babeldoc.format.pdf.document_il import PdfStyle

        translator = self._create_translator()
        style = PdfStyle(font_id="base", font_size=12.0)
        c1 = PdfCharacter(char_unicode="T", box=Box(x=20, y=0, x2=30, y2=12))
        c2 = PdfCharacter(char_unicode="e", box=Box(x=30, y=0, x2=40, y2=12))
        c3 = PdfCharacter(char_unicode="x", box=Box(x=40, y=0, x2=50, y2=12))
        c4 = PdfCharacter(char_unicode="t", box=Box(x=50, y=0, x2=60, y2=12))
        para = PdfParagraph(
            unicode="1. Text",
            pdf_style=style,
            pdf_paragraph_composition=[
                PdfParagraphComposition(
                    pdf_same_style_unicode_characters=PdfSameStyleUnicodeCharacters(
                        unicode="1. ",
                        pdf_style=style,
                        debug_info=False,
                    )
                ),
                PdfParagraphComposition(
                    pdf_same_style_characters=PdfSameStyleCharacters(
                        pdf_style=style,
                        pdf_character=[c1, c2, c3, c4],
                    )
                ),
            ],
        )
        res = translator.get_translate_input(para, {"base": style}, disable_rich_text_translate=True)
        assert res is not None
        assert "1. Text" in res.unicode

