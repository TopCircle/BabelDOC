#!/usr/bin/env python3
"""OA wave W0/R0: identity-MT skip_report + IL dump (no DeepLX).

Skip predicates run inside ILTranslator. ``--skip-translation`` would skip
that stage and produce an empty report — this harness uses FixedMap identity
instead, matching the 0.6.4.69 dual skip_header=True / header_height=40 setup.

Default pages are the W0 1-based PDF subset from
docs/oa-dual-quality-wave-0.6.4.69.md (book p3/p5/… not book numbers).

Example::

    PYTHONPATH=/Users/yun/workspace/BabelDOC-oa-r0 \\
      /Users/yun/workspace/BabelDOC/.venv/bin/python \\
      scripts/oa_r0_skip_report.py --smoke
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

# Full-book source is 121 pages: PDF 1–2 = cover/ToC, PDF N = book pN.
# Wave table's "book = pdf+2" applies to the 118-page dual, NOT this file.
# --pages is 1-based PDF = book page number on Orgasmic Addiction.pdf.
W0_PAGES = "3,5,7,9,19,32,33,41,45,59,63,68,91"
SMOKE_PAGES = "5"  # book p5 — formula + pull-quote

DEFAULT_PDF = (
    "/Users/yun/Library/CloudStorage/OneDrive-Personal/Documentos/"
    "Books/Gabrielle Moore/Orgasmic Addiction/Orgasmic Addiction.pdf"
)
DEFAULT_OUT = Path("/Users/yun/workspace/BabelDOC/tmp/oa_r0")
B0_WORKTREE = Path("/Users/yun/workspace/BabelDOC-oa-r0")

# Prefer the B0 worktree over an editable install of the main checkout.
if B0_WORKTREE.is_dir():
    sys.path.insert(0, str(B0_WORKTREE))


def _import_babeldoc():
    from babeldoc.format.pdf.high_level import translate
    from babeldoc.format.pdf.translation_config import TranslationConfig
    from babeldoc.format.pdf.translation_config import WatermarkOutputMode
    from babeldoc.translator.fixed_map_translator import FixedMapTranslator

    return translate, TranslationConfig, WatermarkOutputMode, FixedMapTranslator


def find_skip_report(working_dir: Path) -> Path | None:
    hits = sorted(working_dir.rglob("skip_report.json"))
    return hits[0] if hits else None


def summarize_report(report: dict) -> dict:
    events = report.get("events") or report.get("skips") or []
    if not events and isinstance(report.get("by_reason"), dict):
        events = []
    reasons = Counter()
    pages = Counter()
    extras = 0
    for ev in events:
        reason = ev.get("reason") or ev.get("skip_reason") or "?"
        reasons[reason] += 1
        pages[ev.get("page_number", ev.get("page", "?"))] += 1
        if ev.get("debug_extra"):
            extras += 1
    return {
        "total": report.get("total", len(events)),
        "schema_version": report.get("schema_version"),
        "by_reason": dict(reasons),
        "by_page_number": {str(k): v for k, v in sorted(pages.items(), key=lambda kv: str(kv[0]))},
        "events_with_debug_extra": extras,
    }


def run(
    *,
    pdf: Path,
    pages: str,
    out_dir: Path,
    skip_header: bool,
    header_height: float,
) -> Path:
    translate, TranslationConfig, WatermarkOutputMode, FixedMapTranslator = (
        _import_babeldoc()
    )
    working_dir = out_dir / "working"
    pdf_out = out_dir / "out"
    working_dir.mkdir(parents=True, exist_ok=True)
    pdf_out.mkdir(parents=True, exist_ok=True)

    config = TranslationConfig(
        translator=FixedMapTranslator({}),
        input_file=str(pdf),
        lang_in="en",
        lang_out="zh-CN",
        doc_layout_model=None,
        pages=pages,
        output_dir=str(pdf_out),
        working_dir=str(working_dir),
        debug=True,
        no_dual=True,
        watermark_output_mode=WatermarkOutputMode.NoWatermark,
        skip_header=skip_header,
        header_height=header_height,
        skip_footer=False,
    )
    print(
        f"[oa_r0] babeldoc={sys.modules['babeldoc'].__file__}\n"
        f"[oa_r0] pdf={pdf}\n"
        f"[oa_r0] pages={pages} skip_header={skip_header} header_height={header_height}\n"
        f"[oa_r0] working={working_dir}",
        flush=True,
    )
    translate(config)
    report_path = find_skip_report(working_dir)
    if report_path is None:
        raise SystemExit(f"skip_report.json not written under {working_dir}")
    archive = out_dir / "skip_report.json"
    shutil.copy2(report_path, archive)
    report = json.loads(archive.read_text(encoding="utf-8"))
    summary = summarize_report(report)
    summary["source_report"] = str(report_path)
    summary["archive"] = str(archive)
    (out_dir / "skip_report_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False), flush=True)
    return archive


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--pdf", type=Path, default=Path(DEFAULT_PDF))
    p.add_argument("--pages", default=W0_PAGES, help="1-based PDF pages (not book pages)")
    p.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    p.add_argument("--smoke", action="store_true", help=f"Only PDF page {SMOKE_PAGES} (book p5)")
    p.add_argument("--no-skip-header", action="store_true")
    p.add_argument("--header-height", type=float, default=40.0)
    args = p.parse_args()
    if not args.pdf.is_file():
        raise SystemExit(f"PDF not found: {args.pdf}")
    pages = SMOKE_PAGES if args.smoke else args.pages
    run(
        pdf=args.pdf,
        pages=pages,
        out_dir=args.out_dir,
        skip_header=not args.no_skip_header,
        header_height=args.header_height,
    )


if __name__ == "__main__":
    main()
