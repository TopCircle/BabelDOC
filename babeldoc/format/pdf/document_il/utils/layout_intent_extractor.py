"""Layout-First P0 extractor: derive a read-only per-paragraph layout intent.

Runs right after ``StylesAndFormulas`` (before translation/typesetting) and
attaches a :class:`LayoutIntent` to every :class:`PdfParagraph` that has a
design box.  The extractor is **read-only**: it never moves boxes or changes
geometry; it only classifies the paragraph and snapshots design geometry that
later passes (gap_contract P1, wrap_shape P2, ...) may consume.

Role classification follows the strict 9-rule order from
``docs/layout-first-coding-plan.md`` §1.4:

    chrome → formula → wrap_column → figure_caption →
    section_header/title → subtitle_overlay → pull_quote → callout → body

``is_layout_debug_stub`` paragraphs **always** get role BODY (no quote/callout
heuristics) and are excluded from gap/stack/photo judgments.  All geometry
helpers are read-only ports of the single-source utilities (figure_wrap /
region_skip / vertical_gap / layout_helper / box_expand) so behavior cannot
drift.

``text_on_photo`` / ``subtitle_overlay`` thresholds are uncalibrated on OA
(coding-plan §4); consumers must not treat them as hard layout policy until
P1+ calibration.
"""

from __future__ import annotations

import copy
import json
import logging
from typing import TYPE_CHECKING

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.utils.box_expand import is_callout_column
from babeldoc.format.pdf.document_il.utils.figure_wrap import is_figure_wrap_paragraph
from babeldoc.format.pdf.document_il.utils.layout_helper import calculate_box_iou
from babeldoc.format.pdf.document_il.utils.layout_helper import is_quote_block
from babeldoc.format.pdf.document_il.utils.layout_intent import LayoutIntent
from babeldoc.format.pdf.document_il.utils.layout_intent import LayoutIntentRole
from babeldoc.format.pdf.document_il.utils.layout_intent import WrapMode
from babeldoc.format.pdf.document_il.utils.line_interval_plan import (
    infer_wrap_mode_from_line_boxes,
)
from babeldoc.format.pdf.document_il.utils.region_skip import is_chrome_paragraph
from babeldoc.format.pdf.document_il.utils.region_skip import is_layout_debug_stub
from babeldoc.format.pdf.document_il.utils.vertical_gap import is_display_title
from babeldoc.format.pdf.document_il.utils.vertical_gap import max_font_size
from babeldoc.format.pdf.document_il.utils.wrap_shape import shape_from_widths

if TYPE_CHECKING:
    from babeldoc.format.pdf.document_il.il_version_1 import Document
    from babeldoc.format.pdf.document_il.il_version_1 import Page
    from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter
    from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
    from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraphComposition
    from babeldoc.format.pdf.translation_config import TranslationConfig

logger = logging.getLogger(__name__)

# Debug dump schema (§1.6). The baseline is the P0 branch head the dump was
# produced against, so digests can be compared across runs.
_LAYOUT_INTENT_DUMP_VERSION = 1
_LAYOUT_INTENT_DUMP_BASELINE = "5cf4962"

# text_on_photo IoU threshold (decision point 4 in the coding plan).
_PHOTO_IOU_THRESHOLD = 0.30

# x-overlap slack, mirroring vertical_gap._x_overlap (slack=8).
_X_OVERLAP_SLACK = 8.0

_FIGURE_CAPTION_LABELS = frozenset({"figure_caption", "figure_title", "figure_text"})
_SECTION_HEADER_LABELS = frozenset({"section_header", "paragraph_title"})
_TITLE_CLASS_LABELS = frozenset({"title", "section_header", "paragraph_title"})
_CALLOUT_LABEL = "callout"


class LayoutIntentExtractor:
    """Project per-paragraph layout intent after StylesAndFormulas.

    Pure read-only pass: it only attaches ``PdfParagraph.layout_intent`` and,
    under ``--debug``, writes ``layout_intent.json``.  Failure of one page or
    one paragraph is isolated and audited, never fatal.
    """

    def __init__(self, translation_config: TranslationConfig) -> None:
        self.translation_config = translation_config
        self.audit = {"pages_skipped": 0, "no_box": 0, "extract_errors": 0}

    # ------------------------------------------------------------------ API

    def extract(self, document: Document) -> None:
        """Populate ``PdfParagraph.layout_intent`` for every page.

        Pages are extracted one by one; a failing page increments
        ``audit.pages_skipped`` and logs a warning instead of aborting.  The
        caller (high_level) wraps this entry in try/except as the last line
        of defense.
        """
        for page in document.page or []:
            try:
                self._extract_page(page)
            except Exception:
                self.audit["pages_skipped"] += 1
                logger.warning(
                    "layout_intent: page %s skipped after extraction error",
                    getattr(page, "page_number", None),
                    exc_info=True,
                )
        if self.translation_config.debug:
            self._dump(document)

    # ------------------------------------------------------------ internals

    def _extract_page(self, page: Page) -> None:
        page_width = self._page_width(page)
        photo_boxes = self._photo_boxes(page)

        # Pass 1 — geometry snapshots + primary roles (rules 1-5).  Title
        # paragraphs are collected here because rule 6 needs the title roster.
        metas: dict[int, dict] = {}
        titles: list[tuple[PdfParagraph, Box, float]] = []
        for para in page.pdf_paragraph or []:
            try:
                meta = self._snapshot_para(para, page)
            except Exception:
                self.audit["extract_errors"] += 1
                logger.warning(
                    "layout_intent: paragraph %s analysis failed",
                    getattr(para, "debug_id", None),
                    exc_info=True,
                )
                continue
            if meta is None:
                continue  # no design box — audited inside _snapshot_para
            if meta["primary"] is LayoutIntentRole.TITLE and meta["ink"] is not None:
                titles.append((para, meta["ink"], max_font_size(para)))
            metas[id(para)] = meta

        # Pass 2 — complete the role (rules 6-9) and build the intent objects.
        intents: dict[int, LayoutIntent] = {}
        for pid, meta in metas.items():
            para = meta["para"]
            try:
                intent = self._build_intent(para, meta, page_width, photo_boxes, titles)
            except Exception:
                self.audit["extract_errors"] += 1
                logger.warning(
                    "layout_intent: paragraph %s intent build failed",
                    getattr(para, "debug_id", None),
                    exc_info=True,
                )
                continue
            para.layout_intent = intent
            intents[pid] = intent

        # Pass 3 — page-level stack / gap_contract projection.  Only
        # intent-bearing content participates (box is not None, non-chrome,
        # non-stub, with ink); chrome/stub are excluded by design.
        if metas:
            self._compute_stacks_and_gaps(page, metas, intents)

    def _snapshot_para(self, para: PdfParagraph, page: Page) -> dict | None:
        """Snapshot design geometry + decide the primary role (rules 1-5).

        Returns ``None`` when the paragraph has no design box (no intent).
        """
        if para.box is None:
            self.audit["no_box"] += 1
            return None
        return {
            "para": para,
            "design_box": copy.deepcopy(para.box),
            "ink": self._ink_rect(para),
            "lines": self._line_boxes(para),
            "primary": self._classify_primary(para, page),
        }

    def _classify_primary(
        self,
        para: PdfParagraph,
        page: Page,
    ) -> LayoutIntentRole | None:
        """Rules 1-5 (+ stub short-circuit); ``None`` falls through to secondary.

        LayoutParser debug stubs (``is_layout_debug_stub``) always return BODY
        immediately — they must not pick up callout/quote geometry heuristics
        (coding-plan §1.4).
        """
        # Diagnostic stubs: fixed BODY, no further role rules.
        if is_layout_debug_stub(para):
            return LayoutIntentRole.BODY
        # Rule 1 — site chrome (header/footer/URL/page number/abandon).
        if is_chrome_paragraph(para, page):
            return LayoutIntentRole.CHROME
        # Rule 2 — composition carries a formula.
        for comp in para.pdf_paragraph_composition or []:
            if comp.pdf_formula is not None:
                return LayoutIntentRole.FORMULA
        # Rule 3 — figure-wrap (taper) column; single source of truth.
        if is_figure_wrap_paragraph(para):
            return LayoutIntentRole.WRAP_COLUMN
        label = (getattr(para, "layout_label", None) or "").strip().lower()
        # Rule 4 — figure caption / title / text.
        if label in _FIGURE_CAPTION_LABELS:
            return LayoutIntentRole.FIGURE_CAPTION
        # Rule 5 — section header / paragraph title; display TITLE only for
        # label=="title" AND is_display_title (vertical_gap).
        if label in _SECTION_HEADER_LABELS:
            return LayoutIntentRole.SECTION_HEADER
        if label == "title" and is_display_title(para):
            return LayoutIntentRole.TITLE
        return None

    def _build_intent(
        self,
        para: PdfParagraph,
        meta: dict,
        page_width: float,
        photo_boxes: list[Box],
        titles: list[tuple[PdfParagraph, Box, float]],
    ) -> LayoutIntent:
        design_box: Box = meta["design_box"]
        ink: Box | None = meta["ink"]
        role = meta["primary"]
        overlays_band = None
        if role is None:
            role, overlays_band = self._classify_secondary(
                para, ink, page_width, titles
            )

        top_inset = 0.0
        bottom_inset = 0.0
        if ink is not None:
            top_inset = float(design_box.y2 - ink.y2)
            bottom_inset = float(ink.y - design_box.y)

        wrap_shape = None
        wrap_mode = WrapMode.NONE
        if role is LayoutIntentRole.WRAP_COLUMN:
            if len(meta["lines"]) >= 2:
                wrap_shape = [
                    (float(line.x - design_box.x), float(line.x2 - line.x))
                    for line in meta["lines"]
                ]
                line_boxes = [
                    (float(line.x), float(line.x2)) for line in meta["lines"]
                ]
                wrap_mode = infer_wrap_mode_from_line_boxes(line_boxes)
                # Shape without clear edge spread: preserve historical right-pin.
                if wrap_mode is WrapMode.NONE:
                    wrap_mode = WrapMode.RIGHT_FIXED
            else:
                # No multi-line boxes (noisy/post-cluster): synthesize from
                # reference widths so P2 pin path still has a shape.
                rm = getattr(para, "reference_metrics", None)
                widths = (
                    getattr(rm, "per_line_widths", None) if rm is not None else None
                )
                wrap_shape = shape_from_widths(widths)
                # Width-only synth: no edge geometry → right-pin (legacy).
                if wrap_shape:
                    wrap_mode = WrapMode.RIGHT_FIXED

        expansion_policy, expansion_limits, overflow_policy = self._project_policy(
            role
        )
        is_chrome = role is LayoutIntentRole.CHROME
        # Chrome + debug stubs never participate in text_on_photo (coding-plan §1.4).
        text_on_photo = False
        if not is_chrome and not is_layout_debug_stub(para):
            text_on_photo = self._is_on_photo(ink, photo_boxes)

        return LayoutIntent(
            role=role,
            design_box=design_box,
            top_inset=top_inset,
            bottom_inset=bottom_inset,
            wrap_shape=wrap_shape,
            wrap_mode=wrap_mode,
            overlays_band=overlays_band,
            expansion_policy=expansion_policy,
            expansion_limits=expansion_limits,
            overflow_policy=overflow_policy,
            is_chrome=is_chrome,
            text_on_photo=text_on_photo,
        )

    def _classify_secondary(
        self,
        para: PdfParagraph,
        ink: Box | None,
        page_width: float,
        titles: list[tuple[PdfParagraph, Box, float]],
    ) -> tuple[LayoutIntentRole, str | None]:
        """Rules 6-9; returns ``(role, overlays_band)``."""
        label = (getattr(para, "layout_label", None) or "").strip().lower()
        # Rule 6 — subtitle overlaid on a display TITLE.
        if ink is not None and label not in _TITLE_CLASS_LABELS:
            band = self._match_subtitle_overlay(para, ink, titles)
            if band is not None:
                return LayoutIntentRole.SUBTITLE_OVERLAY, band
        # Rule 7 — pull quote (P0 single source: is_quote_block).
        if is_quote_block(para, page_width):
            return LayoutIntentRole.PULL_QUOTE, None
        # Rule 8 — callout column.
        if label == _CALLOUT_LABEL or is_callout_column(para.box):
            return LayoutIntentRole.CALLOUT, None
        # Rule 9 — everything else.
        return LayoutIntentRole.BODY, None

    def _match_subtitle_overlay(
        self,
        para: PdfParagraph,
        ink: Box,
        titles: list[tuple[PdfParagraph, Box, float]],
    ) -> str | None:
        """debug_id of the TITLE *para* overlays, or None.

        Criteria (§1.4 rule 6): ink y-interval overlaps the TITLE by at least
        0.5 × the paragraph's line height, font size strictly smaller than the
        title's, and the paragraph carries no title-class label.
        """
        para_size = max_font_size(para)
        line_h = para_size
        if line_h <= 0:
            line_h = ink.y2 - ink.y if ink.y is not None and ink.y2 is not None else 0.0
        best: tuple[float, PdfParagraph] | None = None
        for title_para, title_ink, title_size in titles:
            if title_ink is None or title_size <= 0:
                continue
            overlap = min(ink.y2, title_ink.y2) - max(ink.y, title_ink.y)
            if overlap <= 0:
                continue
            if line_h <= 0 or overlap < 0.5 * line_h:
                continue
            if para_size >= title_size:
                continue
            if best is None or overlap > best[0]:
                best = (overlap, title_para)
        if best is None:
            return None
        return best[1].debug_id

    def _compute_stacks_and_gaps(
        self,
        page: Page,
        metas: dict[int, dict],
        intents: dict[int, LayoutIntent],
    ) -> None:
        """Union-find overlap stacks + per-stack bottom ``gap_contract``.

        Pool = intent-bearing paragraphs (box is not None, non-chrome,
        non-stub, with ink).  Stacks are connected components under
        y-overlap ≥ 0.5 × min(line height) and x-overlap (slack=8).  Only the
        bottom-most member (min ink.y) of each stack carries a
        ``gap_contract`` against the closest non-chrome/non-stub paragraph
        strictly below it.
        """
        pool: list[tuple[PdfParagraph, Box]] = []
        for meta in metas.values():
            para = meta["para"]
            ink = meta["ink"]
            if ink is None:
                continue
            if is_chrome_paragraph(para, page) or is_layout_debug_stub(para):
                continue
            pool.append((para, ink))

        parent = {id(para): id(para) for para, _ in pool}

        def find(node: int) -> int:
            while parent[node] != node:
                parent[node] = parent[parent[node]]
                node = parent[node]
            return node

        def union(a: int, b: int) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        for i in range(len(pool)):
            para_i, ink_i = pool[i]
            for j in range(i + 1, len(pool)):
                para_j, ink_j = pool[j]
                if self._stack_overlap(para_i, ink_i, para_j, ink_j):
                    union(id(para_i), id(para_j))

        # Deterministic stack ids: first-seen root in page order, from 0.
        root_order: list[int] = []
        seen: set[int] = set()
        for para in page.pdf_paragraph or []:
            node = id(para)
            if node not in parent:
                continue
            root = find(node)
            if root not in seen:
                seen.add(root)
                root_order.append(root)
        stack_ids = {root: i for i, root in enumerate(root_order)}

        for para, _ in pool:
            intent = intents.get(id(para))
            if intent is not None:
                intent.stack = stack_ids[find(id(para))]

        for root in root_order:
            members = [item for item in pool if find(id(item[0])) == root]
            bottom_para, bottom_ink = min(members, key=lambda item: item[1].y)
            best: tuple[PdfParagraph, Box] | None = None
            for cand, cand_ink in pool:
                if cand is bottom_para:
                    continue
                if cand_ink.y2 >= bottom_ink.y:  # must be strictly below
                    continue
                if not self._x_overlap(bottom_ink, cand_ink):
                    continue
                if best is None or cand_ink.y2 > best[1].y2:
                    best = (cand, cand_ink)
            intent = intents.get(id(bottom_para))
            if intent is not None and best is not None:
                intent.gap_contract = float(bottom_ink.y - best[1].y2)

    @staticmethod
    def _stack_overlap(
        para_a: PdfParagraph,
        ink_a: Box,
        para_b: PdfParagraph,
        ink_b: Box,
    ) -> bool:
        """y-overlap ≥ 0.5 × min(line height) and x-overlap (slack=8)."""
        if not LayoutIntentExtractor._x_overlap(ink_a, ink_b):
            return False
        height_a = LayoutIntentExtractor._line_height(para_a, ink_a)
        height_b = LayoutIntentExtractor._line_height(para_b, ink_b)
        if height_a <= 0 or height_b <= 0:
            return False
        overlap = min(ink_a.y2, ink_b.y2) - max(ink_a.y, ink_b.y)
        return overlap >= 0.5 * min(height_a, height_b)

    @staticmethod
    def _line_height(para: PdfParagraph, ink: Box) -> float:
        """Single-line height proxy: max rendered font size, else ink height."""
        size = max_font_size(para)
        if size > 0:
            return size
        if ink.y is not None and ink.y2 is not None:
            return ink.y2 - ink.y
        return 0.0

    @staticmethod
    def _x_overlap(a: Box, b: Box, *, slack: float = _X_OVERLAP_SLACK) -> bool:
        """Mirror vertical_gap._x_overlap (slack=8)."""
        return a.x < b.x2 + slack and a.x2 > b.x - slack

    @staticmethod
    def _project_policy(role: LayoutIntentRole) -> tuple[tuple, tuple, str]:
        """§1.4 policy projection — describes current behavior, changes nothing.

        CHROME: no expansion axes; WRAP_COLUMN: right/down, photo/page_margin;
        CALLOUT: left/down/right (mirrors box_expand order), expand.  The
        default is the LayoutIntent constructor default.
        """
        if role is LayoutIntentRole.CHROME:
            return (), (), "scale_down"
        if role is LayoutIntentRole.WRAP_COLUMN:
            return ("right", "down"), ("photo", "page_margin"), "scale_down"
        if role is LayoutIntentRole.CALLOUT:
            return ("left", "down", "right"), ("page_margin",), "expand"
        return ("right", "down"), ("page_margin",), "scale_down"

    def _is_on_photo(self, ink: Box | None, photo_boxes: list[Box]) -> bool:
        if ink is None:
            return False
        for photo_box in photo_boxes:
            if photo_box is None:
                continue
            if calculate_box_iou(ink, photo_box) >= _PHOTO_IOU_THRESHOLD:
                return True
        return False

    @staticmethod
    def _photo_boxes(page: Page) -> list[Box]:
        """Figure / image-form boxes that can host overlaid text.

        Matches exclusion_zone: only ``PdfForm`` with ``form_type == "image"``
        (not vector/other forms).
        """
        boxes: list[Box] = []
        for figure in page.pdf_figure or []:
            if figure.box is not None:
                boxes.append(figure.box)
        for form in page.pdf_form or []:
            if getattr(form, "form_type", None) == "image" and form.box is not None:
                boxes.append(form.box)
        return boxes
    @staticmethod
    def _page_width(page: Page) -> float:
        """cropbox (fallback mediabox) width, mirroring exclusion_zone."""
        for attr in ("cropbox", "mediabox"):
            crop = getattr(page, attr, None)
            if crop is None:
                continue
            box = getattr(crop, "box", None)
            if box is None:
                box = crop
            if box is not None and box.x is not None and box.x2 is not None:
                return float(box.x2 - box.x)
        return 0.0

    @staticmethod
    def _ink_rect(para: PdfParagraph) -> Box | None:
        """Tight box of rendered glyphs, visual_bbox preferred (char fallback).

        Same intent as vertical_gap.ink_box but honors ``visual_bbox`` first
        (decision point 1): ParagraphFinder derives ``para.box`` from visual
        boxes, so insets stay self-consistent with the design box.
        """
        xs: list[float] = []
        ys: list[float] = []
        x2s: list[float] = []
        y2s: list[float] = []
        for ch in LayoutIntentExtractor._iter_chars(para):
            box = LayoutIntentExtractor._char_visual_box(ch)
            if box is None:
                continue
            xs.append(float(box.x))
            ys.append(float(box.y))
            x2s.append(float(box.x2))
            y2s.append(float(box.y2))
        if not ys:
            return None
        return Box(x=min(xs), y=min(ys), x2=max(x2s), y2=max(y2s))

    @staticmethod
    def _char_visual_box(ch: PdfCharacter) -> Box | None:
        """visual_bbox.box when complete, else char box, else None."""
        visual = getattr(ch, "visual_bbox", None)
        if visual is not None:
            box = getattr(visual, "box", None)
            if LayoutIntentExtractor._box_complete(box):
                return box
        box = getattr(ch, "box", None)
        if LayoutIntentExtractor._box_complete(box):
            return box
        return None

    @staticmethod
    def _box_complete(box: Box | None) -> bool:
        return (
            box is not None
            and getattr(box, "x", None) is not None
            and getattr(box, "y", None) is not None
            and getattr(box, "x2", None) is not None
            and getattr(box, "y2", None) is not None
        )

    def _line_boxes(self, para: PdfParagraph) -> list[Box]:
        """Per-line boxes, top-down.

        ``comp.pdf_line.box`` preferred; when no line box is usable, fall back
        to clustering character visual boxes by y2 (tolerance = max(font_size)
        × 0.25).
        """
        lines: list[Box] = []
        for comp in para.pdf_paragraph_composition or []:
            line = comp.pdf_line
            if line is not None and self._box_complete(line.box):
                lines.append(line.box)
        if lines:
            return self._sort_lines_top_down(lines)

        chars: list[Box] = []
        for comp in para.pdf_paragraph_composition or []:
            for ch in self._comp_chars(comp):
                box = self._char_visual_box(ch)
                if box is not None:
                    chars.append(box)
        if not chars:
            return []

        tolerance = max_font_size(para) * 0.25
        ordered = sorted(chars, key=lambda b: -b.y2)
        clusters: list[list[Box]] = []
        for box in ordered:
            if clusters and abs(box.y2 - clusters[-1][0].y2) <= tolerance:
                clusters[-1].append(box)
            else:
                clusters.append([box])
        return [
            Box(
                x=min(b.x for b in cluster),
                y=min(b.y for b in cluster),
                x2=max(b.x2 for b in cluster),
                y2=max(b.y2 for b in cluster),
            )
            for cluster in clusters
        ]

    @staticmethod
    def _sort_lines_top_down(lines: list[Box]) -> list[Box]:
        return sorted(lines, key=lambda b: (-(b.y2 or 0.0), b.x or 0.0))

    @classmethod
    def _iter_chars(cls, para: PdfParagraph):
        """Yield positioned characters from every composition of *para*."""
        for composition in para.pdf_paragraph_composition or []:
            yield from cls._comp_chars(composition)

    @staticmethod
    def _comp_chars(composition: PdfParagraphComposition):
        """Yield positioned characters from one composition."""
        if composition.pdf_character is not None:
            yield composition.pdf_character
        elif composition.pdf_line is not None and composition.pdf_line.pdf_character:
            yield from composition.pdf_line.pdf_character
        elif composition.pdf_formula is not None and composition.pdf_formula.pdf_character:
            yield from composition.pdf_formula.pdf_character
        elif (
            composition.pdf_same_style_characters is not None
            and composition.pdf_same_style_characters.pdf_character
        ):
            yield from composition.pdf_same_style_characters.pdf_character

    # ----------------------------------------------------------- debug dump

    def _dump(self, document: Document) -> None:
        """Write layout_intent.json (self-serialized; --debug only)."""
        try:
            pages: dict[str, dict] = {}
            for page in document.page or []:
                entries: dict[str, dict] = {}
                for para in page.pdf_paragraph or []:
                    intent = getattr(para, "layout_intent", None)
                    if intent is None:
                        continue
                    key = para.debug_id or f"para_{len(entries)}"
                    entries[key] = intent.to_dict()
                if entries:
                    pages[str(page.page_number)] = entries
            payload = {
                "version": _LAYOUT_INTENT_DUMP_VERSION,
                "baseline": _LAYOUT_INTENT_DUMP_BASELINE,
                "pages": pages,
                "audit": dict(self.audit),
            }
            path = self.translation_config.get_working_file_path("layout_intent.json")
            with path.open("w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)
        except Exception:
            # Best-effort diagnostics — never break the pipeline.
            logger.warning("layout_intent: debug dump failed", exc_info=True)
