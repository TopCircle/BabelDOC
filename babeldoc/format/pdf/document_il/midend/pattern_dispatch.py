"""Pattern Dispatch（模式分发器）

根据页面的 FlowRegion 和 VisualObject 特征，识别 Publisher Layout Pattern，
并选择相应的排版策略。

12 种 Pattern：
1. full_text: 无图片，整页全宽
2. right_figure: 右侧图片，LEFT_WRAP→逐渐变宽
3. left_figure: 左侧图片，RIGHT_WRAP→逐渐变宽
4. center_figure: 中间图片，MULTI_COLUMN
5. pull_quote: 红色引文，QUOTE 区域收窄
6. caption: 图片说明，图片下方固定区域
7. sidebar: 侧栏，主区域收窄
8. header_footer: 页眉页脚，HEADER/FOOTER 区域
9. full_image: 整页图片，FULL_IMAGE
10. numbered_step: 步骤标题，独立 Block
11. rounded_image: 圆角图片，逐行变宽
12. person_cutout: 人物抠图，复杂轮廓
"""

import logging
from dataclasses import dataclass, field
from enum import Enum

from babeldoc.format.pdf.document_il import il_version_1
from babeldoc.format.pdf.document_il.midend.flow_skeleton import (
    PublisherSkeleton,
    FlowRegion,
    FlowStateType,
    VisualObject,
    ConstraintPriority,
)

logger = logging.getLogger(__name__)


class PatternType(Enum):
    """Pattern 类型"""
    FULL_TEXT = "full_text"
    RIGHT_FIGURE = "right_figure"
    LEFT_FIGURE = "left_figure"
    CENTER_FIGURE = "center_figure"
    PULL_QUOTE = "pull_quote"
    CAPTION = "caption"
    SIDEBAR = "sidebar"
    HEADER_FOOTER = "header_footer"
    FULL_IMAGE = "full_image"
    NUMBERED_STEP = "numbered_step"
    ROUNDED_IMAGE = "rounded_image"
    PERSON_CUTOUT = "person_cutout"


@dataclass
class PatternMatch:
    """Pattern 匹配结果"""
    pattern: PatternType
    confidence: float  # 0.0-1.0
    regions: list[FlowRegion] = field(default_factory=list)
    objects: list[VisualObject] = field(default_factory=list)
    description: str = ""


class PatternDispatcher:
    """Pattern 分发器"""

    def __init__(self, skeleton: PublisherSkeleton):
        self.skeleton = skeleton

    def detect_pattern(self) -> PatternMatch:
        """检测页面的主要 Pattern。

        Returns:
            PatternMatch: 匹配结果
        """
        # 按优先级检测
        patterns = [
            self._detect_full_image,
            self._detect_header_footer,
            self._detect_pull_quote,
            self._detect_sidebar,
            self._detect_caption,
            self._detect_numbered_step,
            self._detect_center_figure,
            self._detect_right_figure,
            self._detect_left_figure,
            self._detect_rounded_image,
            self._detect_person_cutout,
            self._detect_full_text,
        ]

        for detector in patterns:
            match = detector()
            if match and match.confidence > 0.5:
                return match

        # 默认返回 full_text
        return PatternMatch(
            pattern=PatternType.FULL_TEXT,
            confidence=0.5,
            regions=self.skeleton.regions,
            description="Default full text pattern",
        )

    def _detect_full_image(self) -> PatternMatch | None:
        """检测整页图片 Pattern"""
        # 如果页面大部分被图片覆盖，认为是 full_image
        if not self.skeleton.objects:
            return None

        image_objects = [obj for obj in self.skeleton.objects
                        if obj.kind in ("image", "figure")]
        if not image_objects:
            return None

        # 计算图片覆盖面积
        page_area = ((self.skeleton.page_x_max - self.skeleton.page_x_min) *
                    (self.skeleton.page_y_max - self.skeleton.page_y_min))
        image_area = sum(
            (obj.bbox.x2 - obj.bbox.x) * (obj.bbox.y2 - obj.bbox.y)
            for obj in image_objects
        )

        if image_area > page_area * 0.8:
            return PatternMatch(
                pattern=PatternType.FULL_IMAGE,
                confidence=0.9,
                objects=image_objects,
                description="Full page image",
            )
        return None

    def _detect_header_footer(self) -> PatternMatch | None:
        """检测页眉页脚 Pattern"""
        header_footer_objects = [obj for obj in self.skeleton.objects
                                if obj.kind in ("header", "footer")]
        if not header_footer_objects:
            return None

        # 如果有 header/footer 对象，认为是 header_footer Pattern
        return PatternMatch(
            pattern=PatternType.HEADER_FOOTER,
            confidence=0.8,
            objects=header_footer_objects,
            description="Header/footer detected",
        )

    def _detect_pull_quote(self) -> PatternMatch | None:
        """检测 Pull Quote Pattern"""
        quote_objects = [obj for obj in self.skeleton.objects
                        if obj.kind == "quote"]
        if not quote_objects:
            return None

        # 如果有 quote 对象，认为是 pull_quote Pattern
        return PatternMatch(
            pattern=PatternType.PULL_QUOTE,
            confidence=0.8,
            objects=quote_objects,
            description="Pull quote detected",
        )

    def _detect_sidebar(self) -> PatternMatch | None:
        """检测侧栏 Pattern"""
        # 侧栏通常是页面左侧或右侧的窄条区域
        sidebar_objects = []
        for obj in self.skeleton.objects:
            if obj.kind in ("image", "figure"):
                # 检查是否是侧栏（宽度 < 页面宽度 30%）
                obj_width = obj.bbox.x2 - obj.bbox.x
                page_width = self.skeleton.page_x_max - self.skeleton.page_x_min
                if obj_width < page_width * 0.3:
                    sidebar_objects.append(obj)

        if sidebar_objects:
            return PatternMatch(
                pattern=PatternType.SIDEBAR,
                confidence=0.7,
                objects=sidebar_objects,
                description="Sidebar detected",
            )
        return None

    def _detect_caption(self) -> PatternMatch | None:
        """检测图片说明 Pattern"""
        # 图片说明通常在图片下方，是窄条区域
        caption_regions = []
        for region in self.skeleton.regions:
            if region.state == FlowStateType.FULL:
                # 检查是否在图片下方
                for obj in self.skeleton.objects:
                    if obj.kind in ("image", "figure"):
                        if (region.y_end < obj.bbox.y and
                            region.y_end > obj.bbox.y - 50):
                            caption_regions.append(region)

        if caption_regions:
            return PatternMatch(
                pattern=PatternType.CAPTION,
                confidence=0.7,
                regions=caption_regions,
                description="Caption detected",
            )
        return None

    def _detect_numbered_step(self) -> PatternMatch | None:
        """检测步骤标题 Pattern"""
        # 步骤标题通常是独立的小区域，且不在图片附近（否则是 caption）
        image_objects = [obj for obj in self.skeleton.objects
                        if obj.kind in ("image", "figure")]

        step_regions = []
        for region in self.skeleton.regions:
            region_height = region.y_end - region.y_start
            if region_height >= 30:  # 只考虑小区域
                continue

            # 排除：靠近图片的区域（可能是 caption）
            near_image = False
            for obj in image_objects:
                if (region.y_end < obj.bbox.y and
                    region.y_end > obj.bbox.y - 50):
                    near_image = True
                    break
            if near_image:
                continue

            # 排除：多栏区域（可能是 sidebar 或 figure 的一部分）
            if region.state == FlowStateType.MULTI_COLUMN:
                continue

            step_regions.append(region)

        if step_regions:
            return PatternMatch(
                pattern=PatternType.NUMBERED_STEP,
                confidence=0.6,
                regions=step_regions,
                description="Numbered step detected",
            )
        return None

    def _detect_center_figure(self) -> PatternMatch | None:
        """检测中间图片 Pattern"""
        # 中间图片会导致 MULTI_COLUMN 状态
        multi_column_regions = [r for r in self.skeleton.regions
                               if r.state == FlowStateType.MULTI_COLUMN]
        if multi_column_regions:
            return PatternMatch(
                pattern=PatternType.CENTER_FIGURE,
                confidence=0.8,
                regions=multi_column_regions,
                description="Center figure detected",
            )
        return None

    def _detect_right_figure(self) -> PatternMatch | None:
        """检测右侧图片 Pattern"""
        # 右侧图片会导致 LEFT_WRAP 状态
        left_wrap_regions = [r for r in self.skeleton.regions
                            if r.state == FlowStateType.LEFT_WRAP]
        if left_wrap_regions:
            return PatternMatch(
                pattern=PatternType.RIGHT_FIGURE,
                confidence=0.8,
                regions=left_wrap_regions,
                description="Right figure detected",
            )
        return None

    def _detect_left_figure(self) -> PatternMatch | None:
        """检测左侧图片 Pattern"""
        # 左侧图片会导致 RIGHT_WRAP 状态
        right_wrap_regions = [r for r in self.skeleton.regions
                             if r.state == FlowStateType.RIGHT_WRAP]
        if right_wrap_regions:
            return PatternMatch(
                pattern=PatternType.LEFT_FIGURE,
                confidence=0.8,
                regions=right_wrap_regions,
                description="Left figure detected",
            )
        return None

    def _detect_rounded_image(self) -> PatternMatch | None:
        """检测圆角图片 Pattern"""
        # 圆角图片需要特殊的轮廓处理
        # 这里简化处理，如果有图片且不是 full_image，可能是圆角图片
        image_objects = [obj for obj in self.skeleton.objects
                        if obj.kind in ("image", "figure")]
        if image_objects:
            # 检查是否有多个 FlowRegion（逐行变宽）
            if len(self.skeleton.regions) > 3:
                return PatternMatch(
                    pattern=PatternType.ROUNDED_IMAGE,
                    confidence=0.6,
                    objects=image_objects,
                    description="Rounded image detected",
                )
        return None

    def _detect_person_cutout(self) -> PatternMatch | None:
        """检测人物抠图 Pattern"""
        # 人物抠图需要复杂的轮廓处理
        # 这里简化处理，如果有图片且区域变化复杂
        image_objects = [obj for obj in self.skeleton.objects
                        if obj.kind in ("image", "figure")]
        if image_objects:
            # 检查是否有复杂的区域变化
            if len(self.skeleton.regions) > 5:
                return PatternMatch(
                    pattern=PatternType.PERSON_CUTOUT,
                    confidence=0.5,
                    objects=image_objects,
                    description="Person cutout detected",
                )
        return None

    def _detect_full_text(self) -> PatternMatch | None:
        """检测全文字 Pattern"""
        # 如果没有图片，认为是 full_text
        image_objects = [obj for obj in self.skeleton.objects
                        if obj.kind in ("image", "figure")]
        if not image_objects:
            return PatternMatch(
                pattern=PatternType.FULL_TEXT,
                confidence=0.9,
                regions=self.skeleton.regions,
                description="Full text pattern",
            )
        return None


class PatternComposer:
    """Pattern 排版器"""

    def __init__(self, skeleton: PublisherSkeleton):
        self.skeleton = skeleton
        self.dispatcher = PatternDispatcher(skeleton)

    def compose_page(self, page: il_version_1.Page) -> list[il_version_1.PdfParagraph]:
        """根据 Pattern 排版页面。

        Args:
            page: 页面对象

        Returns:
            排版后的段落列表
        """
        # 检测 Pattern
        pattern_match = self.dispatcher.detect_pattern()

        logger.info(f"Detected pattern: {pattern_match.pattern.value} "
                    f"(confidence: {pattern_match.confidence:.2f})")

        # 根据 Pattern 选择排版策略
        if pattern_match.pattern == PatternType.FULL_TEXT:
            return self._compose_full_text(page, pattern_match)
        elif pattern_match.pattern == PatternType.RIGHT_FIGURE:
            return self._compose_right_figure(page, pattern_match)
        elif pattern_match.pattern == PatternType.LEFT_FIGURE:
            return self._compose_left_figure(page, pattern_match)
        elif pattern_match.pattern == PatternType.CENTER_FIGURE:
            return self._compose_center_figure(page, pattern_match)
        elif pattern_match.pattern == PatternType.PULL_QUOTE:
            return self._compose_pull_quote(page, pattern_match)
        elif pattern_match.pattern == PatternType.CAPTION:
            return self._compose_caption(page, pattern_match)
        elif pattern_match.pattern == PatternType.SIDEBAR:
            return self._compose_sidebar(page, pattern_match)
        elif pattern_match.pattern == PatternType.HEADER_FOOTER:
            return self._compose_header_footer(page, pattern_match)
        elif pattern_match.pattern == PatternType.FULL_IMAGE:
            return self._compose_full_image(page, pattern_match)
        elif pattern_match.pattern == PatternType.NUMBERED_STEP:
            return self._compose_numbered_step(page, pattern_match)
        elif pattern_match.pattern == PatternType.ROUNDED_IMAGE:
            return self._compose_rounded_image(page, pattern_match)
        elif pattern_match.pattern == PatternType.PERSON_CUTOUT:
            return self._compose_person_cutout(page, pattern_match)
        else:
            return self._compose_full_text(page, pattern_match)

    def _compose_full_text(self, page: il_version_1.Page,
                           pattern: PatternMatch) -> list[il_version_1.PdfParagraph]:
        """全文字排版策略：简单回放。"""
        # 使用 ConstraintComposer 进行排版
        from babeldoc.format.pdf.document_il.midend.layout_composer import ConstraintComposer
        composer = ConstraintComposer(self.skeleton)

        # 这里简化处理，实际应该遍历所有段落
        return page.pdf_paragraph

    def _compose_right_figure(self, page: il_version_1.Page,
                              pattern: PatternMatch) -> list[il_version_1.PdfParagraph]:
        """右侧图片排版策略：保持轮廓。"""
        # 使用 ConstraintComposer 进行排版
        from babeldoc.format.pdf.document_il.midend.layout_composer import ConstraintComposer
        composer = ConstraintComposer(self.skeleton)

        # 这里简化处理，实际应该根据 LEFT_WRAP 区域调整
        return page.pdf_paragraph

    def _compose_left_figure(self, page: il_version_1.Page,
                             pattern: PatternMatch) -> list[il_version_1.PdfParagraph]:
        """左侧图片排版策略：镜像。"""
        # 使用 ConstraintComposer 进行排版
        from babeldoc.format.pdf.document_il.midend.layout_composer import ConstraintComposer
        composer = ConstraintComposer(self.skeleton)

        # 这里简化处理，实际应该根据 RIGHT_WRAP 区域调整
        return page.pdf_paragraph

    def _compose_center_figure(self, page: il_version_1.Page,
                               pattern: PatternMatch) -> list[il_version_1.PdfParagraph]:
        """中间图片排版策略：跨区间流动。"""
        # 使用 ConstraintComposer 进行排版
        from babeldoc.format.pdf.document_il.midend.layout_composer import ConstraintComposer
        composer = ConstraintComposer(self.skeleton)

        # 这里简化处理，实际应该根据 MULTI_COLUMN 区域调整
        return page.pdf_paragraph

    def _compose_pull_quote(self, page: il_version_1.Page,
                            pattern: PatternMatch) -> list[il_version_1.PdfParagraph]:
        """Pull Quote 排版策略：Obstacle 绕排。"""
        # 使用 ConstraintComposer 进行排版
        from babeldoc.format.pdf.document_il.midend.layout_composer import ConstraintComposer
        composer = ConstraintComposer(self.skeleton)

        # 这里简化处理，实际应该根据 QUOTE 区域调整
        return page.pdf_paragraph

    def _compose_caption(self, page: il_version_1.Page,
                         pattern: PatternMatch) -> list[il_version_1.PdfParagraph]:
        """图片说明排版策略：Anchor。"""
        # 使用 ConstraintComposer 进行排版
        from babeldoc.format.pdf.document_il.midend.layout_composer import ConstraintComposer
        composer = ConstraintComposer(self.skeleton)

        # 这里简化处理，实际应该根据图片位置调整
        return page.pdf_paragraph

    def _compose_sidebar(self, page: il_version_1.Page,
                         pattern: PatternMatch) -> list[il_version_1.PdfParagraph]:
        """侧栏排版策略：Obstacle。"""
        # 使用 ConstraintComposer 进行排版
        from babeldoc.format.pdf.document_il.midend.layout_composer import ConstraintComposer
        composer = ConstraintComposer(self.skeleton)

        # 这里简化处理，实际应该根据侧栏位置调整
        return page.pdf_paragraph

    def _compose_header_footer(self, page: il_version_1.Page,
                               pattern: PatternMatch) -> list[il_version_1.PdfParagraph]:
        """页眉页脚排版策略：Mask。"""
        # 使用 ConstraintComposer 进行排版
        from babeldoc.format.pdf.document_il.midend.layout_composer import ConstraintComposer
        composer = ConstraintComposer(self.skeleton)

        # 这里简化处理，实际应该根据 header/footer 位置调整
        return page.pdf_paragraph

    def _compose_full_image(self, page: il_version_1.Page,
                            pattern: PatternMatch) -> list[il_version_1.PdfParagraph]:
        """整页图片排版策略：跳过。"""
        # 整页图片不需要排版
        return []

    def _compose_numbered_step(self, page: il_version_1.Page,
                               pattern: PatternMatch) -> list[il_version_1.PdfParagraph]:
        """步骤标题排版策略：Anchor。"""
        # 使用 ConstraintComposer 进行排版
        from babeldoc.format.pdf.document_il.midend.layout_composer import ConstraintComposer
        composer = ConstraintComposer(self.skeleton)

        # 这里简化处理，实际应该根据步骤标题位置调整
        return page.pdf_paragraph

    def _compose_rounded_image(self, page: il_version_1.Page,
                               pattern: PatternMatch) -> list[il_version_1.PdfParagraph]:
        """圆角图片排版策略：contour。"""
        # 使用 ConstraintComposer 进行排版
        from babeldoc.format.pdf.document_il.midend.layout_composer import ConstraintComposer
        composer = ConstraintComposer(self.skeleton)

        # 这里简化处理，实际应该根据圆角图片轮廓调整
        return page.pdf_paragraph

    def _compose_person_cutout(self, page: il_version_1.Page,
                               pattern: PatternMatch) -> list[il_version_1.PdfParagraph]:
        """人物抠图排版策略：mask。"""
        # 使用 ConstraintComposer 进行排版
        from babeldoc.format.pdf.document_il.midend.layout_composer import ConstraintComposer
        composer = ConstraintComposer(self.skeleton)

        # 这里简化处理，实际应该根据人物抠图轮廓调整
        return page.pdf_paragraph
