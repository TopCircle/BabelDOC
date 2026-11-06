"""Bookmark migration follows the pages that were actually written."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pymupdf

from babeldoc.format.pdf.high_level import migrate_toc
from babeldoc.format.pdf.translation_config import TranslateResult
from babeldoc.format.pdf.translation_config import TranslationConfig
from babeldoc.quality import QualityIssue
from babeldoc.quality import ensure_document_quality_report
from babeldoc.translator.fixed_map_translator import FixedMapTranslator

SOURCE_TOC = [
    [1, "gone-parent", 1],
    [2, "kept-child", 2],
    [3, "kept-grand", 2],
    [2, "gone-sibling", 3],
    [1, "kept-five", 5],
    [2, "gone-under-five", 4],
    [3, "kept-under-five", 5],
]

# Document order of pages="5,2", not the order written in the pages string.
# pdf_creater deletes the other pages and leaves 2 then 5.
FILTERED_MONO = [
    [1, "kept-child", 1],
    [2, "kept-grand", 1],
    [1, "kept-five", 2],
    [2, "kept-under-five", 2],
]


def _remap(*args, **kwargs):
    from babeldoc.format.pdf.document_il.utils.toc_migration import remap_toc

    return remap_toc(*args, **kwargs)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_pdf(path: Path, page_count: int, toc: list | None = None) -> None:
    doc = pymupdf.open()
    try:
        for index in range(page_count):
            page = doc.new_page()
            page.insert_text((72, 72), f"page {index + 1}")
        if toc:
            doc.set_toc(toc)
        doc.save(path)
    finally:
        doc.close()


def _read_toc(path: Path) -> list:
    doc = pymupdf.open(path)
    try:
        toc = doc.get_toc(simple=True)
        page_count = doc.page_count
    finally:
        doc.close()
    for row in toc:
        assert len(row) == 3
        assert 1 <= row[2] <= page_count
    return toc


def _page_count(path: Path) -> int:
    doc = pymupdf.open(path)
    try:
        return doc.page_count
    finally:
        doc.close()


def _config(tmp_path: Path, source: Path, **kwargs) -> TranslationConfig:
    return TranslationConfig(
        translator=FixedMapTranslator(),
        input_file=source,
        lang_in="en",
        lang_out="zh-CN",
        doc_layout_model=object(),
        output_dir=tmp_path / "out",
        working_dir=tmp_path / "work",
        debug=False,
        auto_extract_glossary=False,
        skip_clean=True,
        **kwargs,
    )


def test_sparse_selection_remaps_side_by_side_bookmarks():
    entries = [(1, "保留二", 2), (1, "被删三", 3), (1, "保留五", 5)]
    assert _remap(
        entries,
        kept_source_pages=[2, 5],
        output_mode="side_by_side",
        translate_first=False,
    ) == [(1, "保留二", 1), (1, "保留五", 2)]


def test_alternating_bookmarks_point_to_translated_pages():
    entries = [(1, "二", 2), (1, "五", 5)]
    for first, expected in ((False, [2, 4]), (True, [1, 3])):
        result = _remap(
            entries,
            kept_source_pages=[2, 5],
            output_mode="alternating",
            translate_first=first,
        )
        assert [row[2] for row in result] == expected


def test_mono_matches_side_by_side_and_ignores_translate_first():
    entries = [(1, "保留二", 2), (1, "保留五", 5)]
    expected = [(1, "保留二", 1), (1, "保留五", 2)]
    for translate_first in (False, True):
        assert (
            _remap(
                entries,
                kept_source_pages=[2, 5],
                output_mode="mono",
                translate_first=translate_first,
            )
            == expected
        )


def test_deleted_parent_keeps_children_under_nearest_ancestor():
    entries = [
        (1, "被删父", 1),
        (2, "子甲", 2),
        (3, "孙", 2),
        (2, "被删兄", 3),
        (1, "保留五", 5),
        (2, "被删子", 4),
        (3, "重挂", 5),
    ]
    assert _remap(
        entries,
        kept_source_pages=[2, 5],
        output_mode="side_by_side",
        translate_first=False,
    ) == [
        (1, "子甲", 1),
        (2, "孙", 1),
        (1, "保留五", 2),
        (2, "重挂", 2),
    ]


def test_level_gap_collapses_and_first_level_becomes_one():
    entries = [(3, "孤儿", 2), (5, "跳级", 2), (3, "同级", 5)]
    assert _remap(
        entries,
        kept_source_pages=[2, 5],
        output_mode="mono",
        translate_first=True,
    ) == [
        (1, "孤儿", 1),
        (2, "跳级", 1),
        (1, "同级", 2),
    ]


def test_empty_toc_returns_empty():
    assert (
        _remap(
            [],
            kept_source_pages=[1, 2, 3],
            output_mode="alternating",
            translate_first=True,
        )
        == []
    )


def test_unfiltered_pages_keep_mono_and_side_by_side_numbers():
    entries = [(1, "一", 1), (2, "二", 2), (3, "二下", 2), (1, "五", 5)]
    kept = [1, 2, 3, 4, 5]
    for mode in ("mono", "side_by_side"):
        assert (
            _remap(
                entries,
                kept_source_pages=kept,
                output_mode=mode,
                translate_first=False,
            )
            == entries
        )
    original_first = _remap(
        entries,
        kept_source_pages=kept,
        output_mode="alternating",
        translate_first=False,
    )
    translated_first = _remap(
        entries,
        kept_source_pages=kept,
        output_mode="alternating",
        translate_first=True,
    )
    assert [row[2] for row in original_first] == [2, 4, 4, 10]
    assert [row[2] for row in translated_first] == [1, 3, 3, 9]


def test_kept_order_is_write_order_not_sorted_page_numbers():
    entries = [(1, "五", 5), (1, "二", 2)]
    assert _remap(
        entries,
        kept_source_pages=[5, 2],
        output_mode="mono",
        translate_first=False,
    ) == [(1, "五", 1), (1, "二", 2)]


def test_migrate_toc_remaps_filtered_mono_and_side_by_side(tmp_path: Path, monkeypatch):
    source = tmp_path / "book.pdf"
    _write_pdf(source, 5, SOURCE_TOC)
    digest = _sha256(source)
    mono = tmp_path / "mono.pdf"
    dual = tmp_path / "dual.pdf"
    _write_pdf(mono, 2)
    _write_pdf(dual, 2)
    config = _config(
        tmp_path,
        source,
        pages="5,2",
        only_include_translated_page=True,
        use_alternating_pages_dual=False,
        dual_translate_first=True,
    )
    result = TranslateResult(mono, dual)
    result.no_watermark_mono_pdf_path = mono
    result.no_watermark_dual_pdf_path = dual
    saved: list[Path] = []
    from babeldoc.format.pdf.document_il.backend.pdf_creater import PDFCreater

    original_save = PDFCreater.save_pdf_with_timeout

    def _counting_save(pdf, output_path, translation_config, **kwargs):
        saved.append(Path(output_path).resolve())
        return original_save(pdf, output_path, translation_config, **kwargs)

    monkeypatch.setattr(PDFCreater, "save_pdf_with_timeout", _counting_save)
    migrate_toc(config, result)
    assert _sha256(source) == digest
    assert _page_count(mono) == 2
    assert _page_count(dual) == 2
    assert _read_toc(mono) == FILTERED_MONO
    assert _read_toc(dual) == FILTERED_MONO
    assert saved == [mono.resolve(), dual.resolve()]


def test_migrate_toc_alternating_orders_point_at_translated_pages(tmp_path: Path):
    source = tmp_path / "book.pdf"
    _write_pdf(source, 5, SOURCE_TOC)
    digest = _sha256(source)
    expectations = {
        False: [2, 2, 4, 4],
        True: [1, 1, 3, 3],
    }
    for translate_first, pages in expectations.items():
        mono = tmp_path / f"mono-{int(translate_first)}.pdf"
        dual = tmp_path / f"alt-{int(translate_first)}.pdf"
        _write_pdf(mono, 2)
        _write_pdf(dual, 4)
        config = _config(
            tmp_path,
            source,
            pages="2,5",
            only_include_translated_page=True,
            use_alternating_pages_dual=True,
            dual_translate_first=translate_first,
        )
        migrate_toc(config, TranslateResult(mono, dual))
        assert _page_count(mono) == 2
        assert _page_count(dual) == 4
        assert [row[2] for row in _read_toc(mono)] == [1, 1, 2, 2]
        assert [row[2] for row in _read_toc(dual)] == pages
        assert [row[1] for row in _read_toc(dual)] == [
            "kept-child",
            "kept-grand",
            "kept-five",
            "kept-under-five",
        ]
    assert _sha256(source) == digest


def test_migrate_toc_unfiltered_and_empty_do_not_touch_source(tmp_path: Path):
    source = tmp_path / "book.pdf"
    _write_pdf(source, 5, SOURCE_TOC)
    digest = _sha256(source)
    mono = tmp_path / "mono.pdf"
    _write_pdf(mono, 5)
    config = _config(
        tmp_path,
        source,
        only_include_translated_page=False,
        use_alternating_pages_dual=False,
    )
    migrate_toc(config, TranslateResult(mono, None))
    assert _page_count(mono) == 5
    assert _read_toc(mono) == SOURCE_TOC
    assert _sha256(source) == digest

    empty_source = tmp_path / "empty.pdf"
    _write_pdf(empty_source, 5)
    empty_digest = _sha256(empty_source)
    untouched = tmp_path / "untouched.pdf"
    _write_pdf(untouched, 2, [[1, "stale", 1]])
    stale_digest = _sha256(untouched)
    empty_config = _config(
        tmp_path,
        empty_source,
        only_include_translated_page=True,
        pages="2,5",
        use_alternating_pages_dual=False,
    )
    migrate_toc(empty_config, TranslateResult(untouched, None))
    assert _sha256(empty_source) == empty_digest
    assert _sha256(untouched) == stale_digest
    assert _read_toc(untouched) == [[1, "stale", 1]]


def test_toc_migration_error_is_a_warning_without_exception_text(tmp_path: Path):
    from babeldoc.format.pdf import high_level

    source = tmp_path / "book.pdf"
    _write_pdf(source, 5, SOURCE_TOC)
    config = _config(
        tmp_path,
        source,
        pages="2,5",
        only_include_translated_page=True,
    )
    report = ensure_document_quality_report(config)
    missing = tmp_path / "missing.pdf"
    high_level.migrate_document_toc(config, TranslateResult(missing, None))
    high_level.migrate_document_toc(config, TranslateResult(missing, None))
    payload = report.to_dict()
    assert payload["status"] == "degraded"
    warnings = [
        issue for issue in payload["issues"] if issue["code"] == "toc_migration_error"
    ]
    assert warnings == [
        {
            "stage": "document",
            "code": "toc_migration_error",
            "page_index": 0,
            "paragraph_id": "",
            "severity": "warning",
            "details": {},
        }
    ]
    blob = str(payload)
    assert "kept-child" not in blob
    assert "missing.pdf" not in blob
    assert "FileNotFoundError" not in blob
    assert "Traceback" not in blob


def test_toc_migration_error_does_not_replace_layout_incomplete(tmp_path: Path):
    from babeldoc.format.pdf import high_level

    source = tmp_path / "book.pdf"
    _write_pdf(source, 5, SOURCE_TOC)
    config = _config(tmp_path, source, pages="2", only_include_translated_page=True)
    report = ensure_document_quality_report(config)
    report.record(
        QualityIssue(
            "typesetting",
            "layout_incomplete",
            1,
            "p1",
            "error",
            {
                "reason": "capacity",
                "requested_units": 2,
                "placed_units": 1,
            },
        )
    )
    high_level.migrate_document_toc(
        config, TranslateResult(tmp_path / "missing.pdf", None)
    )
    payload = report.to_dict()
    assert payload["status"] == "failed"
    by_code = {issue["code"]: issue for issue in payload["issues"]}
    assert set(by_code) == {"layout_incomplete", "toc_migration_error"}
    assert by_code["layout_incomplete"]["severity"] == "error"
    assert by_code["layout_incomplete"]["page_index"] == 1
    assert by_code["layout_incomplete"]["paragraph_id"] == "p1"
    assert by_code["toc_migration_error"]["severity"] == "warning"
    assert by_code["toc_migration_error"]["details"] == {}
    assert report.warning_count == 1


def test_successful_migration_records_no_toc_warning(tmp_path: Path):
    from babeldoc.format.pdf import high_level

    source = tmp_path / "book.pdf"
    _write_pdf(source, 5, SOURCE_TOC)
    mono = tmp_path / "mono.pdf"
    _write_pdf(mono, 5)
    config = _config(tmp_path, source, only_include_translated_page=False)
    report = ensure_document_quality_report(config)
    high_level.migrate_document_toc(config, TranslateResult(mono, None))
    assert report.status == "success"
    assert report.to_dict()["issues"] == []
    assert _read_toc(mono) == SOURCE_TOC
    assert _page_count(mono) == 5
