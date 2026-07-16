"""Tests for paragraph horizontal alignment detection and typesetting shift."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter
from babeldoc.format.pdf.document_il.il_version_1 import PdfLine
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraphComposition
from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
from babeldoc.format.pdf.document_il.il_version_1 import VisualBbox
from babeldoc.format.pdf.document_il.midend.typesetting import Typesetting
from babeldoc.format.pdf.document_il.midend.typesetting import TypesettingUnit
from babeldoc.format.pdf.document_il.utils.layout_helper import detect_paragraph_alignment


def _char(x: float, x2: float, y: float = 100.0, y2: float = 112.0, ch: str = "a"):
    box = Box(x=x, y=y, x2=x2, y2=y2)
    return PdfCharacter(
        char_unicode=ch,
        box=box,
        visual_bbox=VisualBbox(box=Box(x=x, y=y, x2=x2, y2=y2)),
        pdf_style=PdfStyle(font_id="base", font_size=10.0, graphic_state=None),
    )


def _line_para(line_ranges: list[tuple[float, float]], *, label: str | None = None):
    """Build a paragraph whose compositions are one PdfLine per range."""
    compositions = []
    y = 200.0
    for x, x2 in line_ranges:
        # Put a few chars spanning the line range
        chars = [
            _char(x, x + 5, y=y, y2=y + 12, ch="A"),
            _char(x2 - 5, x2, y=y, y2=y + 12, ch="Z"),
        ]
        line = PdfLine(
            box=Box(x=x, y=y, x2=x2, y2=y + 12),
            pdf_character=chars,
        )
        compositions.append(PdfParagraphComposition(pdf_line=line))
        y -= 15.0

    para_left = min(r[0] for r in line_ranges)
    para_right = max(r[1] for r in line_ranges)
    para_bottom = y
    para_top = 200.0 + 12.0
    return PdfParagraph(
        box=Box(x=para_left, y=para_bottom, x2=para_right, y2=para_top),
        pdf_style=PdfStyle(font_id="base", font_size=10.0, graphic_state=None),
        pdf_paragraph_composition=compositions,
        unicode="test",
        layout_label=label,
    )


def _page(width: float = 612.0):
    return SimpleNamespace(
        cropbox=SimpleNamespace(box=Box(x=0, y=0, x2=width, y2=792)),
        mediabox=SimpleNamespace(box=Box(x=0, y=0, x2=width, y2=792)),
    )


class TestDetectParagraphAlignment:
    def test_multiline_center_varying_widths(self):
        # Page-centered author block: equal L/R margins, varying widths
        # Centers all at 306
        lines = [
            (78.6, 533.4),   # width 454.8, center 306
            (125.3, 486.7),  # width 361.4, center 306
            (132.7, 479.3),  # width 346.6, center 306
            (260.2, 351.8),  # width 91.6, center 306
        ]
        para = _line_para(lines)
        assert detect_paragraph_alignment(para) == "center"

    def test_multiline_left_aligned_body(self):
        # Two-column body: same left edge, full-ish equal widths
        lines = [
            (52.0, 297.0),
            (52.0, 296.5),
            (52.0, 297.2),
            (52.0, 295.0),
        ]
        para = _line_para(lines)
        assert detect_paragraph_alignment(para) == "left"

    def test_near_full_width_lines_never_center(self):
        """Even if line centers cluster, near-full-width body stays left."""
        # Centers near 300, widths still ~75%+ of para span
        lines = [
            (86.0, 520.0),
            (90.0, 510.0),
            (95.0, 505.0),
            (100.0, 490.0),
        ]
        para = _line_para(lines)
        assert detect_paragraph_alignment(para) == "left"

    def test_left_aligned_body_with_short_last_line(self):
        """Regression: full lines have lm≈rm≈0; short last line must NOT
        flip the paragraph to center (the Orgasms ebook false positive)."""
        lines = [
            (56.0, 560.0),  # full
            (56.0, 558.0),  # full
            (56.0, 555.0),  # full
            (56.0, 200.0),  # short last line, flush left
        ]
        para = _line_para(lines)
        assert detect_paragraph_alignment(para) == "left"

    def test_left_aligned_body_near_full_page(self):
        # Near-full-width left body as on the dual PDF English side
        lines = [
            (56.0, 560.0),
            (56.0, 550.0),
            (56.0, 555.0),
            (56.0, 400.0),
        ]
        para = _line_para(lines)
        assert detect_paragraph_alignment(para, _page(612)) == "left"

    def test_title_label_does_not_force_center(self):
        # Ebook section headings are often left-aligned but labeled "title"
        # by DocLayout — must stay left, not float to center of wide box.
        para = _line_para([(56.0, 490.0)], label="title")
        assert detect_paragraph_alignment(para, _page(612)) == "left"

    def test_left_aligned_section_heading_stays_left(self):
        # Short Chinese heading after translation of a left-aligned EN heading
        # with a wide original box: geometry is left-edge at page margin.
        para = _line_para([(56.0, 490.3)], label="title")  # Working Out... style
        assert detect_paragraph_alignment(para, _page(612)) == "left"

    def test_single_line_page_centered(self):
        # Single title line centered on page (L≈R page margins)
        para = _line_para([(63.9, 548.1)])  # center 306, page 612
        assert detect_paragraph_alignment(para, _page(612)) == "center"

    def test_single_line_column_not_center(self):
        # Left column body line — not page-centered
        para = _line_para([(52.0, 297.0)])
        assert detect_paragraph_alignment(para, _page(612)) == "left"

    def test_right_aligned(self):
        lines = [
            (100.0, 300.0),
            (150.0, 300.0),
            (200.0, 300.0),
        ]
        para = _line_para(lines)
        assert detect_paragraph_alignment(para) == "right"


class TestResolveEffectiveAlignment:
    def test_long_body_without_metrics_never_center(self):
        """Legacy path (no reference_metrics): length gate still demotes."""
        para = PdfParagraph(
            box=Box(x=56, y=100, x2=540, y2=200),
            pdf_style=PdfStyle(font_id="base", font_size=14.0, graphic_state=None),
            pdf_paragraph_composition=[],
            unicode="前三个星期，请仅在阴茎松弛状态下进行凯格尔训练。" * 2,
        )
        para.alignment = "center"
        assert Typesetting._resolve_effective_alignment(para) == "left"

    def test_short_centered_title_kept(self):
        para = PdfParagraph(
            box=Box(x=200, y=100, x2=400, y2=120),
            pdf_style=PdfStyle(font_id="base", font_size=14.0, graphic_state=None),
            pdf_paragraph_composition=[],
            unicode="操作指南",
        )
        para.alignment = "center"
        assert Typesetting._resolve_effective_alignment(para) == "center"

    def test_single_line_title_kept_despite_full_box_metrics(self):
        """arXiv title: one centered line fills its own box; must stay center."""
        from babeldoc.format.pdf.document_il.il_version_1 import ReferenceMetrics

        para = PdfParagraph(
            box=Box(x=63.9, y=700, x2=548.3, y2=720),
            pdf_style=PdfStyle(font_id="base", font_size=14.0, graphic_state=None),
            pdf_paragraph_composition=[],
            unicode="超导量子比特读出的基准测试：针对重复测量",
        )
        para.alignment = "center"
        para.reference_metrics = ReferenceMetrics(
            line_count=1,
            avg_line_width=484.4,
            last_line_width=484.4,
            last_line_ratio=1.0,
            font_size=12.0,
            per_line_widths=[484.4],
        )
        assert Typesetting._resolve_effective_alignment(para) == "center"
        # Many CJK units must not demote either
        units = [SimpleNamespace(width=12.0) for _ in range(40)]
        assert Typesetting._resolve_effective_alignment(para, units) == "center"

    def test_long_translated_author_block_stays_center(self):
        """arXiv author/affil: multi-line page-centered; ZH long but still center."""
        from babeldoc.format.pdf.document_il.il_version_1 import ReferenceMetrics

        para = PdfParagraph(
            box=Box(x=78.6, y=650, x2=533.1, y2=700),
            pdf_style=PdfStyle(font_id="base", font_size=10.0, graphic_state=None),
            pdf_paragraph_composition=[],
            unicode=(
                "1美国康涅狄格州纽黑文市06520 耶鲁大学应用物理系，"
                "以及美国康涅狄格州纽黑文市06520 耶鲁大学耶鲁量子研究所"
                "（日期：2024 年7 月16 日）"
            ),
        )
        para.alignment = "center"
        # Varying inset line widths like the golden paper header
        para.reference_metrics = ReferenceMetrics(
            line_count=4,
            avg_line_width=313.0,
            last_line_width=91.9,
            last_line_ratio=0.29,
            font_size=10.0,
            per_line_widths=[454.4, 361.7, 346.9, 91.9],
        )
        assert Typesetting._resolve_effective_alignment(para) == "center"

    def test_body_like_multiline_forced_left(self):
        from babeldoc.format.pdf.document_il.il_version_1 import ReferenceMetrics

        para = PdfParagraph(
            box=Box(x=56, y=100, x2=540, y2=200),
            pdf_style=PdfStyle(font_id="base", font_size=14.0, graphic_state=None),
            pdf_paragraph_composition=[],
            unicode="Short",
        )
        para.alignment = "center"
        para.reference_metrics = ReferenceMetrics(
            line_count=4,
            avg_line_width=450.0,
            last_line_width=200.0,
            last_line_ratio=0.4,
            font_size=14.0,
            per_line_widths=[450, 440, 445, 200],
        )
        assert Typesetting._resolve_effective_alignment(para) == "left"


class TestEffectiveFirstLineIndent:
    def test_caps_indent_when_first_line_would_be_one_glyph(self):
        para = PdfParagraph(
            box=Box(x=56, y=100, x2=160, y2=120),
            pdf_style=PdfStyle(font_id="base", font_size=14.0, graphic_state=None),
            pdf_paragraph_composition=[],
            unicode="如何在性爱中进行凯格尔运动",
            first_line_indent=80.0,  # would leave ~24pt
        )
        units = [SimpleNamespace(width=14.0, is_space=False) for _ in range(10)]
        indent = Typesetting._effective_first_line_indent(
            para,
            para.box,
            available_x=56.0,
            available_x2=160.0,
            scale=1.0,
            typesetting_units=units,
        )
        # Must leave ~4 glyphs * 14 ≈ 56pt
        assert (160.0 - (56.0 + indent)) >= 50.0

    def test_keeps_normal_indent(self):
        para = PdfParagraph(
            box=Box(x=56, y=100, x2=500, y2=200),
            pdf_style=PdfStyle(font_id="base", font_size=14.0, graphic_state=None),
            pdf_paragraph_composition=[],
            unicode="正文",
            first_line_indent=12.0,
        )
        units = [SimpleNamespace(width=14.0, is_space=False) for _ in range(20)]
        indent = Typesetting._effective_first_line_indent(
            para, para.box, 56.0, 500.0, 1.0, units
        )
        assert indent == pytest.approx(12.0)

    def test_indent_is_absolute_not_scaled(self):
        """EN visual indent is in user space; glyph scale must not shrink it."""
        para = PdfParagraph(
            box=Box(x=56, y=100, x2=500, y2=200),
            pdf_style=PdfStyle(font_id="base", font_size=14.0, graphic_state=None),
            pdf_paragraph_composition=[],
            unicode="正文",
            first_line_indent=20.0,
        )
        units = [SimpleNamespace(width=14.0, is_space=False) for _ in range(20)]
        at_half = Typesetting._effective_first_line_indent(
            para, para.box, 56.0, 500.0, 0.5, units
        )
        at_full = Typesetting._effective_first_line_indent(
            para, para.box, 56.0, 500.0, 1.0, units
        )
        assert at_half == pytest.approx(20.0)
        assert at_full == pytest.approx(20.0)

    def test_parse_legacy_string_indent(self):
        para = PdfParagraph(
            box=Box(x=0, y=0, x2=100, y2=20),
            pdf_style=PdfStyle(font_id="base", font_size=10.0, graphic_state=None),
            pdf_paragraph_composition=[],
            unicode="x",
            first_line_indent="18.5",
        )
        assert Typesetting._parse_first_line_indent(para) == pytest.approx(18.5)
        para.first_line_indent = "true"
        assert Typesetting._parse_first_line_indent(para) == pytest.approx(12.0)
        para.first_line_indent = False
        assert Typesetting._parse_first_line_indent(para) == 0.0


class TestApplyLineHorizontalAlignment:
    def _unit_at(self, x: float, width: float = 10.0) -> TypesettingUnit:
        ch = _char(x, x + width)
        return TypesettingUnit(char=ch)

    def test_center_shifts_short_line(self):
        # Line placed left-to-right at x=50..80 within available 50..250
        units = [self._unit_at(50), self._unit_at(60), self._unit_at(70)]
        Typesetting._apply_line_horizontal_alignment(
            units, 0, 3, available_x=50.0, available_x2=250.0, alignment="center"
        )
        # line width = 30, avail = 200, offset = (200-30)/2 = 85 → start at 135
        assert units[0].box.x == pytest.approx(135.0, abs=0.1)
        assert units[2].box.x2 == pytest.approx(165.0, abs=0.1)

    def test_left_alignment_no_shift(self):
        units = [self._unit_at(50), self._unit_at(60)]
        Typesetting._apply_line_horizontal_alignment(
            units, 0, 2, available_x=50.0, available_x2=250.0, alignment="left"
        )
        assert units[0].box.x == pytest.approx(50.0)
        assert units[1].box.x == pytest.approx(60.0)

    def test_right_alignment(self):
        units = [self._unit_at(50), self._unit_at(60), self._unit_at(70)]
        Typesetting._apply_line_horizontal_alignment(
            units, 0, 3, available_x=50.0, available_x2=250.0, alignment="right"
        )
        # line width 30, target left = 250-30 = 220
        assert units[0].box.x == pytest.approx(220.0, abs=0.1)
        assert units[2].box.x2 == pytest.approx(250.0, abs=0.1)

    def test_full_width_line_no_shift(self):
        units = [self._unit_at(50, width=200)]
        Typesetting._apply_line_horizontal_alignment(
            units, 0, 1, available_x=50.0, available_x2=250.0, alignment="center"
        )
        assert units[0].box.x == pytest.approx(50.0)


class TestLayoutStyleConsistency:
    """End-to-end style: indent + center in production layout path (PR-07)."""

    def _unit(self, ch: str = "中", width: float = 10.0, height: float = 12.0):
        box = Box(x=0, y=0, x2=width, y2=height)
        char = PdfCharacter(
            char_unicode=ch,
            box=box,
            visual_bbox=VisualBbox(box=Box(x=0, y=0, x2=width, y2=height)),
            pdf_style=PdfStyle(font_id="base", font_size=10.0, graphic_state=None),
        )
        return TypesettingUnit(char=char)

    def _typesetting(self):
        from unittest.mock import MagicMock

        from babeldoc.format.pdf.translation_config import TranslationConfig
        from babeldoc.translator.fixed_map_translator import FixedMapTranslator

        cfg = TranslationConfig(
            translator=FixedMapTranslator(),
            input_file="style.pdf",
            lang_in="en",
            lang_out="zh-CN",
            doc_layout_model=MagicMock(),
            auto_extract_glossary=False,
        )
        return Typesetting(cfg)

    def test_layout_applies_first_line_indent(self):
        ts = self._typesetting()
        box = Box(x=50, y=100, x2=350, y2=400)
        para = PdfParagraph(
            box=box,
            pdf_style=PdfStyle(font_id="base", font_size=10.0, graphic_state=None),
            pdf_paragraph_composition=[],
            unicode="测试段落",
            first_line_indent=24.0,
            alignment="left",
        )
        units = [self._unit(width=10.0) for _ in range(8)]
        placed, _ = ts._layout_typesetting_units(
            units,
            box,
            scale=1.0,
            line_skip=1.05,
            paragraph=para,
            use_english_line_break=False,
            break_points=None,
            reference_widths=None,
        )
        assert placed
        assert placed[0].box.x == pytest.approx(74.0, abs=0.5)  # 50 + 24

    def test_layout_center_short_title(self):
        ts = self._typesetting()
        box = Box(x=50, y=100, x2=350, y2=150)
        para = PdfParagraph(
            box=box,
            pdf_style=PdfStyle(font_id="base", font_size=10.0, graphic_state=None),
            pdf_paragraph_composition=[],
            unicode="标题",
            first_line_indent=0.0,
            alignment="center",
        )
        # Two 10pt glyphs → line width 20; available 300 → start at 50+(300-20)/2=190
        units = [self._unit(ch="标", width=10.0), self._unit(ch="题", width=10.0)]
        placed, _ = ts._layout_typesetting_units(
            units,
            box,
            scale=1.0,
            line_skip=1.05,
            paragraph=para,
            use_english_line_break=False,
            break_points=None,
        )
        assert placed
        assert placed[0].box.x == pytest.approx(190.0, abs=1.0)

    def test_layout_center_long_zh_title_with_metrics(self):
        """Long ZH title still centers when original single-line was page-centered."""
        from babeldoc.format.pdf.document_il.il_version_1 import ReferenceMetrics

        ts = self._typesetting()
        box = Box(x=63.9, y=100, x2=548.3, y2=130)
        para = PdfParagraph(
            box=box,
            pdf_style=PdfStyle(font_id="base", font_size=12.0, graphic_state=None),
            pdf_paragraph_composition=[],
            unicode="超导量子比特读出的基准测试：针对重复测量",
            first_line_indent=0.0,
            alignment="center",
        )
        para.reference_metrics = ReferenceMetrics(
            line_count=1,
            avg_line_width=484.4,
            last_line_width=484.4,
            last_line_ratio=1.0,
            font_size=12.0,
            per_line_widths=[484.4],
        )
        units = [
            self._unit(ch=c, width=12.0)
            for c in "超导量子比特读出的基准测试：针对重复测量"
        ]
        placed, _ = ts._layout_typesetting_units(
            units,
            box,
            scale=1.0,
            line_skip=1.05,
            paragraph=para,
            use_english_line_break=False,
        )
        assert placed
        # Must not sit at box.x (left); should be shifted toward page center
        assert placed[0].box.x > 100.0
        line_w = placed[-1].box.x2 - placed[0].box.x
        expected_start = box.x + (box.x2 - box.x - line_w) / 2.0
        assert placed[0].box.x == pytest.approx(expected_start, abs=2.0)

    def test_center_ignores_first_line_indent(self):
        ts = self._typesetting()
        box = Box(x=50, y=100, x2=350, y2=150)
        para = PdfParagraph(
            box=box,
            pdf_style=PdfStyle(font_id="base", font_size=10.0, graphic_state=None),
            pdf_paragraph_composition=[],
            unicode="标题",
            first_line_indent=40.0,
            alignment="center",
        )
        units = [self._unit(ch="标", width=10.0), self._unit(ch="题", width=10.0)]
        placed, _ = ts._layout_typesetting_units(
            units,
            box,
            scale=1.0,
            line_skip=1.05,
            paragraph=para,
            use_english_line_break=False,
        )
        assert placed
        # Still centered as if no indent (not left+40)
        assert placed[0].box.x == pytest.approx(190.0, abs=1.0)

    def test_estimate_first_line_width_subtracts_indent(self):
        ts = self._typesetting()
        box = Box(x=0, y=100, x2=200, y2=400)
        para = PdfParagraph(
            box=box,
            pdf_style=PdfStyle(font_id="base", font_size=10.0, graphic_state=None),
            pdf_paragraph_composition=[],
            unicode="正文" * 20,
            first_line_indent=30.0,
            alignment="left",
        )
        units = [self._unit() for _ in range(12)]
        widths = ts._estimate_line_widths(
            units,
            box,
            scale=1.0,
            avg_height=12.0,
            line_skip=1.05,
            paragraph=para,
        )
        assert widths
        assert widths[0] == pytest.approx(170.0)  # 200 - 30
        if len(widths) > 1:
            assert widths[1] == pytest.approx(200.0)

    def test_indent_noop_when_zone_already_past_indent(self):
        """Left figure residual starts past box.x+indent → no extra indent shift."""
        from babeldoc.format.pdf.document_il.midend.exclusion_zone import (
            ExclusionZone,
            ExclusionZoneIndex,
            ZONE_FIGURE,
        )

        ts = self._typesetting()
        # Figure covers [0, 200]; body residual starts at 200
        ts._current_zone_index = ExclusionZoneIndex(
            [
                ExclusionZone(
                    box=Box(x=0, y=100, x2=200, y2=400),
                    kind=ZONE_FIGURE,
                    priority=20,
                )
            ]
        )
        box = Box(x=0, y=100, x2=500, y2=400)
        para = PdfParagraph(
            box=box,
            pdf_style=PdfStyle(font_id="base", font_size=10.0, graphic_state=None),
            pdf_paragraph_composition=[],
            unicode="正文",
            first_line_indent=24.0,
            alignment="left",
        )
        units = [self._unit(width=10.0) for _ in range(5)]
        placed, _ = ts._layout_typesetting_units(
            units,
            box,
            scale=1.0,
            line_skip=1.05,
            paragraph=para,
            use_english_line_break=False,
        )
        assert placed
        # Start at residual left (200), not 0+24
        assert placed[0].box.x == pytest.approx(200.0, abs=0.5)

        widths = ts._estimate_line_widths(
            units, box, 1.0, 12.0, 1.05, paragraph=para
        )
        # Full residual 300; indent adds no lost capacity (line_start==ix1)
        assert widths[0] == pytest.approx(300.0)
