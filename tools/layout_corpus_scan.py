"""Read-only Gabrielle Moore corpus scan.

Writes a manifest, one JSON object per page, and an aggregate summary.
Does not translate, render, or modify PDFs. Absolute paths stay out of
the output.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from babeldoc.format.pdf.document_il.utils.layout_plan.corpus import EXPECTED_PDF_COUNT
from babeldoc.format.pdf.document_il.utils.layout_plan.corpus import (
    EXPECTED_TOP_LEVEL_DIRECTORIES,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.corpus import build_manifest
from babeldoc.format.pdf.document_il.utils.layout_plan.corpus import count_errors
from babeldoc.format.pdf.document_il.utils.layout_plan.corpus import load_lock
from babeldoc.format.pdf.document_il.utils.layout_plan.corpus import lock_errors
from babeldoc.format.pdf.document_il.utils.layout_plan.pdf_scan import scan_pdf


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--lock", type=Path, default=None)
    parser.add_argument("--write-lock", action="store_true")
    parser.add_argument(
        "--manifest-only",
        action="store_true",
        help="Hash the corpus and check counts, then stop.",
    )
    args = parser.parse_args(argv)
    root = args.root.expanduser().resolve()
    if not root.is_dir():
        print(f"corpus root is not a directory: {root}", file=sys.stderr)
        return 2
    manifest = build_manifest(root)
    errors = count_errors(manifest)
    if args.lock is not None and args.lock.is_file() and not args.write_lock:
        errors.extend(lock_errors(manifest, load_lock(args.lock)))
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if args.write_lock:
        if args.lock is None:
            print("--write-lock needs --lock", file=sys.stderr)
            return 2
        args.lock.parent.mkdir(parents=True, exist_ok=True)
        args.lock.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 2
    print(
        f"manifest ok pdfs={EXPECTED_PDF_COUNT} "
        f"top_dirs={EXPECTED_TOP_LEVEL_DIRECTORIES}"
    )
    if args.manifest_only:
        return 0
    summary = _scan_pages(root, manifest, args.out / "pages.jsonl")
    (args.out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        "pages={page_count} regions={region_count} "
        "strategies={by_strategy} gates={by_gate} conflicts={conflicts}".format(
            **summary
        )
    )
    return 0


def _scan_pages(root: Path, manifest: dict, jsonl_path: Path) -> dict:
    strategies: Counter[str] = Counter()
    gates: Counter[str] = Counter()
    books: dict[str, Counter[str]] = {}
    conflicts = 0
    regions = 0
    pages = 0
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for row in manifest["files"]:
            rel = row["path"]
            book = rel.split("/", 1)[0]
            try:
                records = scan_pdf(root / rel, row["sha256"])
            except Exception as exc:
                record = {
                    "source_fingerprint": row["sha256"],
                    "relpath": rel,
                    "book": book,
                    "page_index": None,
                    "input_gate": "unsupported",
                    "error": type(exc).__name__,
                    "regions": [],
                    "decisions": [],
                }
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                gates["unsupported"] += 1
                continue
            for record in records:
                record["relpath"] = rel
                record["book"] = book
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                pages += 1
                gates[record["input_gate"]] += 1
                book_counter = books.setdefault(book, Counter())
                for decision in record["decisions"]:
                    regions += 1
                    strategies[decision["base_strategy"]] += 1
                    book_counter[decision["base_strategy"]] += 1
                    if any(
                        item["reason"] == "conflict_tie"
                        for item in decision["rejected"]
                    ):
                        conflicts += 1
    return {
        "pdf_count": manifest["pdf_count"],
        "top_level_directory_count": manifest["top_level_directory_count"],
        "page_count": pages,
        "region_count": regions,
        "by_strategy": dict(strategies),
        "by_gate": dict(gates),
        "conflicts": conflicts,
        "by_book": {name: dict(counter) for name, counter in sorted(books.items())},
    }


if __name__ == "__main__":
    raise SystemExit(main())
