"""PR-B: decorative title top-band reorder + Chapter spacing/merge."""

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
from babeldoc.format.pdf.document_il.utils.layout_helper import get_char_unicode_string
from babeldoc.format.pdf.document_il.utils.stream_order import (
    maybe_reorder_reversed_stream,
)
from babeldoc.format.pdf.document_il.utils.text_recovery import space_chapter_number


def _ch(
    text: str,
    x: float,
    y: float = 100.0,
    w: float = 8.0,
    *,
    font_size: float = 12.0,
) -> PdfCharacter:
    box = Box(x=x, y=y, x2=x + w, y2=y + font_size)
    return PdfCharacter(
        pdf_character_id=None,
        char_unicode=text,
        box=box,
        visual_bbox=VisualBbox(box=box),
        pdf_style=PdfStyle(font_id="base", font_size=font_size, graphic_state=None),
        scale=1.0,
        advance=w,
        vertical=False,
        xobj_id=None,
    )


def _alnum(s: str) -> str:
    return "".join(c.lower() for c in s if c.isalnum())


def test_space_chapter_number():
    assert space_chapter_number("Chapter1") == "Chapter 1"
    assert space_chapter_number("CHAPTER12") == "CHAPTER 12"
    assert space_chapter_number("Chapter 1") == "Chapter 1"  # already spaced
    assert space_chapter_number("Chapter1爱与性") == "Chapter 1 爱与性"
    assert space_chapter_number("Chapter 1爱与性") == "Chapter 1 爱与性"
    assert "Chapter 1" in get_char_unicode_string(
        [_ch(c, 10 + i * 8) for i, c in enumerate("Chapter1")]
    )


def test_normalize_decorative_title_case():
    from babeldoc.format.pdf.document_il.utils.text_recovery import (
        normalize_decorative_title_case,
    )
    from babeldoc.format.pdf.document_il.utils.text_recovery import (
        recover_latin_word_fragments,
    )

    assert normalize_decorative_title_case("Who haS orgaSMS?") == "who has orgasms?"
    # Global recovery must NOT lower body brands (B1)
    assert recover_latin_word_fragments("The iPhone works today.") == (
        "The iPhone works today."
    )
    assert normalize_decorative_title_case("Hello world") == "Hello world"


def test_plain_text_mid_page_decorative_reverse_single_call():
    """Single stream_order policy reorders mid-page plain decorative reverse."""
    letters = list("Who haS orgaSMS?")
    xs = list(range(100, 100 + 10 * len(letters), 10))
    stream = [_ch(ch, x) for ch, x in zip(reversed(letters), reversed(xs), strict=False)]
    ordered = maybe_reorder_reversed_stream(
        stream, layout_label="plain text", in_page_top_band=False
    )
    assert ordered is not stream
    assert "".join(c.char_unicode for c in ordered) == "Who haS orgaSMS?"


def test_plain_text_top_band_reorders_reverse_title():
    """PR-B: mis-labeled plain text in top band may reverse-reorder."""
    letters = list("Who haS orgaSMS?")
    xs = list(range(100, 100 + 10 * len(letters), 10))
    stream = [_ch(ch, x) for ch, x in zip(reversed(letters), reversed(xs), strict=False)]
    ordered = maybe_reorder_reversed_stream(
        stream, layout_label="plain text", in_page_top_band=True
    )
    assert ordered is not stream
    assert "".join(c.char_unicode for c in ordered) == "Who haS orgaSMS?"
    text = get_char_unicode_string(ordered)
    assert _alnum(text).startswith("who")
    assert "orgasms" in _alnum(text)


def test_1chapter_plain_becomes_chapter_1():
    chapter = list("Chapter")
    xs_ch = [44.0 + i * 9 for i in range(len(chapter))]
    stream = [_ch("1", 199.0)] + [_ch(c, x) for c, x in zip(chapter, xs_ch, strict=False)]
    ordered = maybe_reorder_reversed_stream(
        stream, layout_label="plain text", in_page_top_band=False
    )
    assert "".join(c.char_unicode for c in ordered) == "Chapter1"
    text = get_char_unicode_string(ordered)
    assert text.replace(" ", "").lower().startswith("chapter")
    assert "chapter 1" in text.lower() or text.lower().endswith("1")


def _line_para(
    text: str,
    *,
    x: float = 50.0,
    y: float = 720.0,
    y2: float = 750.0,
    layout_label: str = "plain text",
    char_w: float = 8.0,
    font_size: float = 12.0,
    para_font_size: float | None = None,
) -> PdfParagraph:
    chars = []
    cx = x
    for ch in text:
        chars.append(_ch(ch, cx, y=y, w=char_w, font_size=font_size))
        cx += char_w + 1
    line = PdfLine(
        box=Box(x=x, y=y, x2=cx, y2=y2),
        pdf_character=chars,
    )
    p = PdfParagraph(
        box=Box(x=x, y=y, x2=cx, y2=y2),
        pdf_style=PdfStyle(
            font_id="base",
            font_size=para_font_size if para_font_size is not None else 18.0,
            graphic_state=None,
        ),
        pdf_paragraph_composition=[PdfParagraphComposition(pdf_line=line)],
        unicode=text,
        layout_label=layout_label,
    )
    return p


def _finder() -> ParagraphFinder:
    """Minimal ParagraphFinder without full FontMapper config."""
    finder = object.__new__(ParagraphFinder)
    finder.translation_config = MagicMock()
    finder._current_page = None
    return finder


def test_chapter_and_title_stay_separate_paragraphs():
    """Chapter N + title are not merged (preserve Trajan vs display styles)."""
    from babeldoc.format.pdf.document_il.utils.paragraph_split_policy import (
        split_glued_chapter_title_paragraphs,
    )

    finder = _finder()
    ch = _line_para("Chapter 1", y=730, y2=760, layout_label="plain text")
    title = _line_para("Love and Sex", y=700, y2=728, layout_label="title")
    body = _line_para(
        "This is a long body paragraph about anatomy that must not merge.",
        y=400,
        y2=440,
        layout_label="plain text",
    )
    paras = [ch, title, body]
    split_glued_chapter_title_paragraphs(paras, new_debug_id_factory=lambda: "x")
    assert len(paras) == 3
    assert "chapter" in (paras[0].unicode or "").lower() or "chapter" in "".join(
        c.char_unicode for c in paras[0].pdf_paragraph_composition[0].pdf_line.pdf_character
    ).lower()
    assert not hasattr(finder, "merge_chapter_title_paragraphs")


def _mixed_opener_para(chapter: str, title: str, *, ch_size=32.0, title_size=56.0):
    """OA Ch1/Ch3: Chapter @32pt + digit/title @56pt on one visual line."""
    chars = []
    x = 44.0
    for _i, ch in enumerate(chapter):
        chars.append(_ch(ch, x, y=661.0, w=ch_size * 0.55, font_size=ch_size))
        x += ch_size * 0.55 + 1
    x += 8.0
    for ch in title:
        chars.append(_ch(ch, x, y=605.0, w=title_size * 0.5, font_size=title_size))
        x += title_size * 0.5 + 1
    line = PdfLine(
        box=Box(x=44.0, y=605.0, x2=x, y2=686.0),
        pdf_character=chars,
    )
    return PdfParagraph(
        box=Box(x=44.0, y=605.0, x2=x, y2=686.0),
        pdf_style=PdfStyle(font_id="base", font_size=ch_size, graphic_state=None),
        pdf_paragraph_composition=[PdfParagraphComposition(pdf_line=line)],
        unicode=chapter + "  " + title,
        layout_label="title",
    )


def test_oa_ch1_glued_opener_splits_two_levels():
    """OA p7: 56pt digit glues 'Chapter 1' to 'Love and Sex' — must split."""
    from babeldoc.format.pdf.document_il.utils.paragraph_split_policy import (
        split_glued_chapter_title_paragraphs,
    )

    glued = _mixed_opener_para("Chapter 1", "Love and Sex")
    paras = [glued]
    split_glued_chapter_title_paragraphs(paras, new_debug_id_factory=lambda: "t1")
    assert len(paras) == 2
    ch_text = "".join(
        c.char_unicode for c in paras[0].pdf_paragraph_composition[0].pdf_line.pdf_character
    )
    title_text = "".join(
        c.char_unicode for c in paras[1].pdf_paragraph_composition[0].pdf_line.pdf_character
    )
    assert ch_text.replace(" ", "").lower().startswith("chapter1")
    assert "love" in title_text.lower()
    assert "chapter" not in title_text.lower()


def test_oa_ch3_glued_opener_splits_two_levels():
    from babeldoc.format.pdf.document_il.utils.paragraph_split_policy import (
        split_glued_chapter_title_paragraphs,
    )

    glued = _mixed_opener_para("Chapter 3", "beanactIonMan")
    paras = [glued]
    split_glued_chapter_title_paragraphs(paras, new_debug_id_factory=lambda: "t3")
    assert len(paras) == 2
    ch_text = "".join(
        c.char_unicode for c in paras[0].pdf_paragraph_composition[0].pdf_line.pdf_character
    )
    title_text = "".join(
        c.char_unicode for c in paras[1].pdf_paragraph_composition[0].pdf_line.pdf_character
    )
    assert "3" in ch_text
    assert "bean" in title_text.lower()
    assert "chapter" not in title_text.lower()


def test_small_running_header_not_split():
    """13.4/15pt 'Love and Sex Chapter 1' running header stays one paragraph."""
    from babeldoc.format.pdf.document_il.utils.paragraph_split_policy import (
        split_glued_chapter_title_paragraphs,
    )

    # Prefix is title, not Chapter N — cut requires Chapter-first opener.
    hdr = _line_para(
        "Love and Sex Chapter 1",
        y=680,
        y2=687,
        layout_label="title",
        font_size=13.4,
        para_font_size=13.4,
    )
    paras = [hdr]
    split_glued_chapter_title_paragraphs(paras, new_debug_id_factory=lambda: "h")
    assert len(paras) == 1


def test_midcap_display_title_lowers_without_tracking():
    """W1b: mid-caps display title lowers even when letters are tight."""
    from babeldoc.format.pdf.document_il.utils.text_recovery import (
        should_normalize_midcap_title,
    )
    from babeldoc.format.pdf.document_il.utils.vertical_gap import DISPLAY_TITLE_SIZE_PT

    title = "SLoWcoMfortabLe ScreW"
    para = _line_para(
        title,
        layout_label="title",
        font_size=DISPLAY_TITLE_SIZE_PT,
        para_font_size=DISPLAY_TITLE_SIZE_PT,
    )
    assert should_normalize_midcap_title(para)
    finder = _finder()
    finder.update_paragraph_data(para, update_unicode=True, page=None)
    assert para.unicode == "slowcomfortable screw"


def test_plain_text_12pt_iphone_not_lowered():
    """W1b: 12pt body must keep brand mixed-case (no mid-caps OR)."""
    from babeldoc.format.pdf.document_il.utils.text_recovery import (
        should_normalize_midcap_title,
    )

    para = _line_para(
        "The iPhone works today.",
        layout_label="plain text",
        font_size=12.0,
        para_font_size=12.0,
    )
    assert not should_normalize_midcap_title(para)
    finder = _finder()
    finder.update_paragraph_data(para, update_unicode=True, page=None)
    assert "iPhone" in (para.unicode or "")
    assert "iphone" not in (para.unicode or "")


def test_camelcase_title_splits_before_lower():
    from babeldoc.format.pdf.document_il.utils.text_recovery import (
        should_normalize_midcap_title,
    )

    para = _line_para(
        "LearnTheTrigasmBasics",
        layout_label="title",
        font_size=18.0,
        para_font_size=18.0,
    )
    assert should_normalize_midcap_title(para)
    finder = _finder()
    finder.update_paragraph_data(para, update_unicode=True, page=None)
    assert para.unicode == "learn the trigasm basics"


def test_beanactionman_title_lowers():
    para = _line_para(
        "beanactIonMan",
        layout_label="title",
        font_size=56.0,
        para_font_size=56.0,
    )
    finder = _finder()
    finder.update_paragraph_data(para, update_unicode=True, page=None)
    assert para.unicode == "beanactionman"


def test_long_midcap_title_over_80_chars_lowers():
    """OA p59: name + DIRECT/THRUST tags exceed the old 80-char cap."""
    from babeldoc.format.pdf.document_il.utils.text_recovery import (
        should_normalize_midcap_title,
    )

    title = (
        '"the SLoWcoMfortabLe ScreW(up agaInSt a WaLL)" '
        "(dIrect thruSt, Soft Touch, acRoBaTic)"
    )
    assert len(title) > 80
    para = _line_para(
        title,
        layout_label="title",
        font_size=12.0,
        para_font_size=12.0,
    )
    assert should_normalize_midcap_title(para)
    finder = _finder()
    finder.update_paragraph_data(para, update_unicode=True, page=None)
    u = (para.unicode or "").lower()
    assert "slowcomfortable" in u.replace(" ", "")
    assert "direct" in u
    assert "thrust" in u
    assert "soft touch" in u
    assert "acrobatic" in u
    assert "SLoW" not in (para.unicode or "")


def test_wrapped_soft_touch_s_reads_in_order():
    """OA p59: S of SOFT is last in stream, leftmost on the wrapped tag line."""
    # Line 1 (higher y): dIrect thruSt
    chars = []
    x = 200.0
    y1 = 120.0
    for ch in "dIrect thruSt":
        w = 7.0 if ch != " " else 3.0
        chars.append(_ch(ch, x, y=y1, w=w, font_size=12.0))
        x += w
    # Line 2 (lower y): "oft touch, acrobatic" then S at left (stream last)
    y2 = 100.0
    x = 110.0
    line2 = "oft touch, acrobatic"
    for ch in line2:
        w = 7.0 if ch != " " else 3.0
        chars.append(_ch(ch, x, y=y2, w=w, font_size=12.0))
        x += w
    chars.append(_ch("S", 100.0, y=y2, w=8.0, font_size=12.0))
    line = PdfLine(
        box=Box(x=100.0, y=100.0, x2=x, y2=132.0),
        pdf_character=chars,
    )
    para = PdfParagraph(
        box=Box(x=100.0, y=100.0, x2=x, y2=132.0),
        pdf_style=PdfStyle(font_id="base", font_size=12.0, graphic_state=None),
        pdf_paragraph_composition=[PdfParagraphComposition(pdf_line=line)],
        unicode="",
        layout_label="title",
    )
    finder = _finder()
    finder.update_paragraph_data(para, update_unicode=True, page=None)
    u = (para.unicode or "").lower()
    assert "soft touch" in u
    assert "acrobatic" in u
    assert "acrobat s" not in u
    assert "direct" in u
    assert "thrust" in u

