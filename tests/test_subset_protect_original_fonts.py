"""Subset must trim BabelDOC embedding fonts only — not publisher faces.

Regression: Day 6 cover (pages=2- skips MT) still went through mono save +
global subset_fonts, which collapsed display glyphs (``Day`` width→1.5pt,
``shockingly``→``shockingl``). Same damage hit headers/footers/figure text
that keep original content streams under q…Q overlays.
"""

from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest
from babeldoc.assets import assets
from babeldoc.format.pdf.document_il.backend import pdf_creater as pc
from babeldoc.format.pdf.document_il.utils import font_subset as fs


class TestEmbeddingFontNameMatch:
    def test_source_han_positive(self):
        assert fs.is_babeldoc_embedding_font_name("Source Han Sans CN Regular")
        assert fs.is_babeldoc_embedding_font_name("SourceHanSansCN-Regular")
        assert fs.is_babeldoc_embedding_font_name("/Source#20Han#20Sans#20CN#20Regular")
        # re-export on pdf_creater for older imports
        assert pc.is_babeldoc_embedding_font_name("Source Han Sans CN Regular")

    def test_publisher_subset_tag_negative(self):
        assert not fs.is_babeldoc_embedding_font_name("FQJZCV+Ubuntu-Light")
        assert not fs.is_babeldoc_embedding_font_name("Ubuntu-MediumItalic")
        assert not fs.is_babeldoc_embedding_font_name("TrajanPro-Regular")
        assert not fs.is_babeldoc_embedding_font_name("Georgia-Italic")

    def test_no_substring_false_positive(self):
        # Exact tokens only — short stems must not match arbitrary faces
        assert not fs.is_babeldoc_embedding_font_name("NotARealFont")


class TestSubsetProtectsOriginalFonts:
    def test_cover_glyphs_survive_subset_with_embedding_insert(
        self, tmp_path: Path
    ):
        day6 = Path(
            "/Users/yun/Library/CloudStorage/OneDrive-Personal/Documentos/"
            "Books/Gabrielle Moore/7 day orgasm/Day 6/Day 6.pdf"
        )
        if not day6.is_file():
            pytest.skip("Day 6 source PDF not available on this machine")

        doc = pymupdf.open(day6)
        fam = assets.get_font_family("zh-CN")
        # Mimic pipeline: inject full CJK faces (pages 2+ would use them)
        for name in fam["base"][:1] + fam["normal"][:2]:
            fpath, _ = assets.get_font_and_metadata(name)
            doc[1].insert_font(name, str(fpath))
            # Use a few glyphs so subset keeps a non-empty face
            doc[1].insert_text(
                (72, 72),
                "测试子集",
                fontname=name,
                fontsize=12,
            )

        out = tmp_path / "subset_protected.pdf"
        fs.subset_embedding_fonts_and_save(doc, out)
        doc.close()

        src = pymupdf.open(day6)
        sub = pymupdf.open(out)
        try:
            assert "shockingly" in src[0].get_text()
            assert "shockingly" in sub[0].get_text()
            assert "little" in src[0].get_text()
            assert "little" in sub[0].get_text()

            def day_width(page) -> float:
                for b in page.get_text("dict")["blocks"]:
                    if b.get("type") != 0:
                        continue
                    for line in b["lines"]:
                        for span in line["spans"]:
                            if span.get("text") == "Day" and span.get("size", 0) > 40:
                                x0, _, x1, _ = span["bbox"]
                                return float(x1 - x0)
                return 0.0

            src_w = day_width(src[0])
            sub_w = day_width(sub[0])
            assert src_w > 50
            # Must not collapse to ~1.5pt (pre-fix failure mode)
            assert sub_w > 50
            assert abs(sub_w - src_w) < 1.0
        finally:
            src.close()
            sub.close()

    def test_restored_publisher_ttf_is_valid_sfnt(self, tmp_path: Path):
        """Regression: double-Flate restore made FT_New_Memory_Face fail."""
        day6 = Path(
            "/Users/yun/Library/CloudStorage/OneDrive-Personal/Documentos/"
            "Books/Gabrielle Moore/7 day orgasm/Day 6/Day 6.pdf"
        )
        if not day6.is_file():
            pytest.skip("Day 6 source PDF not available on this machine")

        doc = pymupdf.open(day6)
        fam = assets.get_font_family("zh-CN")
        name = fam["base"][0]
        fpath, _ = assets.get_font_and_metadata(name)
        doc[1].insert_font(name, str(fpath))
        doc[1].insert_text((72, 72), "测", fontname=name, fontsize=12)
        out = tmp_path / "sfnt_check.pdf"
        fs.subset_embedding_fonts_and_save(doc, out)
        doc.close()

        sub = pymupdf.open(out)
        try:
            found = False
            for f in sub.get_page_fonts(0, full=True):
                if "Ubuntu-Light" not in (f[3] or ""):
                    continue
                _n, _ext, _typ, content = sub.extract_font(f[0])
                assert content and len(content) > 1000
                # TrueType / OpenType sfnt version
                assert content[:4] in (
                    b"\x00\x01\x00\x00",
                    b"OTTO",
                    b"true",
                    b"ttcf",
                ), content[:8].hex()
                found = True
                break
            assert found, "expected Ubuntu-Light on cover page resources"
        finally:
            sub.close()

    def test_unprotected_subset_damages_day6_cover(self, tmp_path: Path):
        """Document the failure mode we are guarding against."""
        day6 = Path(
            "/Users/yun/Library/CloudStorage/OneDrive-Personal/Documentos/"
            "Books/Gabrielle Moore/7 day orgasm/Day 6/Day 6.pdf"
        )
        if not day6.is_file():
            pytest.skip("Day 6 source PDF not available on this machine")

        doc = pymupdf.open(day6)
        out = tmp_path / "naive_subset.pdf"
        doc.subset_fonts(fallback=False)
        doc.save(out, garbage=4, deflate=True, deflate_fonts=True, clean=True)
        doc.close()

        sub = pymupdf.open(out)
        try:
            text = sub[0].get_text()
            # Naive subset loses intact extract of these words on this PDF
            assert "shockingly" not in text or "little" not in text
        finally:
            sub.close()
