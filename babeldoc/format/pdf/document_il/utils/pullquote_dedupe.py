"""Skip MT for pull-quote callouts that duplicate body quote text.

Ebook layouts (Day6 TIP2) put the same sentence in the body and a side
callout.  Translating both independently doubles DeepLX damage and wastes
quota.  If the callout's alphanumeric skeleton is contained in a longer
same-page paragraph, skip translating the callout.

**Product note:** skip keeps the callout in the *source language* (usually
EN).  It does not copy the body ZH translation onto the side panel.  Mono
pages therefore show ZH body + EN callout for those duplicates — a
deliberate lightweight tradeoff, not full bilingual callout sync.

Owns only the near-duplicate test; callers decide skip policy.

Geometry thresholds (``width_ratio < 0.55``, ``left_ratio > 0.35``) match
Day6-style right callouts (~x=360 on letter); they are not universal.
"""

from __future__ import annotations

import re

from babeldoc.format.pdf.document_il.il_version_1 import Page
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph

_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize_for_dup(text: str | None) -> str:
    """Lowercase alnum-only skeleton for containment checks."""
    if not text:
        return ""
    return _ALNUM.sub("", text.lower())


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
    # Narrow band on the right half (Day6 callout ~x=360, w~200 on 612)
    left_ratio = (box.x - page_box.x) / page_width
    width_ratio = para_width / page_width
    if width_ratio < 0.55 and left_ratio > 0.35:
        return True
    # Fallback: layout_helper quote heuristic
    try:
        from babeldoc.format.pdf.document_il.utils.layout_helper import (
            is_quote_block,
        )

        return is_quote_block(paragraph, page_width)
    except Exception:
        return False
