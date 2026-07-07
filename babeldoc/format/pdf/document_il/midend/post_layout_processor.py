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

logger = logging.getLogger(__name__)


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
            rendered_box=self._compute_rendered_box(para),
            layout_box=para.box,
            ink_box=None,
        )

    @staticmethod
    def _compute_rendered_box(para: PdfParagraph) -> Box | None:
        """从 pdf_paragraph_composition 的实际字符坐标计算紧密包围盒。

        覆盖全部 5 种 composition 类型：pdf_character, pdf_line,
        pdf_formula, pdf_same_style_characters,
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
        chars = [c for c in chars if c.box is not None]
        if not chars:
            return None
        return Box(
            x=min(c.box.x for c in chars),
            y=min(c.box.y for c in chars),
            x2=max(c.box.x2 for c in chars),
            y2=max(c.box.y2 for c in chars),
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
                self.geometry_cache.bind(para_id, para)

        logger.debug(
            f"DocumentContext: {self._next_page_id} pages, "
            f"{self._next_paragraph_id} paragraphs indexed"
        )


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
        inter_x = max(b1.x, b2.x)
        inter_y = max(b1.y, b2.y)
        inter_x2 = min(b1.x2, b2.x2)
        inter_y2 = min(b1.y2, b2.y2)

        if inter_x >= inter_x2 or inter_y >= inter_y2:
            return 0.0, 0.0

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
# PostLayoutProcessor
# ──────────────────────────────────────────────────────────────


class PostLayoutProcessor:
    """主编排器。Phase 1: 只读检测 + 报告。"""

    def __init__(self, context: DocumentContext):
        self.context = context
        self.detectors: list[OverlapDetector] = []

    def register_detector(self, detector: OverlapDetector):
        self.detectors.append(detector)

    def run(self, dry_run: bool = False) -> OptimizationReport:
        """主入口。

        Args:
            dry_run: True 时只检测不修复（Phase 1 始终为 True）。
        """
        start_time = time.monotonic()

        # Detect
        all_issues: list[LayoutIssue] = []
        for detector in self.detectors:
            issues = detector.detect(self.context)
            all_issues.extend(issues)
            logger.debug(f"[{detector.name}] found {len(issues)} issues")

        elapsed = time.monotonic() - start_time

        # Metrics
        iou_values = [issue.iou for issue in all_issues]
        metrics = OptimizationMetrics(
            total_pages=len(self.context.pages),
            total_paragraphs=len(self.context.paragraphs),
            issues_detected=len(all_issues),
            issues_fixed=0,
            issues_remaining=len(all_issues),
            iterations=0,  # Phase 1: detection-only, no fix iterations
            paragraphs_retypeset=0,
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
