"""Paragraphs the seal keeps together are one paragraph before fill."""

from babeldoc.format.pdf.document_il.utils.mixed_column_split import (
    split_mixed_column_wraps,
)
from babeldoc.format.pdf.document_il.utils.rect_flow_stack import _lines_of
from babeldoc.format.pdf.document_il.utils.rect_flow_stack import attach_layout_plans
from babeldoc.format.pdf.document_il.utils.sealed_paragraph_join import (
    join_sealed_paragraphs,
)


class _Box:
    def __init__(self, x, y, x2, y2):
        self.x = x
        self.y = y
        self.x2 = x2
        self.y2 = y2


class _Docs:
    def __init__(self, pages):
        self.page = pages


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
        lines[0][0],
        lines[-1][2] - 10,
        max(line[1] for line in lines),
        lines[0][2],
    )
    paragraph.unicode = text
    paragraph.layout_label = None
    paragraph.layout_region_id = None
    paragraph.layout_intent = type(
        "_Intent",
        (),
        {
            "role": type("_Role", (), {"value": "body"})(),
            "text_on_photo": False,
        },
    )()
    paragraph.pdf_paragraph_composition = compositions
    return paragraph


def _page(paragraphs):
    box = _Box(0, 0, 612, 792)
    page = type("_Page", (), {})()
    page.page_number = 21
    page.cropbox = type("_Holder", (), {"box": box})()
    page.mediabox = page.cropbox
    page.pdf_paragraph = paragraphs
    page.layout_plan = None
    page.pdf_figure = []
    page.pdf_form = []
    return page


def _column(count, y_top, x1=320.0, last_x1=None):
    lines = []
    for index in range(count):
        right = x1 if last_x1 is None or index < count - 1 else last_x1
        lines.append((36.0, right, y_top - 18.0 * index))
    return lines


def test_slices_of_one_sealed_column_become_one_paragraph():
    sentence = "Another thing you can try is a long readable sentence. "
    rights = [
        320.0, 314.0, 318.0, 312.0, 316.0, 320.0, 315.0, 311.0,
        317.0, 313.0, 319.0, 314.0, 316.0, 312.0, 180.0,
    ]
    lines = [(36.0, right, 500.0 - 18.0 * index) for index, right in enumerate(rights)]
    bounds = (0, 9, 10, 12, 14, 15)
    pieces = [
        _paragraph(lines[bounds[index] : bounds[index + 1]], sentence)
        for index in range(len(bounds) - 1)
    ]
    above = _paragraph(_column(4, 500.0 + 27.0 + 18.0 * 3), sentence * 4)
    title = _paragraph([(41.0, 300.0, lines[-1][2] - 36.0)], "The title stays put.")
    page = _page([above, *pieces, title])
    join_sealed_paragraphs(page)
    assert [len(_lines_of(paragraph)) for paragraph in page.pdf_paragraph] == [
        4,
        15,
        1,
    ]
    assert "Another thing" in page.pdf_paragraph[1].unicode
    assert attach_layout_plans(_Docs([page])) is True
    edges = page.layout_plan.line_edge_links
    column = next(link for link in edges if len(link.edges) == 15)
    assert {edge[0] for edge in column.edges} == {36.0}
    assert {edge[1] for edge in column.edges} == {320.0}


def test_a_left_jump_stays_two_paragraphs():
    upper = _paragraph(_column(4, 400.0), "Upper column stays here. ")
    lower_lines = [(80.0, 300.0, 400.0 - 18.0 * 4 - 18.0 * index) for index in range(4)]
    lower = _paragraph(lower_lines, "Lower column starts inward. ")
    page = _page([upper, lower])
    join_sealed_paragraphs(page)
    assert len(page.pdf_paragraph) == 2


def test_a_leader_beside_one_line_is_not_absorbed():
    host = _paragraph([(100.0, 320.0, 200.0)], "Go to the contents page.")
    leader = _paragraph([(36.0, 70.0, 200.0)], "www.example.com")
    page = _page([leader, host])
    join_sealed_paragraphs(page)
    assert len(page.pdf_paragraph) == 2
    assert page.pdf_paragraph[0].unicode == "www.example.com"


def test_a_joined_stair_can_still_be_cut_apart():
    straight = [(102.0, 510.0, 500.0 - 15.0 * index) for index in range(4)]
    stair = [
        (102.0, 480.0 - 50.0 * index, 440.0 - 15.0 * index) for index in range(5)
    ]
    page = _page(
        [
            _paragraph(straight, "The straight run ends here. "),
            _paragraph(stair, "The wrap steps inward from there. "),
        ],
    )
    join_sealed_paragraphs(page)
    split_mixed_column_wraps(page)
    assert [len(_lines_of(paragraph)) for paragraph in page.pdf_paragraph] == [4, 5]


def test_one_paragraph_is_left_where_it_is():
    only = _paragraph(_column(6, 400.0), "Already one block. ")
    page = _page([only])
    join_sealed_paragraphs(page)
    assert page.pdf_paragraph == [only]


def test_list_items_with_markers_are_not_joined():
    item1 = _paragraph([(36.0, 300.0, 400.0), (54.0, 300.0, 382.0)], "• First bullet point.")
    item2 = _paragraph([(36.0, 300.0, 364.0), (54.0, 300.0, 346.0)], "• Second bullet point.")
    page = _page([item1, item2])
    join_sealed_paragraphs(page)
    assert len(page.pdf_paragraph) == 2
    assert "First" in page.pdf_paragraph[0].unicode
    assert "Second" in page.pdf_paragraph[1].unicode


def test_toc_items_with_leaders_are_not_joined():
    toc1 = _paragraph([(36.0, 300.0, 400.0)], "Introduction ............ 1")
    toc2 = _paragraph([(36.0, 300.0, 380.0)], "Chapter 1 ............... 5")
    page = _page([toc1, toc2])
    join_sealed_paragraphs(page)
    assert len(page.pdf_paragraph) == 2

