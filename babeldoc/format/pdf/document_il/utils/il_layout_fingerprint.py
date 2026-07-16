"""Stable **geometry** fingerprint of a post-typeset Document IL.

Refactor gate (architecture K14): behavior-preserving moves must keep the
same fingerprint. Intentionally **does not** hash character unicode — so
FixedMap / DeepLX text changes do not invalidate a geometry-only gate.

Coverage: positioned chars under ``pdf_character`` / ``pdf_same_style_characters``
/ ``pdf_line`` only. Formula-only and unicode-only runs without boxes are
skipped (document if expanding later).

Rules:
- Only characters with a valid box
- Boxes rounded to **3 decimal places**
- Pages / paragraphs sorted by page_number, debug_id, then geometry
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
    return (
        getattr(box, "x", None) is not None
        and getattr(box, "y", None) is not None
        and getattr(box, "x2", None) is not None
        and getattr(box, "y2", None) is not None
    )


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


def il_layout_fingerprint(doc: Document) -> str:
    """Return sha256 hex digest of sorted post-typeset **geometry** only."""
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
                    if not _box_valid(b):
                        continue
                    rows.append(
                        f"{page_no}|{debug_id}|"
                        f"{round(b.x, 3)},{round(b.y, 3)},"
                        f"{round(b.x2, 3)},{round(b.y2, 3)}"
                    )
    payload = "\n".join(rows).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
