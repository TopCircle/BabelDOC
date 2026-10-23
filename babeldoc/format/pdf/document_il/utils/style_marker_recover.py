"""Style-marker helpers for non-LLM (DeepLX) rich text.

* :func:`coalesce_emphasis_style_run` — merge line-broken italic/bold runs
  before embedding ``〖Bn〗`` (book titles split across compositions).
* :func:`rewrap_styles_from_source` — re-insert dropped markers after MT
  when the source term still appears (any casing).

Composition assembly stays in ``il_translator``.
"""

from __future__ import annotations

import logging
import re
from typing import NamedTuple

from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraphComposition
from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
from babeldoc.format.pdf.document_il.utils.layout_helper import is_same_style
from babeldoc.format.pdf.document_il.utils.layout_helper import (
    is_same_style_except_size,
)

logger = logging.getLogger(__name__)

MARKER_PAIR_RE = re.compile(r"〖[Bb](\d+)〗([\s\S]*?)〖/[Bb]\1〗")
# Single Latin token (no spaces)
_LATIN_TOKEN_RE = re.compile(r"^[A-Za-z][A-Za-z0-9'’\-]*$")
# A short lead-in such as "Vulva:" — the whole span, not a sentence.
_LABEL_RE = re.compile(r"^[^:：\n]{1,40}[:：]\s*$")
# Opening name after an optional formula token. Stops at the first colon.
_LEADING_LABEL_RE = re.compile(
    r"^(?:\{v\d+\})?\s*([^：:\n。.]{1,20})([：:])"
)


class StyleSpan(NamedTuple):
    """One emphasis span embedded as 〖Bid〗…〖/Bid〗 before MT."""

    span_id: int
    style: PdfStyle
    source_text: str


def coalesce_emphasis_style_run(
    compositions: list[PdfParagraphComposition],
    start: int,
    base_style: PdfStyle | None,
) -> tuple[list, PdfStyle, int]:
    """Merge adjacent same-style emphasis compositions starting at *start*.

    Used for non-LLM marker wrap so line-broken italic titles
    (``The `` + ``Passion Prescription``) become one ``〖Bn〗`` span.

    Returns:
        ``(chars, style, next_index)`` — *next_index* is the first composition
        not consumed (always ``> start``).
    """
    if start < 0 or start >= len(compositions):
        return [], base_style, start  # type: ignore[return-value]
    comp = compositions[start]
    if not comp.pdf_same_style_characters:
        return [], base_style, start + 1  # type: ignore[return-value]

    style = comp.pdf_same_style_characters.pdf_style
    chars = list(comp.pdf_same_style_characters.pdf_character or [])
    j = start + 1
    while j < len(compositions):
        nxt = compositions[j]
        if not nxt.pdf_same_style_characters:
            break
        ns = nxt.pdf_same_style_characters.pdf_style
        if not (
            is_same_style(ns, style) or is_same_style_except_size(ns, style)
        ):
            break
        # Stop at body-style runs
        if base_style is not None and (
            is_same_style(ns, base_style)
            or is_same_style_except_size(ns, base_style)
        ):
            break
        chars.extend(nxt.pdf_same_style_characters.pdf_character or [])
        j += 1
    return chars, style, j


def rewrap_styles_from_source(
    output: str,
    spans: list[StyleSpan] | list[tuple],
) -> str | None:
    """Re-insert missing 〖Bn〗 pairs using pre-MT source text.

    * Complete pairs already in *output* are left alone (those span_ids skip).
    * Missing span_ids are matched case-insensitively against *source_text*
      outside occupied ranges (longest source first).
    * Returns a new string if any wrap was added; otherwise ``None``.
    """
    if not output or not spans:
        return None

    normalized = _normalize_spans(spans)
    if not normalized:
        return None

    occupied: list[tuple[int, int]] = []
    present_ids: set[int] = set()
    for m in MARKER_PAIR_RE.finditer(output):
        present_ids.add(int(m.group(1)))
        occupied.append((m.start(), m.end()))

    # Longest source first so multi-word beats nested singles
    ordered = sorted(
        normalized,
        key=lambda s: len(s.source_text or ""),
        reverse=True,
    )

    wraps: list[tuple[int, int, int, str]] = []  # start, end, span_id, matched

    for span in ordered:
        if span.span_id in present_ids:
            continue
        src = (span.source_text or "").strip()
        if len(src) < 2:
            continue
        pat = _term_pattern(src)
        for m in pat.finditer(output):
            if _overlaps(m.start(), m.end(), occupied):
                continue
            occupied.append((m.start(), m.end()))
            present_ids.add(span.span_id)
            wraps.append((m.start(), m.end(), span.span_id, m.group(0)))
            break

    label = _leading_label_wrap(output, ordered, present_ids, occupied)
    if label is not None:
        wraps.append(label)

    if not wraps:
        return None

    text = output
    for start, end, span_id, matched in sorted(wraps, key=lambda w: w[0], reverse=True):
        text = f"{text[:start]}〖B{span_id}〗{matched}〖/B{span_id}〗{text[end:]}"

    logger.debug(
        "style markers recovered from source text: %d span(s) re-wrapped",
        len(wraps),
    )
    return text


def style_by_id(spans: list[StyleSpan] | list[tuple]) -> dict[int, PdfStyle]:
    """Map span_id → PdfStyle for marker parse."""
    return {s.span_id: s.style for s in _normalize_spans(spans)}


def _normalize_spans(spans: list[StyleSpan] | list[tuple]) -> list[StyleSpan]:
    out: list[StyleSpan] = []
    for entry in spans:
        if isinstance(entry, StyleSpan):
            out.append(entry)
            continue
        if len(entry) >= 3:
            out.append(
                StyleSpan(int(entry[0]), entry[1], entry[2] or ""),
            )
        elif len(entry) == 2:
            out.append(StyleSpan(int(entry[0]), entry[1], ""))
    return out


def _is_latin_term(src: str) -> bool:
    """True when every whitespace-separated token is a Latin word."""
    words = src.split()
    return bool(words) and all(_LATIN_TOKEN_RE.fullmatch(w) for w in words)


def _term_pattern(src: str) -> re.Pattern[str]:
    """Match source term; multi-word allows flexible whitespace.

    A trailing colon also matches the fullwidth colon DeepLX writes.
    """
    src = src.strip()
    colon = ""
    if src.endswith((":", "：")):
        src = src[:-1].rstrip()
        colon = "[：:]"

    has_quotes = any(ch in src for ch in ('"', '“', '”', "'", '‘', '’'))
    if has_quotes:
        has_open_quote = src and src[0] in ('"', '“', '”', "'", '‘', '’')
        has_close_quote = src and src[-1] in ('"', '“', '”', "'", '‘', '’')
        parts = []
        n = len(src)
        for idx, ch in enumerate(src):
            if ch in ('"', '“', '”'):
                parts.append(r"[\"“”]" if idx == 0 else r"[\s\xa0]*[\"“”]")
            elif ch in ("'", '‘', '’'):
                parts.append(r"['‘’]" if idx == 0 else r"[\s\xa0]*['‘’]")
            elif ch in (".", ",", ";", "!", "?") and (
                (idx == n - 2 and has_close_quote)
                or idx == n - 1
            ):
                # Punctuation immediately before closing quote (e.g. "Ladyscape.")
                # or at span end when quote was split into next span.
                # DeepLX often moves it outside the quote as Chinese punct: "Ladyscape"。
                parts.append(r"[.,;:!?\s\xa0]*")
            elif ch.isspace() or ch == "\xa0":
                parts.append(r"[\s\xa0]+")
            else:
                parts.append(re.escape(ch))
        if has_open_quote and not has_close_quote:
            parts.append(r"[\s\xa0]*[\"“”'‘’]?")
        body = "".join(parts)
        return re.compile(body + colon, re.IGNORECASE)

    words = src.split()
    if len(words) > 1:
        # ``Passion   Prescription`` / line-break spaces after MT
        body = r"\s+".join(re.escape(w) for w in words)
        if _is_latin_term(src):
            body = rf"(?<![A-Za-z0-9]){body}(?![A-Za-z0-9])"
        return re.compile(body + colon, re.IGNORECASE)
    if _is_latin_term(src):
        body = rf"(?<![A-Za-z0-9]){re.escape(src)}(?![A-Za-z0-9])"
        return re.compile(body + colon, re.IGNORECASE)
    return re.compile(re.escape(src) + colon, re.IGNORECASE)


def _leading_label_wrap(
    output: str,
    spans: list[StyleSpan],
    present_ids: set[int],
    occupied: list[tuple[int, int]],
) -> tuple[int, int, int, str] | None:
    """Bold the opening name when MT translated the label but kept the colon.

    Only one unmatched label span qualifies, and only the text before the
    first colon. A sentence that dropped the colon is left alone.
    """
    pending = [
        span
        for span in spans
        if span.span_id not in present_ids and _LABEL_RE.match((span.source_text or "").strip())
    ]
    if len(pending) != 1:
        return None
    found = _LEADING_LABEL_RE.match(output)
    if found is None:
        return None
    start = found.start(1)
    end = found.end(2)
    if _overlaps(start, end, occupied):
        return None
    return start, end, pending[0].span_id, output[start:end]


def _overlaps(a: int, b: int, occupied: list[tuple[int, int]]) -> bool:
    return any(not (b <= s or a >= e) for s, e in occupied)
