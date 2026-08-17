#!/usr/bin/env python3
"""Diagnose font.unknown title: paragraph split + translate + typeset only."""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pymupdf

from babeldoc.docvision.doclayout import DocLayoutModel
from babeldoc.format.pdf import high_level
from babeldoc.format.pdf.document_il.midend.detect_scanned_file import (
    enable_ocr_workaround_for_searchable_image,
)
from babeldoc.format.pdf.translation_config import TranslationConfig
from babeldoc.format.pdf.translation_config import WatermarkOutputMode
from babeldoc.translator.fixed_map_translator import FixedMapTranslator

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "tests/golden/translate.cli.font.unknown.pdf"


class MapT(FixedMapTranslator):
    def __init__(self):
        super().__init__(
            {
                "The sociology of news production": "新闻生产的社会学",
                "Michael Schudson": "迈克尔·舒德森",
                "UNIVERSITY OF CALIFORNIA, SAN DIEGO": "加州大学圣地亚哥分校",
            }
        )


async def main() -> None:
    workdir = Path(tempfile.mkdtemp(prefix="fu_diag_"))
    print("workdir", workdir)
    model = DocLayoutModel.load_available()
    cfg = TranslationConfig(
        translator=MapT(),
        input_file=str(SRC),
        lang_in="en",
        lang_out="zh-CN",
        doc_layout_model=model,
        auto_extract_glossary=False,
        working_dir=str(workdir),
        output_dir=str(workdir / "out"),
        watermark_output_mode=WatermarkOutputMode.NoWatermark,
        debug=True,
        skip_header=False,
        skip_footer=False,
    )
    async for event in high_level.async_translate(cfg):
        if isinstance(event, dict) and event.get("type") not in (
            "progress_start",
            "progress_update",
            "progress_end",
        ):
            print("event", event.get("type"))

    out = list((workdir / "out").glob("*.mono.pdf"))
    print("outputs", out)
    if not out:
        return
    page = pymupdf.open(out[0])[0]
    text = page.get_text()
    print("has 新闻生产", "新闻生产" in text)
    print("has 舒德森", "舒德森" in text)
    print("has Michael", "Michael" in text)
    print("--- top text ---")
    print(text[:500])

    # dump debug json titles if any
    for j in sorted(workdir.rglob("*typeset*.json"))[:5]:
        print("json", j)
    for j in sorted(workdir.rglob("*paragraph*.json"))[:5]:
        print("json", j)


if __name__ == "__main__":
    asyncio.run(main())
