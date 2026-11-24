"""Tests for bibliography passthrough, spaced style markers, and OCR rendering fixes."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from babeldoc.format.pdf.document_il import Box
from babeldoc.format.pdf.document_il import GraphicState
from babeldoc.format.pdf.document_il import PdfCharacter
from babeldoc.format.pdf.document_il import PdfFont
from babeldoc.format.pdf.document_il import PdfParagraph
from babeldoc.format.pdf.document_il import PdfParagraphComposition
from babeldoc.format.pdf.document_il import PdfRectangle
from babeldoc.format.pdf.document_il import PdfStyle
from babeldoc.format.pdf.document_il.midend.detect_scanned_file import DetectScannedFile
from babeldoc.format.pdf.document_il.midend.detect_scanned_file import ScannedPDFError
from babeldoc.format.pdf.document_il.midend.il_translator import ILTranslator
from babeldoc.format.pdf.document_il.midend.il_translator import TitleContextSnapshot
from babeldoc.format.pdf.document_il.midend.typesetting import Typesetting


def _para(text: str, layout_label: str = "text") -> SimpleNamespace:
    return SimpleNamespace(unicode=text, layout_label=layout_label)


class TestBibliographyParagraphDetection:
    def test_exact_headers_and_footers_are_not_treated_as_entries(self):
        title = TitleContextSnapshot(
            debug_id="t1", unicode="References", page_number=40
        )
        assert (
            ILTranslator._is_bibliography_paragraph(
                _para("References", "title"), title, page_number=40
            )
            is False
        )
        assert (
            ILTranslator._is_bibliography_paragraph(
                _para("Bibliography", "text"), title, page_number=40
            )
            is False
        )
        assert (
            ILTranslator._is_bibliography_paragraph(
                _para("Table of Contents", "text"), title, page_number=40
            )
            is False
        )
        assert (
            ILTranslator._is_bibliography_paragraph(
                _para("www.GabrielleMoore.com", "abandon"), title, page_number=40
            )
            is False
        )
        assert (
            ILTranslator._is_bibliography_paragraph(
                _para("Copyright © 2016 Insspira Publishing Inc.", "text"),
                None,
                page_number=3,
            )
            is False
        )

    def test_content_under_references_section_is_preserved_and_bounded(self):
        title = TitleContextSnapshot(
            debug_id="t1", unicode="References", page_number=40
        )
        assert (
            ILTranslator._is_bibliography_paragraph(
                _para("Komisaruk, B. R., Whipple, B."),
                local_title=title,
                page_number=41,
            )
            is True
        )
        assert (
            ILTranslator._is_bibliography_paragraph(
                _para("Subheading inside references", layout_label="title"),
                local_title=title,
                page_number=41,
            )
            is False
        )
        # Multi-volume anthology: References on page 40 must not leak to body on page 60
        assert (
            ILTranslator._is_bibliography_paragraph(
                _para("1. Direct: Place your fingers gently and maintain steady rhythm."),
                local_title=title,
                page_number=60,
            )
            is False
        )
        assert (
            ILTranslator._is_bibliography_paragraph(
                _para("It might make you feel better to learn a few facts about massage."),
                local_title=title,
                page_number=60,
            )
            is False
        )

    def test_numbered_and_author_year_citations_detected(self):
        assert (
            ILTranslator._is_bibliography_paragraph(
                _para("4. Cox, Tracey. Superflirt. DK Publishing, 2003.")
            )
            is True
        )
        assert (
            ILTranslator._is_bibliography_paragraph(
                _para("44. https://example.com/some-study-reference")
            )
            is True
        )
        assert (
            ILTranslator._is_bibliography_paragraph(
                _para("Chalker, R. (2000). The Clitoral Truth. Seven Stories Press.")
            )
            is True
        )
        assert (
            ILTranslator._is_bibliography_paragraph(
                _para(
                    "Gabrielle Moore Fire Breath Energy Orgasms <http://www.GabrielleMoore.com/tantric-sex/part-two/> Last accessed 8th Feb 2016."
                )
            )
            is True
        )
        assert (
            ILTranslator._is_bibliography_paragraph(
                _para("[12]Masters, W. H. Human Sexual Response.")
            )
            is False
        )
        assert (
            ILTranslator._is_bibliography_paragraph(
                _para("[12] Masters, W. H. Human Sexual Response.")
            )
            is True
        )

    def test_normal_prose_with_years_and_keywords_is_not_skipped(self):
        assert (
            ILTranslator._is_bibliography_paragraph(
                _para("1. Place your hands gently on her shoulders and breathe slowly.")
            )
            is False
        )
        assert (
            ILTranslator._is_bibliography_paragraph(
                _para(
                    "In a 2006 survey, researchers Found that 82% of young Female participants reported arousal."
                )
            )
            is False
        )
        assert (
            ILTranslator._is_bibliography_paragraph(
                _para(
                    "in a 2011 CNN Health report, sex counselor and bestselling author shared tips."
                )
            )
            is False
        )


class TestSpacedStyleMarkerSanitization:
    def test_spaced_rich_text_marker_is_stripped(self):
        cleaned = ILTranslator._strip_style_markers("兴奋 〖 /B1 〗 以及高潮的强度")
        assert cleaned == "兴奋  以及高潮的强度"
        assert ILTranslator._RICH_TEXT_MARKER_RE.sub("", "〖 B0 〗标题〖 /B0 〗") == "标题"


class TestDetectScannedFileBypass:
    def test_skip_scanned_detection_flag_returns_early(self):
        cfg = MagicMock()
        cfg.skip_scanned_detection = True
        detector = DetectScannedFile(cfg)
        docs = SimpleNamespace(page=[])
        detector.process(docs, "dummy.pdf", {})
        cfg.get_working_file_path.assert_not_called()

    def test_ocr_text_layer_bypasses_scanned_error(self, tmp_path):
        import pymupdf

        pdf_path = tmp_path / "ocr.pdf"
        doc = pymupdf.open()
        for _ in range(5):
            doc.new_page()
        doc.save(pdf_path)
        doc.close()

        cfg = MagicMock()
        cfg.primary_font_family = None
        cfg.skip_scanned_detection = False
        cfg.auto_enable_ocr_workaround = False
        cfg.should_translate_page.return_value = True
        cfg.get_working_file_path.return_value = str(pdf_path)
        cfg.progress_monitor.stage_start.return_value.__enter__ = MagicMock(
            return_value=MagicMock()
        )
        cfg.progress_monitor.stage_start.return_value.__exit__ = MagicMock(
            return_value=False
        )

        detector = DetectScannedFile(cfg)
        pages = [
            SimpleNamespace(page_number=i, pdf_character=[object()] * 50)
            for i in range(5)
        ]
        docs = SimpleNamespace(page=pages)

        with (
            patch(
                "babeldoc.format.pdf.document_il.midend.detect_scanned_file.PDFCreater"
            ),
            patch.object(
                detector, "detect_page_is_scanned", return_value=True
            ) as mock_detect,
        ):
            detector.process(docs, str(pdf_path), {})
            assert mock_detect.call_count == 4

    def test_pure_scanned_pdf_still_raises_when_few_chars(self, tmp_path):
        import pymupdf

        pdf_path = tmp_path / "scan.pdf"
        doc = pymupdf.open()
        for _ in range(5):
            doc.new_page()
        doc.save(pdf_path)
        doc.close()

        cfg = MagicMock()
        cfg.primary_font_family = None
        cfg.skip_scanned_detection = False
        cfg.auto_enable_ocr_workaround = False
        cfg.should_translate_page.return_value = True
        cfg.get_working_file_path.return_value = str(pdf_path)
        cfg.progress_monitor.stage_start.return_value.__enter__ = MagicMock(
            return_value=MagicMock()
        )
        cfg.progress_monitor.stage_start.return_value.__exit__ = MagicMock(
            return_value=False
        )

        detector = DetectScannedFile(cfg)
        pages = [
            SimpleNamespace(page_number=i, pdf_character=[object()] * 2)
            for i in range(5)
        ]
        docs = SimpleNamespace(page=pages)

        with (
            patch(
                "babeldoc.format.pdf.document_il.midend.detect_scanned_file.PDFCreater"
            ),
            patch.object(detector, "detect_page_is_scanned", return_value=True),
        ):
            with pytest.raises(ScannedPDFError):
                detector.process(docs, str(pdf_path), {})


class TestOcrSkippedAndGlyphlessHandling:
    def test_strip_ocr_skipped_overlays_drops_white_rect_and_clears_glyphs(self):
        from babeldoc.format.pdf.translation_config import SharedContextCrossSplitPart

        shared = SharedContextCrossSplitPart()
        ts = Typesetting.__new__(Typesetting)
        ts.translation_config = SimpleNamespace(
            ocr_workaround=True, shared_context_cross_split_part=shared
        )

        p1 = PdfParagraph(box=Box(50, 500, 300, 600), unicode="翻译正文", xobj_id=-1)
        p2 = PdfParagraph(
            box=Box(50, 200, 300, 300),
            unicode="4. Cox, Tracey (2003).",
            pdf_paragraph_composition=[PdfParagraphComposition()],
            xobj_id=-1,
        )
        shared.ocr_skipped_para_ids.add(id(p2))
        shared.ocr_para_layout_ids[id(p1)] = 1
        shared.ocr_para_layout_ids[id(p2)] = 1

        r1 = PdfRectangle(box=Box(45, 195, 310, 605), fill_background=True)
        shared.ocr_bg_rect_meta[id(r1)] = (id(p1), 1)

        r2 = PdfRectangle(box=Box(45, 195, 310, 605), fill_background=True)
        shared.ocr_bg_rect_meta[id(r2)] = (id(p2), 1)

        page = SimpleNamespace(pdf_paragraph=[p1, p2], pdf_rectangle=[r1, r2])
        ts._strip_ocr_skipped_overlays(page)

        assert page.pdf_rectangle == [r1]
        assert r1.box == Box(50, 500, 300, 600)
        assert p2.pdf_paragraph_composition == []
        assert p2.unicode == ""

    def test_glyphless_font_char_in_translated_para_maps_to_visible_font(self):
        ts = Typesetting.__new__(Typesetting)
        ts.is_cjk = True
        ts.translation_config = SimpleNamespace(ocr_workaround=True)
        mapped_font = MagicMock()
        mapped_font.char_lengths.return_value = [6.0]
        ts.font_mapper = MagicMock()
        ts.font_mapper.map.return_value = mapped_font

        glyphless = PdfFont(font_id="R8", name="IXCOHI+GlyphLessFont", bold=False)
        char = PdfCharacter(
            pdf_character_id=12,
            char_unicode="7",
            box=Box(100, 50, 110, 62),
            pdf_style=PdfStyle(
                font_id="R8",
                font_size=10.0,
                graphic_state=GraphicState(passthrough_per_char_instruction="3 Tr"),
            ),
            xobj_id=-1,
        )
        para = PdfParagraph(
            box=Box(100, 50, 110, 62),
            pdf_paragraph_composition=[PdfParagraphComposition(pdf_character=char)],
            xobj_id=-1,
        )

        units = ts.create_typesetting_units(para, {"R8": glyphless})
        assert len(units) == 1
        assert units[0].unicode == "7"
        assert units[0].font is mapped_font
        assert units[0].can_passthrough is False
        assert "Tr" not in (units[0].style.graphic_state.passthrough_per_char_instruction or "")
