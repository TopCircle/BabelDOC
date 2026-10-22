"""Read-only corpus manifest. Counts are the checked baseline."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

EXPECTED_PDF_COUNT = 131
EXPECTED_TOP_LEVEL_DIRECTORIES = 101


def is_derived_translation(path: Path) -> bool:
    """True for a generated or hand-revised translation, not a source PDF.

    The check is the filename only. ``.zh`` covers ``.zh.pdf`` and
    ``.zh-CN``. ``no_watermark`` covers duals and monos already translated.
    """
    name = path.name.lower()
    return ".zh" in name or "no_watermark" in name


def list_pdfs(root: Path) -> list[Path]:
    """Recursive source PDF list. Directory symlinks are not followed."""
    found: list[Path] = []
    for dirpath, dirnames, filenames in root.walk(follow_symlinks=False):
        dirnames[:] = [name for name in dirnames if not name.startswith(".")]
        for name in filenames:
            path = dirpath / name
            if name.lower().endswith(".pdf") and not is_derived_translation(path):
                found.append(path)
    found.sort(key=lambda path: path.relative_to(root).as_posix())
    return found


def top_level_directories(root: Path) -> list[str]:
    names = [
        path.name
        for path in root.iterdir()
        if path.is_dir() and not path.name.startswith(".") and not path.is_symlink()
    ]
    names.sort()
    return names


def file_fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(root: Path) -> dict:
    """Relative paths and content hashes. No absolute machine path."""
    files = []
    for path in list_pdfs(root):
        files.append(
            {
                "path": path.relative_to(root).as_posix(),
                "sha256": file_fingerprint(path),
                "bytes": path.stat().st_size,
            }
        )
    return {
        "pdf_count": len(files),
        "top_level_directory_count": len(top_level_directories(root)),
        "files": files,
    }


def count_errors(manifest: dict) -> list[str]:
    errors = []
    if manifest.get("pdf_count") != EXPECTED_PDF_COUNT:
        errors.append(
            f"pdf_count {manifest.get('pdf_count')} != {EXPECTED_PDF_COUNT}"
        )
    top = manifest.get("top_level_directory_count")
    if top != EXPECTED_TOP_LEVEL_DIRECTORIES:
        errors.append(
            f"top_level_directory_count {top} != {EXPECTED_TOP_LEVEL_DIRECTORIES}"
        )
    files = manifest.get("files") or []
    if len(files) != manifest.get("pdf_count"):
        errors.append("file list length does not match pdf_count")
    return errors


def lock_errors(manifest: dict, lock: dict) -> list[str]:
    """Diff two manifests. Paths are corpus-relative.

    Expected totals are reported by ``count_errors``. This only reports
    drift between the live walk and the lock file.
    """
    errors = []
    if manifest.get("pdf_count") != lock.get("pdf_count"):
        errors.append("manifest pdf_count differs from lock")
    if manifest.get("top_level_directory_count") != lock.get(
        "top_level_directory_count"
    ):
        errors.append("manifest directory count differs from lock")
    current = {_row_key(row): row.get("sha256") for row in manifest.get("files") or []}
    locked = {_row_key(row): row.get("sha256") for row in lock.get("files") or []}
    for path in sorted(set(current) - set(locked)):
        errors.append(f"added {path}")
    for path in sorted(set(locked) - set(current)):
        errors.append(f"removed {path}")
    for path in sorted(set(current) & set(locked)):
        if current[path] != locked[path]:
            errors.append(f"changed {path}")
    return errors


def load_lock(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _row_key(row: dict) -> str:
    return str(row.get("path") or "")
