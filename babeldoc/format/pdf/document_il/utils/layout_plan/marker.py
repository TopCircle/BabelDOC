"""First-glyph marker on a source block. This does not choose a strategy."""

from __future__ import annotations

from babeldoc.format.pdf.document_il.utils.layout_helper import is_bullet_point
from babeldoc.format.pdf.document_il.utils.layout_plan.model import MarkerEvidence


class _Style:
    def __init__(self, font_id: str) -> None:
        self.font_id = font_id


class _Glyph:
    """Enough of a character for ``is_bullet_point``."""

    def __init__(self, text: str, font: str) -> None:
        self.char_unicode = text
        self.pdf_style = _Style(font)


def marker_from_glyph(text: str | None, font: str | None) -> MarkerEvidence:
    """Record the first glyph. The bullet test sees the whole span.

    ``is_bullet_point`` treats a dingbat face as a bullet only when the span
    is empty or a single non-space glyph. Slicing to one character first would
    mark a multi-character dingbat run as a bullet.
    """
    raw = text or ""
    face = font or ""
    glyph = next((char for char in raw if not char.isspace()), "")
    return MarkerEvidence(
        text=glyph,
        font=face,
        is_bullet=bool(is_bullet_point(_Glyph(raw.strip(), face))),
    )


def first_marker(lines: list[dict]) -> MarkerEvidence | None:
    """First glyph in block order, including an empty ToUnicode dingbat."""
    for line in lines:
        for span in line.get("spans") or []:
            text = span.get("text") or ""
            evidence = marker_from_glyph(text, span.get("font") or "")
            if text.strip() or evidence.is_bullet:
                return evidence
    return None
