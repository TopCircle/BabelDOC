"""Source geometry evidence consumed only by the canonical intent extractor."""

from __future__ import annotations

from collections.abc import Iterable
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph

_BODY_FONT_MAX = 16.0


def is_multiline_body_run(paragraph: PdfParagraph) -> bool:
    metrics = paragraph.reference_metrics
    return bool(
        metrics
        and metrics.line_count
        and metrics.line_count >= 6
        and metrics.font_size
        and 0 < metrics.font_size <= _BODY_FONT_MAX
    )


def is_right_side_callout(
    paragraph: PdfParagraph, page_width: float, body_hosts: Iterable[PdfParagraph]
) -> bool:
    """Larger short text enclosed by a neighboring source body wrap.

    The extractor supplies only body candidates. Explicit chrome/formula/caption
    roles never reach this inference rule.
    """
    box = paragraph.box
    metrics = paragraph.reference_metrics
    if box is None or None in (box.x, box.x2, box.y, box.y2) or page_width <= 0:
        return False
    if metrics is None or metrics.font_size is None or metrics.line_count is None:
        return False
    size = metrics.font_size
    if (
        box.x < page_width * 0.45
        or not 80.0 <= box.x2 - box.x <= page_width * 0.45
        or not 2 <= metrics.line_count <= 8
        or size <= _BODY_FONT_MAX
    ):
        return False
    for other in body_hosts:
        host, ref = other.box, other.reference_metrics
        if other is paragraph or host is None or ref is None:
            continue
        if None in (host.x, host.x2, host.y, host.y2, ref.line_count, ref.font_size):
            continue
        if (
            ref.line_count >= 6
            and 0 < ref.font_size < size / 1.15
            and host.x < box.x - 48.0
            and host.x2 > box.x + 48.0
            and min(host.y2, box.y2) > max(host.y, box.y)
        ):
            return True
    return False
