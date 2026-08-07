"""Chapter-name paragraphs in the header band must NOT be skipped.

A "Chapter N + title" line at the top of a page is the chapter name (章节名)
— a title to machine-translate, not chrome to keep English.  The layout
parser labels it ``title``/``section_header``, and ``is_header_chrome_exempt``
sends it to MT (correct).  There is deliberately NO running-header predicate
in ``region_skip``: keeping it English produced p82 "Chapter9直接卷曲" style
half-translated headers, and the residue is instead cleaned on the MT output
side (``ILTranslator.fix_untranslated_chapter_markers``).

Only real chrome (labels in ``_CHROME_LABELS``) inside the band is skipped.
"""

from __future__ import annotations

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import Cropbox
from babeldoc.format.pdf.document_il.il_version_1 import Page
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
from babeldoc.format.pdf.document_il.utils.region_skip import (
    classify_header_footer_skip,
)

PAGE_W = 612.0
PAGE_H = 792.0


def _page() -> Page:
    return Page(
        page_number=82,
        cropbox=Cropbox(box=Box(x=0.0, y=0.0, x2=PAGE_W, y2=PAGE_H)),
        mediabox=Cropbox(box=Box(x=0.0, y=0.0, x2=PAGE_W, y2=PAGE_H)),
    )


def _para(
    text: str,
    label: str = "title",
    *,
    y: float = 668.6,
    y2: float = 687.4,
    font_size: float = 13.4,
) -> PdfParagraph:
    return PdfParagraph(
        unicode=text,
        layout_label=label,
        pdf_style=PdfStyle(font_id="base", font_size=font_size, graphic_state=None),
        box=Box(x=42.96, y=y, x2=249.5, y2=y2),
    )


class TestChapterNameNotSkipped:
    def test_p82_chapter_name_in_band_goes_to_mt(self):
        # p82 "Chapter 9 the dIrect curL" (title label, in band) is the
        # chapter name — must be translated (第九章 直接卷曲), not kept EN.
        page = _page()
        para = _para("Chapter 9 the dIrect curL")
        assert (
            classify_header_footer_skip(
                page,
                para,
                skip_header=True,
                skip_footer=True,
                header_height=160.0,
                footer_height=70.0,
            )
            is None
        )

    def test_p19_chapter_name_in_band_goes_to_mt(self):
        # p19 merged "be an actIon Man Chapter 3" (title-first, 15pt) must
        # also be translated — both pages behave consistently.
        page = _page()
        para = _para(
            "be an actIon Man Chapter 3", y=670.4, y2=685.4, font_size=15.0
        )
        assert (
            classify_header_footer_skip(
                page,
                para,
                skip_header=True,
                skip_footer=True,
                header_height=160.0,
                footer_height=70.0,
            )
            is None
        )

    def test_body_chapter_heading_out_of_band_goes_to_mt(self):
        page = _page()
        para = _para("Chapter 3", y=420.0, y2=440.0, font_size=32.0)
        assert (
            classify_header_footer_skip(
                page,
                para,
                skip_header=True,
                skip_footer=True,
                header_height=160.0,
                footer_height=70.0,
            )
            is None
        )

    def test_not_skipped_when_skip_header_off(self):
        page = _page()
        para = _para("Chapter 9 the dIrect curL")
        assert (
            classify_header_footer_skip(
                page,
                para,
                skip_header=False,
                skip_footer=True,
                header_height=160.0,
                footer_height=70.0,
            )
            is None
        )


class TestRealChromeStillSkipped:
    def test_chrome_header_still_skipped(self):
        page = _page()
        chrome = _para("Learn The Trigasm Basics", label="abandon", font_size=13.0)
        assert (
            classify_header_footer_skip(
                page,
                chrome,
                skip_header=True,
                skip_footer=True,
                header_height=160.0,
                footer_height=70.0,
            )
            == "header"
        )

    def test_footer_chrome_still_skipped(self):
        # URL chrome is classified url_chrome (not footer) but still skipped.
        page = _page()
        footer = _para("www.GabrielleMoore.com", label="abandon", y=38.6, y2=52.2)
        assert (
            classify_header_footer_skip(
                page,
                footer,
                skip_header=True,
                skip_footer=True,
                header_height=160.0,
                footer_height=70.0,
            )
            in ("footer", "url_chrome")
        )
