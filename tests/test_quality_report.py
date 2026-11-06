"""Document-scoped quality report aggregation."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from babeldoc.format.pdf.translation_config import TranslationConfig
from babeldoc.quality import QualityIssue
from babeldoc.quality import QualityReport
from babeldoc.translator.fixed_map_translator import FixedMapTranslator


@pytest.fixture
def config(tmp_path: Path) -> TranslationConfig:
    return TranslationConfig(
        translator=FixedMapTranslator(),
        input_file=tmp_path / "part.pdf",
        lang_in="en",
        lang_out="zh-CN",
        doc_layout_model=object(),
        output_dir=tmp_path / "out",
        working_dir=tmp_path / "work",
        debug=False,
        auto_extract_glossary=False,
    )


def test_quality_report_is_deduplicated_and_thread_safe():
    report = QualityReport(run_id="doc-a")
    issues = [
        QualityIssue("translation", "translation_error", 0, str(i), "warning", {})
        for i in range(10)
    ]
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(report.record, issues * 8))
    assert len(report.to_dict()["issues"]) == 10
    assert report.status == "degraded"


def test_reports_are_document_scoped_and_json_safe():
    first_report = QualityReport(run_id="doc-a")
    first_report.record(
        QualityIssue("translation", "translation_error", 0, "p1", "warning", {})
    )
    second_report = QualityReport(run_id="doc-b")
    assert second_report.to_dict()["issues"] == []
    payload = json.loads(json.dumps(first_report.to_dict()))
    assert payload["schema_version"] == 1
    assert payload["run_id"] == "doc-a"
    assert payload["status"] == "degraded"
    assert "_lock" not in payload
    assert "Lock" not in json.dumps(payload)


def test_second_part_uses_original_page_indices(config: TranslationConfig):
    config.source_page_indices = (5, 6)
    assert config.original_page_index(0) == 5


def test_original_page_index_is_strict_and_identity_without_map(
    config: TranslationConfig,
):
    assert config.original_page_index(3) == 3
    config.set_part_source_page_range(5, 6)
    assert config.source_page_indices == (5, 6)
    assert config.original_page_index(1) == 6
    with pytest.raises(IndexError):
        config.original_page_index(2)
    with pytest.raises(IndexError):
        config.original_page_index(-1)


def test_error_outranks_warning_and_issues_are_sorted():
    report = QualityReport(run_id="doc-c")
    report.record(
        QualityIssue("typesetting", "layout_incomplete", 1, "b", "error", {"placed_units": 1})
    )
    report.record(
        QualityIssue("translation", "translation_error", 0, "b", "warning", {})
    )
    report.record(
        QualityIssue("translation", "missing_sentences", 0, "a", "warning", {})
    )
    assert report.status == "failed"
    assert report.warning_count == 2
    ordered = [
        (issue["page_index"], issue["paragraph_id"], issue["stage"], issue["code"])
        for issue in report.to_dict()["issues"]
    ]
    assert ordered == sorted(ordered)


def test_write_json_replaces_atomically_and_keeps_distinct_run_ids(tmp_path: Path):
    destination = tmp_path / "doc.quality.json"
    destination.write_text("stale", encoding="utf-8")
    report = QualityReport(run_id="run-1")
    report.record(
        QualityIssue(
            "translation",
            "translation_error",
            0,
            "p1",
            "warning",
            {"source_sentence_ends": 2},
        )
    )
    report.write_json(destination)
    assert json.loads(destination.read_text(encoding="utf-8"))["run_id"] == "run-1"
    assert list(tmp_path.glob("*.tmp")) == []
    other = tmp_path / "doc.run-2.quality.json"
    QualityReport(run_id="run-2").write_json(other)
    assert destination.is_file()
    assert other.is_file()
