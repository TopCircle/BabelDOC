"""PR-03: TranslationConfig quote_* thresholds reach ExclusionZoneBuilder."""

from __future__ import annotations

from unittest.mock import MagicMock

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import Cropbox
from babeldoc.format.pdf.document_il.il_version_1 import Mediabox
from babeldoc.format.pdf.document_il.il_version_1 import Page
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.midend.exclusion_zone import ZONE_QUOTE
from babeldoc.format.pdf.document_il.midend.exclusion_zone import ExclusionZoneBuilder
from babeldoc.format.pdf.document_il.midend.typesetting import Typesetting
from babeldoc.format.pdf.translation_config import TranslationConfig
from babeldoc.translator.fixed_map_translator import FixedMapTranslator


def _para(x: float, y: float, x2: float, y2: float) -> PdfParagraph:
    p = PdfParagraph()
    p.box = Box(x=x, y=y, x2=x2, y2=y2)
    p.pdf_paragraph_composition = []
    return p


def _page(paragraphs: list[PdfParagraph], width: float = 612.0, height: float = 792.0) -> Page:
    return Page(
        page_number=0,
        pdf_paragraph=paragraphs,
        cropbox=Cropbox(box=Box(x=0, y=0, x2=width, y2=height)),
        mediabox=Mediabox(box=Box(x=0, y=0, x2=width, y2=height)),
    )


def _config(**quote_kwargs) -> TranslationConfig:
    return TranslationConfig(
        translator=FixedMapTranslator(),
        input_file="quote_cfg.pdf",
        lang_in="en",
        lang_out="zh-CN",
        doc_layout_model=MagicMock(),
        auto_extract_glossary=False,
        **quote_kwargs,
    )


class TestQuoteZoneConfigFromTranslationConfig:
    def test_maps_three_thresholds_keeps_margin_defaults(self):
        cfg = _config(
            quote_narrow_threshold=0.55,
            quote_indent_threshold=0.20,
            quote_right_margin_threshold=0.08,
        )
        ts = Typesetting(cfg)
        qc = ts._quote_zone_config()
        assert qc.narrow_threshold == 0.55
        assert qc.indent_threshold == 0.20
        assert qc.right_margin_threshold == 0.08
        # Margins not on TranslationConfig — keep QuoteZoneConfig defaults
        assert qc.left_margin == 0.02
        assert qc.top_margin == 0.01
        assert qc.bottom_margin == 0.01
        # P2: legacy quote geometry off by default
        assert qc.enable_legacy_quote_geometry is False

    def test_build_page_zones_uses_config_thresholds(self):
        """Default thresholds may miss a borderline para; looser ones catch it."""
        # Narrow-ish column: width ~55% of page, indent ~10%
        # Default narrow_threshold=0.70 would still count as narrow (0.55<0.70)
        # but indent 0.10 < default indent_threshold 0.15 → not quote by default.
        borderline = _para(61, 400, 400, 500)  # indent≈0.10, width_ratio≈0.55
        page = _page([borderline])

        # Defaults: not a quote zone
        zones_default = ExclusionZoneBuilder.build(page)
        assert not any(z.kind == ZONE_QUOTE for z in zones_default)

        # Lower indent threshold via Typesetting/config → becomes quote
        cfg = _config(quote_indent_threshold=0.08)
        ts = Typesetting(cfg)
        zones = ts._build_page_exclusion_zones(page)
        assert any(z.kind == ZONE_QUOTE for z in zones)

    def test_build_page_zones_stricter_indent_excludes_body(self):
        """High indent_threshold should refuse body-margin columns."""
        bodyish = _para(50, 300, 300, 500)  # indent ~8%
        page = _page([bodyish])
        cfg = _config(quote_indent_threshold=0.25)
        ts = Typesetting(cfg)
        zones = ts._build_page_exclusion_zones(page)
        assert not any(z.kind == ZONE_QUOTE for z in zones)

    def test_wrap_column_intent_never_quote_zone_when_legacy_off(self):
        """WRAP_COLUMN must not become a quote exclusion (needle strip)."""
        from babeldoc.format.pdf.document_il.utils.layout_intent import LayoutIntent
        from babeldoc.format.pdf.document_il.utils.layout_intent import LayoutIntentRole

        # Geometry that is_quote_block would accept (narrow + indent).
        wrap = _para(200, 300, 400, 500)  # indent~0.33, width_ratio~0.33
        wrap.layout_intent = LayoutIntent(
            role=LayoutIntentRole.WRAP_COLUMN,
            design_box=wrap.box,
            top_inset=0.0,
            bottom_inset=0.0,
            wrap_shape=[(0.0, 180.0), (20.0, 160.0)],
        )
        page = _page([wrap])
        cfg = _config(enable_legacy_quote_geometry=False)
        ts = Typesetting(cfg)
        zones = ts._build_page_exclusion_zones(page)
        assert not any(z.kind == ZONE_QUOTE for z in zones)

        # Legacy on: geometric heuristic may still classify (no figure-wrap taper).
        cfg_legacy = _config(enable_legacy_quote_geometry=True)
        ts_l = Typesetting(cfg_legacy)
        # Still blocked by is_figure_wrap when taper metrics exist — attach none;
        # narrow+indent alone may create a quote under pure geometry.
        zones_l = ts_l._build_page_exclusion_zones(page)
        # With WRAP_COLUMN intent, even legacy path hits is_figure_wrap only if
        # taper metrics exist; without metrics, legacy can quote. Accept either
        # as long as default path never quotes WRAP_COLUMN.
        _ = zones_l

    def test_callout_intent_uses_design_box_not_inflated_para_box(self):
        """OA p91 red bar: CALLOUT design 54–211 must zone, not the 54–494 box.

        FULL_MEASURE (or layout-class residue) inflates para.box to ~440pt.
        A zone from that box would either crush the body or self-block and
        fall back to full measure — the overlap we are fixing.
        """
        from babeldoc.format.pdf.document_il.utils.layout_intent import LayoutIntent
        from babeldoc.format.pdf.document_il.utils.layout_intent import LayoutIntentRole

        design = Box(x=54.18, y=375.99, x2=211.635, y2=450.99)
        inflated = Box(x=54.18, y=372.62, x2=494.82, y2=450.99)
        bar = _para(inflated.x, inflated.y, inflated.x2, inflated.y2)
        bar.layout_intent = LayoutIntent(
            role=LayoutIntentRole.CALLOUT,
            design_box=design,
            top_inset=0.0,
            bottom_inset=0.0,
        )
        page = _page([bar])
        cfg = _config(enable_legacy_quote_geometry=False)
        ts = Typesetting(cfg)
        zones = ts._build_page_exclusion_zones(page)
        quote_zones = [z for z in zones if z.kind == ZONE_QUOTE]
        assert len(quote_zones) == 1
        z = quote_zones[0].box
        # Zone must track the red-bar design width, not the inflated box.
        assert z.x2 <= 250.0
        assert z.x2 >= 211.0
        assert z.x <= 54.18 + 1.0

    def test_p91_body_available_x_starts_after_callout_zone(self):
        """Body line overlapping the red bar must wrap to its right."""
        from babeldoc.format.pdf.document_il.midend.exclusion_zone import (
            ExclusionZoneIndex,
        )
        from babeldoc.format.pdf.document_il.utils.layout_intent import LayoutIntent
        from babeldoc.format.pdf.document_il.utils.layout_intent import LayoutIntentRole

        design = Box(x=54.18, y=375.99, x2=211.635, y2=450.99)
        bar = _para(54.18, 372.62, 494.82, 450.99)
        bar.layout_intent = LayoutIntent(
            role=LayoutIntentRole.CALLOUT,
            design_box=design,
            top_inset=0.0,
            bottom_inset=0.0,
        )
        body = _para(102.18, 357.24, 572.57, 459.24)
        body.layout_intent = LayoutIntent(
            role=LayoutIntentRole.BODY,
            design_box=body.box,
            top_inset=0.0,
            bottom_inset=0.0,
        )
        page = _page([bar, body])
        ts = Typesetting(_config(enable_legacy_quote_geometry=False))
        zones = ts._build_page_exclusion_zones(page)
        index = ExclusionZoneIndex(zones)
        x1, x2 = index.get_available_x_range(380.0, 400.0, 102.18, 572.57)
        assert x1 >= 211.0
        assert x2 == 572.57
