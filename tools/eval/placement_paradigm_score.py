"""Score placement-paradigm guesses on a local English/Chinese page pair.

Reads line boxes and calls ``select_paradigm``. It does not translate and
it does not write a file. Page numbers and book paths stay in the arguments.

Stdout, one line per requested page::

    page paradigm_guess left_mode right_mode short_interior taper

``y`` is converted to the IL axis (up) before the classifier runs.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import fitz
from babeldoc.format.pdf.document_il.utils.layout_intent import LayoutIntentRole
from babeldoc.format.pdf.document_il.utils.placement_paradigm import select_paradigm

_FULL_WIDTH_RATIO = 0.60
_HEADER_Y = 120.0
_FOOTER_MARGIN = 55.0
_DISPLAY_SIZE = 18.0
_COLUMN_OVERLAP = 0.35
_GAP_RATIO = 1.55
_SIZE_SPLIT = 1.5


@dataclass
class Line:
    x0: float
    x1: float
    y: float
    size: float
    text: str


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--en", required=True, type=Path)
    parser.add_argument("--zh", required=True, type=Path)
    parser.add_argument("--pages", required=True, help="1-based pages, comma separated")
    args = parser.parse_args(argv)
    missing = [path for path in (args.en, args.zh) if not path.is_file()]
    if missing:
        for path in missing:
            print(f"missing: {path}", file=sys.stderr)
        return 2
    pages = _parse_pages(args.pages)
    for label, path in (("en", args.en), ("zh", args.zh)):
        print(f"# {label} {path}")
        _print_file(path, pages)
    return 0


def _parse_pages(text: str) -> list[int]:
    pages: list[int] = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        pages.append(int(part))
    return pages


def _print_file(path: Path, pages: list[int]) -> None:
    document = fitz.open(path)
    try:
        for number in pages:
            if number < 1 or number > document.page_count:
                print(f"{number} missing na na 0 0")
                continue
            print(_format_page(number, document[number - 1]))
    finally:
        document.close()


def _format_page(number: int, page) -> str:
    if float(page.rect.width) >= 1000.0:
        return f"{number} spread na na 0 0"
    groups = _groups(page)
    if not groups:
        return f"{number} none na na 0 0"
    chosen = _chosen_group(groups)
    paradigm, _reason, lines = chosen
    left_mode, right_mode = _edge_modes(lines)
    taper = 1 if any(item[0] == "shaped_pocket" for item in groups) else 0
    return (
        f"{number} {paradigm} {left_mode} {right_mode} "
        f"{_short_interior(lines)} {taper}"
    )


def _chosen_group(
    groups: list[tuple[str, str, list[Line]]],
) -> tuple[str, str, list[Line]]:
    shaped = [group for group in groups if group[0] == "shaped_pocket"]
    if shaped:
        return max(shaped, key=lambda group: len(group[2]))
    return max(groups, key=lambda group: len(group[2]))


def _edge_modes(lines: list[Line]) -> tuple[str, str]:
    lefts = [line.x0 for line in lines]
    rights = [line.x1 for line in lines]
    left_mode = "stable" if max(lefts) - min(lefts) <= 8.0 else "step"
    right_mode = "pinned" if max(rights) - min(rights) <= 18.0 else "ragged"
    return left_mode, right_mode


def _short_interior(lines: list[Line]) -> int:
    widths = [line.x1 - line.x0 for line in lines]
    peak = max(widths) if widths else 0.0
    count = 0
    for index, width in enumerate(widths):
        if index == len(widths) - 1:
            continue
        if peak > 0 and width < _FULL_WIDTH_RATIO * peak:
            count += 1
    return count


def _groups(page) -> list[tuple[str, str, list[Line]]]:
    page_h = float(page.rect.height)
    body = _body_lines(extract_lines(page), page_h)
    groups: list[tuple[str, str, list[Line]]] = []
    for column in _columns(body):
        for paragraph in _paragraphs(column):
            boxes = [(line.x0, line.x1, page_h - line.y) for line in paragraph]
            mark = select_paradigm(LayoutIntentRole.BODY, None, boxes)
            groups.append((mark.paradigm.value, mark.reason, paragraph))
    return groups


def extract_lines(page) -> list[Line]:
    raw: list[Line] = []
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block.get("lines") or []:
            spans = line.get("spans") or []
            text = "".join(span.get("text", "") for span in spans).strip()
            if not text or not spans:
                continue
            raw.append(
                Line(
                    x0=min(span["bbox"][0] for span in spans),
                    x1=max(span["bbox"][2] for span in spans),
                    y=min(span["bbox"][1] for span in spans),
                    size=max(float(span.get("size") or 0.0) for span in spans),
                    text=text,
                )
            )
    raw.sort(key=lambda item: (item.y, item.x0))
    return _merge_same_baseline(raw)


def _merge_same_baseline(raw: list[Line]) -> list[Line]:
    merged: list[Line] = []
    for line in raw:
        if merged and abs(line.y - merged[-1].y) < 1.5:
            prev = merged[-1]
            prev.x0 = min(prev.x0, line.x0)
            prev.x1 = max(prev.x1, line.x1)
            prev.size = max(prev.size, line.size)
            prev.text += line.text
            continue
        merged.append(line)
    return merged


def _body_lines(lines: list[Line], page_h: float) -> list[Line]:
    kept: list[Line] = []
    for line in lines:
        if line.y < _HEADER_Y or line.y > page_h - _FOOTER_MARGIN:
            continue
        if line.size >= _DISPLAY_SIZE:
            continue
        lowered = line.text.lower()
        if "www." in lowered or "gabriellemoore.com" in lowered:
            continue
        kept.append(line)
    return kept


def _columns(lines: list[Line]) -> list[list[Line]]:
    columns: list[list[Line]] = []
    for line in sorted(lines, key=lambda item: item.y):
        placed = False
        for column in columns:
            if _overlaps_column(line, column):
                column.append(line)
                placed = True
                break
        if not placed:
            columns.append([line])
    return columns


def _overlaps_column(line: Line, column: list[Line]) -> bool:
    cx0 = min(item.x0 for item in column)
    cx1 = max(item.x1 for item in column)
    overlap = min(line.x1, cx1) - max(line.x0, cx0)
    narrow = max(1.0, min(line.x1 - line.x0, cx1 - cx0))
    return overlap >= _COLUMN_OVERLAP * narrow


def _paragraphs(column: list[Line]) -> list[list[Line]]:
    if not column:
        return []
    ordered = sorted(column, key=lambda item: item.y)
    groups: list[list[Line]] = [[ordered[0]]]
    for index in range(len(ordered) - 1):
        prev, line = ordered[index], ordered[index + 1]
        gap = line.y - prev.y
        split = gap > _GAP_RATIO * max(prev.size, 10.0)
        if split or abs(line.size - prev.size) > _SIZE_SPLIT:
            groups.append([line])
        else:
            groups[-1].append(line)
    return groups


if __name__ == "__main__":
    sys.exit(main())
