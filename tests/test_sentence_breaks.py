"""A rag frame breaks on the sentence, not on each English line width."""

from __future__ import annotations

from babeldoc.format.pdf.document_il.midend.sentence_breaks import close_ahead
from babeldoc.format.pdf.document_il.midend.sentence_breaks import next_line_starts
from babeldoc.format.pdf.document_il.midend.sentence_breaks import sentence_line_breaks


class _Unit:
    def __init__(self, char, *, width=14.0, can_break=True):
        self._char = char
        self.width = width
        self.can_break_line = can_break
        self.is_space = char == " "

    def try_get_unicode(self):
        return self._char


def _units(text, **kwargs):
    return [_Unit(char, **kwargs) for char in text]


def _lines(text, breaks):
    chars = list(text)
    cuts = [index + 1 for index in breaks]
    parts = []
    start = 0
    for cut in cuts:
        parts.append("".join(chars[start:cut]))
        start = cut
    parts.append("".join(chars[start:]))
    return parts


_VERSE = (
    "像青金石小牛一样在圣洁的乳房上昂首阔步。"
    "你，短跑选手，被选中的牧羊人，在各方面你都很合适。"
    "愿你的心享受漫长的岁月。"
)
_ENGLISH = (
    "To prance on the holy breast like a lapis lazuli calf.",
    "You, the sprinter, the chosen shepherd,",
    "In all ways you are fit.",
    "May your heart enjoy long days.",
)


def test_a_verse_follows_the_sentence_and_the_english_line_end():
    breaks = sentence_line_breaks(_units(_VERSE), 400.0, 1.0, _ENGLISH)
    assert _lines(_VERSE, breaks) == [
        "像青金石小牛一样在圣洁的乳房上昂首阔步。",
        "你，短跑选手，被选中的牧羊人，",
        "在各方面你都很合适。",
        "愿你的心享受漫长的岁月。",
    ]


def test_the_placer_starts_the_next_line_after_the_period():
    breaks = sentence_line_breaks(_units(_VERSE), 400.0, 1.0, _ENGLISH)
    starts = next_line_starts(breaks, len(_VERSE))
    assert starts
    for index in starts:
        assert _VERSE[index - 1] in "。，"
        assert _VERSE[index] not in "。，"


def test_without_english_lines_a_comma_clause_stays_with_its_sentence():
    breaks = sentence_line_breaks(_units(_VERSE), 400.0, 1.0, ())
    assert _lines(_VERSE, breaks) == [
        "像青金石小牛一样在圣洁的乳房上昂首阔步。",
        "你，短跑选手，被选中的牧羊人，在各方面你都很合适。",
        "愿你的心享受漫长的岁月。",
    ]


def test_a_wide_sentence_wraps_without_splitting_a_glued_word():
    text = "你，短跑选手，被选中的牧羊人，在各方面你都很合适。"
    units = _units(text)
    for unit in units:
        if unit.try_get_unicode() == "短":
            unit.can_break_line = False
    breaks = sentence_line_breaks(units, 42.0, 1.0, ())
    assert breaks
    for index in breaks:
        assert text[index : index + 2] != "短跑"
    assert "".join(_lines(text, breaks)) == text


def test_one_character_short_of_a_period_ends_on_the_period():
    text = "像青金石小牛一样在圣洁的乳房上昂首阔步。"
    units = _units(text, width=10.0)
    assert close_ahead(list(text), 18) == len(text) - 1
    assert sentence_line_breaks(units, 185.0, 1.0, ()) is None


def test_two_characters_short_of_a_comma_end_on_the_comma():
    text = "从上海洋到下海洋，从胡鲁普之地继续。"
    units = _units(text, width=10.0)
    breaks = sentence_line_breaks(units, 85.0, 1.0, ())
    assert _lines(text, breaks) == [
        "从上海洋到下海洋，",
        "从胡鲁普之地继续。",
    ]


def test_a_long_clause_breaks_at_the_comma_already_on_the_line():
    text = "哦，我的王后，愿他享受悠长的甜蜜时光。"
    # Twelve characters fit through 悠. 长 does not, and 。 is still six away.
    breaks = sentence_line_breaks(_units(text, width=10.0), 125.0, 1.0, ())
    assert _lines(text, breaks) == [
        "哦，我的王后，",
        "愿他享受悠长的甜蜜时光。",
    ]


def test_three_characters_short_of_a_period_stay_on_the_next_line():
    text = "一二三四五六七八九十。"
    breaks = sentence_line_breaks(_units(text, width=10.0), 70.0, 1.0, ())
    assert _lines(text, breaks) == [
        "一二三四五六七",
        "八九十。",
    ]


def test_prose_without_a_terminal_punctuation_uses_the_frame():
    text = "颈部和肩部通常非常紧张大多数人把压力留在这里"
    english = (
        "The neck and shoulders are typically very stress",
        "ful areas and most people hold the tension here",
    )
    assert sentence_line_breaks(_units(text, width=10.0), 400.0, 1.0, english) is None
