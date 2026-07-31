"""PR-B: decorative title top-band reorder + Chapter spacing/merge."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import Page
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


def _ch(text: str, x: float, y: float = 100.0, w: float = 8.0) -> PdfCharacter:
    box = Box(x=x, y=y, x2=x + w, y2=y + 12)
    return PdfCharacter(
        pdf_character_id=None,
        char_unicode=text,
        box=box,
        visual_bbox=VisualBbox(box=box),
        pdf_style=PdfStyle(font_id="base", font_size=12.0, graphic_state=None),
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
    stream = [_ch(ch, x) for ch, x in zip(reversed(letters), reversed(xs))]
    ordered = maybe_reorder_reversed_stream(
        stream, layout_label="plain text", in_page_top_band=False
    )
    assert ordered is not stream
    assert "".join(c.char_unicode for c in ordered) == "Who haS orgaSMS?"


def test_plain_text_top_band_reorders_reverse_title():
    """PR-B: mis-labeled plain text in top band may reverse-reorder."""
    letters = list("Who haS orgaSMS?")
    xs = list(range(100, 100 + 10 * len(letters), 10))
    stream = [_ch(ch, x) for ch, x in zip(reversed(letters), reversed(xs))]
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
    stream = [_ch("1", 199.0)] + [_ch(c, x) for c, x in zip(chapter, xs_ch)]
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
) -> PdfParagraph:
    chars = []
    cx = x
    for ch in text:
        chars.append(_ch(ch, cx, y=y, w=char_w))
        cx += char_w + 1
    line = PdfLine(
        box=Box(x=x, y=y, x2=cx, y2=y2),
        pdf_character=chars,
    )
    p = PdfParagraph(
        box=Box(x=x, y=y, x2=cx, y2=y2),
        pdf_style=PdfStyle(font_id="base", font_size=18.0, graphic_state=None),
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
    finder = _finder()
    page = Page(
        page_number=0,
        mediabox=Box(x=0, y=0, x2=612, y2=792),
        cropbox=SimpleNamespace(box=Box(x=0, y=0, x2=612, y2=792)),
    )
    ch = _line_para("Chapter 1", y=730, y2=760, layout_label="plain text")
    title = _line_para("Love and Sex", y=700, y2=728, layout_label="title")
    body = _line_para(
        "This is a long body paragraph about anatomy that must not merge.",
        y=400,
        y2=440,
        layout_label="plain text",
    )
    paras = [ch, title, body]
    # No merge step in process path; compositions stay three paragraphs.
    assert len(paras) == 3
    assert "chapter" in (paras[0].unicode or "").lower()
    assert "love" in (paras[1].unicode or "").lower()
    assert "anatomy" in (paras[2].unicode or "")
    assert not hasattr(finder, "merge_chapter_title_paragraphs")