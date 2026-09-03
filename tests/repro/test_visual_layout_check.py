"""V1-V5 visual layout acceptance checks: unit tests (no pipeline / no assets).

Builds tiny synthetic run-dirs (typsetting.json + layout_intent.json +
paragraph_finder.json) and asserts the pass/fail logic of every assertion,
including deliberately broken negative cases (orphan line, repeated
sentence, dangling punctuation, CJK header, wrap right-edge drift, font
below min_scale, anchor/gap drift).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import visual_layout_check as vlc

GOLDEN_DIR = Path(__file__).resolve().parent / "golden"


# --------------------------------------------------------------------------
# Synthetic run-dir builder
# --------------------------------------------------------------------------


def make_para(
    debug_id: str,
    role: str,
    box: tuple[float, float, float, float],
    unicode: str,
    *,
    font_size: float = 12.0,
    scale: float = 1.0,
    lines: list[tuple[str, float, float, float, float]] | None = None,
    wrap_mode: str | None = None,
    design_box: tuple[float, float, float, float] | None = None,
    min_scale: float = 0.55,
    gap_contract: float | None = None,
    intent: bool = True,
) -> dict:
    """One typsetting.json paragraph dict.

    ``lines`` entries are ``(text, x0, y_top, y_bottom, char_width)``; default
    renders ``unicode`` as a single line at the box top.
    """
    if lines is None:
        lines = [(unicode, box[0], box[3], box[1], font_size)]
    compositions = []
    for text, x0, y_top, y_bottom, char_w in lines:
        x = x0
        for ch in text:
            compositions.append(
                {
                    "pdf_character": {
                        "char_unicode": ch,
                        "box": {"x": round(x, 3), "y": round(y_bottom, 3),
                                "x2": round(x + char_w, 3), "y2": round(y_top, 3)},
                    }
                }
            )
            x += char_w
    layout_intent = None
    if intent:
        layout_intent = {
            "role": role,
            "design_box": (
                {"x": design_box[0], "y": design_box[1], "x2": design_box[2], "y2": design_box[3]}
                if design_box
                else {"x": box[0], "y": box[1], "x2": box[2], "y2": box[3]}
            ),
            "wrap_mode": wrap_mode or "none",
            "min_scale": min_scale,
            "gap_contract": gap_contract,
            "top_inset": 0.0,
            "bottom_inset": 0.0,
        }
    return {
        "debug_id": debug_id,
        "box": {"x": box[0], "y": box[1], "x2": box[2], "y2": box[3]},
        "pdf_style": {"font_id": "f0", "font_size": font_size, "graphic_state": None},
        "scale": scale,
        "unicode": unicode,
        "layout_intent": layout_intent,
        "layout_label": role,
        "pdf_paragraph_composition": compositions,
    }


def make_run_dir(
    tmp_path: Path,
    paras: list[dict],
    *,
    page_key: str = "18",
    page_height: float = 792.0,
    write_layout_intent: bool = True,
) -> Path:
    """Write a minimal run-dir and return its path."""
    run = tmp_path / "run"
    run.mkdir(parents=True, exist_ok=True)
    page = {
        "page_number": int(page_key),
        "mediabox": {"x": 0, "y": 0, "x2": 612.0, "y2": page_height},
        "pdf_paragraph": paras,
    }
    (run / "typsetting.json").write_text(
        json.dumps({"page": [page], "total_pages": 1}, ensure_ascii=False), encoding="utf-8"
    )
    if write_layout_intent:
        entries = {}
        for i, p in enumerate(paras):
            if p.get("layout_intent") is not None:
                entries[p.get("debug_id") or f"para_{i}"] = p["layout_intent"]
        (run / "layout_intent.json").write_text(
            json.dumps({"pages": {page_key: entries}}, ensure_ascii=False), encoding="utf-8"
        )
    (run / "paragraph_finder.json").write_text(
        json.dumps({"page": [page], "total_pages": 1}, ensure_ascii=False), encoding="utf-8"
    )
    return run


def en_ref(
    *,
    page_no: int = 19,
    run_page_key: str = "18",
    anchors: list[dict] | None = None,
    invariants: dict | None = None,
) -> dict:
    return {
        "schema": "babeldoc-repro-en-blocks/v1",
        "source": "test",
        "page_no": page_no,
        "run_page_key": run_page_key,
        "page_size": [612.0, 792.0],
        "anchors": anchors or [],
        "invariants": invariants or {},
    }


def page_result(report: dict, page_key: str) -> dict[str, vlc.CheckResult]:
    return {c["item"]: c for c in report["pages"][page_key]["checks"]}


# --------------------------------------------------------------------------
# V1 anchors
# --------------------------------------------------------------------------


class TestV1Anchors:
    def test_anchor_aligned_passes(self, tmp_path):
        title = make_para("t", "title", (42, 653.3, 213, 693.5), "第三章", font_size=32.0)
        body = make_para("b", "pull_quote", (102, 557.8, 572, 572.9), "正文内容。", font_size=12.5)
        run = make_run_dir(tmp_path, [title, body])
        ref = en_ref(
            anchors=[
                {"id": "chapter_title", "kind": "chapter_title", "top": 693.5},
                {"id": "body_first_line_0", "kind": "body_first_line", "top": 572.9},
            ]
        )
        report = vlc.check_run_dir(run, ref)
        results = page_result(report, "18")
        assert results["V1.chapter_title"]["status"] == "PASS"
        assert results["V1.body_first_line_0"]["status"] == "PASS"
        assert report["all_pass"] is True

    def test_anchor_drift_fails(self, tmp_path):
        # Title box moved 10pt down (y-up: smaller y2 = lower on page).
        title = make_para("t", "title", (42, 653.3, 213, 683.5), "第三章", font_size=32.0)
        run = make_run_dir(tmp_path, [title])
        ref = en_ref(anchors=[{"id": "chapter_title", "kind": "chapter_title", "top": 693.5}])
        report = vlc.check_run_dir(run, ref)
        results = page_result(report, "18")
        assert results["V1.chapter_title"]["status"] == "FAIL"
        assert abs(results["V1.chapter_title"]["value"] - 10.0) < 1e-6

    def test_no_candidate_skips(self, tmp_path):
        # No title paragraph at all -> SKIP (not a silent pass).
        body = make_para("b", "body", (102, 100, 500, 120), "正文内容。")
        run = make_run_dir(tmp_path, [body])
        ref = en_ref(anchors=[{"id": "chapter_title", "kind": "chapter_title", "top": 693.5}])
        report = vlc.check_run_dir(run, ref)
        results = page_result(report, "18")
        assert results["V1.chapter_title"]["status"] == "SKIP"

    def test_placeholder_fragment_ignored(self, tmp_path):
        # A layout stub ("plain text") must not win anchor matching.
        stub = make_para(None, "body", (100, 571.3, 572, 573.7), "plain text")
        real = make_para("b", "pull_quote", (102, 557.8, 572, 579.7), "正文内容。", font_size=12.5)
        run = make_run_dir(tmp_path, [stub, real])
        ref = en_ref(anchors=[{"id": "body_first_line_0", "kind": "body_first_line", "top": 572.9}])
        report = vlc.check_run_dir(run, ref)
        results = page_result(report, "18")
        assert results["V1.body_first_line_0"]["status"] == "FAIL"  # matched real, drifted
        assert "b" in results["V1.body_first_line_0"]["detail"]


# --------------------------------------------------------------------------
# V2 gap
# --------------------------------------------------------------------------


class TestV2Gap:
    def _page(self, title_bottom: float, body_top: float) -> list[dict]:
        title = make_para(
            "t", "title", (42, title_bottom, 213, title_bottom + 40.0), "标题",
            font_size=32.0, gap_contract=18.0,
        )
        body = make_para("b", "body", (102, body_top - 15.0, 572, body_top), "正文内容。")
        return [title, body]

    def test_gap_matches_passes(self, tmp_path):
        # title ink bottom 590.9, body box top 572.9 -> zh gap 18 == en 18.
        run = make_run_dir(tmp_path, self._page(590.9, 572.9))
        ref = en_ref(invariants={"title_to_body_gaps": [18.0]})
        report = vlc.check_run_dir(run, ref)
        assert page_result(report, "18")["V2.gap"]["status"] == "PASS"

    def test_gap_drift_from_contract_fails(self, tmp_path):
        # Typesetting drifts from the EN contract (zh gap 22 vs contract 18).
        run = make_run_dir(tmp_path, self._page(590.9, 568.9))
        ref = en_ref(invariants={"title_to_body_gaps": [18.0]})
        report = vlc.check_run_dir(run, ref)
        results = page_result(report, "18")
        assert results["V2.gap"]["status"] == "FAIL"
        assert results["V2.gap"]["value"] == pytest.approx(4.0)
        assert "en_ref=18.00 (gap_contract)" in results["V2.gap"]["detail"]

    def test_gap_matches_contract_despite_golden_bbox_difference(self, tmp_path):
        # p19 case: EN golden direct measurement (18.0) includes font ascent
        # that CJK em boxes lack; the doc reference is gap_contract (19.54),
        # so |zh_gap - contract| <= 2 must PASS (the doc's 0.53).
        title = make_para(
            "t", "title", (42, 591.4, 213, 647.4), "成为行动派",
            font_size=56.0, gap_contract=19.54,
        )
        body = make_para("b", "body", (102, 556.33, 572, 571.33), "正文内容。")
        run = make_run_dir(tmp_path, [title, body])
        ref = en_ref(invariants={"title_to_body_gaps": [18.0]})
        report = vlc.check_run_dir(run, ref)
        results = page_result(report, "18")
        assert results["V2.gap"]["status"] == "PASS"
        assert results["V2.gap"]["value"] == pytest.approx(0.53, abs=0.02)
        # 1.54pt golden-vs-contract divergence is within the 3pt sanity band.
        assert "V2.gap_sanity" not in results

    def test_broken_contract_emits_sanity_warn(self, tmp_path):
        # Drop-cap-inclusive contract (11.2) matches typesetting exactly, so
        # the contract gate passes — but the extractor has regressed vs the
        # golden direct measurement and must surface as an advisory WARN.
        title = make_para(
            "t", "title", (42, 591.4, 213, 647.4), "成为行动派",
            font_size=56.0, gap_contract=11.2,
        )
        body = make_para("b", "body", (102, 565.2, 572, 580.2), "正文内容。")
        run = make_run_dir(tmp_path, [title, body])
        ref = en_ref(invariants={"title_to_body_gaps": [18.0]})
        report = vlc.check_run_dir(run, ref)
        results = page_result(report, "18")
        assert results["V2.gap"]["status"] == "PASS"
        assert results["V2.gap_sanity"]["status"] == "WARN"
        assert results["V2.gap_sanity"]["value"] == pytest.approx(6.8, abs=0.02)

    def test_no_title_skips(self, tmp_path):
        body = make_para("b", "body", (102, 100, 500, 120), "正文内容。")
        run = make_run_dir(tmp_path, [body])
        ref = en_ref(invariants={"title_to_body_gaps": [18.0]})
        report = vlc.check_run_dir(run, ref)
        assert page_result(report, "18")["V2.gap"]["status"] == "SKIP"

    def test_nearest_title_above_body_selected(self, tmp_path):
        # Two titles: the chapter title sits far above; the section title is
        # the one directly above the body and must drive the gap.
        chapter = make_para("c", "title", (42, 653.3, 213, 693.5), "第三章", font_size=32.0)
        section = make_para("s", "title", (45, 590.9, 570, 647.4), "成为行动派", font_size=56.0)
        body = make_para("b", "body", (102, 557.8, 572, 579.7), "正文内容。")
        run = make_run_dir(tmp_path, [chapter, section, body])
        ref = en_ref(invariants={"title_to_body_gaps": [11.2]})
        report = vlc.check_run_dir(run, ref)
        results = page_result(report, "18")
        assert results["V2.gap"]["status"] == "PASS"
        assert "title=s" in results["V2.gap"]["detail"]


# --------------------------------------------------------------------------
# V3 wrap / orphan / font scale
# --------------------------------------------------------------------------


class TestV3WrapRight:
    def _wrap_para(self, x0: float = 428.0) -> dict:
        # 6 CJK chars x 12pt -> line right edge = x0 + 72.0; design right 500.0.
        return make_para(
            "w", "wrap_column", (375.9, 234.9, 500.0, 284.9), "绕图列内容。",
            font_size=12.0, wrap_mode="right_fixed", design_box=(375.9, 234.9, 500.0, 284.9),
            lines=[("绕图列内容。", x0, 274.1, 262.1, 12.0)],
        )

    def test_pinned_to_design_right_passes(self, tmp_path):
        run = make_run_dir(tmp_path, [self._wrap_para(428.0)])
        report = vlc.check_run_dir(run, en_ref())
        assert page_result(report, "18")["V3.wrap_right"]["status"] == "PASS"

    def test_right_edge_drift_fails(self, tmp_path):
        # Line right edge at 502.0 vs design right 500.0 -> dev 2.0 > 0.5.
        run = make_run_dir(tmp_path, [self._wrap_para(430.0)])
        report = vlc.check_run_dir(run, en_ref())
        results = page_result(report, "18")
        assert results["V3.wrap_right"]["status"] == "FAIL"
        assert results["V3.wrap_right"]["value"]

    def test_no_wrap_skips(self, tmp_path):
        body = make_para("b", "body", (102, 100, 500, 120), "正文内容。")
        run = make_run_dir(tmp_path, [body])
        report = vlc.check_run_dir(run, en_ref())
        assert page_result(report, "18")["V3.wrap_right"]["status"] == "SKIP"


class TestV3Orphan:
    def _body(self, line_texts: list[str]) -> dict:
        fs = 12.0
        top = 400.0
        lines = []
        for text in line_texts:
            lines.append((text, 100.0, top, top - fs * 0.8, fs))  # CJK char width = fs
            top -= fs * 1.2
        return make_para("b", "body", (100, 100, 572, 420), "".join(line_texts),
                         font_size=fs, lines=lines)

    def test_no_orphan_passes(self, tmp_path):
        run = make_run_dir(tmp_path, [self._body(["这是正常的一行正文内容。", "这是第二行内容。"])])
        report = vlc.check_run_dir(run, en_ref())
        assert page_result(report, "18")["V3.orphan"]["status"] == "PASS"

    def test_single_char_mid_paragraph_fails(self, tmp_path):
        # '的' as a middle line: width 12 < 1.6*12=19.2 -> orphan FAIL.
        run = make_run_dir(tmp_path, [self._body(["这是正常的一行正文内容。", "的", "这是第三行内容。"])])
        report = vlc.check_run_dir(run, en_ref())
        results = page_result(report, "18")
        assert results["V3.orphan"]["status"] == "FAIL"
        assert any("的" in v for v in results["V3.orphan"]["value"])

    def test_single_char_last_line_allowed(self, tmp_path):
        # A short last line is a legal paragraph end, not an orphan.
        run = make_run_dir(tmp_path, [self._body(["这是正常的一行正文内容。", "的"])])
        report = vlc.check_run_dir(run, en_ref())
        assert page_result(report, "18")["V3.orphan"]["status"] == "PASS"


class TestV3FontScale:
    def test_above_min_scale_passes(self, tmp_path):
        para = make_para("b", "body", (100, 100, 500, 120), "正文。", font_size=12.0)
        run = make_run_dir(tmp_path, [para])
        ref = en_ref(invariants={"original_font_sizes": {"body": 12.5}})
        report = vlc.check_run_dir(run, ref)
        assert page_result(report, "18")["V3.font_scale"]["status"] == "PASS"

    def test_below_min_scale_fails(self, tmp_path):
        para = make_para("b", "body", (100, 100, 500, 120), "正文。", font_size=6.0)
        run = make_run_dir(tmp_path, [para])
        ref = en_ref(invariants={"original_font_sizes": {"body": 12.5}})
        report = vlc.check_run_dir(run, ref)
        results = page_result(report, "18")
        assert results["V3.font_scale"]["status"] == "FAIL"
        assert results["V3.font_scale"]["value"]


# --------------------------------------------------------------------------
# V4 repeats / dangling
# --------------------------------------------------------------------------


class TestV4Repeat:
    def test_no_repeat_passes(self, tmp_path):
        para = make_para("b", "body", (100, 100, 500, 120), "这是第一句。这是第二句。")
        run = make_run_dir(tmp_path, [para])
        report = vlc.check_run_dir(run, en_ref())
        assert page_result(report, "18")["V4.repeat"]["status"] == "PASS"

    def test_consecutive_repeat_fails(self, tmp_path):
        para = make_para(
            "b", "body", (100, 100, 500, 120), "这是第一句。这是第一句。这是第二句。"
        )
        run = make_run_dir(tmp_path, [para])
        report = vlc.check_run_dir(run, en_ref())
        results = page_result(report, "18")
        assert results["V4.repeat"]["status"] == "FAIL"
        assert results["V4.repeat"]["value"]["sentences"]

    def test_repeated_line_fails(self, tmp_path):
        fs = 12.0
        lines = [("重复的整行内容。", 100.0, 400.0, 390.4, fs),
                 ("重复的整行内容。", 100.0, 385.6, 376.0, fs)]
        para = make_para("b", "body", (100, 100, 572, 410), "重复的整行内容。",
                         font_size=fs, lines=lines)
        run = make_run_dir(tmp_path, [para])
        report = vlc.check_run_dir(run, en_ref())
        results = page_result(report, "18")
        assert results["V4.repeat"]["status"] == "FAIL"
        assert results["V4.repeat"]["value"]["lines"]

    def test_non_consecutive_repeat_not_blocking(self, tmp_path):
        # Same sentence twice but separated by other text: not a consecutive wall.
        para = make_para("b", "body", (100, 100, 500, 120), "第一句。第二句。第一句。")
        run = make_run_dir(tmp_path, [para])
        report = vlc.check_run_dir(run, en_ref())
        assert page_result(report, "18")["V4.repeat"]["status"] == "PASS"


class TestV4Dangling:
    def test_line_starting_with_sentence_end_fails(self, tmp_path):
        para = make_para("b", "body", (100, 100, 572, 130), "。开头就是标点",
                         lines=[("。开头就是标点", 100.0, 130.0, 120.4, 12.0)])
        run = make_run_dir(tmp_path, [para])
        report = vlc.check_run_dir(run, en_ref())
        assert page_result(report, "18")["V4.dangling"]["status"] == "FAIL"

    def test_line_ending_with_opening_bracket_fails(self, tmp_path):
        para = make_para("b", "body", (100, 100, 572, 130), "结尾是开括号（",
                         lines=[("结尾是开括号（", 100.0, 130.0, 120.4, 12.0)])
        run = make_run_dir(tmp_path, [para])
        report = vlc.check_run_dir(run, en_ref())
        assert page_result(report, "18")["V4.dangling"]["status"] == "FAIL"

    def test_clean_lines_pass(self, tmp_path):
        para = make_para("b", "body", (100, 100, 500, 130), "正常内容，没有悬挂标点。")
        run = make_run_dir(tmp_path, [para])
        report = vlc.check_run_dir(run, en_ref())
        assert page_result(report, "18")["V4.dangling"]["status"] == "PASS"


# --------------------------------------------------------------------------
# V5 callout / header
# --------------------------------------------------------------------------


class TestV5Callout:
    def test_callout_duplicates_body_fails(self, tmp_path):
        body = make_para("b", "body", (100, 300, 500, 320), "这里有一个关键句子。后面还有内容。")
        callout = make_para("c", "callout", (400, 300, 560, 330), "这里有一个关键句子。")
        run = make_run_dir(tmp_path, [body, callout])
        report = vlc.check_run_dir(run, en_ref())
        results = page_result(report, "18")
        assert results["V5.callout"]["status"] == "FAIL"
        assert results["V5.callout"]["value"]

    def test_callout_unique_passes(self, tmp_path):
        body = make_para("b", "body", (100, 300, 500, 320), "这里是正文内容。")
        callout = make_para("c", "callout", (400, 300, 560, 330), "这是侧栏独立内容。")
        run = make_run_dir(tmp_path, [body, callout])
        ref = en_ref(invariants={"callout_count": 1})
        report = vlc.check_run_dir(run, ref)
        assert page_result(report, "18")["V5.callout"]["status"] == "PASS"

    def test_callout_count_mismatch_warns_not_fails(self, tmp_path):
        body = make_para("b", "body", (100, 300, 500, 320), "这里是正文内容。")
        callout = make_para("c", "callout", (400, 300, 560, 330), "这是侧栏独立内容。")
        run = make_run_dir(tmp_path, [body, callout])
        ref = en_ref(invariants={"callout_count": 3})
        report = vlc.check_run_dir(run, ref)
        results = page_result(report, "18")
        assert results["V5.callout"]["status"] == "PASS"
        assert results["V5.callout_count"]["status"] == "WARN"
        assert report["all_pass"] is True


class TestV5Header:
    def _chrome(self, text: str, top: float) -> dict:
        return make_para("h", "chrome", (456, top - 46.0, 592, top), text, font_size=13.0)

    def test_header_cjk_fails(self, tmp_path):
        run = make_run_dir(tmp_path, [self._chrome("第三章 标题", 714.8)])
        report = vlc.check_run_dir(run, en_ref())
        assert page_result(report, "18")["V5.header"]["status"] == "FAIL"

    def test_header_kept_english_passes(self, tmp_path):
        run = make_run_dir(tmp_path, [self._chrome("Learn The Trigasm Basics", 714.8)])
        report = vlc.check_run_dir(run, en_ref())
        assert page_result(report, "18")["V5.header"]["status"] == "PASS"

    def test_footer_chrome_not_header_skips(self, tmp_path):
        run = make_run_dir(tmp_path, [self._chrome("www.GabrielleMoore.com", 52.2)])
        report = vlc.check_run_dir(run, en_ref())
        assert page_result(report, "18")["V5.header"]["status"] == "SKIP"


# --------------------------------------------------------------------------
# Golden references & end-to-end
# --------------------------------------------------------------------------


class TestEnGoldenReferences:
    @pytest.mark.parametrize("name", ["en_p19_blocks.json", "en_p82_blocks.json"])
    def test_golden_loads(self, name):
        ref = vlc.load_en_reference(GOLDEN_DIR / name)
        assert ref["schema"] == "babeldoc-repro-en-blocks/v1"
        assert ref["page_no"] in (19, 82)
        assert "anchors" in ref and "invariants" in ref

    def test_p82_body_anchors_match_acceptance_doc(self):
        # Acceptance doc: p82 body first lines at 147/207/252 (y-down)
        # == y-up 645/585/540; measured EN tops are 646.8/586.8/541.8.
        ref = vlc.load_en_reference(GOLDEN_DIR / "en_p82_blocks.json")
        tops = [
            a["top"] for a in ref["anchors"] if a["kind"] == "body_first_line"
        ]
        assert tops == pytest.approx([646.8, 586.8, 541.8], abs=0.5)
        assert ref["invariants"]["title_to_body_gaps"] == [21.8]

    def test_p19_gap_invariants(self):
        ref = vlc.load_en_reference(GOLDEN_DIR / "en_p19_blocks.json")
        assert ref["invariants"]["title_to_body_gaps"] == [18.0]
        kinds = {a["kind"] for a in ref["anchors"]}
        assert {"chapter_title", "section_title", "body_first_line"} <= kinds


class TestEndToEnd:
    def _good_page(self) -> list[dict]:
        title = make_para("t", "title", (42, 653.3, 213, 693.5), "第三章", font_size=32.0)
        section = make_para("s", "title", (45, 590.9, 570, 647.4), "成为行动派", font_size=56.0)
        body = make_para("b", "body", (102, 557.8, 572, 572.9), "这是正文第一句。这是正文第二句。",
                         font_size=12.5)
        wrap = make_para(
            "w", "wrap_column", (375.9, 234.9, 500.0, 284.9), "绕图列内容。",
            font_size=12.0, wrap_mode="right_fixed",
            design_box=(375.9, 234.9, 500.0, 284.9),
            lines=[("绕图列内容。", 428.0, 274.1, 262.1, 12.0)],
        )
        callout = make_para("c", "callout", (400, 600, 560, 630), "侧栏独立内容。")
        header = make_para("h", "chrome", (456, 668.5, 592, 714.8), "Learn The Trigasm Basics",
                           font_size=13.0)
        return [title, section, body, wrap, callout, header]

    def test_good_page_all_pass(self, tmp_path):
        run = make_run_dir(tmp_path, self._good_page())
        ref = en_ref(
            anchors=[
                {"id": "chapter_title", "kind": "chapter_title", "top": 693.5},
                {"id": "section_title", "kind": "section_title", "top": 647.4},
                {"id": "body_first_line_0", "kind": "body_first_line", "top": 572.9},
            ],
            invariants={
                "title_to_body_gaps": [18.0],
                "callout_count": 1,
                "original_font_sizes": {"title": 32.0, "section_title": 56.0, "body": 12.5,
                                        "wrap_column": 12.0, "callout": 15.0, "chrome": 13.0},
            },
        )
        report = vlc.check_run_dir(run, ref)
        assert report["all_pass"] is True
        assert report["summary"]["fail"] == 0
        assert report["summary"]["pass"] >= 9

    def test_orphan_breaks_all_pass(self, tmp_path):
        paras = self._good_page()
        # Inject a single-char orphan line into the body paragraph.
        body = paras[1]
        body["pdf_paragraph_composition"] = [
            {"pdf_character": {"char_unicode": c, "box": {"x": 100 + i * 12, "y": 550.0,
                                                          "x2": 112 + i * 12, "y2": 562.0}}}
            for i, c in enumerate("的")
        ]
        run = make_run_dir(tmp_path, paras)
        ref = en_ref(
            anchors=[{"id": "body_first_line_0", "kind": "body_first_line", "top": 572.9}],
            invariants={"original_font_sizes": {"body": 12.5, "wrap_column": 12.0,
                                                "title": 32.0, "callout": 15.0, "chrome": 13.0}},
        )
        report = vlc.check_run_dir(run, ref)
        assert report["all_pass"] is False
        results = page_result(report, "18")
        assert results["V3.orphan"]["status"] == "FAIL"
