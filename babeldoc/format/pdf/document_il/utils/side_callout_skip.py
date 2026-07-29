"""Skip MT for side callouts that should keep the source language.

Two independent reasons to leave a paragraph untranslated:

1. **Pull-quote near-duplicate** (Day6): side band repeats body quote text.
2. **Ultra-narrow tall strip** (Orgasmic Addiction p8): ~80pt figure-adjacent
   column that cannot fit CJK after translation even with box expansion.

**Product note:** skip keeps the callout in the *source language* (usually
EN).  Mono pages therefore show ZH body + EN callout — a deliberate
lightweight tradeoff, not full bilingual callout sync.

``should_skip_side_callout_mt`` is the single call-site entry for
``ILTranslator``.  Geometry helpers live here so ``pullquote_dedupe`` can
stay a thin compatibility re-export.
"""

from __future__ import annotations

import re

from babeldoc.format.pdf.document_il.il_version_1 import Page
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph

_ALNUM = re.compile(r"[^a-z0-9]+")

# Day6-style right callout (~x=360, w~200 on letter 612)
_PULLQUOTE_WIDTH_RATIO = 0.55
_PULLQUOTE_LEFT_RATIO = 0.35

# Ultra-narrow side strip (OA p8 red callout ~80pt on 612 ≈ 0.13)
_ULTRA_NARROW_WIDTH_RATIO = 0.18
_ULTRA_NARROW_MIN_HEIGHT_RATIO = 0.9  # tall column, not a single short line
_ULTRA_NARROW_MIN_CHARS = 30
_ULTRA_NARROW_LEFT_RATIO = 0.45  # mostly right-half of the page

# Semantic layout labels only — not engine noise (abandon / fallback_line).
_SKIP_ULTRA_NARROW_LABELS = frozenset({"title", "section_header"})


def normalize_for_dup(text: str | None) -> str:
    """Lowercase alnum-only skeleton for containment checks."""
    if not text:
        return ""
    return _ALNUM.sub("", text.lower())


def _page_box(page: Page):
    """Resolve crop/media box whether stored as ``.box`` wrapper or direct Box."""
    for attr in ("cropbox", "mediabox"):
        cb = getattr(page, attr, None)
        if cb is None:
            continue
        if hasattr(cb, "box") and cb.box is not None:
            return cb.box
        if getattr(cb, "x", None) is not None and getattr(cb, "x2", None) is not None:
            return cb
    return None


def _looks_like_side_callout(paragraph: PdfParagraph, page: Page) -> bool:
    box = getattr(paragraph, "box", None)
    if not box or box.x is None or box.x2 is None:
        return False
    page_box = _page_box(page)
    if page_box is None or page_box.x2 <= page_box.x:
        return False
    page_width = page_box.x2 - page_box.x
    para_width = box.x2 - box.x
    if para_width <= 0:
        return False
    left_ratio = (box.x - page_box.x) / page_width
    width_ratio = para_width / page_width
    if width_ratio < _PULLQUOTE_WIDTH_RATIO and left_ratio > _PULLQUOTE_LEFT_RATIO:
        return True
    try:
        from babeldoc.format.pdf.document_il.utils.layout_helper import (
            is_quote_block,
        )

        return is_quote_block(paragraph, page_width)
    except Exception:
        return False


def is_pullquote_duplicate_of_body(
    paragraph: PdfParagraph,
    page: Page | None,
    *,
    min_quote_chars: int = 40,
) -> bool:
    """True when *paragraph* looks like a side callout of longer body text.

    Conditions:
      1. Paragraph is geometrically a quote/callout (narrow + indented), OR
         its left edge is clearly right of the dominant body column.
      2. Its normalized text is long enough and contained in another
         same-page paragraph's normalized text (strictly longer host).
    """
    if page is None:
        return False
    quote = normalize_for_dup(getattr(paragraph, "unicode", None))
    if len(quote) < min_quote_chars:
        return False

    if not _looks_like_side_callout(paragraph, page):
        return False

    for other in getattr(page, "pdf_paragraph", None) or []:
        if other is paragraph:
            continue
        host = normalize_for_dup(getattr(other, "unicode", None))
        if len(host) <= len(quote):
            continue
        if quote in host:
            return True
    return False


def is_ultra_narrow_side_callout(
    paragraph: PdfParagraph,
    page: Page | None,
) -> bool:
    """True for tall, ultra-narrow side strips that cannot fit CJK.

    Orgasmic Addiction p8: red figure-adjacent callout box ~80×120pt.
    Translating into that box yields a vertical Chinese tower.  Keeping
    the English source preserves the designed layout.

    Does **not** match left-column body text beside a full-bleed photo
    (those have width_ratio ≳ 0.17 but left_ratio low, e.g. x≈100).
    """
    if page is None:
        return False
    label = (getattr(paragraph, "layout_label", None) or "").lower()
    if label in _SKIP_ULTRA_NARROW_LABELS:
        return False
    text = (getattr(paragraph, "unicode", None) or "").strip()
    if len(text) < _ULTRA_NARROW_MIN_CHARS:
        return False
    box = getattr(paragraph, "box", None)
    if not box or box.x is None or box.x2 is None or box.y is None or box.y2 is None:
        return False
    page_box = _page_box(page)
    if page_box is None or page_box.x2 <= page_box.x:
        return False
    page_width = page_box.x2 - page_box.x
    para_w = box.x2 - box.x
    para_h = box.y2 - box.y
    if para_w <= 0 or para_h <= 0:
        return False
    width_ratio = para_w / page_width
    left_ratio = (box.x - page_box.x) / page_width
    if width_ratio >= _ULTRA_NARROW_WIDTH_RATIO:
        return False
    if left_ratio < _ULTRA_NARROW_LEFT_RATIO:
        return False
    if para_h / para_w < _ULTRA_NARROW_MIN_HEIGHT_RATIO:
        return False
    return True


def should_skip_side_callout_mt(
    paragraph: PdfParagraph,
    page: Page | None,
) -> bool:
    """Unified skip: duplicate pull-quote **or** ultra-narrow tall callout."""
    if is_pullquote_duplicate_of_body(paragraph, page):
        return True
    return is_ultra_narrow_side_callout(paragraph, page)
