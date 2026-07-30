"""Safer header/footer skip bounds (PR-C2) + always-on site chrome skip.

Shared by ``ILTranslator`` and ``ParagraphFinder`` so white-fill and MT skip
cannot drift.

URL / bare page-number chrome: always exclude from MT; source spans stay
visible (not deleted from the PDF).
"""

from __future__ import annotations

import re

from babeldoc.format.pdf.document_il.il_version_1 import Page
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph

# Bare site chrome — never machine-translate (leave EN visible).
_URL_CHROME_RE = re.compile(
    r"^(?:https?://|www\.)\S+$",
    re.IGNORECASE,
)
# Bare page number only (running footer digits).
_PAGE_NUM_ONLY_RE = re.compile(r"^\d{1,3}$")
# Fallback band when config heights are not applied to chrome-only checks.
_CHROME_BAND_FALLBACK_PT = 48.0

HEADER_EXEMPT_LABELS = frozenset(
    {
        "title",
        "section_header",
    }
)

BODY_LAYOUT_LABELS = frozenset(
    {
        "",
        "plain text",
        "text",
        "paragraph",
        "paragraph_hybrid",
    }
)

HEADER_BODY_MIN_CHARS = 48
HEADER_BODY_MIN_HEIGHT_PT = 28.0
HEADER_BODY_MIN_CHARS_TALL = 24


def _page_crop_box(page: Page | None):
    if page is None:
        return None
    cb = getattr(page, "cropbox", None) or getattr(page, "mediabox", None)
    if cb is None:
        return None
    if hasattr(cb, "box") and cb.box is not None:
        return cb.box
    if getattr(cb, "x", None) is not None and getattr(cb, "y2", None) is not None:
        return cb
    return None


def is_header_chrome_exempt(paragraph: PdfParagraph) -> bool:
    """True when paragraph must never be treated as header/footer chrome."""
    label = (getattr(paragraph, "layout_label", None) or "").strip().lower()
    if label in HEADER_EXEMPT_LABELS:
        return True
    text = (getattr(paragraph, "unicode", None) or "").strip()
    if not text:
        return False
    if label not in BODY_LAYOUT_LABELS:
        return False
    if len(text) >= HEADER_BODY_MIN_CHARS:
        return True
    box = getattr(paragraph, "box", None)
    if (
        box is not None
        and box.y is not None
        and box.y2 is not None
        and (float(box.y2) - float(box.y)) >= HEADER_BODY_MIN_HEIGHT_PT
        and len(text) >= HEADER_BODY_MIN_CHARS_TALL
    ):
        return True
    return False


def in_header_band(
    page: Page,
    paragraph: PdfParagraph,
    *,
    header_height: float,
) -> bool:
    """True when the paragraph box lies fully inside the top header strip."""
    page_box = _page_crop_box(page)
    box = getattr(paragraph, "box", None)
    if page_box is None or box is None:
        return False
    page_top = page_box.y2
    paragraph_bottom = box.y
    if page_top is None or paragraph_bottom is None:
        return False
    return float(paragraph_bottom) >= float(page_top) - float(header_height)


def in_footer_band(
    page: Page,
    paragraph: PdfParagraph,
    *,
    footer_height: float,
) -> bool:
    """True when the paragraph box lies fully inside the bottom footer strip."""
    page_box = _page_crop_box(page)
    box = getattr(paragraph, "box", None)
    if page_box is None or box is None:
        return False
    page_bottom = page_box.y
    paragraph_top = box.y2
    if page_bottom is None or paragraph_top is None:
        return False
    return float(paragraph_top) <= float(page_bottom) + float(footer_height)


def is_url_site_chrome(paragraph: PdfParagraph) -> bool:
    """True for bare URL / www. host lines (keep EN, skip MT)."""
    text = (getattr(paragraph, "unicode", None) or "").strip()
    if not text or len(text) > 80:
        return False
    return bool(_URL_CHROME_RE.match(text))


def is_bare_page_number_chrome(
    paragraph: PdfParagraph,
    page: Page | None = None,
    *,
    header_height: float = _CHROME_BAND_FALLBACK_PT,
    footer_height: float = _CHROME_BAND_FALLBACK_PT,
) -> bool:
    """True for a lone 1–3 digit page number in the footer/header band."""
    text = (getattr(paragraph, "unicode", None) or "").strip()
    if not _PAGE_NUM_ONLY_RE.match(text):
        return False
    if page is None:
        return False
    if in_footer_band(page, paragraph, footer_height=footer_height):
        return True
    if in_header_band(page, paragraph, header_height=header_height):
        return True
    return False


def classify_header_footer_skip(
    page: Page,
    paragraph: PdfParagraph,
    *,
    skip_header: bool,
    skip_footer: bool,
    header_height: float,
    footer_height: float,
    ocr_workaround: bool = False,
) -> str | None:
    """Single decision point: skip reason code or None.

    Reasons: ``url_chrome`` | ``page_number`` | ``header`` | ``footer``.
    """
    if is_url_site_chrome(paragraph):
        return "url_chrome"
    if is_bare_page_number_chrome(
        paragraph,
        page,
        header_height=header_height or _CHROME_BAND_FALLBACK_PT,
        footer_height=footer_height or _CHROME_BAND_FALLBACK_PT,
    ):
        return "page_number"

    if is_header_chrome_exempt(paragraph):
        return None
    if ocr_workaround:
        return None
    if not (skip_header or skip_footer):
        return None
    if not getattr(paragraph, "box", None):
        return None

    if skip_header and in_header_band(
        page, paragraph, header_height=header_height
    ):
        return "header"
    if skip_footer and in_footer_band(
        page, paragraph, footer_height=footer_height
    ):
        return "footer"
    return None


def should_skip_header_footer(
    page: Page,
    paragraph: PdfParagraph,
    *,
    skip_header: bool,
    skip_footer: bool,
    header_height: float,
    footer_height: float,
    ocr_workaround: bool = False,
) -> bool:
    """Whether to skip MT for header/footer/site chrome."""
    return (
        classify_header_footer_skip(
            page,
            paragraph,
            skip_header=skip_header,
            skip_footer=skip_footer,
            header_height=header_height,
            footer_height=footer_height,
            ocr_workaround=ocr_workaround,
        )
        is not None
    )
