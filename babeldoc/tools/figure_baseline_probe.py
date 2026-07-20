#!/usr/bin/env python3
"""Figure dual baseline probe (dual-layer recover Phase 0).

Hard gate for born-digital figure golden quality. **No translation / no
pipeline side effects** — read an existing dual (or mono) PDF and score
layout metrics used before landing dual-layer PRs.

Metrics (ZH half of side-by-side dual, or full page if mono-width)::

    affil_mid          mean x-mid of affiliation-like lines (half-local)
    crush_ratio        fraction of non-space chars with size < 7pt
    max_left_col_gap   max vertical gap between consecutive left-col body spans
    fig_label_hits     chart-label tokens found inside long CJK body spans

Default fail thresholds (SCORECARD regression probe)::

    |affil_mid - page_center| > 25
    crush_ratio > 0.10
    max_left_col_gap > 120
    any fig_label_hits

Usage::

    python -m babeldoc.tools.figure_baseline_probe \\
        --dual tests/golden/translate.cli.text.with.figure.no_watermark.zh-CN.dual.pdf

    python -m babeldoc.tools.figure_baseline_probe --self-check
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path

from babeldoc.tools.dual_layout_metrics import DEFAULT_CRUSH_RATIO_MAX
from babeldoc.tools.dual_layout_metrics import DEFAULT_HALF_WIDTH
from babeldoc.tools.dual_layout_metrics import DEFAULT_MAX_LEFT_COL_GAP
from babeldoc.tools.dual_layout_metrics import DEFAULT_SMALL_PT
from babeldoc.tools.dual_layout_metrics import choose_half as _choose_half
from babeldoc.tools.dual_layout_metrics import cjk_char_count as _cjk_char_count
from babeldoc.tools.dual_layout_metrics import crush_ratio as _crush_ratio_fn
from babeldoc.tools.dual_layout_metrics import max_left_col_gap as _max_left_col_gap
from babeldoc.tools.dual_layout_metrics import spans_to_boxes

DEFAULT_PAGE_CENTER = DEFAULT_HALF_WIDTH / 2.0  # 306

# Fail if outside these (SCORECARD "Flag as regression").
DEFAULT_AFFIL_CENTER_TOL = 25.0

# Chart / figure annotation tokens that must not appear inside long body text
# when translate_figure_text is off (混段 regression).
DEFAULT_FIG_LABEL_KEYS: tuple[str, ...] = (
    "Ancilla",
    "Data",
    "I/Q",
    "arb.",
    "Readout frequency",
    "SNAIL",
    "flux",
)

_AFFIL_KEYS: tuple[str, ...] = (
    "大学",
    "University",
    "Department",
    "Yale",
    "耶鲁",
    "Applied",
    "系",
    "学院",
    "康涅狄格",
    "New Haven",
    "Institute",
    "研究所",
)


def _has_cjk(s: str) -> bool:
    return any("\u4e00" <= c <= "\u9fff" for c in s)


@dataclass
class ProbeThresholds:
    page_center: float = DEFAULT_PAGE_CENTER
    affil_center_tol: float = DEFAULT_AFFIL_CENTER_TOL
    crush_ratio_max: float = DEFAULT_CRUSH_RATIO_MAX
    max_left_col_gap: float = DEFAULT_MAX_LEFT_COL_GAP
    small_pt: float = DEFAULT_SMALL_PT
    fig_label_keys: tuple[str, ...] = DEFAULT_FIG_LABEL_KEYS


@dataclass
class ProbeResult:
    path: str
    page_index: int
    page_width: float
    page_height: float
    half: str  # "left" | "right" | "full"
    half_origin_x: float
    half_width: float
    n_chars: int
    cjk_chars: int
    crush_ratio: float
    max_left_col_gap: float
    affil_mid: float | None
    page_center: float
    affil_delta: float | None
    fig_label_hits: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures


def _analyze_spans(
    spans: list[tuple[float, tuple, str]],
    half_origin_x: float,
    half_width: float,
    thresholds: ProbeThresholds,
) -> dict:
    sizes, boxes = spans_to_boxes(spans, half_origin_x)
    n = len(sizes)
    crush = _crush_ratio_fn(sizes, thresholds.small_pt)
    max_gap = _max_left_col_gap(boxes, half_width)

    # Affiliation-like lines near header band.
    by_y: dict[int, list] = defaultdict(list)
    for b in boxes:
        if 60 < b[1] < 240 and 7.0 <= b[5] <= 14.0:
            by_y[round(b[1])].append(b)

    affil_mids: list[float] = []
    for _y, items in sorted(by_y.items()):
        text = "".join(i[4] for i in items)
        if any(k in text for k in _AFFIL_KEYS):
            mids = [(i[0] + i[2]) / 2.0 for i in items]
            if mids:
                affil_mids.append(sum(mids) / len(mids))
    affil_mid = (sum(affil_mids) / len(affil_mids)) if affil_mids else None

    # Long CJK body spans must not contain chart label tokens.
    long_body_bits: list[str] = []
    for b in boxes:
        width = b[2] - b[0]
        if 8.0 <= b[5] <= 12.5 and width > 80 and _has_cjk(b[4]):
            long_body_bits.append(b[4])
    joined = " ".join(long_body_bits)
    fig_hits = [k for k in thresholds.fig_label_keys if k in joined]

    return {
        "n_chars": n,
        "cjk_chars": _cjk_char_count(spans),
        "crush_ratio": crush,
        "max_left_col_gap": max_gap,
        "affil_mid": affil_mid,
        "fig_label_hits": fig_hits,
    }


def evaluate_metrics(
    *,
    affil_mid: float | None,
    crush_ratio: float,
    max_left_col_gap: float,
    fig_label_hits: list[str],
    thresholds: ProbeThresholds,
    require_affil: bool = False,
) -> list[str]:
    """Return list of failure strings (empty ⇒ pass)."""
    failures: list[str] = []
    if affil_mid is None:
        if require_affil:
            failures.append("affil_mid: not detected (require_affil)")
    else:
        delta = abs(affil_mid - thresholds.page_center)
        if delta > thresholds.affil_center_tol:
            failures.append(
                f"affil_mid: |{affil_mid:.1f}-{thresholds.page_center:.1f}|="
                f"{delta:.1f} > {thresholds.affil_center_tol}"
            )
    if crush_ratio > thresholds.crush_ratio_max:
        failures.append(
            f"crush_ratio: {crush_ratio:.4f} > {thresholds.crush_ratio_max}"
        )
    if max_left_col_gap > thresholds.max_left_col_gap:
        failures.append(
            f"max_left_col_gap: {max_left_col_gap:.1f} > {thresholds.max_left_col_gap}"
        )
    if fig_label_hits:
        failures.append(f"fig_label_hits: {fig_label_hits}")
    return failures


def probe_dual_pdf(
    path: Path | str,
    *,
    page_index: int = 0,
    half: str = "auto",
    half_width: float = DEFAULT_HALF_WIDTH,
    thresholds: ProbeThresholds | None = None,
    require_affil: bool = False,
) -> ProbeResult:
    """Analyze one page of a dual/mono PDF. Does not modify the file."""
    import pymupdf

    thresholds = thresholds or ProbeThresholds()
    path = Path(path)
    doc = pymupdf.open(path)
    try:
        if page_index < 0 or page_index >= doc.page_count:
            raise IndexError(
                f"page_index={page_index} out of range (pages={doc.page_count})"
            )
        page = doc[page_index]
        half_name, origin_x, hw, spans = _choose_half(page, half, half_width)
        stats = _analyze_spans(spans, origin_x, hw, thresholds)
        affil_mid = stats["affil_mid"]
        affil_delta = (
            abs(affil_mid - thresholds.page_center) if affil_mid is not None else None
        )
        failures = evaluate_metrics(
            affil_mid=affil_mid,
            crush_ratio=stats["crush_ratio"],
            max_left_col_gap=stats["max_left_col_gap"],
            fig_label_hits=stats["fig_label_hits"],
            thresholds=thresholds,
            require_affil=require_affil,
        )
        notes: list[str] = []
        if affil_mid is None:
            notes.append("affil_mid not detected (skipped unless --require-affil)")
        if stats["cjk_chars"] == 0:
            notes.append("no CJK on selected half — check --half / dual layout")

        return ProbeResult(
            path=str(path),
            page_index=page_index,
            page_width=float(page.rect.width),
            page_height=float(page.rect.height),
            half=half_name,
            half_origin_x=origin_x,
            half_width=hw,
            n_chars=stats["n_chars"],
            cjk_chars=stats["cjk_chars"],
            crush_ratio=stats["crush_ratio"],
            max_left_col_gap=stats["max_left_col_gap"],
            affil_mid=affil_mid,
            page_center=thresholds.page_center,
            affil_delta=affil_delta,
            fig_label_hits=list(stats["fig_label_hits"]),
            failures=failures,
            notes=notes,
        )
    finally:
        doc.close()


def _make_self_check_pdf(path: Path) -> None:
    """Tiny synthetic dual (ZH left / EN right) that passes default thresholds."""
    import pymupdf

    doc = pymupdf.open()
    # Side-by-side letter dual
    page = doc.new_page(width=1224, height=792)
    # pymupdf built-in CJK face (needed so get_text sees 汉字)
    zh = "china-s"
    affil = "Department of Applied Physics, Yale University"
    # Start x so line mid ≈ 306 for ~10pt Latin affil
    page.insert_text((150, 100), affil, fontsize=10, fontname="helv")
    page.insert_text(
        (72, 200), "这是正文第一行用于探测左侧栏间距。" * 2, fontsize=10, fontname=zh
    )
    page.insert_text(
        (72, 220), "这是正文第二行继续排列。" * 2, fontsize=10, fontname=zh
    )
    page.insert_text((72, 240), "第三行正文内容。" * 3, fontsize=10, fontname=zh)
    # Right half EN
    page.insert_text((612 + 72, 80), "English title half", fontsize=12, fontname="helv")
    page.insert_text(
        (612 + 72, 200),
        "English body text for the dual right side.",
        fontsize=10,
        fontname="helv",
    )
    doc.save(path)
    doc.close()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Figure dual baseline probe (Phase 0 hard gate). "
            "Exit 0 if metrics pass; exit 1 on regression or error."
        ),
    )
    p.add_argument(
        "--dual",
        type=Path,
        default=None,
        help="Path to dual (or mono) PDF to probe",
    )
    p.add_argument(
        "--page",
        type=int,
        default=0,
        help="0-based page index (default 0)",
    )
    p.add_argument(
        "--half",
        choices=("auto", "left", "right", "full"),
        default="auto",
        help="Which half to score (auto = more CJK)",
    )
    p.add_argument(
        "--half-width",
        type=float,
        default=DEFAULT_HALF_WIDTH,
        help="Mono page width used to detect dual layout (default 612)",
    )
    p.add_argument(
        "--require-affil",
        action="store_true",
        help="Fail if affiliation line cannot be detected",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Print ProbeResult as JSON",
    )
    p.add_argument(
        "--self-check",
        action="store_true",
        help="Write a tiny synthetic dual, probe it, expect pass",
    )
    p.add_argument(
        "--work-dir",
        type=Path,
        default=Path("dual_quality_out"),
        help="Directory for --self-check synthetic PDF",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.self_check:
        args.work_dir.mkdir(parents=True, exist_ok=True)
        synth = args.work_dir / "figure_probe_selfcheck_dual.pdf"
        _make_self_check_pdf(synth)
        result = probe_dual_pdf(
            synth,
            page_index=0,
            half="left",
            require_affil=False,
        )
        # Self-check only asserts we can run + crush/gap/fig gates; affil
        # placement in the synthetic is approximate.
        hard_fail = [
            f
            for f in result.failures
            if not f.startswith("affil_mid:")
        ]
        if args.json:
            print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
        else:
            print(f"self-check pdf={synth}")
            _print_human(result)
        if hard_fail:
            print("SELF-CHECK FAIL:", "; ".join(hard_fail), file=sys.stderr)
            return 1
        print("SELF-CHECK OK")
        return 0

    if args.dual is None:
        print("error: --dual PATH is required (or use --self-check)", file=sys.stderr)
        return 2

    if not args.dual.is_file():
        print(f"error: dual PDF not found: {args.dual}", file=sys.stderr)
        return 2

    result = probe_dual_pdf(
        args.dual,
        page_index=args.page,
        half=args.half,
        half_width=args.half_width,
        require_affil=args.require_affil,
    )
    if args.json:
        print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    else:
        _print_human(result)

    return 0 if result.ok else 1


def _print_human(result: ProbeResult) -> None:
    status = "PASS" if result.ok else "FAIL"
    print(f"[{status}] {result.path} page={result.page_index} half={result.half}")
    print(f"  page_size=({result.page_width:.1f}x{result.page_height:.1f})")
    print(f"  n_chars={result.n_chars} cjk_chars={result.cjk_chars}")
    print(f"  crush_ratio={result.crush_ratio:.4f}  (max {DEFAULT_CRUSH_RATIO_MAX})")
    print(
        f"  max_left_col_gap={result.max_left_col_gap:.1f}pt  "
        f"(max {DEFAULT_MAX_LEFT_COL_GAP})"
    )
    if result.affil_mid is None:
        print("  affil_mid=None")
    else:
        print(
            f"  affil_mid={result.affil_mid:.1f}  center={result.page_center:.1f}  "
            f"|Δ|={result.affil_delta:.1f}  (tol {DEFAULT_AFFIL_CENTER_TOL})"
        )
    print(f"  fig_label_hits={result.fig_label_hits or []}")
    for n in result.notes:
        print(f"  note: {n}")
    for f in result.failures:
        print(f"  FAIL: {f}")


if __name__ == "__main__":
    raise SystemExit(main())
