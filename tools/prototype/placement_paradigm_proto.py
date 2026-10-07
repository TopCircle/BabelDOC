"""Placement-paradigm prototype.

Reads PDF line boxes, groups them into paragraph-like blocks, and labels
each block. Nothing here is imported by Typesetting. Page numbers and
file paths live only in the case table at the bottom.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

KEEP_ROLES = frozenset(
    {
        "chrome",
        "title",
        "pull_quote",
        "callout",
        "list",
        "section_header",
        "figure_caption",
        "dropcap",
        "formula",
    }
)


@dataclass(slots=True)
class Mark:
    paradigm: str
    confidence: float
    reason: str


def select_paradigm(
    role: str,
    wrap_mode: str | None,
    line_boxes: list[tuple[float, float, float]],
) -> Mark:
    """Match the Task 1 contract. ``line_boxes`` are ``(x0, x1, y0)``."""
    if role in KEEP_ROLES:
        return Mark("keep_current", 0.9, "keep_role")
    if not line_boxes:
        return Mark("rect_reflow", 0.4, "no_lines")

    widths = [x1 - x0 for x0, x1, _y in line_boxes]
    peak = max(widths)
    full = [
        (x0, x1, y)
        for (x0, x1, y), width in zip(line_boxes, widths, strict=True)
        if peak > 0 and width >= 0.60 * peak
    ]
    full.sort(key=lambda box: box[2])
    lefts = [box[0] for box in full]
    rights = [box[1] for box in full]
    left_range = (max(lefts) - min(lefts)) if lefts else 0.0
    right_range = (max(rights) - min(rights)) if rights else 0.0
    distinct = len({round(x / 6.0) for x in lefts})
    deltas = [lefts[i + 1] - lefts[i] for i in range(len(lefts) - 1)]
    if deltas:
        bad = sum(1 for delta in deltas if delta < -6.0)
        monotone = 1.0 - bad / len(deltas)
    else:
        monotone = 1.0
    pinned = right_range <= 18.0 and monotone >= 0.7
    taper = len(full) >= 4 and pinned and left_range >= 24.0 and distinct >= 4
    too_short = 0 < len(full) < 4 and pinned and left_range >= 24.0
    stable = bool(lefts) and left_range <= 8.0

    if taper:
        return Mark("shaped_pocket", 0.9, "taper")
    if wrap_mode in {"left_fixed", "right_fixed"}:
        return Mark("rect_reflow", 0.85, "shape_not_taper")
    if too_short:
        return Mark("rect_reflow", 0.8, "taper_too_short")
    if stable:
        return Mark("rect_reflow", 0.9, "stable_column")
    return Mark("rect_reflow", 0.8, "not_taper")


def _assert_synthetic() -> None:
    stable = [(102.0, 570.0, 100.0 + 15.0 * i) for i in range(5)]
    mark = select_paradigm("body", None, stable)
    assert mark.paradigm == "rect_reflow" and mark.reason == "stable_column"
    assert mark.confidence >= 0.8

    taper = [(100.0 + 12.0 * i, 570.0, 100.0 + 15.0 * i) for i in range(4)]
    mark = select_paradigm("body", None, taper)
    assert mark.paradigm == "shaped_pocket" and mark.reason == "taper"

    short = [(100.0 + 12.0 * i, 570.0, 100.0 + 15.0 * i) for i in range(3)]
    mark = select_paradigm("body", None, short)
    assert mark.paradigm == "rect_reflow" and mark.reason == "taper_too_short"

    hanging: list[tuple[float, float, float]] = []
    y = 100.0
    for _ in range(3):
        hanging.append((56.0, 540.0, y))
        y += 16
        hanging.append((92.0, 540.0, y))
        y += 16
        hanging.append((74.0, 220.0, y))
        y += 16
        hanging.append((92.0, 540.0, y))
        y += 20
    mark = select_paradigm("body", None, hanging)
    assert mark.paradigm == "rect_reflow" and mark.reason == "not_taper", mark

    for role in ("pull_quote", "list", "chrome", "title"):
        mark = select_paradigm(role, None, taper)
        assert mark.paradigm == "keep_current" and mark.reason == "keep_role"

    mark = select_paradigm("body", "right_fixed", stable)
    assert mark.paradigm == "rect_reflow" and mark.reason == "shape_not_taper"
    mark = select_paradigm("body", "left_fixed", taper)
    assert mark.paradigm == "shaped_pocket" and mark.reason == "taper"
    mark = select_paradigm("body", None, [])
    assert mark.paradigm == "rect_reflow" and mark.confidence == 0.4
    assert mark.reason == "no_lines"


@dataclass
class Line:
    x0: float
    x1: float
    y: float
    size: float
    text: str


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
                    size=max(float(span.get("size") or 0) for span in spans),
                    text=text,
                )
            )
    raw.sort(key=lambda item: (item.y, item.x0))
    merged: list[Line] = []
    for line in raw:
        if merged and abs(line.y - merged[-1].y) < 1.5:
            prev = merged[-1]
            prev_w = prev.x1 - prev.x0
            line_w = line.x1 - line.x0
            if line_w < 8.0 and prev_w >= 8.0:
                continue
            if prev_w < 8.0 and line_w >= 8.0:
                merged[-1] = line
                continue
            prev.x0 = min(prev.x0, line.x0)
            prev.x1 = max(prev.x1, line.x1)
            prev.size = max(prev.size, line.size)
            prev.text += line.text
            continue
        merged.append(line)
    return merged


def page_gate(page, lines: list[Line]) -> tuple[str | None, float | None]:
    """Input gates. Linguistic checks stay out of ``select_paradigm``."""
    if float(page.rect.width) >= 1000.0:
        return "spread", None
    chars = [char for line in lines for char in line.text if not char.isspace()]
    if len(chars) < 40:
        return "image_only", None
    ascii_letters = [char for char in chars if char.isascii() and char.isalpha()]
    cjk = sum("\u4e00" <= char <= "\u9fff" for char in chars)
    linguistic = (len(ascii_letters) + cjk) / len(chars)
    if linguistic < 0.45:
        return "encoding", linguistic
    # Custom encodings often emit ASCII letters with almost no vowels.
    # Real English sits near 0.4; CJK pages have too few ASCII letters to score.
    if len(ascii_letters) >= 0.40 * len(chars):
        vowels = sum(char.lower() in "aeiou" for char in ascii_letters)
        if vowels / len(ascii_letters) < 0.20:
            return "encoding", linguistic
    return None, linguistic


def _body_lines(lines: list[Line], page_h: float) -> list[Line]:
    kept: list[Line] = []
    for line in lines:
        if line.y < 120.0 or line.y > page_h - 55.0:
            continue
        if line.size >= 18.0:
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
            cx0 = min(item.x0 for item in column)
            cx1 = max(item.x1 for item in column)
            overlap = min(line.x1, cx1) - max(line.x0, cx0)
            narrow = max(1.0, min(line.x1 - line.x0, cx1 - cx0))
            if overlap >= 0.35 * narrow:
                column.append(line)
                placed = True
                break
        if not placed:
            columns.append([line])
    return columns


def _paragraphs(column: list[Line]) -> list[list[Line]]:
    ordered = sorted(column, key=lambda item: item.y)
    groups: list[list[Line]] = [[ordered[0]]]
    for index in range(len(ordered) - 1):
        prev, line = ordered[index], ordered[index + 1]
        gap = line.y - prev.y
        if gap > 1.55 * max(prev.size, 10.0) or abs(line.size - prev.size) > 1.5:
            groups.append([line])
        else:
            groups[-1].append(line)
    return groups


@dataclass
class GroupMark:
    paradigm: str
    reason: str
    n: int
    left: float
    right: float
    y: float


def classify_page(page) -> dict:
    lines = extract_lines(page)
    gate, mean_ratio = page_gate(page, lines)
    result: dict = {
        "width": round(float(page.rect.width), 1),
        "height": round(float(page.rect.height), 1),
        "gate": gate,
        "letter_ratio": None if mean_ratio is None else round(mean_ratio, 3),
        "groups": [],
    }
    if gate:
        return result
    body = _body_lines(lines, float(page.rect.height))
    if not body:
        result["gate"] = "image_only"
        return result
    groups: list[GroupMark] = []
    for column in _columns(body):
        for paragraph in _paragraphs(column):
            boxes = [(line.x0, line.x1, line.y) for line in paragraph]
            mark = select_paradigm("body", None, boxes)
            groups.append(
                GroupMark(
                    paradigm=mark.paradigm,
                    reason=mark.reason,
                    n=len(paragraph),
                    left=round(min(line.x0 for line in paragraph), 1),
                    right=round(max(line.x1 for line in paragraph), 1),
                    y=round(paragraph[0].y, 1),
                )
            )
    result["groups"] = [
        {
            "paradigm": group.paradigm,
            "reason": group.reason,
            "n": group.n,
            "left": group.left,
            "right": group.right,
            "y": group.y,
        }
        for group in groups
    ]
    return result


def _check(kind: str, result: dict) -> str | None:
    if kind in {"spread", "image_only", "encoding"}:
        if result["gate"] != kind:
            return f"gate {result['gate']} != {kind}"
        return None
    if result["gate"]:
        return f"unexpected gate {result['gate']}"
    groups = result["groups"]
    shaped = [group for group in groups if group["paradigm"] == "shaped_pocket"]
    rects = [group for group in groups if group["paradigm"] == "rect_reflow"]
    if kind == "shaped_and_rect":
        if not shaped or not rects:
            return f"shaped={len(shaped)} rect={len(rects)}"
        return None
    if kind == "no_shaped":
        if shaped or not rects:
            return f"shaped={len(shaped)} rect={len(rects)}"
        return None
    if kind == "quote_split":
        lefts = [group["left"] for group in groups]
        if shaped or not lefts or min(lefts) >= 80 or max(lefts) <= 180:
            return f"shaped={len(shaped)} lefts={lefts}"
        return None
    if kind == "stepped_rects":
        lefts = [group["left"] for group in groups]
        if shaped or not lefts or max(lefts) - min(lefts) < 40:
            return f"shaped={len(shaped)} left-span={max(lefts) - min(lefts) if lefts else 0}"
        return None
    return f"unknown check {kind}"


CASES = [
    ("oa-en-19", "Orgasmic Addiction/Orgasmic Addiction.pdf", 19, "shaped_and_rect"),
    ("oa-en-23", "Orgasmic Addiction/Orgasmic Addiction.pdf", 23, "quote_split"),
    ("oa-en-44", "Orgasmic Addiction/Orgasmic Addiction.pdf", 44, "no_shaped"),
    (
        "oa-zh-19",
        "Orgasmic Addiction/Orgasmic Addiction.no_watermark.zh-CN.mono.pdf",
        19,
        "shaped_and_rect",
    ),
    (
        "oa-zh-44",
        "Orgasmic Addiction/Orgasmic Addiction.no_watermark.zh-CN.mono.pdf",
        44,
        "no_shaped",
    ),
    ("vm-6", "Vagina Masterclass/Vagina Masterclass.pdf", 6, "no_shaped"),
    ("vm-8", "Vagina Masterclass/Vagina Masterclass.pdf", 8, "stepped_rects"),
    ("tied-8", "All Tied Up/All Tied Up.pdf", 8, "no_shaped"),
    ("open-8", "Open Her Up/Open Her Up.pdf", 8, "no_shaped"),
    ("flirt-8", "Flirting Fingers/Flirting Fingers.pdf", 8, "no_shaped"),
    ("gspot-8", "G-Spot Ecstasy/eBook.pdf", 8, "no_shaped"),
    ("trigasm-6", "The Perfect Trigasm/The Perfect Trigasm.pdf", 6, "spread"),
    ("boob-6", "Boobgasms/Boobgasms.pdf", 6, "image_only"),
    ("fruit-6", "Forbidden Fruit/Forbidden Fruit.pdf", 6, "encoding"),
    ("turn-6", "Turn Her On Faster/Turn Her On Faster.pdf", 6, "encoding"),
]


def _draw(page, result: dict, dest: Path) -> None:
    if result["gate"]:
        return
    colors = {
        "rect_reflow": (0.1, 0.35, 0.85),
        "shaped_pocket": (0.9, 0.4, 0.05),
        "keep_current": (0.4, 0.4, 0.4),
    }
    shape = page.new_shape()
    for group in result["groups"]:
        # y is the first baseline; draw a thin marker, not a filled column.
        y = group["y"]
        rect = (group["left"], y - 2, group["right"], y + 10)
        shape.draw_rect(rect)
        shape.finish(
            color=colors.get(group["paradigm"], (0, 0, 0)),
            width=0.6,
            fill=colors.get(group["paradigm"], (0, 0, 0)),
            fill_opacity=0.18,
        )
    shape.commit()
    pix = page.get_pixmap(matrix=__import__("fitz").Matrix(1.3, 1.3), alpha=False)
    dest.parent.mkdir(parents=True, exist_ok=True)
    pix.save(dest)


def run(root: Path, out_dir: Path) -> int:
    import fitz

    _assert_synthetic()
    summary = []
    failed = 0
    for name, rel, page_no, kind in CASES:
        path = root / rel
        if not path.is_file():
            summary.append({"name": name, "error": "missing", "path": str(path)})
            failed += 1
            continue
        doc = fitz.open(path)
        page = doc[page_no - 1]
        result = classify_page(page)
        problem = _check(kind, result)
        if problem:
            failed += 1
        row = {
            "name": name,
            "page": page_no,
            "expect": kind,
            "problem": problem,
            **result,
        }
        summary.append(row)
        _draw(page, result, out_dir / f"{name}.png")
        doc.close()
        flag = "FAIL" if problem else "ok"
        print(
            f"{flag:4} {name:12} gate={result['gate']} ratio={result['letter_ratio']} {problem or ''}"
        )
        for group in result["groups"]:
            print(
                f"      {group['paradigm']:14} {group['reason']:16} n={group['n']:2} "
                f"x={group['left']:6.1f}..{group['right']:6.1f} y={group['y']:6.1f}"
            )
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2)
    )
    print(f"failed {failed} / {len(CASES)}")
    return 1 if failed else 0


def main() -> int:
    root = Path(
        "/Users/yun/Library/CloudStorage/OneDrive-Personal/Documentos/Books/Gabrielle Moore"
    )
    out = Path("tmp/paradigm-proto")
    if len(sys.argv) >= 2:
        root = Path(sys.argv[1])
    if len(sys.argv) >= 3:
        out = Path(sys.argv[2])
    return run(root, out)


if __name__ == "__main__":
    sys.exit(main())
