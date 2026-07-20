"""Phase 0: figure dual baseline probe — pure metrics, no pipeline."""

from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest

from babeldoc.tools.figure_baseline_probe import (
    DEFAULT_CRUSH_RATIO_MAX,
    DEFAULT_MAX_LEFT_COL_GAP,
    DEFAULT_PAGE_CENTER,
    ProbeThresholds,
    evaluate_metrics,
    main as probe_main,
    probe_dual_pdf,
)

GOLDEN_DUAL = (
    Path(__file__).resolve().parent
    / "golden"
    / "translate.cli.text.with.figure.no_watermark.zh-CN.dual.pdf"
)


def _write_dual(
    path: Path,
    *,
    affil_x: float = 150.0,
    body_size: float = 10.0,
    tiny_ratio_lines: int = 0,
    big_gap: bool = False,
    fig_label_in_body: bool = False,
) -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=1224, height=792)
    zh = "china-s"
    # Affiliation with keyword so detector fires; x controls mid approx.
    affil = "Department of Applied Physics, Yale University"
    page.insert_text((affil_x, 100), affil, fontsize=10, fontname="helv")
    y = 200.0
    page.insert_text(
        (72, y), "这是正文第一行用于探测。" * 3, fontsize=body_size, fontname=zh
    )
    y += 20 if not big_gap else 150
    page.insert_text(
        (72, y), "这是正文第二行继续。" * 3, fontsize=body_size, fontname=zh
    )
    y += 20
    body2 = "第三行正文。" * 4
    if fig_label_in_body:
        body2 = "Ancilla 通道与正文混排 " + body2
    page.insert_text((72, y), body2, fontsize=body_size, fontname=zh)
    for i in range(tiny_ratio_lines):
        page.insert_text((72, 400 + i * 8), "微小" * 20, fontsize=5.0, fontname=zh)
    # Right half EN filler
    page.insert_text((612 + 72, 80), "English half", fontsize=12, fontname="helv")
    doc.save(path)
    doc.close()


class TestEvaluateMetrics:
    def test_pass_baseline_like(self):
        fails = evaluate_metrics(
            affil_mid=306.0,
            crush_ratio=0.015,
            max_left_col_gap=76.0,
            fig_label_hits=[],
            thresholds=ProbeThresholds(),
        )
        assert fails == []

    def test_fail_affil_off_center(self):
        fails = evaluate_metrics(
            affil_mid=100.0,
            crush_ratio=0.01,
            max_left_col_gap=50.0,
            fig_label_hits=[],
            thresholds=ProbeThresholds(),
        )
        assert any(f.startswith("affil_mid:") for f in fails)

    def test_fail_crush(self):
        fails = evaluate_metrics(
            affil_mid=306.0,
            crush_ratio=0.20,
            max_left_col_gap=50.0,
            fig_label_hits=[],
            thresholds=ProbeThresholds(),
        )
        assert any(f.startswith("crush_ratio:") for f in fails)

    def test_fail_gap(self):
        fails = evaluate_metrics(
            affil_mid=306.0,
            crush_ratio=0.01,
            max_left_col_gap=200.0,
            fig_label_hits=[],
            thresholds=ProbeThresholds(),
        )
        assert any(f.startswith("max_left_col_gap:") for f in fails)

    def test_fail_fig_labels(self):
        fails = evaluate_metrics(
            affil_mid=306.0,
            crush_ratio=0.01,
            max_left_col_gap=50.0,
            fig_label_hits=["Ancilla"],
            thresholds=ProbeThresholds(),
        )
        assert any(f.startswith("fig_label_hits:") for f in fails)

    def test_missing_affil_ok_unless_required(self):
        fails = evaluate_metrics(
            affil_mid=None,
            crush_ratio=0.01,
            max_left_col_gap=50.0,
            fig_label_hits=[],
            thresholds=ProbeThresholds(),
            require_affil=False,
        )
        assert fails == []
        fails_req = evaluate_metrics(
            affil_mid=None,
            crush_ratio=0.01,
            max_left_col_gap=50.0,
            fig_label_hits=[],
            thresholds=ProbeThresholds(),
            require_affil=True,
        )
        assert any("affil_mid" in f for f in fails_req)


class TestProbeDualPdf:
    def test_synthetic_pass(self, tmp_path: Path):
        pdf = tmp_path / "ok_dual.pdf"
        # Place affil so glyph mid is near 306 (string starts ~150 for ~10pt)
        _write_dual(pdf, affil_x=150.0, body_size=10.0)
        result = probe_dual_pdf(pdf, half="left")
        assert result.half == "left"
        assert result.cjk_chars > 0
        assert result.crush_ratio <= DEFAULT_CRUSH_RATIO_MAX
        assert result.max_left_col_gap <= DEFAULT_MAX_LEFT_COL_GAP
        # affil may or may not be exact; crush/gap/fig must pass
        assert not any(f.startswith("crush_ratio:") for f in result.failures)
        assert not any(f.startswith("max_left_col_gap:") for f in result.failures)
        assert not any(f.startswith("fig_label_hits:") for f in result.failures)

    def test_synthetic_crush_fail(self, tmp_path: Path):
        pdf = tmp_path / "crush_dual.pdf"
        _write_dual(pdf, body_size=10.0, tiny_ratio_lines=40)
        result = probe_dual_pdf(pdf, half="left")
        assert result.crush_ratio > DEFAULT_CRUSH_RATIO_MAX
        assert not result.ok
        assert any(f.startswith("crush_ratio:") for f in result.failures)

    def test_synthetic_fig_label_fail(self, tmp_path: Path):
        pdf = tmp_path / "figmix_dual.pdf"
        _write_dual(pdf, fig_label_in_body=True)
        result = probe_dual_pdf(pdf, half="left")
        assert "Ancilla" in result.fig_label_hits
        assert not result.ok

    def test_auto_picks_cjk_half(self, tmp_path: Path):
        pdf = tmp_path / "auto_dual.pdf"
        _write_dual(pdf)
        result = probe_dual_pdf(pdf, half="auto")
        assert result.half == "left"
        assert result.cjk_chars > 0

    @pytest.mark.skipif(not GOLDEN_DUAL.is_file(), reason="local figure dual PDF missing")
    def test_golden_figure_dual_passes_hard_gates(self):
        """Local operator dual — must stay green while dual-layer recovers."""
        result = probe_dual_pdf(GOLDEN_DUAL, half="auto", require_affil=False)
        assert result.cjk_chars > 100
        assert result.crush_ratio <= DEFAULT_CRUSH_RATIO_MAX
        assert result.max_left_col_gap <= DEFAULT_MAX_LEFT_COL_GAP
        assert result.fig_label_hits == []
        if result.affil_mid is not None:
            assert abs(result.affil_mid - DEFAULT_PAGE_CENTER) <= 25.0
        assert result.ok, result.failures


class TestCli:
    def test_self_check_exit_zero(self):
        assert probe_main(["--self-check", "--work-dir", "/tmp/babeldoc_probe_sc"]) == 0

    def test_missing_dual_exit_2(self):
        assert probe_main([]) == 2
