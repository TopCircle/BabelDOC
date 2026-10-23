"""A cut sentence is one paragraph. A period plus a paragraph gap is not."""

from __future__ import annotations

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter
from babeldoc.format.pdf.document_il.il_version_1 import PdfLine
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraphComposition
from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
from babeldoc.format.pdf.document_il.utils.sentence_paragraph_repair import (
    merge_mid_sentence_paragraphs,
)
from babeldoc.format.pdf.document_il.utils.sentence_paragraph_repair import (
    repair_broken_sentences,
)
from babeldoc.format.pdf.document_il.utils.sentence_paragraph_repair import (
    split_sentence_paragraph_gaps,
)


def _mixed(
    parts: list[tuple[str, str, float]], *, x: float, y: float
) -> PdfParagraphComposition:
    chars = []
    cursor = x
    for text, font_id, size in parts:
        for char in text:
            chars.append(
                PdfCharacter(
                    char_unicode=char,
                    box=Box(x=cursor, y=y, x2=cursor + 6, y2=y + 12),
                    pdf_style=PdfStyle(font_id=font_id, font_size=size),
                )
            )
            cursor += 6
    return PdfParagraphComposition(
        pdf_line=PdfLine(
            box=Box(x=x, y=y, x2=max(cursor, x + 1), y2=y + 12),
            pdf_character=chars,
        )
    )


def _line(text: str, *, x: float, y: float, font_id: str = "Myriad", size: float = 12.0):
    chars = []
    cursor = x
    for char in text:
        chars.append(
            PdfCharacter(
                char_unicode=char,
                box=Box(x=cursor, y=y, x2=cursor + 6, y2=y + 12),
                pdf_style=PdfStyle(font_id=font_id, font_size=size),
            )
        )
        cursor += 6
    return PdfParagraphComposition(
        pdf_line=PdfLine(
            box=Box(x=x, y=y, x2=max(cursor, x + 1), y2=y + 12),
            pdf_character=chars,
        )
    )


def _para(*comps: PdfParagraphComposition, xobj_id: int = 0) -> PdfParagraph:
    boxes = [comp.pdf_line.box for comp in comps]
    return PdfParagraph(
        box=Box(
            x=min(box.x for box in boxes),
            y=min(box.y for box in boxes),
            x2=max(box.x2 for box in boxes),
            y2=max(box.y2 for box in boxes),
        ),
        pdf_paragraph_composition=list(comps),
        unicode="",
        xobj_id=xobj_id,
        layout_label="plain text",
    )


def _text(paragraph: PdfParagraph) -> str:
    parts = []
    for composition in paragraph.pdf_paragraph_composition or []:
        line = composition.pdf_line
        if line is None:
            continue
        parts.append("".join(char.char_unicode or "" for char in line.pdf_character or []))
    return "|".join(parts)


def test_a_paragraph_gap_after_a_period_splits():
    paragraph = _para(
        _line("Explore the line above.", x=113, y=444),
        _line("and stimulate her breasts.", x=113, y=430),
        _line("Some women enjoy having", x=113, y=404),
    )
    paragraphs = [paragraph]
    assert split_sentence_paragraph_gaps(paragraphs) == 1
    assert _text(paragraphs[0]) == "Explore the line above.|and stimulate her breasts."
    assert _text(paragraphs[1]) == "Some women enjoy having"


def test_a_line_gap_inside_a_sentence_stays():
    paragraph = _para(
        _line("Be sure to use", x=113, y=400),
        _line("your fingers and tongue", x=113, y=386),
    )
    assert split_sentence_paragraph_gaps([paragraph]) == 0
    assert len(paragraph.pdf_paragraph_composition) == 2


def test_and_zing_and_fingers_become_one_paragraph():
    head = _para(_line("lick just under her areola and,", x=113, y=410))
    zing = _para(_line("zing, the nipples harden. Be sure to use", x=113, y=396))
    fingers = _para(_line("your fingers, tongue, and lips", x=113, y=382))
    done = _para(_line("and stimulate her breasts.", x=113, y=368))
    following = _para(_line("Some women enjoy having", x=113, y=342))
    paragraphs = [head, zing, fingers, done, following]
    assert merge_mid_sentence_paragraphs(paragraphs) == 3
    assert len(paragraphs) == 2
    assert "zing" in _text(paragraphs[0])
    assert "fingers" in _text(paragraphs[0])
    assert "breasts." in _text(paragraphs[0])
    assert _text(paragraphs[1]) == "Some women enjoy having"


def test_a_period_a_hyphen_a_bullet_and_another_face_stay_split():
    finished = _para(_line("stimulate her breasts.", x=113, y=400))
    nxt = _para(_line("Some women enjoy having", x=113, y=386))
    assert merge_mid_sentence_paragraphs([finished, nxt]) == 0

    stem = _para(_line("stimula-", x=113, y=400))
    tail = _para(_line("tion feels better", x=113, y=386))
    assert merge_mid_sentence_paragraphs([stem, tail]) == 0

    body = _para(_line("Be sure to use", x=113, y=400))
    bullet = _para(_line("• her nipples", x=113, y=386))
    assert merge_mid_sentence_paragraphs([body, bullet]) == 0

    left = _para(_line("Be sure to use", x=113, y=400))
    other = _para(_line("your fingers", x=113, y=386), xobj_id=0)
    other_face = _para(
        _line("your fingers", x=113, y=386, font_id="Times-Roman"),
    )
    assert merge_mid_sentence_paragraphs([left, other_face]) == 0

    far = _para(_line("your fingers", x=200, y=386))
    assert merge_mid_sentence_paragraphs([_para(_line("Be sure to use", x=113, y=400)), far]) == 0


def test_a_run_in_line_joins_the_body_opening_left():
    """Title line sits right of the body. The body face already ends that line."""
    title = "Scent-ually massage her. "
    tail = "For a peppery head-to-toe"
    upper = _para(
        _mixed(
            [(title, "MyriadPro-Black", 9.7), (tail, "MyriadPro-Light", 11.8)],
            x=168,
            y=400,
        )
    )
    lower = _para(
        _line("turn-on, start with cinnamon", x=159, y=384, font_id="MyriadPro-Light", size=11.8),
        _line("touched and then she", x=150, y=370, font_id="MyriadPro-Light", size=11.8),
    )
    assert merge_mid_sentence_paragraphs([upper, lower]) == 1
    assert "head-to-toe" in _text(upper)
    assert "turn-on" in _text(upper)

    stepped = _para(
        _line("turn-on further left", x=140, y=384, font_id="MyriadPro-Light", size=11.8)
    )
    alone = _para(
        _mixed(
            [(title, "MyriadPro-Black", 9.7), (tail, "MyriadPro-Light", 11.8)],
            x=168,
            y=400,
        )
    )
    assert merge_mid_sentence_paragraphs([alone, stepped]) == 0


def test_repair_splits_the_stair_then_joins_the_sentence():
    """The live cut: fingers glued under Some women, zing alone above."""
    explore = _para(_line("lick just under her areola and,", x=113, y=424))
    zing = _para(_line("zing, harden. Be sure to use", x=113, y=410))
    glued = _para(
        _line("your fingers to explore", x=113, y=396),
        _line("and stimulate her breasts.", x=113, y=382),
        _line("Some women enjoy having", x=113, y=356),
    )
    paragraphs = [explore, zing, glued]
    repair_broken_sentences(paragraphs)
    assert len(paragraphs) == 2
    joined = _text(paragraphs[0])
    assert "and," in joined
    assert "zing" in joined
    assert "fingers" in joined
    assert "breasts." in joined
    assert "Some women" not in joined
    assert _text(paragraphs[1]) == "Some women enjoy having"


def test_a_split_tail_keeps_the_xobject_and_joins_below():
    """The mid-sentence piece is the tail, so it must carry the xobject."""
    glued = _para(
        _line("She stopped.", x=113, y=420),
        _line("and then she", x=113, y=396),
        xobj_id=7,
    )
    glued.vertical = True
    below = _para(_line("kept going", x=113, y=382), xobj_id=7)
    below.vertical = True
    paragraphs = [glued, below]
    repair_broken_sentences(paragraphs)
    assert len(paragraphs) == 2
    assert paragraphs[0].xobj_id == 7
    assert _text(paragraphs[0]) == "She stopped."
    assert paragraphs[1].xobj_id == 7
    assert paragraphs[1].vertical is True
    assert _text(paragraphs[1]) == "and then she|kept going"
