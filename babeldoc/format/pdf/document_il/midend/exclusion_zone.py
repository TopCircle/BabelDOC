"""ExclusionZone — 通用排版排除区域抽象。

在 Typesetting 阶段主动提供版面约束，使正文排版时自动避开
Quote、Figure、Table 等浮动对象区域。

设计原则：
1. ExclusionZone 是不可变数据对象
2. ExclusionZoneBuilder 负责从页面元素构建 zones
3. ExclusionZoneIndex 基于 R-tree 提供高效的 per-line 可用宽度查询
4. 所有几何计算使用 PDF 坐标系（y 向上）

用法：
    zones = ExclusionZoneBuilder.build(page)
    index = ExclusionZoneIndex(zones)
    left, right = index.get_available_x_range(y_bottom, y_top, page_left, page_right)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

from rtree import index as rtree_index

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import Page
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.utils.layout_helper import box_to_tuple

logger = logging.getLogger(__name__)

# ExclusionZone 类型常量
ZONE_QUOTE = "quote"
ZONE_FIGURE = "figure"
ZONE_TABLE = "table"
ZONE_FORMULA = "formula"
ZONE_SIDEBAR = "sidebar"

ZoneKind = Literal["quote", "figure", "table", "formula", "sidebar"]


@dataclass(frozen=True, slots=True)
class ExclusionZone:
    """一个排版排除区域。

    Attributes:
        box: 排除区域的边界框（含 margins）
        kind: 区域类型（quote, figure, table, formula, sidebar）
        priority: 优先级，数字越大越优先保留（正文让路）
        margins: 原始边距 (left, top, right, bottom)，用于调试
    """

    box: Box
    kind: ZoneKind
    priority: int = 10
    margins: tuple[float, float, float, float] | None = None


class ExclusionZoneBuilder:
    """从页面元素构建排除区域列表。"""

    @staticmethod
    def build(page: Page, quote_config: QuoteZoneConfig | None = None) -> list[ExclusionZone]:
        """构建当前页的所有排除区域。

        Args:
            page: PDF 页面
            quote_config: Quote 检测参数配置

        Returns:
            排除区域列表
        """
        if quote_config is None:
            quote_config = QuoteZoneConfig()

        zones: list[ExclusionZone] = []
        zones.extend(_collect_quote_zones(page, quote_config))
        # 未来扩展:
        # zones.extend(_collect_figure_zones(page))
        # zones.extend(_collect_table_zones(page))
        return zones


@dataclass
class QuoteZoneConfig:
    """Quote 区域检测参数。"""
    narrow_threshold: float = 0.8
    indent_threshold: float = 0.05
    right_margin_threshold: float = 0.05
    left_margin: float = 0.02
    top_margin: float = 0.01
    bottom_margin: float = 0.01


def _collect_quote_zones(page: Page, config: QuoteZoneConfig) -> list[ExclusionZone]:
    """收集页面中所有 Quote 块，转换为 ExclusionZone。"""
    from babeldoc.format.pdf.document_il.utils.layout_helper import (
        get_quote_exclusion_margins,
        is_quote_block,
    )

    zones: list[ExclusionZone] = []

    # 获取页面尺寸
    page_width = _get_page_width(page)
    page_height = _get_page_height(page)
    if page_width <= 0 or page_height <= 0:
        return zones

    for para in page.pdf_paragraph or []:
        if para.box is None:
            continue

        if not is_quote_block(
            para,
            page_width,
            narrow_threshold=config.narrow_threshold,
            indent_threshold=config.indent_threshold,
            right_margin_threshold=config.right_margin_threshold,
        ):
            continue

        # 计算含边距的排除区域
        margins = get_quote_exclusion_margins(
            para, page_width, page_height,
            left_margin=config.left_margin,
            top_margin=config.top_margin,
            bottom_margin=config.bottom_margin,
        )
        left_margin, top_margin, right_margin, bottom_margin = margins

        box = para.box
        exclusion_box = Box(
            x=box.x - left_margin,
            y=box.y - bottom_margin,
            x2=box.x2 + right_margin,
            y2=box.y2 + top_margin,
        )

        zones.append(ExclusionZone(
            box=exclusion_box,
            kind=ZONE_QUOTE,
            priority=20,  # Quote 优先级高于正文
            margins=margins,
        ))

    if zones:
        logger.debug(
            f"Page {page.page_number}: built {len(zones)} quote exclusion zones"
        )

    return zones


def _get_page_width(page: Page) -> float:
    if page.cropbox and page.cropbox.box:
        return page.cropbox.box.x2 - page.cropbox.box.x
    if page.mediabox and page.mediabox.box:
        return page.mediabox.box.x2 - page.mediabox.box.x
    return 0.0


def _get_page_height(page: Page) -> float:
    if page.cropbox and page.cropbox.box:
        return page.cropbox.box.y2 - page.cropbox.box.y
    if page.mediabox and page.mediabox.box:
        return page.mediabox.box.y2 - page.mediabox.box.y
    return 0.0


class ExclusionZoneIndex:
    """基于 R-tree 的排除区域空间索引。

    支持高效的 per-line 可用宽度查询，用于动态行宽计算。
    """

    def __init__(self, zones: list[ExclusionZone]):
        self.zones = zones
        self._rtree = None
        if zones:
            self._rtree = rtree_index.Index()
            for i, zone in enumerate(zones):
                self._rtree.insert(i, box_to_tuple(zone.box))

    def get_available_x_range(
        self,
        y_bottom: float,
        y_top: float,
        default_x: float,
        default_x2: float,
    ) -> tuple[float, float]:
        """给定行的 y 范围，返回该行可用的 x 范围。

        对于与行有垂直交集的排除区域：
        - 如果区域在文本右侧 → 收窄 available_x2
        - 如果区域在文本左侧 → 收窄 available_x

        Args:
            y_bottom: 行底部 y 坐标
            y_top: 行顶部 y 坐标
            default_x: 默认左边界（通常是 paragraph.box.x）
            default_x2: 默认右边界（通常是 paragraph.box.x2）

        Returns:
            (available_x, available_x2) 可用的左右边界
        """
        if not self.zones:
            return (default_x, default_x2)

        available_x = default_x
        available_x2 = default_x2

        # 查询与行 y 范围有交集的 zones
        # R-tree 查询使用 (x_min, y_min, x_max, y_max)
        # 用 default_x/default_x2 作为 x 范围的宽松边界
        candidates = list(self._rtree.intersection(
            (default_x - 1000, y_bottom, default_x2 + 1000, y_top)
        ))

        for zone_idx in candidates:
            zone = self.zones[zone_idx]
            z = zone.box

            # 检查垂直方向是否有交集
            if z.y >= y_top or z.y2 <= y_bottom:
                continue

            # 检查水平方向是否与文本区域有交集
            # （排除完全在文本区域之外的 zone）
            if z.x2 <= default_x or z.x >= default_x2:
                continue

            # Zone 完全覆盖文本区域 → 无可用空间
            if z.x <= available_x and z.x2 >= available_x2:
                available_x = available_x2  # 降级为零宽度
                break

            # Zone 完全包含在文本区域内 → 选择更宽的一侧
            if z.x > available_x and z.x2 < available_x2:
                left_gap = z.x - available_x
                right_gap = available_x2 - z.x2
                if left_gap >= right_gap:
                    available_x2 = z.x  # 保留左侧
                else:
                    available_x = z.x2  # 保留右侧
            elif z.x > available_x:
                # Zone 从右侧收窄
                available_x2 = min(available_x2, z.x)
            elif z.x2 < available_x2:
                # Zone 从左侧收窄
                available_x = max(available_x, z.x2)

        return (available_x, available_x2)
