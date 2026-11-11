"""Directory rows stay one line each. They are not a hanging paragraph."""

from __future__ import annotations

from unittest.mock import MagicMock

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter
from babeldoc.format.pdf.document_il.il_version_1 import PdfLine
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraphComposition
from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
from babeldoc.format.pdf.document_il.il_version_1 import VisualBbox
from babeldoc.format.pdf.document_il.midend.paragraph_finder import ParagraphFinder
from babeldoc.format.pdf.document_il.utils.callout_merge import (
    merge_stacked_narrow_callout_paragraphs,
)
from babeldoc.format.pdf.document_il.utils.layout_intent import LayoutIntent
from babeldoc.format.pdf.document_il.utils.layout_intent import LayoutIntentRole
from babeldoc.format.pdf.document_il.utils.paragraph_split_policy import (
    should_split_line_pair,
)
from babeldoc.format.pdf.document_il.utils.placement_paradigm import ParadigmMark
from babeldoc.format.pdf.document_il.utils.placement_paradigm import PlacementParadigm
from babeldoc.format.pdf.document_il.utils.rect_column_reflow import assign_rect_columns
from babeldoc.format.pdf.document_il.utils.rect_column_reflow import flow_rect_columns
from babeldoc.format.pdf.document_il.utils.rect_column_reflow import (
    uses_rect_column_fill,
)
from babeldoc.format.pdf.document_il.utils.sealed_paragraph_join import (
    join_sealed_paragraphs,
)
from babeldoc.format.pdf.document_il.utils.sentence_paragraph_repair import (
    _can_continue,
)
from babeldoc.format.pdf.document_il.utils.toc_rows import is_toc_entry_line
from babeldoc.format.pdf.document_il.utils.toc_rows import is_toc_header_text
from babeldoc.format.pdf.document_il.utils.toc_rows import is_toc_page_header
from babeldoc.format.pdf.document_il.utils.toc_rows import is_toc_row
from babeldoc.format.pdf.document_il.utils.toc_rows import is_toc_stack
from babeldoc.format.pdf.document_il.utils.toc_rows import separate_glued_directory_rows
from babeldoc.format.pdf.translation_config import TranslationConfig
from babeldoc.translator.fixed_map_translator import FixedMapTranslator

_SPLIT = {
    "median_width": 400.0,
    "split_short_lines": True,
    "short_line_split_factor": 0.5,
    "soft_mid_sentence_font_split": False,
}


def _char(ch: str, x: float, y: float) -> PdfCharacter:
    box = Box(x=x, y=y, x2=x + 5.0, y2=y + 10.0)
    return PdfCharacter(
        char_unicode=ch,
        box=box,
        visual_bbox=VisualBbox(box=Box(x=box.x, y=box.y, x2=box.x2, y2=box.y2)),
        pdf_style=PdfStyle(font_id="F", font_size=10.0, graphic_state=None),
    )


def _line(text: str, y: float, x0: float = 56.0) -> PdfParagraphComposition:
    chars = []
    x = x0
    for ch in text:
        chars.append(_char(ch, x, y))
        x += 6.0
    return PdfParagraphComposition(
        pdf_line=PdfLine(
            box=Box(x=x0, y=y, x2=x, y2=y + 12),
            pdf_character=chars,
        )
    )


def _gap_line(title: str, page: str, y: float, page_x: float) -> PdfLine:
    chars = []
    x = 56.0
    for ch in title:
        chars.append(_char(ch, x, y))
        x += 6.0
    x = page_x
    for ch in page:
        chars.append(_char(ch, x, y))
        x += 6.0
    return PdfLine(
        box=Box(x=56.0, y=y, x2=x, y2=y + 12),
        pdf_character=chars,
    )


def _para(text: str, x: float, y: float, *, width: float | None = None) -> PdfParagraph:
    comp = _line(text, y, x0=x)
    return PdfParagraph(
        box=Box(x=x, y=y, x2=x + (width if width is not None else len(text) * 6.0), y2=y + 12),
        pdf_style=PdfStyle(font_id="F", font_size=10.0, graphic_state=None),
        pdf_paragraph_composition=[comp],
        unicode=text,
        layout_id="L1",
        xobj_id=1,
        debug_id="d",
    )


def _config() -> TranslationConfig:
    return TranslationConfig(
        translator=FixedMapTranslator(),
        input_file="toc.pdf",
        lang_in="en",
        lang_out="zh-CN",
        doc_layout_model=MagicMock(),
        auto_extract_glossary=False,
    )


def _texts(paragraph: PdfParagraph) -> str:
    return "".join(
        char.char_unicode or ""
        for comp in paragraph.pdf_paragraph_composition or []
        if comp.pdf_line
        for char in comp.pdf_line.pdf_character or []
    )


def test_leaders_and_page_numbers_are_directory_rows():
    assert is_toc_entry_line(_line("." * 19 + "41", 100).pdf_line)
    assert is_toc_entry_line(_line("ORGASM" + "…" * 3 + "50", 80).pdf_line)
    assert is_toc_entry_line(
        _line("THE RELATIONSHIP CYCLE " + "_" * 8 + " 6", 60).pdf_line
    )
    assert is_toc_entry_line(_line("44", 40, x0=475).pdf_line)
    assert is_toc_entry_line(_gap_line("Title", "44", 20, 475))
    assert not is_toc_entry_line(_line("in 2014", 10).pdf_line)
    assert not is_toc_entry_line(_line("Dirty Talking", 0).pdf_line)


def test_dotless_rows_between_page_numbers_split():
    lines = [
        _line("Foreplay", 400).pdf_line,
        _line("." * 19 + "41", 380).pdf_line,
        _line("Dirty Talking", 360).pdf_line,
        _line("Gentle Touching", 340).pdf_line,
        _line("44", 320, x0=475).pdf_line,
    ]
    assert is_toc_stack(lines)
    assert should_split_line_pair(
        lines[2],
        lines[3],
        toc_stack=True,
        **_SPLIT,
    )


def test_contents_page_splits_untitled_rows():
    lines = [
        _line("Missionary Position 1", 400, x0=85).pdf_line,
        _line("Missionary Position 2", 386, x0=85).pdf_line,
        _line("Grinding", 372, x0=85).pdf_line,
        _line("Alphabet Position", 358, x0=85).pdf_line,
    ]
    assert not is_toc_stack(lines)
    assert is_toc_stack(lines, on_toc_page=True)
    assert is_toc_header_text("TABLE OF CONTENTS!")
    header = _para("TABLE OF CONTENTS!", 70, 700, width=180)
    rows = PdfParagraph(
        box=Box(x=85, y=300, x2=300, y2=420),
        pdf_style=PdfStyle(font_id="F", font_size=10.0, graphic_state=None),
        pdf_paragraph_composition=[
            _line("Missionary Position 1", 400, x0=85),
            _line("Missionary Position 2", 386, x0=85),
            _line("Grinding", 372, x0=85),
            _line("Alphabet Position", 358, x0=85),
        ],
        unicode="positions",
        layout_label="plain text",
    )
    paras = [header, rows]
    ParagraphFinder(_config()).process_independent_paragraphs(paras, 400.0)
    assert [_texts(p) for p in paras] == [
        "TABLE OF CONTENTS!",
        "Missionary Position 1",
        "Missionary Position 2",
        "Grinding",
        "Alphabet Position",
    ]
    assert all(p.layout_label == "toc" for p in paras[1:])


def _one_row(text: str, y: float) -> PdfParagraph:
    paragraph = PdfParagraph(
        box=Box(x=85, y=y, x2=85 + len(text) * 6.0, y2=y + 12),
        pdf_style=PdfStyle(font_id="F", font_size=10.0, graphic_state=None),
        pdf_paragraph_composition=[_line(text, y, x0=85)],
        unicode="",
        layout_label="plain text",
    )
    return paragraph


def test_separate_directory_rows_are_not_fused():
    """Each position line is already its own paragraph. A later join must not fuse them."""
    names = [
        "Missionary Position 1",
        "Missionary Position 2",
        "Grinding",
        "Alphabet Position",
    ]
    bare = [_one_row(name, 400 - 14 * index) for index, name in enumerate(names)]
    page = type("_Page", (), {})()
    page.pdf_paragraph = bare
    join_sealed_paragraphs(page)
    assert len(page.pdf_paragraph) == 1

    header = PdfParagraph(
        box=Box(x=70, y=700, x2=280, y2=720),
        pdf_style=PdfStyle(font_id="F", font_size=16.0, graphic_state=None),
        pdf_paragraph_composition=[_line("TABLE OF CONTENTS!", 700, x0=70)],
        unicode="",
        layout_label="title",
    )
    rows = [_one_row(name, 400 - 14 * index) for index, name in enumerate(names)]
    sentence = _one_row("She smiled today.", 200)
    paras = [header, *rows, sentence]
    ParagraphFinder(_config()).process_independent_paragraphs(paras, 400.0)
    assert is_toc_page_header("TABLE OF CONTENTS!")
    assert not is_toc_page_header("See the contents.")
    assert not is_toc_page_header("Go to Table Of Contents |")
    assert not is_toc_page_header("Back to Table of Contents")
    assert not is_toc_page_header("Return to Table of Contents")
    assert is_toc_row(_line("Missionary Position 1", 0).pdf_line)
    assert not is_toc_row(_line("www.gabriellemoore.com", 0).pdf_line)
    assert [p.layout_label for p in rows] == ["toc", "toc", "toc", "toc"]
    assert sentence.layout_label == "plain text"
    assert header.layout_label == "title"
    page.pdf_paragraph = paras
    join_sealed_paragraphs(page)
    assert [_texts(p) for p in page.pdf_paragraph if p.layout_label == "toc"] == names


def test_two_leaders_mark_the_dotless_rows():
    leaders = [
        _one_row("Foreplay" + "." * 8 + "45", 500),
        _one_row("Orgasm" + "." * 8 + "50", 486),
    ]
    rows = [
        _one_row("Missionary Position 1", 400),
        _one_row("Grinding", 386),
        _one_row("Alphabet Position", 372),
        _one_row("Woman on Top 1", 358),
    ]
    paras = [*leaders, *rows]
    ParagraphFinder(_config()).process_independent_paragraphs(paras, 400.0)
    assert all(p.layout_label == "toc" for p in rows)


def test_a_citation_inside_prose_is_not_a_directory():
    lines = [
        _line("This is a sentence.", 300).pdf_line,
        _line("See the note .... 12", 280).pdf_line,
        _line("Another sentence ends.", 260).pdf_line,
    ]
    assert not is_toc_stack(lines)
    assert not should_split_line_pair(
        _line("The Female", 400).pdf_line,
        _line("Vulva", 385).pdf_line,
        layout_label="figure_caption",
        toc_stack=False,
        **_SPLIT,
    )


def test_finder_keeps_each_directory_row():
    comps = [
        _line("Foreplay", 400),
        _line("." * 19 + "41", 380),
        _line("Dirty Talking", 360),
        _line("Gentle Touching", 340),
        _line("Kissing", 320),
        _line("ORGASM" + "…" * 3 + "50", 300),
        _line("Missionary Position 1", 280),
        _line("Missionary Position 2", 260),
    ]
    para = PdfParagraph(
        box=Box(x=50, y=240, x2=520, y2=420),
        pdf_style=PdfStyle(font_id="F", font_size=10.0, graphic_state=None),
        pdf_paragraph_composition=comps,
        unicode="x",
        layout_label="plain text",
    )
    paras = [para]
    ParagraphFinder(_config()).process_independent_paragraphs(paras, 400.0)
    assert len(paras) == 8
    assert [_texts(p) for p in paras] == [
        "Foreplay",
        "." * 19 + "41",
        "Dirty Talking",
        "Gentle Touching",
        "Kissing",
        "ORGASM" + "…" * 3 + "50",
        "Missionary Position 1",
        "Missionary Position 2",
    ]
    assert all(p.layout_label == "toc" for p in paras)


def test_right_page_number_does_not_glue_the_rows():
    finder = ParagraphFinder(_config())
    right = [
        _para("Foreplay rules", 56, 400),
        _para("44", 475, 400),
        _para("Kissing", 56, 380),
    ]
    finder.merge_alternating_line_number_paragraphs(right)
    assert len(right) == 3

    left = [
        _para("The sentence goes on", 56, 400),
        _para("12", 20, 400),
        _para("and finishes here.", 56, 380),
    ]
    finder.merge_alternating_line_number_paragraphs(left)
    assert len(left) == 2
    assert "finishes" in _texts(left[0])


def test_callout_and_sentence_repair_leave_directory_rows():
    bare = [
        _para("Dirty Talking", 56, 200, width=90),
        _para("Gentle Touching", 56, 180, width=100),
    ]
    merge_stacked_narrow_callout_paragraphs(bare)
    assert len(bare) == 1

    kept = [
        _para("Dirty Talking", 56, 200, width=90),
        _para("Gentle Touching", 56, 180, width=100),
    ]
    for para in kept:
        para.layout_label = "toc"
    merge_stacked_narrow_callout_paragraphs(kept)
    assert len(kept) == 2

    upper = _para("and,", 50, 200, width=40)
    lower = _para("zing", 50, 180, width=40)
    assert _can_continue(upper, lower)
    upper.layout_label = "toc"
    assert not _can_continue(upper, lower)


def _ids():
    count = 0

    def _next() -> str:
        nonlocal count
        count += 1
        return f"t{count}"

    return _next


def _row_of(chars, *, label: str = "plain text") -> PdfParagraph:
    xs = [char.box.x for char in chars]
    ys = [char.box.y for char in chars]
    x2s = [char.box.x2 for char in chars]
    y2s = [char.box.y2 for char in chars]
    return PdfParagraph(
        box=Box(x=min(xs), y=min(ys), x2=max(x2s), y2=max(y2s)),
        pdf_paragraph_composition=[
            PdfParagraphComposition(
                pdf_line=PdfLine(
                    box=Box(x=min(xs), y=min(ys), x2=max(x2s), y2=max(y2s)),
                    pdf_character=chars,
                )
            )
        ],
        unicode="x",
        layout_label=label,
        debug_id="row",
    )


def test_leaders_give_up_the_page_number():
    chars = []
    x = 56.0
    for ch in "DESIRE....":
        chars.append(_char(ch, x, 100))
        x += 5
    chars.append(_char("4", x, 100))
    chars.append(_char("1", x + 6, 100))
    rows = [_row_of(chars)]
    separate_glued_directory_rows(rows, new_debug_id_factory=_ids())
    assert _texts(rows[0]) == "DESIRE...."
    assert _texts(rows[1]) == "41"


def test_a_contents_entry_called_a_title_is_still_a_row():
    header = _para("TABLE OF CONTENTS!", 70, 700, width=180)
    header.layout_label = "title"
    chapter = _para("CHAPTER 5: FOREPLAY", 56, 600, width=200)
    chapter.layout_label = "title"
    tips = _para("Hot Tips to Remember", 56, 400, width=140)
    tips.layout_label = "title"
    paras = [header, chapter, tips]
    ParagraphFinder(_config()).process_independent_paragraphs(paras, 400.0)
    assert header.layout_label == "title"
    assert chapter.layout_label == "title"
    assert tips.layout_label == "toc"


def test_a_section_rule_does_not_keep_the_next_entry():
    chars = []
    x = 78.0
    for ch in "CYCLE__":
        chars.append(_char(ch, x, 220))
        x += 6
    chars.append(_char("6", 500, 220))
    x = 114.0
    for ch in "In the Beginning":
        chars.append(_char(ch, x, 200))
        x += 6
    rows = [_row_of(chars, label="title")]
    separate_glued_directory_rows(rows, new_debug_id_factory=_ids())
    texts = [_texts(row) for row in rows]
    assert texts[0].startswith("CYCLE")
    assert "6" not in texts[0]
    assert "In the Beginning" not in texts[0]
    assert "In the Beginning" in texts
    assert "6" in texts


def test_a_margin_page_number_leaves_the_title():
    chars = []
    x = 56.0
    for ch in "REVVING":
        chars.append(_char(ch, x, 180))
        x += 6
    chars.append(_char("4", 475, 180))
    chars.append(_char("5", 481, 180))
    rows = [_row_of(chars)]
    separate_glued_directory_rows(rows, new_debug_id_factory=_ids())
    assert _texts(rows[0]) == "REVVING"
    assert _texts(rows[1]) == "45"
    assert rows[1].box.x >= 475
    assert rows[1].layout_label == "toc"


def test_a_year_inside_a_sentence_stays_on_the_line():
    rows = [_row_of([_char(ch, 56.0 + index * 6, 100) for index, ch in enumerate("in 2014")])]
    separate_glued_directory_rows(rows, new_debug_id_factory=_ids())
    assert len(rows) == 1
    assert _texts(rows[0]) == "in 2014"


def test_wrapped_prose_stays_one_paragraph():
    chars = [_char(ch, 56.0 + index * 6, 200) for index, ch in enumerate("She smiled")]
    chars += [_char(ch, 56.0 + index * 6, 180) for index, ch in enumerate("Then she left.")]
    rows = [_row_of(chars)]
    separate_glued_directory_rows(rows, new_debug_id_factory=_ids())
    assert len(rows) == 1


def test_directory_rows_are_not_pulled_into_a_column():
    wide = _para("CHAPTER", 56, 400, width=420)
    wide.layout_label = "toc"
    wide.layout_intent = LayoutIntent(
        role=LayoutIntentRole.BODY,
        design_box=Box(x=56, y=400, x2=476, y2=412),
        top_inset=0.0,
        bottom_inset=0.0,
        paradigm_mark=ParadigmMark(PlacementParadigm.RECT_REFLOW, 0.9, "test"),
    )
    item = _para("Dirty Talking", 85, 380, width=80)
    item.layout_label = "toc"
    item.layout_intent = LayoutIntent(
        role=LayoutIntentRole.BODY,
        design_box=Box(x=85, y=380, x2=165, y2=392),
        top_inset=0.0,
        bottom_inset=0.0,
        paradigm_mark=ParadigmMark(PlacementParadigm.RECT_REFLOW, 0.9, "test"),
    )
    assert not uses_rect_column_fill(item)
    page = [wide, item]
    assign_rect_columns(page)
    assert item.box.x == 85
    # Four points apart, same left edge: a body column would become one run.
    lower = _para("Gentle Touching", 56, 386, width=100)
    lower.layout_label = "toc"
    lower.layout_intent = LayoutIntent(
        role=LayoutIntentRole.BODY,
        design_box=Box(x=56, y=386, x2=156, y2=398),
        top_inset=0.0,
        bottom_inset=0.0,
        paradigm_mark=ParadigmMark(PlacementParadigm.RECT_REFLOW, 0.9, "test"),
    )
    stacked = [wide, lower]
    flow_rect_columns(stacked)
    assert len(stacked) == 2
    assert _texts(lower) == "Gentle Touching"


def test_llt_multiline_toc_entries_and_interrogatives():
    """TOC entries ending with '?' or continuing tightly across lines remain intact."""
    header = _para("Table Of Contents", 56, 700, width=150)
    lines = [
        _line("Have You Been Groomed to", 400.0, x0=74.0),
        _line("Come Quickly?", 386.2, x0=74.0),
        _line("Is It All in Your Head?", 366.4, x0=74.0),
        _line("Other Options to Cool Things", 346.6, x0=74.0),
        _line("Down", 332.8, x0=74.0),
        _line("Technique 2: Establishing", 305.0, x0=56.0),
        _line("Control of Your Ejaculation", 291.6, x0=56.0),
        _line("Response", 278.2, x0=56.0),
    ]
    block = PdfParagraph(
        box=Box(x=56, y=270, x2=280, y2=412),
        pdf_style=PdfStyle(font_id="F", font_size=12.0, graphic_state=None),
        pdf_paragraph_composition=lines,
        unicode="titles",
        layout_label="title",
    )
    paras = [header, block]
    ParagraphFinder(_config()).process_independent_paragraphs(paras, 400.0)

    extracted = [_texts(p) for p in paras]
    assert extracted == [
        "Table Of Contents",
        "Have You Been Groomed toCome Quickly?",
        "Is It All in Your Head?",
        "Other Options to Cool ThingsDown",
        "Technique 2: EstablishingControl of Your EjaculationResponse",
    ]
    assert all(p.layout_label == "toc" for p in paras[1:])


def test_footer_url_never_captures_or_paints_toc_leaders():
    """A URL in the footer with page number must never capture or paint dot leaders."""
    from babeldoc.format.pdf.document_il.utils.toc_rows import capture_toc_leaders
    from babeldoc.format.pdf.document_il.utils.toc_rows import clear_toc_source
    from babeldoc.format.pdf.document_il.utils.toc_rows import paint_toc_leaders

    clear_toc_source()
    footer = _para("www.GabrielleMoore.com", 254.0, 765.0, width=150)
    page_num = _para("2", 527.0, 765.0, width=10)
    paras = [footer, page_num]
    capture_toc_leaders(paras)
    paint_toc_leaders(paras)
    # Ensure no leader paragraphs were injected
    assert len(paras) == 2
    assert _texts(paras[0]) == "www.GabrielleMoore.com"
    assert _texts(paras[1]) == "2"


def test_is_multi_line_continuation_gaps_and_rules():
    """Verify vgap thresholds and connector/particle/technique continuation rules."""
    from babeldoc.format.pdf.document_il.utils.toc_rows import (
        is_multi_line_continuation,
    )

    # Gap <= 6.0 pt allows continuation with connector word
    assert is_multi_line_continuation("Have You Been Groomed to", "Come Quickly?", 4.0)
    assert is_multi_line_continuation("Breathing Techniques for", "Lasting Longer", 4.0)
    assert is_multi_line_continuation("Other Options to Cool Things", "Down", 4.0)
    assert is_multi_line_continuation("Technique 2: Establishing", "Control of Your Ejaculation", 4.0)
    assert is_multi_line_continuation("Control of Your Ejaculation", "Response", 4.0)

    # Gap > 6.0 pt rejects continuation even if connector word matches
    assert not is_multi_line_continuation("Have You Been Groomed to", "Come Quickly?", 7.0)
    assert not is_multi_line_continuation("Have You Been Groomed to", "Come Quickly?", 10.0)

    # Terminal punctuation rejects continuation
    assert not is_multi_line_continuation("Come Quickly?", "Is It All in Your Head?", 4.0)
    assert not is_multi_line_continuation("Is It All in Your Head?", "What is Premature Ejaculation,", 4.0)


