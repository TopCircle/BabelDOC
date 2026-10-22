"""A line-end that still touches its line goes back on that line."""

from babeldoc.format.pdf.document_il.utils.line_tail_stitch import (
    stitch_abutting_line_tails,
)


class _Box:
    def __init__(self, x, y, x2, y2):
        self.x = x
        self.y = y
        self.x2 = x2
        self.y2 = y2


def _paragraph(lines, text):
    compositions = []
    for x0, x1, y0 in lines:
        compositions.append(
            type(
                "_Comp",
                (),
                {
                    "pdf_line": type(
                        "_Line",
                        (),
                        {
                            "box": _Box(x0, y0 - 10, x1, y0),
                            "pdf_character": [],
                        },
                    )(),
                    "pdf_character": None,
                    "pdf_formula": None,
                    "pdf_same_style_characters": None,
                },
            )(),
        )
    paragraph = type("_Para", (), {})()
    paragraph.box = _Box(
        min(line[0] for line in lines),
        lines[-1][2] - 10,
        max(line[1] for line in lines),
        lines[0][2],
    )
    paragraph.unicode = text
    paragraph.pdf_paragraph_composition = compositions
    return paragraph


def _page(paragraphs):
    page = type("_Page", (), {})()
    page.pdf_paragraph = paragraphs
    return page


def _rights(paragraph):
    rights = []
    for composition in paragraph.pdf_paragraph_composition:
        rights.append(composition.pdf_line.box.x2)
    return rights


def test_a_tail_that_touches_the_line_goes_back():
    host = _paragraph(
        [
            (210.0, 511.6, 228.3),
            (206.0, 511.0, 213.3),
            (187.0, 422.9, 153.3),
            (181.0, 244.9, 138.3),
            (174.0, 328.0, 123.3),
        ],
        "Some women",
    )
    tail = _paragraph(
        [
            (422.7, 510.0, 153.3),
            (244.7, 510.0, 138.3),
        ],
        "’s really",
    )
    page = _page([host, tail])

    stitch_abutting_line_tails(page)

    assert page.pdf_paragraph == [host]
    assert _rights(host) == [511.6, 511.0, 510.0, 510.0, 328.0]


def test_a_gap_stays_two_paragraphs():
    host = _paragraph([(187.0, 400.0, 153.3)], "There")
    tail = _paragraph([(412.0, 510.0, 153.3)], "really")
    page = _page([host, tail])

    stitch_abutting_line_tails(page)

    assert page.pdf_paragraph == [host, tail]
    assert host.pdf_paragraph_composition[0].pdf_line.box.x2 == 400.0


def test_a_line_on_the_left_is_not_a_tail():
    body = _paragraph([(210.0, 512.0, 228.0)], "Some women")
    quote = _paragraph([(55.8, 182.0, 226.0)], "making session.")
    page = _page([body, quote])

    stitch_abutting_line_tails(page)

    assert page.pdf_paragraph == [body, quote]


def test_a_partial_tail_stays_apart():
    host = _paragraph(
        [
            (187.0, 422.9, 153.3),
            (181.0, 510.0, 138.3),
        ],
        "There",
    )
    tail = _paragraph(
        [
            (422.7, 510.0, 153.3),
            (300.0, 400.0, 100.0),
        ],
        "’s really",
    )
    page = _page([host, tail])

    stitch_abutting_line_tails(page)

    assert page.pdf_paragraph == [host, tail]
