"""Knuth-Plass 简化版断行优化算法。

前向 DP 实现，用于在给定每行可用宽度的情况下，找到总 raggedness 最小的断行方案。
与 typesetting.py 的 _layout_typesetting_units 配合使用：DP 决定断行位置，实际布局由现有函数完成。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from babeldoc.format.pdf.document_il.midend.typesetting import TypesettingUnit

logger = logging.getLogger(__name__)

# 代价常量
DEFAULT_WIDOW_PENALTY = 500.0  # 孤行惩罚（最后一行 ≤3 个字）
DEFAULT_OVERFLOW_PENALTY = 10000.0  # 超宽惩罚（不应该发生，但作为安全兜底）


def optimal_line_break(
    units: list[TypesettingUnit],
    line_widths: list[float],
    scale: float,
    space_width: float,
    decorative_tracking: float = 0.0,
    widow_penalty: float = DEFAULT_WIDOW_PENALTY,
) -> list[int] | None:
    """前向 DP 断行优化。

    在给定每行可用宽度的情况下，找到总 raggedness 最小的断行方案。
    Raggedness = Σ (available_width - line_width)²，加孤行惩罚。

    Args:
        units: 排版单元列表
        line_widths: 每行可用宽度列表。行号超出长度时使用最后一行的宽度。
        scale: 缩放因子
        space_width: 空格宽度（用于 CJK-英文边界间距）
        decorative_tracking: 装饰字距（每字符额外间距）
        widow_penalty: 孤行惩罚（最后一行 ≤3 个非空格单元时）

    Returns:
        断行位置列表（unit 索引），例如 [5, 12, 20] 表示在 unit 5, 12, 20 后换行。
        如果无法优化（段落太短或所有内容一行放得下），返回 None。
    """
    if not units or not line_widths:
        return None

    n = len(units)

    # 太短的段落不需要优化
    if n <= 3:
        return None

    # 检查是否所有内容一行放得下
    total_width = _compute_line_width(units, 0, n, scale, space_width, decorative_tracking)
    first_line_width = line_widths[0]
    if total_width <= first_line_width:
        return None  # 一行放得下，不需要断行

    # 前向 DP
    INF = float("inf")
    # cost[i] = 排好 units[0..i) 的最小代价
    cost = [INF] * (n + 1)
    cost[0] = 0.0
    # best_prev[i] = 到达位置 i 的最优来源位置（用于回溯）
    best_prev = [-1] * (n + 1)
    # line_num[i] = 位置 i 所在的行号
    line_num = [0] * (n + 1)

    for i in range(n):
        if cost[i] == INF:
            continue

        current_line = line_num[i]
        available = line_widths[min(current_line, len(line_widths) - 1)]

        # 尝试将 units[i..j) 放在当前行
        line_width = 0.0
        has_content = False

        for j in range(i + 1, n + 1):
            unit = units[j - 1]

            # 跳过行首空格（与贪心逻辑一致：行首空格不计入宽度）
            if not has_content and unit.is_space:
                # 空格仍是可断行点，更新 DP（宽度为 0）
                if unit.can_break_line:
                    raggedness = _line_cost(0.0, available, 0, j == n, widow_penalty)
                    new_cost = cost[i] + raggedness
                    if new_cost < cost[j]:
                        cost[j] = new_cost
                        best_prev[j] = i
                        line_num[j] = current_line + 1
                continue

            # 计算这个 unit 的宽度
            unit_w = unit.width * scale

            # CJK-英文边界间距
            if has_content and j > i + 1:
                prev_unit = units[j - 2]
                if (
                    prev_unit.is_cjk_char ^ unit.is_cjk_char
                    and not prev_unit.mixed_character_blacklist
                    and not unit.mixed_character_blacklist
                    and prev_unit.try_get_unicode() != " "
                    and unit.try_get_unicode() != " "
                    and prev_unit.try_get_unicode()
                    not in ["。", "！", "？", "；", "：", "，"]
                ):
                    line_width += space_width * 0.5

            line_width += unit_w

            # Decorative tracking
            if decorative_tracking and not unit.is_space:
                line_width += decorative_tracking

            has_content = True

            # 超宽检查（hung punctuation 允许超出）
            if not unit.is_hung_punctuation and line_width > available:
                # 超宽了，不能再放更多 unit
                break

            # 行尾标点检查：不能出现在行尾的标点需要为下一个字符预留空间
            if (
                unit.is_cannot_appear_in_line_end_punctuation
                and j < n
                and not units[j].is_space
            ):
                next_w = units[j].width * scale
                if line_width + next_w > available:
                    break

            # 如果这个 unit 可以断行，或者是段落末尾，计算代价并更新 DP
            # 段落末尾（j == n）总是合法的断行点
            if unit.can_break_line or j == n:
                # 计算非空格 unit 数量（用于孤行惩罚判断）
                non_space_count = sum(1 for k in range(i, j) if not units[k].is_space)
                raggedness = _line_cost(
                    line_width, available, non_space_count, j == n, widow_penalty
                )
                new_cost = cost[i] + raggedness
                if new_cost < cost[j]:
                    cost[j] = new_cost
                    best_prev[j] = i
                    line_num[j] = current_line + 1

        # 如果没有任何 unit 能放下（第一个非空格 unit 就超宽）
        # 强制放一个 unit 避免死循环
        if not has_content and i < n:
            for k in range(i + 1, n + 1):
                if not units[k - 1].is_space:
                    w = units[k - 1].width * scale
                    raggedness = _line_cost(w, available, 1, k == n, widow_penalty)
                    new_cost = cost[i] + raggedness
                    if new_cost < cost[k]:
                        cost[k] = new_cost
                        best_prev[k] = i
                        line_num[k] = current_line + 1
                    break

    # 检查是否找到解
    if cost[n] == INF:
        return None

    # 回溯断行位置
    breaks = []
    pos = n
    while pos > 0:
        prev = best_prev[pos]
        if prev == -1:
            # 无法回溯，DP 失败
            return None
        if prev > 0:
            breaks.append(prev)  # 在 prev 处断行（prev 是下一行的起始位置）
        pos = prev
    breaks.reverse()

    # 验证：断行位置必须是可断行的（段落末尾除外）
    for bp in breaks:
        if bp > 0 and bp < n and not units[bp - 1].can_break_line:
            # DP 产生了不可断行的位置（非段落末尾），回退
            return None

    return breaks


def _compute_line_width(
    units: list[TypesettingUnit],
    start: int,
    end: int,
    scale: float,
    space_width: float,
    decorative_tracking: float,
) -> float:
    """计算 units[start..end) 的总宽度（匹配贪心逻辑）。

    包含 CJK-英文边界间距和 decorative tracking。
    """
    width = 0.0
    has_content = False

    for k in range(start, end):
        unit = units[k]

        # 跳过行首空格
        if not has_content and unit.is_space:
            continue

        # CJK-英文边界间距
        if has_content and k > start:
            prev_unit = units[k - 1]
            if (
                prev_unit.is_cjk_char ^ unit.is_cjk_char
                and not prev_unit.mixed_character_blacklist
                and not unit.mixed_character_blacklist
                and prev_unit.try_get_unicode() != " "
                and unit.try_get_unicode() != " "
                and prev_unit.try_get_unicode()
                not in ["。", "！", "？", "；", "：", "，"]
            ):
                width += space_width * 0.5

        width += unit.width * scale

        if decorative_tracking and not unit.is_space:
            width += decorative_tracking

        has_content = True

    return width


def _line_cost(
    line_width: float,
    available_width: float,
    num_units: int,
    is_last_line: bool,
    widow_penalty: float,
) -> float:
    """计算一行的代价。

    Raggedness = (available - line_width)²，加孤行惩罚。
    """
    if line_width > available_width:
        # 超宽（不应该发生，hung punctuation 除外）
        return (line_width - available_width) ** 2 * DEFAULT_OVERFLOW_PENALTY

    raggedness = (available_width - line_width) ** 2

    # 孤行惩罚：最后一行只有 ≤3 个非空格单元
    if is_last_line and num_units <= 3:
        raggedness += widow_penalty

    return raggedness
