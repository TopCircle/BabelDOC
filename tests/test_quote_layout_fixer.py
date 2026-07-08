"""QuoteLayoutFixer 单元测试。"""

from __future__ import annotations

import pytest

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import Cropbox
from babeldoc.format.pdf.document_il.il_version_1 import Document
from babeldoc.format.pdf.document_il.il_version_1 import Mediabox
from babeldoc.format.pdf.document_il.il_version_1 import Page
from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraphComposition
from babeldoc.format.pdf.document_il.midend.post_layout_processor import (
    DocumentContext,
    FixAction,
    LayoutIssue,
    QuoteDetector,
    QuoteFixer,
    QuoteResolver,
    PostLayoutProcessor,
)
from babeldoc.format.pdf.document_il.utils.layout_helper import is_quote_block


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


def _make_page(
    paragraphs: list[PdfParagraph],
    page_number: int = 0,
    page_width: float = 612.0,
    page_height: float = 792.0,
) -> Page:
    """创建一个包含段落的 Page。"""
    page = Page(
        pdf_paragraph=paragraphs,
        page_number=page_number,
        cropbox=Cropbox(box=Box(x=0, y=0, x2=page_width, y2=page_height)),
        mediabox=Mediabox(box=Box(x=0, y=0, x2=page_width, y2=page_height)),
    )
    return page


def _make_document(pages: list[Page]) -> Document:
    """创建一个包含页面的 Document。"""
    return Document(page=pages)


# ──────────────────────────────────────────────────────────────
# Test 1: is_quote_block() 启发式检测
# ──────────────────────────────────────────────────────────────


class TestIsQuoteBlock:
    """测试 is_quote_block() 启发式检测函数。"""

    def test_quote_block_detected(self):
        """典型的 Quote 块应该被检测到。"""
        # Quote 块: x=100..400, y=100..200 (宽度=300, 页面宽度=612)
        # 宽度比例 = 300/612 ≈ 0.49 < 0.8 ✓
        # 左侧缩进 = 100/612 ≈ 0.16 > 0.05 ✓
        # 右侧留白 = (612-400)/612 ≈ 0.35 > 0.05 ✓
        para = _make_paragraph(
            chars=[_make_char(100, 100, 400, 200)],
            layout_box=Box(x=100, y=100, x2=400, y2=200),
        )
        assert is_quote_block(para, 612.0) is True

    def test_normal_text_not_detected(self):
        """普通正文段落不应该被检测为 Quote。"""
        # 正文: x=50..562, y=100..200 (宽度=512, 页面宽度=612)
        # 宽度比例 = 512/612 ≈ 0.84 > 0.8 ✗
        para = _make_paragraph(
            chars=[_make_char(50, 100, 562, 200)],
            layout_box=Box(x=50, y=100, x2=562, y2=200),
        )
        assert is_quote_block(para, 612.0) is False

    def test_no_indent_not_detected(self):
        """没有缩进的窄段落不应该被检测为 Quote。"""
        # 窄段落但无缩进: x=0..400, y=100..200
        # 左侧缩进 = 0/612 = 0 < 0.05 ✗
        para = _make_paragraph(
            chars=[_make_char(0, 100, 400, 200)],
            layout_box=Box(x=0, y=100, x2=400, y2=200),
        )
        assert is_quote_block(para, 612.0) is False

    def test_no_right_margin_not_detected(self):
        """没有右侧留白的窄段落不应该被检测为 Quote。"""
        # 窄段落但无右侧留白: x=100..612, y=100..200
        # 右侧留白 = (612-612)/612 = 0 < 0.05 ✗
        para = _make_paragraph(
            chars=[_make_char(100, 100, 612, 200)],
            layout_box=Box(x=100, y=100, x2=612, y2=200),
        )
        assert is_quote_block(para, 612.0) is False

    def test_none_box_not_detected(self):
        """没有 box 的段落不应该被检测为 Quote。"""
        para = _make_paragraph(
            chars=[],
            layout_box=None,
        )
        assert is_quote_block(para, 612.0) is False

    def test_zero_page_width_not_detected(self):
        """页面宽度为 0 时不应该被检测为 Quote。"""
        para = _make_paragraph(
            chars=[_make_char(100, 100, 400, 200)],
            layout_box=Box(x=100, y=100, x2=400, y2=200),
        )
        assert is_quote_block(para, 0.0) is False

    def test_custom_thresholds(self):
        """自定义阈值应该生效。"""
        # 宽度=300, 页面宽度=612
        # 默认阈值 narrow_threshold=0.8: 300/612 ≈ 0.49 < 0.8 ✓
        para = _make_paragraph(
            chars=[_make_char(100, 100, 400, 200)],
            layout_box=Box(x=100, y=100, x2=400, y2=200),
        )

        # 使用更严格的阈值
        assert is_quote_block(para, 612.0, narrow_threshold=0.3) is False

        # 使用更宽松的阈值
        assert is_quote_block(para, 612.0, narrow_threshold=0.9) is True


# ──────────────────────────────────────────────────────────────
# Test 2: QuoteDetector 检测
# ──────────────────────────────────────────────────────────────


class TestQuoteDetector:
    """测试 QuoteDetector 的碰撞检测。"""

    def test_quote_overlaps_with_text(self):
        """Quote 块与正文重叠应该被检测到。"""
        # Quote 块: x=100..400, y=100..200 (窄 + 缩进 + 留白)
        quote_para = _make_paragraph(
            chars=[_make_char(100, 100, 400, 200)],
            layout_box=Box(x=100, y=100, x2=400, y2=200),
            render_order=1,
        )
        # 正文: x=50..562, y=150..250 (与 Quote 重叠 y=150..200)
        text_para = _make_paragraph(
            chars=[_make_char(50, 150, 562, 250)],
            layout_box=Box(x=50, y=150, x2=562, y2=250),
            render_order=0,
        )

        page = _make_page([quote_para, text_para])
        doc = _make_document([page])

        context = DocumentContext.from_document(doc)
        detector = QuoteDetector()

        issues = detector.detect(context)

        assert len(issues) == 1
        issue = issues[0]
        assert issue.issue_type == "quote_collision"
        assert issue.detector_name == "QuoteDetector"

    def test_no_overlap_no_issue(self):
        """Quote 块与正文不重叠不应该产生 issue。"""
        # Quote 块: x=100..400, y=100..200
        quote_para = _make_paragraph(
            chars=[_make_char(100, 100, 400, 200)],
            layout_box=Box(x=100, y=100, x2=400, y2=200),
            render_order=1,
        )
        # 正文: x=50..562, y=250..350 (不与 Quote 重叠)
        text_para = _make_paragraph(
            chars=[_make_char(50, 250, 562, 350)],
            layout_box=Box(x=50, y=250, x2=562, y2=350),
            render_order=0,
        )

        page = _make_page([quote_para, text_para])
        doc = _make_document([page])

        context = DocumentContext.from_document(doc)
        detector = QuoteDetector()

        issues = detector.detect(context)

        assert len(issues) == 0

    def test_two_quotes_no_collision(self):
        """两个 Quote 块不重叠不应该产生 issue。"""
        # Quote 块 1: x=100..400, y=100..200
        quote_para1 = _make_paragraph(
            chars=[_make_char(100, 100, 400, 200)],
            layout_box=Box(x=100, y=100, x2=400, y2=200),
            render_order=0,
        )
        # Quote 块 2: x=100..400, y=300..400
        quote_para2 = _make_paragraph(
            chars=[_make_char(100, 300, 400, 400)],
            layout_box=Box(x=100, y=300, x2=400, y2=400),
            render_order=1,
        )

        page = _make_page([quote_para1, quote_para2])
        doc = _make_document([page])

        context = DocumentContext.from_document(doc)
        detector = QuoteDetector()

        issues = detector.detect(context)

        # 两个 Quote 块都是 Quote，不会互相检测
        assert len(issues) == 0


# ──────────────────────────────────────────────────────────────
# Test 3: QuoteResolver 决策逻辑
# ──────────────────────────────────────────────────────────────


class TestQuoteResolver:
    """测试 QuoteResolver 的修复决策逻辑。"""

    def test_resolve_shrink_text_below_quote(self):
        """正文在 Quote 下方 → 收缩正文顶部。"""
        # Quote 块: y=200..300 (bottom=200, top=300)
        quote_para = _make_paragraph(
            chars=[_make_char(100, 200, 400, 300)],
            layout_box=Box(x=100, y=200, x2=400, y2=300),
            render_order=1,
        )
        # 正文: y=100..250 (与 Quote 重叠 y=200..250, text 在 quote 下方)
        text_para = _make_paragraph(
            chars=[_make_char(50, 100, 562, 250)],
            layout_box=Box(x=50, y=100, x2=562, y2=250),
            render_order=0,
        )

        page = _make_page([quote_para, text_para])
        doc = _make_document([page])

        context = DocumentContext.from_document(doc)
        resolver = QuoteResolver()

        issues = [
            LayoutIssue(
                page_id=0,
                detector_name="QuoteDetector",
                issue_type="quote_collision",
                affected_paragraph_ids=(0, 1),
                iou=0.1,
                coverage=0.2,
                description="Quote collision",
            )
        ]

        actions = resolver.resolve_all(issues, context)

        assert len(actions) == 1
        action = actions[0]
        # 正文的 render_order 更低，应该被收缩
        assert action.shrink_paragraph_id == 1
        # new_y2 = quote.y - 1 = 199
        assert action.new_box.y2 == 199

    def test_resolve_shrink_text_above_quote(self):
        """正文在 Quote 上方 → 收缩正文底部。"""
        # Quote 块: y=100..200 (bottom=100, top=200)
        quote_para = _make_paragraph(
            chars=[_make_char(100, 100, 400, 200)],
            layout_box=Box(x=100, y=100, x2=400, y2=200),
            render_order=0,
        )
        # 正文: y=150..300 (与 Quote 重叠 y=150..200, text 在 quote 上方)
        text_para = _make_paragraph(
            chars=[_make_char(50, 150, 562, 300)],
            layout_box=Box(x=50, y=150, x2=562, y2=300),
            render_order=1,
        )

        page = _make_page([quote_para, text_para])
        doc = _make_document([page])

        context = DocumentContext.from_document(doc)
        resolver = QuoteResolver()

        issues = [
            LayoutIssue(
                page_id=0,
                detector_name="QuoteDetector",
                issue_type="quote_collision",
                affected_paragraph_ids=(0, 1),
                iou=0.1,
                coverage=0.2,
                description="Quote collision",
            )
        ]

        actions = resolver.resolve_all(issues, context)

        assert len(actions) == 1
        action = actions[0]
        assert action.shrink_paragraph_id == 1
        # new_y = quote.y2 + 1 = 201
        assert action.new_box.y == 201

    def test_resolve_no_action_when_no_overlap(self):
        """没有 quote_collision issue 时不生成 FixAction。"""
        context = DocumentContext.from_document(_make_document([_make_page([])]))
        resolver = QuoteResolver()
        actions = resolver.resolve_all([], context)
        assert len(actions) == 0

    def test_resolve_merges_constraints_for_same_paragraph(self):
        """同一正文段落与多个 Quote 碰撞时，合并为最严格的约束。"""
        # Quote 块 1: y=100..200
        quote_para1 = _make_paragraph(
            chars=[_make_char(100, 100, 400, 200)],
            layout_box=Box(x=100, y=100, x2=400, y2=200),
            render_order=0,
        )
        # Quote 块 2: y=250..350
        quote_para2 = _make_paragraph(
            chars=[_make_char(100, 250, 400, 350)],
            layout_box=Box(x=100, y=250, x2=400, y2=350),
            render_order=1,
        )
        # 正文: y=150..300 (与两个 Quote 都重叠)
        text_para = _make_paragraph(
            chars=[_make_char(50, 150, 562, 300)],
            layout_box=Box(x=50, y=150, x2=562, y2=300),
            render_order=2,
        )

        page = _make_page([quote_para1, quote_para2, text_para])
        doc = _make_document([page])

        context = DocumentContext.from_document(doc)
        resolver = QuoteResolver()

        issues = [
            LayoutIssue(
                page_id=0,
                detector_name="QuoteDetector",
                issue_type="quote_collision",
                affected_paragraph_ids=(0, 2),
                iou=0.1,
                coverage=0.2,
                description="Quote 1 collision",
            ),
            LayoutIssue(
                page_id=0,
                detector_name="QuoteDetector",
                issue_type="quote_collision",
                affected_paragraph_ids=(1, 2),
                iou=0.1,
                coverage=0.2,
                description="Quote 2 collision",
            ),
        ]

        actions = resolver.resolve_all(issues, context)

        # 正文段落应该只有一个 FixAction（合并后的约束）
        assert len(actions) == 1
        action = actions[0]
        assert action.shrink_paragraph_id == 2


# ──────────────────────────────────────────────────────────────
# Test 4: QuoteFixer 修复执行
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


class TestQuoteFixer:
    """测试 QuoteFixer 的修复执行。"""

    def test_apply_fix_success(self):
        """成功修复：修改 box 并重新排版。"""
        para = _make_paragraph(
            chars=[_make_char(50, 150, 562, 250)],
            layout_box=Box(x=50, y=150, x2=562, y2=250),
            render_order=1,
        )
        page = _make_page([para])
        doc = _make_document([page])

        context = DocumentContext.from_document(doc)
        mock_typesetter = _MockTypesetting()
        fixer = QuoteFixer(mock_typesetter)

        action = FixAction(
            shrink_paragraph_id=0,
            new_box=Box(x=50, y=150, x2=562, y2=99),
        )

        success = fixer.apply_fix(context, action)

        assert success is True
        assert para.box.y2 == 99
        assert len(mock_typesetter.retypeset_calls) == 1

    def test_apply_fix_rollback_on_failure(self):
        """修复失败时回滚到原始状态。"""
        para = _make_paragraph(
            chars=[_make_char(50, 150, 562, 250)],
            layout_box=Box(x=50, y=150, x2=562, y2=250),
            render_order=1,
        )
        page = _make_page([para])
        doc = _make_document([page])

        context = DocumentContext.from_document(doc)

        # 创建一个会失败的 mock
        class _FailingTypesetting(_MockTypesetting):
            def retypeset_paragraph(self, paragraph, page):
                return False

        fixer = QuoteFixer(_FailingTypesetting())

        old_box = para.box

        action = FixAction(
            shrink_paragraph_id=0,
            new_box=Box(x=50, y=150, x2=562, y2=99),
        )

        success = fixer.apply_fix(context, action)

        assert success is False
        # 回滚：box 恢复
        assert para.box == old_box


# ──────────────────────────────────────────────────────────────
# Test 5: PostLayoutProcessor 集成测试
# ──────────────────────────────────────────────────────────────


class TestPostLayoutProcessorWithQuote:
    """测试 PostLayoutProcessor 集成 Quote 组件。"""

    def test_quote_collision_fixed_before_overlap(self):
        """Quote 碰撞应该在通用重叠之前被修复。"""
        # Quote 块: x=100..400, y=100..200
        quote_para = _make_paragraph(
            chars=[_make_char(100, 100, 400, 200)],
            layout_box=Box(x=100, y=100, x2=400, y2=200),
            render_order=1,
        )
        # 正文: x=50..562, y=150..250 (与 Quote 重叠)
        text_para = _make_paragraph(
            chars=[_make_char(50, 150, 562, 250)],
            layout_box=Box(x=50, y=150, x2=562, y2=250),
            render_order=0,
        )

        page = _make_page([quote_para, text_para])
        doc = _make_document([page])

        context = DocumentContext.from_document(doc)
        mock_typesetter = _MockTypesetting()
        processor = PostLayoutProcessor(context, typesetter=mock_typesetter)

        report = processor.run()

        # 应该检测到 Quote 碰撞
        assert report.metrics.issues_detected >= 1

        # 应该有修复动作
        assert len(mock_typesetter.retypeset_calls) >= 1

    def test_dry_run_does_not_fix_quote(self):
        """dry_run=True 时检测但不修复 Quote 碰撞。"""
        # Quote 块: x=100..400, y=100..200
        quote_para = _make_paragraph(
            chars=[_make_char(100, 100, 400, 200)],
            layout_box=Box(x=100, y=100, x2=400, y2=200),
            render_order=1,
        )
        # 正文: x=50..562, y=150..250 (与 Quote 重叠)
        text_para = _make_paragraph(
            chars=[_make_char(50, 150, 562, 250)],
            layout_box=Box(x=50, y=150, x2=562, y2=250),
            render_order=0,
        )

        page = _make_page([quote_para, text_para])
        doc = _make_document([page])

        context = DocumentContext.from_document(doc)
        mock_typesetter = _MockTypesetting()
        processor = PostLayoutProcessor(context, typesetter=mock_typesetter)

        report = processor.run(dry_run=True)

        # 不应该有修复动作
        assert len(mock_typesetter.retypeset_calls) == 0
        assert report.metrics.issues_fixed == 0
        # 应该检测到碰撞（dry_run 也要报告）
        assert report.metrics.issues_detected > 0

    def test_no_typesetter_does_not_fix_quote(self):
        """typesetter=None 时不修复 Quote 碰撞。"""
        # Quote 块: x=100..400, y=100..200
        quote_para = _make_paragraph(
            chars=[_make_char(100, 100, 400, 200)],
            layout_box=Box(x=100, y=100, x2=400, y2=200),
            render_order=1,
        )
        # 正文: x=50..562, y=150..250 (与 Quote 重叠)
        text_para = _make_paragraph(
            chars=[_make_char(50, 150, 562, 250)],
            layout_box=Box(x=50, y=150, x2=562, y2=250),
            render_order=0,
        )

        page = _make_page([quote_para, text_para])
        doc = _make_document([page])

        context = DocumentContext.from_document(doc)
        processor = PostLayoutProcessor(context, typesetter=None)

        report = processor.run(dry_run=False)

        # 不应该有修复动作
        assert report.metrics.issues_fixed == 0


# ──────────────────────────────────────────────────────────────
# Test 6: QuoteResolver 边界情况
# ──────────────────────────────────────────────────────────────


class TestQuoteResolverEdgeCases:
    """测试 QuoteResolver 的边界情况。"""

    def test_quote_containing_text(self):
        """Quote 完全包含正文时，应该收缩正文。"""
        # Quote 块: x=100..400, y=100..300
        quote_para = _make_paragraph(
            chars=[_make_char(100, 100, 400, 300)],
            layout_box=Box(x=100, y=100, x2=400, y2=300),
            render_order=0,
        )
        # 正文: x=150..350, y=150..250 (完全在 Quote 内部)
        text_para = _make_paragraph(
            chars=[_make_char(150, 150, 350, 250)],
            layout_box=Box(x=150, y=150, x2=350, y2=250),
            render_order=1,
        )

        page = _make_page([quote_para, text_para])
        doc = _make_document([page])

        context = DocumentContext.from_document(doc)
        resolver = QuoteResolver()

        issues = [
            LayoutIssue(
                page_id=0,
                detector_name="QuoteDetector",
                issue_type="quote_collision",
                affected_paragraph_ids=(0, 1),
                iou=0.5,
                coverage=0.8,
                description="Quote contains text",
            )
        ]

        actions = resolver.resolve_all(issues, context)

        # 应该生成一个修复动作
        assert len(actions) == 1
        action = actions[0]
        assert action.shrink_paragraph_id == 1

    def test_text_containing_quote(self):
        """正文完全包含 Quote 时，应该收缩正文。"""
        # Quote 块: x=150..350, y=150..250
        quote_para = _make_paragraph(
            chars=[_make_char(150, 150, 350, 250)],
            layout_box=Box(x=150, y=150, x2=350, y2=250),
            render_order=0,
        )
        # 正文: x=100..400, y=100..300 (完全包含 Quote)
        text_para = _make_paragraph(
            chars=[_make_char(100, 100, 400, 300)],
            layout_box=Box(x=100, y=100, x2=400, y2=300),
            render_order=1,
        )

        page = _make_page([quote_para, text_para])
        doc = _make_document([page])

        context = DocumentContext.from_document(doc)
        resolver = QuoteResolver()

        issues = [
            LayoutIssue(
                page_id=0,
                detector_name="QuoteDetector",
                issue_type="quote_collision",
                affected_paragraph_ids=(0, 1),
                iou=0.3,
                coverage=0.6,
                description="Text contains quote",
            )
        ]

        actions = resolver.resolve_all(issues, context)

        # 应该生成一个修复动作
        assert len(actions) == 1
        action = actions[0]
        assert action.shrink_paragraph_id == 1
