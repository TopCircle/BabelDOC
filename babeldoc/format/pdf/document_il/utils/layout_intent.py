"""LayoutIntent: runtime-only per-paragraph layout projection (Layout-First P0).

Pure model -- no extractor imports. Populated by ``LayoutIntentExtractor``
after StylesAndFormulas, read by Typesetting/PostLayout, and never serialized
to XML: ``PdfParagraph.layout_intent`` is declared with xsdata
``type="Ignore"`` metadata (plus a string forward annotation), so
xml_converter skips it even when set.

``Box`` is imported from ``il_version_1`` only under ``TYPE_CHECKING``, so
this module has no runtime dependency on ``il_version_1``; in turn
``il_version_1`` imports ``LayoutIntent`` at runtime (required by xsdata's
``get_type_hints``) without creating an import cycle.

``wrap_shape`` stores EN-measured ``(left_offset, width)`` with
``left_offset = line.x - design_box.x``. P2 consumption
(``Typesetting._typeset_wrap_line``) pins the right edge at
``design_box.x2`` and sets ``left = design.x2 - width`` (left-edge step).
Placement uses **width only**; left_offset is forensic/debug. When EN
right edges are not exactly at ``design_box.x2``, pin-right can diverge
slightly from original EN ink — that is intentional (avoid mirror taper).

``text_on_photo`` / subtitle overlay signals are uncalibrated on real OA
pages until P1+; treat as advisory for consumers.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Type-checker-only: keeps the model's one-way dependency on
    # il_version_1.Box without a runtime import, so il_version_1 can import
    # LayoutIntent at runtime (required by xsdata, see il_version_1.py).
    from babeldoc.format.pdf.document_il.il_version_1 import Box


class LayoutIntentRole(str, Enum):
    BODY = "body"
    TITLE = "title"
    SUBTITLE_OVERLAY = "subtitle_overlay"
    PULL_QUOTE = "pull_quote"
    CALLOUT = "callout"
    FIGURE_CAPTION = "figure_caption"
    CHROME = "chrome"
    WRAP_COLUMN = "wrap_column"
    # Pre-declared members (review "enum too narrow" blocker): P0 only emits
    # FORMULA/SECTION_HEADER; the rest keep BODY until P2+.
    FORMULA = "formula"
    SECTION_HEADER = "section_header"
    LIST = "list"
    DROPCAP = "dropcap"
    OCR = "ocr"


@dataclass(slots=True)
class LayoutIntent:
    """Pre-translation derived projection; consumers must not mutate it.

    All fields are runtime-only. The owning ``PdfParagraph.layout_intent``
    field uses xsdata ``type="Ignore"`` metadata, so xml_converter never
    serializes it (a bare metadata-less field would be emitted as an element
    once set to a non-None value).
    """

    role: LayoutIntentRole  # classification result; unknown always BODY
    design_box: Box  # deep copy of para.box after Styles; read-only for layout
    top_inset: float  # design_box.y2 - first-line ink top (y2 max), PDF y-up
    bottom_inset: float  # last-line ink bottom (y min) - design_box.y
    wrap_shape: list[tuple[float, float]] | None = (
        None  # per-line (left_offset, width); right edge = design right edge, left edge = right edge - width
    )
    overlays_band: str | None = (
        None  # SUBTITLE_OVERLAY -> debug_id of the TITLE it overlays
    )
    stack: int = 0  # design overlap group (members do not push each other); only group bottom carries gap_contract
    expansion_policy: tuple[str, ...] = (
        "right",
        "down",
    )  # expandable axes in order; chrome=(); wrap_column forbids left
    expansion_limits: tuple[str, ...] = (
        "page_margin",
    )  # symbol source; P1+ reads ExclusionZoneIndex values
    overflow_policy: str = "scale_down"  # scale_down | expand
    min_scale: float = 0.55  # per-paragraph scale floor (global default)
    gap_contract: float | None = (
        None  # ink bottom - next content block's ink top (negative = overlap); excludes stub/chrome
    )
    is_chrome: bool = False
    text_on_photo: bool = False

    def to_dict(self) -> dict:
        """Project to a plain JSON-serializable dict.

        Box -> [x, y, x2, y2]; wrap_shape -> [[left_offset, width], ...];
        role -> .value; tuple policies -> lists (JSON has no tuples).
        """
        return {
            "role": self.role.value,
            "design_box": [
                self.design_box.x,
                self.design_box.y,
                self.design_box.x2,
                self.design_box.y2,
            ],
            "top_inset": self.top_inset,
            "bottom_inset": self.bottom_inset,
            "wrap_shape": (
                [[left, width] for left, width in self.wrap_shape]
                if self.wrap_shape is not None
                else None
            ),
            "overlays_band": self.overlays_band,
            "stack": self.stack,
            "expansion_policy": list(self.expansion_policy),
            "expansion_limits": list(self.expansion_limits),
            "overflow_policy": self.overflow_policy,
            "min_scale": self.min_scale,
            "gap_contract": self.gap_contract,
            "is_chrome": self.is_chrome,
            "text_on_photo": self.text_on_photo,
        }
