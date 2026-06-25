#!/usr/bin/env python3
"""
Diagnostic script: analyze a PDF through BabelDOC's IL pipeline.
Dumps font, paragraph, xobj, and style data for debugging.

Usage:
    python3 debug_analyze_pdf.py /path/to/input.pdf [--pages "1,6,20"]
"""

import argparse
import sys
from pathlib import Path

# Add local repo to path so we use our patched code
REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))

from babeldoc.format.pdf.document_il import il_version_1
from babeldoc.format.pdf.parse_only import parse_with_legacy_ir
from babeldoc.format.pdf.parse_shared import _ParseOnlyDocLayoutModel
from babeldoc.format.pdf.translation_config import TranslationConfig
from babeldoc.progress_monitor import ProgressMonitor


def run_paragraph_finder(il):
    """Run paragraph_finder on the IL to populate pdf_paragraph."""
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


def analyze_raw_characters(page, page_num, font_registry):
    """Dump raw pdf_character data before paragraph finding."""
    chars = page.pdf_character
    if not chars:
        print(f"\n  (no raw characters on this page)")
        return

    print(f"\n--- RAW CHARACTERS ({len(chars)}) ---")

    # Group characters by visual line (same y-range)
    # First, show overall stats
    font_ids = {}
    xobj_ids = {}
    for c in chars:
        fid = c.pdf_style.font_id if c.pdf_style else None
        xid = c.xobj_id
        font_ids[fid] = font_ids.get(fid, 0) + 1
        xobj_ids[xid] = xobj_ids.get(xid, 0) + 1

    print(f"  Font distribution: {font_ids}")
    print(f"  XObj distribution: {xobj_ids}")

    # Group chars by approximate visual line (similar y)
    LINE_Y_TOLERANCE = 5  # pts
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

    # Sort lines by y
    lines.sort(key=lambda l: l["y"])

    print(f"  Visual lines: {len(lines)} (tolerance={LINE_Y_TOLERANCE}pt)")
    print()

    for li, line in enumerate(lines):
        lchars = sorted(line["chars"], key=lambda c: c.visual_bbox.box.x if c.visual_bbox else 0)
        text = "".join(c.char_unicode or "" for c in lchars)
        fids_in_line = set()
        xids_in_line = set()
        for c in lchars:
            if c.pdf_style and c.pdf_style.font_id:
                fids_in_line.add(c.pdf_style.font_id)
            if c.xobj_id is not None:
                xids_in_line.add(c.xobj_id)

        show = ("LESSON" in text.upper() or "ther" in text.lower()
                or len(fids_in_line) > 1 or len(xids_in_line) > 1
                or "TT" in str(fids_in_line) or "T1_3" in str(fids_in_line))

        flags = []
        if len(fids_in_line) > 1:
            flags.append(f"MULTI-FONT({fids_in_line})")
        if len(xids_in_line) > 1:
            flags.append(f"MULTI-XOBJ({xids_in_line})")
        if "LESSON" in text.upper():
            flags.append("LESSON")

        print(f"  L{li}: y={line['y']:.0f} {len(lchars)} chars {len(fids_in_line)} fonts "
              f"{len(xids_in_line)} xobjs{(' | ' + ', '.join(flags)) if flags else ''}")
        print(f"    text: {repr(text[:250])}")

        if show:
            for ci, c in enumerate(lchars):
                style = c.pdf_style
                fid = style.font_id if style else None
                fs = style.font_size if style else None
                xid = c.xobj_id
                uc = c.char_unicode or ""
                cbox = c.visual_bbox.box if c.visual_bbox else None
                box_str = f"({cbox.x:.0f},{cbox.y:.0f},{cbox.x2:.0f},{cbox.y2:.0f})" if cbox else "?"
                finfo = font_registry.get(fid)
                b = f"b={finfo.bold}" if finfo else "?"
                it = f"i={finfo.italic}" if finfo else ""
                print(f"      [{ci}] fid={fid} {b} {it} sz={fs} xid={xid} {box_str} {repr(uc)}")
            print()


def analyze_paragraphs(il):
    """Analyze paragraphs after paragraph_finder has run."""
    for page_idx, page in enumerate(il.page):
        page_num = page_idx + 1

        # Build font registry for this page
        font_registry = {f.font_id: f for f in page.pdf_font}

        print(f"\n{'='*80}")
        print(f"PAGE {page_num} — PARAGRAPHS ({len(page.pdf_paragraph)})")
        print(f"{'='*80}")

        for para_idx, para in enumerate(page.pdf_paragraph):
            comps = para.pdf_paragraph_composition
            if not comps:
                continue

            all_text = []
            font_ids_in_para = set()
            xobj_ids_in_para = set()
            style_changes = []
            prev_fid = None
            prev_xid = None
            prev_fs = None

            for comp in comps:
                line = comp.pdf_line
                if not line:
                    continue
                for char in line.pdf_character:
                    style = char.pdf_style
                    fid = style.font_id if style else None
                    fs = style.font_size if style else None
                    xid = char.xobj_id
                    uc = char.char_unicode or ""

                    if fid:
                        font_ids_in_para.add(fid)
                    if xid is not None:
                        xobj_ids_in_para.add(xid)
                    all_text.append(uc)

                    if fid != prev_fid or xid != prev_xid:
                        if prev_fid is not None:
                            style_changes.append({
                                "at_char": len(all_text),
                                "prev_fid": prev_fid,
                                "new_fid": fid,
                                "prev_xid": prev_xid,
                                "new_xid": xid,
                                "prev_fs": prev_fs,
                                "new_fs": fs,
                            })
                    prev_fid = fid
                    prev_xid = xid
                    prev_fs = fs

            text = "".join(all_text)
            has_lesson = "LESSON" in text.upper()
            has_ther = "ther" in text.lower()
            multi_font = len(font_ids_in_para) > 1
            multi_xobj = len(xobj_ids_in_para) > 1

            if not (has_lesson or has_ther or multi_font or multi_xobj or style_changes):
                continue  # skip unremarkable paragraphs

            flags = []
            if multi_font:
                flags.append(f"MULTI-FONT({font_ids_in_para})")
            if multi_xobj:
                flags.append(f"MULTI-XOBJ({xobj_ids_in_para})")
            if has_lesson:
                flags.append("LESSON")
            if has_ther:
                flags.append("THER")
            if style_changes:
                flags.append(f"STYLE-CHANGES({len(style_changes)})")

            print(f"\n  Para {para_idx}: {len(comps)} comps, {len(all_text)} chars, "
                  f"{len(font_ids_in_para)} fonts, {len(xobj_ids_in_para)} xobjs"
                  f"{' | ' + ', '.join(flags) if flags else ''}")
            print(f"    text: {repr(text[:300])}")

            # Detail
            for ci, comp in enumerate(comps):
                line = comp.pdf_line
                if not line:
                    continue
                for chi, char in enumerate(line.pdf_character):
                    style = char.pdf_style
                    fid = style.font_id if style else None
                    fs = style.font_size if style else None
                    xid = char.xobj_id
                    uc = char.char_unicode or ""
                    cbox = char.visual_bbox.box if char.visual_bbox else None
                    box_str = f"({cbox.x:.0f},{cbox.y:.0f},{cbox.x2:.0f},{cbox.y2:.0f})" if cbox else "?"
                    finfo = font_registry.get(fid)
                    b = f"b={finfo.bold}" if finfo else "?"
                    it = f"i={finfo.italic}" if finfo else ""
                    print(f"      comp[{ci}][{chi}] fid={fid} {b} {it} sz={fs} "
                          f"xid={xid} {box_str} {repr(uc)}")

            if style_changes:
                print(f"    --- Style changes ({len(style_changes)}) ---")
                for sc in style_changes:
                    print(f"      @char[{sc['at_char']}]: "
                          f"fid {sc['prev_fid']}→{sc['new_fid']} "
                          f"xid {sc['prev_xid']}→{sc['new_xid']} "
                          f"sz {sc['prev_fs']}→{sc['new_fs']}")


def main():
    parser = argparse.ArgumentParser(description="Diagnose BabelDOC PDF processing")
    parser.add_argument("pdf_path", help="Path to the PDF file")
    parser.add_argument("--pages", help="Page range to parse (e.g. '1,6,20')", default=None)
    args = parser.parse_args()

    pdf_path = Path(args.pdf_path)
    if not pdf_path.exists():
        print(f"ERROR: File not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Parsing: {pdf_path}")
    print(f"Pages filter: {args.pages or 'all'}")
    print()

    # Step 1: Create raw IL
    il = parse_with_legacy_ir(str(pdf_path), pages=args.pages, debug=False)

    print("=" * 80)
    print(f"PDF ANALYSIS REPORT")
    print(f"Total pages: {len(il.page)}")
    print("=" * 80)

    for page_idx, page in enumerate(il.page):
        page_num = page_idx + 1
        print(f"\n{'='*80}")
        print(f"PAGE {page_num}")
        print(f"{'='*80}")

        # Font inventory
        print(f"\n--- FONTS ({len(page.pdf_font)}) ---")
        font_registry = {}
        for font in page.pdf_font:
            font_registry[font.font_id] = font
            # Flag fonts whose name contains bold keywords but bold=False
            name_lower = (font.name or "").lower()
            if "+" in name_lower:
                name_lower = name_lower.split("+", 1)[1]
            kw_match = [kw for kw in ("bold", "heavy", "black", "semibold", "extrabold", "medium")
                        if kw in name_lower]
            mismatch = " *** NAME_HAS_BOLD_KW_BUT_bold=False ***" if (kw_match and not font.bold) else ""
            print(f"  fid={str(font.font_id):>20s}  bold={str(font.bold):5s}  italic={str(font.italic):5s}  "
                  f"monospace={str(font.monospace):5s}  serif={str(font.serif):5s}  name={font.name}{mismatch}")

        # Analyze raw characters (before paragraph finding)
        analyze_raw_characters(page, page_num, font_registry)

    # Step 2: Run paragraph finder
    print(f"\n{'='*80}")
    print("Running paragraph_finder...")
    print(f"{'='*80}")
    run_paragraph_finder(il)

    # Step 3: Analyze paragraphs
    analyze_paragraphs(il)

    print("\nDone.")


if __name__ == "__main__":
    main()
