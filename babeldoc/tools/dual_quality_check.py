#!/usr/bin/env python3
"""Dual-quality helpers: IL fingerprint smoke, PNG SSIM, dual text-layer metrics.

Modes
-----
- ``--self-check``: empty-Document geometry fingerprint (CI smoke)
- ``--mode ssim``: compare equal-length lists of page PNGs (OpenCV + skimage)
- ``--dual PATH``: S1.1 multi-page text-layer metrics on an existing dual PDF

``--dual`` and ``--mode ssim`` are mutually exclusive.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _fingerprint_empty() -> str:
    from babeldoc.format.pdf.document_il.il_version_1 import Document
    from babeldoc.format.pdf.document_il.utils.il_layout_fingerprint import (
        il_layout_fingerprint,
    )

    return il_layout_fingerprint(Document(page=[]))


def _load_gray_png(path: Path):
    import cv2
    import numpy as np

    img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise SystemExit(f"failed to read PNG: {path}")
    return np.asarray(img)


def _ssim_compare(
    actual: Path, expected: Path, work_dir: Path, page_index: int
) -> float:
    import cv2
    import numpy as np
    from skimage.metrics import structural_similarity

    a = _load_gray_png(actual)
    e = _load_gray_png(expected)
    if a.shape != e.shape:
        raise SystemExit(
            f"page {page_index}: shape mismatch actual={a.shape} expected={e.shape}"
        )
    score = float(structural_similarity(a, e, data_range=255))
    if score < 0.98:
        work_dir.mkdir(parents=True, exist_ok=True)
        diff = np.abs(a.astype(np.int16) - e.astype(np.int16)).astype(np.uint8)
        diff_path = work_dir / f"page{page_index}_diff.png"
        cv2.imwrite(str(diff_path), diff)
        print(
            f"FAIL page_index={page_index} ssim={score:.4f} "
            f"actual={actual} expected={expected} diff={diff_path}",
            file=sys.stderr,
        )
    return score


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "BabelDOC dual-quality helpers. "
            "See tests/golden/README.md for operator workflow."
        ),
    )
    p.add_argument(
        "--self-check",
        action="store_true",
        help="Print empty-Document geometry fingerprint and exit",
    )
    p.add_argument(
        "--expected-fingerprint",
        type=str,
        default=None,
        help="With --self-check: exit 1 if fingerprint differs",
    )
    p.add_argument(
        "--mode",
        choices=("il", "ssim"),
        default="il",
        help="il = self-check fingerprint; ssim = compare PNGs (not with --dual)",
    )
    p.add_argument(
        "--actual-png",
        type=Path,
        action="append",
        default=[],
        help="Actual page PNG for ssim (repeatable)",
    )
    p.add_argument(
        "--expected-png",
        type=Path,
        action="append",
        default=[],
        help="Expected page PNG for ssim (repeatable)",
    )
    p.add_argument(
        "--work-dir",
        type=Path,
        default=Path("dual_quality_out"),
        help="Directory for ssim diff artifacts",
    )
    # S1.1 metrics
    p.add_argument(
        "--dual",
        type=Path,
        default=None,
        help="Existing dual/mono PDF for text-layer metrics (S1.1)",
    )
    p.add_argument(
        "--pages",
        type=str,
        default=None,
        help="1-based page ranges, e.g. 4-26 or 4-6,10 (default: all)",
    )
    p.add_argument(
        "--half",
        choices=("auto", "left", "right", "full"),
        default="auto",
        help="Which half to score (auto = more CJK); dual_quality --pages is 1-based",
    )
    p.add_argument(
        "--profile",
        choices=("default", "strict"),
        default="default",
        help="default: vgap is warning; strict: vgap hard-fails",
    )
    p.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Write DualLayoutReport JSON to this path",
    )
    return p


def _run_dual_metrics(args: argparse.Namespace) -> int:
    from babeldoc.tools.dual_layout_metrics import (
        analyze_dual_pdf,
        format_page_line,
        parse_pages_spec,
        write_report_json,
    )

    if args.mode == "ssim":
        print(
            "error: --dual is mutually exclusive with --mode ssim",
            file=sys.stderr,
        )
        return 2

    dual: Path = args.dual
    if not dual.is_file():
        print(f"error: dual PDF not found: {dual}", file=sys.stderr)
        return 2

    try:
        pages = parse_pages_spec(args.pages)
    except ValueError as e:
        print(f"error: invalid --pages: {e}", file=sys.stderr)
        return 2

    try:
        report = analyze_dual_pdf(
            dual,
            pages=pages,
            half=args.half,
            profile=args.profile,
        )
    except IndexError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    for pm in report.pages:
        print(format_page_line(pm))

    if args.json_out is not None:
        write_report_json(report, args.json_out)
        print(f"json_out={args.json_out}")

    status = "PASS" if report.ok else "FAIL"
    print(f"[{status}] {report.path} pages={len(report.pages)} profile={report.profile}")
    return 0 if report.ok else 1


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.dual is not None:
        return _run_dual_metrics(args)

    if args.mode == "il" or args.self_check:
        if not args.self_check and args.mode == "il":
            print(
                "error: --mode il only supports --self-check in this release.\n"
                "Use --dual PATH for text-layer metrics (S1.1).\n"
                "Compute IL fingerprints in tests via il_layout_fingerprint(doc).",
                file=sys.stderr,
            )
            return 2
        fp = _fingerprint_empty()
        print(fp)
        if args.expected_fingerprint and fp != args.expected_fingerprint:
            print(
                f"FAIL fingerprint mismatch\n"
                f"  actual=  {fp}\n"
                f"  expected={args.expected_fingerprint}",
                file=sys.stderr,
            )
            return 1
        return 0

    # mode ssim
    actuals = args.actual_png or []
    expecteds = args.expected_png or []
    if len(actuals) != len(expecteds) or not actuals:
        print(
            "error: --mode ssim requires equal non-empty "
            "--actual-png and --expected-png lists",
            file=sys.stderr,
        )
        return 2
    exit_code = 0
    for i, (a, e) in enumerate(zip(actuals, expecteds, strict=True)):
        if not a.is_file() or not e.is_file():
            print(f"error: missing PNG actual={a} expected={e}", file=sys.stderr)
            return 2
        score = _ssim_compare(a, e, args.work_dir, i)
        print(f"page_index={i} ssim={score:.6f}")
        if score < 0.98:
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
