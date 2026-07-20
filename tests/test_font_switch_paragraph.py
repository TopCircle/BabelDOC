"""Phase B: font-face paragraph splits — hard on born-digital, soft under OCR."""

from __future__ import annotations

from unittest.mock import MagicMock

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter
from babeldoc.format.pdf.document_il.il_version_1 import PdfFont
from babeldoc.format.pdf.document_il.il_version_1 import PdfLine
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraphComposition
from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
from babeldoc.format.pdf.document_il.il_version_1 import VisualBbox
from babeldoc.format.pdf.document_il.midend.paragraph_finder import ParagraphFinder
from babeldoc.format.pdf.document_il.utils.fontmap import FontMapper
from babeldoc.format.pdf.document_il.utils.paragraph_split_policy import (
    line_ends_sentence,
    should_split_on_font_face_switch,
)
from babeldoc.format.pdf.translation_config import TranslationConfig
from babeldoc.translator.fixed_map_translator import FixedMapTranslator


def _char(ch: str, x: float, y: float, font_id: str, size: float = 10.0) -> PdfCharacter:
    box = Box(x=x, y=y, x2=x + size * 0.5, y2=y + size)
    return PdfCharacter(
        char_unicode=ch,
        box=box,
        visual_bbox=VisualBbox(box=Box(x=box.x, y=box.y, x2=box.x2, y2=box.y2)),
        pdf_style=PdfStyle(font_id=font_id, font_size=size, graphic_state=None),
    )


def _line(text: str, y: float, font_id: str, x0: float = 50.0) -> PdfParagraphComposition:
    chars = []
    x = x0
    for ch in text:
        chars.append(_char(ch, x, y, font_id))
        x += 6.0
    return PdfParagraphComposition(
        pdf_line=PdfLine(
            box=Box(x=x0, y=y, x2=x, y2=y + 12),
            pdf_character=chars,
        )
    )


def _config(*, ocr_workaround: bool = False) -> TranslationConfig:
    return TranslationConfig(
        translator=FixedMapTranslator(),
        input_file="font_unknown.pdf",
        lang_in="en",
        lang_out="zh-CN",
        doc_layout_model=MagicMock(),
        auto_extract_glossary=False,
        ocr_workaround=ocr_workaround,
    )


def _para_text(para: PdfParagraph) -> str:
    return "".join(
        c.char_unicode
        for comp in para.pdf_paragraph_composition or []
        if comp.pdf_line
        for c in comp.pdf_line.pdf_character
    )


class TestLineEndsSentence:
    def test_period_and_colon(self):
        assert line_ends_sentence(_line("ends here.", 10, "F1").pdf_line)
        assert line_ends_sentence(_line("label:", 10, "F1").pdf_line)
        assert not line_ends_sentence(
            _line("occasional bias, occasional", 10, "F1").pdf_line
        )

    def test_trailing_quote_after_period(self):
        assert line_ends_sentence(_line('said "hello."', 10, "F1").pdf_line)


class TestFontSwitchParagraphSplit:
    def test_born_digital_mid_sentence_face_still_splits(self):
        """Default (no OCR): face switch always splits — arXiv figure labels.

        Body ``SFRM`` then short ``Arial`` annotation mid-clause must not stay
        one paragraph (else labels translate into body / dual mess).
        """
        pf = ParagraphFinder(_config(ocr_workaround=False))
        para = PdfParagraph(
            box=Box(x=50, y=200, x2=340, y2=300),
            pdf_style=PdfStyle(font_id="SFRM1000", font_size=10.0, graphic_state=None),
            pdf_paragraph_composition=[
                _line("at higher readout power, the dispersive ap-", 280, "SFRM1000"),
                _line("Ancilla", 265, "ArialMT", x0=320.0),
                _line("proximation breaks down [14], causing", 250, "SFRM1000"),
            ],
            unicode="x",
        )
        paras = [para]
        pf.process_independent_paragraphs(paras, median_width=200.0)
        assert len(paras) >= 2
        assert should_split_on_font_face_switch(
            _line(
                "at higher readout power, the dispersive ap-", 280, "SFRM1000"
            ).pdf_line,
            _line("Ancilla", 265, "ArialMT").pdf_line,
            soft_mid_sentence=False,
        )
        # Label is not glued into the first body fragment
        assert "Ancilla" not in _para_text(paras[0])

    def test_ocr_mid_sentence_times_to_courier_not_split(self):
        """OCR dual-layer (font.unknown): mid-clause face keep for MT context."""
        pf = ParagraphFinder(_config(ocr_workaround=True))
        para = PdfParagraph(
            box=Box(x=50, y=200, x2=340, y2=300),
            pdf_style=PdfStyle(font_id="Font1", font_size=10.0, graphic_state=None),
            pdf_paragraph_composition=[
                _line(
                    "nothing but the facts, and yes, there's occasional bias, occasional",
                    280,
                    "Font1",
                ),
                _line(
                    "sensationalism, occasional inaccuracy, but a responsible journalist",
                    265,
                    "Font2",
                ),
                _line("never, never, never fakes the news.", 250, "Font2"),
            ],
            unicode="x",
        )
        paras = [para]
        pf.process_independent_paragraphs(paras, median_width=200.0)
        assert len(paras) == 1
        assert (
            should_split_on_font_face_switch(
                paras[0].pdf_paragraph_composition[0].pdf_line,
                paras[0].pdf_paragraph_composition[1].pdf_line,
                soft_mid_sentence=True,
            )
            is False
        )

    def test_ocr_sentence_final_times_to_courier_splits(self):
        """OCR path: clean sentence boundary → mono block is its own paragraph."""
        pf = ParagraphFinder(_config(ocr_workaround=True))
        para = PdfParagraph(
            box=Box(x=50, y=200, x2=340, y2=300),
            pdf_style=PdfStyle(font_id="Font1", font_size=10.0, graphic_state=None),
            pdf_paragraph_composition=[
                _line("body text about facts and bias.", 280, "Font1"),
                _line("never never never fakes the news.", 265, "Font2"),
            ],
            unicode="x",
        )
        paras = [para]
        pf.process_independent_paragraphs(paras, median_width=200.0)
        assert len(paras) == 2
        assert "never" not in _para_text(paras[0])
        assert "never" in _para_text(paras[1])
        assert "bias" in _para_text(paras[0])

    def test_born_digital_sentence_final_still_splits(self):
        pf = ParagraphFinder(_config(ocr_workaround=False))
        para = PdfParagraph(
            box=Box(x=50, y=200, x2=340, y2=300),
            pdf_style=PdfStyle(font_id="Font1", font_size=10.0, graphic_state=None),
            pdf_paragraph_composition=[
                _line("body text about facts and bias.", 280, "Font1"),
                _line("never never never fakes the news.", 265, "Font2"),
            ],
            unicode="x",
        )
        paras = [para]
        pf.process_independent_paragraphs(paras, median_width=200.0)
        assert len(paras) == 2

    def test_same_font_not_split(self):
        pf = ParagraphFinder(_config())
        para = PdfParagraph(
            box=Box(x=50, y=200, x2=340, y2=300),
            pdf_style=PdfStyle(font_id="Font1", font_size=10.0, graphic_state=None),
            pdf_paragraph_composition=[
                _line("first line of body text here xx", 280, "Font1"),
                _line("second line of body text here", 265, "Font1"),
            ],
            unicode="x",
        )
        paras = [para]
        pf.process_independent_paragraphs(paras, median_width=200.0)
        assert len(paras) == 1

    def test_date_tail_still_splits(self):
        """Regression: short centered (Dated: …) under affiliation stays separate."""
        pf = ParagraphFinder(_config(ocr_workaround=False))
        para = PdfParagraph(
            box=Box(x=50, y=200, x2=500, y2=300),
            pdf_style=PdfStyle(font_id="Font1", font_size=10.0, graphic_state=None),
            pdf_paragraph_composition=[
                _line(
                    "Department of Applied Physics, Yale University",
                    280,
                    "Font1",
                    x0=80.0,
                ),
                # short inset date line (same font — geometry triggers split)
                _line("(Dated: January 1, 2024)", 265, "Font1", x0=180.0),
            ],
            unicode="x",
        )
        # make date line geometrically short/inset vs affil
        affil = para.pdf_paragraph_composition[0].pdf_line
        date = para.pdf_paragraph_composition[1].pdf_line
        affil.box = Box(x=80, y=280, x2=480, y2=292)
        date.box = Box(x=200, y=265, x2=360, y2=277)
        paras = [para]
        pf.process_independent_paragraphs(paras, median_width=400.0)
        assert len(paras) == 2
        assert "Dated" in _para_text(paras[1])
        assert "Department" in _para_text(paras[0])


class TestMonoFontMapping:
    def test_courier_name_forces_sans_not_serif(self):
        """Courier-like original should map CJK to sans stand-in (not serif body)."""
        cfg = _config()
        mapper = FontMapper(cfg)
        courier = PdfFont(
            font_id="Font2",
            name="AAAAAC+Courier",
            xref_id=1,
            bold=False,
            italic=False,
            monospace=False,  # often missing on subset fonts
            serif=False,
        )
        mapped = mapper.map(courier, "中")
        assert mapped is not None
        fid = mapped.font_id.lower()
        # sans stand-in for mono: SourceHanSans… not SourceHanSerif…
        assert "serif" not in fid or "sans" in fid
        assert "sans" in fid

    def test_times_stays_serif_when_primary_none(self):
        cfg = _config()
        mapper = FontMapper(cfg)
        times = PdfFont(
            font_id="Font1",
            name="AAAAAB+TimesNewRomanPSMT",
            xref_id=1,
            bold=False,
            italic=False,
            monospace=False,
            serif=True,
        )
        mapped = mapper.map(times, "中")
        assert mapped is not None
        assert "serif" in mapped.font_id.lower()
