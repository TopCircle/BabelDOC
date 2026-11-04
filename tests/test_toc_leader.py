"""A contents leader inside a formula is not part of the title."""

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter
from babeldoc.format.pdf.document_il.il_version_1 import PdfFormula
from babeldoc.format.pdf.document_il.il_version_1 import PdfLine
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraphComposition
from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
from babeldoc.format.pdf.document_il.il_version_1 import VisualBbox
from babeldoc.format.pdf.document_il.utils.toc_rows import detach_leader_page_numbers
from babeldoc.format.pdf.document_il.utils.toc_rows import leader_title_text


def _ids():
    count = 0

    def _next() -> str:
        nonlocal count
        count += 1
        return f"n{count}"

    return _next


def _char(text: str, x: float, *, y: float = 100.0, width: float = 6.0) -> PdfCharacter:
    box = Box(x=x, y=y, x2=x + width, y2=y + 10.0)
    return PdfCharacter(
        char_unicode=text,
        box=box,
        visual_bbox=VisualBbox(box=Box(x=x, y=y, x2=x + width, y2=y + 10.0)),
        pdf_style=PdfStyle(font_id="F", font_size=10.0, graphic_state=None),
    )


def _line(text: str, x: float, *, y: float = 100.0) -> tuple[PdfParagraphComposition, list]:
    chars = []
    cursor = x
    for glyph in text:
        chars.append(_char(glyph, cursor, y=y))
        cursor += 6.0
    composition = PdfParagraphComposition(
        pdf_line=PdfLine(
            box=Box(x=x, y=y, x2=cursor, y2=y + 12.0),
            pdf_character=chars,
        )
    )
    return composition, chars


def _formula(chars) -> PdfParagraphComposition:
    xs = [char.box.x for char in chars]
    x2s = [char.box.x2 for char in chars]
    return PdfParagraphComposition(
        pdf_formula=PdfFormula(
            box=Box(x=min(xs), y=100.0, x2=max(x2s), y2=110.0),
            pdf_character=chars,
            x_offset=0.0,
            y_offset=0.0,
        )
    )


def _texts(paragraph) -> str:
    parts = [paragraph.unicode or ""]
    for comp in paragraph.pdf_paragraph_composition or []:
        line = comp.pdf_line
        formula = comp.pdf_formula
        chars = []
        if line is not None and line.pdf_character:
            chars.extend(line.pdf_character)
        if formula is not None and formula.pdf_character:
            chars.extend(formula.pdf_character)
        parts.append("".join(char.char_unicode or "" for char in chars))
    return "".join(parts)


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


def test_a_leader_formula_gives_up_its_page_number():
    line, title_chars = _line("THE RELATIONSHIP CYCLE", 78.0)
    title_x2 = title_chars[-1].box.x2
    underscores = []
    cursor = title_x2 + 6.0
    for _ in range(8):
        underscores.append(_char("_", cursor))
        cursor += 6.0
    digit = _char("6", cursor + 24.0)
    style = PdfStyle(font_id="F", font_size=10.0, graphic_state=None)
    host = PdfParagraph(
        box=Box(x=78.0, y=100.0, x2=digit.box.x2, y2=112.0),
        pdf_style=style,
        pdf_paragraph_composition=[
            line,
            _formula([*underscores, digit]),
        ],
        unicode="THE RELATIONSHIP CYCLE ______ 6",
        layout_label="title",
        layout_id=3,
        xobj_id=2,
        debug_id="host",
    )
    later = PdfParagraph(
        box=Box(x=78.0, y=80.0, x2=120.0, y2=92.0),
        unicode="Later",
        pdf_paragraph_composition=[],
    )
    rows = [host, later]
    detach_leader_page_numbers(rows, new_debug_id_factory=_ids())
    assert [row.debug_id for row in rows] == ["host", "n1", None]
    assert rows[2] is later
    sibling = rows[1]
    assert "_" not in _texts(host)
    assert "6" not in _texts(host)
    assert host.unicode == "THE RELATIONSHIP CYCLE"
    assert sibling.unicode == "6"
    assert sibling.box.x == digit.box.x
    assert sibling.layout_label == "toc"
    assert sibling.pdf_style is style
    assert sibling.layout_id == 3
    assert sibling.xobj_id == 2
    assert host.box.x == 78.0
    assert host.box.x2 == title_x2
    assert host.box.x2 < digit.box.x
    assert all(comp.pdf_formula is None for comp in host.pdf_paragraph_composition)


def test_a_digit_formula_stays_one_paragraph():
    digit = _char("6", 400.0)
    formula = _formula([digit]).pdf_formula
    host = PdfParagraph(
        box=Box(x=400.0, y=100.0, x2=digit.box.x2, y2=112.0),
        unicode="6",
        pdf_paragraph_composition=[PdfParagraphComposition(pdf_formula=formula)],
    )
    rows = [host]
    detach_leader_page_numbers(rows, new_debug_id_factory=_ids())
    assert rows == [host]
    assert formula.pdf_character[0].char_unicode == "6"
    assert host.unicode == "6"
    assert host.box.x2 == digit.box.x2


def test_a_year_with_no_leader_stays_on_the_line():
    line, chars = _line("in 2014", 56.0)
    host = PdfParagraph(
        box=Box(x=56.0, y=100.0, x2=200.0, y2=112.0),
        unicode="in 2014",
        pdf_paragraph_composition=[line],
    )
    rows = [host]
    detach_leader_page_numbers(rows, new_debug_id_factory=_ids())
    assert rows == [host]
    assert host.unicode == "in 2014"
    assert host.box.x == 56.0
    assert host.box.x2 == 200.0
    assert "".join(char.char_unicode or "" for char in chars) == "in 2014"


def test_an_underscore_formula_stays_one_title():
    words = "SEXUAL DESIRE: THE DIFFERENCE BETWEEN MEN AND WOMEN"
    line, title_chars = _line(words, 78.0)
    underscores = [_char("_", title_chars[-1].box.x2 + 6.0 + index * 6.0) for index in range(6)]
    host = PdfParagraph(
        box=Box(x=78.0, y=100.0, x2=underscores[-1].box.x2, y2=112.0),
        unicode=words + " ______",
        pdf_paragraph_composition=[line, _formula(underscores)],
        layout_label="title",
    )
    rows = [host]
    detach_leader_page_numbers(rows, new_debug_id_factory=_ids())
    assert rows == [host]
    assert host.unicode == words
    assert "_" not in _texts(host)
    line_text = "".join(
        char.char_unicode or ""
        for char in host.pdf_paragraph_composition[0].pdf_line.pdf_character
    )
    assert line_text == words
    assert len(host.pdf_paragraph_composition) == 1
