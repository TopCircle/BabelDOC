"""SCAN and MATCH lines stay measurements and decisions."""

from babeldoc.format.pdf.document_il.utils.layout_plan.compose import build_plan
from babeldoc.format.pdf.document_il.utils.layout_plan.facts import SourceBlock
from babeldoc.format.pdf.document_il.utils.layout_plan.facts import build_facts
from babeldoc.format.pdf.document_il.utils.layout_plan.log import emit
from babeldoc.format.pdf.document_il.utils.layout_plan.log import records
from babeldoc.format.pdf.document_il.utils.layout_plan.measure import measure_region
from babeldoc.format.pdf.document_il.utils.layout_plan.model import FigureBox
from babeldoc.format.pdf.document_il.utils.layout_plan.model import LineBox


def _block(lines) -> SourceBlock:
    return SourceBlock(lines=tuple(LineBox(*line) for line in lines), role="body")


def _page(blocks, gate="single_page", figures=()):
    facts = build_facts(
        source_fingerprint="book",
        page_index=28,
        page_width=612,
        page_height=792,
        input_gate=gate,
        text_health=1.0,
        blocks=blocks,
        figures=figures,
    )
    return facts, build_plan(facts)


def test_scan_then_match_keeps_unmatched_empty():
    column = _block([(72, 400, 500), (72, 400, 482), (74, 398, 464)])
    short = _block([(72, 180, 400)])
    facts, plan = _page(
        [column, short],
        figures=(FigureBox(300, 450, 420, 520),),
    )
    rows = records(facts, plan)
    kinds = [row["kind"] for row in rows]
    assert kinds == ["SCAN", "MATCH", "SCAN", "MATCH", "PAGE"]
    assert rows[0]["page"] == 29
    assert rows[0]["lines"] == 3
    assert rows[0]["figs"] == 1
    measured = measure_region(facts.regions[0], facts.figures)
    assert rows[0]["left"] == [
        round(measured.left[0], 1),
        round(measured.left[1], 1),
    ]
    assert rows[0]["left_range"] == round(measured.left_range, 1)
    assert rows[0]["right_range"] == round(measured.right_range, 1)
    assert rows[0]["full_count"] == measured.full_count
    assert "rect_flow" not in rows[0]["line"]
    assert rows[0]["line"].startswith("SCAN page=29 ")
    assert rows[1]["status"] == "matched"
    # Base strategy stays rect_flow at confidence 0.9. The granted fill
    # is rect/light_column with residual 2. The log names that fill.
    # 0.9 is the confidence and must not appear as the residual.
    assert plan.decisions[0].base_strategy == "rect_flow"
    assert plan.decisions[0].confidence == 0.9
    assert rows[1]["paradigm"] == "rect/light_column"
    assert rows[1]["residual"] == 2.0
    assert "residual=2" in rows[1]["line"]
    assert "0.9" not in rows[1]["line"]
    assert rows[3]["status"] == "unmatched"
    assert rows[3]["paradigm"] == ""
    assert rows[3]["nearest"] == ""
    assert rows[3]["line"].endswith("residual= nearest=")
    assert rows[4]["line"] == (
        "PAGE page=29 blocks=2 matched=1 unmatched=1 gate=0 conflict=0"
    )


def test_a_closed_page_is_a_gate_not_an_unmatched_block():
    facts, plan = _page([_block([(72, 400, 500), (72, 400, 482)])], gate="bad_encoding")
    rows = records(facts, plan)
    assert rows[1]["status"] == "gate"
    assert rows[1]["paradigm"] == ""
    assert "gate=bad_encoding" in rows[1]["line"]
    assert rows[2]["unmatched"] == 0
    assert rows[2]["gate"] == 1


def test_emit_writes_every_block_and_says_the_unmatched_ones(caplog, tmp_path):
    facts, plan = _page(
        [
            _block([(72, 400, 500), (72, 400, 482), (74, 398, 464)]),
            _block([(72, 180, 400)]),
        ]
    )
    path = tmp_path / "layout-log.jsonl"
    with caplog.at_level("INFO", logger="babeldoc.layout_plan"):
        emit(facts, plan, path, console=True)
    text = path.read_text(encoding="utf-8")
    assert text.count("\n") == 5
    assert "SCAN page=29" in text
    assert "MATCH page=29" in text
    spoken = " ".join(caplog.messages)
    assert "status=unmatched" in spoken
    assert "status=matched" not in spoken
    assert "PAGE page=29" in spoken
