"""Synthetic PDFs translated through the real parse, typeset, and write path.

Only layout-model inference is replaced. The model object is truthy so
``TranslationConfig`` does not load ONNX when the model is ``None``.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import socket
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pymupdf
from babeldoc.docvision.base_doclayout import YoloBox
from babeldoc.docvision.base_doclayout import YoloResult
from babeldoc.format.pdf.high_level import async_translate
from babeldoc.format.pdf.translation_config import TranslateResult
from babeldoc.format.pdf.translation_config import TranslationConfig
from babeldoc.format.pdf.translation_config import WatermarkOutputMode

PAGE_W = 420.0
PAGE_H = 320.0
HEADING_W = 720.0
HEADING_H = 360.0
PHOTO_OBSTACLE = (300, 40, 400, 200)
_CASE_TIMEOUT_S = 300

BODY_LINES = (
    "This is the first paragraph.",
    "Keep API and BDSM here.",
)
BODY_SOURCE = " ".join(BODY_LINES)
BODY_TARGET = "这是第一段。这里保留 API 与 BDSM。"
PHOTO_SOURCE = "Stay left of the photo."
PHOTO_TARGET = "留在照片左侧。"
SECOND_SOURCE = "First body stays above the second body."
SECOND_TARGET = "第一段在第二段之上。"
HEADING_TITLE = "Chapter One"
HEADING_TITLE_TARGET = "第一章"
# A点 / G点 are source glyphs in a formula font so typesetting does not
# open a CJK/Latin gap inside the token. Placeholders are per paragraph.
HEADING_SPOT_KEY = "Find the <b1>and the <b2>."
HEADING_SPOT_TARGET = "找到<b1>与<b2>。"
_SPOT_FONT_PATTERN = r"Source Han Sans CN"
HEADING_FORMULA = "Energy is E <b1>mc2 and the count is 12."
HEADING_FORMULA_TARGET = "能量是E<b1>mc2，计数为12。"
HEADING_TAIL = "First body stays above the second body."
HEADING_TAIL_TARGET = "第一段在第二段之上。"
UNMAPPED_SOURCE = "This sentence stays in English on purpose."
CONTOUR_LINES = (
    "Alpha beta gamma delta epsilon zeta eta theta iota kappa",
    "Alpha beta gamma delta epsilon zeta eta theta iota",
    "Alpha beta gamma delta epsilon zeta eta theta",
    "Alpha beta gamma delta epsilon zeta eta",
    "Alpha beta gamma delta epsilon zeta",
    "Alpha beta gamma delta epsilon",
)
CONTOUR_SOURCE = " ".join(CONTOUR_LINES)

DELIVERY_CASES = (
    "body",
    "photo_wrap",
    "toc",
    "heading_formula",
    "contour_exhausted",
    "translator_error",
    "split_two_parts",
)

_ASSETS_OK = False


@dataclass
class DeliveryFixtureResult:
    result: TranslateResult | None
    events: list[dict]
    quality: dict
    extracted_target_text: str
    invalid_page_bookmarks: list[int]


class DeterministicLayout:
    """Yield fixed YOLO boxes. Truthy so TranslationConfig skips ONNX."""

    def __init__(self, results: list[YoloResult]):
        self._results = results

    def handle_document(self, pages, mupdf_doc, translate_config, save_debug_image):
        del mupdf_doc, translate_config, save_debug_image
        # A split part receives only its own pages. Repeat the last box when
        # every page uses the same plain-text layout.
        for index, page in enumerate(pages):
            chosen = self._results[index if index < len(self._results) else -1]
            yield page, chosen


def _box(xyxy: tuple[float, float, float, float], cls: int, conf: float = 0.99):
    return YoloBox(
        xyxy=np.array(xyxy, dtype=np.float64),
        conf=np.float64(conf),
        cls=cls,
    )


def _plain_page(width: float, height: float) -> YoloResult:
    return YoloResult(
        names={0: "plain text"},
        boxes=[_box((1, 1, width - 1, height - 1), 0)],
    )


def _fold(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _ensure_assets() -> None:
    global _ASSETS_OK
    if _ASSETS_OK:
        return
    from pipeline_assets import check_assets

    missing = check_assets()
    if missing:
        raise RuntimeError(
            "delivery fixture assets missing or corrupt: " + ", ".join(missing)
        )
    _ASSETS_OK = True


def _stamp_source(source: Path, output_dir: Path) -> None:
    payload = {
        "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "mtime_ns": source.stat().st_mtime_ns,
    }
    (output_dir / "source-stamp.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )


def _write_body_lines(page) -> None:
    page.insert_text((40, 80), BODY_LINES[0], fontsize=12, fontname="helv")
    page.insert_text((40, 100), BODY_LINES[1], fontsize=12, fontname="helv")


def _insert_photo(page) -> None:
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 80, 120), 0)
    pixmap.set_rect(pixmap.irect, (180, 40, 40))
    page.insert_image(pymupdf.Rect(*PHOTO_OBSTACLE), pixmap=pixmap)
    page.insert_text((40, 120), PHOTO_SOURCE, fontsize=12, fontname="helv")


def _spot_font_file() -> str:
    from babeldoc.const import CACHE_FOLDER

    path = Path(CACHE_FOLDER) / "fonts" / "SourceHanSansCN-Regular.ttf"
    if not path.is_file():
        raise RuntimeError(f"delivery fixture font missing: {path}")
    return str(path)


def _insert_heading(page) -> None:
    page.insert_text((40, 55), HEADING_TITLE, fontsize=18, fontname="helv")
    fontfile = _spot_font_file()
    page.insert_font(fontname="spot", fontfile=fontfile)
    helv = pymupdf.Font("helv")
    spot = pymupdf.Font(fontfile=fontfile)
    x = 40.0
    size = 12.0
    for text, fontname, measure in (
        ("Find the ", "helv", helv),
        ("A点", "spot", spot),
        (" and the ", "helv", helv),
        ("G点", "spot", spot),
        (".", "helv", helv),
    ):
        page.insert_text((x, 120), text, fontsize=size, fontname=fontname)
        x += measure.text_length(text, fontsize=size)
    page.insert_text(
        (40, 180),
        "Energy is E = mc2 and the count is 12.",
        fontsize=12,
        fontname="helv",
    )
    page.insert_text((40, 240), HEADING_TAIL, fontsize=12, fontname="helv")


def _insert_contour(page) -> None:
    for index, line in enumerate(CONTOUR_LINES):
        page.insert_text(
            (30 + index * 14, 60 + index * 18),
            line,
            fontsize=12,
            fontname="helv",
        )


def _photo_layout() -> YoloResult:
    return YoloResult(
        names={0: "plain text", 1: "figure"},
        boxes=[
            _box((20, 80, 250, 180), 0),
            _box(PHOTO_OBSTACLE, 1, 0.95),
        ],
    )


def _heading_layout() -> YoloResult:
    return YoloResult(
        names={0: "plain text", 1: "title"},
        boxes=[
            _box((20, 20, 360, 80), 1),
            _box((20, 90, 680, 145), 0, 0.99),
            _box((20, 155, 680, 205), 0, 0.9),
            _box((20, 215, 680, 280), 0, 0.8),
        ],
    )


def _build_case(
    case_name: str, source: Path
) -> tuple[dict[str, str], list, bool, str | None]:
    if case_name not in DELIVERY_CASES:
        raise KeyError(case_name)
    document = pymupdf.open()
    split = False
    formula_font = None
    if case_name == "body":
        _write_body_lines(document.new_page(width=PAGE_W, height=PAGE_H))
        layouts = [_plain_page(PAGE_W, PAGE_H)]
        mapping = {BODY_SOURCE: BODY_TARGET}
    elif case_name == "photo_wrap":
        _insert_photo(document.new_page(width=PAGE_W, height=PAGE_H))
        layouts = [_photo_layout()]
        mapping = {PHOTO_SOURCE: PHOTO_TARGET}
    elif case_name == "toc":
        _write_body_lines(document.new_page(width=PAGE_W, height=PAGE_H))
        document.new_page(width=PAGE_W, height=PAGE_H).insert_text(
            (40, 80),
            SECOND_SOURCE,
            fontsize=12,
            fontname="helv",
        )
        document.set_toc([[1, "First", 1], [1, "Second", 2]])
        layouts = [_plain_page(PAGE_W, PAGE_H), _plain_page(PAGE_W, PAGE_H)]
        mapping = {BODY_SOURCE: BODY_TARGET, SECOND_SOURCE: SECOND_TARGET}
    elif case_name == "heading_formula":
        _insert_heading(document.new_page(width=HEADING_W, height=HEADING_H))
        layouts = [_heading_layout()]
        mapping = {
            HEADING_TITLE: HEADING_TITLE_TARGET,
            HEADING_SPOT_KEY: HEADING_SPOT_TARGET,
            HEADING_FORMULA: HEADING_FORMULA_TARGET,
            HEADING_TAIL: HEADING_TAIL_TARGET,
        }
        formula_font = _SPOT_FONT_PATTERN
    elif case_name == "contour_exhausted":
        _insert_contour(document.new_page(width=PAGE_W, height=PAGE_H))
        layouts = [_plain_page(PAGE_W, PAGE_H)]
        mapping = {CONTOUR_SOURCE: "中" * 400}
    elif case_name == "translator_error":
        document.new_page(width=PAGE_W, height=PAGE_H).insert_text(
            (40, 80),
            UNMAPPED_SOURCE,
            fontsize=12,
            fontname="helv",
        )
        layouts = [_plain_page(PAGE_W, PAGE_H)]
        mapping = {}
    else:
        _write_body_lines(document.new_page(width=PAGE_W, height=PAGE_H))
        document.new_page(width=PAGE_W, height=PAGE_H).insert_text(
            (40, 80),
            UNMAPPED_SOURCE,
            fontsize=12,
            fontname="helv",
        )
        layouts = [_plain_page(PAGE_W, PAGE_H), _plain_page(PAGE_W, PAGE_H)]
        mapping = {BODY_SOURCE: BODY_TARGET}
        split = True
    source.parent.mkdir(parents=True, exist_ok=True)
    document.save(source)
    document.close()
    return mapping, layouts, split, formula_font


def _config(
    source: Path,
    output_dir: Path,
    layouts: list,
    mapping: dict,
    split: bool,
    formula_font: str | None,
):
    from test_pipeline_delivery_e2e import StrictFixedMapTranslator

    return TranslationConfig(
        StrictFixedMapTranslator(mapping),
        str(source),
        "en",
        "zh-CN",
        DeterministicLayout(layouts),
        output_dir=str(output_dir),
        working_dir=str(output_dir / "work"),
        debug=False,
        no_dual=True,
        watermark_output_mode=WatermarkOutputMode.NoWatermark,
        auto_extract_glossary=False,
        skip_scanned_detection=True,
        skip_clean=True,
        qps=1,
        pool_max_workers=1,
        report_interval=5.0,
        use_rich_pbar=False,
        formular_font_pattern=formula_font,
        split_strategy=(
            TranslationConfig.create_max_pages_per_part_split_strategy(1)
            if split
            else None
        ),
    )


def _refuse_socket(*_args, **_kwargs):
    raise AssertionError("offline delivery fixture blocked a real socket")


async def _collect(config: TranslationConfig):
    events: list[dict] = []
    result: TranslateResult | None = None
    # Break on the terminal event. Waiting for another queue item races
    # AsyncCallback.finished and can block after a successful finish.
    async for event in async_translate(config):
        stored = {"type": event["type"]}
        if event["type"] == "error":
            stored["error"] = str(event.get("error"))
            events.append(stored)
            break
        if event["type"] == "finish":
            result = event.get("translate_result")
            events.append(stored)
            break
        events.append(stored)
    return result, events


def _result_pdf(result: TranslateResult | None) -> Path | None:
    if result is None:
        return None
    for attr in ("no_watermark_mono_pdf_path", "mono_pdf_path"):
        path = getattr(result, attr, None)
        if path and Path(path).is_file():
            return Path(path)
    return None


def _extracted_text(result: TranslateResult | None) -> str:
    path = _result_pdf(result)
    if path is None:
        return ""
    chunks: list[str] = []
    with pymupdf.open(path) as document:
        for page in document:
            chunks.append(page.get_text())
    return _fold("\n".join(chunks))


def _invalid_bookmarks(result: TranslateResult | None) -> list[int]:
    path = _result_pdf(result)
    if path is None:
        return []
    invalid: list[int] = []
    with pymupdf.open(path) as document:
        for _level, _title, page in document.get_toc():
            if page < 1 or page > document.page_count:
                invalid.append(int(page))
    return invalid


def _quality(output_dir: Path) -> dict:
    files = sorted(path for path in output_dir.glob("*.quality.json") if path.is_file())
    if len(files) != 1:
        raise RuntimeError(
            f"expected one quality report in {output_dir}, found {len(files)}"
        )
    return json.loads(files[0].read_text(encoding="utf-8"))


def run_delivery_fixture(case_name: str, output_dir: Path) -> DeliveryFixtureResult:
    """Translate one synthetic case through the real delivery pipeline."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    _ensure_assets()
    source = output_dir / "source.pdf"
    mapping, layouts, split, formula_font = _build_case(case_name, source)
    _stamp_source(source, output_dir)
    config = _config(source, output_dir, layouts, mapping, split, formula_font)
    with (
        patch.object(socket.socket, "connect", _refuse_socket),
        patch("socket.create_connection", _refuse_socket),
    ):
        result, events = asyncio.run(
            asyncio.wait_for(_collect(config), timeout=_CASE_TIMEOUT_S)
        )
    return DeliveryFixtureResult(
        result=result,
        events=events,
        quality=_quality(output_dir),
        extracted_target_text=_extracted_text(result),
        invalid_page_bookmarks=_invalid_bookmarks(result),
    )
