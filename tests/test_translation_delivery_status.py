"""Translation fallbacks publish a document-scoped quality report."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pymupdf
import pytest

from babeldoc.babeldoc_exception.BabelDOCException import ContentFilterError
from babeldoc.babeldoc_exception.LayoutIncompleteError import LayoutIncompleteError
from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import Document
from babeldoc.format.pdf.document_il.il_version_1 import Page
from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter
from babeldoc.format.pdf.document_il.il_version_1 import PdfLine
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraphComposition
from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
from babeldoc.format.pdf.document_il.midend.il_translator import ILTranslator
from babeldoc.format.pdf.document_il.midend.il_translator import (
    ParagraphTranslateTracker,
)
from babeldoc.format.pdf.document_il.midend.il_translator_llm_only import (
    ILTranslatorLLMOnly,
)
from babeldoc.format.pdf.high_level import do_translate
from babeldoc.format.pdf.split_manager import SplitPoint
from babeldoc.format.pdf.translation_config import TranslateResult
from babeldoc.format.pdf.translation_config import TranslationConfig
from babeldoc.progress_monitor import ProgressMonitor
from babeldoc.quality import QualityIssue
from babeldoc.quality import QualityReport
from babeldoc.quality import record_layout_incomplete
from babeldoc.translator.fixed_map_translator import FixedMapTranslator

SOURCE_SECRET = "Keep this source sentence intact."
ERROR_SECRET = "service exploded with SOURCE body"


class _Tok:
    def encode(self, text, disallowed_special=()):  # noqa: ARG002
        return list(text or "")


class _Pbar:
    def advance(self, n=1):  # noqa: ARG002
        return None


class _Raising(FixedMapTranslator):
    def __init__(self, exc: BaseException):
        super().__init__()
        self._exc = exc
        self.calls = 0

    def translate(self, text, ignore_cache=False, rate_limit_params=None):  # noqa: ARG002
        self.calls += 1
        raise self._exc


class _Short(FixedMapTranslator):
    """Whole-paragraph calls stay one sentence short; per-sentence calls fail."""

    def translate(self, text, ignore_cache=False, rate_limit_params=None):  # noqa: ARG002
        if text.count(".") >= 2 or "Beta" in (text or ""):
            return "短。"
        raise RuntimeError("sentence retry failed")


class _Banner(FixedMapTranslator):
    def __init__(self, banner: str):
        super().__init__()
        self.banner = banner

    def translate(self, text, ignore_cache=False, rate_limit_params=None):  # noqa: ARG002
        return self.banner


class _PlainTranslation(FixedMapTranslator):
    def translate(self, text, ignore_cache=False, rate_limit_params=None):  # noqa: ARG002
        return "完整的中文译文。"


class _Mapped(FixedMapTranslator):
    def __init__(self, mapping: dict[str, str]):
        super().__init__(mapping)
        self.calls = 0

    def translate(self, text, ignore_cache=False, rate_limit_params=None):  # noqa: ARG002
        self.calls += 1
        return super().translate(text, ignore_cache, rate_limit_params)


class _ScriptedLLM(FixedMapTranslator):
    def __init__(self, *, fallback_ok: bool):
        super().__init__()
        self.fallback_ok = fallback_ok
        self.calls: list[str] = []

    def do_llm_translate(self, text, rate_limit_params=None):  # noqa: ARG002
        if text is None:
            return ""
        raise AssertionError("batch path must call llm_translate")

    def llm_translate(self, text, rate_limit_params=None, ignore_cache=False):  # noqa: ARG002
        self.calls.append(text or "")
        if len(self.calls) == 1:
            raise RuntimeError("batch failed BATCH_SECRET")
        if not self.fallback_ok:
            raise RuntimeError("paragraph failed PARA_SECRET")
        return "完整的中文译文。"


class _TwoParts:
    def determine_split_points(self, config):  # noqa: ARG002
        return [SplitPoint(0, 0), SplitPoint(1, 1)]


def _style() -> PdfStyle:
    return PdfStyle(font_id="f0", font_size=12.0, graphic_state=None)


def _paragraph(text: str, *, debug_id: str | None, box: Box | None = None) -> PdfParagraph:
    style = _style()
    chars: list[PdfCharacter] = []
    x = 72.0
    for ch in text:
        chars.append(
            PdfCharacter(
                pdf_style=style,
                box=Box(x=x, y=400, x2=x + 5, y2=412),
                char_unicode=ch,
                advance=5.0,
            )
        )
        x += 5
    line_box = box or Box(x=72, y=400, x2=max(x, 73), y2=412)
    return PdfParagraph(
        box=line_box,
        pdf_style=style,
        pdf_paragraph_composition=[
            PdfParagraphComposition(
                pdf_line=PdfLine(box=line_box, pdf_character=chars)
            )
        ],
        unicode=text,
        layout_label="plain text",
        debug_id=debug_id,
        vertical=False,
    )


def _page(paragraphs: list[PdfParagraph], *, number: int = 0) -> Page:
    return Page(
        page_number=number,
        cropbox=type("Crop", (), {"box": Box(x=0, y=0, x2=612, y2=792)})(),
        pdf_paragraph=list(paragraphs),
    )


def _glyph_text(paragraph: PdfParagraph) -> str:
    chars: list[str] = []
    for comp in paragraph.pdf_paragraph_composition:
        line = comp.pdf_line
        if line is None:
            continue
        chars.extend(ch.char_unicode or "" for ch in line.pdf_character)
    return "".join(chars)


def _config(tmp_path: Path, translator, name: str = "book.pdf", **kwargs) -> TranslationConfig:
    pdf = tmp_path / name
    if not pdf.exists():
        _write_pdf(pdf, pages=kwargs.pop("pdf_pages", 1))
    else:
        kwargs.pop("pdf_pages", None)
    return TranslationConfig(
        translator=translator,
        input_file=pdf,
        lang_in="en",
        lang_out="zh-CN",
        doc_layout_model=object(),
        output_dir=tmp_path / "out",
        working_dir=tmp_path / "work",
        debug=False,
        auto_extract_glossary=False,
        pool_max_workers=kwargs.pop("pool_max_workers", 2),
        **kwargs,
    )


def _write_pdf(path: Path, pages: int) -> None:
    doc = pymupdf.open()
    for index in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"page {index}")
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(path)
    doc.close()


def _attach(config: TranslationConfig, run_id: str = "run-1") -> QualityReport:
    report = QualityReport(run_id=run_id)
    config.shared_context_cross_split_part.quality_report = report
    return report


def _translator(config: TranslationConfig) -> ILTranslator:
    config.progress_monitor = ProgressMonitor([("Translate Paragraphs", 1.0)])
    return ILTranslator(config.translator, config, tokenizer=_Tok())


def _events():
    found = []

    def finish(**kwargs):
        found.append(kwargs)

    return found, finish


def _run_paragraph(translator: ILTranslator, paragraph: PdfParagraph, page: Page) -> None:
    translator.translate_paragraph(
        paragraph,
        page,
        _Pbar(),
        ParagraphTranslateTracker(),
        {},
        {},
    )


def _issue_blob(report: QualityReport) -> str:
    return json.dumps(report.to_dict(), ensure_ascii=False)


def test_service_error_keeps_composition_and_records_translation_error(tmp_path: Path):
    translator_engine = _Raising(RuntimeError(ERROR_SECRET))
    config = _config(tmp_path, translator_engine)
    config.source_page_indices = (6, 7, 8, 9)
    report = _attach(config)
    engine = _translator(config)
    paragraph = _paragraph(SOURCE_SECRET, debug_id="para-keep")
    page = _page([paragraph], number=3)
    composition_ids = [id(comp) for comp in paragraph.pdf_paragraph_composition]

    _run_paragraph(engine, paragraph, page)

    assert _glyph_text(paragraph) == SOURCE_SECRET
    assert [id(comp) for comp in paragraph.pdf_paragraph_composition] == composition_ids
    payload = report.to_dict()
    assert payload["status"] == "degraded"
    assert payload["issues"][0]["code"] == "translation_error"
    assert payload["issues"][0]["severity"] == "warning"
    assert payload["issues"][0]["page_index"] == 9
    assert payload["issues"][0]["paragraph_id"] == "para-keep"
    blob = _issue_blob(report)
    assert SOURCE_SECRET not in blob
    assert ERROR_SECRET not in blob
    assert "RuntimeError" not in blob


@pytest.mark.parametrize(
    "banner",
    [
        "You're using an older version of DeepL.",
        "请更新至最新版本。DeepL",
    ],
)
def test_deepl_deprecation_banner_keeps_source_and_records_translation_error(
    tmp_path: Path, banner: str
):
    config = _config(tmp_path, _Banner(banner), name=f"banner-{abs(hash(banner))}.pdf")
    report = _attach(config)
    engine = _translator(config)
    paragraph = _paragraph(SOURCE_SECRET, debug_id="deepl-banner")
    page = _page([paragraph])
    composition_ids = [id(comp) for comp in paragraph.pdf_paragraph_composition]

    _run_paragraph(engine, paragraph, page)

    assert _glyph_text(paragraph) == SOURCE_SECRET
    assert paragraph.unicode == SOURCE_SECRET
    assert [id(comp) for comp in paragraph.pdf_paragraph_composition] == composition_ids
    payload = report.to_dict()
    assert payload["status"] == "degraded"
    assert len(payload["issues"]) == 1
    issue = payload["issues"][0]
    assert issue["code"] == "translation_error"
    assert issue["severity"] == "warning"
    assert issue["details"] == {}
    blob = _issue_blob(report)
    assert banner not in blob
    assert SOURCE_SECRET not in blob


def test_unmapped_paragraph_page_is_not_recorded_as_original(tmp_path: Path):
    config = _config(tmp_path, _Raising(RuntimeError(ERROR_SECRET)))
    config.source_page_indices = (5,)
    report = _attach(config)
    engine = _translator(config)
    paragraph = _paragraph(SOURCE_SECRET, debug_id="unmapped-para")
    local_page = 3

    with pytest.raises(IndexError):
        _run_paragraph(engine, paragraph, _page([paragraph], number=local_page))

    assert all(issue["page_index"] != local_page for issue in report.to_dict()["issues"])
    assert _glyph_text(paragraph) == SOURCE_SECRET


def test_unmapped_layout_page_is_not_recorded_as_original(tmp_path: Path):
    config = _config(tmp_path, FixedMapTranslator(), name="layout-unmapped.pdf")
    config.source_page_indices = (5,)
    report = _attach(config)
    local_page = 3
    exc = LayoutIncompleteError(
        page_index=local_page,
        paragraph_id="layout-para",
        reason="contour_exhausted",
        requested_units=4,
        placed_units=1,
    )

    with pytest.raises(IndexError):
        record_layout_incomplete(config, exc)

    assert report.to_dict()["issues"] == []
    assert getattr(exc, "_quality_recorded", False) is False


def test_non_page_index_error_restores_source_and_records_translation_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    config = _config(
        tmp_path, _PlainTranslation(), name="later-index.pdf"
    )
    config.source_page_indices = (6, 7, 8, 9)
    report = _attach(config)
    engine = _translator(config)
    paragraph = _paragraph(SOURCE_SECRET, debug_id="later-index")
    page = _page([paragraph], number=3)
    composition_ids = [id(comp) for comp in paragraph.pdf_paragraph_composition]
    laid = "完整的中文译文。"

    def replace_then_fail(paragraph, tracker, translate_input, translated_text):  # noqa: ARG001
        replacement = _paragraph(laid, debug_id="laid-out")
        paragraph.pdf_paragraph_composition = replacement.pdf_paragraph_composition
        paragraph.unicode = replacement.unicode
        raise IndexError("layout slot")

    monkeypatch.setattr(engine, "post_translate_paragraph", replace_then_fail)

    _run_paragraph(engine, paragraph, page)

    assert _glyph_text(paragraph) == SOURCE_SECRET
    assert paragraph.unicode == SOURCE_SECRET
    assert [id(comp) for comp in paragraph.pdf_paragraph_composition] == composition_ids
    payload = report.to_dict()
    assert payload["status"] == "degraded"
    assert len(payload["issues"]) == 1
    issue = payload["issues"][0]
    assert issue["code"] == "translation_error"
    assert issue["severity"] == "warning"
    assert issue["page_index"] == 9
    assert issue["paragraph_id"] == "later-index"
    assert issue["details"] == {}
    blob = _issue_blob(report)
    assert "layout slot" not in blob
    assert "IndexError" not in blob
    assert SOURCE_SECRET not in blob
    assert laid not in blob


def test_still_missing_sentences_keep_source_and_warn(tmp_path: Path):
    source = "Alpha ends here. Beta ends here."
    config = _config(tmp_path, _Short())
    report = _attach(config)
    engine = _translator(config)
    paragraph = _paragraph(source, debug_id="drop-1")
    page = _page([paragraph])

    _run_paragraph(engine, paragraph, page)

    assert _glyph_text(paragraph) == source
    assert paragraph.unicode == source
    issue = report.to_dict()["issues"][0]
    assert issue["code"] == "missing_sentences"
    assert issue["severity"] == "warning"
    assert isinstance(issue["details"]["source_sentence_ends"], int)
    assert source not in _issue_blob(report)
    assert report.status == "degraded"


def test_exact_repeated_sentences_keep_source_and_warn(tmp_path: Path):
    source = "这是一个重复的句子。这是一个重复的句子。"
    engine_tr = _Mapped({})
    config = _config(tmp_path, engine_tr)
    report = _attach(config)
    engine = _translator(config)
    paragraph = _paragraph(source, debug_id="dup-src")
    page = _page([paragraph])

    _run_paragraph(engine, paragraph, page)

    assert engine_tr.calls == 0
    assert _glyph_text(paragraph) == source
    assert report.to_dict()["issues"][0]["code"] == "repeated_sentences"
    assert source not in _issue_blob(report)

    output = "这是一个重复的句子。这是一个重复的句子。"
    unique = "Body stays unique here."
    mapped = _Mapped({unique: output})
    config2 = _config(tmp_path, mapped, name="other.pdf")
    report2 = _attach(config2, run_id="run-2")
    engine2 = _translator(config2)
    paragraph2 = _paragraph(unique, debug_id="dup-out")
    _run_paragraph(engine2, paragraph2, _page([paragraph2]))
    assert _glyph_text(paragraph2) == unique
    assert paragraph2.unicode == unique
    assert report2.to_dict()["issues"][0]["code"] == "repeated_sentences"
    blob = _issue_blob(report2)
    assert unique not in blob
    assert output not in blob


def test_content_filter_warns_and_keeps_composition(tmp_path: Path):
    secret = "unsafe SECRET payload"
    config = _config(tmp_path, _Raising(ContentFilterError(secret)))
    report = _attach(config)
    engine = _translator(config)
    paragraph = _paragraph(SOURCE_SECRET, debug_id="filter-1")
    page = _page([paragraph])
    before = _glyph_text(paragraph)

    _run_paragraph(engine, paragraph, page)

    assert _glyph_text(paragraph) == before
    assert any("敏感" in (item.unicode or "") for item in page.pdf_paragraph)
    issue = report.to_dict()["issues"][0]
    assert issue["code"] == "content_filter"
    assert issue["details"] == {}
    assert secret not in _issue_blob(report)
    assert SOURCE_SECRET not in _issue_blob(report)


def test_url_and_footer_skips_record_no_quality_warning(tmp_path: Path):
    config = _config(
        tmp_path,
        _Raising(RuntimeError("should not translate")),
        skip_footer=True,
        footer_height=40,
    )
    report = _attach(config)
    engine = _translator(config)
    url = _paragraph("www.example.com", debug_id="url-1", box=Box(x=72, y=500, x2=200, y2=512))
    footer = _paragraph("Page footer", debug_id="foot-1", box=Box(x=72, y=4, x2=180, y2=16))
    docs = Document(page=[_page([url, footer])], total_pages=1)

    engine.translate(docs)

    assert report.to_dict()["issues"] == []
    reasons = engine.skip_report.counts_by_reason()
    assert reasons.get("url_chrome") == 1
    assert reasons.get("footer") == 1
    assert config.translator.calls == 0


def test_concurrent_tasks_use_registered_paragraph_ids(tmp_path: Path):
    config = _config(
        tmp_path,
        _Raising(RuntimeError(ERROR_SECRET)),
        pool_max_workers=4,
    )
    config.source_page_indices = (5, 6, 7)
    report = _attach(config)
    engine = _translator(config)
    first = _paragraph("First body sentence here.", debug_id=None)
    second = _paragraph("Second body sentence here.", debug_id=None)
    page = _page([first, second], number=2)
    docs = Document(page=[page], total_pages=1)

    engine.translate(docs)

    ids = [issue["paragraph_id"] for issue in report.to_dict()["issues"]]
    assert ids == ["p7:r0", "p7:r1"]
    assert all(issue["page_index"] == 7 for issue in report.to_dict()["issues"])
    assert str(id(first)) not in ids
    assert str(id(second)) not in ids
    assert "First body sentence here." not in _issue_blob(report)


def test_llm_batch_fallback_uses_shared_quality_report(tmp_path: Path):
    failing = _ScriptedLLM(fallback_ok=False)
    config = _config(tmp_path, failing, pool_max_workers=2)
    report = _attach(config, run_id="llm-fail")
    config.progress_monitor = ProgressMonitor([("Translate Paragraphs", 1.0)])
    llm = ILTranslatorLLMOnly(failing, config, tokenizer=_Tok())
    paragraph = _paragraph("Keep the original body here.", debug_id="llm-1")
    docs = Document(page=[_page([paragraph])], total_pages=1)

    llm.translate(docs)

    assert report is config.shared_context_cross_split_part.quality_report
    issues = report.to_dict()["issues"]
    assert len(issues) == 1
    assert issues[0]["code"] == "translation_error"
    assert issues[0]["paragraph_id"] == "llm-1"
    assert _glyph_text(paragraph) == "Keep the original body here."
    blob = _issue_blob(report)
    assert "Keep the original body here." not in blob
    assert "BATCH_SECRET" not in blob
    assert "PARA_SECRET" not in blob
    assert len(failing.calls) >= 2

    ok_engine = _ScriptedLLM(fallback_ok=True)
    config_ok = _config(tmp_path, ok_engine, name="llm-ok.pdf")
    report_ok = _attach(config_ok, run_id="llm-ok")
    config_ok.progress_monitor = ProgressMonitor([("Translate Paragraphs", 1.0)])
    llm_ok = ILTranslatorLLMOnly(ok_engine, config_ok, tokenizer=_Tok())
    ok_paragraph = _paragraph("Keep the original body here.", debug_id="llm-2")
    llm_ok.translate(Document(page=[_page([ok_paragraph])], total_pages=1))

    assert report_ok.to_dict()["issues"] == []
    assert report_ok.status == "success"
    assert _glyph_text(ok_paragraph) != "Keep the original body here."
    assert len(ok_engine.calls) >= 2


def test_layout_incomplete_is_failed_without_finish_and_uses_original_pages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    pdf = tmp_path / "book.pdf"
    _write_pdf(pdf, pages=2)
    config = TranslationConfig(
        translator=FixedMapTranslator(),
        input_file=pdf,
        lang_in="en",
        lang_out="zh-CN",
        doc_layout_model=object(),
        output_dir=tmp_path / "out",
        working_dir=tmp_path / "work",
        debug=False,
        auto_extract_glossary=False,
        split_strategy=_TwoParts(),
    )
    seen: list[tuple[int, ...] | None] = []
    shared_ids: list[int] = []

    def fake_single(pm, part_config):  # noqa: ARG001
        seen.append(part_config.source_page_indices)
        shared_ids.append(id(part_config.shared_context_cross_split_part.quality_report))
        if len(seen) == 1:
            return TranslateResult(None, None)
        raise LayoutIncompleteError(
            page_index=0,
            paragraph_id="layout-para",
            reason="contour_exhausted",
            requested_units=4,
            placed_units=1,
        )

    import babeldoc.format.pdf.high_level as high_level

    monkeypatch.setattr(high_level, "_do_translate_single", fake_single)
    events, finish = _events()
    monitor = ProgressMonitor([("Translate Paragraphs", 1.0)], finish_callback=finish)
    with pytest.raises(LayoutIncompleteError):
        do_translate(monitor, config)

    assert seen == [(0,), (1,)]
    assert shared_ids[0] == shared_ids[1]
    assert not any(event.get("type") == "finish" for event in events)
    reports = list((tmp_path / "out").glob("book.*.quality.json"))
    assert len(reports) == 1
    payload = json.loads(reports[0].read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    assert payload["schema_version"] == 1
    assert len(payload["issues"]) == 1
    issue = payload["issues"][0]
    assert issue["code"] == "layout_incomplete"
    assert issue["severity"] == "error"
    assert issue["page_index"] == 1
    assert issue["paragraph_id"] == "layout-para"
    assert issue["details"]["reason"] == "contour_exhausted"
    assert issue["details"]["requested_units"] == 4
    assert issue["details"]["placed_units"] == 1
    blob = json.dumps(payload, ensure_ascii=False)
    assert "layout-para body text" not in blob


def test_failed_document_omits_exception_text_and_cancel_stays_cancel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    secret = "secret boom TEXT"
    config = _config(tmp_path, FixedMapTranslator(), name="plain.pdf")
    events, finish = _events()
    monitor = ProgressMonitor([("Translate Paragraphs", 1.0)], finish_callback=finish)

    import babeldoc.format.pdf.high_level as high_level

    def boom(pm, part_config):  # noqa: ARG001
        raise RuntimeError(secret)

    monkeypatch.setattr(high_level, "_do_translate_single", boom)
    with pytest.raises(RuntimeError):
        do_translate(monitor, config)

    assert not any(event.get("type") == "finish" for event in events)
    reports = list((tmp_path / "out").glob("plain.*.quality.json"))
    assert len(reports) == 1
    payload = json.loads(reports[0].read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    assert secret not in json.dumps(payload, ensure_ascii=False)
    assert config.debug is False

    config_cancel = _config(tmp_path, FixedMapTranslator(), name="cancel.pdf")
    events_cancel, finish_cancel = _events()
    monitor_cancel = ProgressMonitor(
        [("Translate Paragraphs", 1.0)], finish_callback=finish_cancel
    )

    def cancel(pm, part_config):  # noqa: ARG001
        raise asyncio.CancelledError

    monkeypatch.setattr(high_level, "_do_translate_single", cancel)
    with pytest.raises(asyncio.CancelledError):
        do_translate(monitor_cancel, config_cancel)

    assert not any(event.get("type") == "finish" for event in events_cancel)
    assert list((tmp_path / "out").glob("cancel.*.quality.json")) == []


def test_success_publishes_distinct_reports_without_debug(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    import babeldoc.format.pdf.high_level as high_level

    def succeed(pm, part_config):  # noqa: ARG001
        part_config.shared_context_cross_split_part.quality_report.record(
            QualityIssue("translation", "translation_error", 0, "p1", "warning", {})
        )
        return TranslateResult(None, None)

    monkeypatch.setattr(high_level, "_do_translate_single", succeed)
    events, finish = _events()
    first = _config(tmp_path, FixedMapTranslator(), name="one.pdf")
    monitor = ProgressMonitor([("Translate Paragraphs", 1.0)], finish_callback=finish)
    result = do_translate(monitor, first)
    second = _config(tmp_path, FixedMapTranslator(), name="one.pdf")
    result_two = do_translate(
        ProgressMonitor([("Translate Paragraphs", 1.0)], finish_callback=finish),
        second,
    )

    assert result.quality_status == "degraded"
    assert result.quality_warning_count == 1
    assert result.quality_report_path is not None
    assert result.quality_report_path.is_file()
    assert result_two.quality_report_path != result.quality_report_path
    assert result.quality_report_path.is_file() and result_two.quality_report_path.is_file()
    body = result.quality_report_path.read_text(encoding="utf-8")
    assert "Keep this source sentence intact." not in body
    assert json.loads(body)["status"] == "degraded"
    assert any(event.get("type") == "finish" for event in events)
    assert first.debug is False
