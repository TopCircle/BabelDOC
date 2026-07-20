"""S1.1: dual text-layer metrics — synth PDF only (no ONNX / large duals)."""

from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest

from babeldoc.tools.dual_layout_metrics import (
    DualLayoutReport,
    analyze_dual_pdf,
    parse_pages_spec,
)
from babeldoc.tools.dual_quality_check import main as dual_quality_main


def _write_dual(
    path: Path,
    *,
    body_size: float = 10.0,
    tiny_lines: int = 0,
    soh: bool = False,
    big_gap: bool = False,
) -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=1224, height=792)
    zh = "china-s"
    y = 200.0
    page.insert_text(
        (72, y), "这是正文第一行用于探测。" * 3, fontsize=body_size, fontname=zh
    )
    y += 20 if not big_gap else 150
    page.insert_text(
        (72, y), "这是正文第二行继续。" * 3, fontsize=body_size, fontname=zh
    )
    y += 20
    page.insert_text((72, y), "第三行正文。" * 4, fontsize=body_size, fontname=zh)
    for i in range(tiny_lines):
        page.insert_text((72, 400 + i * 8), "微小" * 20, fontsize=4.0, fontname=zh)
    if soh:
        # Embed SOH via TextWriter / raw insert if possible
        page.insert_text((72, 500), "控制\x01字符", fontsize=10, fontname=zh)
    page.insert_text((612 + 72, 80), "English half", fontsize=12, fontname="helv")
    doc.save(path)
    doc.close()


class TestParsePagesSpec:
    def test_none(self):
        assert parse_pages_spec(None) is None
        assert parse_pages_spec("") is None

    def test_range_and_list(self):
        assert parse_pages_spec("4-6,10") == [4, 5, 6, 10]
        assert parse_pages_spec("1") == [1]

    def test_rejects_zero_based(self):
        with pytest.raises(ValueError):
            parse_pages_spec("0")


class TestAnalyzeDualPdf:
    def test_ok_page(self, tmp_path: Path):
        pdf = tmp_path / "ok.pdf"
        _write_dual(pdf)
        rep = analyze_dual_pdf(pdf, half="left", profile="default")
        assert isinstance(rep, DualLayoutReport)
        assert rep.ok
        assert len(rep.pages) == 1
        pm = rep.pages[0]
        assert pm.failures == []
        assert pm.cjk_chars > 0
        assert pm.crush_ratio < 0.10

    def test_crush_fails(self, tmp_path: Path):
        pdf = tmp_path / "crush.pdf"
        # Many tiny glyphs → crush_ratio high
        _write_dual(pdf, tiny_lines=40)
        rep = analyze_dual_pdf(pdf, half="left")
        assert not rep.ok
        assert "crush" in rep.pages[0].failures or "min_font" in rep.pages[0].failures

    def test_soh_fails(self, tmp_path: Path):
        pdf = tmp_path / "soh.pdf"
        _write_dual(pdf, soh=True)
        rep = analyze_dual_pdf(pdf, half="left")
        # Some PDF writers drop SOH; if preserved must fail
        if rep.pages[0].soh_hits > 0:
            assert not rep.ok
            assert "soh" in rep.pages[0].failures
        else:
            pytest.skip("PDF writer stripped SOH control char from text layer")

    def test_big_gap_soft_default(self, tmp_path: Path):
        pdf = tmp_path / "gap.pdf"
        _write_dual(pdf, big_gap=True)
        rep = analyze_dual_pdf(pdf, half="left", profile="default")
        pm = rep.pages[0]
        # large gap may or may not exceed 120 depending on insert_text metrics;
        # default must not hard-fail on vgap alone when only warning applies
        if pm.max_left_col_gap > 120:
            assert "vgap" in pm.warnings
            assert "vgap" not in pm.failures
            # still ok if no crush/soh/min_font
            if not any(c in pm.failures for c in ("crush", "min_font", "soh")):
                assert pm.ok

    def test_pages_1_based(self, tmp_path: Path):
        pdf = tmp_path / "multi.pdf"
        doc = pymupdf.open()
        for _ in range(3):
            p = doc.new_page(width=612, height=792)
            p.insert_text((72, 100), "Hello body text here.", fontsize=11, fontname="helv")
        doc.save(pdf)
        doc.close()
        rep = analyze_dual_pdf(pdf, pages=[2], half="full")
        assert len(rep.pages) == 1
        assert rep.pages[0].page_index == 1

    def test_json_roundtrip_shape(self, tmp_path: Path):
        pdf = tmp_path / "ok.pdf"
        _write_dual(pdf)
        rep = analyze_dual_pdf(pdf, half="left")
        data = rep.to_json()
        assert data["ok"] is True
        assert data["profile"] == "default"
        assert "pages" in data


class TestDualQualityCliMetrics:
    def test_dual_ok_exit_0(self, tmp_path: Path, capsys):
        pdf = tmp_path / "ok.pdf"
        _write_dual(pdf)
        code = dual_quality_main(["--dual", str(pdf), "--half", "left"])
        assert code == 0
        out = capsys.readouterr().out
        assert "PASS" in out or "p1" in out

    def test_dual_crush_exit_1(self, tmp_path: Path):
        pdf = tmp_path / "crush.pdf"
        _write_dual(pdf, tiny_lines=40)
        code = dual_quality_main(["--dual", str(pdf), "--half", "left"])
        assert code == 1

    def test_dual_and_ssim_mutex(self, tmp_path: Path, capsys):
        pdf = tmp_path / "ok.pdf"
        _write_dual(pdf)
        code = dual_quality_main(
            [
                "--dual",
                str(pdf),
                "--mode",
                "ssim",
                "--actual-png",
                "a.png",
                "--expected-png",
                "b.png",
            ]
        )
        assert code == 2
        err = capsys.readouterr().err.lower()
        assert "ssim" in err or "dual" in err or "exclusive" in err or "mutex" in err

    def test_missing_dual_file(self, tmp_path: Path):
        code = dual_quality_main(["--dual", str(tmp_path / "nope.pdf")])
        assert code == 2
