"""Regression tests for upstream v0.7.1 merge, version 0.7.1.0, and GHSA parser limits."""

from __future__ import annotations

import io
import pickle
import zlib
from pathlib import Path
from unittest.mock import MagicMock

import babeldoc
import pytest
import tomllib
from babeldoc.const import __version__ as const_version
from babeldoc.format.pdf.babelpdf.cmap import CharacterMap
from babeldoc.format.pdf.document_il.backend.pdf_creater import BitStream
from babeldoc.format.pdf.new_parser.runtime.cmap_types_runtime import UnicodeMap
from babeldoc.format.pdf.new_parser.runtime.to_unicode_parser_runtime import (
    parse_tounicode_stream,
)
from babeldoc.format.pdf.parser_resource import ParserResourceLimitError
from babeldoc.format.pdf.parser_resource import parser_resource_limits_context
from babeldoc.format.pdf.translation_config import SharedContextCrossSplitPart
from babeldoc.format.pdf.translation_config import TranslationConfig
from babeldoc.glossary import Glossary
from babeldoc.glossary import GlossaryEntry
from babeldoc.pdfminer.cmapdb import CMapParser
from babeldoc.pdfminer.cmapdb import UnicodeMap as LegacyUnicodeMap
from babeldoc.pdfminer.pdftypes import PDFStream
from babeldoc.pdfminer.psparser import LIT

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_version_and_pyproject_manifest_v0710():
    assert babeldoc.__version__ == "0.7.1.0"
    assert const_version == "0.7.1.0"

    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["version"] == "0.7.1.0"
    assert pyproject["bumpver"]["current_version"] == "0.7.1.0"
    assert pyproject["build-system"]["build-backend"] == "hatchling.build"

    deps = pyproject["project"]["dependencies"]
    assert not any(dep.startswith("bitstring") for dep in deps)
    assert "pymupdf>=1.26.7,<2" in deps


def test_translation_config_allows_none_input_file_v071_regression():
    cfg = TranslationConfig(
        translator=None,
        input_file=None,
        lang_in="en",
        lang_out="zh-CN",
        doc_layout_model=MagicMock(),
        auto_extract_glossary=False,
    )
    try:
        assert cfg._capture_document_name is None
        assert cfg.disable_parser_resource_limits is False
        cfg.capture_stages = True
        capture_path = cfg.get_stage_capture_file_path("parser")
        assert capture_path is not None
        assert capture_path.name == "parser.json.zst"
    finally:
        cfg.cleanup_temp_files()


def test_disable_parser_resource_limits_requires_strict_bool():
    with pytest.raises(TypeError, match="disable_parser_resource_limits must be a bool"):
        TranslationConfig(
            translator=None,
            input_file=None,
            lang_in="en",
            lang_out="zh-CN",
            doc_layout_model=MagicMock(),
            disable_parser_resource_limits=1,  # type: ignore[arg-type]
        )


def test_parser_resource_limit_error_pickle_roundtrip():
    err = ParserResourceLimitError(
        "limit exceeded",
        limit_name="max_decompressed_stream_bytes",
        limit=1024,
        observed_or_requested=2048,
        unit="bytes",
        scope="stream",
        phase="stream_decode",
        page=0,
        object_ref=(7, 0),
        policy_version=1,
    )
    restored = pickle.loads(pickle.dumps(err))  # noqa: S301
    assert isinstance(restored, ParserResourceLimitError)
    assert str(restored) == "limit exceeded"
    assert restored.limit_name == "max_decompressed_stream_bytes"
    assert restored.object_ref == (7, 0)


def test_flate_decompression_bomb_rejected_and_toggleable(monkeypatch):
    monkeypatch.setattr(
        "babeldoc.format.pdf.parser_resource.DEFAULT_MAX_DECOMPRESSED_STREAM_BYTES",
        1024 * 1024,  # 1 MiB cap for fast test
    )
    payload = zlib.compress(b"\x00" * (2 * 1024 * 1024), level=9)
    stream = PDFStream(attrs={"Filter": LIT("FlateDecode")}, rawdata=payload)
    stream.set_objid(12, 0)

    with pytest.raises(ParserResourceLimitError) as exc_info:
        stream.decode()
    assert exc_info.value.limit_name == "max_decompressed_stream_bytes"
    assert exc_info.value.object_ref == (12, 0)

    stream_allowed = PDFStream(attrs={"Filter": LIT("FlateDecode")}, rawdata=payload)
    with parser_resource_limits_context(disabled=True):
        stream_allowed.decode()
    assert stream_allowed.data is not None
    assert len(stream_allowed.data) == 2 * 1024 * 1024


def test_tounicode_bfrange_and_cidrange_amplification_rejected():
    malicious_tounicode = (
        b"/CIDInit /ProcSet findresource begin 12 dict begin begincmap "
        b"1 beginbfrange <00000000> <00FFFFFF> <0041> endbfrange endcmap"
    )
    with pytest.raises(ParserResourceLimitError) as exc_new:
        parse_tounicode_stream(malicious_tounicode, UnicodeMap())
    assert exc_new.value.limit_name == "max_cmap_range_entries"

    with pytest.raises(ParserResourceLimitError) as exc_legacy:
        CMapParser(LegacyUnicodeMap(), io.BytesIO(malicious_tounicode)).run()
    assert exc_legacy.value.limit_name == "max_cmap_range_entries"

    malicious_cidrange = (
        "begincmap\n1 begincidrange\n<00000000> <00FFFFFF> 1\nendcidrange\nendcmap\n"
    )
    with pytest.raises(ParserResourceLimitError) as exc_babelpdf:
        CharacterMap(malicious_cidrange)
    assert exc_babelpdf.value.limit_name == "max_cmap_range_entries"


def test_auto_extracted_glossary_source_spelling_votes_and_tiebreak():
    entries = [
        GlossaryEntry("Neural Net", "神经网络"),
        GlossaryEntry("neural net", "神经网络"),
        GlossaryEntry("neural net", "神经网络"),
    ]
    g = Glossary.from_auto_extracted_entries("auto", entries)
    assert len(g.entries) == 1
    assert g.entries[0].source == "neural net"

    sc = SharedContextCrossSplitPart()
    sc.initialize_glossaries([])
    sc.add_raw_extracted_term_pair("Alpha", "乙")
    sc.add_raw_extracted_term_pair("Alpha", "甲")
    sc.finalize_auto_extracted_glossary()
    assert sc.auto_extracted_glossary is not None
    assert sc.auto_extracted_glossary.entries[0].target == "乙" if "乙" < "甲" else "甲"


def test_lightweight_bitstream_replacement():
    s1 = BitStream(b"q ")
    s2 = BitStream(b"1 0 0 1 0 0 cm ")
    s1.append(s2)
    s1.append(b"Q\n")
    expected = b"q 1 0 0 1 0 0 cm Q\n"
    assert s1.tobytes() == expected
    assert s1.bytes == expected
    assert len(s1) == len(expected)
