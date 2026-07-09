"""line_break_optimizer 单元测试。"""

from __future__ import annotations

import pytest

from babeldoc.format.pdf.document_il.midend.line_break_optimizer import (
    _compute_line_width,
    _line_cost,
    optimal_line_break,
)


# ──────────────────────────────────────────────────────────────
# Mock TypesettingUnit
# ──────────────────────────────────────────────────────────────


class MockUnit:
    """用于测试的简化 TypesettingUnit mock。"""

    def __init__(
        self,
        width: float,
        height: float = 10.0,
        unicode: str = "字",
        can_break_line: bool = True,
        is_space: bool = False,
        is_cjk_char: bool = True,
        is_hung_punctuation: bool = False,
        is_cannot_appear_in_line_end_punctuation: bool = False,
        mixed_character_blacklist: bool = False,
    ):
        self._width = width
        self._height = height
        self._unicode = unicode
        self._can_break_line = can_break_line
        self._is_space = is_space
        self._is_cjk_char = is_cjk_char
        self._is_hung_punctuation = is_hung_punctuation
        self._is_cannot_appear_in_line_end_punctuation = (
            is_cannot_appear_in_line_end_punctuation
        )
        self._mixed_character_blacklist = mixed_character_blacklist

    @property
    def width(self):
        return self._width

    @property
    def height(self):
        return self._height

    @property
    def can_break_line(self):
        return self._can_break_line

    @property
    def is_space(self):
        return self._is_space

    @property
    def is_cjk_char(self):
        return self._is_cjk_char

    @property
    def is_hung_punctuation(self):
        return self._is_hung_punctuation

    @property
    def is_cannot_appear_in_line_end_punctuation(self):
        return self._is_cannot_appear_in_line_end_punctuation

    @property
    def mixed_character_blacklist(self):
        return self._mixed_character_blacklist

    def try_get_unicode(self):
        return self._unicode


def _cjk_units(text: str, char_width: float = 10.0) -> list[MockUnit]:
    """从中文文本创建 MockUnit 列表。每个 CJK 字符可断行。"""
    return [
        MockUnit(width=char_width, unicode=ch, can_break_line=True, is_cjk_char=True)
        for ch in text
    ]


def _eng_units(words: list[str], char_width: float = 8.0) -> list[MockUnit]:
    """从英文单词列表创建 MockUnit 列表。只能在 word 边界断行。"""
    units = []
    for word in words:
        for ch in word:
            units.append(
                MockUnit(
                    width=char_width,
                    unicode=ch,
                    can_break_line=False,
                    is_cjk_char=False,
                )
            )
        # 空格作为断行点
        units.append(
            MockUnit(
                width=char_width * 0.5,
                unicode=" ",
                can_break_line=True,
                is_cjk_char=False,
                is_space=True,
            )
        )
    return units


# ──────────────────────────────────────────────────────────────
# Tests: optimal_line_break
# ──────────────────────────────────────────────────────────────


class TestOptimalLineBreak:
    """optimal_line_break 主函数测试。"""

    def test_returns_none_for_empty_units(self):
        """空单元列表返回 None。"""
        result = optimal_line_break([], [100.0], scale=1.0, space_width=5.0)
        assert result is None

    def test_returns_none_for_short_paragraph(self):
        """≤3 个单元不需要优化。"""
        units = _cjk_units("你好")
        result = optimal_line_break(units, [100.0], scale=1.0, space_width=5.0)
        assert result is None

    def test_returns_none_when_fits_in_one_line(self):
        """所有内容一行放得下时返回 None。"""
        units = _cjk_units("你好世界", char_width=10.0)
        # 总宽度 = 4 * 10 = 40，可用宽度 100
        result = optimal_line_break(units, [100.0], scale=1.0, space_width=5.0)
        assert result is None

    def test_cjk_even_distribution(self):
        """中文文本均匀分布到多行。"""
        # 10 个字符，每个宽 10，总宽 100
        # 可用宽度 55 → 每行 5 个字符
        units = _cjk_units("一二三四五六七八九十", char_width=10.0)
        line_widths = [55.0, 55.0]
        result = optimal_line_break(units, line_widths, scale=1.0, space_width=5.0)
        assert result is not None
        # 应该在第 5 个字符后断行
        assert 5 in result

    def test_no_widow_line(self):
        """最后一行不应只有 1-2 个字。"""
        # 7 个字符，每个宽 10，总宽 70
        # 可用宽度 55 → 贪心会 5+2，DP 应该 4+3 或 3+4
        units = _cjk_units("一二三四五六七", char_width=10.0)
        line_widths = [55.0, 55.0]
        result = optimal_line_break(
            units, line_widths, scale=1.0, space_width=5.0, widow_penalty=500
        )
        assert result is not None
        # 断行后最后一行不应只有 ≤2 个字
        last_line_start = result[-1] if result else 0
        last_line_count = len(units) - last_line_start
        assert last_line_count > 2, f"最后一行只有 {last_line_count} 个字（孤行）"

    def test_english_word_boundary_break(self):
        """英文只在 word 边界断行。"""
        # "hello world foo" → 只能在空格处断行
        units = _eng_units(["hello", "world", "foo"], char_width=8.0)
        # hello = 5*8 + 1*4 = 44, world = 5*8 + 1*4 = 44, foo = 3*8 + 1*4 = 28
        line_widths = [60.0, 60.0]
        result = optimal_line_break(units, line_widths, scale=1.0, space_width=4.0)
        assert result is not None
        # 所有断行点必须在 can_break_line=True 的位置（空格）
        for bp in result:
            assert units[bp - 1].can_break_line or units[bp - 1].is_space, (
                f"断行点 {bp} 处的 unit 不可断行"
            )

    def test_dynamic_line_widths(self):
        """不同行有不同可用宽度时，DP 能自适应。"""
        # 10 个字符，每个宽 10
        # 第一行宽 35（放 3 个），第二行宽 55（放 5 个），第三行宽 35（放 2 个）
        units = _cjk_units("一二三四五六七八九十", char_width=10.0)
        line_widths = [35.0, 55.0, 35.0]
        result = optimal_line_break(units, line_widths, scale=1.0, space_width=5.0)
        assert result is not None
        # 验证每行不超宽
        breaks = [0] + result + [len(units)]
        for line_idx in range(len(breaks) - 1):
            start, end = breaks[line_idx], breaks[line_idx + 1]
            line_w = sum(u.width for u in units[start:end])
            available = line_widths[min(line_idx, len(line_widths) - 1)]
            assert line_w <= available + 1.0, (
                f"行 {line_idx} 超宽: {line_w} > {available}"
            )

    def test_hung_punctuation_allows_overflow(self):
        """Hung punctuation 可以超出右边界。"""
        units = _cjk_units("你好世", char_width=10.0)
        # 最后一个是 hung punctuation
        units[-1] = MockUnit(
            width=10.0,
            unicode="，",
            can_break_line=True,
            is_cjk_char=True,
            is_hung_punctuation=True,
        )
        # 可用宽度 25 → 前两个放得下（20），hung punctuation 可以超出
        line_widths = [25.0, 25.0]
        result = optimal_line_break(units, line_widths, scale=1.0, space_width=5.0)
        # 应该能一行放得下（hung punctuation 不触发断行）
        assert result is None  # 一行放得下

    def test_cannot_appear_in_line_end(self):
        """行尾禁用标点需要为下一个字符预留空间。"""
        units = _cjk_units("你好世界", char_width=10.0)
        # "世" 是行尾禁用标点（如左引号）
        units[2] = MockUnit(
            width=10.0,
            unicode="「",
            can_break_line=True,
            is_cjk_char=True,
            is_cannot_appear_in_line_end_punctuation=True,
        )
        # 可用宽度 35 → 如果 "「" 在行尾，需要为 "界" 预留空间
        # 所以前 2 个放一行，后 2 个放一行
        line_widths = [35.0, 35.0]
        result = optimal_line_break(units, line_widths, scale=1.0, space_width=5.0)
        assert result is not None
        # "「"（index 2）不应是断行点
        assert 3 not in result, "「 不应在行尾断行"

    def test_mixed_cjk_english(self):
        """中英文混合文本的断行。"""
        units = []
        # "你好"
        for ch in "你好":
            units.append(MockUnit(width=10.0, unicode=ch, is_cjk_char=True))
        # "hello"
        for ch in "hello":
            units.append(MockUnit(width=8.0, unicode=ch, is_cjk_char=False, can_break_line=False))
        # 空格断行点
        units.append(MockUnit(width=4.0, unicode=" ", is_space=True, is_cjk_char=False, can_break_line=True))
        # "world"
        for ch in "world":
            units.append(MockUnit(width=8.0, unicode=ch, is_cjk_char=False, can_break_line=False))

        # 总宽 ≈ 2*10 + 5*8 + 4 + 5*8 = 104（加边界间距约 109）
        # 可用宽度 60 → 需要至少 2 行
        line_widths = [60.0, 60.0]
        result = optimal_line_break(units, line_widths, scale=1.0, space_width=5.0)
        assert result is not None, "DP 应找到至少一个断行点"
        # 断行位置必须是可断行的
        for bp in result:
            assert units[bp - 1].can_break_line, f"断行点 {bp} 处不可断行"


# ──────────────────────────────────────────────────────────────
# Tests: _line_cost
# ──────────────────────────────────────────────────────────────


class TestLineCost:
    """_line_cost 代价函数测试。"""

    def test_raggedness_calculation(self):
        """raggedness = (available - line_width)²。"""
        cost = _line_cost(80.0, 100.0, 5, False, 500)
        assert cost == (100 - 80) ** 2  # 400

    def test_overflow_penalty(self):
        """超宽时使用 overflow 惩罚。"""
        cost = _line_cost(110.0, 100.0, 5, False, 500)
        assert cost > 1000  # 大额惩罚

    def test_widow_penalty(self):
        """最后一行 ≤3 个字时加孤行惩罚。"""
        cost_no_widow = _line_cost(80.0, 100.0, 5, True, 500)
        cost_widow = _line_cost(80.0, 100.0, 2, True, 500)
        assert cost_widow > cost_no_widow
        assert cost_widow - cost_no_widow == 500

    def test_no_widow_penalty_for_non_last_line(self):
        """非最后一行不加孤行惩罚。"""
        cost = _line_cost(80.0, 100.0, 2, False, 500)
        assert cost == (100 - 80) ** 2  # 无孤行惩罚


# ──────────────────────────────────────────────────────────────
# Tests: _compute_line_width
# ──────────────────────────────────────────────────────────────


class TestComputeLineWidth:
    """_compute_line_width 宽度计算测试。"""

    def test_basic_width(self):
        """基本宽度计算。"""
        units = _cjk_units("你好", char_width=10.0)
        w = _compute_line_width(units, 0, 2, scale=1.0, space_width=5.0, decorative_tracking=0.0)
        assert w == 20.0

    def test_cjk_english_boundary_spacing(self):
        """CJK-英文边界间距。"""
        units = [
            MockUnit(width=10.0, unicode="你", is_cjk_char=True),
            MockUnit(width=8.0, unicode="a", is_cjk_char=False),
        ]
        w = _compute_line_width(units, 0, 2, scale=1.0, space_width=5.0, decorative_tracking=0.0)
        # 10 + 8 + 5*0.5 (边界间距) = 20.5
        assert w == 20.5

    def test_decorative_tracking(self):
        """装饰字距。"""
        units = _cjk_units("你好", char_width=10.0)
        w = _compute_line_width(units, 0, 2, scale=1.0, space_width=5.0, decorative_tracking=2.0)
        # 10 + 2 + 10 + 2 = 24
        assert w == 24.0

    def test_scale_applied(self):
        """缩放因子。"""
        units = _cjk_units("你好", char_width=10.0)
        w = _compute_line_width(units, 0, 2, scale=0.8, space_width=5.0, decorative_tracking=0.0)
        # 10*0.8 + 10*0.8 = 16
        assert w == 16.0
