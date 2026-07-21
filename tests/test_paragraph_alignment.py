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
        assert detect_paragraph_alignment(para, _page(612)) == "center"

    def test_arxiv_affil_date_page_symmetric_center(self):
        """Affiliation lines share a near-left edge but each is page-centered.

        Without page geometry this used to return left (left_ratio ≥ 0.65),
        so ZH lines 3–4 of translate.cli.text.with.figure sat left of mid.
        """
        lines = [
            (125.3, 487.0),  # center 306.15
            (132.7, 479.6),  # center 306.15
            (260.2, 352.1),  # date, center 306.15
        ]
        para = _line_para(lines)
        assert detect_paragraph_alignment(para, _page(612)) == "center"
        # affil only (no date) must also stay center
        para2 = _line_para(lines[:2])
        assert detect_paragraph_alignment(para2, _page(612)) == "center"

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

    def test_atu_p4_survey_body_not_page_symmetric_center(self):
        """All Tied Up book p4 above Nice Rack: flush-left EN body.

        Two/three full-measure lines at x=56 have lm≈rm and mid-page centers;
        page-symmetric detection must not call that a centered header.
        """
        # Para 2: survey (3 lines, short last)
        para2 = _line_para(
            [
                (56.0, 557.2),
                (56.0, 559.2),
                (56.0, 175.4),
            ]
        )
        assert detect_paragraph_alignment(para2, _page(612)) == "left"
        # Para 3: two thirds (2 lines, both fairly full — the hard case)
        para3 = _line_para(
            [
                (56.0, 546.1),
                (56.0, 480.2),
            ]
        )
        assert detect_paragraph_alignment(para3, _page(612)) == "left"
        # 2 full lines without short tail (if last EN line split off)
        para2_only = _line_para(
            [
                (56.0, 557.2),
                (56.0, 559.2),
            ]
        )
        assert detect_paragraph_alignment(para2_only, _page(612)) == "left"

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
        # arXiv-style title: L≈R margins both ≥60, mid at page center
        # (golden translate.cli.text.with.figure first line)
        para = _line_para([(63.9, 548.1)])  # lm=rm≈64, center 306, page 612
        assert detect_paragraph_alignment(para, _page(612)) == "center"

    def test_single_line_flush_left_fullish_not_center(self):
        """ATU p7 lead-in / p13 TECHNIQUE title: flush left ~0.8 page wide."""
        # w=490, center≈301, left@56 — lm=56 < 60 fails true-center margins
        para = _line_para([(56.0, 546.0)])
        assert detect_paragraph_alignment(para, _page(612)) == "left"
        para_title = _line_para([(56.0, 558.0)], label="title")
        assert detect_paragraph_alignment(para_title, _page(612)) == "left"

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

    def test_two_line_affil_after_date_split_stays_center(self):
        """Regression: date split leaves a 2-line affil with fullish≈1 vs tight box.

        Must NOT demote to left — dual header lines 3–4 were page-left by ~47pt.
        """
        from babeldoc.format.pdf.document_il.il_version_1 import ReferenceMetrics

        para = PdfParagraph(
            box=Box(x=125.3, y=90, x2=487.0, y2=113),
            pdf_style=PdfStyle(font_id="base", font_size=10.0, graphic_state=None),
            pdf_paragraph_composition=[],
            unicode=(
                "鲁大学应用物理系，美国康涅狄格州纽黑文市06520，"
                "以及耶鲁大学耶鲁量子研究所，美国康涅狄格州纽黑文市06520"
            ),
        )
        para.alignment = "center"
        para.reference_metrics = ReferenceMetrics(
            line_count=2,
            avg_line_width=354.3,
            last_line_width=346.9,
            last_line_ratio=346.9 / 354.3,
            font_size=10.0,
            per_line_widths=[361.7, 346.9],
        )
        assert Typesetting._resolve_effective_alignment(para, is_cjk=True) == "center"

    def test_atu_p4_full_measure_body_demotes_even_if_tagged_center(self):
        """Safety net: EN max line ≥470pt (ebook full measure) + CJK → left.

        tight_header used to block demotion because body also has fullish≈1
        relative to its own box — same as arXiv tight headers.
        """
        from babeldoc.format.pdf.document_il.il_version_1 import ReferenceMetrics

        zh = (
            "最近的一项全国性调查清楚地表明，与伴侣一起参加各种性活动的女性"
            "更有可能经历和享受高潮体验"
        )
        para = PdfParagraph(
            box=Box(x=56, y=100, x2=560, y2=180),
            pdf_style=PdfStyle(font_id="base", font_size=14.0, graphic_state=None),
            pdf_paragraph_composition=[],
            unicode=zh,
        )
        para.alignment = "center"
        para.reference_metrics = ReferenceMetrics(
            line_count=2,
            avg_line_width=490.0,
            last_line_width=480.0,
            last_line_ratio=0.98,
            font_size=14.0,
            per_line_widths=[500.0, 480.0],
        )
        assert Typesetting._resolve_effective_alignment(para, is_cjk=True) == "left"

        # Short last line must not drag max below threshold
        para2 = PdfParagraph(
            box=Box(x=56, y=100, x2=560, y2=200),
            pdf_style=PdfStyle(font_id="base", font_size=14.0, graphic_state=None),
            pdf_paragraph_composition=[],
            unicode=zh,
        )
        para2.alignment = "center"
        para2.reference_metrics = ReferenceMetrics(
            line_count=3,
            avg_line_width=370.0,
            last_line_width=117.0,
            last_line_ratio=0.23,
            font_size=14.0,
            per_line_widths=[498.0, 497.0, 117.0],
        )
        assert Typesetting._resolve_effective_alignment(para2, is_cjk=True) == "left"

        # Metrics collapsed to 1 line but box is still full-measure body
        para1 = PdfParagraph(
            box=Box(x=56, y=100, x2=558, y2=120),
            pdf_style=PdfStyle(font_id="base", font_size=14.0, graphic_state=None),
            pdf_paragraph_composition=[],
            unicode=zh,
        )
        para1.alignment = "center"
        para1.reference_metrics = ReferenceMetrics(
            line_count=1,
            avg_line_width=501.0,
            last_line_width=501.0,
            last_line_ratio=1.0,
            font_size=14.0,
            per_line_widths=[501.0],
        )
        assert Typesetting._resolve_effective_alignment(para1, is_cjk=True) == "left"

    def test_atu_p7_short_leadin_demotes_despite_short_zh(self):
        """p7 safety lead-in ~24 CJK chars from full-measure EN must go left."""
        from babeldoc.format.pdf.document_il.il_version_1 import ReferenceMetrics

        zh = "在捆绑安全方面，您需要采取一些基本的预防措施。"
        para = PdfParagraph(
            box=Box(x=56, y=100, x2=546, y2=120),
            pdf_style=PdfStyle(font_id="base", font_size=14.0, graphic_state=None),
            pdf_paragraph_composition=[],
            unicode=zh,
        )
        para.alignment = "center"
        para.reference_metrics = ReferenceMetrics(
            line_count=1,
            avg_line_width=490.0,
            last_line_width=490.0,
            last_line_ratio=1.0,
            font_size=14.0,
            per_line_widths=[490.0],
        )
        assert Typesetting._resolve_effective_alignment(para, is_cjk=True) == "left"
        # Section title style
        para.layout_label = "title"
        para.unicode = "技术1：简单领带"
        assert Typesetting._resolve_effective_alignment(para, is_cjk=True) == "left"

    def test_atu_long_cjk_centered_en_block_demotes_left(self):
        """All Tied Up p5-style: short centered EN lines → long ZH must flush-left."""
        from babeldoc.format.pdf.document_il.il_version_1 import ReferenceMetrics

        long_zh = (
            "最近的一项全国性调查清楚地表明，与伴侣一起参加各种性活动的女性"
            "更有可能经历和享受高潮体验。在这个世界上，有近三分之二的女性"
            "在来访时感到困难重重，这应该足以成为您尝试新事物的理由！"
        )
        cases = [
            # Real ATU: often ONE centered EN line → multi-line ZH
            ("single_en_line", 1, [320.0], 1.0),
            ("uniform", 4, [280.0, 240.0, 260.0, 140.0], 0.50),
            ("mild_taper", 4, [280.0, 240.0, 200.0, 100.0], 100 / 280),
        ]
        for name, nline, widths, last_r in cases:
            para = PdfParagraph(
                box=Box(x=100, y=100, x2=100 + max(widths), y2=280),
                pdf_style=PdfStyle(font_id="base", font_size=11.0, graphic_state=None),
                pdf_paragraph_composition=[],
                unicode=long_zh,
            )
            para.alignment = "center"
            para.reference_metrics = ReferenceMetrics(
                line_count=nline,
                avg_line_width=sum(widths) / len(widths),
                last_line_width=widths[-1],
                last_line_ratio=last_r,
                font_size=11.0,
                per_line_widths=widths,
            )
            assert (
                Typesetting._resolve_effective_alignment(para, is_cjk=True) == "left"
            ), name
        # Non-CJK: single-line centered EN stays center (no ZH-overflow demotion)
        para_en = PdfParagraph(
            box=Box(x=100, y=100, x2=420, y2=120),
            pdf_style=PdfStyle(font_id="base", font_size=11.0, graphic_state=None),
            pdf_paragraph_composition=[],
            unicode="And the cherry on top of it all? More survey text here.",
        )
        para_en.alignment = "center"
        para_en.reference_metrics = ReferenceMetrics(
            line_count=1,
            avg_line_width=320.0,
            last_line_width=320.0,
            last_line_ratio=1.0,
            font_size=11.0,
            per_line_widths=[320.0],
        )
        assert (
            Typesetting._resolve_effective_alignment(para_en, is_cjk=False) == "center"
        )


class TestLooksLikeListItem:
    def test_numbered_forms(self):
        # Include MT ``2。`` (ideographic full stop) — real ATU dual markers
        for text in (
            "1. 第一步",
            "2、第二步",
            "3) 第三",
            "(4) 第四",
            "① 圆圈",
            "2。永远、永远、永远",
            "5.\xa0保持清醒",
        ):
            para = PdfParagraph(
                box=Box(x=0, y=0, x2=100, y2=20),
                pdf_style=PdfStyle(font_id="base", font_size=10.0, graphic_state=None),
                pdf_paragraph_composition=[],
                unicode=text,
            )
            assert Typesetting._looks_like_numbered_list_item(para), text

    def test_body_not_list(self):
        para = PdfParagraph(
            box=Box(x=0, y=0, x2=100, y2=20),
            pdf_style=PdfStyle(font_id="base", font_size=10.0, graphic_state=None),
            pdf_paragraph_composition=[],
            unicode="在这个世界上，有近三分之二的女性",
        )
        assert not Typesetting._looks_like_numbered_list_item(para)


class TestReattachTrailingListMarkers:
    """ATU dual p21: ``4.``/``5.`` glued onto prior item ends → hang broken."""

    def _para(self, text: str) -> PdfParagraph:
        from babeldoc.format.pdf.document_il.il_version_1 import (
            PdfSameStyleUnicodeCharacters,
        )

        ssu = PdfSameStyleUnicodeCharacters(
            unicode=text,
            pdf_style=PdfStyle(font_id="base", font_size=11.0, graphic_state=None),
        )
        return PdfParagraph(
            box=Box(x=56, y=100, x2=360, y2=200),
            pdf_style=PdfStyle(font_id="base", font_size=11.0, graphic_state=None),
            pdf_paragraph_composition=[
                PdfParagraphComposition(pdf_same_style_unicode_characters=ssu)
            ],
            unicode=text,
        )

    def test_atu_p21_items_3_to_5_reattach(self):
        """Item3 ends ``。4.``; item4 body ends ``。5.``; item5 body has no serial."""
        p3 = self._para(
            "3。您可以尝试打第四个结，使其紧贴阴蒂。"
            "试一试，做做实验，不断变化，直到恰到好处。4."
        )
        p4 = self._para(
            "将打结的绳子从她两腿之间拉到背上，绕到后颈的绳子下面，"
            "然后拉过来，让绳子垂下来。5."
        )
        p5 = self._para(
            "现在把两股绳子分开，分别放在她身体的两侧。现在情况变得复杂了。"
        )
        # Body-only box after serial theft sits at hang column (~92).
        p5.box = Box(x=92.0, y=100, x2=360, y2=200)
        p5.first_line_indent = 18.0
        p6 = self._para("6。将绳子拉到她腋下，在她身体两侧各拉一根。")

        n = Typesetting.reattach_trailing_list_markers([p3, p4, p5, p6])
        assert n == 2
        assert p3.unicode.endswith("恰到好处。")
        assert not p3.unicode.rstrip().endswith("4.")
        assert Typesetting._looks_like_numbered_list_item(p4)
        assert p4.unicode.startswith("4.")
        assert "垂下来。" in p4.unicode and not p4.unicode.rstrip().endswith("5.")
        assert Typesetting._looks_like_numbered_list_item(p5)
        assert p5.unicode.startswith("5.")
        assert "复杂了" in p5.unicode
        # Snap body-only box left to list gutter; clear indent for hang.
        assert p5.box.x == pytest.approx(56.0)
        assert float(p5.first_line_indent or 0) == 0.0
        # item 6 unchanged
        assert p6.unicode.startswith("6。")
        # compositions stay in sync for typesetting units
        assert p4.pdf_paragraph_composition[0].pdf_same_style_unicode_characters.unicode.startswith(
            "4."
        )
        assert p5.pdf_paragraph_composition[0].pdf_same_style_unicode_characters.unicode.startswith(
            "5."
        )

    def test_does_not_steal_prose_number(self):
        """``The answer is 42.`` must not reattach ``42.`` onto the next para."""
        a = self._para("The answer is 42.")
        b = self._para("More prose continues on the next paragraph without a list.")
        n = Typesetting.reattach_trailing_list_markers([a, b])
        assert n == 0
        assert a.unicode == "The answer is 42."
        assert not Typesetting._looks_like_numbered_list_item(b)

    def test_skips_when_next_already_has_marker(self):
        a = self._para("3。直到恰到好处。4.")
        b = self._para("4。将打结的绳子从她两腿之间拉到背上。")
        n = Typesetting.reattach_trailing_list_markers([a, b])
        assert n == 0
        assert a.unicode.endswith("4.")

    def test_list_item_forces_left_even_if_center_geometry(self):
        """ATU safety list: short multi-line items false-center without this."""
        para = PdfParagraph(
            box=Box(x=100, y=100, x2=400, y2=160),
            pdf_style=PdfStyle(font_id="base", font_size=11.0, graphic_state=None),
            pdf_paragraph_composition=[],
            unicode="2。永远、永远、永远不要让被捆绑者独自留在房间里，哪怕只有一分钟。",
            alignment="center",
        )
        assert (
            Typesetting._resolve_effective_alignment(para, is_cjk=True) == "left"
        )


class TestListMarkerHangWidth:
    """Hanging indent under body after serial (EN dual golden list vs flush ZH)."""

    def _units_for(self, text: str, *, char_w: float = 10.0):
        units = []
        for ch in text:
            u = SimpleNamespace(
                width=char_w * (0.55 if ch.isascii() else 1.0),
                is_space=(ch == " "),
                unicode=ch,
            )
            u.try_get_unicode = lambda c=ch: c
            units.append(u)
        return units

    def test_measures_marker_including_trailing_space(self):
        text = "2. 永远、永远、永远不要将被捆绑者单独留在房间里"
        para = PdfParagraph(
            box=Box(x=56, y=100, x2=360, y2=200),
            pdf_style=PdfStyle(font_id="base", font_size=11.0, graphic_state=None),
            pdf_paragraph_composition=[],
            unicode=text,
        )
        units = self._units_for(text, char_w=10.0)
        hang = Typesetting._list_marker_hang_width(para, units, scale=1.0)
        # "2. " → digit 0.55*10 + '.' 0.55*10 + space 0.55*10 ≈ 16.5
        assert 12.0 <= hang <= 22.0

    def test_body_paragraph_zero_hang(self):
        para = PdfParagraph(
            box=Box(x=56, y=100, x2=360, y2=200),
            pdf_style=PdfStyle(font_id="base", font_size=11.0, graphic_state=None),
            pdf_paragraph_composition=[],
            unicode="在捆绑安全方面，您需要采取一些基本的预防措施。",
        )
        units = self._units_for(para.unicode, char_w=12.0)
        assert Typesetting._list_marker_hang_width(para, units, scale=1.0) == 0.0

    def test_cjk_enumeration_marker(self):
        text = "1、一定要使用安全词"
        para = PdfParagraph(
            box=Box(x=56, y=100, x2=360, y2=200),
            pdf_style=PdfStyle(font_id="base", font_size=11.0, graphic_state=None),
            pdf_paragraph_composition=[],
            unicode=text,
        )
        units = self._units_for(text, char_w=12.0)
        hang = Typesetting._list_marker_hang_width(para, units, scale=1.0)
        # "1、" — digit + fullwidth punct, no trailing space in text
        assert hang >= 10.0

    def test_inset_only_on_wrap_lines_not_ocr(self):
        text = "2. 永远永远"
        para = PdfParagraph(
            box=Box(x=56, y=100, x2=360, y2=200),
            pdf_style=PdfStyle(font_id="base", font_size=11.0, graphic_state=None),
            pdf_paragraph_composition=[],
            unicode=text,
        )
        units = self._units_for(text, char_w=10.0)
        raw = Typesetting._list_marker_hang_width(para, units, scale=1.0)
        assert raw > 8.0
        # first line: no hang
        assert (
            Typesetting._numbered_list_hang_inset(
                para,
                units,
                1.0,
                line_idx=0,
                alignment="left",
                ocr_workaround=False,
                pocket_span=300.0,
            )
            == 0.0
        )
        # wrap line: hang
        wrap_hang = Typesetting._numbered_list_hang_inset(
            para,
            units,
            1.0,
            line_idx=1,
            alignment="left",
            ocr_workaround=False,
            pocket_span=300.0,
        )
        assert wrap_hang == pytest.approx(raw, abs=0.01)
        # OCR: hang off (estimate must match place)
        assert (
            Typesetting._numbered_list_hang_inset(
                para,
                units,
                1.0,
                line_idx=1,
                alignment="left",
                ocr_workaround=True,
                pocket_span=300.0,
            )
            == 0.0
        )

    def test_inset_leftmost_interval_preserves_rest(self):
        intervals = [(50.0, 200.0), (220.0, 300.0)]
        out = Typesetting._inset_leftmost_interval(intervals, 16.5)
        assert out[0] == pytest.approx((66.5, 200.0))
        assert out[1] == (220.0, 300.0)


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

    def test_list_item_drops_indent(self):
        para = PdfParagraph(
            box=Box(x=56, y=100, x2=500, y2=200),
            pdf_style=PdfStyle(font_id="base", font_size=14.0, graphic_state=None),
            pdf_paragraph_composition=[],
            unicode="1. 让她把双臂或双腿放在您的腿上",
            first_line_indent=40.0,
        )
        units = [SimpleNamespace(width=14.0, is_space=False) for _ in range(20)]
        indent = Typesetting._effective_first_line_indent(
            para, para.box, 56.0, 500.0, 1.0, units
        )
        assert indent == 0.0

    def test_extreme_indent_dropped(self):
        """Centered short first line often becomes huge first_line_indent."""
        para = PdfParagraph(
            box=Box(x=56, y=100, x2=500, y2=200),
            pdf_style=PdfStyle(font_id="base", font_size=14.0, graphic_state=None),
            pdf_paragraph_composition=[],
            unicode="正文段落",
            first_line_indent=120.0,  # > 18% of box width
        )
        units = [SimpleNamespace(width=14.0, is_space=False) for _ in range(20)]
        indent = Typesetting._effective_first_line_indent(
            para, para.box, 56.0, 500.0, 1.0, units
        )
        assert indent == 0.0

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

    def test_layout_numbered_list_hanging_indent_on_wrap(self):
        """Wrap lines of ``2. …`` hang under body — match EN dual list style.

        Golden: Screenshot_21-7-2026 list items 2/5 — ZH was flush under digit.
        """
        ts = self._typesetting()
        # Narrow box so body wraps after marker + a few CJK glyphs
        box = Box(x=50, y=100, x2=170, y2=400)
        text = "2. 永远永远永远永远永远永远永远永远"
        para = PdfParagraph(
            box=box,
            pdf_style=PdfStyle(font_id="base", font_size=10.0, graphic_state=None),
            pdf_paragraph_composition=[],
            unicode=text,
            first_line_indent=0.0,
            alignment="left",
        )
        units = []
        for ch in text:
            w = 5.5 if ch.isascii() or ch == " " else 12.0
            units.append(self._unit(ch=ch, width=w))
        hang = Typesetting._list_marker_hang_width(para, units, scale=1.0)
        assert hang > 8.0

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
        # First line: marker at left edge of box
        assert placed[0].box.x == pytest.approx(50.0, abs=0.5)
        # Find first unit that drops to a lower y (wrap)
        y0 = placed[0].box.y
        wrap_units = [u for u in placed if u.box and u.box.y < y0 - 1.0]
        assert wrap_units, "expected at least one wrap line"
        # Continuation starts near available_x + hang, not flush at 50
        assert wrap_units[0].box.x == pytest.approx(50.0 + hang, abs=1.5)
        assert wrap_units[0].box.x > 50.0 + 8.0

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
