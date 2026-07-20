"""Dual PDF text-layer layout metrics (S1.1 / I2-quality).

Read an existing dual (or mono) PDF and score the ZH half without running
translation. Shared span helpers are the **single** implementation used by
``figure_baseline_probe`` for half selection, crush ratio, and left-col gap.

Hard failures (profile ``default``): crush, extreme min font, SOH.
Soft warnings: max_left_col_gap (same algorithm as the figure probe).
"""

from __future__ import annotations

import json
import statistics
from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path

# Letter mono width; dual side-by-side is typically 2× this.
DEFAULT_HALF_WIDTH = 612.0

# Shared with figure_baseline_probe (do not re-tune without Phase 0 review).
DEFAULT_SMALL_PT = 7.0
DEFAULT_CRUSH_RATIO_MAX = 0.10
DEFAULT_MAX_LEFT_COL_GAP = 120.0
DEFAULT_MIN_FONT_HARD = 5.0
DEFAULT_MIN_CHARS_FOR_FONT_GATES = 20

# Left-col gap body band — must match figure_baseline_probe historical filters.
_BODY_SIZE_MIN = 7.5
_BODY_SIZE_MAX = 12.5
_BODY_X_FRAC = 0.55
_GAP_CAP = 400.0

_CONTROL_OK = frozenset("\t\n\r")


# ---------------------------------------------------------------------------
# Shared text-layer helpers (canonical implementation)
# ---------------------------------------------------------------------------


def collect_spans(
    page, x_min: float, x_max: float
) -> list[tuple[float, tuple, str]]:
    """Return (size, bbox, text) for spans whose center x is in [x_min, x_max)."""
    spans: list[tuple[float, tuple, str]] = []
    for block in page.get_text("dict").get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for sp in line.get("spans", []):
                bb = sp.get("bbox")
                if not bb or len(bb) < 4:
                    continue
                cx = (bb[0] + bb[2]) / 2.0
                if x_min <= cx < x_max:
                    spans.append(
                        (float(sp.get("size") or 0.0), tuple(bb), sp.get("text") or "")
                    )
    return spans


def cjk_char_count(spans: list[tuple[float, tuple, str]]) -> int:
    n = 0
    for _, _, t in spans:
        for c in t:
            if "\u4e00" <= c <= "\u9fff":
                n += 1
    return n


def latin_char_count(spans: list[tuple[float, tuple, str]]) -> int:
    n = 0
    for _, _, t in spans:
        for c in t:
            if ("A" <= c <= "Z") or ("a" <= c <= "z"):
                n += 1
    return n


def choose_half(
    page,
    half: str,
    half_width: float = DEFAULT_HALF_WIDTH,
) -> tuple[str, float, float, list[tuple[float, tuple, str]]]:
    """Return (half_name, origin_x, width, spans)."""
    w = float(page.rect.width)
    h = float(page.rect.height)
    is_dual_wide = w >= half_width * 1.8 or (w > h * 1.3 and w >= half_width * 1.5)

    if half == "full" or not is_dual_wide:
        spans = collect_spans(page, 0.0, w)
        return "full", 0.0, w, spans

    mid = w / 2.0
    left = collect_spans(page, 0.0, mid)
    right = collect_spans(page, mid, w)

    if half == "left":
        return "left", 0.0, mid, left
    if half == "right":
        return "right", mid, w - mid, right

    # auto: prefer the half with more CJK (ZH side of dual)
    if cjk_char_count(right) > cjk_char_count(left):
        return "right", mid, w - mid, right
    return "left", 0.0, mid, left


def crush_ratio(sizes: list[float], small_pt: float = DEFAULT_SMALL_PT) -> float:
    """Fraction of non-space glyph sizes strictly below *small_pt*."""
    if not sizes:
        return 0.0
    small = sum(1 for s in sizes if s < small_pt)
    return small / len(sizes)


def max_left_col_gap(
    boxes: list[tuple[float, float, float, float, str, float]],
    half_width: float,
) -> float:
    """Max vertical gap between consecutive left-column body spans.

    Filters match figure_baseline_probe (body size band + left x band + gap cap).
    *boxes*: (rx0, y0, rx1, y1, text, size) in half-local x.
    """
    body = [
        b
        for b in boxes
        if _BODY_SIZE_MIN <= b[5] <= _BODY_SIZE_MAX and b[0] < half_width * _BODY_X_FRAC
    ]
    body_sorted = sorted(body, key=lambda b: (b[1], b[0]))
    max_gap = 0.0
    for a, b in zip(body_sorted, body_sorted[1:]):
        gap = b[1] - a[3]
        if 0 < gap < _GAP_CAP:
            max_gap = max(max_gap, gap)
    return max_gap


def soh_hits_in_spans(spans: list[tuple[float, tuple, str]]) -> int:
    n = 0
    for _, _, t in spans:
        for c in t:
            o = ord(c)
            if o < 32 and c not in _CONTROL_OK:
                n += 1
    return n


def spans_to_boxes(
    spans: list[tuple[float, tuple, str]],
    half_origin_x: float,
) -> tuple[list[float], list[tuple[float, float, float, float, str, float]]]:
    """Build non-space sizes and half-local boxes from spans."""
    sizes: list[float] = []
    boxes: list[tuple[float, float, float, float, str, float]] = []
    for size, bb, t in spans:
        if not t.strip():
            continue
        x0, y0, x1, y1 = bb[0], bb[1], bb[2], bb[3]
        rx0, rx1 = x0 - half_origin_x, x1 - half_origin_x
        for ch in t:
            if not ch.isspace():
                sizes.append(size)
        boxes.append((rx0, y0, rx1, y1, t, size))
    return sizes, boxes


# ---------------------------------------------------------------------------
# Multi-page dual report
# ---------------------------------------------------------------------------


@dataclass
class MetricsThresholds:
    small_pt: float = DEFAULT_SMALL_PT
    crush_ratio_max: float = DEFAULT_CRUSH_RATIO_MAX
    min_font_hard: float = DEFAULT_MIN_FONT_HARD
    max_left_col_gap: float = DEFAULT_MAX_LEFT_COL_GAP
    min_chars_for_font_gates: int = DEFAULT_MIN_CHARS_FOR_FONT_GATES
    half_width: float = DEFAULT_HALF_WIDTH


@dataclass
class PageMetrics:
    page_index: int  # 0-based
    half: str
    n_chars: int
    cjk_chars: int
    latin_chars: int
    crush_ratio: float
    min_font_pt: float | None
    median_font_pt: float | None
    max_left_col_gap: float
    soh_hits: int
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures


@dataclass
class DualLayoutReport:
    path: str
    pages: list[PageMetrics]
    profile: str  # default | strict

    @property
    def ok(self) -> bool:
        return all(p.ok for p in self.pages)

    def to_json(self) -> dict:
        return {
            "path": self.path,
            "profile": self.profile,
            "ok": self.ok,
            "pages": [asdict(p) for p in self.pages],
        }


def parse_pages_spec(spec: str | None) -> list[int] | None:
    """Parse 1-based page ranges like ``4-26`` or ``4-6,10`` → sorted unique 1-based.

    Returns None if *spec* is None/empty (meaning all pages).
    """
    if spec is None or not str(spec).strip():
        return None
    out: set[int] = set()
    for part in str(spec).split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            start, end = int(a.strip()), int(b.strip())
            if start < 1 or end < start:
                raise ValueError(f"invalid page range: {part!r}")
            out.update(range(start, end + 1))
        else:
            n = int(part)
            if n < 1:
                raise ValueError(f"page numbers are 1-based, got {n}")
            out.add(n)
    return sorted(out)


def _evaluate_page(
    sizes: list[float],
    boxes: list[tuple[float, float, float, float, str, float]],
    spans: list[tuple[float, tuple, str]],
    half_width: float,
    *,
    profile: str,
    thresholds: MetricsThresholds,
) -> tuple[list[str], list[str], float, float | None, float | None, int, float]:
    n = len(sizes)
    cr = crush_ratio(sizes, thresholds.small_pt)
    gap = max_left_col_gap(boxes, half_width)
    soh = soh_hits_in_spans(spans)
    min_pt = min(sizes) if sizes else None
    med_pt = float(statistics.median(sizes)) if sizes else None

    failures: list[str] = []
    warnings: list[str] = []
    n_gate = thresholds.min_chars_for_font_gates

    if n >= n_gate and cr > thresholds.crush_ratio_max:
        failures.append("crush")
    if n > n_gate and min_pt is not None and min_pt < thresholds.min_font_hard:
        failures.append("min_font")
    if soh > 0:
        failures.append("soh")

    if gap > thresholds.max_left_col_gap:
        if profile == "strict":
            failures.append("vgap")
        else:
            warnings.append("vgap")

    return failures, warnings, cr, min_pt, med_pt, soh, gap


def analyze_dual_pdf(
    path: Path | str,
    *,
    pages: list[int] | None = None,
    half: str = "auto",
    profile: str = "default",
    thresholds: MetricsThresholds | None = None,
) -> DualLayoutReport:
    """Analyze one or more pages of a dual/mono PDF (text layer only).

    *pages*: 1-based PDF page numbers; None = all pages.
    *profile*: ``default`` (gap soft) or ``strict`` (gap hard fail).
    """
    import pymupdf

    if profile not in ("default", "strict"):
        raise ValueError(f"unknown profile: {profile!r}")
    if half not in ("auto", "left", "right", "full"):
        raise ValueError(f"unknown half: {half!r}")

    thresholds = thresholds or MetricsThresholds()
    path = Path(path)
    doc = pymupdf.open(path)
    page_metrics: list[PageMetrics] = []
    try:
        if pages is None:
            indices = list(range(doc.page_count))
        else:
            indices = []
            for p1 in pages:
                idx = p1 - 1
                if idx < 0 or idx >= doc.page_count:
                    raise IndexError(
                        f"page {p1} out of range (PDF has {doc.page_count} pages)"
                    )
                indices.append(idx)

        for page_index in indices:
            page = doc[page_index]
            half_name, origin_x, hw, spans = choose_half(
                page, half, thresholds.half_width
            )
            sizes, boxes = spans_to_boxes(spans, origin_x)
            failures, warnings, cr, min_pt, med_pt, soh, gap = _evaluate_page(
                sizes,
                boxes,
                spans,
                hw,
                profile=profile,
                thresholds=thresholds,
            )
            page_metrics.append(
                PageMetrics(
                    page_index=page_index,
                    half=half_name,
                    n_chars=len(sizes),
                    cjk_chars=cjk_char_count(spans),
                    latin_chars=latin_char_count(spans),
                    crush_ratio=cr,
                    min_font_pt=min_pt,
                    median_font_pt=med_pt,
                    max_left_col_gap=gap,
                    soh_hits=soh,
                    failures=failures,
                    warnings=warnings,
                )
            )
    finally:
        doc.close()

    return DualLayoutReport(path=str(path), pages=page_metrics, profile=profile)


def format_page_line(pm: PageMetrics) -> str:
    status = "PASS" if pm.ok else "FAIL"
    p1 = pm.page_index + 1
    min_s = f"{pm.min_font_pt:.1f}" if pm.min_font_pt is not None else "n/a"
    parts = [
        f"[{status}] p{p1} half={pm.half}",
        f"crush={pm.crush_ratio:.4f}",
        f"min={min_s}",
        f"vgap={pm.max_left_col_gap:.1f}",
        f"cjk={pm.cjk_chars}",
        f"soh={pm.soh_hits}",
    ]
    if pm.failures:
        parts.append("failures=" + ",".join(pm.failures))
    if pm.warnings:
        parts.append("warnings=" + ",".join(pm.warnings))
    return " ".join(parts)


def write_report_json(report: DualLayoutReport, path: Path | str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.to_json(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
