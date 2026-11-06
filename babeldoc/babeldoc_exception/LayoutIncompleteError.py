# ruff: noqa: N999
"""Capacity failure for a contour that cannot hold the translated line.

The payload is counts and ids only. Pickle must not pull a page, a font,
or the paragraph text into another process.
"""

from __future__ import annotations

_REASONS = frozenset(
    {
        "contour_exhausted",
        "contour_glyph_too_wide",
        "layout_depth_exhausted",
    }
)


class LayoutIncompleteError(Exception):
    """A final contour apply did not fit, so nothing was committed."""

    def __init__(
        self,
        *,
        page_index: int,
        paragraph_id: str,
        reason: str,
        requested_units: int,
        placed_units: int,
    ):
        if reason not in _REASONS:
            raise ValueError(f"unknown layout incomplete reason: {reason}")
        self.page_index = int(page_index)
        self.paragraph_id = str(paragraph_id)
        self.reason = reason
        self.requested_units = int(requested_units)
        self.placed_units = int(placed_units)
        super().__init__(
            f"layout incomplete: {self.reason} "
            f"page={self.page_index} paragraph={self.paragraph_id} "
            f"placed={self.placed_units}/{self.requested_units}"
        )

    def to_dict(self) -> dict[str, int | str]:
        return {
            "page_index": self.page_index,
            "paragraph_id": self.paragraph_id,
            "reason": self.reason,
            "requested_units": self.requested_units,
            "placed_units": self.placed_units,
        }

    def __reduce__(self):
        return (
            self._rebuild,
            (
                self.page_index,
                self.paragraph_id,
                self.reason,
                self.requested_units,
                self.placed_units,
            ),
        )

    @staticmethod
    def _rebuild(
        page_index: int,
        paragraph_id: str,
        reason: str,
        requested_units: int,
        placed_units: int,
    ) -> LayoutIncompleteError:
        return LayoutIncompleteError(
            page_index=page_index,
            paragraph_id=paragraph_id,
            reason=reason,
            requested_units=requested_units,
            placed_units=placed_units,
        )
