"""Regressions from the LLT page 5 and 10 callouts."""

from types import SimpleNamespace

import pytest
from babeldoc.format.pdf.document_il.utils.layout_intent_extractor import (
    LayoutIntentExtractor,
)
from babeldoc.format.pdf.document_il.il_version_1 import Page, Cropbox


def extract_intents(page):
    actual = Page(
        pdf_paragraph=page.pdf_paragraph,
        pdf_curve=[],
        cropbox=Cropbox(box=page.cropbox.box),
    )
    LayoutIntentExtractor(SimpleNamespace(debug=False))._extract_page(actual)


from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter, PdfStyle
from babeldoc.format.pdf.document_il.il_version_1 import (
    PdfLine,
    PdfParagraph,
    PdfParagraphComposition,
)
from babeldoc.format.pdf.document_il.utils.layout_intent import LayoutIntentRole
from babeldoc.format.pdf.document_il.utils.rect_flow_stack import _lines_of
from babeldoc.format.pdf.document_il.utils.rect_column_reflow import (
    mark_display_bands,
    forget_display_bands,
    drop_below_display_band,
)


def test_multiline_body_mislabelled_title_does_not_displace_the_side_quote():
    body = PdfParagraph(
        box=Box(x=90, y=87, x2=559, y2=355),
        pdf_paragraph_composition=[],
        unicode="A long body paragraph.",
    )
    body.layout_label = "title"
    body.reference_metrics = SimpleNamespace(font_size=14, line_count=15)
    quote = PdfParagraph(
        box=Box(x=350, y=190, x2=545, y2=320),
        pdf_paragraph_composition=[],
        unicode="Side quote",
    )
    page = SimpleNamespace(
        pdf_paragraph=[body, quote],
        pdf_curve=[],
        cropbox=SimpleNamespace(box=Box(x=0, y=0, x2=612, y2=792)),
    )
    extract_intents(page)
    assert body.layout_intent.role is LayoutIntentRole.BODY
    try:
        mark_display_bands(page)
        assert (
            drop_below_display_band(quote, 302.0, 18.0, page, (350.0, 545.0)) == 302.0
        )
    finally:
        forget_display_bands([body, quote], page)


def test_decorative_quote_row_is_not_a_narrow_text_contour():
    def line(text, left, right, top, size):
        char = PdfCharacter(
            char_unicode=text,
            pdf_style=PdfStyle(font_size=size),
            box=Box(x=left, y=top - size, x2=right, y2=top),
        )
        return PdfParagraphComposition(
            pdf_line=PdfLine(
                box=Box(x=left, y=top - size, x2=right, y2=top), pdf_character=[char]
            )
        )

    p = PdfParagraph(
        box=Box(x=312, y=339, x2=556, y2=471),
        unicode="Your partner “",
        pdf_paragraph_composition=[
            line("“", 312, 350.9, 470.9, 100),
            line("Your partner", 351.45, 531, 424, 18),
            line("might not", 351.45, 539, 403, 18),
        ],
    )
    samples = _lines_of(p)
    assert [(s.x0, s.y0) for s in samples] == [(351.45, 424.0), (351.45, 403.0)]


def test_large_right_side_callout_stays_in_its_source_pocket():
    from babeldoc.format.pdf.document_il.utils.rect_column_reflow import (
        stays_in_source_box,
    )

    quote = PdfParagraph(
        box=Box(x=312, y=339, x2=556, y2=440),
        pdf_paragraph_composition=[],
        unicode="Side callout",
    )
    quote.reference_metrics = SimpleNamespace(font_size=18, line_count=4)
    quote.layout_intent = SimpleNamespace(role=LayoutIntentRole.BODY)
    body = PdfParagraph(
        box=Box(x=56, y=140, x2=558, y2=464),
        pdf_paragraph_composition=[],
        unicode="Main wrap body",
    )
    body.reference_metrics = SimpleNamespace(font_size=14, line_count=18)
    body.layout_intent = SimpleNamespace(role=LayoutIntentRole.BODY)
    for index in range(18):
        top = 464 - index * 18
        right = 290 if 339 < top < 440 else 558
        char = PdfCharacter(
            char_unicode="Body",
            pdf_style=PdfStyle(font_size=14),
            box=Box(x=56, y=top - 14, x2=right, y2=top),
        )
        body.pdf_paragraph_composition.append(
            PdfParagraphComposition(
                pdf_line=PdfLine(box=char.box, pdf_character=[char])
            )
        )
    page = SimpleNamespace(
        pdf_paragraph=[body, quote],
        pdf_curve=[],
        cropbox=SimpleNamespace(box=Box(x=0, y=0, x2=612, y2=792)),
    )
    extract_intents(page)
    assert quote.layout_intent.role is LayoutIntentRole.PULL_QUOTE
    try:
        mark_display_bands(page)
        assert stays_in_source_box(quote)
    finally:
        forget_display_bands([quote], page)


def test_ordinary_large_right_column_body_is_not_a_fixed_callout():
    from babeldoc.format.pdf.document_il.utils.rect_column_reflow import (
        stays_in_source_box,
    )

    columns = []
    for left in [56, 312]:
        p = PdfParagraph(
            box=Box(x=left, y=339, x2=left + 244, y2=440),
            pdf_paragraph_composition=[],
            unicode="Column body",
        )
        p.reference_metrics = SimpleNamespace(font_size=18, line_count=4)
        p.layout_intent = SimpleNamespace(role=LayoutIntentRole.BODY)
        columns.append(p)
    page = SimpleNamespace(
        pdf_paragraph=columns,
        pdf_curve=[],
        cropbox=SimpleNamespace(box=Box(x=0, y=0, x2=612, y2=792)),
    )
    try:
        mark_display_bands(page)
        assert not any(stays_in_source_box(p) for p in columns)
    finally:
        forget_display_bands(columns, page)


@pytest.mark.parametrize(
    "role",
    [
        LayoutIntentRole.CHROME,
        LayoutIntentRole.FORMULA,
        LayoutIntentRole.FIGURE_CAPTION,
    ],
)
def test_side_callout_inference_preserves_explicit_non_body_roles(role):
    from babeldoc.format.pdf.document_il.utils.rect_column_reflow import (
        stays_in_source_box,
    )

    candidate = PdfParagraph(
        box=Box(x=312, y=339, x2=556, y2=440),
        pdf_paragraph_composition=[],
        unicode="Explicit role",
    )
    candidate.reference_metrics = SimpleNamespace(font_size=18, line_count=4)
    candidate.layout_intent = SimpleNamespace(role=role)
    body = PdfParagraph(
        box=Box(x=56, y=140, x2=558, y2=464),
        pdf_paragraph_composition=[],
        unicode="Body",
    )
    body.reference_metrics = SimpleNamespace(font_size=14, line_count=18)
    body.layout_intent = SimpleNamespace(role=LayoutIntentRole.BODY)
    page = SimpleNamespace(
        pdf_paragraph=[body, candidate],
        pdf_curve=[],
        cropbox=SimpleNamespace(box=Box(x=0, y=0, x2=612, y2=792)),
    )
    try:
        mark_display_bands(page)
        assert not stays_in_source_box(candidate)
    finally:
        forget_display_bands([body, candidate], page)
