"""Repair misplaced red hollow-circle bullets in an emitted dual PDF.

This is an artifact-level fallback for PDFs generated before the IL repair
landed. It uses the source PDF's bullet y-baselines as the authoritative list
map, removes misplaced target glyphs, and paints the marker at the source left
gutter. The source PDF is never modified.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pymupdf


BULLET = ""
RED = (0.819, 0.124, 0.151)


def bullet_boxes(page: pymupdf.Page) -> list[tuple[float, float, float, float]]:
    boxes: list[tuple[float, float, float, float]] = []
    for block in page.get_text("rawdict")["blocks"]:
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                for char in span.get("chars", []):
                    if char.get("c") == BULLET:
                        boxes.append(tuple(float(v) for v in char["bbox"]))
    return boxes


def repair(source: Path, target: Path, output: Path) -> int:
    src = pymupdf.open(source)
    out = pymupdf.open(target)
    if len(out) + 2 > len(src):
        raise ValueError(f"target page range does not fit source: source={len(src)} target={len(out)}")

    moved = 0
    for index, page in enumerate(out):
        source_boxes = bullet_boxes(src[index + 2])
        if not source_boxes:
            continue
        target_boxes = bullet_boxes(page)
        for box in target_boxes:
            x0, y0, x1, y1 = box
            if x0 <= 144:
                continue
            match = min(source_boxes, key=lambda b: abs(b[1] - y0))
            # CJK reflow can move a marker by a few points vertically while
            # preserving the list order; allow that small baseline drift.
            if abs(match[1] - y0) > 12.0:
                continue
            page.add_redact_annot(pymupdf.Rect(*box), fill=(1, 1, 1))
            # The translated body no longer reserves the source marker's
            # 12pt gutter, so place the repaired marker just to its left.
            # This keeps it clear of the first CJK glyph while matching the
            # source's visual marker-to-body spacing.
            cx = (match[0] + match[2]) / 2 - 12.0
            cy = (y0 + y1) / 2
            page.draw_circle((cx, cy), 2.4, color=RED, fill=(1, 1, 1), width=0.8, overlay=True)
            moved += 1
        if page.first_annot:
            page.apply_redactions(images=0, graphics=0, text=0)

    out.save(output, garbage=4, deflate=True)
    src.close()
    out.close()
    return moved


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(repair(args.source, args.target, args.output))


if __name__ == "__main__":
    main()
