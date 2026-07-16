#!/usr/bin/env python3
"""Dual-quality harness CLI (PR-01 scaffold).

Entry (architecture plan Phase 0b)::

    python -m babeldoc.tools.dual_quality_check --input PATH \\
        [--pages 1,2] [--mode il|ssim|both] [--dpi 72]

**PR-01 scope (scaffold):**
- ``--mode il``: fingerprint a constructed or JSON-serialized Document IL
  (or compute fingerprint after a lightweight in-process helper for tests)
- ``--mode ssim``: compare two pixmap PNGs (actual vs expected) when provided
- Full PDF→translate→dual pipeline golden runs land in later quality PRs

Failure UX prints page index and artifact paths under ``--work-dir``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _parse_pages(spec: str | None) -> list[int] | None:
    if not spec:
        return None
    pages: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        pages.append(int(part))
    return pages or None


def _fingerprint_from_minimal_il() -> str:
    """Self-check: empty document has a stable empty-hash path."""
    from babeldoc.format.pdf.document_il.il_version_1 import Document
    from babeldoc.format.pdf.document_il.utils.il_layout_fingerprint import (
        il_layout_fingerprint,
    )

    doc = Document(page=[])
    return il_layout_fingerprint(doc)


def _fingerprint_from_json(path: Path) -> str:
    """Load IL from debug JSON if shape is compatible; else error clearly."""
    from babeldoc.format.pdf.document_il.utils.il_layout_fingerprint import (
        il_layout_fingerprint,
    )
    from babeldoc.format.pdf.document_il.xml_converter import XMLConverter

    converter = XMLConverter()
    # write_json dumps; read path may be create_il / typsetting debug dumps
    data = json.loads(path.read_text(encoding="utf-8"))
    if not hasattr(converter, "read_json") and not hasattr(converter, "from_json"):
        # Fall back: only support our test helper structure via Document rebuild
        raise SystemExit(
            "IL JSON reload is limited in this scaffold. "
            "Use unit tests (il_layout_fingerprint) or pass --self-check. "
            f"Got keys: {list(data)[:8] if isinstance(data, dict) else type(data)}"
        )
    # Prefer documented API if present
    if hasattr(converter, "read_json"):
        doc = converter.read_json(path)  # type: ignore[attr-defined]
    else:
        doc = converter.from_json(data)  # type: ignore[attr-defined]
    return il_layout_fingerprint(doc)


def _load_gray_png(path: Path):
    import cv2
    import numpy as np

    img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise SystemExit(f"failed to read PNG: {path}")
    return np.asarray(img)


def _ssim_compare(actual: Path, expected: Path, work_dir: Path, page_index: int) -> float:
    """Return SSIM in [0,1]. Write abs-diff PNG under work_dir on soft fail."""
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
        description="BabelDOC dual-quality harness (scaffold)",
    )
    p.add_argument(
        "--input",
        type=Path,
        help="Input PDF (future full run) or IL debug JSON for --mode il",
    )
    p.add_argument(
        "--pages",
        type=str,
        default=None,
        help="Comma-separated 0-based page indices (reserved for full runs)",
    )
    p.add_argument(
        "--mode",
        choices=("il", "ssim", "both"),
        default="il",
        help="il = layout fingerprint; ssim = pixmap compare; both = both",
    )
    p.add_argument(
        "--dpi",
        type=int,
        default=72,
        help="Pixmap DPI for ssim mode (default 72; scorecard may use 144)",
    )
    p.add_argument(
        "--actual-png",
        type=Path,
        action="append",
        default=[],
        help="Actual page PNG for ssim (repeatable, order = page order)",
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
        help="Directory for failure artifacts",
    )
    p.add_argument(
        "--self-check",
        action="store_true",
        help="Print fingerprint of empty Document (no --input needed)",
    )
    p.add_argument(
        "--expected-fingerprint",
        type=str,
        default=None,
        help="If set with --mode il, exit 1 when fingerprint differs",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _ = _parse_pages(args.pages)
    _ = args.dpi  # reserved for full pixmap capture later

    exit_code = 0
    fp: str | None = None

    if args.self_check:
        fp = _fingerprint_from_minimal_il()
        print(fp)
        if args.expected_fingerprint and fp != args.expected_fingerprint:
            print(
                f"FAIL fingerprint mismatch\n"
                f"  actual=  {fp}\n"
                f"  expected={args.expected_fingerprint}",
                file=sys.stderr,
            )
            return 1
        if args.mode == "ssim":
            # self-check is IL-only
            return 0
        if args.mode == "il":
            return 0
        # mode both: fall through only if user also passed ssim pngs

    if args.mode in ("il", "both") and not args.self_check:
        if args.input is None:
            print(
                "error: --input required for --mode il (or use --self-check)",
                file=sys.stderr,
            )
            return 2
        if args.input.suffix.lower() == ".json":
            try:
                fp = _fingerprint_from_json(args.input)
            except SystemExit as e:
                print(str(e), file=sys.stderr)
                return 2
            except Exception as e:
                print(
                    f"error: cannot load IL JSON for fingerprint: {e}\n"
                    "PR-01 scaffold: prefer unit tests or --self-check; "
                    "full PDF dual golden runs come in later PRs.",
                    file=sys.stderr,
                )
                return 2
        else:
            print(
                "error: PDF end-to-end dual golden is not in PR-01 scaffold.\n"
                "Use IL debug JSON, --self-check, or unit tests "
                "(tests/test_dual_golden_synth.py).",
                file=sys.stderr,
            )
            return 2
        print(f"il_layout_fingerprint={fp}")
        if args.expected_fingerprint and fp != args.expected_fingerprint:
            print(
                f"FAIL fingerprint mismatch\n"
                f"  actual=  {fp}\n"
                f"  expected={args.expected_fingerprint}",
                file=sys.stderr,
            )
            exit_code = 1

    if args.mode in ("ssim", "both"):
        actuals = args.actual_png or []
        expecteds = args.expected_png or []
        if len(actuals) != len(expecteds) or not actuals:
            print(
                "error: --mode ssim requires equal non-empty "
                "--actual-png and --expected-png lists",
                file=sys.stderr,
            )
            return 2
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
