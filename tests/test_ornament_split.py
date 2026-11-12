"""Unit tests for ornament splitting, outline hang guard, title gap, and overlap checks."""

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter
from babeldoc.format.pdf.document_il.il_version_1 import PdfLine
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraphComposition
from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.contract import (
    BlockEdges,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.outline import hang
from babeldoc.format.pdf.document_il.utils.ornament_split import (
    detach_decorative_quotes_and_margin_counters,
)
from babeldoc.format.pdf.document_il.utils.ornament_split import (
    detach_oversized_quote_chars,
)
from babeldoc.format.pdf.document_il.utils.ornament_split import (
    is_decorative_quote_ornament,
)
from babeldoc.format.pdf.document_il.utils.same_baseline import rendered_lines_overlap
from babeldoc.format.pdf.document_il.utils.toc_rows import is_toc_paragraph
from babeldoc.format.pdf.document_il.utils.vertical_gap import is_display_title


def _char_comp(text_char: str, box: tuple[float, float, float, float], fs: float) -> PdfParagraphComposition:
    b = Box(x=box[0], y=box[1], x2=box[2], y2=box[3])
    return PdfParagraphComposition(
        pdf_character=PdfCharacter(
            char_unicode=text_char,
            box=b,
            pdf_style=PdfStyle(font_id="F1", font_size=fs),
        )
    )


def _line_comp(text: str, box: tuple[float, float, float, float], fs: float) -> PdfParagraphComposition:
    b = Box(x=box[0], y=box[1], x2=box[2], y2=box[3])
    chars = []
    if text:
        step = (box[2] - box[0]) / max(1, len(text))
        for idx, ch in enumerate(text):
            chars.append(
                PdfCharacter(
                    char_unicode=ch,
                    box=Box(x=box[0] + idx * step, y=box[1], x2=box[0] + (idx + 1) * step, y2=box[3]),
                    pdf_style=PdfStyle(font_id="F1", font_size=fs),
                )
            )
    return PdfParagraphComposition(pdf_line=PdfLine(box=b, pdf_character=chars))


def _id_gen():
    counter = iter(range(100))
    return lambda: f"id_{next(counter)}"


def test_detach_oversized_quote_char_before_line_grouping():
    quote_comp = _char_comp("“", (313.0, 313.2, 344.5, 337.6), 100.0)
    body_comps = [
        _char_comp(ch, (351.5 + i * 6.0, 309.5, 357.5 + i * 6.0, 327.5), 18.0)
        for i, ch in enumerate("Most pressure")
    ]
    para = PdfParagraph(
        box=Box(x=313.0, y=309.5, x2=430.0, y2=337.6),
        pdf_style=PdfStyle(font_id="F1", font_size=18.0),
        pdf_paragraph_composition=[quote_comp, *body_comps],
        unicode="“Most pressure",
        layout_label="plain text",
        debug_id="p_quote",
    )
    paragraphs = [para]

    detach_oversized_quote_chars(paragraphs, new_debug_id_factory=_id_gen())

    assert len(paragraphs) == 2
    assert paragraphs[0].unicode == "“"
    assert is_decorative_quote_ornament(paragraphs[0])
    assert paragraphs[1].unicode == "Mostpressure"
    assert paragraphs[1].box.x == 351.5


def test_detach_margin_counter_and_pair_list_step():
    step1 = PdfParagraph(
        box=Box(x=92.0, y=580.6, x2=400.0, y2=676.6),
        pdf_style=PdfStyle(font_id="F1", font_size=12.0),
        pdf_paragraph_composition=[
            _line_comp("Practice breathing", (103.0, 662.6, 357.3, 676.6), 12.0),
            _line_comp("from your belly.", (92.1, 646.6, 300.0, 660.6), 12.0),
            _line_comp("2", (89.7, 588.6, 101.5, 601.8), 30.0),
        ],
        unicode="Practice breathing from your belly. 2",
        layout_label="plain text",
        debug_id="step1",
    )
    num1 = PdfParagraph(
        box=Box(x=88.4, y=670.6, x2=102.8, y2=700.6),
        pdf_style=PdfStyle(font_id="F1", font_size=30.0),
        pdf_paragraph_composition=[_line_comp("1", (88.4, 670.6, 102.8, 700.6), 30.0)],
        unicode="1",
        layout_label="abandon",
        debug_id="num1",
    )
    step2 = PdfParagraph(
        box=Box(x=92.0, y=560.6, x2=380.0, y2=594.6),
        pdf_style=PdfStyle(font_id="F1", font_size=12.0),
        pdf_paragraph_composition=[
            _line_comp("Inhaling very slowly.", (104.1, 580.6, 280.0, 594.6), 12.0),
            _line_comp("Keep steady rhythm.", (92.0, 560.6, 260.0, 574.6), 12.0),
        ],
        unicode="Inhaling very slowly. Keep steady rhythm.",
        layout_label="plain text",
        debug_id="step2",
    )
    paragraphs = [num1, step1, step2]

    detach_decorative_quotes_and_margin_counters(
        paragraphs, new_debug_id_factory=_id_gen()
    )

    assert len(paragraphs) == 4
    texts = [p.unicode for p in paragraphs]
    assert texts == [
        "1",
        "Practice breathing from your belly.",
        "2",
        "Inhaling very slowly. Keep steady rhythm.",
    ]
    assert all(p.layout_label == "list" for p in paragraphs)


def test_outline_hang_rejects_disjoint_left_ornament():
    edges = BlockEdges(
        full_count=4,
        left_range=39.45,
        right_range=2.7,
        left_monotone=1.0,
        right_monotone=0.0,
        marker="none",
    )
    disjoint_lines = [
        (312.0, 350.9, 440.3),
        (351.45, 556.0, 420.0),
        (351.45, 554.0, 400.0),
        (351.45, 555.0, 380.0),
    ]
    assert hang(edges, disjoint_lines, "shallow") is None

    genuine_hang_lines = [
        (72.0, 500.0, 700.0),
        (96.0, 498.0, 684.0),
        (96.0, 501.0, 668.0),
        (96.0, 499.0, 652.0),
    ]
    assert hang(edges, genuine_hang_lines, "shallow") is not None


def test_is_display_title_rejects_quote_ornament_and_bare_counter():
    quote_para = PdfParagraph(
        box=Box(x=312.0, y=370.9, x2=350.9, y2=470.9),
        pdf_style=PdfStyle(font_id="F1", font_size=100.0),
        pdf_paragraph_composition=[_line_comp("“", (312.0, 370.9, 350.9, 470.9), 100.0)],
        unicode="“",
        layout_label="plain text",
    )
    counter_para = PdfParagraph(
        box=Box(x=88.4, y=670.6, x2=102.8, y2=700.6),
        pdf_style=PdfStyle(font_id="F1", font_size=30.0),
        pdf_paragraph_composition=[_line_comp("1", (88.4, 670.6, 102.8, 700.6), 30.0)],
        unicode="1",
        layout_label="list",
    )
    heading_para = PdfParagraph(
        box=Box(x=56.0, y=680.0, x2=400.0, y2=710.0),
        pdf_style=PdfStyle(font_id="F1", font_size=30.0),
        pdf_paragraph_composition=[_line_comp("Chapter 1: Basics", (56.0, 680.0, 400.0, 710.0), 30.0)],
        unicode="Chapter 1: Basics",
        layout_label="title",
    )

    assert is_display_title(quote_para) is False
    assert is_display_title(counter_para) is False
    assert is_display_title(heading_para) is True


def test_rendered_lines_overlap_ignores_corner_numeral_union_bbox():
    corner_num = PdfParagraph(
        box=Box(x=88.4, y=670.6, x2=102.8, y2=700.6),
        pdf_style=PdfStyle(font_id="F1", font_size=30.0),
        pdf_paragraph_composition=[_line_comp("1", (88.4, 670.6, 102.8, 700.6), 30.0)],
        unicode="1",
    )
    step_body = PdfParagraph(
        box=Box(x=92.1, y=646.0, x2=357.3, y2=676.6),
        pdf_style=PdfStyle(font_id="F1", font_size=12.0),
        pdf_paragraph_composition=[
            _line_comp("Line one right of numeral.", (103.0, 662.6, 357.3, 676.6), 12.0),
            _line_comp("Line two wraps below numeral.", (92.1, 646.0, 340.0, 660.6), 12.0),
        ],
        unicode="Line one right of numeral. Line two wraps below numeral.",
    )
    assert rendered_lines_overlap(corner_num, step_body) is False


def test_bare_margin_counter_is_not_misclassified_as_toc_and_skips_as_pure_numeric():
    from unittest.mock import MagicMock

    from babeldoc.format.pdf.document_il.midend.il_translator import ILTranslator
    from babeldoc.format.pdf.document_il.utils.skip_audit import SkipReason
    from babeldoc.format.pdf.translation_config import TranslationConfig
    from babeldoc.translator.fixed_map_translator import FixedMapTranslator

    base_tr = FixedMapTranslator()
    cfg = TranslationConfig(
        translator=base_tr,
        input_file="dummy.pdf",
        lang_in="en",
        lang_out="zh-CN",
        doc_layout_model=MagicMock(),
        auto_extract_glossary=False,
        min_text_length=1,
    )
    translator = ILTranslator(base_tr, cfg)

    list_counter = PdfParagraph(
        box=Box(x=88.4, y=670.6, x2=102.8, y2=700.6),
        pdf_style=PdfStyle(font_id="F1", font_size=30.0),
        pdf_paragraph_composition=[_line_comp("1", (88.4, 670.6, 102.8, 700.6), 30.0)],
        unicode="1",
        layout_label="list",
    )
    plain_num = PdfParagraph(
        box=Box(x=200.0, y=500.0, x2=228.0, y2=514.0),
        pdf_style=PdfStyle(font_id="F1", font_size=14.0),
        pdf_paragraph_composition=[_line_comp("2026", (200.0, 500.0, 228.0, 514.0), 14.0)],
        unicode="2026",
        layout_label="plain text",
    )
    toc_num = PdfParagraph(
        box=Box(x=527.1, y=635.0, x2=534.9, y2=651.0),
        pdf_style=PdfStyle(font_id="F1", font_size=14.0),
        pdf_paragraph_composition=[_line_comp("3", (527.1, 635.0, 534.9, 651.0), 14.0)],
        unicode="3",
        layout_label="toc",
    )
    leader_row = PdfParagraph(
        box=Box(x=56.0, y=600.0, x2=534.9, y2=616.0),
        pdf_style=PdfStyle(font_id="F1", font_size=14.0),
        pdf_paragraph_composition=[_line_comp("Foreword ........ 3", (56.0, 600.0, 534.9, 616.0), 14.0)],
        unicode="Foreword ........ 3",
        layout_label="plain text",
    )

    assert is_toc_paragraph(list_counter) is False
    assert is_toc_paragraph(plain_num) is False
    assert is_toc_paragraph(toc_num) is True
    assert is_toc_paragraph(leader_row) is True

    assert translator.get_translate_input(list_counter) is None
    assert (
        translator.skip_report.counts_by_reason()[SkipReason.PURE_NUMERIC.value] == 1
    )
    assert translator.get_translate_input(toc_num) is not None
