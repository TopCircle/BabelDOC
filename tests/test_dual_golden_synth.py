"""PR-01: dual-quality harness unit tests (no large PDF, no ONNX)."""

from __future__ import annotations

import hashlib

import pytest
from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import Document
from babeldoc.format.pdf.document_il.il_version_1 import Page
from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraphComposition
from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
from babeldoc.format.pdf.document_il.utils.il_layout_fingerprint import (
    il_layout_fingerprint,
)
from babeldoc.tools.dual_quality_check import main as dual_quality_main
from babeldoc.tools.fixed_map_translator import FixedMapTranslator


def _style() -> PdfStyle:
    return PdfStyle(font_id="f0", font_size=10.0, graphic_state=None)


def _char(x: float, y: float, ch: str) -> PdfCharacter:
    return PdfCharacter(
        pdf_style=_style(),
        box=Box(x=x, y=y, x2=x + 5.0, y2=y + 10.0),
        char_unicode=ch,
    )


def _page_with_chars(
    page_number: int,
    debug_id: str,
    chars: list[tuple[float, float, str]],
) -> Page:
    comps = [
        PdfParagraphComposition(pdf_character=_char(x, y, c)) for x, y, c in chars
    ]
    para = PdfParagraph(
        box=Box(x=0, y=0, x2=100, y2=100),
        pdf_style=_style(),
        pdf_paragraph_composition=comps,
        unicode="".join(c for _, _, c in chars),
        debug_id=debug_id,
    )
    return Page(
        page_number=page_number,
        pdf_paragraph=[para],
    )


class TestFixedMapTranslator:
    def test_name_within_cache_limit(self):
        assert len(FixedMapTranslator.name) <= 20

    def test_lookup_and_identity_fallback(self):
        t = FixedMapTranslator({"Hello": "你好"})
        assert t.translate("Hello") == "你好"
        assert t.translate("World") == "World"
        assert t.do_translate("Hello") == "你好"

    def test_forces_non_llm_path(self):
        t = FixedMapTranslator()
        with pytest.raises(NotImplementedError):
            t.do_llm_translate(None)

    def test_duck_typed_surface_for_dispatch(self):
        t = FixedMapTranslator()
        assert hasattr(t, "lang_in")
        assert hasattr(t, "lang_out")
        assert hasattr(t, "ignore_cache")
        assert callable(t.translate)
        assert callable(t.do_llm_translate)


class TestIlLayoutFingerprint:
    def test_empty_document_is_empty_sha256(self):
        doc = Document(page=[])
        fp = il_layout_fingerprint(doc)
        assert fp == hashlib.sha256(b"").hexdigest()

    def test_stable_for_same_geometry(self):
        p = _page_with_chars(0, "p1", [(10.0, 20.0, "A"), (15.0, 20.0, "B")])
        doc = Document(page=[p])
        assert il_layout_fingerprint(doc) == il_layout_fingerprint(doc)

    def test_changes_when_box_moves(self):
        p1 = _page_with_chars(0, "p1", [(10.0, 20.0, "A")])
        p2 = _page_with_chars(0, "p1", [(10.5, 20.0, "A")])
        assert il_layout_fingerprint(Document(page=[p1])) != il_layout_fingerprint(
            Document(page=[p2])
        )

    def test_rounding_to_3dp_collapses_noise(self):
        p1 = _page_with_chars(0, "p1", [(10.0001, 20.0, "A")])
        p2 = _page_with_chars(0, "p1", [(10.0004, 20.0, "A")])
        # both round to 10.0 at 3dp
        assert il_layout_fingerprint(Document(page=[p1])) == il_layout_fingerprint(
            Document(page=[p2])
        )

    def test_sorted_by_debug_id_not_append_order(self):
        pa = _page_with_chars(0, "a", [(0.0, 0.0, "X")])
        pb = _page_with_chars(0, "b", [(0.0, 0.0, "Y")])
        # two paragraphs on one page: order of list should not matter
        doc_ab = Document(
            page=[
                Page(
                    page_number=0,
                    pdf_paragraph=pa.pdf_paragraph + pb.pdf_paragraph,
                )
            ]
        )
        doc_ba = Document(
            page=[
                Page(
                    page_number=0,
                    pdf_paragraph=pb.pdf_paragraph + pa.pdf_paragraph,
                )
            ]
        )
        assert il_layout_fingerprint(doc_ab) == il_layout_fingerprint(doc_ba)


class TestDualQualityCli:
    def test_self_check_prints_empty_fingerprint(self, capsys):
        code = dual_quality_main(["--self-check"])
        assert code == 0
        out = capsys.readouterr().out.strip()
        assert out == hashlib.sha256(b"").hexdigest()

    def test_expected_fingerprint_match_ok(self):
        empty = hashlib.sha256(b"").hexdigest()
        assert dual_quality_main(["--self-check", "--expected-fingerprint", empty]) == 0

    def test_expected_fingerprint_mismatch_exits_1(self, capsys):
        code = dual_quality_main(
            ["--self-check", "--expected-fingerprint", "deadbeef"]
        )
        assert code == 1
        err = capsys.readouterr().err
        assert "mismatch" in err.lower() or "FAIL" in err
