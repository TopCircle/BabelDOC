"""W1b: ToUnicode must export unified CJK, not compatibility ideographs.

OA dual left column extracted U+F967 (不) instead of U+4E0D (不) because:
1. Source Han shares one GID for both codepoints
2. reproduce_cmap skipped subset-tagged faces (``ABCDEF+Source Han …``)
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pymupdf
import pytest

from babeldoc.format.pdf.document_il.backend.pdf_creater import (
    _font_is_babeldoc_embedding_for_cmap,
)
from babeldoc.format.pdf.document_il.backend.pdf_creater import apply_normalization
from babeldoc.format.pdf.document_il.backend.pdf_creater import make_tounicode
from babeldoc.format.pdf.document_il.backend.pdf_creater import normalize_export_unicode
from babeldoc.format.pdf.document_il.backend.pdf_creater import reproduce_cmap


class TestNormalizeExportUnicode:
    def test_compat_ideographs_to_unified(self):
        assert normalize_export_unicode(0xF967) == 0x4E0D  # 不 → 不
        assert normalize_export_unicode(0xF9FF) == 0x523A  # 刺 → 刺
        assert normalize_export_unicode(0xF901) == 0x66F4  # 更 → 更
        assert normalize_export_unicode(0x4E0D) == 0x4E0D

    def test_apply_normalization_writes_unified(self):
        cmap: dict[int, int] = {}
        apply_normalization(cmap, 8773, 0xF967)
        assert cmap[8773] == 0x4E0D

    def test_make_tounicode_emits_unified_not_f9xx(self):
        # cmap still holds F9xx; emit path must normalize
        text = make_tounicode({100: 0xF967, 101: 0xF9FF}, [100, 101])
        assert re.search(r"<0064><4e0d>", text, re.I)
        assert re.search(r"<0065><523a>", text, re.I)
        assert not re.search(r"<f9", text, re.I)


class TestFontMatchStripsSubsetPrefix:
    def test_subset_tagged_source_han_matches(self):
        # page.get_fonts() row shape (xref, ext, type, basefont, name, …)
        row = (
            109,
            "ttf",
            "Type0",
            "CKCLFN+Source Han Serif CN Bold",
            "SourceHanSerifCN-Bold.ttf",
            "Identity-H",
            133,
        )
        assert _font_is_babeldoc_embedding_for_cmap(row)

    def test_publisher_face_does_not_match(self):
        row = (
            48,
            "cff",
            "Type1",
            "POULUG+TrajanPro-Regular",
            "KSPF15",
            "MacRomanEncoding",
            107,
        )
        assert not _font_is_babeldoc_embedding_for_cmap(row)

    def test_untagged_font_names_entry_matches(self):
        row = (
            1,
            "ttf",
            "Type0",
            "Source Han Sans CN Regular",
            "SourceHanSansCN-Regular.ttf",
            "Identity-H",
            10,
        )
        assert _font_is_babeldoc_embedding_for_cmap(row)


OA_DUAL = Path(
    "/Users/yun/Library/CloudStorage/OneDrive-Personal/Documentos/Books/"
    "Gabrielle Moore/Orgasmic Addiction/"
    "Orgasmic Addiction.no_watermark.zh-CN.dual.pdf"
)


def _left_compat_count(doc: pymupdf.Document, page_index: int = 2) -> tuple[int, int]:
    """Return (F9xx count, U+4E0D count) on left half of one page."""
    page = doc[page_index]
    mid = page.rect.width / 2
    f9 = bu = 0
    for b in page.get_text("rawdict").get("blocks", []):
        if b.get("type") != 0:
            continue
        for line in b.get("lines", []):
            for s in line.get("spans", []):
                if s["bbox"][0] >= mid:
                    continue
                for ch in s.get("chars") or []:
                    c = ch.get("c") or ""
                    if not c:
                        continue
                    o = ord(c[0])
                    if 0xF900 <= o <= 0xFAFF:
                        f9 += 1
                    if o == 0x4E0D:
                        bu += 1
    return f9, bu


def _p3_left_has_chars(doc: pymupdf.Document, needles: list[str]) -> dict[str, bool]:
    page = doc[2]
    mid = page.rect.width / 2
    chars: list[str] = []
    for b in page.get_text("rawdict").get("blocks", []):
        if b.get("type") != 0:
            continue
        for line in b.get("lines", []):
            for s in line.get("spans", []):
                if s["bbox"][0] >= mid:
                    continue
                for ch in s.get("chars") or []:
                    c = ch.get("c") or ""
                    if c:
                        chars.append(c)
    text = "".join(chars)
    return {n: n in text for n in needles}


@pytest.mark.skipif(not OA_DUAL.is_file(), reason="OA dual PDF not present")
class TestReproduceCmapFixesOaCompat:
    def test_reproduce_cmap_reduces_left_f9xx_preserves_hanzi(self, tmp_path):
        """F9xx→unified without mojibake (书 must survive)."""
        doc = pymupdf.open(OA_DUAL)
        before_f9, before_bu = _left_compat_count(doc)
        before_chars = _p3_left_has_chars(doc, ["书", "义", "意义"])
        # 0.6.4.57 fixture has F9xx; if already clean, still assert integrity
        if before_f9 == 0 and before_chars.get("书"):
            doc.close()
            pytest.skip("fixture already clean")
        assert before_chars.get("书"), "fixture p3 should contain 书 before cmap rewrite"

        reproduce_cmap(doc)
        out = tmp_path / "oa_cmap_fixed.pdf"
        doc.save(out)
        doc.close()

        fixed = pymupdf.open(out)
        after_f9, after_bu = _left_compat_count(fixed)
        after_chars = _p3_left_has_chars(fixed, ["书", "义", "意义", "不"])
        fixed.close()

        assert after_f9 == 0, f"F9xx remaining: {after_f9}"
        assert after_bu > 0, "unified 不 should appear"
        assert after_chars.get("书") and after_chars.get("义"), (
            f"hanzi corrupted after cmap rewrite: {after_chars}"
        )
