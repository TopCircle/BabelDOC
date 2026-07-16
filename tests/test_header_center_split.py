"""arXiv-style header: page-symmetric center + date line split."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter
from babeldoc.format.pdf.document_il.il_version_1 import PdfLine
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraphComposition
from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
from babeldoc.format.pdf.document_il.il_version_1 import VisualBbox
from babeldoc.format.pdf.document_il.midend.paragraph_finder import ParagraphFinder
from babeldoc.format.pdf.document_il.utils.layout_helper import detect_paragraph_alignment
from babeldoc.format.pdf.translation_config import TranslationConfig
from babeldoc.translator.fixed_map_translator import FixedMapTranslator


def _page(width: float = 612.0):
    return SimpleNamespace(
        cropbox=SimpleNamespace(box=Box(x=0, y=0, x2=width, y2=792)),
        mediabox=SimpleNamespace(box=Box(x=0, y=0, x2=width, y2=792)),
    )


def _line_comp(x: float, x2: float, y: float, text: str) -> PdfParagraphComposition:
    style = PdfStyle(font_id="base", font_size=10.0, graphic_state=None)
    chars = []
    n = max(len(text), 1)
    w = (x2 - x) / n
    cx = x
    for ch in text:
        b = Box(x=cx, y=y, x2=min(cx + w, x2), y2=y + 10)
        chars.append(
            PdfCharacter(
                char_unicode=ch,
                box=b,
                visual_bbox=VisualBbox(box=Box(x=b.x, y=b.y, x2=b.x2, y2=b.y2)),
                pdf_style=style,
            )
        )
        cx += w
    return PdfParagraphComposition(
        pdf_line=PdfLine(box=Box(x=x, y=y, x2=x2, y2=y + 10), pdf_character=chars)
    )


class TestArxivHeaderGeometry:
    def test_affil_plus_date_detect_center(self):
        from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph as P

        # Build via detect helper used in alignment tests
        ranges = [(125.3, 487.0), (132.7, 479.6), (260.2, 352.1)]
        comps = []
        y = 200.0
        for x, x2 in ranges:
            comps.append(_line_comp(x, x2, y, "x" * 10))
            y -= 12
        pl = min(r[0] for r in ranges)
        pr = max(r[1] for r in ranges)
        para = P(
            box=Box(x=pl, y=y, x2=pr, y2=212),
            pdf_style=PdfStyle(font_id="base", font_size=10.0, graphic_state=None),
            pdf_paragraph_composition=comps,
            unicode="affil",
        )
        assert detect_paragraph_alignment(para, _page(612)) == "center"

    def test_left_column_body_not_page_center(self):
        ranges = [(52.0, 297.0), (52.0, 296.0), (52.0, 297.0), (52.0, 200.0)]
        comps = []
        y = 400.0
        for x, x2 in ranges:
            comps.append(_line_comp(x, x2, y, "body line text here"))
            y -= 12
        pl = min(r[0] for r in ranges)
        pr = max(r[1] for r in ranges)
        para = PdfParagraph(
            box=Box(x=pl, y=y, x2=pr, y2=420),
            pdf_style=PdfStyle(font_id="base", font_size=10.0, graphic_state=None),
            pdf_paragraph_composition=comps,
            unicode="body",
        )
        assert detect_paragraph_alignment(para, _page(612)) == "left"

    def test_splits_dated_line_to_own_paragraph(self):
        cfg = TranslationConfig(
            translator=FixedMapTranslator(),
            input_file="header.pdf",
            lang_in="en",
            lang_out="zh-CN",
            doc_layout_model=MagicMock(),
            auto_extract_glossary=False,
        )
        pf = ParagraphFinder(cfg)
        para = PdfParagraph(
            box=Box(x=125, y=90, x2=487, y2=124),
            pdf_style=PdfStyle(font_id="base", font_size=10.0, graphic_state=None),
            pdf_paragraph_composition=[
                _line_comp(125.3, 487.0, 100, "1Department of Applied Physics Yale"),
                _line_comp(132.7, 479.6, 88, "and Yale Quantum Institute"),
                _line_comp(260.2, 352.1, 76, "(Dated: July 16, 2024)"),
            ],
            unicode="x",
        )
        paras = [para]
        pf.process_independent_paragraphs(paras, median_width=200.0)
        assert len(paras) == 2
        last_text = "".join(
            c.char_unicode
            for comp in paras[1].pdf_paragraph_composition
            if comp.pdf_line
            for c in comp.pdf_line.pdf_character
        )
        assert "Dated" in last_text
        first_text = "".join(
            c.char_unicode
            for comp in paras[0].pdf_paragraph_composition
            if comp.pdf_line
            for c in comp.pdf_line.pdf_character
        )
        assert "Dated" not in first_text
        assert "Department" in first_text
