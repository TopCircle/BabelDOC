"""Skip-reason audit for ILTranslator (PR-C1).

Records *why* a paragraph was not machine-translated.  Observability only —
call sites must keep existing skip predicates unchanged.

Emitted as ``skip_report.json`` next to ``translate_tracking.json`` when
``debug`` or ``working_dir`` is set.
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from babeldoc.format.pdf.document_il.il_version_1 import Page
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph

PREVIEW_MAX = 80


class SkipReason(str, Enum):
    """Stable reason codes for skip_report.json (do not rename lightly)."""

    FIGURE_TEXT = "figure_text"
    HEADER = "header"
    FOOTER = "footer"
    ULTRA_NARROW = "ultra_narrow"
    PULLQUOTE = "pullquote"
    PURE_NUMERIC = "pure_numeric"
    PLACEHOLDER_ONLY = "placeholder_only"
    TOO_SHORT = "too_short"
    VERTICAL = "vertical"
    EMPTY_COMPOSITION = "empty_composition"


@dataclass(frozen=True)
class SkipEvent:
    page_number: int | None
    paragraph_id: str | None
    reason: str
    unicode_preview: str
    layout_label: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def unicode_preview(text: str | None, max_len: int = PREVIEW_MAX) -> str:
    if not text:
        return ""
    t = text.replace("\n", " ").strip()
    if len(t) <= max_len:
        return t
    return t[: max_len - 1] + "…"


def side_callout_skip_reason(
    paragraph: PdfParagraph,
    page: Page | None,
) -> SkipReason | None:
    """Mirror of ``should_skip_side_callout_mt`` with a specific reason.

    Order matches ``should_skip_side_callout_mt`` (pullquote first).
    """
    from babeldoc.format.pdf.document_il.utils.side_callout_skip import (
        is_pullquote_duplicate_of_body,
    )
    from babeldoc.format.pdf.document_il.utils.side_callout_skip import (
        is_ultra_narrow_side_callout,
    )

    if is_pullquote_duplicate_of_body(paragraph, page):
        return SkipReason.PULLQUOTE
    if is_ultra_narrow_side_callout(paragraph, page):
        return SkipReason.ULTRA_NARROW
    return None


class SkipReport:
    """Thread-safe skip event collector."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: list[SkipEvent] = []

    def record(
        self,
        *,
        page: Page | None = None,
        page_number: int | None = None,
        paragraph: PdfParagraph | None = None,
        reason: SkipReason | str,
        unicode: str | None = None,
        layout_label: str | None = None,
        paragraph_id: str | None = None,
    ) -> None:
        """Append one skip event. Safe from worker threads."""
        reason_s = reason.value if isinstance(reason, SkipReason) else str(reason)
        pn = page_number
        if pn is None and page is not None:
            pn = getattr(page, "page_number", None)
        pid = paragraph_id
        text = unicode
        label = layout_label
        if paragraph is not None:
            if pid is None:
                pid = getattr(paragraph, "debug_id", None)
            if text is None:
                text = getattr(paragraph, "unicode", None)
            if label is None:
                label = getattr(paragraph, "layout_label", None)
        event = SkipEvent(
            page_number=pn,
            paragraph_id=pid,
            reason=reason_s,
            unicode_preview=unicode_preview(text),
            layout_label=label,
        )
        with self._lock:
            self._events.append(event)

    @property
    def events(self) -> list[SkipEvent]:
        with self._lock:
            return list(self._events)

    def counts_by_reason(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for e in self.events:
            counts[e.reason] = counts.get(e.reason, 0) + 1
        return counts

    def to_dict(self) -> dict[str, Any]:
        events = self.events
        return {
            "schema_version": 1,
            "total": len(events),
            "counts_by_reason": self.counts_by_reason(),
            "events": [e.to_dict() for e in events],
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    def write_json(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")
        return path

    def clear(self) -> None:
        with self._lock:
            self._events.clear()
