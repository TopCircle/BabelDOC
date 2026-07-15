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

# polygon_scanline_blocked_intervals 的类型别名
# 每个元素是一个 (x_start, x_end) 区间，表示多边形在该 y 处覆盖的 x 范围
BlockedInterval = tuple[float, float]

from rtree import index as rtree_index

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import Page
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.utils.layout_helper import box_to_tuple
from babeldoc.format.pdf.document_il.utils.layout_helper import get_adaptive_image_padding

logger = logging.getLogger(__name__)

# ExclusionZone 类型常量
ZONE_QUOTE = "quote"
ZONE_FIGURE = "figure"
ZONE_TABLE = "table"
ZONE_FORMULA = "formula"
ZONE_SIDEBAR = "sidebar"

ZoneKind = Literal["quote", "figure", "table", "formula", "sidebar"]

# Minimum continuous horizontal strip (pt) that may host body text.
# Narrower residuals force ~1–4pt scale crush (Orgasms p.10/19/20).
# ~4 CJK chars at ~7pt ≈ 28pt; also used as floor vs 15% of paragraph width.
MIN_USABLE_LINE_WIDTH_PT = 28.0


def min_usable_line_width(para_width: float | None = None) -> float:
    """Minimum usable line width for wrap / residual-strip decisions.

    Uses the larger of an absolute floor and a fraction of the paragraph
    width so very wide pages still reject needle-thin strips.
    """
    floor = MIN_USABLE_LINE_WIDTH_PT
    if para_width is not None and para_width > 0:
        return max(floor, para_width * 0.15)
    return floor


@dataclass(frozen=True, slots=True)
class ExclusionZone:
    """一个排版排除区域。

    Attributes:
        box: 排除区域的边界框（含 margins）
        kind: 区域类型（quote, figure, table, formula, sidebar）
        priority: 优先级，数字越大越优先保留（正文让路）
        margins: 原始边距 (left, top, right, bottom)，用于调试
        polygon: 可选的多边形顶点列表，用于非矩形排除区（Phase 2b）
    """

    box: Box
    kind: ZoneKind
    priority: int = 10
    margins: tuple[float, float, float, float] | None = None
    polygon: tuple[tuple[float, float], ...] | None = None


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
        zones.extend(_collect_figure_zones(page))
        # 未来扩展:
        # zones.extend(_collect_table_zones(page))
        return zones


@dataclass
class QuoteZoneConfig:
    """Quote 区域检测参数。"""
    narrow_threshold: float = 0.8
    # Must exceed typical body page margin (~5–12%); see is_quote_block.
    indent_threshold: float = 0.15
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

        box = para.box
        para_width = box.x2 - box.x
        width_ratio = para_width / page_width if page_width > 0 else 1.0
        left_indent = box.x
        indent_ratio = left_indent / page_width if page_width > 0 else 0.0
        right_margin = page_width - box.x2
        margin_ratio = right_margin / page_width if page_width > 0 else 0.0

        is_quote = is_quote_block(
            para,
            page_width,
            narrow_threshold=config.narrow_threshold,
            indent_threshold=config.indent_threshold,
            right_margin_threshold=config.right_margin_threshold,
        )

        if not is_quote:
            # 诊断日志：记录为什么不是 Quote
            if width_ratio < 0.9:  # 只记录窄段落（排除明显不是 Quote 的）
                logger.debug(
                    f"Page {page.page_number}: para at ({box.x:.1f},{box.y:.1f})-({box.x2:.1f},{box.y2:.1f}) "
                    f"NOT quote: width_ratio={width_ratio:.3f}(<{config.narrow_threshold}), "
                    f"indent_ratio={indent_ratio:.3f}(>{config.indent_threshold}), "
                    f"margin_ratio={margin_ratio:.3f}(>{config.right_margin_threshold})"
                )
            continue

        # 计算含边距的排除区域（自适应 padding）
        from babeldoc.format.pdf.document_il.midend.flow_skeleton import get_paragraph_font_size
        font_size = get_paragraph_font_size(para)
        adaptive_margin = get_adaptive_image_padding(font_size)
        # 将自适应 margin 转为相对于页面尺寸的比例
        adaptive_left = adaptive_margin / page_width if page_width > 0 else config.left_margin
        adaptive_top = adaptive_margin / page_height if page_height > 0 else config.top_margin
        adaptive_bottom = adaptive_margin / page_height if page_height > 0 else config.bottom_margin

        margins = get_quote_exclusion_margins(
            para, page_width, page_height,
            left_margin=adaptive_left,
            top_margin=adaptive_top,
            bottom_margin=adaptive_bottom,
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


def _collect_figure_zones(page: Page) -> list[ExclusionZone]:
    """收集页面中所有图形区域，转换为 ExclusionZone。

    来源：
    1. PdfFigure — 布局模型检测的图形 bounding box
    2. PdfForm (form_type="image") — PDF 中的图片 XObject
    """
    zones: list[ExclusionZone] = []
    seen_boxes: set[tuple[float, float, float, float]] = set()

    page_width = _get_page_width(page)
    page_height = _get_page_height(page)
    if page_width <= 0 or page_height <= 0:
        return zones

    def _add_zone(box: Box, kind: str = ZONE_FIGURE) -> None:
        """添加一个 figure 排除区，自动去重和添加 padding。"""
        # 去重：同一位置的图形只添加一次
        key = (round(box.x, 1), round(box.y, 1), round(box.x2, 1), round(box.y2, 1))
        if key in seen_boxes:
            return
        seen_boxes.add(key)

        # 使用固定 padding（绝对值，单位 pt）
        # 12pt 是合理的图文间距，与 get_adaptive_image_padding 的最小值一致
        padding = 12.0

        exclusion_box = Box(
            x=box.x - padding,
            y=box.y - padding,
            x2=box.x2 + padding,
            y2=box.y2 + padding,
        )

        zones.append(ExclusionZone(
            box=exclusion_box,
            kind=kind,
            priority=20,  # Figure 优先级高于 quote(10)
            margins=(padding, padding, padding, padding),
        ))

    # 收集 PdfFigure（布局模型检测的图形区域）
    for figure in page.pdf_figure or []:
        if figure.box is not None:
            _add_zone(figure.box)

    # 收集 PdfForm 中的图片（form_type="image"）
    for form in page.pdf_form or []:
        if form.form_type == "image" and form.box is not None:
            _add_zone(form.box)

    if zones:
        logger.debug(
            f"Page {page.page_number}: built {len(zones)} figure exclusion zones"
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


def polygon_scanline_blocked_intervals(
    y: float,
    polygon: tuple[tuple[float, float], ...],
) -> list[BlockedInterval]:
    """计算水平扫描线 y 与多边形的交集区间。

    使用 even-odd rule：排序交点，配对后每对之间的区间为 blocked。

    Args:
        y: 扫描线的 y 坐标
        polygon: 多边形顶点列表，每对 (x, y) 是一个顶点，隐式闭合

    Returns:
        blocked 区间列表 [(x_start, x_end), ...]，按 x 排序且不重叠
    """
    if len(polygon) < 3:
        return []

    n = len(polygon)
    intersections: list[float] = []

    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]

        # 确保 y1 <= y2（方便后续判断）
        if y1 > y2:
            x1, y1, x2, y2 = x2, y2, x1, y1

        # 边与扫描线无交集
        if y < y1 or y >= y2:
            continue

        # y == y2 时跳过（vertex-on-scanline 守卫：只在 y_max 端计数）
        # 这避免了退化交点（多边形顶点恰好在扫描线上）
        if y == y2 and y1 != y2:
            continue

        # 计算交点的 x 坐标（线性插值）
        if abs(y2 - y1) < 1e-10:
            # 水平边，跳过
            continue

        t = (y - y1) / (y2 - y1)
        x_intersect = x1 + t * (x2 - x1)
        intersections.append(x_intersect)

    # 排序并配对
    intersections.sort()

    # 配对：每两个交点之间是 blocked 区间
    intervals: list[BlockedInterval] = []
    i = 0
    while i + 1 < len(intersections):
        x_start = intersections[i]
        x_end = intersections[i + 1]
        if x_end - x_start > 1e-6:  # 忽略退化区间
            intervals.append((x_start, x_end))
        i += 2

    return intervals


def _merge_blocked_intervals(intervals: list[BlockedInterval]) -> list[BlockedInterval]:
    """合并重叠的 blocked 区间。"""
    if not intervals:
        return []

    sorted_intervals = sorted(intervals, key=lambda iv: iv[0])
    merged = [sorted_intervals[0]]

    for start, end in sorted_intervals[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end + 1e-6:
            # 重叠或相邻，合并
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))

    return merged


def _box_intersection_area(a: Box, b: Box) -> float:
    """Axis-aligned box intersection area; 0 if no overlap."""
    if a is None or b is None:
        return 0.0
    x1 = max(a.x, b.x)
    y1 = max(a.y, b.y)
    x2 = min(a.x2, b.x2)
    y2 = min(a.y2, b.y2)
    if x2 <= x1 or y2 <= y1:
        return 0.0
    return (x2 - x1) * (y2 - y1)


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

    def filter_for_paragraph(
        self,
        para_box: Box,
        *,
        max_coverage: float = 0.35,
        min_residual_width: float | None = None,
        drop_all_figures: bool = False,
    ) -> ExclusionZoneIndex:
        """Filter figure zones for one paragraph (quotes always kept).

        Side-image ebooks (Orgasms p.3/8/13) often place a **full-height photo
        bbox** on the right while English line lengths **vary** and intentionally
        run into that bbox (artistic wrap, not a hard rectangular column).
        Applying those figures as exclusion zones forces a uniform ~150pt strip
        — worse than following original ``reference_widths``.

        Rules (figures only):

        1. ``drop_all_figures`` — strip every figure (scale-floor retry).
        2. **Artistic overlay**: if the original paragraph box already extends
           past the figure's left edge (text was designed into the photo bbox),
           **drop** the zone and let original line metrics drive shape.
        3. **Needle residual**: residual strip after carving the figure is
           narrower than ``min_residual_width`` and the figure actually bites
           the para → **drop** (avoids 1–4pt scale crush).
        4. **Clean side float**: body sits fully left of the figure
           (``para.x2 <= zone.x``) with usable residual → **keep** for hard
           rectangular wrap.

        Args:
            para_box: Paragraph layout box (original EN geometry).
            max_coverage: Legacy API; residual/overlay rules decide.
            min_residual_width: Floor for a usable wrap strip.
            drop_all_figures: Drop all figures regardless.
        """
        if not self.zones or para_box is None:
            return self

        para_w = para_box.x2 - para_box.x
        para_h = para_box.y2 - para_box.y
        para_area = para_w * para_h
        if para_area <= 1.0:
            return self

        if min_residual_width is None:
            min_residual_width = min_usable_line_width(para_w)

        kept: list[ExclusionZone] = []
        dropped = 0
        for zone in self.zones:
            if zone.kind != ZONE_FIGURE:
                kept.append(zone)
                continue
            if drop_all_figures:
                dropped += 1
                continue

            coverage = _box_intersection_area(para_box, zone.box) / para_area
            residual = _max_horizontal_residual(para_box, zone.box)
            z = zone.box

            # No real horizontal bite → keep (disjoint / no effect on x range)
            if coverage <= 1e-6:
                kept.append(zone)
                continue

            # Original text already runs into the figure bbox → freeform/artistic
            # wrap encoded in line widths. Hard clip → ugly equal-width column.
            # (EN lines on Orgasms p.3 end near x=400 while figure starts ~231.)
            if para_box.x2 > z.x + 8.0:
                dropped += 1
                logger.debug(
                    "Dropping figure zone: paragraph extends into figure "
                    "(para.x2=%.0f > zone.x=%.0f); use original line metrics "
                    "instead of rectangular clip",
                    para_box.x2,
                    z.x,
                )
                continue

            # Needle / full cover with no usable strip → drop to avoid crush
            if residual < min_residual_width:
                dropped += 1
                logger.debug(
                    "Dropping figure zone: residual %.1fpt < %.1fpt "
                    "(coverage %.0f%%): zone=(%.0f,%.0f)-(%.0f,%.0f)",
                    residual,
                    min_residual_width,
                    coverage * 100,
                    z.x,
                    z.y,
                    z.x2,
                    z.y2,
                )
                continue

            # Clean side-by-side: body left of figure with room to wrap
            kept.append(zone)

        if dropped == 0:
            return self
        return ExclusionZoneIndex(kept)

    def get_available_x_range(
        self,
        y_bottom: float,
        y_top: float,
        default_x: float,
        default_x2: float,
        min_width: float | None = None,
    ) -> tuple[float, float]:
        """给定行的 y 范围，返回该行可用的 x 范围。

        对于与行有垂直交集的排除区域：
        - 如果区域在文本右侧 → 收窄 available_x2
        - 如果区域在文本左侧 → 收窄 available_x
        - 如果区域有多边形 → 使用 scanline 计算精确 blocked 区间

        若收窄后宽度 < ``min_width``（默认 :data:`MIN_USABLE_LINE_WIDTH_PT`），
        回退到 ``(default_x, default_x2)``，避免在针尖缝里排正文。

        Args:
            y_bottom: 行底部 y 坐标
            y_top: 行顶部 y 坐标
            default_x: 默认左边界（通常是 paragraph.box.x）
            default_x2: 默认右边界（通常是 paragraph.box.x2）
            min_width: 最小可用宽度；None 时用绝对地板

        Returns:
            (available_x, available_x2) 可用的左右边界
        """
        if not self.zones:
            return (default_x, default_x2)

        if min_width is None:
            min_width = min_usable_line_width(default_x2 - default_x)

        available_x = default_x
        available_x2 = default_x2

        # 收集所有 blocked 区间（来自多边形 zones）
        all_blocked: list[BlockedInterval] = []

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

            # 多边形 zone：使用 scanline 计算精确 blocked 区间
            if zone.polygon is not None:
                scan_y = (y_bottom + y_top) / 2.0
                blocked = polygon_scanline_blocked_intervals(scan_y, zone.polygon)
                # 只保留与文本区域有交集的 blocked 区间
                for bx_start, bx_end in blocked:
                    if bx_end > default_x and bx_start < default_x2:
                        all_blocked.append((
                            max(bx_start, default_x),
                            min(bx_end, default_x2),
                        ))
                continue

            # 矩形 zone：原有逻辑
            # Zone 完全覆盖文本区域 → 无可用空间
            if z.x <= available_x and z.x2 >= available_x2:
                available_x = available_x2  # 降级为零宽度
                break

            # Zone 完全包含在文本区域内 → 选择可用残条
            # Prefer the LEFT residual when it is usable: side-photo ebooks
            # (Orgasms p.21) put the figure on the right; picking the thinner
            # right strip centers body text mid-photo.
            if z.x > available_x and z.x2 < available_x2:
                left_gap = z.x - available_x
                right_gap = available_x2 - z.x2
                if left_gap >= min_width:
                    available_x2 = z.x  # keep left (normal side-photo wrap)
                elif right_gap >= min_width:
                    available_x = z.x2  # only right strip is usable
                elif left_gap >= right_gap:
                    available_x2 = z.x
                else:
                    available_x = z.x2
            elif z.x > available_x:
                # Zone 从右侧收窄
                available_x2 = min(available_x2, z.x)
            elif z.x2 < available_x2:
                # Zone 从左侧收窄
                available_x = max(available_x, z.x2)

        # 多边形 blocked 区间处理：从可用区间中减去 blocked，取最宽的连续区间
        if all_blocked:
            result = _subtract_blocked_from_range(
                available_x, available_x2, all_blocked
            )
            available_x, available_x2 = result

        # Zero / inverted / needle-thin → fall back to full paragraph width
        usable = available_x2 - available_x
        if usable < min_width:
            logger.debug(
                "Zone strip too narrow (%.1fpt < %.1fpt) at y=[%.1f,%.1f]; "
                "using full paragraph width [%.1f,%.1f]",
                usable,
                min_width,
                y_bottom,
                y_top,
                default_x,
                default_x2,
            )
            return (default_x, default_x2)

        # 诊断日志：记录 zone 对可用宽度的影响
        if available_x != default_x or available_x2 != default_x2:
            logger.debug(
                f"Zone narrowed line at y=[{y_bottom:.1f},{y_top:.1f}]: "
                f"original=[{default_x:.1f},{default_x2:.1f}] "
                f"→ available=[{available_x:.1f},{available_x2:.1f}] "
                f"(narrowed by {len(candidates)} zones)"
            )

        return (available_x, available_x2)


def _max_horizontal_residual(para_box: Box, zone_box: Box) -> float:
    """Widest horizontal strip of ``para_box`` left after removing ``zone_box``.

    Returns 0 if the zone fully covers the paragraph horizontally.
    Returns a large value if they do not horizontally intersect (caller should
    usually skip residual logic in that case via coverage).
    """
    if para_box is None or zone_box is None:
        return float("inf")
    # No horizontal overlap → residual is full para width
    if zone_box.x2 <= para_box.x or zone_box.x >= para_box.x2:
        return para_box.x2 - para_box.x

    left = max(0.0, zone_box.x - para_box.x)
    right = max(0.0, para_box.x2 - zone_box.x2)
    return max(left, right)


def _subtract_blocked_from_range(
    range_start: float,
    range_end: float,
    blocked: list[BlockedInterval],
) -> tuple[float, float]:
    """从可用区间中减去 blocked 区间，返回最宽的连续子区间。

    例如：range=[0, 100], blocked=[(30, 50)] → [(0, 30), (50, 100)] → 返回 (50, 100)

    注意：对于倾斜多边形，随着扫描线 y 变化，最宽子区间可能在左右两侧之间切换，
    导致文本位置跳跃。这是单区间返回值的固有限制。
    """
    if not blocked:
        return (range_start, range_end)

    merged = _merge_blocked_intervals(blocked)

    # 计算所有可用子区间
    available: list[tuple[float, float]] = []
    cursor = range_start

    for bx_start, bx_end in merged:
        if bx_start > cursor:
            available.append((cursor, bx_start))
        cursor = max(cursor, bx_end)

    if cursor < range_end:
        available.append((cursor, range_end))

    if not available:
        return (range_start, range_start)  # 完全 blocked

    # 返回最宽的区间；宽度相等时优先选择左侧（更符合阅读习惯）
    best = max(available, key=lambda iv: (iv[1] - iv[0], -(iv[0])))
    return best
