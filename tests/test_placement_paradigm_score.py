"""Scorer for placement guesses on a local page pair."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "eval" / "placement_paradigm_score.py"


def _write_pair(path: Path) -> None:
    """Page 1 is one stable column. Page 2 is a four-line right-pinned taper."""
    font = fitz.Font("cour")
    size = 12.0

    def text_for_width(width: float) -> str:
        count = 1
        while font.text_length("m" * (count + 1), fontsize=size) <= width:
            count += 1
        return "m" * count

    document = fitz.open()
    stable = document.new_page(width=612, height=792)
    stable_text = text_for_width(420.0)
    for index in range(4):
        stable.insert_text(
            (102, 180 + index * 16),
            stable_text,
            fontsize=size,
            fontname="cour",
        )

    taper = document.new_page(width=612, height=792)
    right = 520.0
    for index in range(4):
        left = 100.0 + 30.0 * index
        taper.insert_text(
            (left, 180 + index * 16),
            text_for_width(right - left),
            fontsize=size,
            fontname="cour",
        )
    document.save(path)
    document.close()


def _run(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def test_score_prints_rect_and_shaped(tmp_path: Path):
    pdf = tmp_path / "pair.pdf"
    _write_pair(pdf)
    result = _run(
        "--en",
        str(pdf),
        "--zh",
        str(pdf),
        "--pages",
        "1,2",
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert "rect_reflow" in result.stdout
    assert "shaped_pocket" in result.stdout


def test_score_missing_file_exits_2(tmp_path: Path):
    missing = tmp_path / "absent.pdf"
    result = _run(
        "--en",
        str(missing),
        "--zh",
        str(missing),
        "--pages",
        "1",
        cwd=tmp_path,
    )
    assert result.returncode == 2
    assert "can't open file" not in result.stderr
    assert list(tmp_path.iterdir()) == []
