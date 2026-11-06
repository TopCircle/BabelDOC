"""Remap a simple PDF outline onto the pages that were actually written.

``kept_source_pages`` is the 1-based source order of those pages. The
output page is that sequence index, not the original page number and not
a guess from the output page count. Alternating bookmarks point at the
translated page. This does not read or write action links.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

TocEntry = tuple[int, str, int]
OutputMode = Literal["mono", "side_by_side", "alternating"]

_OUTPUT_MODES = frozenset({"mono", "side_by_side", "alternating"})


def remap_toc(
    entries: Sequence[TocEntry],
    *,
    kept_source_pages: Sequence[int],
    output_mode: OutputMode,
    translate_first: bool,
) -> list[TocEntry]:
    """Return simple ``(level, title, page)`` rows for ``output_mode``.

    Removed targets are dropped. A kept child hangs off the nearest kept
    ancestor. Emitted levels start at 1 and never increase by more than 1.
    An empty outline returns an empty list.
    """
    if not entries:
        return []
    if output_mode not in _OUTPUT_MODES:
        raise ValueError(f"unknown toc output mode: {output_mode}")

    index_by_page: dict[int, int] = {}
    for index, source_page in enumerate(kept_source_pages):
        index_by_page.setdefault(int(source_page), index)

    remapped: list[TocEntry] = []
    # Original level of each kept ancestor, paired with the level we emit.
    stack: list[tuple[int, int]] = []
    for raw in entries:
        level = int(raw[0])
        title = raw[1] if isinstance(raw[1], str) else str(raw[1])
        try:
            source_page = int(raw[2])
        except (TypeError, ValueError):
            source_page = None
        while stack and stack[-1][0] >= level:
            stack.pop()
        kept_index = None if source_page is None else index_by_page.get(source_page)
        if kept_index is None:
            continue
        if output_mode == "alternating":
            output_page = 2 * kept_index + (1 if translate_first else 2)
        else:
            output_page = kept_index + 1
        new_level = 1 if not stack else stack[-1][1] + 1
        stack.append((level, new_level))
        remapped.append((new_level, title, output_page))
    return remapped
