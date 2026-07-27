"""Subset BabelDOC embedding fonts only; leave publisher faces intact.

MuPDF ``Document.subset_fonts`` rewrites every eligible embedded face. That
corrupts original fonts still required by:

* pages outside ``--pages`` (cover when ``2-``)
* untranslated header/footer under ``q … Q`` base streams
* figure / callout labels left in the source language

Strategy: detach non-embedding FontFile* (save **decompressed** programs),
run subset, restore with a single compress pass.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from babeldoc.assets.embedding_assets_metadata import EMBEDDING_FONT_METADATA
from babeldoc.assets.embedding_assets_metadata import FONT_NAMES

logger = logging.getLogger(__name__)

_PDF_NAME_HEX_RE = re.compile(r"#([0-9A-Fa-f]{2})")
_FONT_FILE_KEYS = ("FontFile", "FontFile2", "FontFile3")
_VERSION_SUFFIX_RE = re.compile(r"\.\d+.*$")


def pdf_name_decode(name: str | None) -> str:
    """Decode PDF name escapes (``#20`` → space) and strip leading ``/``."""
    if not name:
        return ""
    s = name[1:] if name.startswith("/") else name
    return _PDF_NAME_HEX_RE.sub(lambda m: chr(int(m.group(1), 16)), s)


def norm_font_token(name: str | None) -> str:
    """Normalize font labels for exact embedding-font matching."""
    s = pdf_name_decode(name)
    # Drop PDF subset tag prefix ``ABCDEF+Ubuntu-Light`` → ``Ubuntu-Light``
    if "+" in s:
        s = s.split("+", 1)[1]
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _embedding_font_tokens() -> frozenset[str]:
    """Exact normalized tokens for BabelDOC-injected faces only."""
    toks: set[str] = set()
    for n in FONT_NAMES:
        t = norm_font_token(n)
        if t:
            toks.add(t)
    for file_name, meta in EMBEDDING_FONT_METADATA.items():
        stem = Path(file_name).stem
        # ``LXGWWenKaiGB-Regular.1.520`` → also without version suffix
        for candidate in (
            stem,
            _VERSION_SUFFIX_RE.sub("", stem),
            meta.get("font_name") or "",
        ):
            t = norm_font_token(candidate)
            if t:
                toks.add(t)
    return frozenset(toks)


_EMBEDDING_FONT_TOKENS = _embedding_font_tokens()


def is_babeldoc_embedding_font_name(name: str | None) -> bool:
    """True when ``name`` is a BabelDOC embedding face (Source Han / LXGW / Noto…).

    Matching is **exact** on normalized tokens (no bidirectional substring), so
    publisher faces like ``Ubuntu-Light`` / ``TrajanPro`` never match.
    """
    token = norm_font_token(name)
    if not token or len(token) < 4:
        return False
    return token in _EMBEDDING_FONT_TOKENS


@dataclass(frozen=True, slots=True)
class FontStreamBackup:
    """Detached publisher FontFile* program for restore after subset."""

    descriptor_xref: int
    key: str  # FontFile / FontFile2 / FontFile3
    file_xref: int
    data: bytes  # decompressed font program
    length1: int | None
    subtype: str | None
    label: str


def _font_descriptor_label(doc: pymupdf.Document, desc_xref: int) -> str:
    for key in ("FontName", "FontFamily", "BaseFont"):
        v = doc.xref_get_key(desc_xref, key)
        if v[0] != "null" and v[1]:
            return pdf_name_decode(v[1])
    return ""


def iter_font_file_links(
    doc: pymupdf.Document,
) -> list[tuple[int, str, int, bool, str]]:
    """List ``(descriptor_xref, key, file_xref, is_embedding, label)``."""
    found: list[tuple[int, str, int, bool, str]] = []
    for xref in range(1, doc.xref_length()):
        for key in _FONT_FILE_KEYS:
            k = doc.xref_get_key(xref, key)
            if k[0] != "xref":
                continue
            m = re.search(r"(\d+)\s+0\s+R", k[1] or "")
            if not m:
                continue
            file_xref = int(m.group(1))
            label = _font_descriptor_label(doc, xref)
            found.append(
                (xref, key, file_xref, is_babeldoc_embedding_font_name(label), label)
            )
    return found


def protect_non_embedding_font_files(doc: pymupdf.Document) -> list[FontStreamBackup]:
    """Detach original FontFile* streams so ``subset_fonts`` cannot rewrite them."""
    protected: list[FontStreamBackup] = []
    for desc_xref, key, file_xref, is_emb, label in iter_font_file_links(doc):
        if is_emb:
            continue
        try:
            data = doc.xref_stream(file_xref)
        except Exception as e:
            logger.debug(
                "Skip protecting font stream xref=%s (%s): %s", file_xref, label, e
            )
            continue
        if not data:
            continue
        length1: int | None = None
        subtype: str | None = None
        try:
            l1 = doc.xref_get_key(file_xref, "Length1")
            if l1[0] != "null" and l1[1]:
                length1 = int(str(l1[1]).strip())
        except Exception:
            length1 = None
        try:
            st = doc.xref_get_key(file_xref, "Subtype")
            if st[0] != "null" and st[1]:
                subtype = str(st[1]).strip()
        except Exception:
            subtype = None
        protected.append(
            FontStreamBackup(
                descriptor_xref=desc_xref,
                key=key,
                file_xref=file_xref,
                data=data,
                length1=length1,
                subtype=subtype,
                label=label,
            )
        )
        doc.xref_set_key(desc_xref, key, "null")
    if protected:
        logger.info(
            "Font subset protect: detached %d original font stream(s) "
            "(headers/footers/figures/skipped pages)",
            len(protected),
        )
    return protected


def restore_non_embedding_font_files(
    doc: pymupdf.Document,
    protected: list[FontStreamBackup],
) -> None:
    """Re-attach original FontFile* streams after subsetting embedding fonts."""
    restored = 0
    for bak in protected:
        try:
            doc.update_stream(bak.file_xref, bak.data)
            if bak.length1 is not None:
                doc.xref_set_key(bak.file_xref, "Length1", str(bak.length1))
            if bak.subtype:
                subtype = bak.subtype
                if not subtype.startswith("/"):
                    subtype = "/" + subtype.lstrip("/")
                doc.xref_set_key(bak.file_xref, "Subtype", subtype)
            doc.xref_set_key(
                bak.descriptor_xref, bak.key, f"{bak.file_xref} 0 R"
            )
            restored += 1
        except Exception as e:
            logger.warning(
                "Failed to restore original font stream xref=%s (%s): %s",
                bak.file_xref,
                bak.label,
                e,
            )
    if restored:
        logger.info(
            "Font subset protect: restored %d original font stream(s)", restored
        )


def subset_embedding_fonts_and_save(
    pdf: pymupdf.Document, output_path: str | Path
) -> None:
    """Subset embedding fonts only, restore publisher faces, write compact PDF."""
    protected = protect_non_embedding_font_files(pdf)
    try:
        try:
            pdf.subset_fonts(fallback=False)
        except Exception as e:
            logger.warning(
                "subset_fonts(fallback=False) failed (%s); retry fallback=True", e
            )
            pdf.subset_fonts(fallback=True)
    finally:
        restore_non_embedding_font_files(pdf, protected)
    pdf.save(
        str(output_path),
        garbage=4,
        deflate=True,
        deflate_fonts=True,
        clean=True,
    )
