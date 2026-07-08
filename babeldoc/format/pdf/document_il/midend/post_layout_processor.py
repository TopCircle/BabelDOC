"""PostLayoutProcessor — 文档级排版后处理框架。

Phase 1: 只读检测（OverlapDetector）+ 报告输出。
Phase 2: 修复（Resolver + Executor + Fixer）— 待实现。

设计原则：
1. Issue 是不可变快照，不持有运行时对象引用
2. 所有几何计算统一走 GeometryCache
3. 只允许 Paragraph 级修复，不允许 Page 级重排
4. Fixer 不允许直接修改 Document，只通过 Executor

用法：
    context = DocumentContext.from_document(document)
    processor = PostLayoutProcessor(context)
    report = processor.run()
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from dataclasses import field

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import Document
from babeldoc.format.pdf.document_il.il_version_1 import Page
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.il_version_1 import ReferenceMetrics

# 避免循环导入：TYPE_CHECKING 时导入 Typesetting
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from babeldoc.format.pdf.document_il.midend.typesetting import Typesetting

logger = logging.getLogger(__name__)

# 浮点比较容差：IoU/coverage 低于此值视为无重叠（避免舍入误差误报）
_OVERLAP_EPSILON = 1e-9


# ──────────────────────────────────────────────────────────────
# 共享工具函数
# ──────────────────────────────────────────────────────────────


def extract_rendered_chars(para: PdfParagraph) -> list:
    """从段落 composition 中提取所有可渲染字符。

    覆盖全部 5 种 composition 类型：
    pdf_character, pdf_line, pdf_formula, pdf_same_style_characters,
    pdf_same_style_unicode_characters（无字符坐标，跳过）。
    """
    chars = []
    for comp in para.pdf_paragraph_composition or []:
        if comp.pdf_character:
            chars.append(comp.pdf_character)
        elif comp.pdf_line:
            chars.extend(comp.pdf_line.pdf_character)
        elif comp.pdf_formula:
            chars.extend(comp.pdf_formula.pdf_character)
        elif comp.pdf_same_style_characters:
            chars.extend(comp.pdf_same_style_characters.pdf_character)
        # pdf_same_style_unicode_characters 无 pdf_character 字段，跳过
    return chars


def char_has_valid_box(c) -> bool:
    """检查字符的 box 字段是否完整可用。"""
    return (
        c.box is not None
        and c.box.x is not None
        and c.box.y is not None
        and c.box.x2 is not None
        and c.box.y2 is not None
    )


def compute_rendered_box(para: PdfParagraph) -> tuple[Box | None, list]:
    """从段落实际字符坐标计算紧密包围盒。

    Returns (box, valid_chars) — the bounding box and the filtered chars used
    to compute it, so callers can reuse the char list without re-extracting.
    """
    chars = [c for c in extract_rendered_chars(para) if char_has_valid_box(c)]
    if not chars:
        return None, []
    return Box(
        x=min(c.box.x for c in chars),
        y=min(c.box.y for c in chars),
        x2=max(c.box.x2 for c in chars),
        y2=max(c.box.y2 for c in chars),
    ), chars


def box_intersection(b1: Box, b2: Box) -> tuple[float, float, float, float] | None:
    """计算两个 Box 的交集坐标。返回 (x, y, x2, y2) 或 None。"""
    if any(
        v is None
        for v in (b1.x, b1.y, b1.x2, b1.y2, b2.x, b2.y, b2.x2, b2.y2)
    ):
        return None
    ix = max(b1.x, b2.x)
    iy = max(b1.y, b2.y)
    ix2 = min(b1.x2, b2.x2)
    iy2 = min(b1.y2, b2.y2)
    if ix >= ix2 or iy >= iy2:
        return None
    return ix, iy, ix2, iy2


# ──────────────────────────────────────────────────────────────
# 数据结构
# ──────────────────────────────────────────────────────────────


@dataclass
class ParagraphLayoutInfo:
    """Computed layout metrics for a translated paragraph (post-typesetting).

    Field names mirror ReferenceMetrics for symmetric comparison,
    plus height (recomputable from rendered_box) and density.
    """

    height: float | None = None  # rendered_box.y2 - rendered_box.y
    line_count: int | None = None
    avg_line_width: float | None = None
    last_line_width: float | None = None
    last_line_ratio: float | None = None  # last_line_width / avg_line_width
    font_size: float | None = None  # mode of char font sizes
    density: float | None = None  # total char area / rendered box area


@dataclass
class ParagraphGeometry:
    """段落几何信息快照。"""

    paragraph_id: int
    rendered_box: Box | None  # 从实际 char 坐标计算的紧密包围盒
    layout_box: Box | None  # paragraph.box，排版时的逻辑包围盒
    ink_box: Box | None  # 预留
    reference_metrics: ReferenceMetrics | None = None  # 原始英文布局指标
    layout_info: ParagraphLayoutInfo | None = None  # 译文布局指标


@dataclass
class LayoutIssue:
    """布局问题快照。"""

    page_id: int
    detector_name: str
    issue_type: str
    affected_paragraph_ids: tuple[int, ...]
    iou: float  # intersection / union
    coverage: float  # intersection / smaller_box_area
    description: str
    bbox_evidence: dict = field(default_factory=dict)


@dataclass
class FixAction:
    """单个修复动作。"""

    shrink_paragraph_id: int  # 要收缩的段落
    new_box: Box  # 收缩后的 box


@dataclass
class OptimizationMetrics:
    """量化指标。"""

    total_pages: int
    total_paragraphs: int
    issues_detected: int
    issues_fixed: int
    issues_remaining: int
    iterations: int
    paragraphs_retypeset: int
    geometry_recomputed: int
    avg_iou: float
    max_iou: float
    elapsed_seconds: float


@dataclass
class OptimizationReport:
    """最终报告。"""

    metrics: OptimizationMetrics
    issues: list[LayoutIssue]
    debug_output: dict = field(default_factory=dict)


# ──────────────────────────────────────────────────────────────
# GeometryCache
# ──────────────────────────────────────────────────────────────


class GeometryCache:
    """段落几何缓存。一次计算，多次使用。"""

    def __init__(self):
        self._cache: dict[int, ParagraphGeometry] = {}
        self._paragraphs: dict[int, PdfParagraph] = {}
        self.computed_count: int = 0

    def bind(self, paragraph_id: int, paragraph: PdfParagraph):
        """绑定 paragraph_id 到实际对象。"""
        self._paragraphs[paragraph_id] = paragraph

    def get_geometry(self, paragraph_id: int) -> ParagraphGeometry:
        if paragraph_id not in self._cache:
            self._cache[paragraph_id] = self._compute(paragraph_id)
            self.computed_count += 1
        return self._cache[paragraph_id]

    def invalidate(self, paragraph_id: int):
        """re-typeset 后清除该段落的全部几何缓存。"""
        self._cache.pop(paragraph_id, None)

    def _compute(self, paragraph_id: int) -> ParagraphGeometry:
        para = self._paragraphs.get(paragraph_id)
        if para is None:
            return ParagraphGeometry(
                paragraph_id=paragraph_id,
                rendered_box=None,
                layout_box=None,
                ink_box=None,
            )

        rendered_box, valid_chars = compute_rendered_box(para)

        # Compute layout_info from rendered chars (reuse already-filtered chars)
        layout_info = None
        if rendered_box:
            layout_info = self._compute_layout_info(para, rendered_box, valid_chars)

        return ParagraphGeometry(
            paragraph_id=paragraph_id,
            rendered_box=rendered_box,
            layout_box=para.box,
            ink_box=None,
            reference_metrics=getattr(para, 'reference_metrics', None),
            layout_info=layout_info,
        )

    @staticmethod
    def _compute_layout_info(
        para: PdfParagraph, rendered_box: Box, valid_chars: list | None = None,
    ) -> ParagraphLayoutInfo | None:
        """Compute translated layout metrics from rendered characters.

        Args:
            para: The paragraph to analyze.
            rendered_box: Pre-computed bounding box.
            valid_chars: Pre-filtered chars with valid boxes (avoids re-extraction).
        """
        try:
            from babeldoc.format.pdf.document_il.utils.layout_helper import (
                count_lines_from_compositions,
                compute_per_line_widths,
            )
        except ImportError:
            return None

        height = rendered_box.y2 - rendered_box.y

        line_count = count_lines_from_compositions(para)
        per_line_widths = compute_per_line_widths(para)

        avg_line_width = (
            sum(per_line_widths) / len(per_line_widths) if per_line_widths else None
        )
        last_line_width = per_line_widths[-1] if per_line_widths else None
        last_line_ratio = (
            last_line_width / avg_line_width
            if avg_line_width and avg_line_width > 0
            else None
        )

        # font_size: mode of char font sizes
        font_size = None
        if valid_chars is None:
            chars = extract_rendered_chars(para)
            valid_chars = [c for c in chars if char_has_valid_box(c)]
        font_sizes = [
            c.pdf_style.font_size
            for c in valid_chars
            if c.pdf_style and c.pdf_style.font_size is not None
        ]
        if font_sizes:
            import statistics

            try:
                font_size = statistics.mode(font_sizes)
            except statistics.StatisticsError:
                font_size = statistics.median(font_sizes)

        # Density: total char area / rendered box area
        density = None
        if valid_chars and rendered_box:
            total_char_area = sum(
                (c.box.x2 - c.box.x) * (c.box.y2 - c.box.y) for c in valid_chars
            )
            box_area = (rendered_box.x2 - rendered_box.x) * (
                rendered_box.y2 - rendered_box.y
            )
            density = total_char_area / box_area if box_area > 0 else None

        return ParagraphLayoutInfo(
            height=height,
            line_count=line_count,
            avg_line_width=avg_line_width,
            last_line_width=last_line_width,
            last_line_ratio=last_line_ratio,
            font_size=font_size,
            density=density,
        )


# ──────────────────────────────────────────────────────────────
# DocumentContext
# ──────────────────────────────────────────────────────────────


@dataclass
class ProcessorConfig:
    """处理器配置。"""

    max_iterations: int = 3
    min_iou_threshold: float = 0.0  # 低于此值的重叠不报告
    min_coverage_threshold: float = 0.0


class DocumentContext:
    """整个 PostLayoutProcessor 的唯一数据入口。

    所有 Detector、Resolver、Fixer 只接收 context，禁止直接访问 Document。

    使用内部分配的 page_id / paragraph_id，不依赖 page_number 或 id(obj)。
    """

    def __init__(self, document: Document, config: ProcessorConfig | None = None):
        self.document = document
        self.config = config or ProcessorConfig()
        self.pages: dict[int, Page] = {}
        self.paragraphs: dict[int, PdfParagraph] = {}
        self.paragraph_page: dict[int, int] = {}  # paragraph_id -> page_id
        self.page_paragraphs: dict[int, list[int]] = {}  # page_id -> [paragraph_id]
        self._para_to_id: dict[int, int] = {}  # id(para) -> paragraph_id
        self.geometry_cache = GeometryCache()
        self._next_page_id = 0
        self._next_paragraph_id = 0
        self._build_indices()

    @classmethod
    def from_document(
        cls, document: Document, config: ProcessorConfig | None = None
    ) -> DocumentContext:
        return cls(document, config)

    def get_paragraph(self, paragraph_id: int) -> PdfParagraph | None:
        return self.paragraphs.get(paragraph_id)

    def get_page(self, page_id: int) -> Page | None:
        return self.pages.get(page_id)

    def _alloc_page_id(self) -> int:
        pid = self._next_page_id
        self._next_page_id += 1
        return pid

    def _alloc_paragraph_id(self) -> int:
        pid = self._next_paragraph_id
        self._next_paragraph_id += 1
        return pid

    def _build_indices(self):
        for page in self.document.page or []:
            page_id = self._alloc_page_id()
            self.pages[page_id] = page
            self.page_paragraphs[page_id] = []

            for para in page.pdf_paragraph or []:
                para_id = self._alloc_paragraph_id()
                self.paragraphs[para_id] = para
                self.paragraph_page[para_id] = page_id
                self.page_paragraphs[page_id].append(para_id)
                self._para_to_id[id(para)] = para_id
                self.geometry_cache.bind(para_id, para)

        logger.debug(
            f"DocumentContext: {self._next_page_id} pages, "
            f"{self._next_paragraph_id} paragraphs indexed"
        )

    def get_paragraph_id(self, para: PdfParagraph) -> int | None:
        """O(1) 查找段落的 paragraph_id。"""
        return self._para_to_id.get(id(para))


# ──────────────────────────────────────────────────────────────
# OverlapDetector
# ──────────────────────────────────────────────────────────────


class OverlapDetector:
    """只读检测器：检测同页段落之间的二维包围盒重叠。"""

    name = "OverlapDetector"

    def detect(self, context: DocumentContext) -> list[LayoutIssue]:
        issues: list[LayoutIssue] = []
        cfg = context.config

        for page_id, para_ids in context.page_paragraphs.items():
            if len(para_ids) < 2:
                continue

            for i in range(len(para_ids)):
                for j in range(i + 1, len(para_ids)):
                    pid_i, pid_j = para_ids[i], para_ids[j]

                    geom_i = context.geometry_cache.get_geometry(pid_i)
                    geom_j = context.geometry_cache.get_geometry(pid_j)

                    box_i = geom_i.rendered_box
                    box_j = geom_j.rendered_box

                    if box_i is None or box_j is None:
                        continue

                    iou, coverage = self._compute_overlap_metrics(box_i, box_j)

                    if iou <= cfg.min_iou_threshold and coverage <= cfg.min_coverage_threshold:
                        continue

                    para_i = context.paragraphs[pid_i]
                    para_j = context.paragraphs[pid_j]

                    # 跳过不同 XObject 的段落（坐标系独立）
                    if para_i.xobj_id != para_j.xobj_id:
                        continue

                    label_i = para_i.layout_label or "unknown"
                    label_j = para_j.layout_label or "unknown"

                    issues.append(
                        LayoutIssue(
                            page_id=page_id,
                            detector_name=self.name,
                            issue_type="overlap",
                            affected_paragraph_ids=(pid_i, pid_j),
                            iou=iou,
                            coverage=coverage,
                            description=(
                                f"Paragraph {pid_i} [{label_i}] "
                                f"overlaps Paragraph {pid_j} [{label_j}] "
                                f"(iou={iou:.4f}, coverage={coverage:.4f})"
                            ),
                            bbox_evidence={
                                "p1": self._box_to_dict(box_i),
                                "p2": self._box_to_dict(box_j),
                            },
                        )
                    )

        return issues

    @staticmethod
    def _compute_overlap_metrics(b1: Box, b2: Box) -> tuple[float, float]:
        """计算 IoU 和 coverage。

        Returns:
            (iou, coverage) — iou = intersection/union, coverage = intersection/smaller_area
        """
        inter = box_intersection(b1, b2)
        if inter is None:
            return 0.0, 0.0

        inter_x, inter_y, inter_x2, inter_y2 = inter
        inter_area = (inter_x2 - inter_x) * (inter_y2 - inter_y)
        area1 = (b1.x2 - b1.x) * (b1.y2 - b1.y)
        area2 = (b2.x2 - b2.x) * (b2.y2 - b2.y)
        union_area = area1 + area2 - inter_area

        iou = inter_area / union_area if union_area > 0 else 0.0
        smaller = min(area1, area2)
        coverage = inter_area / smaller if smaller > 0 else 0.0

        return iou, coverage

    @staticmethod
    def _box_to_dict(box: Box) -> dict:
        return {"x": box.x, "y": box.y, "x2": box.x2, "y2": box.y2}


# ──────────────────────────────────────────────────────────────
# QuoteDetector
# ──────────────────────────────────────────────────────────────


class QuoteDetector:
    """检测 Quote（引文框）块与正文的碰撞问题。

    Quote 块的特征：
    1. 宽度明显窄于页面宽度（两侧有留白）
    2. 左侧有明显缩进
    3. 右侧有明显留白

    检测逻辑：
    1. 识别所有 Quote 块
    2. 对每个 Quote 块，检查与同页正文段落的重叠
    3. 生成 LayoutIssue（issue_type="quote_collision"）
    """

    name = "QuoteDetector"

    def __init__(
        self,
        narrow_threshold: float = 0.8,
        indent_threshold: float = 0.05,
        right_margin_threshold: float = 0.05,
    ):
        self.narrow_threshold = narrow_threshold
        self.indent_threshold = indent_threshold
        self.right_margin_threshold = right_margin_threshold

    def detect(self, context: DocumentContext) -> list[LayoutIssue]:
        """检测所有 Quote 块，返回与正文碰撞的 issue 列表。"""
        from babeldoc.format.pdf.document_il.utils.layout_helper import is_quote_block

        issues: list[LayoutIssue] = []

        for page_id, para_ids in context.page_paragraphs.items():
            if len(para_ids) < 2:
                continue

            page = context.get_page(page_id)
            if page is None:
                continue

            # 获取页面宽度
            page_width = self._get_page_width(page)
            if page_width <= 0:
                continue

            # 识别 Quote 块和正文段落
            quote_paras: list[int] = []
            text_paras: list[int] = []

            for pid in para_ids:
                para = context.get_paragraph(pid)
                if para is None:
                    continue

                if is_quote_block(
                    para,
                    page_width,
                    narrow_threshold=self.narrow_threshold,
                    indent_threshold=self.indent_threshold,
                    right_margin_threshold=self.right_margin_threshold,
                ):
                    quote_paras.append(pid)
                else:
                    text_paras.append(pid)

            # 检查每个 Quote 块与正文段落的碰撞
            for quote_pid in quote_paras:
                quote_geom = context.geometry_cache.get_geometry(quote_pid)
                quote_box = quote_geom.rendered_box
                if quote_box is None:
                    continue

                for text_pid in text_paras:
                    text_geom = context.geometry_cache.get_geometry(text_pid)
                    text_box = text_geom.rendered_box
                    if text_box is None:
                        continue

                    # 检查是否重叠（使用 epsilon 避免舍入误差误报）
                    iou, coverage = self._compute_overlap_metrics(quote_box, text_box)

                    if iou > _OVERLAP_EPSILON or coverage > _OVERLAP_EPSILON:
                        quote_para = context.get_paragraph(quote_pid)
                        text_para = context.get_paragraph(text_pid)

                        # 跳过不同 XObject 的段落
                        if quote_para and text_para and quote_para.xobj_id != text_para.xobj_id:
                            continue

                        issues.append(
                            LayoutIssue(
                                page_id=page_id,
                                detector_name=self.name,
                                issue_type="quote_collision",
                                affected_paragraph_ids=(quote_pid, text_pid),
                                iou=iou,
                                coverage=coverage,
                                description=(
                                    f"Quote block {quote_pid} collides with "
                                    f"text paragraph {text_pid} "
                                    f"(iou={iou:.4f}, coverage={coverage:.4f})"
                                ),
                                bbox_evidence={
                                    "quote_box": self._box_to_dict(quote_box),
                                    "text_box": self._box_to_dict(text_box),
                                },
                            )
                        )

        return issues

    @staticmethod
    def _get_page_width(page) -> float:
        """获取页面宽度。"""
        if page.cropbox and page.cropbox.box:
            return page.cropbox.box.x2 - page.cropbox.box.x
        if page.mediabox and page.mediabox.box:
            return page.mediabox.box.x2 - page.mediabox.box.x
        return 0.0

    @staticmethod
    def _compute_overlap_metrics(b1: Box, b2: Box) -> tuple[float, float]:
        """计算 IoU 和 coverage。"""
        inter = box_intersection(b1, b2)
        if inter is None:
            return 0.0, 0.0

        inter_x, inter_y, inter_x2, inter_y2 = inter
        inter_area = (inter_x2 - inter_x) * (inter_y2 - inter_y)
        area1 = (b1.x2 - b1.x) * (b1.y2 - b1.y)
        area2 = (b2.x2 - b2.x) * (b2.y2 - b2.y)
        union_area = area1 + area2 - inter_area

        iou = inter_area / union_area if union_area > 0 else 0.0
        smaller = min(area1, area2)
        coverage = inter_area / smaller if smaller > 0 else 0.0

        return iou, coverage

    @staticmethod
    def _box_to_dict(box: Box) -> dict:
        return {"x": box.x, "y": box.y, "x2": box.x2, "y2": box.y2}


# ──────────────────────────────────────────────────────────────
# QuoteResolver
# ──────────────────────────────────────────────────────────────


class QuoteResolver:
    """将 Quote 碰撞 issue 解析为 FixAction。

    决策逻辑：
    - Quote 块优先级高于正文（Quote 不动，正文让路）
    - 如果 Quote 与正文重叠，收缩/移动正文段落
    - 收缩方向：根据 Quote 与正文的相对位置决定
    """

    def resolve_all(
        self, issues: list[LayoutIssue], context: DocumentContext
    ) -> list[FixAction]:
        """为所有 quote_collision issue 生成修复动作列表。

        同一段落只生成一个 FixAction（最严格的约束）。
        """
        # {paragraph_id: new_box}
        constraints: dict[int, Box] = {}

        for issue in issues:
            if issue.issue_type != "quote_collision":
                continue

            quote_pid, text_pid = issue.affected_paragraph_ids
            quote_para = context.get_paragraph(quote_pid)
            text_para = context.get_paragraph(text_pid)
            if quote_para is None or text_para is None:
                continue

            quote_geom = context.geometry_cache.get_geometry(quote_pid)
            text_geom = context.geometry_cache.get_geometry(text_pid)
            quote_box = quote_geom.rendered_box
            text_box = text_geom.rendered_box
            if quote_box is None or text_box is None:
                continue

            # Quote 优先：收缩正文段落
            if text_para.box is None:
                continue

            new_box = self._compute_shrunk_box_for_quote(
                text_para.box, text_box, quote_box
            )
            if new_box is None:
                continue

            # 合并约束：如果同一段落已有约束，取更严格的
            if text_pid in constraints:
                constraints[text_pid] = self._merge_constraints(
                    constraints[text_pid], new_box
                )
            else:
                constraints[text_pid] = new_box

        return [
            FixAction(
                shrink_paragraph_id=pid,
                new_box=new_box,
            )
            for pid, new_box in constraints.items()
        ]

    @staticmethod
    def _compute_shrunk_box_for_quote(
        layout_box: Box, text_box: Box, quote_box: Box
    ) -> Box | None:
        """计算为 Quote 让路后的正文 box。

        策略（PDF 坐标系，y 向上）：
        - 如果正文在 Quote 下方 → 收缩正文顶部 (new_y2 = quote.y - 1)
        - 如果正文在 Quote 上方 → 收缩正文底部 (new_y = quote.y2 + 1)
        - 如果正文与 Quote 左右重叠 → 收缩正文右侧 (new_x2 = quote.x - 1)
        """
        # 检查垂直重叠
        vertical_overlap = (
            text_box.y < quote_box.y2 and text_box.y2 > quote_box.y
        )

        # 检查水平重叠
        horizontal_overlap = (
            text_box.x < quote_box.x2 and text_box.x2 > quote_box.x
        )

        if not vertical_overlap or not horizontal_overlap:
            return None

        # 优先处理垂直方向的碰撞
        # 正文在 Quote 下方（正文顶部低于或等于 Quote 顶部）
        if text_box.y2 <= quote_box.y2 and text_box.y < quote_box.y:
            new_y2 = quote_box.y - 1
            if new_y2 > layout_box.y:
                return Box(
                    x=layout_box.x,
                    y=layout_box.y,
                    x2=layout_box.x2,
                    y2=new_y2,
                )

        # 正文在 Quote 上方（正文底部高于或等于 Quote 底部）
        if text_box.y >= quote_box.y and text_box.y2 > quote_box.y2:
            new_y = quote_box.y2 + 1
            if new_y < (layout_box.y2 or float("inf")):
                return Box(
                    x=layout_box.x,
                    y=new_y,
                    x2=layout_box.x2,
                    y2=layout_box.y2,
                )

        # 正文横跨 Quote（顶部在 Quote 上方，底部在 Quote 下方）
        # 选择空间更大的一侧收缩
        if text_box.y2 > quote_box.y2 and text_box.y < quote_box.y:
            space_above = text_box.y2 - quote_box.y2
            space_below = quote_box.y - text_box.y
            if space_above >= space_below:
                new_y = quote_box.y2 + 1
                if new_y < (layout_box.y2 or float("inf")):
                    return Box(
                        x=layout_box.x,
                        y=new_y,
                        x2=layout_box.x2,
                        y2=layout_box.y2,
                    )
            else:
                new_y2 = quote_box.y - 1
                if new_y2 > layout_box.y:
                    return Box(
                        x=layout_box.x,
                        y=layout_box.y,
                        x2=layout_box.x2,
                        y2=new_y2,
                    )

        # 处理包含情况：text 完全在 quote 内部或 quote 完全在 text 内部
        # 选择收缩方向：向空间更大的方向收缩
        text_in_quote = (
            text_box.y >= quote_box.y
            and text_box.y2 <= quote_box.y2
            and text_box.x >= quote_box.x
            and text_box.x2 <= quote_box.x2
        )
        quote_in_text = (
            quote_box.y >= text_box.y
            and quote_box.y2 <= text_box.y2
            and quote_box.x >= text_box.x
            and quote_box.x2 <= text_box.x2
        )

        if text_in_quote or quote_in_text:
            # 使用 Quote 高度作为扩展参考（需要逃出 Quote 区域）
            quote_height = quote_box.y2 - quote_box.y
            expand_limit = max(quote_height * 0.5, 50)  # 至少 50pt
            # 尝试向上收缩（new_y = quote.y2 + 1）
            new_y = quote_box.y2 + 1
            if new_y < (text_box.y2 + expand_limit):
                effective_y2 = (
                    layout_box.y2
                    if layout_box.y2 is not None
                    else text_box.y2
                )
                return Box(
                    x=layout_box.x,
                    y=new_y,
                    x2=layout_box.x2,
                    y2=max(effective_y2, text_box.y2),
                )
            # 尝试向下收缩（new_y2 = quote.y - 1）
            new_y2 = quote_box.y - 1
            if new_y2 > (text_box.y - expand_limit):
                return Box(
                    x=layout_box.x,
                    y=min(layout_box.y, text_box.y),
                    x2=layout_box.x2,
                    y2=new_y2,
                )

        # 如果垂直方向无法收缩，尝试水平方向
        # 正文在 Quote 右侧
        if text_box.x >= quote_box.x2:
            new_x = quote_box.x2 + 1
            if new_x < (layout_box.x2 or float("inf")):
                return Box(
                    x=new_x,
                    y=layout_box.y,
                    x2=layout_box.x2,
                    y2=layout_box.y2,
                )

        # 正文在 Quote 左侧
        if text_box.x2 <= quote_box.x:
            new_x2 = quote_box.x - 1
            if new_x2 > layout_box.x:
                return Box(
                    x=layout_box.x,
                    y=layout_box.y,
                    x2=new_x2,
                    y2=layout_box.y2,
                )

        return None

    @staticmethod
    def _merge_constraints(box_a: Box, box_b: Box) -> Box:
        """合并两个约束，取更严格的（更小的有效区域）。"""
        inter = box_intersection(box_a, box_b)
        if inter is not None:
            return Box(x=inter[0], y=inter[1], x2=inter[2], y2=inter[3])
        # 无交集时返回更小的 box（保守策略）
        x = max(box_a.x or 0, box_b.x or 0)
        y = max(box_a.y or 0, box_b.y or 0)
        x2 = min(box_a.x2 or float("inf"), box_b.x2 or float("inf"))
        y2 = min(box_a.y2 or float("inf"), box_b.y2 or float("inf"))
        # 防止退化 box（x > x2 或 y > y2），回退到 box_a
        if x > x2 or y > y2:
            return box_a
        return Box(x=x, y=y, x2=x2, y2=y2)


# ──────────────────────────────────────────────────────────────
# QuoteFixer
# ──────────────────────────────────────────────────────────────


class QuoteFixer:
    """应用 Quote 修复动作：收缩正文 box + 重新排版。"""

    def __init__(self, typesetter: Typesetting):
        self._typesetter = typesetter

    def apply_fix(
        self, context: DocumentContext, action: FixAction
    ) -> bool:
        """应用单个 Quote 修复动作。

        Returns:
            True 表示成功，False 表示失败（已回滚）。
        """
        para = context.get_paragraph(action.shrink_paragraph_id)
        if para is None:
            return False

        page_id = context.paragraph_page.get(action.shrink_paragraph_id)
        if page_id is None:
            return False
        page = context.get_page(page_id)
        if page is None:
            return False

        # 保存旧 box 用于回滚
        old_box = para.box
        para.box = action.new_box

        success = self._typesetter.retypeset_paragraph(para, page)
        if success:
            context.geometry_cache.invalidate(action.shrink_paragraph_id)
            logger.debug(
                f"Quote fix: paragraph {action.shrink_paragraph_id}: "
                f"box {old_box} → {action.new_box}"
            )
            return True
        else:
            # retypeset_paragraph 已回滚 composition，这里回滚 box
            para.box = old_box
            return False


# ──────────────────────────────────────────────────────────────
# OverlapResolver
# ──────────────────────────────────────────────────────────────


class OverlapResolver:
    """将 LayoutIssue 解析为 FixAction。

    决策逻辑：
    - render_order 更低的段落保持不变
    - shrink 段落在 keep 之下 → 收缩顶部 (new_y2 = keep_box.y - 1)
    - shrink 段落在 keep 之上 → 收缩底部 (new_y = keep_box.y2 + 1)
    - 同一段落出现在多个 issue 中时，合并为最严格的约束
    """

    def resolve_all(
        self, issues: list[LayoutIssue], context: DocumentContext
    ) -> list[FixAction]:
        """为所有 issue 生成修复动作列表。

        同一段落只生成一个 FixAction（最严格的约束）。
        """
        # {paragraph_id: (new_box, keep_paragraph_id)}
        constraints: dict[int, tuple[Box, int]] = {}

        for issue in issues:
            if issue.issue_type != "overlap":
                continue

            pid_i, pid_j = issue.affected_paragraph_ids
            para_i = context.get_paragraph(pid_i)
            para_j = context.get_paragraph(pid_j)
            if para_i is None or para_j is None:
                continue

            geom_i = context.geometry_cache.get_geometry(pid_i)
            geom_j = context.geometry_cache.get_geometry(pid_j)
            box_i = geom_i.rendered_box
            box_j = geom_j.rendered_box
            if box_i is None or box_j is None:
                continue

            # 确定 keep / shrink
            if (para_i.render_order or 0) <= (para_j.render_order or 0):
                keep_para, shrink_para = para_i, para_j
                keep_box, shrink_box = box_i, box_j
            else:
                keep_para, shrink_para = para_j, para_i
                keep_box, shrink_box = box_j, box_i

            if shrink_para.box is None:
                continue

            # 确定收缩方向
            new_box = self._compute_shrunk_box(
                shrink_para.box, shrink_box, keep_box
            )
            if new_box is None:
                continue

            # 合并约束：如果同一段落已有约束，取更严格的
            shrink_pid = context.get_paragraph_id(shrink_para)
            if shrink_pid is None:
                continue

            if shrink_pid in constraints:
                existing_box = constraints[shrink_pid]
                merged = self._merge_constraints(existing_box, new_box)
                constraints[shrink_pid] = merged
            else:
                constraints[shrink_pid] = new_box

        return [
            FixAction(
                shrink_paragraph_id=pid,
                new_box=new_box,
            )
            for pid, new_box in constraints.items()
        ]

    @staticmethod
    def _compute_shrunk_box(
        layout_box: Box, shrink_box: Box, keep_box: Box
    ) -> Box | None:
        """计算收缩后的 box。

        收缩策略（PDF 坐标系，y 向上）：
        - shrink 在 keep 之下 → 收缩顶部 (new_y2 = keep.y - 1)
        - shrink 在 keep 之上 → 收缩底部 (new_y = keep.y2 + 1)
        - 两者同时（containment）→ 优先收缩底部

        Returns:
            收缩后的 Box，或 None 如果无法收缩。
        """
        extends_below = shrink_box.y < keep_box.y2
        extends_above = shrink_box.y2 > keep_box.y2

        if extends_above:
            # shrink 顶部在 keep 之上 → 收缩底部
            new_y = keep_box.y2 + 1
            if new_y < (layout_box.y2 or float("inf")):
                return Box(
                    x=layout_box.x,
                    y=new_y,
                    x2=layout_box.x2,
                    y2=layout_box.y2,
                )
        if extends_below:
            # shrink 底部在 keep 之下 → 收缩顶部
            new_y2 = keep_box.y - 1
            if new_y2 > layout_box.y:
                return Box(
                    x=layout_box.x,
                    y=layout_box.y,
                    x2=layout_box.x2,
                    y2=new_y2,
                )
        return None

    @staticmethod
    def _merge_constraints(box_a: Box, box_b: Box) -> Box:
        """合并两个约束，取更严格的（更小的有效区域）。"""
        inter = box_intersection(box_a, box_b)
        if inter is not None:
            return Box(x=inter[0], y=inter[1], x2=inter[2], y2=inter[3])
        # 无交集时返回更小的 box（保守策略）
        x = max(box_a.x or 0, box_b.x or 0)
        y = max(box_a.y or 0, box_b.y or 0)
        x2 = min(box_a.x2 or float("inf"), box_b.x2 or float("inf"))
        y2 = min(box_a.y2 or float("inf"), box_b.y2 or float("inf"))
        # 防止退化 box（x > x2 或 y > y2），回退到 box_a
        if x > x2 or y > y2:
            return box_a
        return Box(x=x, y=y, x2=x2, y2=y2)


# ──────────────────────────────────────────────────────────────
# OverlapFixer
# ──────────────────────────────────────────────────────────────


class OverlapFixer:
    """应用 FixAction：收缩 box + 重新排版。"""

    def __init__(self, typesetter: Typesetting):
        self._typesetter = typesetter

    def apply_fix(
        self, context: DocumentContext, action: FixAction
    ) -> bool:
        """应用单个修复动作。

        Returns:
            True 表示成功，False 表示失败（已回滚）。
        """
        para = context.get_paragraph(action.shrink_paragraph_id)
        if para is None:
            return False

        page_id = context.paragraph_page.get(action.shrink_paragraph_id)
        if page_id is None:
            return False
        page = context.get_page(page_id)
        if page is None:
            return False

        # 保存旧 box 用于回滚（composition 回滚由 retypeset_paragraph 处理）
        old_box = para.box
        para.box = action.new_box

        success = self._typesetter.retypeset_paragraph(para, page)
        if success:
            context.geometry_cache.invalidate(action.shrink_paragraph_id)
            logger.debug(
                f"Fixed paragraph {action.shrink_paragraph_id}: "
                f"box {old_box} → {action.new_box}"
            )
            return True
        else:
            # retypeset_paragraph 已回滚 composition，这里回滚 box
            para.box = old_box
            return False


# ──────────────────────────────────────────────────────────────
# PostLayoutProcessor
# ──────────────────────────────────────────────────────────────


class PostLayoutProcessor:
    """主编排器。

    Phase 1: 只读检测 + 报告（typesetter=None 或 dry_run=True）。
    Phase 2: Quote 碰撞检测 + 修复（优先级高于通用重叠）。
    Phase 3: 通用重叠检测 + 修复循环（需要 typesetter）。
    """

    def __init__(
        self,
        context: DocumentContext,
        typesetter: Typesetting | None = None,
        quote_narrow_threshold: float = 0.8,
        quote_indent_threshold: float = 0.05,
        quote_right_margin_threshold: float = 0.05,
    ):
        self.context = context
        self.detectors: list[OverlapDetector] = []
        self.resolver = OverlapResolver()
        self.fixer = OverlapFixer(typesetter) if typesetter else None

        # Quote 组件
        self.quote_detector = QuoteDetector(
            narrow_threshold=quote_narrow_threshold,
            indent_threshold=quote_indent_threshold,
            right_margin_threshold=quote_right_margin_threshold,
        )
        self.quote_resolver = QuoteResolver()
        self.quote_fixer = QuoteFixer(typesetter) if typesetter else None

    def register_detector(self, detector: OverlapDetector):
        self.detectors.append(detector)

    def run(self, dry_run: bool = False) -> OptimizationReport:
        """主入口。

        Args:
            dry_run: True 时只检测不修复。
        """
        start_time = time.monotonic()

        can_fix = not dry_run and self.fixer is not None
        total_fixed = 0
        total_retypeset = 0
        total_detected = 0
        iterations = 0
        loop_found_clean = False
        max_iterations = self.context.config.max_iterations

        # Phase 2: Quote 碰撞检测 + 修复（优先级高于通用重叠）
        quote_issues = []
        quote_fixed = 0
        fixed_quote_pids: set[str] = set()  # 已修复的 Quote 段落 ID
        # 检测始终执行（dry_run 也需要报告），修复仅在 can_fix 时执行
        if self.quote_detector:
            quote_issues = self.quote_detector.detect(self.context)
            if quote_issues:
                total_detected += len(quote_issues)
                if can_fix and self.quote_fixer:
                    quote_actions = self.quote_resolver.resolve_all(
                        quote_issues, self.context
                    )
                    for action in quote_actions:
                        success = self.quote_fixer.apply_fix(
                            self.context, action
                        )
                        if success:
                            quote_fixed += 1
                            total_fixed += 1
                            total_retypeset += 1
                            # 记录已修复的段落 ID，避免 Phase 3 重复计数
                            fixed_quote_pids.add(
                                action.shrink_paragraph_id
                            )
                    logger.debug(
                        f"Quote collision: {len(quote_issues)} issues, "
                        f"{quote_fixed} fixed"
                    )

        # Phase 3: 通用重叠检测→修复循环
        # 排除已修复的 Quote 段落，避免重复计数和优先级冲突
        if can_fix:
            for iteration in range(max_iterations):
                issues = [
                    i
                    for i in self._detect_all()
                    if not any(
                        pid in fixed_quote_pids
                        for pid in i.affected_paragraph_ids
                    )
                ]
                if not issues:
                    iterations = iteration + 1
                    loop_found_clean = True
                    break

                total_detected += len(issues)
                actions = self.resolver.resolve_all(issues, self.context)
                if not actions:
                    iterations = iteration + 1
                    break

                fixed_in_round = 0
                for action in actions:
                    success = self.fixer.apply_fix(self.context, action)
                    if success:
                        fixed_in_round += 1
                        total_retypeset += 1

                total_fixed += fixed_in_round
                iterations = iteration + 1
                logger.debug(
                    f"Iteration {iteration + 1}: "
                    f"{len(issues)} issues, {fixed_in_round} fixed"
                )

                if fixed_in_round == 0:
                    break
        else:
            iterations = 0

        # 最终检测：仅当循环未确认 clean 时执行
        if loop_found_clean:
            all_issues = []
        else:
            all_issues = [
                i
                for i in self._detect_all()
                if not any(
                    pid in fixed_quote_pids
                    for pid in i.affected_paragraph_ids
                )
            ]
            total_detected += len(all_issues)

        # 合并未修复的 Quote issues 到 all_issues 用于报告
        unfixed_quote_issues = [
            qi
            for qi in quote_issues
            if not any(
                pid in fixed_quote_pids
                for pid in qi.affected_paragraph_ids
            )
        ]
        all_issues = unfixed_quote_issues + all_issues

        elapsed = time.monotonic() - start_time

        # Metrics
        iou_values = [issue.iou for issue in all_issues]
        metrics = OptimizationMetrics(
            total_pages=len(self.context.pages),
            total_paragraphs=len(self.context.paragraphs),
            issues_detected=total_detected,
            issues_fixed=total_fixed,
            issues_remaining=len(all_issues),
            iterations=iterations,
            paragraphs_retypeset=total_retypeset,
            geometry_recomputed=self.context.geometry_cache.computed_count,
            avg_iou=sum(iou_values) / len(iou_values) if iou_values else 0.0,
            max_iou=max(iou_values) if iou_values else 0.0,
            elapsed_seconds=elapsed,
        )

        # Debug output
        debug_output = self._build_debug_output(all_issues)

        report = OptimizationReport(
            metrics=metrics,
            issues=all_issues,
            debug_output=debug_output,
        )

        self._log_report(report)
        return report

    def _detect_all(self) -> list[LayoutIssue]:
        """执行所有检测器，返回全部 issue。"""
        all_issues: list[LayoutIssue] = []
        for detector in self.detectors:
            issues = detector.detect(self.context)
            all_issues.extend(issues)
        return all_issues

    def _build_debug_output(self, issues: list[LayoutIssue]) -> dict:
        """构建结构化调试输出，可序列化为 JSON。"""
        pages_output: dict[int, list[dict]] = {}
        for issue in issues:
            page_id = issue.page_id
            if page_id not in pages_output:
                pages_output[page_id] = []
            page = self.context.get_page(page_id)
            page_number = page.page_number if page else page_id
            pages_output[page_id].append(
                {
                    "page_number": page_number,
                    "detector": issue.detector_name,
                    "type": issue.issue_type,
                    "paragraphs": list(issue.affected_paragraph_ids),
                    "iou": round(issue.iou, 6),
                    "coverage": round(issue.coverage, 6),
                    "description": issue.description,
                    "bbox_evidence": issue.bbox_evidence,
                }
            )

        # Flatten for output
        flat_issues = []
        for page_issues in pages_output.values():
            flat_issues.extend(page_issues)

        return {
            "total_issues": len(issues),
            "issues": flat_issues,
        }

    def _log_report(self, report: OptimizationReport):
        m = report.metrics
        logger.info(
            f"PostLayoutProcessor: {m.issues_detected} issues detected "
            f"across {m.total_pages} pages ({m.total_paragraphs} paragraphs), "
            f"avg_iou={m.avg_iou:.4f}, max_iou={m.max_iou:.4f}, "
            f"elapsed={m.elapsed_seconds:.2f}s"
        )
        for issue in report.issues:
            logger.warning(f"[{issue.detector_name}] {issue.description}")
