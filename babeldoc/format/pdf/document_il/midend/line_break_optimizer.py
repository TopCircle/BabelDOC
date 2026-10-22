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
# Intermediate CJK lines: multiply residual² so DP prefers fuller lines
# (方块感 / English-style rectangular column). Last line stays unweighted.
# 2.5 was too soft vs kinsoku-forced early wraps; 6.0 strongly packs mids.
CJK_INTERIOR_FILL_WEIGHT = 6.0
# Interior line that ends on ，。； and is within this slack of the
# measure counts as full (prefer 一种。 over 将新|技巧).
CJK_PUNCT_FILL_SLACK_PT = 80.0
CJK_PUNCT_FILL_SLACK_RATIO = 0.18
CJK_LINE_END_PUNCT = frozenset("。．？！；：，、")


def optimal_line_break(
    units: list[TypesettingUnit],
    line_widths: list[float],
    scale: float,
    space_width: float,
    decorative_tracking: float = 0.0,
    widow_penalty: float = DEFAULT_WIDOW_PENALTY,
    cjk_mode: bool | None = None,
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
        cjk_mode: CJK 模式。None 时自动检测（>50% 非空格 unit 为 CJK）。

    Returns:
        断行位置列表（unit 索引），例如 [5, 12, 20] 表示在 unit 5, 12, 20 后换行。
        如果无法优化（段落太短或所有内容一行放得下），返回 None。
    """
    if not units or not line_widths:
        return None

    # 自动检测 CJK 模式
    if cjk_mode is None:
        cjk_count = sum(1 for u in units if u.is_cjk_char and not u.is_space)
        non_space_count = sum(1 for u in units if not u.is_space)
        cjk_mode = non_space_count > 0 and cjk_count / non_space_count > 0.5

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
    INF = float("inf")  # noqa: N806
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
        non_space_count = 0

        for j in range(i + 1, n + 1):
            unit = units[j - 1]

            # 跳过行首空格（与贪心逻辑一致：行首空格不计入宽度）
            if not has_content and unit.is_space:
                # 空格仍是可断行点，更新 DP（宽度为 0）
                if unit.can_break_line:
                    raggedness = _line_cost(0.0, available, 0, j == n, widow_penalty, cjk_mode)
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
            if not unit.is_space:
                non_space_count += 1

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
            # hung punctuation 不能作为断行点（与 typesetter 保持一致）
            if (unit.can_break_line and not unit.is_hung_punctuation) or j == n:
                end_ch = unit.try_get_unicode() if cjk_mode else None
                raggedness = _line_cost(
                    line_width,
                    available,
                    non_space_count,
                    j == n,
                    widow_penalty,
                    cjk_mode,
                    ends_with_punct=bool(
                        end_ch and end_ch in CJK_LINE_END_PUNCT
                    ),
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
                    raggedness = _line_cost(w, available, 1, k == n, widow_penalty, cjk_mode)
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
    cjk_mode: bool = False,
    *,
    ends_with_punct: bool = False,
) -> float:
    """计算一行的代价。

    Raggedness = (available - line_width)²，加孤行惩罚。
    CJK 模式：中间行加重未填满；末行剩余不收费（允许短末行）；
    中间行若以 ，。； 收尾且距栏宽在 slack 内，视为已满；
    任何 ≤2 字行严厉加 orphan 惩罚。
    """
    if line_width > available_width:
        # 超宽（不应该发生，hung punctuation 除外）
        return (line_width - available_width) ** 2 * DEFAULT_OVERFLOW_PENALTY

    remaining = available_width - line_width

    if cjk_mode:
        if is_last_line:
            # Short last line is correct CJK body (W4e). Taxing leftover
            # here made DP steal chars from interiors (OA p5 420pt mid
            # lines so the tail could grow).
            raggedness = 0.0
        else:
            # 80pt is the wide-column floor. On a wrap gap it is a hole:
            # a comma 60pt early counts as full, and the next line sticks out.
            # 18% of a 470pt column is still past 80, so that column stays put.
            slack = min(
                CJK_PUNCT_FILL_SLACK_PT,
                max(12.0, available_width * CJK_PUNCT_FILL_SLACK_RATIO),
            )
            if ends_with_punct and remaining <= slack:
                raggedness = 0.0
            else:
                # Prefer fuller intermediate lines (reduces 短长交错 raggedness)
                raggedness = (remaining ** 2) * CJK_INTERIOR_FILL_WEIGHT
        if num_units <= 2:
            # Must beat the interior-fill gain of parking one extra
            # 12pt glyph on the previous line (OA-scale ~1150).
            raggedness += widow_penalty * 4
            if num_units == 1:
                # Extra must beat interior-fill of one 12pt glyph.
                # OA p35 caption: leftover 10.9pt vs 21.9pt → fill delta
                # ~2166, so *4 (=2000) still chose |阴. *8 (=4000) prefers
                # 外阴 (and any 单字末行) without taxing 2-char last lines.
                raggedness += widow_penalty * 8
        return raggedness

    raggedness = remaining ** 2

    # 孤行惩罚：最后一行只有 ≤3 个非空格单元
    if is_last_line and num_units <= 3:
        raggedness += widow_penalty

    return raggedness


def centered_line_breaks(
    units: list[TypesettingUnit],
    line_widths: list[float],
    scale: float,
    decorative_tracking: float = 0.0,
) -> list[int] | None:
    """Breaks that keep a centered column within about one character.

    Each line stays inside its slab. A line that cannot hold the shared
    count stays shorter. The extra characters go to the wider slabs.
    """
    specs = _ink_specs(units, scale, decorative_tracking)
    ink = sum(1 for _width, is_ink, _can in specs if is_ink)
    if ink <= 3 or not line_widths:
        return None
    caps = _slab_caps(specs, line_widths)
    if caps is None:
        return None
    glyphs = []
    for index, ((width, is_ink, can), unit) in enumerate(
        zip(specs, units, strict=True)
    ):
        if is_ink:
            glyphs.append((index, width, can, unit.try_get_unicode() or ""))
    counts = _place_legal(glyphs, caps, line_widths, specs)
    if counts is None:
        return None
    return _breaks_for_counts(specs, counts, line_widths)


def _ink_specs(
    units: list[TypesettingUnit],
    scale: float,
    decorative_tracking: float,
) -> list[tuple[float, bool, bool]]:
    specs = []
    for unit in units:
        width = unit.width * scale
        if decorative_tracking and not unit.is_space:
            width += decorative_tracking
        specs.append((width, not unit.is_space, bool(unit.can_break_line)))
    return specs


def _slab_caps(
    specs: list[tuple[float, bool, bool]],
    line_widths: list[float],
) -> list[int] | None:
    """How many characters each slab holds. One em is the median advance."""
    advances = [width for width, is_ink, _can in specs if is_ink and width > 0]
    if not advances:
        return None
    advances.sort()
    em = advances[len(advances) // 2]
    return [max(int((slab + 1e-6) // em), 1) for slab in line_widths]


def _prefix_len(caps: list[int], ink: int) -> int | None:
    """Shortest run of slabs that can hold `ink` characters."""
    room = 0
    for index, cap in enumerate(caps):
        room += cap
        if room >= ink:
            return index + 1
    return None


def _glyph_span_fits(
    specs: list[tuple[float, bool, bool]],
    glyphs: list[tuple[int, float, bool, str]],
    count: int,
    slab: float,
) -> bool:
    spec_start = glyphs[0][0]
    spec_end = glyphs[count - 1][0]
    total = sum(width for width, _ink, _can in specs[spec_start : spec_end + 1])
    return total <= slab + 0.05


# A short last line is normal. Ending on these is a better tie-break than
# cutting the next word, when the column stays about as even either way.
_SOFT_LINE_END = frozenset("和与或而并及")


def _place_legal(
    glyphs: list[tuple[int, float, bool, str]],
    caps: list[int],
    slabs: list[float],
    specs: list[tuple[float, bool, bool]],
) -> list[int] | None:
    """Share characters, then slide a break off a word.

    A planned line may end on the first character of a dictionary word.
    That break is illegal, so the line moves by one or two characters and
    the rest of the column is shared again. A line of one or two characters
    is kept only when no nearby break avoids it.
    """
    ink = len(glyphs)
    if ink == 0:
        return []
    n_lines = _prefix_len(caps, ink)
    if n_lines is None:
        return None
    counts = _share_counts(caps[:n_lines], ink)
    if not counts:
        return None
    if n_lines == 1:
        if _glyph_span_fits(specs, glyphs, ink, slabs[0]):
            return [ink]
        return None
    return _slide_first(glyphs, caps, slabs, specs, counts[0])


def _share_rank(
    counts: list[int],
    target: int,
    glyphs: list[tuple[int, float, bool, str]],
) -> tuple[int, int, int, int, int, int]:
    """Lower is closer to an even column. A short widow ranks worst.

    The last line may be a character or two shorter without counting as a
    spike. When two shares are equally even, prefer a break after 和/而/并.
    """
    widow = 0 if min(counts) >= 3 else 1
    tail = 0
    body = counts
    if len(counts) >= 2 and counts[-1] <= counts[-2]:
        body = counts[:-1]
        short = counts[-2] - counts[-1]
    else:
        short = 0
        if len(counts) >= 2:
            tail = counts[-1] - counts[-2]
    gaps = [abs(left - right) for left, right in zip(body, body[1:], strict=False)]
    worst = max(gaps) if gaps else 0
    if short > 2:
        worst = max(worst, short - 2)
    plain = 0
    cursor = 0
    for count in counts[:-1]:
        cursor += count
        if glyphs[cursor - 1][3] not in _SOFT_LINE_END:
            plain += 1
    return (widow, worst, tail, sum(gaps), plain, abs(counts[0] - target))


def _slide_first(
    glyphs: list[tuple[int, float, bool, str]],
    caps: list[int],
    slabs: list[float],
    specs: list[tuple[float, bool, bool]],
    target: int,
) -> list[int] | None:
    """Move the first break onto a character that may end a line.

    Among the legal slides, keep the one whose lines stay nearest each
    other. A last line longer than the line above it is the spike a
    centered column shows, so that costs more than being one character
    off the share.
    """
    ink = len(glyphs)
    best: list[int] | None = None
    best_rank: tuple[int, int, int, int, int, int] | None = None
    for delta in (0, -1, 1, -2, 2):
        count = target + delta
        if count < 1 or count >= ink or not glyphs[count - 1][2]:
            continue
        if not _glyph_span_fits(specs, glyphs, count, slabs[0]):
            continue
        rest = _place_legal(glyphs[count:], caps[1:], slabs[1:], specs)
        if rest is None:
            continue
        placed = [count, *rest]
        rank = _share_rank(placed, target, glyphs)
        if best_rank is None or rank < best_rank:
            best = placed
            best_rank = rank
    return best


def _share_counts(caps: list[int], total: int) -> list[int] | None:
    """Spread `total` across the slabs. Neighbors differ by about one."""
    if sum(caps) < total:
        return None
    counts = [min(cap, total // len(caps)) for cap in caps]
    left = total - sum(counts)
    for _step in range(left):
        roomiest = max(
            range(len(caps)),
            key=lambda index: caps[index] - counts[index],
        )
        if caps[roomiest] <= counts[roomiest]:
            return None
        counts[roomiest] += 1
    return counts


def _breaks_for_counts(
    specs: list[tuple[float, bool, bool]],
    counts: list[int],
    line_widths: list[float],
) -> list[int] | None:
    """Start index of each line after the first. None when a line leaves its slab."""
    breaks: list[int] = []
    line = 0
    left = counts[0]
    start = 0
    for index, (_width, is_ink, can_break) in enumerate(specs):
        if not is_ink:
            continue
        left -= 1
        if left > 0:
            continue
        if not _span_fits(specs, start, index, line_widths[line]):
            return None
        if line >= len(counts) - 1:
            return breaks
        if not can_break:
            return None
        breaks.append(index + 1)
        line += 1
        left = counts[line]
        start = index + 1
    return None


def _span_fits(
    specs: list[tuple[float, bool, bool]],
    start: int,
    end: int,
    slab: float,
) -> bool:
    total = sum(width for width, _ink, _can in specs[start : end + 1])
    return total <= slab + 0.05
