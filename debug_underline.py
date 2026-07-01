#!/usr/bin/env python3
"""Diagnose underline source in PDF.
Runs in Docker container: python3 /app/BabelDOC/debug_underline.py
"""
import sys
sys.path.insert(0, "/app")

# Step 1: Check raw PDF curves
from babeldoc.format.pdf.parse_only import parse_with_legacy_ir

pdf_path = sys.argv[1] if len(sys.argv) > 1 else "/root/.config/pdf2zh/Day_1.pdf"
pages = sys.argv[2] if len(sys.argv) > 2 else "6,20"

il = parse_with_legacy_ir(pdf_path, pages=pages, debug=False)

for pi, page in enumerate(il.page):
    pg = pi + 1
    print(f"\n{'='*60}")
    print(f"PAGE {pg} — RAW CURVES")
    print(f"{'='*60}")

    curves = page.pdf_curve
    print(f"  Total curves: {len(curves)}")

    for ci, c in enumerate(curves):
        if not c.box:
            continue
        h = c.box.y2 - c.box.y
        w = c.box.x2 - c.box.x
        ratio = w / h if h > 0 else float('inf')
        thin = "THIN" if (h > 0 and h < 3.0 and w > 3.0 and ratio > 3.0) else ""
        print(f"  C{ci}: y={c.box.y:.1f} h={h:.2f} w={w:.1f} ratio={ratio:.1f} {thin}")

    # Step 2: Check for annotations
    print(f"\n  RAW CHARS: {len(page.pdf_character)}")
    # Group chars by visual line for "ther" detection
    lines = {}
    for c in page.pdf_character:
        if not c.visual_bbox:
            continue
        y = round(c.visual_bbox.box.y / 5) * 5  # round to nearest 5pt
        if y not in lines:
            lines[y] = []
        lines[y].append(c)

    for y in sorted(lines.keys())[:5]:
        chars = sorted(lines[y], key=lambda c: c.visual_bbox.box.x)
        text = "".join(c.char_unicode or "" for c in chars)
        if len(text) > 3:
            print(f"  y={y}: {text[:80]!r}")

# Step 3: Try pymupdf for annotations
print(f"\n{'='*60}")
print("PYMUPDF ANNOTATIONS CHECK")
print(f"{'='*60}")
try:
    import pymupdf
    doc = pymupdf.open(pdf_path)
    for pi in range(min(2, len(doc))):
        page = doc[pi]
        annots = list(page.annots()) if page.annots() else []
        print(f"  Page {pi+1}: {len(annots)} annotations")
        for a in annots[:5]:
            print(f"    type={a.type} rect={a.rect}")
except Exception as e:
    print(f"  pymupdf check failed: {e}")

# Step 4: Check text rendering mode
print(f"\n{'='*60}")
print("TEXT RENDERING MODE CHECK")
print(f"{'='*60}")
try:
    import pymupdf
    doc = pymupdf.open(pdf_path)
    for pi in range(min(2, len(doc))):
        page = doc[pi]
        blocks = page.get_text("dict")["blocks"]
        underline_count = 0
        for block in blocks:
            if "lines" not in block:
                continue
            for line in block["lines"]:
                for span in line["spans"]:
                    flags = span.get("flags", 0)
                    # flags: bit 1 = italic, bit 4 = monospace, etc.
                    # Check for underline flag (pymupdf: flags & 4 = superscript, not underline)
                    # pymupdf doesn't directly expose underline in flags
                    # But we can check the span text for "underline" patterns
                    if flags & 0x04:  # superscript
                        pass
        print(f"  Page {pi+1}: checked {sum(1 for b in blocks if 'lines' in b)} text blocks")
except Exception as e:
    print(f"  pymupdf text check failed: {e}")

print("\nDone.")
