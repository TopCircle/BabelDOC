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

# 避免循环导入：TYPE_CHECKING 时导入 Typesetting
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from babeldoc.format.pdf.document_il.midend.typesetting import Typesetting

logger = logging.getLogger(__name__)


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


def compute_rendered_box(para: PdfParagraph) -> Box | None:
    """从段落实际字符坐标计算紧密包围盒。"""
    chars = [c for c in extract_rendered_chars(para) if char_has_valid_box(c)]
    if not chars:
        return None
    return Box(
        x=min(c.box.x for c in chars),
        y=min(c.box.y for c in chars),
        x2=max(c.box.x2 for c in chars),
        y2=max(c.box.y2 for c in chars),
    )


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
class ParagraphGeometry:
    """段落几何信息快照。"""

    paragraph_id: int
    rendered_box: Box | None  # 从实际 char 坐标计算的紧密包围盒
    layout_box: Box | None  # paragraph.box，排版时的逻辑包围盒
    ink_box: Box | None  # 预留


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
        return ParagraphGeometry(
            paragraph_id=paragraph_id,
            rendered_box=compute_rendered_box(para),
            layout_box=para.box,
            ink_box=None,
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
        return Box(
            x=max(box_a.x or 0, box_b.x or 0),
            y=max(box_a.y or 0, box_b.y or 0),
            x2=min(box_a.x2 or float("inf"), box_b.x2 or float("inf")),
            y2=min(box_a.y2 or float("inf"), box_b.y2 or float("inf")),
        )


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
    Phase 2: 检测 + 修复循环（需要 typesetter）。
    """

    def __init__(
        self,
        context: DocumentContext,
        typesetter: Typesetting | None = None,
    ):
        self.context = context
        self.detectors: list[OverlapDetector] = []
        self.resolver = OverlapResolver()
        self.fixer = OverlapFixer(typesetter) if typesetter else None

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

        # Phase 2: 检测→修复循环
        if can_fix:
            for iteration in range(max_iterations):
                issues = self._detect_all()
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
            all_issues = self._detect_all()
            total_detected += len(all_issues)

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
