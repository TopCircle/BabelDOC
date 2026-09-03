"""Repro digest regression tests (Layout-First P0, design doc §2).

``test_synth_digest_stable`` is the default-running gate: it runs the full
pipeline on the synthetic page and asserts Δ=0 against the committed golden
``tests/repro/golden/synth_layout.json``. The remaining tests are fast unit
checks that need no ONNX assets.
"""

from __future__ import annotations

import json
from pathlib import Path

import digest
import pytest
import synth_page

GOLDEN = Path(__file__).resolve().parent / "golden" / "synth_layout.json"


@pytest.fixture(scope="module")
def golden() -> dict:
    if not GOLDEN.exists():
        pytest.skip("golden not committed yet; run tests/repro/digest.py --update-golden")
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


class TestSynthDigestStable:
    @pytest.mark.skipif(
        not GOLDEN.exists(),
        reason="golden not committed yet; run tests/repro/digest.py --update-golden",
    )
    def test_synth_digest_stable(self, tmp_path):
        """Full-pipeline synth run must reproduce the committed golden (Δ=0)."""
        out_dir = tmp_path / "out"
        code = digest.main(
            [
                "--golden",
                str(GOLDEN),
                "--working-dir",
                str(tmp_path),
                "--out-dir",
                str(out_dir),
            ]
        )
        assert code == 0

    def test_golden_schema_and_digest_consistency(self, golden):
        """Golden must be self-consistent (digest sha = canonical of pages)."""
        assert golden["schema"] == "babeldoc-repro-layout/v1"
        assert golden["digest_sha256"] == digest.canonical_sha256(golden["pages"])
        assert golden["fingerprint_sha256"]

    def test_golden_prior_debug_id_set_present(self, golden):
        """Golden must pin the prior debug_id set (plan §2 assertion)."""
        for page_no, page in golden["pages"].items():
            assert page["debug_ids"], f"page {page_no} missing prior debug_ids"


class TestCanonicalSerialization:
    def test_deterministic_across_key_order(self):
        a = {"1": {"b": 1, "a": 2}}
        b = {"1": {"a": 2, "b": 1}}
        assert digest.canonical_sha256(a) == digest.canonical_sha256(b)

    def test_sensitive_to_geometry(self):
        p1 = {"1": {"paragraphs": {"p": {"box": [1.0, 2.0, 3.0, 4.0]}}}}
        p2 = {"1": {"paragraphs": {"p": {"box": [1.5, 2.0, 3.0, 4.0]}}}}
        assert digest.canonical_sha256(p1) != digest.canonical_sha256(p2)


class TestLineWidthsFromPdfCharacters:
    def test_y_clustering_groups_same_line(self):
        from driver import compute_line_widths

        para = {
            "pdf_paragraph_composition": [
                {"pdf_character": {"box": {"x": 10, "y": 100, "x2": 20, "y2": 112}}},
                {"pdf_character": {"box": {"x": 20, "y": 100, "x2": 40, "y2": 112}}},
                {"pdf_character": {"box": {"x": 10, "y": 88, "x2": 25, "y2": 100}}},
            ]
        }
        assert compute_line_widths(para) == [30.0, 15.0]

    def test_supports_same_style_and_line_compositions(self):
        from driver import compute_line_widths

        para = {
            "pdf_paragraph_composition": [
                {
                    "pdf_same_style_characters": {
                        "pdf_character": [
                            {"box": {"x": 5, "y": 50, "x2": 15, "y2": 62}},
                            {"box": {"x": 15, "y": 50, "x2": 25, "y2": 62}},
                        ]
                    }
                },
                {
                    "pdf_line": {
                        "pdf_character": [
                            {"box": {"x": 7, "y": 38, "x2": 17, "y2": 50}},
                        ]
                    }
                },
            ]
        }
        assert compute_line_widths(para) == [20.0, 10.0]


class TestSynthPageSpec:
    def test_roles_covered(self):
        assert {"title", "wrap_column", "chrome", "body"} <= synth_page.synth_roles()

    def test_il_document_shape(self):
        doc = synth_page.build_synth_il_document()
        assert len(doc.page) == 1
        paras = doc.page[0].pdf_paragraph
        assert {p.debug_id for p in paras} == {
            "synth_chrome_header",
            "synth_title",
            "synth_wrap_column",
            "synth_body",
        }
        assert all(p.pdf_paragraph_composition for p in paras)

    def test_synth_pdf_text_layout_deterministic(self, tmp_path):
        """Pipeline input determinism: same text, geometry, page size.

        Raw PDF bytes are not compared (pymupdf embeds random object/trailer
        IDs); what must be stable is the parsed geometry the digest gates on.
        """
        import pymupdf

        p1 = tmp_path / "a.pdf"
        p2 = tmp_path / "b.pdf"
        synth_page.write_synth_pdf(p1)
        synth_page.write_synth_pdf(p2)
        with pymupdf.open(p1) as d1, pymupdf.open(p2) as d2:
            assert d1.page_count == d2.page_count == 1
            assert d1[0].rect == d2[0].rect
            t1 = " ".join(d1[0].get_text().split())
            t2 = " ".join(d2[0].get_text().split())
        assert t1 == t2
        assert "Chapter 3" in t1
        assert "ORGASMIC ADDICTION" in t1
