"""Drop-cap letter rejoined to word remainder for MT input."""

from __future__ import annotations

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter
from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
from babeldoc.format.pdf.document_il.il_version_1 import VisualBbox
from babeldoc.format.pdf.document_il.utils.drop_cap import (
    is_drop_cap_pair,
    rejoin_drop_cap_in_text,
)
from babeldoc.format.pdf.document_il.utils.layout_helper import get_char_unicode_string
from babeldoc.format.pdf.document_il.utils.text_recovery import recover_latin_word_fragments


def _ch(
    u: str,
    x: float,
    *,
    size: float = 12.0,
    w: float | None = None,
    y: float = 200.0,
    font_id: str = "Body",
) -> PdfCharacter:
    if w is None:
        w = size * 0.55
    box = Box(x=x, y=y, x2=x + w, y2=y + size)
    return PdfCharacter(
        char_unicode=u,
        box=box,
        visual_bbox=VisualBbox(box=box),
        pdf_style=PdfStyle(font_id=font_id, font_size=size, graphic_state=None),
        scale=1.0,
        advance=w,
    )


def test_rejoin_drop_cap_text_if_you():
    assert rejoin_drop_cap_in_text("I f you want") == "If you want"
    assert rejoin_drop_cap_in_text("W e are told") == "We are told"
    # Must not glue full words
    assert rejoin_drop_cap_in_text("A man with a plan") == "A man with a plan"
    assert rejoin_drop_cap_in_text("I love you") == "I love you"


def test_geometry_if_you_want():
    """OA-style: Trajan I @35 + Myriad 'f you want…' @12.5 → If you want…"""
    chars = [
        _ch("I", 102.0, size=35.4, w=18.0, font_id="Trajan"),
        _ch("f", 121.1, size=12.5, w=5.0, font_id="Myriad"),
        _ch(" ", 126.0, size=12.5, w=3.0),
        _ch("y", 129.0, size=12.5, w=6.0, font_id="Myriad"),
        _ch("o", 135.0, size=12.5, w=6.0, font_id="Myriad"),
        _ch("u", 141.0, size=12.5, w=6.0, font_id="Myriad"),
        _ch(" ", 147.0, size=12.5, w=3.0),
        _ch("w", 150.0, size=12.5, w=7.0, font_id="Myriad"),
        _ch("a", 157.0, size=12.5, w=6.0, font_id="Myriad"),
        _ch("n", 163.0, size=12.5, w=6.0, font_id="Myriad"),
        _ch("t", 169.0, size=12.5, w=5.0, font_id="Myriad"),
    ]
    assert is_drop_cap_pair(chars[0], chars[1])
    text = get_char_unicode_string(chars)
    assert text.startswith("If you want")
    assert "I f" not in text


def test_nbsp_drop_cap_i():
    """Source often has NBSP before I; layout_helper normalizes NBSP first."""
    assert rejoin_drop_cap_in_text("I f you") == "If you"
    assert rejoin_drop_cap_in_text("\u00a0I f you").replace("\u00a0", "") == "If you"
    # recover path
    assert recover_latin_word_fragments("I f you want some action") == (
        "If you want some action"
    )


def test_no_false_join_sentence_i():
    """Standalone pronoun I before a full word stays."""
    assert rejoin_drop_cap_in_text("I love maintaining") == "I love maintaining"


def test_place_drop_cap_non_adjacent():
    """Drop-cap I after body stream still moves before f… for MT."""
    from babeldoc.format.pdf.document_il.utils.drop_cap import (
        place_drop_caps_before_continuations,
    )

    body = [_ch(c, 120 + i * 6, size=12.5, y=180.0) for i, c in enumerate("f you")]
    drop = _ch("I", 102.0, size=35.4, w=18.0, y=200.0, font_id="Trajan")
    # Stream: body first, drop-cap last (bottom→top paint remnant)
    stream = body + [drop]
    placed = place_drop_caps_before_continuations(stream)
    assert placed[0].char_unicode == "I"
    assert placed[1].char_unicode == "f"


def test_place_drop_cap_welcome_not_darling():
    """OA p3: leftover Trajan W rejoins elcome, not darling."""
    from babeldoc.format.pdf.document_il.utils.drop_cap import (
        place_drop_caps_before_continuations,
    )

    # Body 12.5pt; 'd' visual top sits closer to the cap than 'e' (ascender),
    # so nearest-y pairing attaches W to darling.
    body = []
    for i, c in enumerate("elcome my darling!"):
        y = 202.0 if c == "d" else 200.0
        body.append(_ch(c, 146.0 + i * 6.0, size=12.5, y=y))
    drop = _ch("W", 102.0, size=33.7, w=38.0, y=181.3, font_id="Trajan")
    stream = body + [drop]
    placed = place_drop_caps_before_continuations(stream)
    text = get_char_unicode_string(placed)
    assert text.startswith("Welcome my darling")
    assert "Wdarling" not in text
    assert "elcome my W" not in text


def test_place_drop_cap_same_line_not_wrapped_and():
    """OA p3 wrap: left-margin 'and' must not steal W from elcome."""
    from babeldoc.format.pdf.document_il.utils.drop_cap import (
        place_drop_caps_before_continuations,
    )

    line1 = [
        _ch(c, 146.0 + i * 6.0, size=12.5, y=200.0)
        for i, c in enumerate("elcome my darling!")
    ]
    line2 = [
        _ch(c, 102.0 + i * 6.0, size=12.5, y=180.0)
        for i, c in enumerate("ins and outs of")
    ]
    drop = _ch("W", 102.0, size=33.7, w=38.0, y=200.0, font_id="Trajan")
    stream = line1 + line2 + [drop]
    placed = place_drop_caps_before_continuations(stream)
    text = get_char_unicode_string(placed)
    assert text.startswith("Welcome my darling")
    assert "Wand" not in text


def test_style_markers_do_not_skip_drop_cap_prep():
    """OA p3: ILTranslator wraps Trajan W as 〖B0〗; prep must still rejoin.

    get_char_unicode_string used to skip climb+drop-cap whenever the list
    mixed PdfCharacters with marker strings, so MT saw
    ``elcome … 〖B0〗W 〖/B0〗`` instead of ``Welcome``.
    """
    body = [
        _ch(c, 146.0 + i * 6.0, size=12.5, y=200.0)
        for i, c in enumerate("elcome my darling!")
    ]
    drop = _ch("W", 102.0, size=33.7, w=38.0, y=181.3, font_id="Trajan")
    mixed: list = [*body, "〖B0〗", drop, "〖/B0〗"]
    text = get_char_unicode_string(mixed)
    stripped = text.replace("〖B0〗", "").replace("〖/B0〗", "")
    assert stripped.startswith("Welcome my darling")
    assert "elcome my W" not in stripped
    assert "Wdarling" not in stripped


def test_drop_cap_padding_spaces_do_not_split_welcome():
    """OA p3 Trajan run is [space, W, space] then elcome — padding is not a word gap."""
    pad_l = _ch(" ", 90.0, size=33.7, w=8.0, y=181.3, font_id="Trajan")
    drop = _ch("W", 102.0, size=33.7, w=38.0, y=181.3, font_id="Trajan")
    pad_r = _ch(" ", 142.0, size=33.7, w=10.0, y=181.3, font_id="Trajan")
    body = [
        _ch(c, 146.0 + i * 6.0, size=12.5, y=200.0)
        for i, c in enumerate("elcome my darling!")
    ]
    mixed: list = ["〖B0〗", pad_l, drop, pad_r, "〖/B0〗", *body]
    text = get_char_unicode_string(mixed)
    stripped = text.replace("〖B0〗", "").replace("〖/B0〗", "")
    assert stripped.startswith("Welcome my darling")
    assert not stripped.startswith("W ")
    assert "W elcome" not in stripped
