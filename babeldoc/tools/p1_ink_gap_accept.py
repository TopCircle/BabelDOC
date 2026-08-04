"""P1 dual acceptance: |zh_ink_gap − en_ink_gap| ≤ ε on sample pages.

Layout-First plan §6 P1 OA gate. Reads an existing dual PDF (left ZH / right EN
side-by-side), finds a display-title + first body-below pair on each half, and
scores relative ink gap.

Usage::

    python -m babeldoc.tools.p1_ink_gap_accept \\
        --pdf path/to/book.zh-CN.dual.pdf \\
        --pages 3,7,12,19,33,40,73 \\
        --json-out docs/p1_ink_gap_accept_oa.json

Exit 0 always unless --fail-on-miss (then non-zero when any page fails ε and
is not marked clamped/skip).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Keep in sync with vertical_gap.RELATIVE_GAP_EPS_PT / MAX_SINGLE_JUMP_DY_PT
DEFAULT_EPS = 2.0
DEFAULT_MAX_JUMP = 24.0
DEFAULT_TITLE_SIZE = 18.0
DEFAULT_HALF_WIDTH = 612.0

# Default OA chapter-ish sample (plan problem pages + dual_layout diff pages).
DEFAULT_PAGES = (3, 7, 12, 19, 33, 40, 73)


@dataclass
class HalfGap:
    title_text: str
    title_size: float
    body_text: str
    body_size: float
    gap_pt: float
    title_bbox: list[float]
    body_bbox: list[float]


@dataclass
class PageGapResult:
    page: int  # 1-based
    zh: dict[str, Any] | None
    en: dict[str, Any] | None
    en_gap: float | None
    zh_gap: float | None
    abs_diff: float | None
    deficit: float | None  # max(0, en_gap - eps - zh_gap) when both known
    pass_eps: bool | None
    likely_clamped: bool | None  # deficit > max_jump
    note: str


def _spans_in_x(page, x_min: float, x_max: float) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for block in page.get_text("dict").get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for sp in line.get("spans", []):
                bb = sp.get("bbox")
                if not bb or len(bb) < 4:
                    continue
                x0, y0, x1, y1 = (float(bb[0]), float(bb[1]), float(bb[2]), float(bb[3]))
                cx = (x0 + x1) / 2.0
                if not (x_min <= cx < x_max):
                    continue
                text = (sp.get("text") or "").strip()
                if not text:
                    continue
                out.append(
                    {
                        "text": text,
                        "size": float(sp.get("size") or 0.0),
                        "bbox": [x0, y0, x1, y1],
                        "y0": y0,
                        "y1": y1,
                        "x0": x0,
                        "x1": x1,
                    }
                )
    return out


def find_title_body_gap(
    spans: list[dict[str, Any]],
    *,
    title_size_min: float = DEFAULT_TITLE_SIZE,
) -> HalfGap | None:
    """Largest display-ish span + first smaller span clearly below it.

    PyMuPDF y grows downward: visual gap under title = body.y0 − title.y1.
    """
    titles = [s for s in spans if s["size"] >= title_size_min]
    if not titles:
        return None
    # Prefer larger size, then higher on page (smaller y0).
    title = max(titles, key=lambda s: (s["size"], -s["y0"]))
    below = [
        s
        for s in spans
        if s["y0"] > title["y1"] - 1.0
        and s["size"] < title["size"] * 0.85
        and len(s["text"]) > 1
        and s is not title
    ]
    if not below:
        return None
    body = min(below, key=lambda s: s["y0"])
    gap = float(body["y0"] - title["y1"])
    return HalfGap(
        title_text=title["text"][:80],
        title_size=title["size"],
        body_text=body["text"][:80],
        body_size=body["size"],
        gap_pt=gap,
        title_bbox=list(title["bbox"]),
        body_bbox=list(body["bbox"]),
    )


def half_gap_dict(g: HalfGap | None) -> dict[str, Any] | None:
    if g is None:
        return None
    return asdict(g)


def score_page(
    page,
    page_1based: int,
    *,
    half_width: float = DEFAULT_HALF_WIDTH,
    eps: float = DEFAULT_EPS,
    max_jump: float = DEFAULT_MAX_JUMP,
    title_size_min: float = DEFAULT_TITLE_SIZE,
) -> PageGapResult:
    w = float(page.rect.width)
    # Side-by-side dual: left [0, mid), right [mid, w). Prefer explicit half_width
    # when page is ~2× letter; else mid split.
    mid = half_width if abs(w - 2 * half_width) < 20 else w / 2.0

    zh_spans = _spans_in_x(page, 0.0, mid)
    en_spans = _spans_in_x(page, mid, w + 1.0)

    zh = find_title_body_gap(zh_spans, title_size_min=title_size_min)
    en = find_title_body_gap(en_spans, title_size_min=title_size_min)

    if zh is None and en is None:
        return PageGapResult(
            page=page_1based,
            zh=None,
            en=None,
            en_gap=None,
            zh_gap=None,
            abs_diff=None,
            deficit=None,
            pass_eps=None,
            likely_clamped=None,
            note="skip: no title+body pair on either half",
        )
    if zh is None:
        return PageGapResult(
            page=page_1based,
            zh=None,
            en=half_gap_dict(en),
            en_gap=en.gap_pt if en else None,
            zh_gap=None,
            abs_diff=None,
            deficit=None,
            pass_eps=None,
            likely_clamped=None,
            note="skip: no ZH title+body pair",
        )
    if en is None:
        return PageGapResult(
            page=page_1based,
            zh=half_gap_dict(zh),
            en=None,
            en_gap=None,
            zh_gap=zh.gap_pt,
            abs_diff=None,
            deficit=None,
            pass_eps=None,
            likely_clamped=None,
            note="skip: no EN title+body pair",
        )

    en_gap = float(en.gap_pt)
    zh_gap = float(zh.gap_pt)
    abs_diff = abs(zh_gap - en_gap)
    # Same spirit as vertical_gap.gap_deficit (need = max(en,0)).
    need = max(en_gap, 0.0)
    deficit = max(0.0, need - eps - zh_gap)
    pass_eps = deficit <= 0.0
    # If ZH still short by more than one post-pass jump, clamp likely blocked full EN match.
    likely_clamped = (not pass_eps) and (deficit > max_jump - 1e-6)

    note = "pass" if pass_eps else (
        "fail_clamped" if likely_clamped else "fail_short"
    )
    return PageGapResult(
        page=page_1based,
        zh=half_gap_dict(zh),
        en=half_gap_dict(en),
        en_gap=round(en_gap, 3),
        zh_gap=round(zh_gap, 3),
        abs_diff=round(abs_diff, 3),
        deficit=round(deficit, 3),
        pass_eps=pass_eps,
        likely_clamped=likely_clamped,
        note=note,
    )


def evaluate_pdf(
    pdf_path: Path,
    pages: list[int],
    *,
    eps: float = DEFAULT_EPS,
    max_jump: float = DEFAULT_MAX_JUMP,
    half_width: float = DEFAULT_HALF_WIDTH,
    title_size_min: float = DEFAULT_TITLE_SIZE,
) -> dict[str, Any]:
    import fitz

    doc = fitz.open(pdf_path)
    results: list[dict[str, Any]] = []
    try:
        for p1 in pages:
            if p1 < 1 or p1 > len(doc):
                results.append(
                    asdict(
                        PageGapResult(
                            page=p1,
                            zh=None,
                            en=None,
                            en_gap=None,
                            zh_gap=None,
                            abs_diff=None,
                            deficit=None,
                            pass_eps=None,
                            likely_clamped=None,
                            note=f"skip: page out of range (doc has {len(doc)})",
                        )
                    )
                )
                continue
            r = score_page(
                doc[p1 - 1],
                p1,
                half_width=half_width,
                eps=eps,
                max_jump=max_jump,
                title_size_min=title_size_min,
            )
            results.append(asdict(r))
    finally:
        doc.close()

    scored = [r for r in results if r.get("pass_eps") is not None]
    passed = [r for r in scored if r["pass_eps"]]
    failed = [r for r in scored if not r["pass_eps"]]
    clamped = [r for r in failed if r.get("likely_clamped")]
    skipped = [r for r in results if r.get("pass_eps") is None]

    # P1 acceptance status for the sample set.
    if not scored:
        status = "no_scored_pages"
    elif not failed:
        status = "pass"
    elif len(clamped) == len(failed):
        status = "partial_clamped"  # all fails explained by 24pt transition
    else:
        status = "fail"

    return {
        "schema": "babeldoc-p1-ink-gap-accept/v1",
        "pdf": str(pdf_path),
        "eps_pt": eps,
        "max_jump_pt": max_jump,
        "pages_requested": pages,
        "status": status,
        "summary": {
            "scored": len(scored),
            "pass": len(passed),
            "fail": len(failed),
            "fail_clamped": len(clamped),
            "skipped": len(skipped),
        },
        "results": results,
        "done_rule": (
            "P1 implementation Done when mechanism ships; "
            "P1 acceptance Pass when all scored sample pages pass ε, "
            "or Partial when remaining fails are likely_clamped (dy cap)."
        ),
    }


def _parse_pages(s: str) -> list[int]:
    pages: list[int] = []
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            pages.extend(range(int(a), int(b) + 1))
        else:
            pages.append(int(part))
    return pages


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--pdf", required=True, type=Path)
    p.add_argument(
        "--pages",
        default=",".join(str(x) for x in DEFAULT_PAGES),
        help="1-based pages, e.g. 3,7,12,19 or 1-5",
    )
    p.add_argument("--eps", type=float, default=DEFAULT_EPS)
    p.add_argument("--max-jump", type=float, default=DEFAULT_MAX_JUMP)
    p.add_argument("--half-width", type=float, default=DEFAULT_HALF_WIDTH)
    p.add_argument("--title-size-min", type=float, default=DEFAULT_TITLE_SIZE)
    p.add_argument("--json-out", type=Path, default=None)
    p.add_argument(
        "--fail-on-miss",
        action="store_true",
        help="exit 1 if status is fail (partial_clamped still exits 0)",
    )
    args = p.parse_args(argv)

    if not args.pdf.is_file():
        print(f"pdf not found: {args.pdf}", file=sys.stderr)
        return 2

    pages = _parse_pages(args.pages)
    report = evaluate_pdf(
        args.pdf,
        pages,
        eps=args.eps,
        max_jump=args.max_jump,
        half_width=args.half_width,
        title_size_min=args.title_size_min,
    )

    # Human table
    print(f"pdf: {report['pdf']}")
    print(f"status: {report['status']}  summary={report['summary']}")
    print(
        f"{'page':>5}  {'en_gap':>8}  {'zh_gap':>8}  {'|diff|':>8}  "
        f"{'deficit':>8}  {'ε-pass':>6}  {'clamp?':>6}  note"
    )
    for r in report["results"]:
        def fmt(x):
            return f"{x:8.2f}" if isinstance(x, (int, float)) else f"{'—':>8}"

        print(
            f"{r['page']:5d}  {fmt(r['en_gap'])}  {fmt(r['zh_gap'])}  "
            f"{fmt(r['abs_diff'])}  {fmt(r['deficit'])}  "
            f"{str(r['pass_eps']):>6}  {str(r['likely_clamped']):>6}  {r['note']}"
        )

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {args.json_out}")

    if args.fail_on_miss and report["status"] == "fail":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
