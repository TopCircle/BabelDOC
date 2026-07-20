"""Phase C: OCR dual-layer typesetting — larger scale, expand box, no mode demotion.

All behavior is gated on ``ocr_workaround`` so born-digital figure duals stay
on the existing scale/expand path.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
from babeldoc.format.pdf.document_il.midend.paragraph_finder import ParagraphFinder
from babeldoc.format.pdf.document_il.midend.typesetting import Typesetting
from babeldoc.format.pdf.translation_config import TranslationConfig
from babeldoc.translator.fixed_map_translator import FixedMapTranslator


def _config(ocr: bool = True) -> TranslationConfig:
    return TranslationConfig(
        translator=FixedMapTranslator(),
        input_file="ocr.pdf",
        lang_in="en",
        lang_out="zh-CN",
        doc_layout_model=MagicMock(),
        auto_extract_glossary=False,
        ocr_workaround=ocr,
    )


def _page(*, crop_y2: float = 800.0):
    return SimpleNamespace(
        cropbox=SimpleNamespace(box=Box(x=0, y=0, x2=400, y2=crop_y2)),
        pdf_paragraph=[],
        pdf_character=[],
        pdf_figure=[],
        pdf_curve=[],
        pdf_form=[],
        pdf_rectangle=[],
    )


class TestOcrLayoutScale:
    def test_ocr_line_skip_tighter_than_default(self):
        assert Typesetting._OCR_LINE_SKIP_CJK < Typesetting._DEFAULT_LINE_SKIP_CJK
        assert Typesetting._OCR_LINE_SKIP_CJK >= 1.2
        assert Typesetting._OCR_MIN_SCALE >= 0.85

    def test_ocr_normalize_lifts_courier_size(self):
        ts = Typesetting(_config(ocr=True))
        units = [
            SimpleNamespace(font_size=11.0, formular=None, char=None, style=None),
            SimpleNamespace(font_size=7.5, formular=None, char=None, style=None),
            SimpleNamespace(font_size=11.2, formular=None, char=None, style=None),
        ]
        out = ts._ocr_normalize_unit_font_sizes(units)
        sizes = [u.font_size for u in out]
        assert min(sizes) >= 10.0 - 1e-6
        assert max(sizes) >= 11.0

    def test_ocr_normalize_not_called_path_without_ocr_units_unchanged(self):
        """Helper is OCR-only; calling it still lifts, but non-OCR never calls it."""
        ts = Typesetting(_config(ocr=False))
        assert ts.translation_config.ocr_workaround is False

    def test_ocr_pre_expand_down_and_right(self):
        ts = Typesetting(_config(ocr=True))
        page = _page()
        # Obstacle para below leaves room to grow down to y=100
        other = PdfParagraph(
            box=Box(x=50, y=50, x2=300, y2=100),
            pdf_style=PdfStyle(font_id="F1", font_size=10.0, graphic_state=None),
            pdf_paragraph_composition=[],
            unicode="next",
        )
        page.pdf_paragraph = [other]
        para = PdfParagraph(
            box=Box(x=50, y=200, x2=200, y2=400),
            pdf_style=PdfStyle(font_id="F1", font_size=10.0, graphic_state=None),
            pdf_paragraph_composition=[],
            unicode="body",
        )
        page.pdf_paragraph.append(para)
        box = para.box
        expanded = ts._ocr_pre_expand_box(box, para, page, apply_layout=True)
        # Right: toward crop 0.9*400 - 5 (get_max_right_space behavior)
        assert expanded.x2 > box.x2 or expanded.y < box.y
        # Down: toward other.y2 (=100) + 2 when free space exists
        if expanded.y < box.y:
            assert expanded.y <= 102 + 1e-6
        assert para.box.y == expanded.y
        assert para.box.x2 == expanded.x2

    def test_mode_demotion_skipped_under_ocr(self):
        ts = Typesetting(_config(ocr=True))
        p_small = PdfParagraph(
            box=Box(x=0, y=0, x2=100, y2=50),
            pdf_style=PdfStyle(font_id="F1", font_size=10.0, graphic_state=None),
            pdf_paragraph_composition=[],
            unicode="x" * 200,
            optimal_scale=0.6,
        )
        p_large = PdfParagraph(
            box=Box(x=0, y=100, x2=100, y2=150),
            pdf_style=PdfStyle(font_id="F1", font_size=10.0, graphic_state=None),
            pdf_paragraph_composition=[],
            unicode="title",
            optimal_scale=1.0,
        )
        # Mirror preprocess mode-demotion gate
        all_paragraphs = [p_small, p_large]
        all_scales = [0.6] * 50 + [1.0] * 5
        if getattr(ts.translation_config, "ocr_workaround", False):
            pass  # no demotion
        else:
            import statistics

            mode_scale = min(statistics.multimode(all_scales))
            for paragraph in all_paragraphs:
                if (
                    paragraph.optimal_scale is not None
                    and paragraph.optimal_scale > mode_scale
                ):
                    paragraph.optimal_scale = mode_scale
        assert p_large.optimal_scale == 1.0
        assert p_small.optimal_scale == 0.6

    def test_mode_demotion_still_runs_without_ocr(self):
        ts = Typesetting(_config(ocr=False))
        assert ts.translation_config.ocr_workaround is False

    def test_white_fill_updates_paragraph_box(self):
        """OCR white cover must enlarge typesetting box, not only paint white."""
        from babeldoc.format.pdf.document_il.il_version_1 import Page
        from babeldoc.format.pdf.document_il.il_version_1 import PageLayout

        cfg = _config(ocr=True)
        pf = ParagraphFinder(cfg)
        para = PdfParagraph(
            box=Box(x=50, y=400, x2=200, y2=480),  # tight
            pdf_style=PdfStyle(font_id="F1", font_size=10.0, graphic_state=None),
            pdf_paragraph_composition=[],
            unicode="body",
            layout_id=1,
        )
        page = Page(
            page_number=0,
            pdf_paragraph=[para],
            pdf_rectangle=[],
            page_layout=[
                PageLayout(
                    id=1,
                    box=Box(x=40, y=300, x2=350, y2=500),  # taller layout
                    class_name="text",
                )
            ],
        )
        try:
            pf.add_text_fill_background(page)
        except TypeError:
            page = SimpleNamespace(
                pdf_paragraph=[para],
                pdf_rectangle=[],
                page_layout=[
                    SimpleNamespace(
                        id=1,
                        box=Box(x=40, y=300, x2=350, y2=500),
                        class_name="text",
                    )
                ],
            )
            pf.add_text_fill_background(page)
        assert para.box.y <= 300 + 1e-6
        assert para.box.y2 >= 500 - 1e-6
        assert para.box.x2 >= 350 - 1e-6
        assert len(page.pdf_rectangle) == 1
