"""CJK 断行优化单元测试。"""

from __future__ import annotations

from babeldoc.format.pdf.document_il.midend.line_break_optimizer import (
    CJK_INTERIOR_FILL_WEIGHT,
)
from babeldoc.format.pdf.document_il.midend.line_break_optimizer import _line_cost
from babeldoc.format.pdf.document_il.midend.line_break_optimizer import (
    optimal_line_break,
)
from babeldoc.format.pdf.document_il.midend.typesetting import merge_cjk_units
from babeldoc.format.pdf.document_il.utils.cjk_dict import is_cjk_two_char_word
from babeldoc.format.pdf.document_il.utils.cjk_dict import is_cjk_word_boundary
from babeldoc.format.pdf.document_il.utils.cjk_kinsoku import is_cjk_line_end_forbidden
from babeldoc.format.pdf.document_il.utils.cjk_kinsoku import (
    is_cjk_line_start_forbidden,
)

# ──────────────────────────────────────────────────────────────
# Mock TypesettingUnit
# ──────────────────────────────────────────────────────────────


class MockUnit:
    """用于测试的简化 TypesettingUnit mock。"""

    def __init__(
        self,
        width: float = 10.0,
        unicode: str = "字",
        can_break_line: bool = True,
        is_cjk_char: bool = True,
        is_space: bool = False,
    ):
        self._width = width
        self._unicode = unicode
        self._can_break_line = can_break_line
        self._is_cjk_char = is_cjk_char
        self._is_space = is_space

    @property
    def width(self):
        return self._width

    @property
    def height(self):
        return 10.0

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
        return False

    @property
    def is_cannot_appear_in_line_end_punctuation(self):
        return False

    @property
    def mixed_character_blacklist(self):
        return False

    def try_get_unicode(self):
        return self._unicode


def _cjk_units(text: str, char_width: float = 10.0) -> list[MockUnit]:
    """创建 CJK 字符 unit 列表。"""
    return [MockUnit(width=char_width, unicode=ch) for ch in text]


# ──────────────────────────────────────────────────────────────
# 词典测试
# ──────────────────────────────────────────────────────────────


class TestCJKDict:
    def test_common_two_char_words(self):
        """常见二字词应被识别。"""
        assert is_cjk_two_char_word("保持")
        assert is_cjk_two_char_word("收缩")
        assert is_cjk_two_char_word("状态")
        assert is_cjk_two_char_word("持续")
        assert is_cjk_two_char_word("时间")
        assert is_cjk_two_char_word("学习")
        assert is_cjk_two_char_word("中国")
        assert is_cjk_two_char_word("发展")

    def test_non_words(self):
        """非常见词组不应被识别。"""
        assert not is_cjk_two_char_word("保收")  # 不是词
        assert not is_cjk_two_char_word("缩状")  # 不是词

    def test_word_boundary(self):
        """词组边界检测。"""
        text = "保持收缩状态"
        # "保持" 是词，"持" 和 "收" 之间是边界
        assert is_cjk_word_boundary(text, 2)  # "持" 和 "收" 之间
        # "收缩" 是词，"收" 和 "缩" 之间不是边界
        assert not is_cjk_word_boundary(text, 3)  # "收" 和 "缩" 之间
        # "状态" 是词，"状" 和 "态" 之间不是边界
        assert not is_cjk_word_boundary(text, 5)  # "状" 和 "态" 之间


# ──────────────────────────────────────────────────────────────
# DP CJK 模式测试
# ──────────────────────────────────────────────────────────────


class TestCJKDP:
    def test_cjk_mode_auto_detect(self):
        """DP 应自动检测 CJK 模式。"""
        # 8 个字符，每个宽 20，总宽 160，行宽 100 → 需要断行
        units = _cjk_units("一二三四五六七八", char_width=20.0)
        line_widths = [100.0, 100.0]
        result = optimal_line_break(units, line_widths, scale=1.0, space_width=5.0)
        # 应该产生断行结果
        assert result is not None

    def test_cjk_prefers_full_lines(self):
        """CJK 模式应优先填满每一行。"""
        # 8 个字符，每个宽 20，行宽 100
        # 理想断行：5+3（第一行满）或 4+4
        # 不理想：3+3+2（两行都不满）
        units = _cjk_units("一二三四五六七八", char_width=20.0)
        line_widths = [100.0, 100.0]
        result = optimal_line_break(units, line_widths, scale=1.0, space_width=5.0)
        assert result is not None
        # 应该产生一行断点（两行）
        assert len(result) == 1
        # 断点应该是 5（5+3）或 4（4+4）
        assert result[0] in [4, 5]

    def test_cjk_avoids_widow_line(self):
        """CJK 模式应避免孤行（最后一行 ≤2 个字）。"""
        # 7 个字符，每个宽 10，行宽 55
        # 贪心会 5+2，DP 应该 4+3 或 3+4
        units = _cjk_units("一二三四五六七", char_width=10.0)
        line_widths = [55.0, 55.0]
        result = optimal_line_break(units, line_widths, scale=1.0, space_width=5.0)
        assert result is not None
        last_line_start = result[-1] if result else 0
        last_line_count = len(units) - last_line_start
        assert last_line_count > 2, f"最后一行只有 {last_line_count} 个字（孤行）"

    def test_cjk_mixed_latin(self):
        """CJK 和拉丁字符混排时应正确处理。"""
        units = [
            MockUnit(width=10.0, unicode="你", is_cjk_char=True),
            MockUnit(width=10.0, unicode="好", is_cjk_char=True),
            MockUnit(width=8.0, unicode="A", is_cjk_char=False),
            MockUnit(width=8.0, unicode="B", is_cjk_char=False),
            MockUnit(width=10.0, unicode="世", is_cjk_char=True),
            MockUnit(width=10.0, unicode="界", is_cjk_char=True),
        ]
        line_widths = [40.0, 40.0]
        result = optimal_line_break(units, line_widths, scale=1.0, space_width=5.0)
        # 应该能产生断行结果
        assert result is not None

    def test_single_line_no_break(self):
        """一行能放下时不应断行。"""
        units = _cjk_units("一二三", char_width=10.0)
        line_widths = [100.0]
        result = optimal_line_break(units, line_widths, scale=1.0, space_width=5.0)
        assert result is None  # 不需要断行


# ──────────────────────────────────────────────────────────────
# CJK cost 函数测试
# ──────────────────────────────────────────────────────────────


class TestCJKCost:
    def test_cjk_interior_line_penalty(self):
        """CJK 内部行应强烈惩罚非满行。"""
        full_cost = _line_cost(100, 100, 10, False, 500, cjk_mode=True)
        half_cost = _line_cost(50, 100, 5, False, 500, cjk_mode=True)
        assert full_cost < half_cost
        # 半行：(50)² * FILL_WEIGHT
        assert half_cost == (50**2) * CJK_INTERIOR_FILL_WEIGHT
        assert half_cost > 1000

    def test_cjk_interior_heavier_than_last_line_same_gap(self):
        """中间行未填满应比最后一行同 residual 更重。"""
        interior = _line_cost(50, 100, 5, False, 500, cjk_mode=True)
        last = _line_cost(50, 100, 5, True, 500, cjk_mode=True)
        assert interior > last
        assert interior == last * CJK_INTERIOR_FILL_WEIGHT

    def test_cjk_last_line_widow(self):
        """CJK 最后一行孤行应被严厉惩罚。"""
        widow_cost = _line_cost(20, 100, 2, True, 500, cjk_mode=True)
        normal_cost = _line_cost(30, 100, 3, True, 500, cjk_mode=True)
        assert widow_cost > normal_cost
        assert widow_cost >= 500

    def test_cjk_last_line_normal(self):
        """CJK 最后一行正常长度应有二次惩罚（与原始版本一致）。"""
        cost = _line_cost(30, 100, 3, True, 500, cjk_mode=True)
        assert cost == (100 - 30) ** 2

    def test_english_mode_unchanged(self):
        """英文模式不应受影响。"""
        cost = _line_cost(80, 100, 5, False, 500, cjk_mode=False)
        assert cost == (100 - 80) ** 2  # = 400


class TestKinsoku:
    def test_line_start_forbidden_chars(self):
        assert is_cjk_line_start_forbidden("。")
        assert is_cjk_line_start_forbidden("，")
        assert is_cjk_line_start_forbidden("）")
        assert not is_cjk_line_start_forbidden("中")

    def test_line_end_forbidden_chars(self):
        assert is_cjk_line_end_forbidden("（")
        assert is_cjk_line_end_forbidden("【")
        assert is_cjk_line_end_forbidden("“")
        assert not is_cjk_line_end_forbidden("。")

    def test_merge_cjk_marks_kinsoku_and_words(self):
        """开括号不可断；词组内部不可断；句号前不可断。"""

        class _U(MockUnit):
            def __init__(self, **kw):
                super().__init__(**kw)
                self.can_break_line_cache = None

        units = [
            _U(unicode="保"),
            _U(unicode="持"),
            _U(unicode="（"),
            _U(unicode="测"),
            _U(unicode="试"),
            _U(unicode="）"),
            _U(unicode="。"),
        ]
        merge_cjk_units(units)
        # 「持」在「保持」内部 → 不可断
        assert units[1].can_break_line_cache is False
        # 开括号行尾禁则
        assert units[2].can_break_line_cache is False
        # 句号行首禁则 → 前一字符「）」不可断
        assert units[5].can_break_line_cache is False
