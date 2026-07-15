"""ToUnicode must keep blank spacing glyphs (space = glyph 1).

Without this, Identity-H dual PDFs extract spaces as U+0001 SOH.
"""

from __future__ import annotations

import io
import os
import re
from pathlib import Path

import freetype
import pymupdf
import pytest

from babeldoc.format.pdf.document_il.backend.pdf_creater import make_tounicode
from babeldoc.format.pdf.document_il.backend.pdf_creater import parse_truetype_data
from babeldoc.format.pdf.document_il.backend.pdf_creater import reproduce_cmap


FONT_PATH = Path(
    os.path.expanduser("~/.cache/babeldoc/fonts/SourceHanSerifCN-Regular.ttf")
)


@pytest.mark.skipif(not FONT_PATH.is_file(), reason="SourceHanSerifCN not cached")
class TestParseTrueTypeIncludesSpace:
    def test_space_glyph_1_included(self):
        data = FONT_PATH.read_bytes()
        used = parse_truetype_data(data)
        assert 1 in used, "glyph 1 (space) must stay for ToUnicode"

        face = freetype.Face(io.BytesIO(data))
        face.load_glyph(1)
        assert not face.glyph.outline.contours
        assert face.glyph.metrics.horiAdvance > 0


class TestMakeToUnicodeSpace:
    def test_forces_space_mapping_when_missing_from_cmap(self):
        # used contains glyph 1; cmap empty → still emit <0001><0020>
        text = make_tounicode({}, [1, 2])
        assert re.search(r"<0001><0020>", text, re.I)

    def test_keeps_existing_space_mapping(self):
        text = make_tounicode({1: 0x0020, 2: 0x0021}, [1, 2])
        assert re.search(r"<0001><0020>", text, re.I)
        assert re.search(r"<0002><0021>", text, re.I)


@pytest.mark.skipif(
    not Path("tests/Longer Stronger Orgasms For Him.no_watermark.zh-CN.dual.pdf").is_file(),
    reason="dual sample PDF not present",
)
class TestReproduceCmapFixesSoh:
    def test_reproduce_cmap_maps_space_not_soh(self, tmp_path):
        """After reproduce_cmap, left-column spaces must not extract as U+0001."""
        src = Path("tests/Longer Stronger Orgasms For Him.no_watermark.zh-CN.dual.pdf")
        doc = pymupdf.open(src)
        before = sum(p.get_text().count("\x01") for p in doc)
        assert before > 0, "sample dual should still show SOH-as-space bug"

        reproduce_cmap(doc)
        out = tmp_path / "fixed.pdf"
        doc.save(out)
        doc.close()

        fixed = pymupdf.open(out)
        after = sum(p.get_text().count("\x01") for p in fixed)
        # Spaces should reappear; SOH should drop sharply
        p21 = fixed[21]
        mid = p21.rect.width / 2
        zh_spaces = zh_soh = 0
        for b in p21.get_text("rawdict")["blocks"]:
            if b.get("type") != 0:
                continue
            for line in b.get("lines", []):
                for s in line.get("spans", []):
                    if s["bbox"][0] >= mid:
                        continue
                    for ch in s.get("chars") or []:
                        c = ch.get("c") or ""
                        if c == " ":
                            zh_spaces += 1
                        if c == "\x01":
                            zh_soh += 1
        fixed.close()

        assert after < before * 0.2, f"SOH not fixed: before={before} after={after}"
        assert zh_soh == 0 or zh_spaces > zh_soh
