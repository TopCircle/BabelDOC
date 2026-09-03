#!/usr/bin/env python3
"""Local repro: font.unknown dual should keep ZH title after OCR layout fix."""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

import pymupdf
from babeldoc.docvision.doclayout import DocLayoutModel
from babeldoc.format.pdf import high_level
from babeldoc.format.pdf.translation_config import TranslationConfig
from babeldoc.format.pdf.translation_config import WatermarkOutputMode
from babeldoc.translator.fixed_map_translator import FixedMapTranslator

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "tests/golden/translate.cli.font.unknown.pdf"


def main() -> int:
    if not SRC.is_file():
        print("missing", SRC, file=sys.stderr)
        return 2

    workdir = Path(tempfile.mkdtemp(prefix="fu_title_"))
    model = DocLayoutModel.load_available()
    cfg = TranslationConfig(
        translator=FixedMapTranslator(
            {
                "The sociology of news production": "新闻生产的社会学",
                "Michael Schudson": "迈克尔·舒德森",
                "UNIVERSITY OF CALIFORNIA, SAN DIEGO": "加州大学圣地亚哥分校",
            }
        ),
        input_file=str(SRC),
        lang_in="en",
        lang_out="zh-CN",
        doc_layout_model=model,
        auto_extract_glossary=False,
        working_dir=str(workdir),
        output_dir=str(workdir / "out"),
        watermark_output_mode=WatermarkOutputMode.NoWatermark,
        debug=False,
    )

    async def run() -> None:
        async for _ in high_level.async_translate(cfg):
            pass

    asyncio.run(run())
    duals = list((workdir / "out").glob("*.dual.pdf"))
    monos = list((workdir / "out").glob("*.mono.pdf"))
    pdf = monos[0] if monos else (duals[0] if duals else None)
    if pdf is None:
        print("no output pdf in", workdir / "out", file=sys.stderr)
        return 1

    doc = pymupdf.open(pdf)
    page = doc[0]
    text = page.get_text()
    mid = page.rect.width / 2
    left_top = []
    for b in page.get_text("dict")["blocks"]:
        if b.get("type") != 0:
            continue
        for line in b.get("lines", []):
            for sp in line.get("spans", []):
                bb = sp["bbox"]
                cx = (bb[0] + bb[2]) / 2
                if cx < mid and bb[1] < 120:
                    left_top.append((bb[1], sp.get("text", "")))
    doc.close()

    has_title = "新闻生产" in text or "社会学" in text
    has_author = "舒德森" in text or "迈克尔" in text
    print("pdf", pdf)
    print("has_zh_title", has_title, "has_zh_author", has_author)
    print("top left spans:")
    for y, t in sorted(left_top)[:12]:
        print(f"  y={y:.1f} {t!r}")
    return 0 if has_title else 1


if __name__ == "__main__":
    raise SystemExit(main())
