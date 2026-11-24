"""Tests for bibliography passthrough detection and scanned-PDF OCR bypass."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from babeldoc.format.pdf.document_il.midend.detect_scanned_file import DetectScannedFile
from babeldoc.format.pdf.document_il.midend.detect_scanned_file import ScannedPDFError
from babeldoc.format.pdf.document_il.midend.il_translator import ILTranslator
from babeldoc.format.pdf.document_il.midend.il_translator import TitleContextSnapshot


def _para(text: str, layout_label: str = "text") -> SimpleNamespace:
    return SimpleNamespace(unicode=text, layout_label=layout_label)


class TestBibliographyParagraphDetection:
    def test_exact_headers_and_footers_are_not_treated_as_entries(self):
        title = TitleContextSnapshot(debug_id="t1", unicode="References")
        assert ILTranslator._is_bibliography_paragraph(_para("References", "title"), title) is False
        assert ILTranslator._is_bibliography_paragraph(_para("Bibliography", "text"), title) is False
        assert ILTranslator._is_bibliography_paragraph(_para("Table of Contents", "text"), title) is False
        assert (
            ILTranslator._is_bibliography_paragraph(
                _para("www.GabrielleMoore.com", "abandon"), title
            )
            is False
        )

    def test_content_under_references_section_is_preserved(self):
        title = TitleContextSnapshot(debug_id="t1", unicode="References")
        assert (
            ILTranslator._is_bibliography_paragraph(
                _para("Some short note under references section."), local_title=title
            )
            is True
        )
        assert (
            ILTranslator._is_bibliography_paragraph(
                _para("Subheading inside references", layout_label="title"),
                local_title=title,
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

    def test_normal_prose_is_not_skipped(self):
        assert (
            ILTranslator._is_bibliography_paragraph(
                _para("1. Place your hands gently on her shoulders and breathe slowly.")
            )
            is False
        )
        assert (
            ILTranslator._is_bibliography_paragraph(
                _para("In 2010 she noticed a dramatic improvement in intimacy.")
            )
            is False
        )


class TestDetectScannedFileBypass:
    def test_skip_scanned_detection_flag_returns_early(self):
        cfg = MagicMock()
        cfg.skip_scanned_detection = True
        detector = DetectScannedFile(cfg)
        docs = SimpleNamespace(page=[])
        # Should return immediately without opening input.pdf
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
            patch.object(detector, "detect_page_is_scanned", return_value=True) as mock_detect,
        ):
            # Must not raise ScannedPDFError when OCR character count > 200
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
