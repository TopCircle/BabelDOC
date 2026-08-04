"""Thin typesetting hooks for Layout-First P1 gap pipeline.

Keeps ``Typesetting.render_page`` free of gap business logic: pre-pass
reservation, post-pass limited repair, optional debug dump.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from typing import Any

from babeldoc.format.pdf.document_il.utils.layout_audit import LayoutAuditReport

if TYPE_CHECKING:
    from babeldoc.format.pdf.document_il.il_version_1 import Page

logger = logging.getLogger(__name__)


def pre_typeset_gap_pass(page: Page) -> LayoutAuditReport:
    """First-pass gap_contract reservation (before glyph layout)."""
    try:
        from babeldoc.format.pdf.document_il.utils.gap_contract_pass import (
            apply_gap_contract_first_pass,
        )

        return apply_gap_contract_first_pass(page)
    except Exception:
        logger.warning(
            "gap_contract first-pass failed page=%s",
            getattr(page, "page_number", None),
            exc_info=True,
        )
        return LayoutAuditReport()


def post_typeset_gap_pass(
    page: Page,
    report: LayoutAuditReport | None = None,
    *,
    translation_config: Any = None,
) -> LayoutAuditReport:
    """Post-typeset limited title→body repair + optional audit dump."""
    try:
        from babeldoc.format.pdf.document_il.utils.vertical_gap import (
            enforce_title_body_gaps,
        )

        out = enforce_title_body_gaps(page, report=report)
    except Exception:
        logger.warning(
            "title-body gap repair failed page=%s",
            getattr(page, "page_number", None),
            exc_info=True,
        )
        return report if report is not None else LayoutAuditReport()

    if translation_config is not None and getattr(
        translation_config, "debug", False
    ):
        try:
            path = translation_config.get_working_file_path(
                f"layout_audit_p{page.page_number}.json"
            )
            out.dump(path)
        except Exception:
            logger.debug("layout_audit dump skipped", exc_info=True)
    return out
