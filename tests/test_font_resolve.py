"""Shared style font_id resolution (orphan F33, page-stream xobj)."""

from __future__ import annotations

from babeldoc.format.pdf.document_il.il_version_1 import PdfFont
from babeldoc.format.pdf.document_il.utils.font_resolve import PAGE_STREAM_XOBJ_ID
from babeldoc.format.pdf.document_il.utils.font_resolve import (
    make_synthetic_style_probe,
)
from babeldoc.format.pdf.document_il.utils.font_resolve import normalize_xobj_id
from babeldoc.format.pdf.document_il.utils.font_resolve import resolve_style_font
from babeldoc.format.pdf.document_il.utils.font_resolve import (
    resolve_style_font_for_typesetting,
)


def _pdf_font(fid: str, *, bold: bool = False) -> PdfFont:
    return PdfFont(
        name=fid,
        font_id=fid,
        xref_id=1,
        encoding_length=1,
        bold=bold,
        italic=False,
        monospace=False,
        serif=True,
    )


def test_normalize_xobj_id():
    assert normalize_xobj_id(None) == PAGE_STREAM_XOBJ_ID
    assert normalize_xobj_id(-1) == -1
    assert normalize_xobj_id(7) == 7


def test_resolve_xobj_then_page():
    f1 = _pdf_font("F1")
    f2 = _pdf_font("F2", bold=True)
    fonts = {"F1": f1, 7: {"F2": f2}}
    assert resolve_style_font(fonts, "F2", 7) is f2
    assert resolve_style_font(fonts, "F1", 7) is f1  # page after xobj miss
    assert resolve_style_font(fonts, "F33", 7) is None


def test_resolve_does_not_pick_random_page_font():
    """Orphan id must not silently return an unrelated face."""
    fonts = {"F1": _pdf_font("F1", bold=True)}
    assert resolve_style_font(fonts, "F33") is None
    # typesetting uses synthetic with the requested id
    probe = resolve_style_font_for_typesetting(fonts, "F33")
    assert isinstance(probe, PdfFont)
    assert probe.font_id == "F33"
    assert probe.bold is False  # neutral, not F1's bold


def test_resolve_typesetting_returns_real_when_present():
    f1 = _pdf_font("F1")
    assert resolve_style_font_for_typesetting({"F1": f1}, "F1") is f1


def test_synthetic_probe_not_for_embedding():
    p = make_synthetic_style_probe("F33")
    assert p.xref_id == 0
    assert p.font_id == "F33"
