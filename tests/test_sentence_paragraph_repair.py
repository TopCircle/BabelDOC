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


def _line(
    text: str,
    *,
    x: float,
    y: float,
    x2: float | None = None,
    font_id: str = "Myriad",
    size: float = 12.0,
):
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
            box=Box(
                x=x,
                y=y,
                x2=x2 if x2 is not None else max(cursor, x + 1),
                y2=y + 12,
            ),
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


def test_wrap_continuation_around_side_figure_joins():
    """A sentence stepping right to wrap around a figure joins when right edges align."""
    upper = _para(
        _line("Next, move your body up as much as possible while still keeping your penis inside", x=84, y=338),
        _line("of her. You want the weight of your body propped up by your hands and your pubic", x=66, y=323),
    )
    # Right edge is pinned to x=550
    upper.box.x2 = 550.0
    for comp in upper.pdf_paragraph_composition:
        comp.pdf_line.box.x2 = 550.0

    lower = _para(
        _line("mound grinding into hers. With each thrust, focus on rubbing the fleshy part", x=312, y=308),
        _line("of your body just above where the penis meets the flesh along her slit.", x=312, y=293),
    )
    lower.box.x2 = 550.0
    for comp in lower.pdf_paragraph_composition:
        comp.pdf_line.box.x2 = 550.0

    paragraphs = [upper, lower]
    repair_broken_sentences(paragraphs)
    assert len(paragraphs) == 1
    joined = _text(paragraphs[0])
    assert "and your pubic|mound grinding into hers" in joined


def test_same_line_horizontal_split_joins():
    """Two paragraph boxes meeting mid-line join and splice that line into one."""
    upper = _para(
        _line("There are several ways to rebuild intimacy in your relationship.", x=113, y=544),
        _line("Because women are usually the ones who don't", x=113, y=530),
    )
    # Line 2 ends at x2=208
    upper.pdf_paragraph_composition[1].pdf_line.box.x2 = 208.0

    lower = _para(
        _line("enjoy having sex when there is lack of intimacy", x=211, y=530),
        _line("in their relationship, this exercise provides women with what they need.", x=113, y=516),
    )
    lower.pdf_paragraph_composition[0].pdf_line.box.x2 = 328.0

    paragraphs = [upper, lower]
    repair_broken_sentences(paragraphs)
    assert len(paragraphs) == 1
    joined = _text(paragraphs[0])
    assert "the ones who don't" in joined
    assert "enjoy having sex when" in joined
    # The two segments on y=530 are spliced into one line
    assert paragraphs[0].pdf_paragraph_composition[1].pdf_line.box.x2 == 328.0


def test_multi_line_run_in_paragraph_merge():
    """A multi-line run-in title paragraph merges with the body paragraph below."""

    def _line_mixed(lead_txt, body_txt, x=161.0, y=108.0):
        chars = [
            PdfCharacter(
                char_unicode=c,
                box=Box(x=x + i * 6, y=y, x2=x + (i + 1) * 6, y2=y + 12),
                pdf_style=PdfStyle(font_id="LeadFont", font_size=12.0),
            )
            for i, c in enumerate(lead_txt)
        ]
        offset = len(lead_txt) * 6
        chars += [
            PdfCharacter(
                char_unicode=c,
                box=Box(
                    x=x + offset + i * 6,
                    y=y,
                    x2=x + offset + (i + 1) * 6,
                    y2=y + 12,
                ),
                pdf_style=PdfStyle(font_id="BodyFont", font_size=12.0),
            )
            for i, c in enumerate(body_txt)
        ]
        total_len = len(lead_txt) + len(body_txt)
        return PdfParagraphComposition(
            pdf_line=PdfLine(
                box=Box(x=x, y=y, x2=x + total_len * 6, y2=y + 12),
                pdf_character=chars,
            )
        )

    # Line 0 in upper paragraph: all in LeadFont
    l0 = _line(
        "3. SIT DOWN WITH YOUR LADY ONCE A DAY AND DISCUSS WHAT'S",
        x=140.0,
        y=124.0,
        font_id="LeadFont",
    )
    upper = _para(l0)

    # Lower paragraph: starts with LeadFont "GOING ON WITH HER. ", transitions to BodyFont
    l1 = _line_mixed(
        "GOING ON WITH HER. ",
        "This means talking to her about what she has been feeling...",
        x=161.0,
        y=108.0,
    )
    lower = _para(l1)

    paragraphs = [upper, lower]
    repair_broken_sentences(paragraphs)
    assert len(paragraphs) == 1
    joined = _text(paragraphs[0])
    assert "3. SIT DOWN WITH YOUR LADY ONCE A DAY AND DISCUSS WHAT'S" in joined
    assert "GOING ON WITH HER. This means talking" in joined


def test_all_caps_heading_does_not_merge_into_body():
    upper = _para(_line("CLIMAX CUE", x=402.0, y=240.0, font_id="FuturaMed", size=13.0))
    lower = _para(
        _line(
            "This is another one of those positions that I find unusual.",
            x=402.0,
            y=226.0,
            font_id="FuturaLight",
            size=13.0,
        )
    )
    paragraphs = [upper, lower]
    repair_broken_sentences(paragraphs)
    assert len(paragraphs) == 2
    assert _text(paragraphs[0]) == "CLIMAX CUE"
    assert "This is another one" in _text(paragraphs[1])


def test_multi_word_line_ending_with_hyphen_merges():
    upper = _para(
        _line(
            "Do you feel inadequate because you're not a five-",
            x=314.0,
            y=440.0,
            x2=576.0,
        )
    )
    lower = _para(
        _line(
            "in-a-row guy? Remember that multiple orgasms",
            x=325.0,
            y=422.0,
            x2=578.0,
        )
    )
    paragraphs = [upper, lower]
    repair_broken_sentences(paragraphs)
    assert len(paragraphs) == 1
    joined = _text(paragraphs[0])
    assert "not a five-|in-a-row guy?" in joined


def test_sentence_gap_cut_with_moderate_body_leading():
    lines = [
        _line("says Paul Joannides, author of", x=353.0, y=183.0),
        _line("Getting It On! A Book About The Wonders", x=350.0, y=165.0),
        _line("of Sex.", x=348.0, y=147.0),
        _line("In conclusion, don't put too much pressure", x=360.0, y=120.0),
        _line("on yourself. Sure, many of us perceive sex", x=365.0, y=102.0),
    ]
    paragraph = _para(*lines)
    paragraphs = [paragraph]
    assert split_sentence_paragraph_gaps(paragraphs) == 1
    assert len(paragraphs) == 2
    assert _text(paragraphs[0]).endswith("of Sex.")
    assert _text(paragraphs[1]).startswith("In conclusion,")


def test_multiline_heading_merges_with_large_font_gap():
    # Heading in 21pt with ~11pt gap between line bounding boxes
    upper = _para(
        _line(
            "Fingering Techniques 2: Deep Spot Doggie Boogie: Doggie",
            x=36.0,
            y=400.0,
            x2=580.0,
            size=21.0,
        )
    )
    lower = _para(
        _line(
            "Style with Deep Spot Fingering",
            x=36.0,
            y=376.0,  # line box y2 = 376 + 12 = 388, upper y = 400 => gap = 12pt
            x2=340.0,
            size=21.0,
        )
    )
    paragraphs = [upper, lower]
    repair_broken_sentences(paragraphs)
    assert len(paragraphs) == 1
    assert "Doggie|Style with Deep Spot Fingering" in _text(paragraphs[0])


def test_bullet_hanging_indent_continuation_merges():
    # Bullet at x=51.0, continuation at x=66.0 (delta = 15pt), broken mid-sentence with "and"
    upper = _para(
        _line(
            "\x12 Continue to apply more pressure as she becomes more and",
            x=51.0,
            y=400.0,
            x2=390.0,
        )
    )
    lower = _para(
        _line(
            "more aroused. Get her feedback for what feels the best.",
            x=66.0,
            y=384.0,
            x2=375.0,
        )
    )
    paragraphs = [upper, lower]
    repair_broken_sentences(paragraphs)
    assert len(paragraphs) == 1
    assert "becomes more and|more aroused." in _text(paragraphs[0])


def test_alphabetical_list_marker_hanging_indent_merges():
    """Page 15: marker 'b)' / 'c)' at x=128pt and indented body at x=146pt must merge."""
    # List item b)
    upper_b = _para(
        _line(
            "b)\t Remembering your deep breathing techniques, start to take",
            x=128.0,
            y=600.0,
            x2=522.0,
        )
    )
    lower_b = _para(
        _line(
            "things to the next level, but still steering clear of what’s below",
            x=146.0,
            y=584.0,
            x2=556.0,
        )
    )
    paras_b = [upper_b, lower_b]
    repair_broken_sentences(paras_b)
    assert len(paras_b) == 1
    assert "start to take|things to the next level" in _text(paras_b[0])

    # List item c)
    upper_c = _para(
        _line(
            "c)\t When you finally get below the belt, spend some time pleasuring",
            x=128.0,
            y=500.0,
            x2=552.0,
        )
    )
    lower_c = _para(
        _line(
            "her before even allowing her to touch you back. If she questions",
            x=146.0,
            y=484.0,
            x2=556.0,
        )
    )
    paras_c = [upper_c, lower_c]
    repair_broken_sentences(paras_c)
    assert len(paras_c) == 1
    assert "pleasuring|her before even allowing" in _text(paras_c[0])


def test_consecutive_alphabetical_list_items_stay_split():
    """Consecutive list items 'b)' and 'c)' must remain separate paragraphs."""
    item_b = _para(
        _line(
            "b)\t Remembering your deep breathing techniques, as you do.",
            x=128.0,
            y=600.0,
            x2=522.0,
        )
    )
    item_c = _para(
        _line(
            "c)\t When you finally get below the belt, spend some time pleasuring",
            x=128.0,
            y=560.0,
            x2=552.0,
        )
    )
    paras = [item_b, item_c]
    repair_broken_sentences(paras)
    assert len(paras) == 2







