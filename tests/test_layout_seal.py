"""The seal cuts on pitch, left edge, and column. It does not name a shape."""

from pathlib import Path

from babeldoc.format.pdf.document_il.utils.layout_plan.model import LineBox
from babeldoc.format.pdf.document_il.utils.layout_plan.model import geometry_digest
from babeldoc.format.pdf.document_il.utils.layout_plan.model import make_region_id
from babeldoc.format.pdf.document_il.utils.layout_plan.seal import seal_lines

_SEAL = (
    Path(__file__).parents[1]
    / "babeldoc/format/pdf/document_il/utils/layout_plan/seal.py"
)


def _lines(*rows: tuple[float, float, float]) -> tuple[LineBox, ...]:
    return tuple(LineBox(*row) for row in rows)


def test_a_short_last_line_stays_when_the_right_edge_steps_in():
    blocks = seal_lines(
        _lines(
            (72, 400, 500),
            (72, 360, 485),
            (72, 200, 470),
            (72, 400, 440),
            (72, 180, 425),
        )
    )
    assert [len(block.lines) for block in blocks] == [3, 2]
    assert blocks[1].opened_by == "gap"
    assert blocks[0].lines[-1].x1 == 200


def test_a_narrow_line_between_full_lines_is_not_dropped():
    blocks = seal_lines(
        _lines(
            (72, 400, 500),
            (72, 110, 485),
            (72, 400, 470),
        )
    )
    assert len(blocks) == 1
    assert len(blocks[0].lines) == 3


def test_a_left_jump_opens_a_block_and_a_right_edge_change_does_not():
    blocks = seal_lines(
        _lines(
            (72, 400, 500),
            (72, 380, 485),
            (110, 400, 470),
            (110, 360, 455),
        )
    )
    assert [len(block.lines) for block in blocks] == [2, 2]
    assert blocks[1].opened_by == "left"


def test_a_hanging_run_stops_at_the_next_run():
    blocks = seal_lines(
        _lines(
            (100, 420, 500),
            (118, 400, 484),
            (100, 420, 452),
            (118, 380, 436),
        )
    )
    assert [len(block.lines) for block in blocks] == [2, 2]
    assert blocks[1].opened_by == "gap"


def test_one_right_step_hangs_and_the_next_paragraph_gap_opens():
    blocks = seal_lines(
        _lines(
            (100, 420, 500),
            (118, 400, 484),
            (118, 360, 468),
            (100, 420, 430),
        )
    )
    assert [len(block.lines) for block in blocks] == [3, 1]
    assert blocks[1].opened_by == "gap"


def test_two_columns_on_the_same_rows_stay_two_blocks():
    blocks = seal_lines(
        _lines(
            (72, 280, 500),
            (360, 560, 500),
            (72, 280, 485),
            (360, 560, 485),
        )
    )
    assert [len(block.lines) for block in blocks] == [2, 2]
    assert blocks[1].opened_by == "column"
    assert blocks[0].lines[0].x0 == 72
    assert blocks[1].lines[0].x0 == 360


def test_a_first_line_indent_stays_when_the_right_wall_matches():
    blocks = seal_lines(
        _lines(
            (110, 400, 500),
            (72, 400, 485),
            (72, 360, 470),
        )
    )
    assert len(blocks) == 1
    assert [line.x0 for line in blocks[0].lines] == [110, 72, 72]
    assert blocks[0].leaders == ()


def test_a_left_step_off_the_right_wall_opens_a_block():
    blocks = seal_lines(
        _lines(
            (180, 250, 500),
            (72, 400, 485),
            (72, 400, 470),
        )
    )
    assert [len(block.lines) for block in blocks] == [1, 2]
    assert blocks[1].opened_by == "left"


def test_a_later_left_step_still_opens_a_block():
    blocks = seal_lines(
        _lines(
            (72, 400, 500),
            (72, 400, 485),
            (40, 400, 470),
        )
    )
    assert [len(block.lines) for block in blocks] == [2, 1]
    assert blocks[1].opened_by == "left"


def test_a_short_left_token_is_a_leader_not_an_edge():
    number = LineBox(125, 146, 500)
    blocks = seal_lines(
        (
            number,
            LineBox(161, 526, 500),
            LineBox(140, 526, 485),
            LineBox(140, 513, 470),
        )
    )
    assert len(blocks) == 1
    assert [line.x0 for line in blocks[0].lines] == [161, 140, 140]
    assert blocks[0].leaders == (number,)
    assert number.x0 not in [line.x0 for line in blocks[0].lines]


def test_a_later_full_line_on_the_same_left_does_not_keep_the_token():
    number = LineBox(125, 146, 500)
    blocks = seal_lines(
        (
            number,
            LineBox(161, 526, 500),
            LineBox(140, 526, 485),
            LineBox(125, 526, 200),
        )
    )
    assert [len(block.lines) for block in blocks] == [2, 1]
    assert blocks[0].leaders == (number,)


def test_a_wide_line_beside_a_short_line_stays_its_own_block():
    blocks = seal_lines(_lines((36, 83, 700), (96, 104, 700)))
    assert [len(block.lines) for block in blocks] == [1, 1]
    assert blocks[0].leaders == ()
    assert blocks[1].leaders == ()


def test_a_left_walk_past_the_edge_tolerance_does_not_stay_one_block():
    blocks = seal_lines(
        _lines(*[(300 + 20 * index, 520, 400 - 15 * index) for index in range(6)])
    )
    assert len(blocks) > 1
    assert blocks[0].opened_by == "page"


def test_the_block_id_is_the_geometry_digest_only():
    lines = _lines((72, 400, 500), (72, 400, 485))
    blocks = seal_lines(lines)
    assert len(blocks) == 1
    assert blocks[0].block_id == geometry_digest(blocks[0].lines)
    assert len(blocks[0].block_id) == 16
    assert blocks[0].block_id != make_region_id("book", 0, 0, lines)
    assert "paradigm" not in blocks[0].to_dict()


def test_no_lines_seals_nothing():
    assert seal_lines(()) == ()


def test_the_cutter_does_not_name_a_shape():
    text = _SEAL.read_text(encoding="utf-8")
    for banned in ("rect_flow", "shaped_pocket", "is_taper", "select_paradigm"):
        assert banned not in text
