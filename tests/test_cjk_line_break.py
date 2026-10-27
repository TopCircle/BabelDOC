"""CJK 断行优化单元测试。"""

from __future__ import annotations

from babeldoc.format.pdf.document_il.midend.line_break_optimizer import (
    CJK_INTERIOR_FILL_WEIGHT,
)
from babeldoc.format.pdf.document_il.midend.line_break_optimizer import _line_cost
from babeldoc.format.pdf.document_il.midend.line_break_optimizer import (
    break_leaves_a_hole,
)
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
        assert is_cjk_two_char_word("空调")
        assert is_cjk_two_char_word("风扇")
        assert is_cjk_two_char_word("按摩")

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

    def test_oa_p35_caption_avoids_single_cjk_last_char(self):
        """OA p35 figure_caption: do not wrap the last CJK onto its own line."""
        chars = list("图片1-雌性外阴")
        units = []
        for ch in chars:
            is_cjk = "\u4e00" <= ch <= "\u9fff"
            units.append(
                MockUnit(
                    width=10.0 if is_cjk else 6.0,
                    unicode=ch,
                    is_cjk_char=is_cjk,
                    can_break_line=True,
                )
            )
        # Total ~ 6*10 + 3*6 = 78. Line 70 fits all but last 阴.
        result = optimal_line_break(units, [70.0, 70.0], scale=1.0, space_width=5.0)
        assert result is not None
        last_start = result[-1]
        last_text = "".join(u.try_get_unicode() for u in units[last_start:])
        assert len(units) - last_start >= 2, f"last line {last_text!r}"
        assert last_text != "阴"

    def test_oa_p35_caption_87pt_measure(self):
        """Match xuRUB: 11pt CJK, 87.9pt measure, greedy leaves 阴."""
        chars = list("图片 1 - 雌性外阴")
        units = []
        for ch in chars:
            is_cjk = "\u4e00" <= ch <= "\u9fff"
            if ch == " ":
                units.append(MockUnit(width=3.9, unicode=ch, is_cjk_char=False, is_space=True, can_break_line=True))
            elif is_cjk:
                units.append(MockUnit(width=11.0, unicode=ch, is_cjk_char=True, can_break_line=True))
            else:
                units.append(MockUnit(width=6.5 if ch == "1" else 3.9, unicode=ch, is_cjk_char=False, can_break_line=True))
        result = optimal_line_break(units, [87.9, 87.9], scale=1.0, space_width=3.0)
        assert result is not None
        last_text = "".join(u.try_get_unicode() for u in units[result[-1]:])
        assert last_text != "阴", last_text
        assert "阴" in last_text

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
        """中间行未填满应比最后一行同 residual 更重（末行剩余不再计费）。"""
        interior = _line_cost(50, 100, 5, False, 500, cjk_mode=True)
        last = _line_cost(50, 100, 5, True, 500, cjk_mode=True)
        assert last == 0.0
        assert interior > last
        assert interior == (50**2) * CJK_INTERIOR_FILL_WEIGHT

    def test_cjk_last_line_widow(self):
        """CJK 最后一行孤行应被严厉惩罚。"""
        widow_cost = _line_cost(20, 100, 2, True, 500, cjk_mode=True)
        normal_cost = _line_cost(30, 100, 3, True, 500, cjk_mode=True)
        assert widow_cost > normal_cost
        assert widow_cost >= 500

    def test_cjk_one_char_last_line_costs_more_than_two(self):
        """OA p35 caption: 1-char last line must lose to 2-char last line."""
        one = _line_cost(12, 80, 1, True, 500, cjk_mode=True)
        two = _line_cost(24, 80, 2, True, 500, cjk_mode=True)
        interior_gain = _line_cost(68, 80, 6, False, 500, cjk_mode=True) - _line_cost(
            80, 80, 7, False, 500, cjk_mode=True
        )
        assert one > two
        assert one - two >= 4000
        assert one - two > interior_gain

    def test_cjk_last_line_does_not_tax_leftover(self):
        """CJK 末行允许短：剩余宽度不再用二次惩罚（否则会抽空中间行）。"""
        short_last = _line_cost(30, 100, 5, True, 500, cjk_mode=True)
        long_last = _line_cost(80, 100, 8, True, 500, cjk_mode=True)
        interior_gap = _line_cost(80, 100, 8, False, 500, cjk_mode=True)
        assert short_last == long_last == 0.0
        # 中间行 20pt 空洞必须比「把这 20pt 挪到末行」更贵
        assert interior_gap > 0

    def test_oa_p5_interior_fills_and_keeps_yizhong_together(self):
        """OA p5「一次只学一种。」：中间行尽量满栏，禁止断在「学/一种」。"""

        class _U(MockUnit):
            def __init__(self, ch: str, width: float = 12.0):
                super().__init__(width=width, unicode=ch, is_cjk_char=True)
                self.can_break_line_cache = None

            @property
            def can_break_line(self):
                if self.can_break_line_cache is not None:
                    return self.can_break_line_cache
                return True

        text = (
            "你可以一次学习几种这里介绍的新技巧，边学边练，但我强烈建议一次只学一种。"
            "将新技巧加入你的常规性爱剧目中，以便在舒适的环境中掌握它们，"
            "然后再将这些技巧全部混合起来新体位"
        )
        units = [_U(ch) for ch in text]
        merge_cjk_units(units)
        available = 470.0
        breaks = optimal_line_break(
            units, [available], scale=1.0, space_width=6.0, cjk_mode=True
        )
        assert breaks is not None
        from babeldoc.format.pdf.document_il.midend.line_break_optimizer import (
            _compute_line_width,
        )

        pts = [0] + breaks + [len(units)]
        lines = []
        for a, b in zip(pts[:-1], pts[1:], strict=False):
            chunk = "".join(u.try_get_unicode() for u in units[a:b])
            width = _compute_line_width(units, a, b, 1.0, 6.0, 0.0)
            lines.append((chunk, width))
        joined = "".join(ch for ch, _w in lines)
        assert "学\n一种" not in "\n".join(ch for ch, _w in lines)
        assert lines[0][0].endswith("一种。"), lines[0][0]
        # Interiors ≥ 95%, or end on ，。 within slack (line 1 max 432pt).
        for chunk, width in lines[:-1]:
            punct_ok = chunk[-1] in "。．？！；：，、" and width / available >= 0.90
            assert width / available >= 0.95 or punct_ok, (chunk, width, available)
        assert joined == text

    def test_a_comma_far_from_a_narrow_gap_is_not_a_full_line(self):
        """A 470pt column still treats 38pt of leftover comma as full.

        A 193pt gap does not. 61pt early is a hole.
        """
        wide = _line_cost(
            432, 470, 36, False, 500, cjk_mode=True, ends_with_punct=True
        )
        hole = _line_cost(
            132, 193, 11, False, 500, cjk_mode=True, ends_with_punct=True
        )
        assert wide == 0.0
        assert hole > 0.0

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
        # 半角标点亦属行首禁则（行首不得出现标点符号）
        assert is_cjk_line_start_forbidden(".")
        assert is_cjk_line_start_forbidden(",")
        assert is_cjk_line_start_forbidden(")")
        assert is_cjk_line_start_forbidden('"')
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
        """「见3.2」混排：半角点前不可断（避免行首出现半角点号「.2」）。"""

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
        # 半角 '.' 属行首禁则，前一单元「3」不可断（避免行首出现「.2」）
        assert units[1].can_break_line_cache is False
        # 「见」之后可断（允许「见 | 3.2」）
        assert units[0].can_break_line_cache is not False


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

    def test_percent_stays_on_the_same_line_as_its_digits(self):
        """40% must not break as 4|0% or 40|%. A bare number may still end a line."""

        class _U(MockUnit):
            def __init__(self, **kw):
                super().__init__(**kw)
                self.can_break_line_cache = None

            @property
            def can_break_line(self):
                if self.can_break_line_cache is not None:
                    return self.can_break_line_cache
                return self._can_break_line

        def units_for(text: str):
            built = []
            for ch in text:
                cjk = not (ch.isdigit() or ch in "%％ ")
                built.append(
                    _U(unicode=ch, width=10.0, is_cjk_char=cjk, is_space=ch == " ")
                )
            return built

        text = "几乎是40%的差距"
        units = units_for(text)
        merge_cjk_units(units)
        i4 = text.index("4")
        i0 = text.index("0")
        assert units[i4].can_break_line_cache is False
        assert units[i0].can_break_line_cache is False
        assert units[i4 - 1].can_break_line_cache is not False
        breaks = optimal_line_break(
            units, [50.0, 50.0, 50.0, 50.0], scale=1.0, space_width=5.0, cjk_mode=True
        )
        assert breaks is not None
        for bp in breaks:
            assert units[bp].try_get_unicode() not in {"%", "0"}
            assert units[bp - 1].can_break_line

        spaced = units_for("是40 %的")
        merge_cjk_units(spaced)
        assert spaced[1].can_break_line_cache is False  # 4|
        assert spaced[2].can_break_line_cache is False  # 0|
        assert spaced[3].can_break_line_cache is False  # space before %

        bare_text = "一共40人"
        bare = units_for(bare_text)
        merge_cjk_units(bare)
        assert bare[bare_text.index("4")].can_break_line_cache is False
        assert bare[bare_text.index("0")].can_break_line_cache is not False

        # NBSP or a zero-width mark between the digits and % still stays glued.
        for glue in ("\u00a0", "\u200b"):
            raw = f"一下。57{glue}% 的"
            glued = units_for(raw)
            merge_cjk_units(glued)
            assert glued[raw.index("7")].can_break_line_cache is False
            assert glued[raw.index(glue)].can_break_line_cache is False
            assert glued[raw.index("。")].can_break_line_cache is not False

    def test_massage_paragraph_keeps_the_verb_and_the_noun(self):
        """Day 1 p17 section 4 must not break 按摩|她 or 空|调."""

        class _U(MockUnit):
            def __init__(self, ch: str):
                super().__init__(width=11.8, unicode=ch, is_cjk_char=True)
                self.can_break_line_cache = None

            @property
            def can_break_line(self):
                if self.can_break_line_cache is not None:
                    return self.can_break_line_cache
                return True

        text = (
            "打开后，先是肉桂味的润滑剂，一碰就会热意起来。按摩她，"
            "摩擦刺激用手指中的液体。在进行性交之前，打开风扇或空调，"
            "看着她战栗因快感。"
        )
        units = [_U(ch) for ch in text]
        merge_cjk_units(units)
        mo = text.index("摩")
        kong = text.index("空")
        zhi = text.index("之")
        assert units[mo].can_break_line_cache is False
        assert units[kong].can_break_line_cache is False
        assert units[zhi].can_break_line_cache is False
        assert break_leaves_a_hole(59, 295)
        assert not break_leaves_a_hole(24, 295)
        breaks = optimal_line_break(
            units,
            [295.0, 330.4, 338.0],
            scale=1.0,
            space_width=0.0,
            cjk_mode=True,
        )
        assert breaks is not None
        lines = []
        pts = [0] + breaks + [len(units)]
        for a, b in zip(pts[:-1], pts[1:], strict=False):
            lines.append("".join(u.try_get_unicode() for u in units[a:b]))
        joined = "\n".join(lines)
        assert "按摩\n她" not in joined
        assert "空\n调" not in joined
        assert "风\n扇" not in joined
        assert "".join(lines) == text
