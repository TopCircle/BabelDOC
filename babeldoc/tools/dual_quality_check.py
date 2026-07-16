#!/usr/bin/env python3
"""Thin CLI for dual-quality checks (PR-01, review-tightened).

What this **does**:
- ``--self-check``: print geometry fingerprint of an empty Document
- ``--mode ssim``: compare equal-length lists of page PNGs (OpenCV + skimage)

What this **does not** do (later PRs):
- PDF → translate → dual end-to-end
- Reload of debug IL JSON (XMLConverter has write-only JSON today)

Library entry points for tests / future harness code:
- ``babeldoc.format.pdf.document_il.utils.il_layout_fingerprint.il_layout_fingerprint``
- ``babeldoc.translator.fixed_map_translator.FixedMapTranslator``
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
            "Not a full PDF dual golden runner (see tests/golden/README.md)."
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
        help="il = self-check fingerprint only; ssim = compare PNGs",
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
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.mode == "il" or args.self_check:
        if not args.self_check and args.mode == "il":
            print(
                "error: --mode il only supports --self-check in this release.\n"
                "Compute fingerprints in tests via il_layout_fingerprint(doc).\n"
                "PDF/IL-JSON dual goldens are not implemented yet.",
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
