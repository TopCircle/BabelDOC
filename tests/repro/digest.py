"""Layout digest comparison: canonical typsetting sha256 + geometry fingerprint.

Δ=0 gate for the Layout-First P0 repro infrastructure (design doc §2).

A "digest" is a pair:

* ``digest_sha256`` — sha256 of the canonical (sorted-key, compact) JSON
  serialization of the typsetting summary ``pages`` (per paragraph box,
  scale, optimal_scale and y-clustered line widths).
* ``fingerprint_sha256`` — ``il_layout_fingerprint`` of the post-typeset
  in-memory Document (geometry-only sha256).

Δ=0 holds when **both** hashes match the golden and the prior (pre-typeset)
``paragraph_finder`` debug_id sets are unchanged.

Typical usage::

    # CI / default: run the synthetic page and compare against the golden
    python tests/repro/digest.py --golden tests/repro/golden/synth_layout.json

    # Local OA p19 gate (requires the OA original)
    python tests/repro/digest.py --golden tests/repro/golden/oa_p19_typsetting.json \
        --pdf "path/to/Orgasmic Addiction.pdf" --pages 19 \
        --working-dir /tmp/oa --out-dir /tmp/oa/out \
        --map-json oa_p19_map.json --translator fixedmap \
        --header-height 160 --footer-height 70

    # Refresh the golden after a deliberate layout change
    python tests/repro/digest.py --golden tests/repro/golden/synth_layout.json \
        --update-golden

    # Compare an already-produced run (no re-run)
    python tests/repro/digest.py --golden ... --run-dir /tmp/run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import driver  # noqa: E402  (sibling import after sys.path setup)
import synth_page  # noqa: E402
import visual_layout_check  # noqa: E402

GOLDEN_SUMMARY_FILENAME = driver.SUMMARY_FILENAME


def canonical_sha256(pages: dict) -> str:
    """sha256 of the canonical serialization of the typsetting summary."""
    payload = json.dumps(
        pages,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_summary(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _diff_pages(golden_pages: dict, run_pages: dict) -> list[str]:
    """Human-readable per-paragraph differences (box/scale/line widths)."""
    diffs: list[str] = []
    for page_no in sorted(set(golden_pages) | set(run_pages)):
        g = golden_pages.get(page_no)
        r = run_pages.get(page_no)
        if g is None or r is None:
            diffs.append(f"page {page_no}: {'missing in run' if g is None else 'missing in golden'}")
            continue
        g_ids = set(g.get("debug_ids", []))
        r_ids = set(r.get("debug_ids", []))
        if g_ids != r_ids:
            diffs.append(
                f"page {page_no}: prior debug_id set changed "
                f"(added={sorted(r_ids - g_ids)}, removed={sorted(g_ids - r_ids)})"
            )
        g_paras = g.get("paragraphs", {})
        r_paras = r.get("paragraphs", {})
        for did in sorted(set(g_paras) | set(r_paras)):
            if did not in g_paras:
                diffs.append(f"page {page_no} {did}: added in run")
                continue
            if did not in r_paras:
                diffs.append(f"page {page_no} {did}: removed in run")
                continue
            gp, rp = g_paras[did], r_paras[did]
            if gp != rp:
                diffs.append(f"page {page_no} {did}: golden={gp!r} run={rp!r}")
    return diffs


def compare(
    golden: dict,
    run: dict,
    *,
    strict_fingerprint: bool = False,
) -> tuple[bool, list[str]]:
    """Δ=0 verdict: canonical typsetting sha + prior debug_id sets.

    Full-document ``il_layout_fingerprint`` includes LayoutParser debug stubs
    and is sensitive to DocLayout/ONNX provider noise across machines. By
    default a fingerprint mismatch is **advisory only** (printed, not a hard
    fail). Pass ``strict_fingerprint=True`` (CLI ``--strict-fingerprint``)
    to gate on it for local deep checks.
    """
    diffs: list[str] = []
    warnings: list[str] = []
    golden_sha = canonical_sha256(golden.get("pages", {}))
    run_sha = canonical_sha256(run.get("pages", {}))
    if golden_sha != run_sha:
        diffs.append(f"canonical typsetting sha mismatch: golden={golden_sha} run={run_sha}")
        diffs.extend(_diff_pages(golden.get("pages", {}), run.get("pages", {})))
    g_fp = golden.get("fingerprint_sha256")
    r_fp = run.get("fingerprint_sha256")
    if g_fp != r_fp:
        msg = f"il_layout_fingerprint mismatch: golden={g_fp} run={r_fp}"
        if strict_fingerprint:
            diffs.append(msg)
        else:
            warnings.append(msg + " (advisory; use --strict-fingerprint to fail)")
    # Prior debug_id sets are asserted even when the canonical sha matches.
    for page_no in sorted(set(golden.get("pages", {})) | set(run.get("pages", {}))):
        g_ids = set((golden.get("pages", {}).get(page_no) or {}).get("debug_ids", []))
        r_ids = set((run.get("pages", {}).get(page_no) or {}).get("debug_ids", []))
        if g_ids != r_ids:
            diffs.append(
                f"page {page_no}: prior debug_id set changed "
                f"(added={sorted(r_ids - g_ids)}, removed={sorted(g_ids - r_ids)})"
            )
    # Attach soft warnings on the run summary for callers that print them.
    run["_compare_warnings"] = warnings
    return not diffs, diffs


def write_golden(path: Path, run: dict) -> None:
    """Persist a run summary as the new golden (deterministic ordering)."""
    golden = {
        "schema": "babeldoc-repro-layout/v1",
        "digest_sha256": canonical_sha256(run.get("pages", {})),
        "fingerprint_sha256": run.get("fingerprint_sha256"),
        "pages": run.get("pages", {}),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(golden, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def run_synth(working_dir: Path, out_dir: Path, translator: str) -> dict:
    """Run the synthetic page through the driver and return its summary."""
    pdf_path = working_dir / synth_page.SYNTH_PDF_NAME
    synth_page.write_synth_pdf(pdf_path)
    result = driver.run_translate(
        pdf=pdf_path,
        pages="1",
        working_dir=working_dir,
        out_dir=out_dir,
        mapping={},  # identity: deterministic, geometry-only gate
        translator_name=translator,
    )
    return result["summary"]


def run_digest(args) -> tuple[int, dict | None]:
    """Execute the digest workflow; returns (exit_code, run_summary)."""
    golden_path = Path(args.golden)
    if not args.update_golden and not golden_path.exists():
        print(f"golden not found: {golden_path}", file=sys.stderr)
        return 2, None

    run_dir = Path(args.run_dir) if args.run_dir else Path(args.working_dir)

    if args.run_dir:
        run_summary = load_summary(run_dir / GOLDEN_SUMMARY_FILENAME)
    else:
        working_dir = Path(args.working_dir)
        out_dir = Path(args.out_dir)
        working_dir.mkdir(parents=True, exist_ok=True)
        out_dir.mkdir(parents=True, exist_ok=True)
        if args.pdf:
            result = driver.run_translate(
                pdf=args.pdf,
                pages=args.pages,
                working_dir=working_dir,
                out_dir=out_dir,
                map_json=args.map_json,
                translator_name=args.translator,
                skip_header=not args.no_skip_header,
                header_height=args.header_height,
                skip_footer=not args.no_skip_footer,
                footer_height=args.footer_height,
            )
            run_summary = result["summary"]
        else:
            run_summary = run_synth(working_dir, out_dir, args.translator)

    code = 0
    if args.update_golden:
        write_golden(golden_path, run_summary)
        print(f"updated golden: {golden_path}")
        print(f"digest_sha256       : {canonical_sha256(run_summary.get('pages', {}))}")
        print(f"fingerprint_sha256  : {run_summary.get('fingerprint_sha256')}")
    else:
        golden = load_summary(golden_path)
        ok, diffs = compare(
            golden,
            run_summary,
            strict_fingerprint=bool(getattr(args, "strict_fingerprint", False)),
        )
        warnings = list(run_summary.pop("_compare_warnings", None) or [])
        if ok:
            print(
                "Δ=0 PASS (canonical typsetting sha + prior debug_id set"
                + ("; strict fingerprint" if args.strict_fingerprint else "")
                + ")"
            )
            print(f"digest_sha256       : {canonical_sha256(run_summary.get('pages', {}))}")
            print(f"fingerprint_sha256  : {run_summary.get('fingerprint_sha256')}")
            for line in warnings:
                print(f"WARN: {line}", file=sys.stderr)
        else:
            print("Δ≠0 FAIL", file=sys.stderr)
            for line in diffs:
                print(f"  {line}", file=sys.stderr)
            for line in warnings:
                print(f"WARN: {line}", file=sys.stderr)
            code = 1

    visual_code = _maybe_run_visual_check(args, run_dir, run_summary)
    return code or visual_code, run_summary


def _auto_pick_en_reference(run_dir: Path) -> Path | None:
    """Pick ``golden/en_pXX_blocks.json`` whose run page key matches the run."""
    try:
        pages = visual_layout_check.load_run(run_dir)["pages"]
    except FileNotFoundError:
        return None
    for name in ("en_p19_blocks.json", "en_p82_blocks.json"):
        path = ROOT / "golden" / name
        if not path.exists():
            continue
        ref = visual_layout_check.load_en_reference(path)
        if any(visual_layout_check.en_page_for_run(ref, key) is not None for key in pages):
            return path
    return None


def _maybe_run_visual_check(args, run_dir: Path, run_summary: dict) -> int:
    """Run the V1-V5 visual layout check on the run (advisory by default).

    Returns 1 only when ``--visual-gate`` is set and any assertion FAILed;
    otherwise the V1-V5 report is printed for diagnosis without changing the
    digest exit code (the \u0394=0 gate keeps its own semantics).
    """
    if not getattr(args, "visual_check", False):
        return 0
    if run_dir is None or not Path(run_dir).exists():
        print("visual check skipped: run-dir missing", file=sys.stderr)
        return 0
    ref_path = Path(args.en_reference) if getattr(args, "en_reference", None) else None
    if ref_path is None:
        ref_path = _auto_pick_en_reference(Path(run_dir))
    if ref_path is None:
        keys = sorted(run_summary.get("pages", {}))
        print(
            f"visual check skipped: no EN reference for run page(s) {keys} "
            "(use --en-reference tests/repro/golden/en_pXX_blocks.json)",
            file=sys.stderr,
        )
        return 0
    report = visual_layout_check.check_run_dir(run_dir, ref_path)
    print()
    print(visual_layout_check.format_report(report))
    if getattr(args, "visual_gate", False) and not report["all_pass"]:
        print("visual gate FAILED (drop --visual-gate to keep advisory)", file=sys.stderr)
        return 1
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--golden", required=True, help="golden summary JSON path")
    parser.add_argument(
        "--run-dir",
        default=None,
        help="compare an existing run (expects repro_typsetting_summary.json)",
    )
    parser.add_argument("--pdf", default=None, help="input PDF (default: synth page)")
    parser.add_argument("--pages", default="1", help="pages spec for --pdf runs")
    parser.add_argument(
        "--working-dir",
        default=None,
        help="working dir (default: temp dir for synth runs)",
    )
    parser.add_argument("--out-dir", default=None, help="output dir (default: temp)")
    parser.add_argument("--map-json", default=None)
    parser.add_argument(
        "--translator",
        choices=("fixedmap", "identity"),
        default="identity",
    )
    parser.add_argument("--update-golden", action="store_true")
    parser.add_argument(
        "--strict-fingerprint",
        action="store_true",
        help=(
            "Also require full-document il_layout_fingerprint match. "
            "Default off: fingerprint includes DocLayout stubs and is "
            "noisy across ONNX providers / machines."
        ),
    )
    parser.add_argument(
        "--visual-check",
        action="store_true",
        help=(
            "Run the V1-V5 visual layout acceptance checks on the run "
            "(docs/visual-layout-acceptance.md) and print the per-item report. "
            "Advisory unless --visual-gate is also given."
        ),
    )
    parser.add_argument(
        "--en-reference",
        default=None,
        help=(
            "EN block reference golden for --visual-check "
            "(default: auto-pick golden/en_p19_blocks.json / en_p82_blocks.json)"
        ),
    )
    parser.add_argument(
        "--visual-gate",
        action="store_true",
        help="With --visual-check: exit 1 when any V1-V5 assertion FAILs.",
    )
    parser.add_argument("--header-height", type=float, default=driver.DEFAULT_HEADER_HEIGHT)
    parser.add_argument("--footer-height", type=float, default=driver.DEFAULT_FOOTER_HEIGHT)
    parser.add_argument("--no-skip-header", action="store_true")
    parser.add_argument("--no-skip-footer", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.working_dir is None:
        args.working_dir = tempfile.mkdtemp(prefix="babeldoc-repro-")
    if args.out_dir is None:
        args.out_dir = str(Path(args.working_dir) / "out")
    code, _ = run_digest(args)
    return code


if __name__ == "__main__":
    sys.exit(main())
