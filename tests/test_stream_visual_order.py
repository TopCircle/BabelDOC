"""Reverse-paint decorative titles → visual LTR reorder (stream_order)."""

from __future__ import annotations

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
from babeldoc.format.pdf.document_il.il_version_1 import VisualBbox
from babeldoc.format.pdf.document_il.utils.layout_helper import (
    get_char_unicode_string,
)
from babeldoc.format.pdf.document_il.utils.stream_order import (
    is_stream_visually_reversed,
)
from babeldoc.format.pdf.document_il.utils.stream_order import (
    maybe_reorder_reversed_stream,
)
from babeldoc.format.pdf.document_il.utils.stream_order import (
    sort_chars_visual_order,
)
from babeldoc.format.pdf.document_il.utils.stream_order import (
    reorder_plain_paragraph_runs_if_stream_climbs,
)


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


def test_who_has_orgasms_reverse_stream_detected():
    # Paint order right-to-left; visual LTR: Who haS orgaSMS?
    letters = list("Who haS orgaSMS?")
    xs = list(range(100, 100 + 10 * len(letters), 10))
    stream = [_ch(ch, x) for ch, x in zip(reversed(letters), reversed(xs))]

    assert is_stream_visually_reversed(stream) is True
    # Plain or title: decorative reverse reorders (geometry gate)
    for label in ("plain text", "title", None):
        ordered = maybe_reorder_reversed_stream(stream, layout_label=label)
        assert ordered is not stream
        assert "".join(c.char_unicode for c in ordered) == "Who haS orgaSMS?"
    text = get_char_unicode_string(
        maybe_reorder_reversed_stream(stream, layout_label="title")
    )
    assert _alnum(text).startswith("who")
    assert "orgasms" in _alnum(text)


def test_ltr_body_not_reversed():
    word = "There is a myth"
    chars = [_ch(ch, 100 + i * 7) for i, ch in enumerate(word)]
    assert is_stream_visually_reversed(chars) is False
    assert maybe_reorder_reversed_stream(chars) is chars  # identity
    assert [c.char_unicode for c in sort_chars_visual_order(chars)] == list(word)


def test_sort_is_idempotent_on_ltr():
    word = "prepare for the best"
    chars = [_ch(ch, 50 + i * 6) for i, ch in enumerate(word)]
    once = sort_chars_visual_order(chars)
    twice = sort_chars_visual_order(once)
    assert [c.char_unicode for c in once] == [c.char_unicode for c in twice]


def test_long_body_not_reordered_even_if_partially_rtl():
    """Guard: long runs skip reorder even when reverse_ratio would fire."""
    # Build a long reverse stream — decorative guard rejects by length
    letters = list("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789xxx")
    assert len(letters) > 64
    xs = list(range(100, 100 + 5 * len(letters), 5))
    stream = [_ch(ch, x) for ch, x in zip(reversed(letters), reversed(xs))]
    # may be reverse-dominant geometrically
    assert is_stream_visually_reversed(stream) is True
    # but maybe_reorder refuses long runs
    assert maybe_reorder_reversed_stream(stream) is stream


def test_cluster_by_y_then_x():
    """Two visual lines: lower line first in stream, higher y on top."""
    # PDF y grows up: line at y=120 is above y=100
    top = [_ch(c, 100 + i * 10, y=120) for i, c in enumerate("AB")]
    bot = [_ch(c, 100 + i * 10, y=100) for i, c in enumerate("CD")]
    # stream paints bottom first, reverse within top
    stream = list(reversed(bot)) + list(reversed(top))
    ordered = sort_chars_visual_order(stream)
    assert "".join(c.char_unicode for c in ordered) == "ABCD"


def test_1chapter_misplaced_digit_becomes_chapter_1():
    """OA decorative '1' painted first at right edge → visual 'Chapter 1'."""
    # Stream: digit at x=199 first, then Chapter LTR from x=44 (tight kerning)
    chapter = list("Chapter")
    xs_ch = [44.0 + i * 9 for i in range(len(chapter))]
    stream = [_ch("1", 199.0)] + [_ch(c, x) for c, x in zip(chapter, xs_ch)]
    assert "".join(c.char_unicode for c in stream) == "1Chapter"
    # plain or title: misplaced digit + decorative short run
    ordered = maybe_reorder_reversed_stream(stream, layout_label="plain text")
    assert ordered is not stream
    assert "".join(c.char_unicode for c in ordered) == "Chapter1"
    text = get_char_unicode_string(ordered)
    alnum = "".join(c for c in text.lower() if c.isalnum())
    assert alnum.startswith("chapter")
    assert alnum.endswith("1")
    assert not alnum.startswith("1chapter")


def test_plain_decorative_reverse_reorders_single_policy():
    """Geometry+label policy: plain mid-page decorative reverse reorders once."""
    letters = list("Who haS orgaSMS?")
    xs = list(range(100, 100 + 10 * len(letters), 10))
    stream = [_ch(ch, x) for ch, x in zip(reversed(letters), reversed(xs))]
    assert is_stream_visually_reversed(stream) is True
    for label in (None, "", "plain text", "paragraph", "text", "title"):
        ordered = maybe_reorder_reversed_stream(
            stream, layout_label=label, in_page_top_band=False
        )
        assert ordered is not stream
        assert "".join(c.char_unicode for c in ordered) == "Who haS orgaSMS?"
    # abandon / figure never
    for label in ("abandon", "figure", "table"):
        assert (
            maybe_reorder_reversed_stream(
                stream, layout_label=label, in_page_top_band=True
            )
            is stream
        )


def test_long_ltr_body_identity():
    word = "prepare for the best syndrome analysis path"
    chars = [_ch(ch, 50 + i * 6) for i, ch in enumerate(word)]
    assert maybe_reorder_reversed_stream(chars, layout_label="plain text") is chars


def test_descender_glyphs_stay_on_same_line_as_peers():
    """arXiv body: p/y have lower box.y but same topline — must not split.

    Regression: figure golden dual scrambled ``pseudo-syndrome`` → ``seudo``
    when mid-Y clustering put descenders in another bucket.
    """
    # Tops aligned at y2=360; bottoms differ for descenders
    def _glyph(ch: str, x: float, *, descender: bool = False) -> PdfCharacter:
        if descender:
            box = Box(x=x, y=353.5, x2=x + 5, y2=360.0)  # lower bottom
        else:
            box = Box(x=x, y=355.4, x2=x + 5, y2=360.0)
        return PdfCharacter(
            pdf_character_id=None,
            char_unicode=ch,
            box=box,
            visual_bbox=VisualBbox(box=box),
            pdf_style=PdfStyle(font_id="base", font_size=10.0, graphic_state=None),
            scale=1.0,
            advance=5.0,
            vertical=False,
            xobj_id=None,
        )

    word = list("pseudo-syndrome")
    # p and y are descenders
    desc = {"p", "y", "g", "q"}
    stream = [
        _glyph(ch, 100 + i * 6, descender=(ch in desc)) for i, ch in enumerate(word)
    ]
    # LTR body line must not be rewritten
    assert maybe_reorder_reversed_stream(stream) is stream
    ordered = sort_chars_visual_order(stream)
    assert "".join(c.char_unicode for c in ordered) == "pseudo-syndrome"


def test_ltr_body_line_not_reordered_when_sort_would_shuffle_noise():
    """Even if decorative-like (single letters), pure LTR body is untouched."""
    word = list("compositeoperation")
    chars = [_ch(ch, 50 + i * 5) for i, ch in enumerate(word)]
    assert maybe_reorder_reversed_stream(chars) is chars


def _paragraph(
    text: str,
    *,
    y: float,
    xobj_id: int = 0,
    label: str = "plain text",
) -> PdfParagraph:
    return PdfParagraph(
        box=Box(x=100, y=y, x2=500, y2=y + 30),
        pdf_paragraph_composition=[],
        unicode=text,
        xobj_id=xobj_id,
        layout_label=label,
    )


def test_reorders_plain_paragraph_run_when_stream_climbs():
    paragraphs = [
        _paragraph("bottom", y=100),
        _paragraph("middle", y=140),
        _paragraph("top", y=180),
    ]
    assert reorder_plain_paragraph_runs_if_stream_climbs(paragraphs) is True
    assert [p.unicode for p in paragraphs] == ["top", "middle", "bottom"]


def test_does_not_reorder_mixed_xobject_or_title_run():
    paragraphs = [
        _paragraph("bottom", y=100),
        _paragraph("middle", y=140, xobj_id=1),
        _paragraph("top", y=180, label="title"),
    ]
    assert reorder_plain_paragraph_runs_if_stream_climbs(paragraphs) is False
