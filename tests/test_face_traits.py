"""Token-boundary face trait inference (review B2 anti-false-positives)."""

from __future__ import annotations

from babeldoc.format.pdf.document_il.utils.face_traits import font_name_tokens
from babeldoc.format.pdf.document_il.utils.face_traits import (
    infer_face_traits_from_name,
)
from babeldoc.format.pdf.document_il.utils.face_traits import normalize_ps_font_name


def test_tokens_split_camel_and_subset():
    assert font_name_tokens("AAAA+MyriadPro-Light") == frozenset(
        {"myriad", "pro", "light"}
    )
    assert "mono" not in font_name_tokens("MonotypeCorsiva")
    assert "corsiva" in font_name_tokens("MonotypeCorsiva")


def test_cardinal_not_din_sans():
    """Substring ``din`` in Cardinal must not force sans."""
    b, i, m, s = infer_face_traits_from_name(
        "Cardinal", bold=False, italic=False, monospaced=False, serif=True
    )
    assert s is True
    assert m is False
    assert b is False


def test_garamond_condensed_stays_serif():
    b, i, m, s = infer_face_traits_from_name(
        "Garamond-Condensed",
        bold=False,
        italic=False,
        monospaced=False,
        serif=True,
    )
    assert s is True


def test_monotype_not_mono():
    b, i, m, s = infer_face_traits_from_name(
        "MonotypeCorsiva",
        bold=False,
        italic=False,
        monospaced=False,
        serif=True,
    )
    assert m is False


def test_academic_not_demi_bold():
    b, i, m, s = infer_face_traits_from_name(
        "Academic", bold=False, italic=False, monospaced=False, serif=True
    )
    assert b is False


def test_oa_faces_positive():
    _, _, _, s = infer_face_traits_from_name(
        "MyriadPro-Light", bold=False, italic=False, monospaced=False, serif=True
    )
    assert s is False
    b, _, _, s = infer_face_traits_from_name(
        "TrajanPro-Regular", bold=False, italic=False, monospaced=False, serif=True
    )
    assert s is True and b is True  # display bold
    b, _, _, s = infer_face_traits_from_name(
        "MicrostyleATT", bold=False, italic=False, monospaced=False, serif=True
    )
    assert s is False and b is True


def test_prefer_display_bold_off():
    b, _, _, s = infer_face_traits_from_name(
        "TrajanPro-Regular",
        bold=False,
        italic=False,
        monospaced=False,
        serif=True,
        prefer_display_bold=False,
    )
    assert s is True and b is False


def test_normalize_ps_strips_subset():
    assert normalize_ps_font_name("ABC+Times-Bold") == "timesbold"
