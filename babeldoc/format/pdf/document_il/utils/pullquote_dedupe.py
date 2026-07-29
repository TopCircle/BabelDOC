"""Compatibility re-export for side-callout MT skip policy.

Implementation lives in :mod:`side_callout_skip`.  Import from there for
new code; this module remains so older imports keep working.
"""

from __future__ import annotations

from babeldoc.format.pdf.document_il.utils.side_callout_skip import (
    is_pullquote_duplicate_of_body,
)
from babeldoc.format.pdf.document_il.utils.side_callout_skip import (
    is_ultra_narrow_side_callout,
)
from babeldoc.format.pdf.document_il.utils.side_callout_skip import normalize_for_dup
from babeldoc.format.pdf.document_il.utils.side_callout_skip import (
    should_skip_side_callout_mt,
)

__all__ = [
    "is_pullquote_duplicate_of_body",
    "is_ultra_narrow_side_callout",
    "normalize_for_dup",
    "should_skip_side_callout_mt",
]
