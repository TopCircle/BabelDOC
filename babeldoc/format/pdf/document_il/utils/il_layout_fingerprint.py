"""Stable geometry fingerprint of a post-typeset Document IL.

Used as a **refactor gate**: behavior-preserving moves (extract modules,
rename, reorder pure helpers) must keep the same fingerprint. Quality PRs
that intentionally change layout update golden fingerprints deliberately.

Rules (architecture plan K14 / Phase 0b):
- Only **positioned** composition characters with a valid box
- Boxes rounded to **3 decimal places**
- Paragraphs sorted by ``debug_id`` then geometry
- Do **not** hash full paragraph unicode or runtime-only fields
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from babeldoc.format.pdf.document_il.il_version_1 import Document
    from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter
    from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraphComposition


def _box_valid(box) -> bool:
    if box is None:
        return False
    try:
        return all(
            getattr(box, attr) is not None for attr in ("x", "y", "x2", "y2")
        )
    except Exception:
        return False


def _iter_positioned_chars(
    composition: PdfParagraphComposition,
) -> Iterator[PdfCharacter]:
    """Yield characters that carry a usable box after typesetting."""
    if composition.pdf_character is not None:
        ch = composition.pdf_character
        if _box_valid(ch.box):
            yield ch
        return

    if composition.pdf_same_style_characters is not None:
        for ch in composition.pdf_same_style_characters.pdf_character or []:
            if _box_valid(ch.box):
                yield ch
        return

    if composition.pdf_line is not None:
        for ch in composition.pdf_line.pdf_character or []:
            if _box_valid(ch.box):
                yield ch
        return

    # Formulas / unicode-only style runs: no stable box → skip for fingerprint


def il_layout_fingerprint(doc: Document) -> str:
    """Return sha256 hex digest of sorted post-typeset char geometry."""
    rows: list[str] = []
    pages = sorted(doc.page or [], key=lambda p: p.page_number or 0)
    for page in pages:
        page_no = page.page_number if page.page_number is not None else -1
        paras = sorted(
            page.pdf_paragraph or [],
            key=lambda p: (
                p.debug_id or "",
                p.box.y2 if p.box and p.box.y2 is not None else 0.0,
                p.box.x if p.box and p.box.x is not None else 0.0,
            ),
        )
        for para in paras:
            debug_id = para.debug_id or ""
            for comp in para.pdf_paragraph_composition or []:
                for ch in _iter_positioned_chars(comp):
                    b = ch.box
                    assert b is not None
                    rows.append(
                        f"{page_no}|{debug_id}|"
                        f"{round(b.x, 3)},{round(b.y, 3)},"
                        f"{round(b.x2, 3)},{round(b.y2, 3)}|"
                        f"{ch.char_unicode or ''}"
                    )
    payload = "\n".join(rows).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
