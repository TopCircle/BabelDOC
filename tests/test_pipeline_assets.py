"""Offline font, CMap, and tokenizer prepare/check contract."""

from __future__ import annotations

import hashlib
from pathlib import Path

import babeldoc.assets.assets as asset_download
import babeldoc.const as const
import pipeline_assets
import pytest
from babeldoc.assets.embedding_assets_metadata import CMAP_METADATA
from babeldoc.assets.embedding_assets_metadata import EMBEDDING_FONT_METADATA
from babeldoc.assets.embedding_assets_metadata import TIKTOKEN_CACHES
from babeldoc.assets.embedding_assets_metadata import get_font_family
from babeldoc.docvision.base_doclayout import DocLayoutModel

PAYLOAD = b"fixture-ok"
PAYLOAD_SHA3 = hashlib.sha3_256(PAYLOAD).hexdigest()
ONNX_NAME = "doclayout_yolo_docstructbench_imgsz1024.onnx"
FONT_ROLES = ("normal", "script", "fallback", "base")


def _published_font_names() -> list[str]:
    family = get_font_family("zh-CN")
    names: list[str] = []
    seen: set[str] = set()
    for role in FONT_ROLES:
        for name in family[role]:
            if name in seen:
                continue
            seen.add(name)
            names.append(name)
    return names


def _assert_published_manifest(manifest: dict[str, list[dict[str, str]]]) -> None:
    assert set(manifest) == {"fonts", "cmap", "tiktoken"}
    blob = str(manifest)
    assert ONNX_NAME not in blob
    assert "models/" not in blob
    fonts = manifest["fonts"]
    assert [item["name"] for item in fonts] == _published_font_names()
    for item in fonts:
        assert item["path"] == f"fonts/{item['name']}"
        assert item["sha3_256"] == EMBEDDING_FONT_METADATA[item["name"]]["sha3_256"]
        assert item["name"] != ONNX_NAME
    assert [item["name"] for item in manifest["cmap"]] == list(CMAP_METADATA)
    for item in manifest["cmap"]:
        assert item["path"] == f"cmap/{item['name']}"
        assert item["sha3_256"] == CMAP_METADATA[item["name"]]["sha3_256"]
    assert [item["name"] for item in manifest["tiktoken"]] == list(TIKTOKEN_CACHES)
    for item in manifest["tiktoken"]:
        assert item["path"] == f"tiktoken/{item['name']}"
        assert item["sha3_256"] == TIKTOKEN_CACHES[item["name"]]


def _use_cache(monkeypatch: pytest.MonkeyPatch, cache: Path) -> None:
    monkeypatch.setattr(const, "CACHE_FOLDER", cache)


def _stand_in_digests(monkeypatch: pytest.MonkeyPatch) -> None:
    for meta in EMBEDDING_FONT_METADATA.values():
        monkeypatch.setitem(meta, "sha3_256", PAYLOAD_SHA3)
    for meta in CMAP_METADATA.values():
        monkeypatch.setitem(meta, "sha3_256", PAYLOAD_SHA3)
    for name in list(TIKTOKEN_CACHES):
        monkeypatch.setitem(TIKTOKEN_CACHES, name, PAYLOAD_SHA3)


def _install_fake_downloader(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    calls: list[tuple[str, str]] = []

    def fake(kind: str, name: str) -> None:
        calls.append((kind, name))
        manifest = pipeline_assets.required_assets()
        item = next(entry for entry in manifest[kind] if entry["name"] == name)
        path = Path(const.CACHE_FOLDER) / item["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(PAYLOAD)

    monkeypatch.setattr(pipeline_assets, "download_missing", fake)
    return calls


def _install_tokenizer(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    seen: list[str] = []

    def encoding_for_model(model: str):
        seen.append(model)
        return object()

    monkeypatch.setattr("tiktoken.encoding_for_model", encoding_for_model)
    return seen


def _forbid_onnx(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    called: list[str] = []

    def boom(name: str):
        def _boom(*_args, **_kwargs):
            called.append(name)
            raise AssertionError(f"{name} must not run during asset prepare")

        return _boom

    monkeypatch.setattr(DocLayoutModel, "load_available", boom("load_available"))
    monkeypatch.setattr(DocLayoutModel, "load_onnx", boom("load_onnx"))
    monkeypatch.setattr(
        asset_download,
        "get_doclayout_onnx_model_path",
        boom("get_doclayout_onnx_model_path"),
    )
    monkeypatch.setattr(
        asset_download,
        "get_doclayout_onnx_model_path_async",
        boom("get_doclayout_onnx_model_path_async"),
    )
    monkeypatch.setattr(asset_download, "async_warmup", boom("async_warmup"))
    return called


def test_cold_cache_prepare_then_check(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _assert_published_manifest(pipeline_assets.required_assets())
    cache = tmp_path / "cache"
    _use_cache(monkeypatch, cache)
    _stand_in_digests(monkeypatch)
    downloads = _install_fake_downloader(monkeypatch)
    tokenizers = _install_tokenizer(monkeypatch)
    onnx_calls = _forbid_onnx(monkeypatch)

    assert pipeline_assets.main(["--prepare"]) == 0
    assert pipeline_assets.check_assets() == []
    kinds = {kind for kind, _name in downloads}
    assert kinds == {"fonts", "cmap", "tiktoken"}
    manifest = pipeline_assets.required_assets()
    expected_calls = [
        (kind, item["name"])
        for kind in ("fonts", "cmap", "tiktoken")
        for item in manifest[kind]
    ]
    assert downloads == expected_calls
    assert tokenizers
    assert set(tokenizers) == {"gpt-4o"}
    assert onnx_calls == []

    downloads.clear()
    assert pipeline_assets.main(["--prepare"]) == 0
    assert downloads == []
    assert pipeline_assets.check_assets() == []


def test_check_is_read_only_and_reports_missing_or_corrupt_asset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    absent = tmp_path / "absent"
    _use_cache(monkeypatch, absent)
    _assert_published_manifest(pipeline_assets.required_assets())
    missing = pipeline_assets.check_assets()
    manifest = pipeline_assets.required_assets()
    expected_names = [
        item["name"]
        for kind in ("fonts", "cmap", "tiktoken")
        for item in manifest[kind]
    ]
    assert missing == expected_names
    assert not absent.exists()

    cache = tmp_path / "cache"
    _use_cache(monkeypatch, cache)
    _stand_in_digests(monkeypatch)
    downloads = _install_fake_downloader(monkeypatch)
    _install_tokenizer(monkeypatch)
    assert pipeline_assets.main(["--prepare"]) == 0
    assert pipeline_assets.check_assets() == []

    manifest = pipeline_assets.required_assets()
    deleted = manifest["fonts"][0]
    corrupted = manifest["cmap"][0]
    deleted_path = cache / deleted["path"]
    corrupted_path = cache / corrupted["path"]
    deleted_path.unlink()
    corrupted_path.write_bytes(b"corrupt")
    downloads.clear()

    found = pipeline_assets.check_assets()
    assert deleted["name"] in found
    assert corrupted["name"] in found
    assert downloads == []
    assert not deleted_path.exists()
    assert corrupted_path.read_bytes() == b"corrupt"

    assert pipeline_assets.main(["--check"]) == 1
    printed = capsys.readouterr().out.split()
    assert deleted["name"] in printed
    assert corrupted["name"] in printed
    assert downloads == []


def test_prepare_does_not_load_onnx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    cache = tmp_path / "cache"
    _use_cache(monkeypatch, cache)
    _stand_in_digests(monkeypatch)
    _install_fake_downloader(monkeypatch)
    tokenizers = _install_tokenizer(monkeypatch)
    onnx_calls = _forbid_onnx(monkeypatch)

    pipeline_assets.prepare_assets()

    assert onnx_calls == []
    assert tokenizers
    assert set(tokenizers) == {"gpt-4o"}
    assert pipeline_assets.check_assets() == []
    manifest = pipeline_assets.required_assets()
    blob = str(manifest)
    assert ONNX_NAME not in blob
