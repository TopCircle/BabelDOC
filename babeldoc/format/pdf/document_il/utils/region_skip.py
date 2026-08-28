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


_CHROME_LABELS = frozenset({"abandon", "header", "footer"})

# LayoutParser / AddDebugInformation label stubs: unicode is the layout
# class name and the composition is a debug PdfSameStyleUnicodeCharacters.
_LAYOUT_STUB_UNICODE = frozenset(
    {
        "title",
        "section_header",
        "plain text",
        "tiny text",
        "fallback_line",
        "abandon",
        "figure",
        "figure_text",
        "figure_caption",
        "figure_title",
        "table",
        "table_caption",
        "table_title",
        "table_footnote",
        "table_text",
        "header",
        "footer",
        "seal",
        "formula",
        "isolate_formula",
        "formula_caption",
        "abstract",
        "paragraph_title",
        "content",
        "doc_title",
        "author_info_hybrid",
        "reference",
    }
)


def is_layout_debug_stub(paragraph: PdfParagraph) -> bool:
    """True for LayoutParser / AddDebugInformation label stub paragraphs.

    Stubs carry the layout class name as their unicode (e.g. "fallback_line",
    "title") and/or a debug ``PdfSameStyleUnicodeCharacters`` composition.
    They are diagnostic boxes, not real content: they must not create
    exclusion zones nor participate in title→body gap cascades.

    ``xobj_id`` is deliberately NOT used — page-level paragraphs and tests
    use -1 for real content too.
    """
    uni = (getattr(paragraph, "unicode", None) or "").strip()
    if uni in _LAYOUT_STUB_UNICODE:
        return True
    # ParagraphFinder can glue stub rows into "fallback_linefallback_line…"
    if uni and not uni.replace("fallback_line", "").strip():
        return True
    # AddDebugInformation labels ("paragraph[abc12]-[title]", "pagenumber: 19")
    # — the debug composition may already be replaced by rendered chars by
    # the time vertical-gap/overlap passes run, so the unicode pattern is the
    # surviving signal.
    if re.match(r"^(?:paragraph\[|pagenumber[: ])", uni):
        return True
    for comp in getattr(paragraph, "pdf_paragraph_composition", None) or []:
        ss = comp.pdf_same_style_unicode_characters
        if ss is not None and getattr(ss, "debug_info", False):
            return True
    return False


def is_chrome_paragraph(
    paragraph: PdfParagraph,
    page: Page | None = None,
) -> bool:
    """True for site chrome that is never MT'd and must never be moved by
    layout passes (header/footer skip, URL, page number, abandon labels).

    ``enforce_title_body_gaps`` / post-typesetting overlap fixing shift whole
    follower chains; without this guard a skipped footer/header gets dragged
    off-page (OA p19 footer moved to PDF y=-56).

    Composes the canonical helpers so band rules cannot diverge:
    ``is_url_site_chrome`` and ``is_bare_page_number_chrome``.
    """
    label = (getattr(paragraph, "layout_label", None) or "").strip().lower()
    if label in _CHROME_LABELS:
        return True
    if is_url_site_chrome(paragraph):
        return True
    if page is not None and is_bare_page_number_chrome(paragraph, page):
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
