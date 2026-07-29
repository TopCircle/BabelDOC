"""Resolve style font_id against the page/xobj font map without KeyError.

Used by ``remove_descent`` (optional hit) and ``typesetting`` (must return a
style probe for FontMapper).  Orphan ids (e.g. F33 not in ``page.pdf_font``)
must not abort the job.
"""

from __future__ import annotations

import logging
from typing import Any

from babeldoc.format.pdf.document_il import il_version_1

logger = logging.getLogger(__name__)

# Page content stream — same convention as layout_parser / il_translator.
PAGE_STREAM_XOBJ_ID = -1

# Synthetic probes are not embedded; FontMapper.map only reads style flags.
_SYNTHETIC_XREF_ID = 0


def normalize_xobj_id(xobj_id: int | None) -> int:
    """Map None (page-level paragraph) to PAGE_STREAM_XOBJ_ID."""
    return PAGE_STREAM_XOBJ_ID if xobj_id is None else xobj_id


def resolve_style_font(
    fonts: dict[str | int, Any],
    font_id: str | None,
    xobj_id: int | None = None,
) -> il_version_1.PdfFont | None:
    """Look up *font_id* in the typesetting font map.

    Order:
      1. XObject-local ``dict[str, PdfFont]`` when *xobj_id* is present
      2. Page-level entry if it is a ``PdfFont`` (not an xobj dict / mupdf Font)

    Returns None when missing — callers decide synthetic / skip.
    Does **not** pick a random page font (that silently wrong-styles glyphs).
    """
    if not font_id:
        return None

    # 1) XObject-local map
    if xobj_id is not None and xobj_id in fonts:
        font_map = fonts[xobj_id]
        if isinstance(font_map, dict) and font_id in font_map:
            hit = font_map[font_id]
            if isinstance(hit, il_version_1.PdfFont):
                return hit

    # 2) Page-level PdfFont only (skip xobj dicts and pymupdf.Font injects)
    hit = fonts.get(font_id)
    if isinstance(hit, il_version_1.PdfFont):
        return hit

    return None


def make_synthetic_style_probe(font_id: str | None) -> il_version_1.PdfFont:
    """Neutral PdfFont for FontMapper when the real face is missing.

    Not for embedding (xref_id is a sentinel). map() only needs bold/serif.
    """
    fid = font_id or "base"
    return il_version_1.PdfFont(
        name=fid,
        font_id=fid,
        xref_id=_SYNTHETIC_XREF_ID,
        encoding_length=2,
        bold=False,
        italic=False,
        monospace=False,
        serif=True,
    )


def resolve_style_font_for_typesetting(
    fonts: dict[str | int, Any],
    font_id: str | None,
    xobj_id: int | None = None,
) -> il_version_1.PdfFont | Any:
    """Typesetting path: PdfFont, exact pymupdf inject, or synthetic probe.

    Never raises KeyError. Does not pick a random page face.
    FontMapper.map accepts both PdfFont and pymupdf.Font.
    """
    hit = resolve_style_font(fonts, font_id, xobj_id)
    if hit is not None:
        return hit

    # Exact BabelDOC inject (fontid2font) — not a random page font
    raw = fonts.get(font_id) if font_id else None
    if raw is not None and not isinstance(raw, dict) and not isinstance(
        raw, il_version_1.PdfFont
    ):
        return raw

    logger.warning(
        "typesetting: font_id %r missing (xobj=%s); using synthetic PdfFont",
        font_id,
        xobj_id,
    )
    return make_synthetic_style_probe(font_id)
