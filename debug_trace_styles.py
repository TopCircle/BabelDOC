#!/usr/bin/env python3
"""
End-to-end diagnostic: trace style_spans through the pipeline.

Usage:
    python3 debug_trace_styles.py Day_1.pdf --pages "6"
"""

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))

import pymupdf
from babeldoc.format.pdf.document_il.midend.layout_parser import LayoutParser
from babeldoc.format.pdf.document_il.midend.paragraph_finder import ParagraphFinder
from babeldoc.format.pdf.document_il.midend.styles_and_formulas import StylesAndFormulas
from babeldoc.format.pdf.document_il.utils.layout_helper import is_same_style, is_same_style_except_size
from babeldoc.format.pdf.parse_only import parse_with_legacy_ir
from babeldoc.format.pdf.parse_shared import _ParseOnlyDocLayoutModel
from babeldoc.format.pdf.translation_config import TranslationConfig
from babeldoc.progress_monitor import ProgressMonitor


def make_config():
    return TranslationConfig(
        translator=None,
        input_file="",
        lang_in="",
        lang_out="",
        doc_layout_model=_ParseOnlyDocLayoutModel(),
        progress_monitor=ProgressMonitor([("Test", 1.0)]),
        auto_extract_glossary=False,
        skip_translation=True,
        table_model=None,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf_path")
    parser.add_argument("--pages", default=None)
    args = parser.parse_args()

    pdf_path = Path(args.pdf_path)

    # Step 1: Create IL
    il = parse_with_legacy_ir(args.pdf_path, pages=args.pages, debug=False)
    print(f"Pages in IL: {len(il.page)}")

    # Step 2: Open PDF for layout parsing
    doc_pdf = pymupdf.open(str(pdf_path))

    # Step 3: LayoutParser
    config = make_config()
    layout_parser = LayoutParser(config)
    layout_parser.process(il, doc_pdf)

    # Step 4: ParagraphFinder
    pf = ParagraphFinder(config)
    for page in il.page:
        pf.process_page(page)

    # Step 5: StylesAndFormulas
    saf = StylesAndFormulas(config)
    for page in il.page:
        saf.process_page_styles(page)

    # Step 6: Examine results
    for page_idx, page in enumerate(il.page):
        page_num = int(page.page_number) if page.page_number else (page_idx + 1)
        print(f"\n{'='*80}")
        print(f"PAGE {page_num} (after styles_and_formulas)")
        print(f"Paragraphs: {len(page.pdf_paragraph)}")
        print(f"{'='*80}")

        font_registry = {f.font_id: f for f in page.pdf_font}

        for pi, para in enumerate(page.pdf_paragraph):
            comps = para.pdf_paragraph_composition
            if not comps:
                continue

            same_style_comps = [c for c in comps if c.pdf_same_style_characters]
            if not same_style_comps:
                continue

            # Build full text
            all_text = ""
            for c in same_style_comps:
                for ch in c.pdf_same_style_characters.pdf_character:
                    all_text += ch.char_unicode or ""

            has_lesson = "lesson" in all_text.lower()
            has_bold_font = any(
                c.pdf_same_style_characters.pdf_style
                and c.pdf_same_style_characters.pdf_style.font_id
                and font_registry.get(c.pdf_same_style_characters.pdf_style.font_id)
                and font_registry[c.pdf_same_style_characters.pdf_style.font_id].bold
                for c in same_style_comps
            )

            if not (has_lesson or has_bold_font):
                continue

            base_style = para.pdf_style
            print(f"\n--- Para {pi} ---")
            print(f"  base_style: font_id={base_style.font_id if base_style else 'None'} "
                  f"size={base_style.font_size if base_style else 'None'}")
            print(f"  text: {repr(all_text[:300])}")

            for ci, comp in enumerate(same_style_comps):
                ssc = comp.pdf_same_style_characters
                style = ssc.pdf_style
                fid = style.font_id if style else None
                fs = style.font_size if style else None
                chars_text = "".join(c.char_unicode or "" for c in ssc.pdf_character)
                finfo = font_registry.get(fid)

                same_base = is_same_style(style, base_style)
                same_except_size = is_same_style_except_size(style, base_style)
                would_span = not (same_base or same_except_size)

                print(f"  comp[{ci}]: fid={fid} bold={finfo.bold if finfo else '?'} "
                      f"sz={fs:.1f} same_base={same_base} same_except={same_except_size} "
                      f"-> SPAN={'YES' if would_span else 'no'} "
                      f"text={repr(chars_text[:100])}")

    doc_pdf.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
