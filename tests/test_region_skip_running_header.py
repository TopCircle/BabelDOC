"""Running header "Chapter N + title" stays EN (acceptance V5).

p82 regression: the layout parser labels the running header ``title``, which
``is_header_chrome_exempt`` would exempt from the header skip — the whole
header then went to MT and came back "Chapter9直接卷曲" instead of the EN
"Chapter 9 the dIrect curL". The running-header predicate must override that
exemption whenever the "Chapter N + title" paragraph sits in the header band.
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
from babeldoc.format.pdf.document_il.utils.region_skip import is_running_header
from babeldoc.format.pdf.document_il.utils.region_skip import (
    is_running_header_in_band,
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
    y: float = 668.0,
    y2: float = 687.4,
    x: float = 42.96,
    x2: float = 249.5,
    font_size: float = 15.0,
) -> PdfParagraph:
    return PdfParagraph(
        unicode=text,
        layout_label=label,
        pdf_style=PdfStyle(font_id="base", font_size=font_size, graphic_state=None),
        box=Box(x=x, y=y, x2=x2, y2=y2),
    )


class TestIsRunningHeader:
    def test_chapter_opener_title_in_band_not_running_header(self):
        # p19: the real 32pt "Chapter 3" title sits inside the header band but
        # must still be machine-translated (第三章), not kept EN.
        page = _page()
        para = _para("Chapter 3", y=660.0, y2=693.5, font_size=32.0)
        assert is_running_header(para)
        assert is_running_header_in_band(page, para, header_height=160.0) is False
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

    def test_running_header_without_font_size_not_classified(self):
        # Unknown font size: safe default is to NOT skip (never regress a real
        # chapter title); real running headers always carry a size in IL.
        page = _page()
        para = _para("Chapter 9 the dIrect curL", font_size=None)
        assert is_running_header_in_band(page, para, header_height=160.0) is False

    def test_chapter_number_title(self):
        assert is_running_header(_para("Chapter 9 the dIrect curL"))
        assert is_running_header(_para("Chapter9 the dIrect curL"))
        assert is_running_header(_para("chapter 3 Rules of Attraction"))
        assert is_running_header(_para("Chapter 19"))

    def test_not_running_header(self):
        assert not is_running_header(_para(""))
        assert not is_running_header(_para("ORGASMIC ADDICTION"))
        assert not is_running_header(_para("The dIrect curL"))
        assert not is_running_header(_para("19"))
        assert not is_running_header(_para("Chapter the dIrect curL"))

    def test_in_band_p82(self):
        page = _page()
        para = _para("Chapter 9 the dIrect curL")
        assert is_running_header_in_band(page, para, header_height=160.0) is True

    def test_body_chapter_heading_out_of_band(self):
        # A real "Chapter 3" section heading in the body (below the band) must
        # NOT be treated as a running header (it must still be translated).
        page = _page()
        para = _para("Chapter 3", y=420.0, y2=440.0)
        assert is_running_header_in_band(page, para, header_height=160.0) is False


class TestClassifyRunningHeader:
    def test_title_label_running_header_skipped(self):
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
            == "header"
        )

    def test_section_header_label_running_header_skipped(self):
        # p82's running header is labelled "title" by the parser; other books
        # may use "section_header" — both must stay EN.
        page = _page()
        para = _para("Chapter 9 the dIrect curL", label="section_header")
        assert (
            classify_header_footer_skip(
                page,
                para,
                skip_header=True,
                skip_footer=True,
                header_height=160.0,
                footer_height=70.0,
            )
            == "header"
        )

    def test_plain_label_running_header_skipped(self):
        page = _page()
        para = _para("Chapter 9 the dIrect curL", label="plain text")
        assert (
            classify_header_footer_skip(
                page,
                para,
                skip_header=True,
                skip_footer=True,
                header_height=160.0,
                footer_height=70.0,
            )
            == "header"
        )

    def test_body_chapter_heading_not_skipped(self):
        # "Chapter 3" heading in the body must still be MT'd (map: 第三章).
        page = _page()
        para = _para("Chapter 3", y=420.0, y2=440.0)
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
