"""Synthetic delivery regressions: real parse, typeset, and PDF write."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pymupdf
from babeldoc.translator.fixed_map_translator import FixedMapTranslator
from pipeline_fixtures import run_delivery_fixture

EXPECTED_PATH = Path(__file__).parent / "golden" / "pipeline_delivery" / "expected.json"
BODY_TARGET = "这是第一段。这里保留 API 与 BDSM。"
UNMAPPED_SOURCE = "This sentence stays in English on purpose."
GLYPH_SLACK = 1.0
OVERLAP_LIMIT = 0.4


class StrictFixedMapTranslator(FixedMapTranslator):
    """Reject unmapped non-empty text so an identity fallback cannot hide a miss."""

    def translate(
        self,
        text: str,
        ignore_cache: bool = False,
        rate_limit_params: dict | None = None,
    ) -> str:
        del ignore_cache, rate_limit_params
        if text is None or str(text).strip() == "":
            return "" if text is None else text
        if text not in self._map:
            raise AssertionError(f"unmapped delivery text: {text!r}")
        return self._map[text]


def _expected() -> dict:
    return json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))


def _fold(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _mono_pdf(delivery) -> Path | None:
    result = delivery.result
    if result is None:
        return None
    for attr in ("no_watermark_mono_pdf_path", "mono_pdf_path"):
        path = getattr(result, attr, None)
        if path and Path(path).is_file():
            return Path(path)
    return None


def _paragraph_count(pdf_path: Path) -> int:
    count = 0
    with pymupdf.open(pdf_path) as doc:
        for page in doc:
            for block in page.get_text("blocks"):
                if len(block) >= 7 and block[6] == 0 and str(block[4]).strip():
                    count += 1
    return count


def _assert_source_unchanged(output_dir: Path) -> None:
    source = output_dir / "source.pdf"
    stamp = json.loads((output_dir / "source-stamp.json").read_text(encoding="utf-8"))
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    assert digest == stamp["sha256"]
    assert source.stat().st_mtime_ns == stamp["mtime_ns"]


def _assert_glyphs(delivery, spec: dict) -> None:
    if spec["quality_status"] != "success":
        return
    pdf_path = _mono_pdf(delivery)
    assert pdf_path is not None
    box = spec["page_box"]
    with pymupdf.open(pdf_path) as doc:
        assert doc.page_count == spec["page_count"]
        for page_index, page in enumerate(doc):
            raw = page.get_text("rawdict")
            for block in raw["blocks"]:
                if block.get("type") != 0:
                    continue
                for line in block["lines"]:
                    for span in line["spans"]:
                        for char in span.get("chars") or []:
                            x0, y0, x1, y1 = char["bbox"]
                            assert x0 >= box[0] - GLYPH_SLACK, char
                            assert y0 >= box[1] - GLYPH_SLACK, char
                            assert x1 <= box[2] + GLYPH_SLACK, char
                            assert y1 <= box[3] + GLYPH_SLACK, char
                            glyph = pymupdf.Rect(x0, y0, x1, y1)
                            for obstacle in spec["obstacles"]:
                                if obstacle["page"] != page_index:
                                    continue
                                overlap = glyph & pymupdf.Rect(*obstacle["rect"])
                                assert (
                                    overlap.width <= OVERLAP_LIMIT
                                    or overlap.height <= OVERLAP_LIMIT
                                ), char


def _assert_recorded(delivery, case_name: str, output_dir: Path) -> None:
    spec = _expected()[case_name]
    assert delivery.quality["status"] == spec["quality_status"]
    if spec["quality_status"] == "failed":
        assert delivery.result is not None
        assert _mono_pdf(delivery) is not None
        _assert_source_unchanged(output_dir)
        return
    assert delivery.extracted_target_text == spec["target_text"]
    pdf_path = _mono_pdf(delivery)
    assert pdf_path is not None
    with pymupdf.open(pdf_path) as doc:
        assert doc.page_count == spec["page_count"]
    assert _paragraph_count(pdf_path) == spec["paragraph_count"]
    _assert_glyphs(delivery, spec)
    _assert_source_unchanged(output_dir)


def test_successful_delivery_preserves_all_expected_target_text(tmp_path: Path):
    delivery = run_delivery_fixture("body", tmp_path)
    assert delivery.quality["status"] == "success"
    assert delivery.extracted_target_text == BODY_TARGET
    assert "API" in delivery.extracted_target_text
    assert "BDSM" in delivery.extracted_target_text
    assert delivery.invalid_page_bookmarks == []
    _assert_recorded(delivery, "body", tmp_path)


def test_photo_wrap_glyphs_miss_the_figure(tmp_path: Path):
    delivery = run_delivery_fixture("photo_wrap", tmp_path)
    assert delivery.quality["status"] == "success"
    assert "留在照片左侧。" in delivery.extracted_target_text
    _assert_recorded(delivery, "photo_wrap", tmp_path)


def test_toc_bookmarks_stay_inside_the_output(tmp_path: Path):
    delivery = run_delivery_fixture("toc", tmp_path)
    assert delivery.quality["status"] == "success"
    assert delivery.invalid_page_bookmarks == []
    pdf_path = _mono_pdf(delivery)
    assert pdf_path is not None
    with pymupdf.open(pdf_path) as doc:
        pages = [entry[2] for entry in doc.get_toc()]
    assert pages == [1, 2]
    assert "这是第一段。" in delivery.extracted_target_text
    assert "第一段在第二段之上。" in delivery.extracted_target_text
    assert delivery.extracted_target_text.index("这是第一段。") < (
        delivery.extracted_target_text.index("第一段在第二段之上。")
    )
    _assert_recorded(delivery, "toc", tmp_path)


def test_heading_formula_keeps_digits_points_and_reading_order(tmp_path: Path):
    delivery = run_delivery_fixture("heading_formula", tmp_path)
    assert delivery.quality["status"] == "success"
    text = delivery.extracted_target_text
    for token in ("第一章", "A点", "G点", "12", "mc2"):
        assert token in text
    assert text.index("第一章") < text.index("A点") < text.index("G点")
    assert text.index("G点") < text.index("12")
    _assert_recorded(delivery, "heading_formula", tmp_path)


def test_incomplete_contour_marks_the_paragraph_and_still_writes_pdf(tmp_path: Path):
    delivery = run_delivery_fixture("contour_exhausted", tmp_path)
    event_types = [event["type"] for event in delivery.events]
    assert "error" not in event_types
    assert "finish" in event_types
    assert delivery.result is not None
    assert delivery.quality["status"] == "failed"
    issues = [
        issue
        for issue in delivery.quality.get("issues", [])
        if issue.get("code") == "layout_incomplete"
    ]
    assert len(issues) == 1
    assert issues[0]["details"]["reason"] == "contour_exhausted"
    assert issues[0]["severity"] == "error"
    pdf_path = _mono_pdf(delivery)
    assert pdf_path is not None
    assert pdf_path.is_file()
    _assert_source_unchanged(tmp_path)


def test_translator_error_keeps_source_and_degrades(tmp_path: Path):
    delivery = run_delivery_fixture("translator_error", tmp_path)
    event_types = [event["type"] for event in delivery.events]
    assert "finish" in event_types
    assert "error" not in event_types
    assert delivery.result is not None
    assert delivery.quality["status"] == "degraded"
    assert UNMAPPED_SOURCE in delivery.extracted_target_text
    codes = [issue["code"] for issue in delivery.quality["issues"]]
    assert "translation_error" in codes
    _assert_recorded(delivery, "translator_error", tmp_path)


def test_split_part_two_issue_uses_the_original_page(tmp_path: Path):
    delivery = run_delivery_fixture("split_two_parts", tmp_path)
    assert delivery.quality["status"] == "degraded"
    assert delivery.result is not None
    errors = [
        issue
        for issue in delivery.quality["issues"]
        if issue["code"] == "translation_error"
    ]
    assert errors
    assert {issue["page_index"] for issue in errors} == {1}
    pdf_path = _mono_pdf(delivery)
    assert pdf_path is not None
    with pymupdf.open(pdf_path) as doc:
        assert UNMAPPED_SOURCE in _fold(doc[1].get_text())
        assert "这是第一段。" in _fold(doc[0].get_text())
    assert BODY_TARGET.split("。", 1)[0] in delivery.extracted_target_text
    _assert_recorded(delivery, "split_two_parts", tmp_path)
