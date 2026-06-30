#!/usr/bin/env python3
"""
Focused diagnostic: analyze LESSON fragmentation, "ther" residuals,
XObject boundaries, and multi-font lines in a PDF through BabelDOC's IL pipeline.

Usage:
    python3 debug_analyze_pdf.py Day_1.pdf --pages "6,20"
"""

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))

from babeldoc.format.pdf.document_il import il_version_1
from babeldoc.format.pdf.parse_only import parse_with_legacy_ir
from babeldoc.format.pdf.parse_shared import _ParseOnlyDocLayoutModel
from babeldoc.format.pdf.translation_config import TranslationConfig
from babeldoc.progress_monitor import ProgressMonitor


def run_paragraph_finder(il):
    """Run paragraph_finder on the IL."""
    from babeldoc.format.pdf.document_il.midend.paragraph_finder import ParagraphFinder

    config = TranslationConfig(
        translator=None,
        input_file="",
        lang_in="",
        lang_out="",
        doc_layout_model=_ParseOnlyDocLayoutModel(),
        progress_monitor=ProgressMonitor([("Parse Paragraphs", 1.0)]),
        auto_extract_glossary=False,
        skip_translation=True,
        table_model=None,
    )
    finder = ParagraphFinder(config)
    for page in il.page:
        finder.process_page(page)
    return finder


def analyze_page(page, page_num, font_registry):
    """Compact analysis focusing on keyword matches and structural issues."""
    chars = page.pdf_character
    if not chars:
        print(f"  (no chars)")
        return

    # Group by visual line
    LINE_Y_TOLERANCE = 5
    lines = []
    sorted_chars = sorted(chars, key=lambda c: (c.visual_bbox.box.y if c.visual_bbox else 0))
    for c in sorted_chars:
        if not c.visual_bbox:
            continue
        cy = c.visual_bbox.box.y
        placed = False
        for line in lines:
            if abs(line["y"] - cy) < LINE_Y_TOLERANCE:
                line["chars"].append(c)
                placed = True
                break
        if not placed:
            lines.append({"y": cy, "chars": [c]})
    lines.sort(key=lambda l: l["y"])

    # Quick stats
    font_ids = {}
    xobj_ids = {}
    for c in chars:
        fid = c.pdf_style.font_id if c.pdf_style else None
        xid = c.xobj_id
        font_ids[fid] = font_ids.get(fid, 0) + 1
        xobj_ids[xid] = xobj_ids.get(xid, 0) + 1

    has_multi_xobj = len([k for k, v in xobj_ids.items() if v > 0 and k != 0]) > 0
    multi_font_lines = 0
    keyword_lines = []

    print(f"\n  Chars={len(chars)}  Fonts={len(font_ids)}  XObjs={len(xobj_ids)}"
          f"  Lines≈{len(lines)}")
    print(f"  Font dist: {{{', '.join(f'{k}:{v}' for k,v in sorted(font_ids.items(), key=lambda x:-x[1])[:6])}}}")
    if has_multi_xobj:
        xobj_nonzero = {k: v for k, v in sorted(xobj_ids.items(), key=lambda x: -x[1]) if k != 0}
        print(f"  XObj non-0: {xobj_nonzero}")

    for li, line in enumerate(lines):
        lchars = sorted(line["chars"], key=lambda c: c.visual_bbox.box.x if c.visual_bbox else 0)
        text = "".join(c.char_unicode or "" for c in lchars)
        fids = set()
        xids = set()
        for c in lchars:
            if c.pdf_style and c.pdf_style.font_id:
                fids.add(c.pdf_style.font_id)
            if c.xobj_id is not None:
                xids.add(c.xobj_id)

        is_interesting = False
        reasons = []
        if "LESSON" in text.upper():
            is_interesting = True
            reasons.append("LESSON")
        if "ther" in text.lower() and len(text) < 200:
            is_interesting = True
            reasons.append("ther")
        if len(fids) > 1:
            is_interesting = True
            reasons.append(f"MULTI-FONT({fids})")
            multi_font_lines += 1
        if len(xids) > 1:
            is_interesting = True
            reasons.append(f"MULTI-XOBJ({xids})")

        if is_interesting:
            keyword_lines.append((li, line, text, fids, xids, reasons))

    # Show all interesting lines
    print(f"\n  Interesting lines: {len(keyword_lines)} (multi-font: {multi_font_lines})")
    for li, line, text, fids, xids, reasons in keyword_lines:
        lchars = sorted(line["chars"], key=lambda c: c.visual_bbox.box.x if c.visual_bbox else 0)
        print(f"\n  L{li} y={line['y']:.0f} | {' '.join(reasons)}")
        print(f"    text: {repr(text[:200])}")

        # Show per-char details for XObject boundaries or LESSON
        if "LESSON" in reasons or "MULTI-XOBJ" in reasons or "ther" in reasons:
            prev_xid = None
            for ci, c in enumerate(lchars):
                fid = c.pdf_style.font_id if c.pdf_style else "?"
                fs = c.pdf_style.font_size if c.pdf_style else 0
                xid = c.xobj_id
                uc = c.char_unicode or ""
                cbox = c.visual_bbox.box if c.visual_bbox else None
                finfo = font_registry.get(fid)
                b = f"b={finfo.bold}" if finfo else "?"
                i = f"i={finfo.italic}" if finfo else ""

                # Mark XObject transitions
                xobj_flag = ""
                if prev_xid is not None and xid != prev_xid:
                    xobj_flag = f" <-- XOBJ {prev_xid}→{xid}"
                prev_xid = xid

                if uc.strip():
                    print(f"      [{ci}] fid={fid} {b} {i} sz={fs:.1f} xid={xid}"
                          f" ({cbox.x:.0f},{cbox.y:.0f}-{cbox.x2:.0f},{cbox.y2:.0f})"
                          f" '{uc}'{xobj_flag}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf_path")
    parser.add_argument("--pages", default=None)
    args = parser.parse_args()

    pdf_path = Path(args.pdf_path)
    if not pdf_path.exists():
        print(f"ERROR: {pdf_path} not found", file=sys.stderr)
        sys.exit(1)

    print(f"Parsing: {pdf_path}  pages={args.pages or 'all'}")

    # Step 1: Parse raw IL
    il = parse_with_legacy_ir(str(pdf_path), pages=args.pages, debug=False)
    print(f"Pages parsed: {len(il.page)}")

    # Step 2: Analyze raw characters (pre-paragraph)
    for page_idx, page in enumerate(il.page):
        pg = page_idx + 1
        font_reg = {f.font_id: f for f in page.pdf_font}
        print(f"\n{'='*60}")
        print(f"PAGE {pg} — RAW CHARS")
        print(f"{'='*60}")
        analyze_page(page, pg, font_reg)

    # Step 3: Run paragraph finder
    print(f"\n{'='*60}")
    print("Running paragraph_finder...")
    run_paragraph_finder(il)

    # Step 4: Check paragraphs
    for page_idx, page in enumerate(il.page):
        pg = page_idx + 1
        paras = page.pdf_paragraph
        print(f"\nPAGE {pg} — PARAGRAPHS ({len(paras)})")

        for pi, para in enumerate(paras):
            comps = para.pdf_paragraph_composition
            if not comps:
                continue
            # Extract text from paragraph
            all_text = []
            fids = set()
            xids = set()
            for comp in comps:
                if comp.pdf_line:
                    for c in comp.pdf_line.pdf_character:
                        all_text.append(c.char_unicode or "")
                        if c.pdf_style:
                            fids.add(c.pdf_style.font_id)
                        if c.xobj_id is not None:
                            xids.add(c.xobj_id)
                elif comp.pdf_character:
                    all_text.append(comp.pdf_character.char_unicode or "")
                    if comp.pdf_character.pdf_style:
                        fids.add(comp.pdf_character.pdf_style.font_id)
                    if comp.pdf_character.xobj_id is not None:
                        xids.add(comp.pdf_character.xobj_id)

            text = "".join(all_text)
            is_interesting = any([
                "LESSON" in text.upper(),
                "ther" in text.lower(),
                len(fids) > 1,
                len(xids) > 1,
            ])

            if is_interesting or pi < 5:
                flags = []
                if len(fids) > 1:
                    flags.append(f"fonts={fids}")
                if len(xids) > 1:
                    flags.append(f"xobjs={xids}")
                print(f"  P{pi}: {len(comps)} comps, {len(all_text)} chars"
                      f"{' | ' + ', '.join(flags) if flags else ''}")
                print(f"    text: {repr(text[:250])}")

    print("\nDone.")


if __name__ == "__main__":
    main()
