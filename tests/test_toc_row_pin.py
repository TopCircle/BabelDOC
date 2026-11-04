"""Contents bang stays on the header. Overlapping rows open by one line."""

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter
from babeldoc.format.pdf.document_il.il_version_1 import PdfLine
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraphComposition
from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
from babeldoc.format.pdf.document_il.utils.toc_rows import capture_toc_leaders
from babeldoc.format.pdf.document_il.utils.toc_rows import clear_toc_source
from babeldoc.format.pdf.document_il.utils.toc_rows import fit_directory_boxes
from babeldoc.format.pdf.document_il.utils.toc_rows import join_or_drop_header_bang
from babeldoc.format.pdf.document_il.utils.toc_rows import leader_title_text
from babeldoc.format.pdf.document_il.utils.toc_rows import paint_toc_leaders
from babeldoc.format.pdf.document_il.utils.toc_rows import pin_toc_row_baselines
from babeldoc.format.pdf.document_il.utils.toc_rows import remember_toc_source


def _para(text: str, y: float, *, x: float = 56.0, label: str = "toc") -> PdfParagraph:
    paragraph = PdfParagraph(
        box=Box(x=x, y=y, x2=x + 80.0, y2=y + 12.0),
        unicode=text,
        layout_label=label,
        pdf_paragraph_composition=[],
    )
    return paragraph


def test_header_bang_joins_and_a_body_bang_is_removed():
    header = _para("TABLE OF CONTENTS", 700, label="title")
    bang = _para("!", 700, x=400, label="plain text")
    body = _para("!", 400, x=278, label="plain text")
    rows = [header, bang, body]
    join_or_drop_header_bang(rows)
    assert len(rows) == 1
    assert rows[0].unicode == "TABLE OF CONTENTS"


def test_a_bang_on_a_body_page_stays():
    body = _para("!", 400, x=278, label="plain text")
    rows = [body]
    join_or_drop_header_bang(rows)
    assert rows == [body]


def test_a_bang_glyph_on_the_header_is_removed():
    bang = PdfCharacter(
        box=Box(x=200.0, y=700.0, x2=206.0, y2=712.0),
        char_unicode="!",
    )
    word = PdfCharacter(
        box=Box(x=74.0, y=700.0, x2=180.0, y2=712.0),
        char_unicode="TABLE OF CONTENTS",
    )
    header = _para("TABLE OF CONTENTS!", 700, label="title")
    header.pdf_paragraph_composition = [
        PdfParagraphComposition(
            pdf_line=PdfLine(
                box=Box(x=74.0, y=700.0, x2=206.0, y2=712.0),
                pdf_character=[word, bang],
            )
        )
    ]
    rows = [header]
    join_or_drop_header_bang(rows)
    assert rows[0].unicode == "TABLE OF CONTENTS"
    chars = rows[0].pdf_paragraph_composition[0].pdf_line.pdf_character
    assert [char.char_unicode for char in chars] == ["TABLE OF CONTENTS"]


def test_a_row_moved_onto_the_line_above_returns():
    upper = _para("Tease Her", 300)
    lower = _para("Partial", 296)
    far = _para("Hot Tips", 240)
    remember_toc_source([upper, lower, far])
    lower.box.y2 = 320
    lower.box.y = 308
    pin_toc_row_baselines([upper, lower, far])
    assert abs(lower.box.y2 - 308) < 1
    assert abs(upper.box.y2 - 312) < 1
    assert far.box.y2 == 252


def test_a_leader_row_box_shrinks_to_the_words():
    word = PdfCharacter(
        box=Box(x=78.0, y=200.0, x2=208.0, y2=212.0),
        char_unicode="CYCLE",
    )
    rule = PdfCharacter(
        box=Box(x=220.0, y=200.0, x2=548.0, y2=212.0),
        char_unicode="______",
    )
    paragraph = _para("THE RELATIONSHIP CYCLE ______", 200, x=78.0)
    paragraph.box.x2 = 558.0
    paragraph.pdf_paragraph_composition = [
        PdfParagraphComposition(
            pdf_line=PdfLine(
                box=Box(x=78.0, y=200.0, x2=558.0, y2=212.0),
                pdf_character=[word, rule],
            )
        )
    ]
    fit_directory_boxes([paragraph])
    assert paragraph.alignment == "left"
    assert abs(paragraph.box.x - 78.0) < 1
    assert abs(paragraph.box.x2 - 208.0) < 1


def test_source_dots_are_repeated_up_to_the_page_number():
    clear_toc_source()
    style = PdfStyle(font_id="F", font_size=10.0, graphic_state=None)

    def glyph(text: str, x: float, *, cid: int = 3) -> PdfCharacter:
        return PdfCharacter(
            pdf_style=style,
            box=Box(x=x, y=100.0, x2=x + 4.0, y2=110.0),
            char_unicode=text,
            pdf_character_id=cid,
        )

    word = glyph("D", 56.0, cid=2)
    word.box.x2 = 90.0
    dots = [glyph(".", 100.0 + index * 4.0) for index in range(6)]
    title = _para("DESIRE......", 100, x=56.0)
    title.debug_id = "title"
    title.box.x2 = 160.0
    title.pdf_paragraph_composition = [
        PdfParagraphComposition(
            pdf_line=PdfLine(
                box=Box(x=56.0, y=100.0, x2=160.0, y2=110.0),
                pdf_character=[word, *dots],
            )
        )
    ]
    number = glyph("41", 180.0, cid=9)
    number.box.x2 = 196.0
    page_number = _para("41", 100, x=180.0)
    page_number.debug_id = "num"
    page_number.box.x2 = 196.0
    page_number.pdf_paragraph_composition = [
        PdfParagraphComposition(pdf_character=number)
    ]
    rows = [title, page_number]
    capture_toc_leaders(rows)
    title.pdf_paragraph_composition = [PdfParagraphComposition(pdf_character=word)]
    title.unicode = "创建性欲望"
    paint_toc_leaders(rows)
    assert len(rows) == 3
    painted = [
        comp.pdf_character
        for comp in rows[2].pdf_paragraph_composition
        if comp.pdf_character is not None
    ]
    assert painted
    assert {char.char_unicode for char in painted} == {"."}
    assert painted[0].box.x > 90.0
    assert painted[-1].box.x2 < 180.0


def test_an_ellipsis_row_uses_the_same_period():
    clear_toc_source()
    style = PdfStyle(font_id="F", font_size=10.0, graphic_state=None)

    def glyph(text: str, x: float, *, width: float, cid: int) -> PdfCharacter:
        return PdfCharacter(
            pdf_style=style,
            box=Box(x=x, y=100.0, x2=x + width, y2=110.0),
            char_unicode=text,
            pdf_character_id=cid,
        )

    period = _para("DESIRE...", 100, x=56.0)
    period.debug_id = "period"
    period.box.x2 = 160.0
    period.pdf_paragraph_composition = [
        PdfParagraphComposition(pdf_character=glyph(".", 100.0, width=4.0, cid=3)),
        PdfParagraphComposition(pdf_character=glyph(".", 104.0, width=4.0, cid=3)),
    ]
    ellipsis = _para("ORGASM…", 80, x=56.0)
    ellipsis.debug_id = "ellipsis"
    ellipsis.box.x2 = 160.0
    ellipsis.pdf_paragraph_composition = [
        PdfParagraphComposition(pdf_character=glyph("…", 100.0, width=12.0, cid=8)),
        PdfParagraphComposition(pdf_character=glyph("…", 112.0, width=12.0, cid=8)),
    ]
    number = _para("50", 80, x=180.0)
    number.debug_id = "fifty"
    number.pdf_paragraph_composition = [
        PdfParagraphComposition(pdf_character=glyph("50", 180.0, width=16.0, cid=9)),
    ]
    rows = [period, ellipsis, number]
    capture_toc_leaders(rows)
    ellipsis.pdf_paragraph_composition = [
        PdfParagraphComposition(pdf_character=glyph("高", 56.0, width=20.0, cid=1)),
    ]
    ellipsis.unicode = "高潮"
    paint_toc_leaders(rows)
    painted = [
        comp.pdf_character
        for row in rows
        if (row.debug_id or "").endswith("ellipsis-leader")
        for comp in row.pdf_paragraph_composition
        if comp.pdf_character is not None
    ]
    assert painted
    assert {char.char_unicode for char in painted} == {"."}
    assert abs((painted[1].box.x - painted[0].box.x) - 4.0) < 0.2


def test_periods_step_by_the_english_gap_not_the_ink():
    clear_toc_source()
    style = PdfStyle(font_id="F", font_size=10.0, graphic_state=None)
    dots = []
    for index in range(3):
        x = 100.0 + index * 5.44
        dots.append(
            PdfCharacter(
                pdf_style=style,
                box=Box(x=x, y=100.0, x2=x + 2.9, y2=110.0),
                char_unicode=".",
                pdf_character_id=3,
            )
        )
    title = _para("DESIRE...", 100, x=56.0)
    title.debug_id = "desire"
    word = PdfCharacter(
        pdf_style=style,
        box=Box(x=56.0, y=100.0, x2=90.0, y2=110.0),
        char_unicode="D",
        pdf_character_id=2,
    )
    title.pdf_paragraph_composition = [
        PdfParagraphComposition(
            pdf_line=PdfLine(
                box=Box(x=56.0, y=100.0, x2=120.0, y2=110.0),
                pdf_character=[word, *dots],
            )
        )
    ]
    number = _para("41", 100, x=180.0)
    number.debug_id = "num"
    number.pdf_paragraph_composition = [
        PdfParagraphComposition(
            pdf_character=PdfCharacter(
                pdf_style=style,
                box=Box(x=180.0, y=100.0, x2=196.0, y2=110.0),
                char_unicode="41",
                pdf_character_id=9,
            )
        )
    ]
    rows = [title, number]
    capture_toc_leaders(rows)
    title.pdf_paragraph_composition = [PdfParagraphComposition(pdf_character=word)]
    title.unicode = "创建性欲望"
    paint_toc_leaders(rows)
    painted = [
        comp.pdf_character
        for row in rows
        if (row.debug_id or "").endswith("-leader")
        for comp in row.pdf_paragraph_composition
        if comp.pdf_character is not None
    ]
    assert len(painted) >= 2
    assert abs((painted[1].box.x - painted[0].box.x) - 5.44) < 0.05


def test_a_split_rule_still_fills_the_title_gap():
    clear_toc_source()
    style = PdfStyle(font_id="F", font_size=10.0, graphic_state=None)

    def glyph(text: str, x: float, *, width: float = 6.0) -> PdfCharacter:
        return PdfCharacter(
            pdf_style=style,
            box=Box(x=x, y=300.0, x2=x + width, y2=312.0),
            char_unicode=text,
            pdf_character_id=4,
        )

    title = _para("REASONS", 300, x=78.0)
    title.debug_id = "reasons"
    title.box.x2 = 200.0
    word = glyph("R", 78.0, width=40.0)
    title.pdf_paragraph_composition = [
        PdfParagraphComposition(pdf_character=word),
    ]
    rule = _para("______", 300, x=210.0, label="plain text")
    rule.debug_id = "rule"
    rule.box.x2 = 540.0
    rule.pdf_paragraph_composition = [
        PdfParagraphComposition(pdf_character=glyph("_", 210.0 + index * 6.0))
        for index in range(4)
    ]
    number = _para("17", 300, x=548.0)
    number.debug_id = "seventeen"
    digit = glyph("17", 548.0, width=10.0)
    number.pdf_paragraph_composition = [
        PdfParagraphComposition(pdf_character=digit),
    ]
    rows = [title, rule, number]
    capture_toc_leaders(rows)
    paint_toc_leaders(rows)
    painted = [
        comp.pdf_character
        for row in rows
        if (row.debug_id or "").endswith("-leader")
        for comp in row.pdf_paragraph_composition
        if comp.pdf_character is not None
    ]
    assert painted
    assert painted[0].box.x > 118.0
    assert painted[-1].box.x2 < 548.0


def test_a_row_without_a_leader_stays_empty():
    clear_toc_source()
    title = _para("Tease Her", 300)
    title.debug_id = "tease"
    number = _para("49", 300, x=470.0)
    number.debug_id = "forty-nine"
    rows = [title, number]
    capture_toc_leaders(rows)
    paint_toc_leaders(rows)
    assert rows == [title, number]


def test_a_shifted_title_returns_to_its_source_line():
    word = _para("ORGASM", 400)
    number = _para("50", 400, x=470)
    remember_toc_source([word, number])
    word.box.y2 = 384
    word.box.y = 372
    pin_toc_row_baselines([word, number])
    assert abs(word.box.y2 - 412) < 1
    assert abs(number.box.y2 - 412) < 1


def test_moved_glyphs_return_while_the_paragraph_box_stayed():
    char = PdfCharacter(
        box=Box(x=56.0, y=400.0, x2=80.0, y2=412.0),
        char_unicode="高",
    )
    line = PdfLine(
        box=Box(x=56.0, y=400.0, x2=80.0, y2=412.0),
        pdf_character=[char],
    )
    paragraph = _para("高潮", 400)
    paragraph.pdf_paragraph_composition = [
        PdfParagraphComposition(pdf_line=line),
    ]
    remember_toc_source([paragraph])
    assert paragraph.box.y2 == 412
    char.box.y = 372.0
    char.box.y2 = 384.0
    pin_toc_row_baselines([paragraph])
    assert abs(char.box.y2 - 412) < 1


def test_leader_title_drops_the_rule_and_the_page_number():
    assert leader_title_text("THE RELATIONSHIP CYCLE ______ 6") == (
        "THE RELATIONSHIP CYCLE"
    )
    assert (
        leader_title_text(
            "SEXUAL DESIRE: THE DIFFERENCE BETWEEN MEN AND WOMEN ______"
        )
        == "SEXUAL DESIRE: THE DIFFERENCE BETWEEN MEN AND WOMEN"
    )
    assert leader_title_text("in 2014") is None
