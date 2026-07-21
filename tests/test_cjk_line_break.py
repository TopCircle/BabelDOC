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
        # ATU p22–23 mid-word goldens
        assert is_cjk_two_char_word("乳房")
        assert is_cjk_two_char_word("背带")
        assert is_cjk_two_char_word("积聚")
        assert is_cjk_two_char_word("绳索")
        assert is_cjk_two_char_word("捆绑")

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


class TestUniformCjkReferenceWidths:
    """CJK dual: rectangular column, not EN last-line short mid-paragraph."""

    def test_collapses_short_en_tail(self):
        from babeldoc.format.pdf.document_il.midend.typesetting import Typesetting

        # EN body: two full + short last → ZH must not use 200 as mid line
        out = Typesetting._uniform_cjk_reference_widths([500.0, 500.0, 200.0])
        assert out == [500.0]

    def test_keeps_narrow_figure_column(self):
        from babeldoc.format.pdf.document_il.midend.typesetting import Typesetting

        # All lines short relative to page but equal → keep column
        out = Typesetting._uniform_cjk_reference_widths([180.0, 180.0, 175.0, 100.0])
        assert out == [180.0]

    def test_empty_passthrough(self):
        from babeldoc.format.pdf.document_il.midend.typesetting import Typesetting

        assert Typesetting._uniform_cjk_reference_widths(None) is None
        assert Typesetting._uniform_cjk_reference_widths([]) == []


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
        assert is_cjk_line_start_forbidden("％")  # fullwidth percent OK
        assert not is_cjk_line_start_forbidden("中")
        # Half-width must NOT glue CJK+Latin mixed runs (约 50% / 见 3.2)
        assert not is_cjk_line_start_forbidden(".")
        assert not is_cjk_line_start_forbidden("%")
        assert not is_cjk_line_start_forbidden("/")
        assert not is_cjk_line_start_forbidden(",")
        # Layout-first: particles are NOT hard kinsoku (would force short lines)
        assert not is_cjk_line_start_forbidden("的")
        assert not is_cjk_line_start_forbidden("了")

    def test_line_end_forbidden_chars(self):
        assert is_cjk_line_end_forbidden("（")
        assert is_cjk_line_end_forbidden("【")
        assert is_cjk_line_end_forbidden("“")
        assert is_cjk_line_end_forbidden("(")  # mixed-script open paren
        assert not is_cjk_line_end_forbidden("。")
        # Conjunctions not hard-glued (layout fill wins over 词语搭配)
        assert not is_cjk_line_end_forbidden("和")
        assert not is_cjk_line_end_forbidden("的")

    def test_halfwidth_period_does_not_block_break_after_cjk(self):
        """「见3.」式混排：半角点不应禁止在「3」前断（点不在行首禁则里）。"""

        class _U(MockUnit):
            def __init__(self, **kw):
                super().__init__(**kw)
                self.can_break_line_cache = None

        units = [
            _U(unicode="见", is_cjk_char=True),
            _U(unicode="3", is_cjk_char=False),
            _U(unicode=".", is_cjk_char=False),
            _U(unicode="2", is_cjk_char=False),
        ]
        merge_cjk_units(units)
        # 半角 '.' 不得把「3」标成不可断
        assert units[1].can_break_line_cache is not False


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
        # 「保持」：不可在首字「保」之后断（can_break = break AFTER unit）
        assert units[0].can_break_line_cache is False
        # 开括号行尾禁则
        assert units[2].can_break_line_cache is False
        # 句号行首禁则 → 前一字符「）」不可断
        assert units[5].can_break_line_cache is False

    def test_atu_p22_word_dict_secondary_to_fill(self):
        """Dict still protects 背|带 / 乳|房; layout measure is separate path."""

        class _U(MockUnit):
            def __init__(self, **kw):
                super().__init__(**kw)
                self.can_break_line_cache = None

            @property
            def can_break_line(self):
                if self.can_break_line_cache is not None:
                    return self.can_break_line_cache
                return self._can_break_line

        # Secondary: two-char dict still glues known words
        units = [_U(unicode=ch) for ch in "这些背带设计"]
        merge_cjk_units(units)
        assert units[2].can_break_line_cache is False  # 背|

        units = [_U(unicode=ch) for ch in "指的是乳房在"]
        merge_cjk_units(units)
        assert units[3].can_break_line_cache is False  # 乳|

        # Particles/conjunctions are NOT hard-glued (layout-first)
        units = [_U(unicode=ch) for ch in "圈在她的背部"]
        merge_cjk_units(units)
        de_idx = next(i for i, u in enumerate(units) if u.try_get_unicode() == "的")
        assert units[de_idx - 1].can_break_line_cache is not False

        units = [_U(unicode=ch) for ch in "肩膀和前方"]
        merge_cjk_units(units)
        he_idx = next(i for i, u in enumerate(units) if u.try_get_unicode() == "和")
        assert units[he_idx].can_break_line_cache is not False

        # With uniform full measure, interior residuals stay small (layout-first)
        text = "这些背带设计用于挤压乳房与血液积聚在乳房中使其变得异常敏感"
        units = [_U(unicode=ch, width=12.0) for ch in text]
        merge_cjk_units(units)
        line_w = 120.0
        breaks = optimal_line_break(
            units, [line_w] * 6, scale=1.0, space_width=5.0, cjk_mode=True
        )
        assert breaks is not None
        from babeldoc.format.pdf.document_il.midend.line_break_optimizer import (
            _compute_line_width,
        )

        pts = [0] + breaks + [len(units)]
        interior_rems = []
        for i in range(len(pts) - 2):  # exclude last line
            a, b = pts[i], pts[i + 1]
            w = _compute_line_width(units, a, b, 1.0, 5.0, 0.0)
            interior_rems.append(line_w - w)
        # Interiors should be near-full (≤ ~1.5 chars leftover under fill weight)
        assert max(interior_rems) <= 24.0, interior_rems

    def test_merge_glues_ganqing_and_volume_year(self):
        """感情 / 第11卷 / 1989年 must not break mid-token."""

        class _U(MockUnit):
            def __init__(self, **kw):
                super().__init__(**kw)
                self.can_break_line_cache = None

        # 感情用事
        units = [_U(unicode=ch) for ch in "感情用事"]
        merge_cjk_units(units)
        assert units[0].can_break_line_cache is False  # 感|情
        assert units[2].can_break_line_cache is False  # 用|事

        # 第11卷（1989年）
        text = "第11卷（1989年）"
        units = []
        for ch in text:
            is_cjk = not ch.isdigit()
            units.append(_U(unicode=ch, is_cjk_char=is_cjk))
        merge_cjk_units(units)
        # 第 + digits + 卷
        assert units[0].can_break_line_cache is False  # 第|
        assert units[1].can_break_line_cache is False  # 1|
        assert units[2].can_break_line_cache is False  # 1|卷
        # open paren
        assert units[4].can_break_line_cache is False  # （|
        # 1989年
        assert units[5].can_break_line_cache is False  # 1|
        assert units[6].can_break_line_cache is False
        assert units[7].can_break_line_cache is False
        assert units[8].can_break_line_cache is False  # 9|年

    def test_dp_never_breaks_ganqing_or_open_paren(self):
        """DP break points must respect can_break after merge."""

        class _U(MockUnit):
            def __init__(self, **kw):
                super().__init__(**kw)
                self.can_break_line_cache = None

            @property
            def can_break_line(self):
                if self.can_break_line_cache is not None:
                    return self.can_break_line_cache
                return self._can_break_line

        text = "偶尔会有感情用事，偶尔会有不准确的地方"
        units = [_U(unicode=ch, width=10.0) for ch in text]
        merge_cjk_units(units)
        # Force a width that would greedily hit 感|情 without protection
        # 偶尔会有感 = 5 chars = 50; line width 55 → would want break after 感
        breaks = optimal_line_break(
            units, [55.0, 55.0, 55.0], scale=1.0, space_width=5.0, cjk_mode=True
        )
        assert breaks is not None
        for bp in breaks:
            prev = units[bp - 1]
            assert prev.can_break_line, (
                f"illegal break after {prev.try_get_unicode()!r} at {bp}"
            )
            # never 感|情
            if prev.try_get_unicode() == "感":
                raise AssertionError("broke 感|情")

        # Footer-like citation
        text2 = "新德里），第11卷（1989年），263-282页"
        units2 = []
        for ch in text2:
            is_cjk = not (ch.isdigit() or ch in "-")
            units2.append(
                _U(
                    unicode=ch,
                    width=10.0 if is_cjk else 6.0,
                    is_cjk_char=is_cjk and ch not in "），，",
                )
            )
        # Fix punctuation is_cjk
        for u in units2:
            if u.try_get_unicode() in "），，（":
                u._is_cjk_char = True
        merge_cjk_units(units2)
        breaks2 = optimal_line_break(
            units2, [80.0, 80.0, 80.0], scale=1.0, space_width=5.0, cjk_mode=True
        )
        if breaks2:
            for bp in breaks2:
                prev_ch = units2[bp - 1].try_get_unicode()
                assert units2[bp - 1].can_break_line, f"illegal after {prev_ch!r}"
                assert prev_ch not in "（(", f"open paren at EOL before index {bp}"
                assert not (prev_ch == "德" and units2[bp].try_get_unicode() == "里")
