#!/usr/bin/env python3
"""Diagnose underline/curve detection and residual character issues."""
import sys
sys.path.insert(0, "/app")

from babeldoc.format.pdf.parse_only import parse_with_legacy_ir
from babeldoc.format.pdf.document_il.midend.paragraph_finder import ParagraphFinder
from babeldoc.format.pdf.document_il.midend.styles_and_formulas import StylesAndFormulas
from babeldoc.format.pdf.parse_shared import _ParseOnlyDocLayoutModel
from babeldoc.format.pdf.translation_config import TranslationConfig
from babeldoc.progress_monitor import ProgressMonitor
from babeldoc.format.pdf.document_il.utils.layout_helper import get_paragraph_bounding_box, get_char_unicode_string

pdf_path = sys.argv[1] if len(sys.argv) > 1 else "/root/.config/pdf2zh/Day_1.pdf"
pages = sys.argv[2] if len(sys.argv) > 2 else "6,20"

config = TranslationConfig(
    translator=None, input_file=pdf_path, lang_in="en", lang_out="zh",
    doc_layout_model=_ParseOnlyDocLayoutModel(),
    progress_monitor=ProgressMonitor([("test", 1.0)]),
    auto_extract_glossary=False, skip_translation=True,
    remove_non_formula_lines=True,
)

il = parse_with_legacy_ir(pdf_path, pages=pages, debug=False)
finder = ParagraphFinder(config)
for page in il.page:
    finder.process_page(page)

for pi, page in enumerate(il.page):
    pg = pi + 1
    print(f"\n{'='*60}")
    print(f"PAGE {pg}")
    print(f"{'='*60}")

    # Curves
    curves = page.pdf_curve
    thin = []
    for c in curves:
        if not c.box:
            continue
        h = c.box.y2 - c.box.y
        w = c.box.x2 - c.box.x
        if h > 0 and h < 3.0 and w > 3.0 and w / h > 3.0:
            thin.append((c, h, w))
    print(f"  Curves: {len(curves)} total, {len(thin)} thin-horizontal")
    for c, h, w in thin[:10]:
        print(f"    y={c.box.y:.1f} h={h:.2f} w={w:.1f}")

    # Paragraphs
    paras = page.pdf_paragraph
    print(f"  Paragraphs: {len(paras)}")
    for pi2, para in enumerate(paras[:10]):
        pbox = get_paragraph_bounding_box(para)
        text = para.unicode[:80] if para.unicode else "(no unicode)"
        comps = para.pdf_paragraph_composition
        print(f"    P{pi2}: box=({pbox.x:.0f},{pbox.y:.0f},{pbox.x2:.0f},{pbox.y2:.0f}) "
              f"comps={len(comps)} text={text!r}")

    # Residual: check for multi-word fragments in paragraphs
    for pi2, para in enumerate(paras):
        text = para.unicode or ""
        # Check if "ther" or similar fragments appear
        if "ther" in text.lower() and len(text) < 100:
            print(f"  *** RESIDUAL P{pi2}: {text[:100]!r}")
