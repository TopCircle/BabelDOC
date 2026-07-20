#!/usr/bin/env python3
"""E2E verify: font.unknown dual must not split 感情 / 第11卷（1989年）."""

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
OUT = ROOT / "dual_quality_out" / "font_unknown_fix_verify"

MAPPING = {
    "The sociology of news production": "新闻制作社会学",
    "Michael Schudson": "迈克尔-舒德森",
    "UNIVERSITY OF CALIFORNIA, SAN DIEGO": "加州大学圣地亚哥分校",
    (
        "Social scientists who study the news speak a language that journalists "
        "mistrust and misunderstand. They speak of 'constructing the news', of "
        "'making news', of the 'social construction of reality'. 'News is what "
        "newspapermen make it' (Gieber, 1964: 173). 'News is the result of the "
        "methods newsworkers employ' (Fishman, 1980: 14). News is 'manufactured "
        "by journalists' (Cohen and Young, 1973: 97). Even journalists who are "
        "critical of the daily practices of their colleagues and their own "
        "organizations find this talk offensive. I have been at several "
        "conferences of journalists and social scientists where such language "
        "promptly pushed the journalists into a fierce defence of their work, on "
        "the familiar ground that they just report the world as they see it, the "
        "facts, facts, and nothing but the facts, and yes, there's occasional "
        "bias, occasional sensationalism, occasional inaccuracy, but a "
        "responsible journalist never, never, never fakes the news."
    ): (
        "研究新闻的社会科学家使用了一种新闻记者不信任和误解的语言。"
        "他们说的是「构建新闻」、「制造新闻」、「现实的社会建构」。"
        "新闻是新闻工作者所使用方法的结果（Fishman, 1980:14）。"
        "新闻是「记者制造出来的」（Cohen 和 Young, 1973: 97）。"
        "即使是对同事和自己所在机构的日常做法持批评态度的记者，也会觉得这种言论具有攻击性。"
        "我参加过几次记者和社会科学家的会议，在这些会议上，这种言辞很快就把记者推向了"
        "为他们的工作进行激烈辩护的境地，理由是他们只是报道他们所看到的世界，报道事实，"
        "事实，除了事实什么都没有，是的，偶尔会有偏见，偶尔会有感情用事，偶尔会有不准确的地方，"
        "但一个负责任的记者永远、永远、永远不会伪造新闻。"
    ),
    (
        "That's not what we said, the hurt scholars respond. We didn't "
        "say journalists fake the news, we said journalists make the news:"
    ): (
        "受伤的学者们回应说，我们不是这么说的。我们没说记者伪造新闻，我们说的是记者制造新闻："
    ),
    (
        "To say that a news report is a story, no more, but no less, is not to "
        "demean the news, not to accuse it of being fictitious. Rather, it "
        "alerts us that news, like all public documents, is a constructed "
        "reality possessing its own internal validity."
    ): (
        "说新闻报道是一个故事，不多也不少，并不是贬低新闻，也不是指责新闻是虚构的。"
        "相反，它提醒我们，新闻与所有公共文件一样，是一种建构的现实，拥有其自身的内在有效性。"
    ),
    "(Tuchman, 1976: 97)": "（Tuchman, 1976: 97）",
    (
        "In the most elementary way, this is obvious. Journalists write the "
        "words that turn up in the papers or on the screen as stories. Not "
        "government officials, not cultural forces, not 'reality' magically"
    ): (
        "从最基本的角度看，这是显而易见的。记者撰写的文字作为故事出现在报纸或屏幕上。"
        "不是政府官员，不是文化力量，也不是「现实」神奇地"
    ),
    (
        "Media, Culture and Society (SAGE, London, Newbury Park and New Delhi), "
        "Vol. 11 (1989), 263-282"
    ): (
        "媒体、文化与社会》（SAGE，伦敦，纽伯里公园和新德里），"
        "第11卷（1989年），263-282页"
    ),
}


def main() -> int:
    if not SRC.is_file():
        print("missing", SRC, file=sys.stderr)
        return 2

    OUT.mkdir(parents=True, exist_ok=True)
    workdir = Path(tempfile.mkdtemp(prefix="fu_fix_"))
    model = DocLayoutModel.load_available()
    cfg = TranslationConfig(
        translator=FixedMapTranslator(MAPPING),
        input_file=str(SRC),
        lang_in="en",
        lang_out="zh-CN",
        doc_layout_model=model,
        auto_extract_glossary=False,
        working_dir=str(workdir),
        output_dir=str(OUT),
        watermark_output_mode=WatermarkOutputMode.NoWatermark,
        debug=False,
        auto_enable_ocr_workaround=True,
        dual_translate_first=True,
        no_dual=False,
        no_mono=True,
    )

    async def run() -> None:
        async for event in high_level.async_translate(cfg):
            if isinstance(event, dict) and event.get("type") in ("error", "finish"):
                print("event", event.get("type"), event.get("error") or event.get("message"))

    asyncio.run(run())
    pdfs = sorted(OUT.glob("*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not pdfs:
        print("no pdf in", OUT, file=sys.stderr)
        return 1
    duals = [p for p in pdfs if "dual" in p.name]
    pdf = duals[0] if duals else pdfs[0]

    doc = pymupdf.open(pdf)
    page = doc[0]
    mid = page.rect.width / 2
    left = pymupdf.Rect(0, 0, mid, page.rect.height)
    lines: list[tuple[float, str]] = []
    for b in page.get_text("dict", clip=left)["blocks"]:
        if b.get("type") != 0:
            continue
        for line in b.get("lines", []):
            spans = "".join(s.get("text", "") for s in line.get("spans", []))
            lines.append((line["bbox"][1], spans))

    print("pdf", pdf)
    print("=== LEFT LINES ===")
    for y, s in lines:
        print(f"  y={y:.1f}: {s!r}")

    bad: list[str] = []
    for i, (_y, s) in enumerate(lines):
        if s.rstrip().endswith("（") or s.rstrip().endswith("("):
            bad.append(f"open-paren EOL: {s!r}")
        if s.endswith("感") and i + 1 < len(lines) and lines[i + 1][1].startswith("情"):
            bad.append("感|情 split")
        if s.endswith("德") and i + 1 < len(lines) and lines[i + 1][1].startswith("里"):
            bad.append("德|里 split")
        if "第" in s and s.rstrip().endswith("卷（"):
            bad.append(f"卷（ EOL: {s!r}")

    pix = page.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5), clip=left)
    preview = OUT / "left_preview.png"
    pix.save(str(preview))
    doc.close()
    print("preview", preview)
    print("BAD", bad or "none")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
