"""Layout Composer（约束排版器）

在 Publisher Skeleton 约束下重建排版。

核心变化（v4）：
- 复用现有 TypesettingUnit（passthrough/formula/unicode）
- 复用现有 Knuth-Plass DP 优化器
- 只替换 get_available_x_range → get_intervals_at
- 保留 scale 计算管线
"""

import logging
from dataclasses import dataclass, field

from babeldoc.format.pdf.document_il import il_version_1
from babeldoc.format.pdf.document_il.midend.flow_skeleton import (
    PublisherSkeleton,
    FlowRegion,
    FlowStateType,
    VisualObject,
    ConstraintPriority,
    Padding,
)

logger = logging.getLogger(__name__)


# ============================================================
# TypesettingUnit（排版单位）
# ============================================================

@dataclass
class TypesettingUnit:
    """排版单位。兼容现有三种模式。"""

    # === 模式 1: PdfCharacter passthrough ===
    char: il_version_1.PdfCharacter | None = None

    # === 模式 2: PdfFormula passthrough ===
    formular: il_version_1.PdfFormula | None = None

    # === 模式 3: unicode 渲染 ===
    unicode: str | None = None

    # === 通用属性 ===
    width: float = 0.0
    height: float = 0.0
    box: il_version_1.Box | None = None
    xobj_id: int | None = None

    # === passthrough 标志 ===
    can_passthrough: bool = False

    # === 断行属性（复用现有逻辑） ===
    can_break_line: bool = False
    is_cjk_char: bool = False
    is_space: bool = False
    is_hung_punctuation: bool = False
    is_cannot_appear_in_line_end_punctuation: bool = False

    # === 样式 ===
    font_size: float = 10.0
    font_family: str = ""

    # === 来源 ===
    source_paragraph_id: int | None = None

    def relocate(self, x: float, y: float, scale: float) -> 'TypesettingUnit':
        """将 unit 放置在指定位置。

        创建一个新的 TypesettingUnit，box 使用新的位置和缩放后的尺寸。
        char/formular 保持引用（commit_line 会更新其位置）。
        """
        # 创建新的 box（使用缩放后的尺寸）
        new_box = il_version_1.Box(
            x=x,
            y=y,
            x2=x + self.width * scale,
            y2=y + self.height * scale,
        )

        # 返回新的 TypesettingUnit
        # 注意：char/formular 保持引用，commit_line 会处理位置更新
        return TypesettingUnit(
            char=self.char,
            formular=self.formular,
            unicode=self.unicode,
            width=self.width,
            height=self.height,
            box=new_box,
            xobj_id=self.xobj_id,
            can_passthrough=self.can_passthrough,
            can_break_line=self.can_break_line,
            is_cjk_char=self.is_cjk_char,
            is_space=self.is_space,
            is_hung_punctuation=self.is_hung_punctuation,
            is_cannot_appear_in_line_end_punctuation=self.is_cannot_appear_in_line_end_punctuation,
            font_size=self.font_size,
            font_family=self.font_family,
            source_paragraph_id=self.source_paragraph_id,
        )


# ============================================================
# ConstraintComposer（约束排版器）
# ============================================================

class ConstraintComposer:
    """
    在 Publisher Skeleton 约束下重建排版。

    核心变化（v4）：
    - 复用现有 TypesettingUnit（passthrough/formula/unicode）
    - 复用现有 Knuth-Plass DP 优化器
    - 只替换 get_available_x_range → get_intervals_at
    - 保留 scale 计算管线
    """

    def __init__(self, skeleton: PublisherSkeleton):
        self.skeleton = skeleton

    def compose_paragraph(self, paragraph: il_version_1.PdfParagraph,
                          units: list[TypesettingUnit],
                          scale: float) -> list[il_version_1.PdfLine]:
        """
        排版一个段落。

        流程（复用现有逻辑）：
        1. 获取段落的 optimal_scale（保留现有 preprocess_document）
        2. 调用 _layout_typesetting_units（修改为多区间）
        3. 调用 fix_overlapping_paragraphs_post_typesetting
        """
        # 复用现有的 _find_optimal_scale_and_layout 逻辑
        # 只替换内部的 get_available_x_range 调用
        return self._layout_with_multi_intervals(paragraph, units, scale)

    def _layout_with_multi_intervals(self, paragraph: il_version_1.PdfParagraph,
                                      units: list[TypesettingUnit],
                                      scale: float) -> list[il_version_1.PdfLine]:
        """
        多区间排版主循环。

        复用现有 Knuth-Plass DP 优化器，只替换宽度查询接口。
        """
        box = paragraph.box
        avg_height = compute_avg_height(units, scale)

        # 获取样式
        style = self.skeleton.get_style_at((box.y + box.y2) / 2)
        line_height = style.leading if style else avg_height * 1.4

        # === 步骤 1：估算每行宽度（多区间版本） ===
        line_widths = self._estimate_line_widths_multi(box, avg_height, line_height)

        # === 步骤 2：调用现有 DP 优化器获取断点 ===
        break_points = self._compute_optimal_breaks(units, line_widths, scale)

        # === 步骤 3：按断点排版（多区间感知） ===
        if break_points:
            return self._layout_with_break_points(
                paragraph, units, scale, break_points, line_height)
        else:
            return self._layout_greedy_multi(
                paragraph, units, scale, line_height)

    def _estimate_line_widths_multi(self, box: il_version_1.Box,
                                     avg_height: float,
                                     line_height: float) -> list[float]:
        """
        估算每行可用宽度（多区间版本）。

        复用现有 _estimate_line_widths 逻辑，但使用 get_intervals_at。
        每行的宽度 = 所有区间宽度之和。
        """
        widths = []
        y = box.y2 - avg_height
        while y >= box.y:
            intervals = self.skeleton.get_intervals_at(y)
            if intervals:
                # 多区间：总宽度 = 所有区间之和
                total_width = sum(ix2 - ix1 for ix1, ix2 in intervals)
            else:
                # 回退到页面宽度
                total_width = self.skeleton.page_x_max - self.skeleton.page_x_min
            widths.append(total_width)
            y -= line_height
        return widths

    def _compute_optimal_breaks(self, units: list[TypesettingUnit],
                                 line_widths: list[float],
                                 scale: float) -> list[int] | None:
        """
        调用现有 Knuth-Plass DP 优化器获取断点。

        复用现有 optimal_line_break（line_break_optimizer.py）。
        """
        try:
            from babeldoc.format.pdf.document_il.midend.line_break_optimizer import optimal_line_break
            return optimal_line_break(
                units, line_widths, scale,
                space_width=self._get_space_width(units),
                decorative_tracking=0,
            )
        except ImportError:
            logger.warning("line_break_optimizer not available, falling back to greedy")
            return None

    def _get_space_width(self, units: list[TypesettingUnit]) -> float:
        """获取空格宽度。"""
        for unit in units:
            if unit.is_space:
                return unit.width
        return 3.0  # 默认空格宽度

    def _layout_with_break_points(self, paragraph: il_version_1.PdfParagraph,
                                   units: list[TypesettingUnit],
                                   scale: float,
                                   break_points: list[int],
                                   line_height: float) -> list[il_version_1.PdfLine]:
        """
        按 DP 断点排版（多区间感知）。

        每行：
        1. 获取当前 y 的区间集合
        2. 从第一个区间开始填入
        3. 当前区间放不下 → 跳到下一个区间
        4. 所有区间都放不下 → 换行（由 break_points 控制）
        """
        box = paragraph.box
        lines = []
        current_y = box.y2 - compute_avg_height(units, scale)
        unit_idx = 0

        for bp in break_points:
            line_units = units[unit_idx:bp]
            current_y, placed_units = self._place_line_in_intervals(
                line_units, current_y, scale, line_height, box)
            if placed_units:
                lines.append(commit_line(placed_units, current_y,
                                         compute_avg_height(units, scale)))
            current_y -= line_height
            unit_idx = bp

        # 最后一行
        if unit_idx < len(units):
            line_units = units[unit_idx:]
            current_y, placed_units = self._place_line_in_intervals(
                line_units, current_y, scale, line_height, box)
            if placed_units:
                lines.append(commit_line(placed_units, current_y,
                                         compute_avg_height(units, scale)))

        return lines

    def _place_line_in_intervals(self, units: list[TypesettingUnit],
                                  y: float, scale: float,
                                  line_height: float,
                                  box: il_version_1.Box) -> tuple[float, list[TypesettingUnit]]:
        """
        将一行 unit 放入当前 y 的区间集合中。

        返回 (实际 y, 放置后的 units)。
        """
        intervals = self.skeleton.get_intervals_at(y)
        if not intervals:
            intervals = [(self.skeleton.page_x_min, self.skeleton.page_x_max)]

        style = self.skeleton.get_style_at(y)
        placed = []
        interval_idx = 0
        current_x = intervals[0][0] if intervals else box.x
        is_line_start = True  # 标记是否是行首（用于缩进）

        for unit in units:
            unit_width = unit.width * scale
            placed_flag = False

            while interval_idx < len(intervals):
                ix1, ix2 = intervals[interval_idx]

                # 应用缩进：只在行首（第一个 unit 的第一个区间）应用
                if is_line_start and style:
                    ix1 += style.left_indent

                if current_x < ix1:
                    current_x = ix1

                if current_x + unit_width <= ix2:
                    placed.append(unit.relocate(current_x, y, scale))
                    current_x += unit_width
                    placed_flag = True
                    is_line_start = False  # 行首标记只生效一次
                    break
                else:
                    interval_idx += 1
                    if interval_idx < len(intervals):
                        current_x = intervals[interval_idx][0]

            if not placed_flag:
                # 放不下，强制放入当前区间（溢出）
                if intervals:
                    placed.append(unit.relocate(current_x, y, scale))
                    current_x += unit_width
                    is_line_start = False

        return y, placed

    def _layout_greedy_multi(self, paragraph: il_version_1.PdfParagraph,
                              units: list[TypesettingUnit],
                              scale: float,
                              line_height: float) -> list[il_version_1.PdfLine]:
        """
        贪心排版（DP 不可用时的回退）。

        复用现有 _layout_typesetting_units 逻辑，改为多区间。
        """
        box = paragraph.box
        avg_height = compute_avg_height(units, scale)
        lines = []
        current_line = []
        current_y = box.y2 - avg_height
        current_interval_idx = 0
        current_x = box.x

        for unit in units:
            unit_width = unit.width * scale
            placed = False

            while not placed:
                intervals = self.skeleton.get_intervals_at(current_y)
                if not intervals:
                    intervals = [(self.skeleton.page_x_min, self.skeleton.page_x_max)]

                if not intervals:
                    break

                style = self.skeleton.get_style_at(current_y)

                while current_interval_idx < len(intervals):
                    ix1, ix2 = intervals[current_interval_idx]

                    if not current_line and style:
                        ix1 += style.left_indent

                    if current_x < ix1:
                        current_x = ix1

                    if current_x + unit_width <= ix2:
                        placed_unit = unit.relocate(current_x, current_y, scale)
                        current_line.append(placed_unit)
                        current_x += unit_width
                        placed = True
                        break
                    else:
                        current_interval_idx += 1
                        if current_interval_idx < len(intervals):
                            current_x = intervals[current_interval_idx][0]

                if not placed:
                    if current_line:
                        lines.append(commit_line(current_line, current_y, avg_height))
                        current_line = []
                    current_y -= line_height
                    current_interval_idx = 0
                    current_x = box.x
                    if current_y < box.y:
                        # 段落空间不足，强制放入最后一行避免丢失内容
                        logger.warning(
                            "Paragraph box exhausted, force-placing remaining %d units",
                            len(units) - units.index(unit),
                        )
                        # 从当前 unit 开始，强制放入当前行
                        for remaining_unit in units[units.index(unit):]:
                            current_line.append(remaining_unit.relocate(
                                current_x, current_y + line_height, scale))
                            current_x += remaining_unit.width * scale
                        lines.append(commit_line(current_line, current_y + line_height, avg_height))
                        return lines

        if current_line:
            lines.append(commit_line(current_line, current_y, avg_height))

        return lines

    def apply_constraints(self, units: list[TypesettingUnit],
                          scale: float = 1.0) -> list[TypesettingUnit]:
        """
        应用几何约束（带优先级）。

        优先级：
        - HARD: 绝对不可侵犯（Logo、页码）
        - SOFT: 尽量保持（图片、Quote）
        - RELAXABLE: 可以调整（正文间距、字号）
        """
        for unit in units:
            y = unit.box.y if unit.box else 0

            # 检查 HARD 约束
            for obj in self.skeleton.objects:
                if obj.priority == ConstraintPriority.HARD:
                    if self._violates_constraint(unit, obj):
                        unit = self._move_away_from(unit, obj, scale)

            # 检查 SOFT 约束
            for obj in self.skeleton.objects:
                if obj.priority == ConstraintPriority.SOFT:
                    if self._violates_constraint(unit, obj):
                        unit = self._adjust_for_soft_constraint(unit, obj)

        return units

    def _violates_constraint(self, unit: TypesettingUnit, obj: VisualObject) -> bool:
        """检查 unit 是否违反约束。"""
        if not unit.box:
            return False

        # 检查是否在对象的 padding 区域内
        obj_left = obj.bbox.x - obj.padding.left
        obj_right = obj.bbox.x2 + obj.padding.right
        obj_top = obj.bbox.y2 + obj.padding.top
        obj_bottom = obj.bbox.y - obj.padding.bottom

        return (unit.box.x < obj_right and unit.box.x2 > obj_left and
                unit.box.y < obj_top and unit.box.y2 > obj_bottom)

    def _move_away_from(self, unit: TypesettingUnit, obj: VisualObject,
                        scale: float = 1.0) -> TypesettingUnit:
        """将 unit 移开 HARD 约束对象。"""
        if not unit.box:
            return unit

        # 计算移动方向（向左或向右）
        obj_center = (obj.bbox.x + obj.bbox.x2) / 2
        unit_center = (unit.box.x + unit.box.x2) / 2

        # 使用缩放后的宽度计算新位置
        scaled_width = unit.width * scale
        if unit_center < obj_center:
            # 向左移动
            new_x = obj.bbox.x - obj.padding.left - scaled_width
        else:
            # 向右移动
            new_x = obj.bbox.x2 + obj.padding.right

        return unit.relocate(new_x, unit.box.y, scale)

    def _adjust_for_soft_constraint(self, unit: TypesettingUnit,
                                    obj: VisualObject) -> TypesettingUnit:
        """
        调整 unit 以满足 SOFT 约束。

        策略（按优先级）：
        1. 缩小行间距 (-10%)
        2. 缩小字号 (-5%)
        3. 缩小段落间距 (-20%)
        """
        # 策略 1: 缩小行间距
        # 策略 2: 缩小字号
        # 策略 3: 缩小段落间距
        # 这些策略需要在更高层实现，这里只是占位
        return unit


# ============================================================
# 辅助函数
# ============================================================

def compute_avg_height(units: list[TypesettingUnit], scale: float) -> float:
    """计算单位的平均高度。"""
    if not units:
        return 10.0 * scale

    heights = [unit.height for unit in units if unit.height > 0]
    if heights:
        return sum(heights) / len(heights) * scale
    return 10.0 * scale


def commit_line(units: list[TypesettingUnit], y: float,
                avg_height: float) -> il_version_1.PdfLine:
    """将一行 units 提交为 PdfLine。

    处理三种 unit 类型：
    - char (PdfCharacter passthrough): 直接添加
    - formular (PdfFormula): 更新公式位置后添加其字符
    - unicode: 记录警告（PdfLine 不支持纯 unicode）
    """
    characters = []
    for u in units:
        if u.char:
            # PdfCharacter passthrough
            characters.append(u.char)
        elif u.formular:
            # PdfFormula: 更新公式位置并提取字符
            if u.box:
                u.formular.box = u.box
            if hasattr(u.formular, 'pdf_character'):
                characters.extend(u.formular.pdf_character)
        elif u.unicode:
            # unicode 渲染模式：PdfLine 不支持纯 unicode，记录警告
            logger.warning("Unicode unit lost in commit_line: %r", u.unicode)

    # 创建 PdfLine
    line = il_version_1.PdfLine(
        box=il_version_1.Box(
            x=min(u.box.x for u in units if u.box),
            y=y,
            x2=max(u.box.x2 for u in units if u.box),
            y2=y + avg_height,
        ),
        pdf_character=characters,
    )
    return line


def create_typesetting_units_from_paragraph(
    paragraph: il_version_1.PdfParagraph,
) -> list[TypesettingUnit]:
    """从段落创建 TypesettingUnit 列表。

    复用现有 typesetting.py 的 create_typesetting_units 逻辑。
    """
    units = []

    for comp in paragraph.pdf_paragraph_composition:
        if comp.pdf_character:
            # PdfCharacter passthrough
            char = comp.pdf_character
            units.append(TypesettingUnit(
                char=char,
                width=char.box.x2 - char.box.x if char.box else 0,
                height=char.box.y2 - char.box.y if char.box else 0,
                box=char.box,
                xobj_id=char.xobj_id,
                can_passthrough=True,
                font_size=char.pdf_style.font_size if char.pdf_style else 10.0,
            ))
        elif comp.pdf_formula:
            # PdfFormula passthrough
            formula = comp.pdf_formula
            units.append(TypesettingUnit(
                formular=formula,
                width=formula.box.x2 - formula.box.x if formula.box else 0,
                height=formula.box.y2 - formula.box.y if formula.box else 0,
                box=formula.box,
                xobj_id=getattr(formula, 'xobj_id', None),
                can_passthrough=True,
            ))
        elif comp.pdf_same_style_unicode_characters:
            # unicode 渲染
            chars = comp.pdf_same_style_unicode_characters
            for char in chars.pdf_character:
                units.append(TypesettingUnit(
                    char=char,
                    width=char.box.x2 - char.box.x if char.box else 0,
                    height=char.box.y2 - char.box.y if char.box else 0,
                    box=char.box,
                    xobj_id=char.xobj_id,
                    can_passthrough=True,
                    font_size=char.pdf_style.font_size if char.pdf_style else 10.0,
                ))

    return units
