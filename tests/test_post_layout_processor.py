"""PostLayoutProcessor 单元测试。"""

from __future__ import annotations

import pytest

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import Document
from babeldoc.format.pdf.document_il.il_version_1 import Page
from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraphComposition
from babeldoc.format.pdf.document_il.midend.post_layout_processor import (
    DocumentContext,
    FixAction,
    GeometryCache,
    LayoutIssue,
    OverlapDetector,
    OverlapFixer,
    OverlapResolver,
    PostLayoutProcessor,
)


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────


def _make_char(x: float, y: float, x2: float, y2: float) -> PdfCharacter:
    """创建一个带 box 的 PdfCharacter。"""
    return PdfCharacter(
        box=Box(x=x, y=y, x2=x2, y2=y2),
        char_unicode="X",
    )


def _make_paragraph(
    chars: list[PdfCharacter],
    *,
    layout_box: Box | None = None,
    render_order: int = 0,
    xobj_id: int | None = None,
) -> PdfParagraph:
    """创建一个包含 pdf_character composition 的 PdfParagraph。"""
    compositions = [
        PdfParagraphComposition(pdf_character=c) for c in chars
    ]
    para = PdfParagraph(
        box=layout_box,
        pdf_paragraph_composition=compositions,
        render_order=render_order,
        xobj_id=xobj_id,
    )
    return para


def _make_page(paragraphs: list[PdfParagraph], page_number: int = 0) -> Page:
    """创建一个包含段落的 Page。"""
    page = Page(pdf_paragraph=paragraphs, page_number=page_number)
    return page


def _make_document(pages: list[Page]) -> Document:
    """创建一个包含页面的 Document。"""
    return Document(page=pages)


# ──────────────────────────────────────────────────────────────
# Test 1: 不重叠 → 0 issues
# ──────────────────────────────────────────────────────────────


class TestNoOverlap:
    """两个不重叠的段落应该产生 0 个 issue。"""

    def test_no_overlap_separate_paragraphs(self):
        # Paragraph A: x=0..100, y=0..50
        para_a = _make_paragraph(
            chars=[_make_char(0, 0, 100, 50)],
            layout_box=Box(x=0, y=0, x2=100, y2=50),
            render_order=0,
        )
        # Paragraph B: x=0..100, y=60..110 (不重叠)
        para_b = _make_paragraph(
            chars=[_make_char(0, 60, 100, 110)],
            layout_box=Box(x=0, y=60, x2=100, y2=110),
            render_order=1,
        )

        page = _make_page([para_a, para_b])
        doc = _make_document([page])

        context = DocumentContext.from_document(doc)
        processor = PostLayoutProcessor(context)
        processor.register_detector(OverlapDetector())
        report = processor.run()

        assert report.metrics.issues_detected == 0
        assert report.metrics.issues_remaining == 0
        assert len(report.issues) == 0

    def test_no_overlap_adjacent_paragraphs(self):
        """边界刚好接触（无重叠）也应该是 0 issue。"""
        # Paragraph A: x=0..100, y=0..50
        para_a = _make_paragraph(
            chars=[_make_char(0, 0, 100, 50)],
            layout_box=Box(x=0, y=0, x2=100, y2=50),
            render_order=0,
        )
        # Paragraph B: x=0..100, y=50..100 (边界接触，不重叠)
        para_b = _make_paragraph(
            chars=[_make_char(0, 50, 100, 100)],
            layout_box=Box(x=0, y=50, x2=100, y2=100),
            render_order=1,
        )

        page = _make_page([para_a, para_b])
        doc = _make_document([page])

        context = DocumentContext.from_document(doc)
        processor = PostLayoutProcessor(context)
        processor.register_detector(OverlapDetector())
        report = processor.run()

        assert report.metrics.issues_detected == 0


# ──────────────────────────────────────────────────────────────
# Test 2: 部分重叠 → 1 issue
# ──────────────────────────────────────────────────────────────


class TestPartialOverlap:
    """两个部分重叠的段落应该产生 1 个 issue。"""

    def test_partial_overlap(self):
        # Paragraph A: x=0..100, y=0..60
        para_a = _make_paragraph(
            chars=[_make_char(0, 0, 100, 60)],
            layout_box=Box(x=0, y=0, x2=100, y2=60),
            render_order=0,
        )
        # Paragraph B: x=0..100, y=40..100 (重叠 y=40..60)
        para_b = _make_paragraph(
            chars=[_make_char(0, 40, 100, 100)],
            layout_box=Box(x=0, y=40, x2=100, y2=100),
            render_order=1,
        )

        page = _make_page([para_a, para_b])
        doc = _make_document([page])

        context = DocumentContext.from_document(doc)
        processor = PostLayoutProcessor(context)
        processor.register_detector(OverlapDetector())
        report = processor.run()

        assert report.metrics.issues_detected == 1
        assert report.metrics.issues_remaining == 1
        assert len(report.issues) == 1

        issue = report.issues[0]
        assert issue.issue_type == "overlap"
        assert issue.iou > 0
        assert issue.coverage > 0

    def test_partial_overlap_x_direction(self):
        """水平方向重叠也应该检测到。"""
        # Paragraph A: x=0..60, y=0..50
        para_a = _make_paragraph(
            chars=[_make_char(0, 0, 60, 50)],
            layout_box=Box(x=0, y=0, x2=60, y2=50),
            render_order=0,
        )
        # Paragraph B: x=40..100, y=0..50 (水平重叠 x=40..60)
        para_b = _make_paragraph(
            chars=[_make_char(40, 0, 100, 50)],
            layout_box=Box(x=40, y=0, x2=100, y2=50),
            render_order=1,
        )

        page = _make_page([para_a, para_b])
        doc = _make_document([page])

        context = DocumentContext.from_document(doc)
        processor = PostLayoutProcessor(context)
        processor.register_detector(OverlapDetector())
        report = processor.run()

        assert report.metrics.issues_detected == 1


# ──────────────────────────────────────────────────────────────
# Test 3: 三个段落链式重叠 → 2 issues（不是 3 或 4）
# ──────────────────────────────────────────────────────────────


class TestChainOverlap:
    """三个段落 A-B, B-C 重叠，应该产生恰好 2 个 issue。"""

    def test_chain_overlap_three_paragraphs(self):
        # Paragraph A: x=0..100, y=0..60
        para_a = _make_paragraph(
            chars=[_make_char(0, 0, 100, 60)],
            layout_box=Box(x=0, y=0, x2=100, y2=60),
            render_order=0,
        )
        # Paragraph B: x=0..100, y=40..100 (与 A 重叠 y=40..60)
        para_b = _make_paragraph(
            chars=[_make_char(0, 40, 100, 100)],
            layout_box=Box(x=0, y=40, x2=100, y2=100),
            render_order=1,
        )
        # Paragraph C: x=0..100, y=80..140 (与 B 重叠 y=80..100，不与 A 重叠)
        para_c = _make_paragraph(
            chars=[_make_char(0, 80, 100, 140)],
            layout_box=Box(x=0, y=80, x2=100, y2=140),
            render_order=2,
        )

        page = _make_page([para_a, para_b, para_c])
        doc = _make_document([page])

        context = DocumentContext.from_document(doc)
        processor = PostLayoutProcessor(context)
        processor.register_detector(OverlapDetector())
        report = processor.run()

        # A-B 重叠, B-C 重叠, A-C 不重叠 → 恰好 2 个 issue
        assert report.metrics.issues_detected == 2
        assert len(report.issues) == 2

        # 验证每对只出现一次（无重复）
        pairs = set()
        for issue in report.issues:
            pair = tuple(sorted(issue.affected_paragraph_ids))
            pairs.add(pair)
        assert len(pairs) == 2

    def test_chain_overlap_all_three(self):
        """三个段落全部互相重叠 → 3 个 issue（C(3,2)=3）。"""
        # Paragraph A: x=0..100, y=0..100
        para_a = _make_paragraph(
            chars=[_make_char(0, 0, 100, 100)],
            layout_box=Box(x=0, y=0, x2=100, y2=100),
            render_order=0,
        )
        # Paragraph B: x=0..100, y=30..130 (与 A 重叠 y=30..100)
        para_b = _make_paragraph(
            chars=[_make_char(0, 30, 100, 130)],
            layout_box=Box(x=0, y=30, x2=100, y2=130),
            render_order=1,
        )
        # Paragraph C: x=0..100, y=60..160 (与 A 重叠 y=60..100, 与 B 重叠 y=60..130)
        para_c = _make_paragraph(
            chars=[_make_char(0, 60, 100, 160)],
            layout_box=Box(x=0, y=60, x2=100, y2=160),
            render_order=2,
        )

        page = _make_page([para_a, para_b, para_c])
        doc = _make_document([page])

        context = DocumentContext.from_document(doc)
        processor = PostLayoutProcessor(context)
        processor.register_detector(OverlapDetector())
        report = processor.run()

        # C(3,2) = 3 个重叠对
        assert report.metrics.issues_detected == 3
        assert len(report.issues) == 3


# ──────────────────────────────────────────────────────────────
# Test 4: GeometryCache 失效后重新计算
# ──────────────────────────────────────────────────────────────


class TestGeometryCacheInvalidation:
    """invalidate() 后 get_geometry() 应该重新计算。"""

    def test_invalidate_recomputes(self):
        cache = GeometryCache()
        para = _make_paragraph(
            chars=[_make_char(0, 0, 100, 50)],
            layout_box=Box(x=0, y=0, x2=100, y2=50),
        )
        cache.bind(0, para)

        # 首次获取
        geom1 = cache.get_geometry(0)
        assert geom1.rendered_box is not None
        assert geom1.rendered_box.x == 0
        assert geom1.rendered_box.y2 == 50
        assert cache.computed_count == 1

        # 修改段落的 composition（模拟 re-typeset）
        new_char = _make_char(0, 0, 100, 80)
        para.pdf_paragraph_composition = [
            PdfParagraphComposition(pdf_character=new_char)
        ]
        para.box = Box(x=0, y=0, x2=100, y2=80)

        # 未 invalidate 前，缓存返回旧值
        geom_cached = cache.get_geometry(0)
        assert geom_cached.rendered_box.y2 == 50  # 旧值
        assert cache.computed_count == 1

        # invalidate 后，重新计算
        cache.invalidate(0)
        geom2 = cache.get_geometry(0)
        assert geom2.rendered_box is not None
        assert geom2.rendered_box.y2 == 80  # 新值
        assert geom2.layout_box.y2 == 80  # 新值
        assert cache.computed_count == 2

    def test_invalidate_nonexistent_is_noop(self):
        cache = GeometryCache()
        cache.invalidate(999)  # 不应抛异常


# ──────────────────────────────────────────────────────────────
# Test 5: xobj_id 过滤
# ──────────────────────────────────────────────────────────────


class TestXobjIdFilter:
    """不同 xobj_id 的段落不应报告重叠。"""

    def test_different_xobj_no_overlap_reported(self):
        para_a = _make_paragraph(
            chars=[_make_char(0, 0, 100, 60)],
            layout_box=Box(x=0, y=0, x2=100, y2=60),
            render_order=0,
            xobj_id=1,
        )
        para_b = _make_paragraph(
            chars=[_make_char(0, 40, 100, 100)],
            layout_box=Box(x=0, y=40, x2=100, y2=100),
            render_order=1,
            xobj_id=2,  # 不同 xobj
        )

        page = _make_page([para_a, para_b])
        doc = _make_document([page])

        context = DocumentContext.from_document(doc)
        processor = PostLayoutProcessor(context)
        processor.register_detector(OverlapDetector())
        report = processor.run()

        assert report.metrics.issues_detected == 0

    def test_same_xobj_reports_overlap(self):
        para_a = _make_paragraph(
            chars=[_make_char(0, 0, 100, 60)],
            layout_box=Box(x=0, y=0, x2=100, y2=60),
            render_order=0,
            xobj_id=1,
        )
        para_b = _make_paragraph(
            chars=[_make_char(0, 40, 100, 100)],
            layout_box=Box(x=0, y=40, x2=100, y2=100),
            render_order=1,
            xobj_id=1,  # 同一 xobj
        )

        page = _make_page([para_a, para_b])
        doc = _make_document([page])

        context = DocumentContext.from_document(doc)
        processor = PostLayoutProcessor(context)
        processor.register_detector(OverlapDetector())
        report = processor.run()

        assert report.metrics.issues_detected == 1


# ──────────────────────────────────────────────────────────────
# Test 6: run() 始终返回 OptimizationReport
# ──────────────────────────────────────────────────────────────


class TestRunAlwaysReturnsReport:
    """run() 应该始终返回 OptimizationReport，不返回 None。"""

    def test_empty_document(self):
        doc = _make_document([])
        context = DocumentContext.from_document(doc)
        processor = PostLayoutProcessor(context)
        processor.register_detector(OverlapDetector())
        report = processor.run()

        assert report is not None
        assert report.metrics.total_pages == 0
        assert report.metrics.total_paragraphs == 0
        assert report.metrics.issues_detected == 0

    def test_single_paragraph_no_overlap(self):
        para = _make_paragraph(
            chars=[_make_char(0, 0, 100, 50)],
            layout_box=Box(x=0, y=0, x2=100, y2=50),
        )
        page = _make_page([para])
        doc = _make_document([page])

        context = DocumentContext.from_document(doc)
        processor = PostLayoutProcessor(context)
        processor.register_detector(OverlapDetector())
        report = processor.run()

        assert report is not None
        assert report.metrics.issues_detected == 0


# ──────────────────────────────────────────────────────────────
# Test 7: report 输出完整性
# ──────────────────────────────────────────────────────────────


class TestReportOutput:
    """验证 report 结构完整性。"""

    def test_report_has_debug_output(self):
        para_a = _make_paragraph(
            chars=[_make_char(0, 0, 100, 60)],
            layout_box=Box(x=0, y=0, x2=100, y2=60),
            render_order=0,
        )
        para_b = _make_paragraph(
            chars=[_make_char(0, 40, 100, 100)],
            layout_box=Box(x=0, y=40, x2=100, y2=100),
            render_order=1,
        )

        page = _make_page([para_a, para_b])
        doc = _make_document([page])

        context = DocumentContext.from_document(doc)
        processor = PostLayoutProcessor(context)
        processor.register_detector(OverlapDetector())
        report = processor.run()

        # debug_output 结构完整
        assert "total_issues" in report.debug_output
        assert "issues" in report.debug_output
        assert report.debug_output["total_issues"] == 1

        # issue 结构完整
        issue_data = report.debug_output["issues"][0]
        assert "page_number" in issue_data
        assert "detector" in issue_data
        assert "type" in issue_data
        assert "paragraphs" in issue_data
        assert "iou" in issue_data
        assert "coverage" in issue_data
        assert "description" in issue_data
        assert "bbox_evidence" in issue_data

        # bbox_evidence 是快照（dict），不是 Box 引用
        evidence = issue_data["bbox_evidence"]
        assert isinstance(evidence, dict)
        assert "p1" in evidence
        assert "p2" in evidence
        assert isinstance(evidence["p1"], dict)
        assert "x" in evidence["p1"]
        assert "y" in evidence["p1"]


# ──────────────────────────────────────────────────────────────
# Test 8: bbox_evidence 是快照不是引用
# ──────────────────────────────────────────────────────────────


class TestBboxEvidenceSnapshot:
    """bbox_evidence 应该是值拷贝，不是 Box 引用。"""

    def test_evidence_not_affected_by_later_box_mutation(self):
        para_a = _make_paragraph(
            chars=[_make_char(0, 0, 100, 60)],
            layout_box=Box(x=0, y=0, x2=100, y2=60),
            render_order=0,
        )
        para_b = _make_paragraph(
            chars=[_make_char(0, 40, 100, 100)],
            layout_box=Box(x=0, y=40, x2=100, y2=100),
            render_order=1,
        )

        page = _make_page([para_a, para_b])
        doc = _make_document([page])

        context = DocumentContext.from_document(doc)
        processor = PostLayoutProcessor(context)
        processor.register_detector(OverlapDetector())
        report = processor.run()

        # 记录原始 evidence
        evidence_before = report.issues[0].bbox_evidence.copy()

        # 修改原始 Box（模拟后续 fix 操作）
        para_a.pdf_paragraph_composition[0].pdf_character.box.x = -999

        # evidence 不应受影响
        assert report.issues[0].bbox_evidence == evidence_before
        assert report.issues[0].bbox_evidence["p1"]["x"] == 0  # 原始值


# ──────────────────────────────────────────────────────────────
# Phase 2: OverlapResolver 测试
# ──────────────────────────────────────────────────────────────


class TestOverlapResolver:
    """测试 OverlapResolver 的修复决策逻辑。"""

    def test_resolve_shrink_from_above(self):
        """shrink 段落在 keep 之下 → 收缩顶部。"""
        # Paragraph A (render_order=0): y=0..60, rendered y=0..60
        para_a = _make_paragraph(
            chars=[_make_char(0, 0, 100, 60)],
            layout_box=Box(x=0, y=0, x2=100, y2=60),
            render_order=0,
        )
        # Paragraph B (render_order=1): y=40..100, rendered y=40..100
        para_b = _make_paragraph(
            chars=[_make_char(0, 40, 100, 100)],
            layout_box=Box(x=0, y=40, x2=100, y2=100),
            render_order=1,
        )

        page = _make_page([para_a, para_b])
        doc = _make_document([page])

        context = DocumentContext.from_document(doc)
        resolver = OverlapResolver()

        # 创建一个 overlap issue
        issues = [LayoutIssue(
            page_id=0,
            detector_name="test",
            issue_type="overlap",
            affected_paragraph_ids=(0, 1),
            iou=0.1,
            coverage=0.2,
            description="test overlap",
        )]

        actions = resolver.resolve_all(issues, context)

        assert len(actions) == 1
        action = actions[0]
        # B 的 render_order 更高，应该被收缩
        assert action.shrink_paragraph_id == 1
        assert action.new_box is not None
        # new_y = keep_box.y2 + 1 = 61
        assert action.new_box.y == 61

    def test_resolve_no_action_when_no_overlap(self):
        """没有 overlap issue 时不生成 FixAction。"""
        context = DocumentContext.from_document(_make_document([_make_page([])]))
        resolver = OverlapResolver()
        actions = resolver.resolve_all([], context)
        assert len(actions) == 0

    def test_resolve_merges_constraints_for_same_paragraph(self):
        """同一段落出现在多个 issue 中时，合并为最严格的约束。"""
        # 三个段落：A, B, C
        # A-B 重叠，A-C 重叠
        # A 都是 keep（render_order 最低）
        # B 和 C 都要收缩
        para_a = _make_paragraph(
            chars=[_make_char(0, 0, 100, 100)],
            layout_box=Box(x=0, y=0, x2=100, y2=100),
            render_order=0,
        )
        para_b = _make_paragraph(
            chars=[_make_char(0, 80, 100, 150)],
            layout_box=Box(x=0, y=80, x2=100, y2=150),
            render_order=1,
        )
        para_c = _make_paragraph(
            chars=[_make_char(0, 90, 100, 160)],
            layout_box=Box(x=0, y=90, x2=100, y2=160),
            render_order=2,
        )

        page = _make_page([para_a, para_b, para_c])
        doc = _make_document([page])

        context = DocumentContext.from_document(doc)
        resolver = OverlapResolver()

        issues = [
            LayoutIssue(
                page_id=0, detector_name="test", issue_type="overlap",
                affected_paragraph_ids=(0, 1), iou=0.1, coverage=0.2,
                description="A-B overlap",
            ),
            LayoutIssue(
                page_id=0, detector_name="test", issue_type="overlap",
                affected_paragraph_ids=(0, 2), iou=0.1, coverage=0.2,
                description="A-C overlap",
            ),
        ]

        actions = resolver.resolve_all(issues, context)

        # B 和 C 各有一个 FixAction
        assert len(actions) == 2
        action_pids = {a.shrink_paragraph_id for a in actions}
        assert action_pids == {1, 2}


# ──────────────────────────────────────────────────────────────
# Phase 2: OverlapFixer 测试（需要 mock Typesetting）
# ──────────────────────────────────────────────────────────────


class _MockTypesetting:
    """模拟 Typesetting，不执行实际排版。"""

    def __init__(self):
        self.retypeset_calls = []

    def retypeset_paragraph(self, paragraph, page):
        self.retypeset_calls.append({
            "paragraph": paragraph,
            "page": page,
        })
        # 模拟排版：添加一个 composition
        paragraph.pdf_paragraph_composition = [
            PdfParagraphComposition(
                pdf_character=_make_char(
                    paragraph.box.x,
                    paragraph.box.y,
                    paragraph.box.x2,
                    paragraph.box.y + 10,
                )
            )
        ]
        return True


class TestOverlapFixer:
    """测试 OverlapFixer 的修复执行。"""

    def test_apply_fix_success(self):
        """成功修复：修改 box 并重新排版。"""
        para = _make_paragraph(
            chars=[_make_char(0, 0, 100, 100)],
            layout_box=Box(x=0, y=0, x2=100, y2=100),
            render_order=1,
        )
        page = _make_page([para])
        doc = _make_document([page])

        context = DocumentContext.from_document(doc)
        mock_typesetter = _MockTypesetting()
        fixer = OverlapFixer(mock_typesetter)

        action = FixAction(
            shrink_paragraph_id=0,
            new_box=Box(x=0, y=50, x2=100, y2=100),
        )

        success = fixer.apply_fix(context, action)

        assert success is True
        assert para.box.y == 50
        assert len(mock_typesetter.retypeset_calls) == 1

    def test_apply_fix_rollback_on_failure(self):
        """修复失败时回滚到原始状态。"""
        para = _make_paragraph(
            chars=[_make_char(0, 0, 100, 100)],
            layout_box=Box(x=0, y=0, x2=100, y2=100),
            render_order=1,
        )
        page = _make_page([para])
        doc = _make_document([page])

        context = DocumentContext.from_document(doc)

        # 创建一个会抛异常的 mock
        class _FailingTypesetting(_MockTypesetting):
            def retypeset_paragraph(self, paragraph, page):
                return False

        fixer = OverlapFixer(_FailingTypesetting())

        old_box = para.box
        old_comps = para.pdf_paragraph_composition[:]

        action = FixAction(
            shrink_paragraph_id=0,
            new_box=Box(x=0, y=50, x2=100, y2=100),
        )

        success = fixer.apply_fix(context, action)

        assert success is False
        # 回滚：box 和 composition 恢复
        assert para.box == old_box
        assert para.pdf_paragraph_composition == old_comps


# ──────────────────────────────────────────────────────────────
# Phase 2: PostLayoutProcessor 修复循环测试
# ──────────────────────────────────────────────────────────────


class TestPostLayoutProcessorFixLoop:
    """测试 PostLayoutProcessor 的 detect→fix→re-detect 循环。"""

    def test_dry_run_does_not_fix(self):
        """dry_run=True 时不修复。"""
        para_a = _make_paragraph(
            chars=[_make_char(0, 0, 100, 60)],
            layout_box=Box(x=0, y=0, x2=100, y2=60),
            render_order=0,
        )
        para_b = _make_paragraph(
            chars=[_make_char(0, 40, 100, 100)],
            layout_box=Box(x=0, y=40, x2=100, y2=100),
            render_order=1,
        )

        page = _make_page([para_a, para_b])
        doc = _make_document([page])

        context = DocumentContext.from_document(doc)
        mock_typesetter = _MockTypesetting()
        processor = PostLayoutProcessor(context, typesetter=mock_typesetter)
        processor.register_detector(OverlapDetector())

        report = processor.run(dry_run=True)

        assert report.metrics.issues_fixed == 0
        assert report.metrics.iterations == 0
        assert len(mock_typesetter.retypeset_calls) == 0

    def test_no_typesetter_does_not_fix(self):
        """typesetter=None 时不修复。"""
        para_a = _make_paragraph(
            chars=[_make_char(0, 0, 100, 60)],
            layout_box=Box(x=0, y=0, x2=100, y2=60),
            render_order=0,
        )
        para_b = _make_paragraph(
            chars=[_make_char(0, 40, 100, 100)],
            layout_box=Box(x=0, y=40, x2=100, y2=100),
            render_order=1,
        )

        page = _make_page([para_a, para_b])
        doc = _make_document([page])

        context = DocumentContext.from_document(doc)
        processor = PostLayoutProcessor(context, typesetter=None)
        processor.register_detector(OverlapDetector())

        report = processor.run(dry_run=False)

        assert report.metrics.issues_fixed == 0
        assert report.metrics.iterations == 0
