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

from babeldoc.format.pdf.parse_only import parse_with_legacy_ir


def analyze_il(il):
    """Analyze the IL document and dump relevant diagnostics."""
    print("=" * 80)
    print(f"PDF ANALYSIS REPORT")
    print(f"Total pages: {len(il.page)}")
    print("=" * 80)

    for page_idx, page in enumerate(il.page):
        page_num = page_idx + 1
        print(f"\n{'='*80}")
        print(f"PAGE {page_num}")
        print(f"{'='*80}")

        # --- Font inventory ---
        print(f"\n--- FONTS ({len(page.pdf_font)}) ---")
        font_registry = {}
        for font in page.pdf_font:
            font_registry[font.font_id] = font
            print(f"  font_id={str(font.font_id):>20s}  bold={str(font.bold):5s}  italic={str(font.italic):5s}  "
                  f"monospace={str(font.monospace):5s}  serif={str(font.serif):5s}  name={font.name}")

        # --- Paragraph analysis ---
        print(f"\n--- PARAGRAPHS ({len(page.pdf_paragraph)}) ---")
        for para_idx, para in enumerate(page.pdf_paragraph):
            comps = para.pdf_paragraph_composition
            if not comps:
                print(f"  Para {para_idx}: EMPTY (no compositions)")
                continue

            # Collect unique font_ids and xobj_ids per paragraph
            font_ids_in_para = set()
            xobj_ids_in_para = set()
            all_chars_unicode = []
            style_changes = []

            prev_font_id = None
            prev_xobj_id = None
            for comp in comps:
                char = comp.pdf_character
                if char is None:
                    continue
                style = char.pdf_style
                fid = style.font_id if style else None
                fs = style.font_size if style else None
                xid = char.xobj_id
                uc = char.char_unicode

                if fid is not None:
                    font_ids_in_para.add(fid)
                if xid is not None:
                    xobj_ids_in_para.add(xid)
                if uc:
                    all_chars_unicode.append(uc)

                # Track style changes
                if fid != prev_font_id or xid != prev_xobj_id:
                    if prev_font_id is not None or prev_xobj_id is not None:
                        style_changes.append({
                            "char_idx": len(all_chars_unicode),
                            "prev_font_id": prev_font_id,
                            "new_font_id": fid,
                            "prev_xobj_id": prev_xobj_id,
                            "new_xobj_id": xid,
                            "prev_font_size": prev_fs,
                            "new_font_size": fs,
                        })
                prev_font_id = fid
                prev_xobj_id = xid
                prev_fs = fs

            text = "".join(all_chars_unicode)
            has_lesson = "LESSON" in text.upper() or "LESS" in text.upper()
            has_ther = "ther" in text.lower()

            # Decide visibility: show all paras with multi-font, multi-xobj, LESSON, or "ther"
            show_detail = (
                len(font_ids_in_para) > 1
                or len(xobj_ids_in_para) > 1
                or has_lesson
                or has_ther
                or len(style_changes) > 0
            )

            # Summary line
            flags = []
            if len(font_ids_in_para) > 1:
                flags.append(f"MULTI-FONT({font_ids_in_para})")
            if len(xobj_ids_in_para) > 1:
                flags.append(f"MULTI-XOBJ({xobj_ids_in_para})")
            if has_lesson:
                flags.append("LESSON")
            if has_ther:
                flags.append("THER")
            if len(style_changes) > 0:
                flags.append(f"STYLE-CHANGES({len(style_changes)})")

            print(f"\n  Para {para_idx}: {len(comps)} comps, {len(all_chars_unicode)} chars, "
                  f"{len(font_ids_in_para)} fonts, {len(xobj_ids_in_para)} xobjs"
                  f"{' | ' + ', '.join(flags) if flags else ''}")
            print(f"    text: {repr(text[:200])}")

            if show_detail:
                # Detailed per-composition dump
                print(f"    --- Detail ({len(comps)} compositions) ---")
                for ci, comp in enumerate(comps):
                    char = comp.pdf_character
                    if char is None:
                        print(f"      comp[{ci}]: char=None")
                        continue
                    style = char.pdf_style
                    fid = style.font_id if style else None
                    fs = style.font_size if style else None
                    xid = char.xobj_id
                    uc = char.char_unicode or ""
                    cbox = char.visual_bbox.box if char.visual_bbox else None
                    box_str = f"box=({cbox.x:.0f},{cbox.y:.0f},{cbox.x2:.0f},{cbox.y2:.0f})" if cbox else "box=None"

                    font_info = font_registry.get(fid)
                    bold_str = f"bold={font_info.bold}" if font_info else "font=?"
                    italic_str = f"italic={font_info.italic}" if font_info else ""

                    print(f"      comp[{ci}]: font_id={fid} {bold_str} {italic_str} "
                          f"size={fs} xobj={xid} {box_str} text={repr(uc)}")

                # Style change summary
                if style_changes:
                    print(f"    --- Style changes ({len(style_changes)}) ---")
                    for sc in style_changes:
                        print(f"      @char[{sc['char_idx']}]: "
                              f"font_id {sc['prev_font_id']}→{sc['new_font_id']} "
                              f"xobj {sc['prev_xobj_id']}→{sc['new_xobj_id']} "
                              f"size {sc['prev_font_size']}→{sc['new_font_size']}")


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

    il = parse_with_legacy_ir(
        str(pdf_path),
        pages=args.pages,
        debug=False,
    )

    analyze_il(il)
    print("\nDone.")


if __name__ == "__main__":
    main()
