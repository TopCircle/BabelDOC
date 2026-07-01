#!/usr/bin/env python3
"""Diagnose decorative text detection — find spaced-out text like 'G e n t l y'."""
import sys
sys.path.insert(0, "/app")

from babeldoc.format.pdf.parse_only import parse_with_legacy_ir

pdf_path = sys.argv[1] if len(sys.argv) > 1 else "/root/.config/pdf2zh/Day_1.pdf"
pages = sys.argv[2] if len(sys.argv) > 2 else "6,20"

il = parse_with_legacy_ir(pdf_path, pages=pages, debug=False)

for pi, page in enumerate(il.page):
    pg = pi + 1
    chars = page.pdf_character
    if not chars:
        continue

    # Group by visual line
    lines = {}
    for c in chars:
        if not c.visual_bbox:
            continue
        y = round(c.visual_bbox.box.y / 3) * 3
        if y not in lines:
            lines[y] = []
        lines[y].append(c)

    print(f"\nPAGE {pg} — checking {len(chars)} chars, {len(lines)} lines")
    for y in sorted(lines.keys()):
        line_chars = sorted(lines[y], key=lambda c: c.visual_bbox.box.x)
        if len(line_chars) < 3:
            continue

        # Calculate spacing ratios
        gaps = []
        widths = []
        for i in range(len(line_chars) - 1):
            c1 = line_chars[i]
            c2 = line_chars[i + 1]
            w1 = c1.visual_bbox.box.x2 - c1.visual_bbox.box.x
            gap = c2.visual_bbox.box.x - c1.visual_bbox.box.x2
            widths.append(w1)
            gaps.append(gap)

        if not widths:
            continue

        avg_w = sum(widths) / len(widths)
        avg_gap = sum(gaps) / len(gaps)

        # Decorative: gap >> char_width (letters spaced out)
        if avg_w > 0 and avg_gap > avg_w * 1.5:
            text = "".join(c.char_unicode or "" for c in line_chars)
            ratio = avg_gap / avg_w
            print(f"  DECORATIVE y={y}: gap_ratio={ratio:.1f} avg_w={avg_w:.1f} "
                  f"avg_gap={avg_gap:.1f} text={text[:60]!r}")

            # Show individual gaps
            gap_detail = [f"{g:.1f}" for g in gaps[:15]]
            print(f"    gaps: {', '.join(gap_detail)}")
