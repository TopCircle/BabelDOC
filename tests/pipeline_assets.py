"""Read-only check and bounded prepare for font, CMap, and tokenizer assets.

Hashes come only from ``embedding_assets_metadata``. ``--prepare`` must not
call ``async_warmup`` or load a layout ONNX model. ``--check`` never downloads
and never creates cache directories.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import babeldoc.const as const
from babeldoc.assets.embedding_assets_metadata import CMAP_METADATA
from babeldoc.assets.embedding_assets_metadata import EMBEDDING_FONT_METADATA
from babeldoc.assets.embedding_assets_metadata import TIKTOKEN_CACHES
from babeldoc.assets.embedding_assets_metadata import get_font_family

_FONT_ROLES = ("normal", "script", "fallback", "base")
_KINDS = ("fonts", "cmap", "tiktoken")


def _cache_path(relative: str) -> Path:
    return Path(const.CACHE_FOLDER) / relative


def _sha3_matches(path: Path, digest: str) -> bool:
    if not path.is_file():
        return False
    hasher = hashlib.sha3_256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest() == digest


def required_assets() -> dict[str, list[dict[str, str]]]:
    """Cache-relative font, CMap, and tokenizer files for zh-CN delivery."""
    fonts: list[dict[str, str]] = []
    seen: set[str] = set()
    family = get_font_family("zh-CN")
    for role in _FONT_ROLES:
        for name in family[role]:
            if name in seen:
                continue
            seen.add(name)
            fonts.append(
                {
                    "path": f"fonts/{name}",
                    "sha3_256": EMBEDDING_FONT_METADATA[name]["sha3_256"],
                    "name": name,
                }
            )
    cmaps = [
        {
            "path": f"cmap/{name}",
            "sha3_256": meta["sha3_256"],
            "name": name,
        }
        for name, meta in CMAP_METADATA.items()
    ]
    tokenizers = [
        {
            "path": f"tiktoken/{name}",
            "sha3_256": digest,
            "name": name,
        }
        for name, digest in TIKTOKEN_CACHES.items()
    ]
    return {"fonts": fonts, "cmap": cmaps, "tiktoken": tokenizers}


def check_assets() -> list[str]:
    """Return names that are missing or whose sha3_256 does not match."""
    missing: list[str] = []
    for kind in _KINDS:
        for item in required_assets()[kind]:
            path = _cache_path(item["path"])
            if not _sha3_matches(path, item["sha3_256"]):
                missing.append(item["name"])
    return missing


def _preload_tokenizer() -> None:
    from tiktoken import encoding_for_model

    encoding_for_model("gpt-4o")


def download_missing(kind: str, name: str) -> None:
    """Fill one manifest miss from the existing font, CMap, or tokenizer source."""
    if kind == "fonts":
        from babeldoc.assets.assets import get_font_and_metadata

        get_font_and_metadata(name)
        return
    if kind == "cmap":
        from babeldoc.assets.assets import get_cmap_file_path

        get_cmap_file_path(name)
        return
    if kind == "tiktoken":
        _preload_tokenizer()
        return
    raise RuntimeError(f"unknown asset kind: {kind}")


def prepare_assets() -> None:
    """Verify hits and download only font, CMap, or tokenizer misses."""
    manifest = required_assets()
    for kind in _KINDS:
        for item in manifest[kind]:
            path = _cache_path(item["path"])
            if _sha3_matches(path, item["sha3_256"]):
                continue
            download_missing(kind, item["name"])
    problems: list[str] = []
    for kind in _KINDS:
        for item in manifest[kind]:
            path = _cache_path(item["path"])
            if not _sha3_matches(path, item["sha3_256"]):
                problems.append(item["name"])
    if problems:
        raise RuntimeError(
            "asset prepare left missing or corrupt files: " + ", ".join(problems)
        )
    _preload_tokenizer()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--prepare", action="store_true")
    group.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if args.prepare:
        prepare_assets()
        return 0
    missing = check_assets()
    for name in missing:
        print(name)
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
