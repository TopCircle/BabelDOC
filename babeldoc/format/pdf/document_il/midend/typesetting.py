from __future__ import annotations

import copy
import logging
import re
import statistics
import unicodedata
from dataclasses import dataclass
from functools import cache

import pymupdf
import regex
from rtree import index

from babeldoc.const import WATERMARK_VERSION
from babeldoc.format.pdf.document_il import Box
from babeldoc.format.pdf.document_il import PdfCharacter
from babeldoc.format.pdf.document_il import PdfCurve
from babeldoc.format.pdf.document_il import PdfForm
from babeldoc.format.pdf.document_il import PdfFormula
from babeldoc.format.pdf.document_il import PdfParagraphComposition
from babeldoc.format.pdf.document_il import PdfStyle
from babeldoc.format.pdf.document_il import il_version_1
from babeldoc.format.pdf.document_il.utils.fontmap import FontMapper
from babeldoc.format.pdf.document_il.utils.formular_helper import update_formula_data
from babeldoc.format.pdf.document_il.midend.line_break_optimizer import optimal_line_break
from babeldoc.format.pdf.document_il.utils.layout_helper import box_to_tuple
from babeldoc.format.pdf.document_il.utils.cjk_dict import (
    is_cjk_three_char_word,
    is_cjk_two_char_word,
)
from babeldoc.format.pdf.translation_config import TranslationConfig
from babeldoc.format.pdf.translation_config import WatermarkOutputMode

logger = logging.getLogger(__name__)

LINE_BREAK_REGEX = regex.compile(
    r"^["
    r"a-z"
    r"A-Z"
    r"0-9"
    r"\u00C0-\u00FF"  # Latin-1 Supplement
    r"\u0100-\u017F"  # Latin Extended A
    r"\u0180-\u024F"  # Latin Extended B
    r"\u1E00-\u1EFF"  # Latin Extended Additional
    r"\u2C60-\u2C7F"  # Latin Extended C
    r"\uA720-\uA7FF"  # Latin Extended D
    r"\uAB30-\uAB6F"  # Latin Extended E
    r"\u0250-\u02A0"  # IPA Extensions
    r"\u0400-\u04FF"  # Cyrillic
    r"\u0300-\u036F"  # Combining Diacritical Marks
    r"\u0500-\u052F"  # Cyrillic Supplement
    r"\u0370-\u03FF"  # Greek and Coptic
    r"\u2DE0-\u2DFF"  # Cyrillic Extended-A
    r"\uA650-\uA69F"  # Cyrillic Extended-B
    r"\u1200-\u137F"  # Ethiopic
    r"\u1380-\u139F"  # Ethiopic Supplement
    r"\u2D80-\u2DDF"  # Ethiopic Extended
    r"\uAB00-\uAB2F"  # Ethiopic Extended-A
    r"\U0001E7E0-\U0001E7FF"  # Ethiopic Extended-B
    r"\u0E80-\u0EFF"  # Lao
    r"\u0D00-\u0D7F"  # Malayalam
    r"\u0A80-\u0AFF"  # Gujarati
    r"\u0E00-\u0E7F"  # Thai
    r"\u1000-\u109F"  # Myanmar
    r"\uAA60-\uAA7F"  # Myanmar Extended-A
    r"\uA9E0-\uA9FF"  # Myanmar Extended-B
    r"\U000116D0-\U000116FF"  # Myanmar Extended-C
    r"\u0B80-\u0BFF"  # Tamil
    r"\u0C00-\u0C7F"  # Telugu
    r"\u0B00-\u0B7F"  # Oriya
    r"\u0530-\u058F"  # Armenian
    r"\u10A0-\u10FF"  # Georgian
    r"\u1C90-\u1CBF"  # Georgian Extended
    r"\u2D00-\u2D2F"  # Georgian Supplement
    r"\u1780-\u17FF"  # Khmer
    r"\u19E0-\u19FF"  # Khmer Symbols
    r"\U00010B00-\U00010B3F"  # Avestan
    r"\u1D00-\u1D7F"  # Phonetic Extensions
    r"\u1400-\u167F"  # Unified Canadian Aboriginal Syllabics
    r"\u0B00-\u0B7F"  # Oriya
    r"\u0780-\u07BF"  # Thaana
    r"\U0001E900-\U0001E95F"  # Adlam
    r"\u1C80-\u1C8F"  # Cyrillic Extended-C
    r"\U0001E030-\U0001E08F"  # Cyrillic Extended-D
    r"\uA000-\uA48F"  # Yi Syllables
    r"\uA490-\uA4CF"  # Yi Radicals
    r"'"
    r"-"  # Hyphen
    r"·"  # Middle Dot (U+00B7) For Català
    r"ʻ"  # Spacing Modifier Letters U+02BB
    r"]+$"
)


@dataclass
class RetypesetResult:
    """Result of retypeset_with_scale_range()."""

    success: bool  # whether retypesetting succeeded
    best_scale: float | None = None  # the scale that was applied
    reason: str = ""  # failure reason or notes


# CJK 禁则字符集
_CJK_LINE_END_FORBIDDEN = frozenset("（【《「『〖〈〔")  # 行尾禁用
_CJK_LINE_START_FORBIDDEN = frozenset("。？！；：，、）】》」』〗〉〕")  # 行首禁用


def merge_cjk_units(units: list['TypesettingUnit']) -> list['TypesettingUnit']:
    """标记 CJK 词组边界，使 DP 和贪心断行不会在词组内部断开。

    策略：
    1. 提取 CJK 字符序列及其在 units 中的位置
    2. 使用内置词典识别词组边界
    3. 标记词组内部字符为 can_break_line=False
    4. 处理禁则：行首/行尾标点保护

    Args:
        units: 原始 TypesettingUnit 列表（每个 unit 对应一个字符）

    Returns:
        修改后的列表（原地修改 can_break_line 属性，返回同一列表）
    """
    if not units:
        return units

    n = len(units)

    # 收集 CJK 字符的位置和 unicode
    cjk_positions = []  # (index, unicode_char)
    for i, unit in enumerate(units):
        if unit.is_cjk_char:
            unicode = unit.try_get_unicode()
            if unicode:
                cjk_positions.append((i, unicode))

    if len(cjk_positions) < 2:
        return units

    # 构建 CJK 文本序列
    cjk_text = ''.join(ch for _, ch in cjk_positions)
    cjk_indices = [idx for idx, _ in cjk_positions]

    # 标记词组内部字符为不可断行
    # 使用二字词/三字词词典判断每个位置是否为词组边界
    # 边界：可以在该位置断行（即该位置之前的字符是词组末尾）
    # 注意：只在原始 units 中相邻的 CJK 字符之间检查词边界，
    #       避免因剥离非 CJK 字符导致的误匹配
    word_internal = set()  # 词组内部字符的 unit index

    for cjk_pos in range(1, len(cjk_text)):
        unit_idx = cjk_indices[cjk_pos]

        # 检查是否在词组内部（当前位置不是词组边界）
        # 只在原始 units 中相邻的 CJK 字符之间检查词边界，
        # 避免因剥离非 CJK 字符导致的误匹配
        if cjk_indices[cjk_pos] - cjk_indices[cjk_pos - 1] != 1:
            continue  # 原始序列中不相邻，跳过

        # 检查二字词：cjk_text[pos-1:pos+1]
        word2 = cjk_text[cjk_pos - 1 : cjk_pos + 1]
        if is_cjk_two_char_word(word2):
            word_internal.add(unit_idx)
            continue

        # 检查三字词：cjk_text[pos-2:pos+1]，需要 pos-2 也相邻
        if (
            cjk_pos >= 2
            and cjk_indices[cjk_pos - 1] - cjk_indices[cjk_pos - 2] == 1
        ):
            word3 = cjk_text[cjk_pos - 2 : cjk_pos + 1]
            if is_cjk_three_char_word(word3):
                word_internal.add(unit_idx)
                # 也标记中间字符
                word_internal.add(cjk_indices[cjk_pos - 1])

    # 应用标记
    for i, unit in enumerate(units):
        if i in word_internal:
            unit.can_break_line_cache = False

    # 处理禁则
    for i, unit in enumerate(units):
        unicode = unit.try_get_unicode()
        if not unicode:
            continue

        # 行首禁用标点：标点前的 CJK 字符不可断行（避免标点出现在行首）
        # 仅当前置字符是 CJK 时才抑制断行；空格/英文后的标点可以正常断行
        if (
            unicode in _CJK_LINE_START_FORBIDDEN
            and i > 0
            and units[i - 1].is_cjk_char
        ):
            units[i - 1].can_break_line_cache = False

        # 行尾禁用标点：标点本身不可断行（避免标点出现在行尾后孤零零）
        # 这个已有 is_cannot_appear_in_line_end_punctuation 处理

    return units


class TypesettingUnit:
    def __str__(self):
        return self.try_get_unicode() or ""

    def __init__(
        self,
        char: PdfCharacter | None = None,
        formular: PdfFormula | None = None,
        unicode: str | None = None,
        font: pymupdf.Font | None = None,
        original_font: il_version_1.PdfFont | None = None,
        font_size: float | None = None,
        style: PdfStyle | None = None,
        xobj_id: int | None = None,
        debug_info: bool = False,
    ):
        assert (char is not None) + (formular is not None) + (
            unicode is not None
        ) == 1, "Only one of chars and formular can be not None"
        self.char = char
        self.formular = formular
        self.unicode = unicode
        self.x = None
        self.y = None
        self.scale = None
        self.debug_info = debug_info

        # Cache variables
        self.box_cache: Box | None = None
        self.can_break_line_cache: bool | None = None
        self.is_cjk_char_cache: bool | None = None
        self.mixed_character_blacklist_cache: bool | None = None
        self.is_space_cache: bool | None = None
        self.is_hung_punctuation_cache: bool | None = None
        self.is_cannot_appear_in_line_end_punctuation_cache: bool | None = None
        self.can_passthrough_cache: bool | None = None
        self.width_cache: float | None = None
        self.height_cache: float | None = None

        self.font_size: float | None = None

        if unicode:
            assert font_size, "Font size must be provided when unicode is provided"
            assert style, "Style must be provided when unicode is provided"
            assert len(unicode) == 1, "Unicode must be a single character"
            assert xobj_id is not None, (
                "Xobj id must be provided when unicode is provided"
            )

            self.font = font
            if font is not None and hasattr(font, "font_id"):
                self.font_id = font.font_id
            else:
                self.font_id = "base"
            if original_font:
                self.original_font = original_font
            else:
                self.original_font = None

            self.font_size = font_size
            self.style = style
            self.xobj_id = xobj_id

    def try_resue_cache(self, old_tu: TypesettingUnit):
        if old_tu.is_cjk_char_cache is not None:
            self.is_cjk_char_cache = old_tu.is_cjk_char_cache

        if old_tu.can_break_line_cache is not None:
            self.can_break_line_cache = old_tu.can_break_line_cache

        if old_tu.is_space_cache is not None:
            self.is_space_cache = old_tu.is_space_cache

        if old_tu.is_hung_punctuation_cache is not None:
            self.is_hung_punctuation_cache = old_tu.is_hung_punctuation_cache

        if old_tu.is_cannot_appear_in_line_end_punctuation_cache is not None:
            self.is_cannot_appear_in_line_end_punctuation_cache = (
                old_tu.is_cannot_appear_in_line_end_punctuation_cache
            )

        if old_tu.can_passthrough_cache is not None:
            self.can_passthrough_cache = old_tu.can_passthrough_cache

        if old_tu.mixed_character_blacklist_cache is not None:
            self.mixed_character_blacklist_cache = (
                old_tu.mixed_character_blacklist_cache
            )

    def try_get_unicode(self) -> str | None:
        if self.char:
            return self.char.char_unicode
        elif self.formular:
            return None
        elif self.unicode:
            return self.unicode

    @property
    def mixed_character_blacklist(self):
        if self.mixed_character_blacklist_cache is None:
            self.mixed_character_blacklist_cache = self.calc_mixed_character_blacklist()

        return self.mixed_character_blacklist_cache

    def calc_mixed_character_blacklist(self):
        unicode = self.try_get_unicode()
        if unicode:
            return unicode in [
                "。",
                "，",
                "：",
                "？",
                "！",
            ]
        return False

    @property
    def can_break_line(self):
        if self.can_break_line_cache is None:
            self.can_break_line_cache = self.calc_can_break_line()

        return self.can_break_line_cache

    def calc_can_break_line(self):
        unicode = self.try_get_unicode()
        if not unicode:
            return True
        if LINE_BREAK_REGEX.match(unicode):
            return False
        return True

    @property
    def is_cjk_char(self):
        if self.is_cjk_char_cache is None:
            self.is_cjk_char_cache = self.calc_is_cjk_char()

        return self.is_cjk_char_cache

    def calc_is_cjk_char(self):
        if self.formular:
            return False
        unicode = self.try_get_unicode()
        if not unicode:
            return False
        if "(cid" in unicode:
            return False
        if len(unicode) > 1:
            return False
        assert len(unicode) == 1, "Unicode must be a single character"
        if unicode in [
            "（",
            "）",
            "【",
            "】",
            "《",
            "》",
            "〔",
            "〕",
            "〈",
            "〉",
            "〖",
            "〗",
            "「",
            "」",
            "『",
            "』",
            "、",
            "。",
            "：",
            "？",
            "！",
            "，",
        ]:
            return True
        if unicode:
            if re.match(
                r"^["
                r"\u3000-\u303f"  # CJK Symbols and Punctuation
                r"\u3040-\u309f"  # Hiragana
                r"\u30a0-\u30ff"  # Katakana
                r"\u3100-\u312f"  # Bopomofo
                r"\uac00-\ud7af"  # Hangul Syllables
                r"\u1100-\u11ff"  # Hangul Jamo
                r"\u3130-\u318f"  # Hangul Compatibility Jamo
                r"\ua960-\ua97f"  # Hangul Jamo Extended-A
                r"\ud7b0-\ud7ff"  # Hangul Jamo Extended-B
                r"\u3190-\u319f"  # Kanbun
                r"\u3200-\u32ff"  # Enclosed CJK Letters and Months
                r"\u3300-\u33ff"  # CJK Compatibility
                r"\ufe30-\ufe4f"  # CJK Compatibility Forms
                r"\u4e00-\u9fff"  # CJK Unified Ideographs
                r"\u2e80-\u2eff"  # CJK Radicals Supplement
                r"\u31c0-\u31ef"  # CJK Strokes
                r"\u2f00-\u2fdf"  # Kangxi Radicals
                r"\ufe10-\ufe1f"  # Vertical Forms
                r"]+$",
                unicode,
            ):
                return True
            try:
                unicodedata_name = unicodedata.name(unicode)
                return (
                    "CJK UNIFIED IDEOGRAPH" in unicodedata_name
                    or "FULLWIDTH" in unicodedata_name
                )
            except ValueError:
                return False
        return False

    @property
    def is_space(self):
        if self.is_space_cache is None:
            self.is_space_cache = self.calc_is_space()

        return self.is_space_cache

    def calc_is_space(self):
        if self.formular:
            return False
        unicode = self.try_get_unicode()
        return unicode == " "

    @property
    def is_hung_punctuation(self):
        if self.is_hung_punctuation_cache is None:
            self.is_hung_punctuation_cache = self.calc_is_hung_punctuation()

        return self.is_hung_punctuation_cache

    def calc_is_hung_punctuation(self):
        if self.formular:
            return False
        unicode = self.try_get_unicode()

        if unicode:
            return unicode in [
                # 英文标点
                ",",
                ".",
                ":",
                ";",
                "?",
                "!",
                # 中文点号
                "，",  # 逗号
                "。",  # 句号
                "．",  # 全角句号
                "、",  # 顿号
                "：",  # 冒号
                "；",  # 分号
                "！",  # 叹号
                "‼",  # 双叹号
                "？",  # 问号
                "⁇",  # 双问号
                # 结束引号
                "”",  # 右双引号
                "’",  # 右单引号
                "」",  # 右直角单引号
                "』",  # 右直角双引号
                # 结束括号
                ")",  # 右圆括号
                "]",  # 右方括号
                "}",  # 右花括号
                "）",  # 右圆括号
                "〕",  # 右龟甲括号
                "〉",  # 右单书名号
                "】",  # 右黑色方头括号
                "〗",  # 右空白方头括号
                "］",  # 全角右方括号
                "｝",  # 全角右花括号
                # 结束双书名号
                "》",  # 右双书名号
                # 连接号
                "～",  # 全角波浪号
                "-",  # 连字符减号
                "–",  # 短破折号 (EN DASH)
                "—",  # 长破折号 (EM DASH)
                # 间隔号
                "·",  # 中间点
                "・",  # 片假名中间点
                "‧",  # 连字点
                # 分隔号
                "/",  # 斜杠
                "／",  # 全角斜杠
                "⁄",  # 分数斜杠
            ]
        return False

    @property
    def is_cannot_appear_in_line_end_punctuation(self):
        if self.is_cannot_appear_in_line_end_punctuation_cache is None:
            self.is_cannot_appear_in_line_end_punctuation_cache = (
                self.calc_is_cannot_appear_in_line_end_punctuation()
            )

        return self.is_cannot_appear_in_line_end_punctuation_cache

    def calc_is_cannot_appear_in_line_end_punctuation(self):
        if self.formular:
            return False
        unicode = self.try_get_unicode()
        if not unicode:
            return False
        return unicode in [
            # 开始引号
            "“",  # 左双引号
            "‘",  # 左单引号
            "「",  # 左直角单引号
            "『",  # 左直角双引号
            # 开始括号
            "(",  # 左圆括号
            "[",  # 左方括号
            "{",  # 左花括号
            "（",  # 左圆括号
            "〔",  # 左龟甲括号
            "〈",  # 左单书名号
            "《",  # 左双书名号
            # 开始单双书名号
            "〖",  # 左空白方头括号
            "〘",  # 左黑色方头括号
            "〚",  # 左单书名号
        ]

    def passthrough(
        self,
    ) -> tuple[list[PdfCharacter], list[PdfCurve], list[PdfForm]]:
        if self.char:
            return [self.char], [], []
        elif self.formular:
            return (
                self.formular.pdf_character,
                self.formular.pdf_curve,
                self.formular.pdf_form,
            )
        elif self.unicode:
            logger.error(f"Cannot passthrough unicode. TypesettingUnit: {self}. ")
            logger.error(f"Cannot passthrough unicode. TypesettingUnit: {self}. ")
            return [], [], []

    @property
    def can_passthrough(self):
        if self.can_passthrough_cache is None:
            self.can_passthrough_cache = self.calc_can_passthrough()

        return self.can_passthrough_cache

    def calc_can_passthrough(self):
        return self.unicode is None

    def calculate_box(self):
        if self.char:
            box = copy.deepcopy(self.char.box)
            if self.char.visual_bbox and self.char.visual_bbox.box:
                box.y = self.char.visual_bbox.box.y
                box.y2 = self.char.visual_bbox.box.y2
                # return self.char.visual_bbox.box

            return box
        elif self.formular:
            return self.formular.box
            # if self.formular.x_offset <= 0.5:
            #     return self.formular.box
            # formular_box = copy.copy(self.formular.box)
            # formular_box.x2 += self.formular.x_advance
            # return formular_box
        elif self.unicode:
            char_width = self.font.char_lengths(self.unicode, self.font_size)[0]
            if self.x is None or self.y is None or self.scale is None:
                return Box(0, 0, char_width, self.font_size)
            return Box(self.x, self.y, self.x + char_width, self.y + self.font_size)

    @property
    def box(self):
        if not self.box_cache:
            self.box_cache = self.calculate_box()

        return self.box_cache

    @property
    def width(self):
        if self.width_cache is None:
            self.width_cache = self.calc_width()

        return self.width_cache

    def calc_width(self):
        box = self.box
        return box.x2 - box.x

    @property
    def height(self):
        if self.height_cache is None:
            self.height_cache = self.calc_height()

        return self.height_cache

    def calc_height(self):
        box = self.box
        return box.y2 - box.y

    def shift_x(self, dx: float) -> None:
        """Shift this unit horizontally in place (after relocate)."""
        if abs(dx) < 1e-6:
            return
        if self.char and self.char.box:
            self.char.box.x += dx
            self.char.box.x2 += dx
            if self.char.visual_bbox and self.char.visual_bbox.box:
                self.char.visual_bbox.box.x += dx
                self.char.visual_bbox.box.x2 += dx
        elif self.formular:
            if self.formular.box:
                self.formular.box.x += dx
                self.formular.box.x2 += dx
            for char in self.formular.pdf_character or []:
                if char.box:
                    char.box.x += dx
                    char.box.x2 += dx
                if char.visual_bbox and char.visual_bbox.box:
                    char.visual_bbox.box.x += dx
                    char.visual_bbox.box.x2 += dx
            for curve in self.formular.pdf_curve or []:
                if curve.box:
                    curve.box.x += dx
                    curve.box.x2 += dx
                if curve.relocation_transform and len(curve.relocation_transform) >= 6:
                    # CTM translation component e (index 4)
                    rt = list(curve.relocation_transform)
                    rt[4] += dx
                    curve.relocation_transform = rt
            for form in self.formular.pdf_form or []:
                if form.box:
                    form.box.x += dx
                    form.box.x2 += dx
                if form.relocation_transform and len(form.relocation_transform) >= 6:
                    rt = list(form.relocation_transform)
                    rt[4] += dx
                    form.relocation_transform = rt
        elif self.unicode is not None and self.x is not None:
            self.x += dx
        self.box_cache = None

    def relocate(
        self,
        x: float,
        y: float,
        scale: float,
    ) -> TypesettingUnit:
        """重定位并缩放排版单元

        Args:
            x: 新的 x 坐标
            y: 新的 y 坐标
            scale: 缩放因子

        Returns:
            新的排版单元
        """
        if self.char:
            # 创建新的字符对象
            new_char = PdfCharacter(
                pdf_character_id=self.char.pdf_character_id,
                char_unicode=self.char.char_unicode,
                box=Box(
                    x=x,
                    y=y,
                    x2=x + self.width * scale,
                    y2=y + self.height * scale,
                ),
                pdf_style=PdfStyle(
                    font_id=self.char.pdf_style.font_id,
                    font_size=self.char.pdf_style.font_size * scale,
                    graphic_state=self.char.pdf_style.graphic_state,
                ),
                scale=scale,
                vertical=self.char.vertical,
                advance=self.char.advance * scale if self.char.advance else None,
                debug_info=self.debug_info,
                xobj_id=self.char.xobj_id,
            )
            new_tu = TypesettingUnit(char=new_char)
            new_tu.try_resue_cache(self)
            return new_tu

        elif self.formular:
            # 创建新的公式对象，保持内部字符的相对位置
            new_chars = []
            min_x = self.formular.box.x
            min_y = self.formular.box.y

            for char in self.formular.pdf_character:
                # 计算相对位置
                rel_x = char.box.x - min_x
                rel_y = char.box.y - min_y

                visual_rel_x = char.visual_bbox.box.x - min_x
                visual_rel_y = char.visual_bbox.box.y - min_y

                # 创建新的字符对象
                new_char = PdfCharacter(
                    pdf_character_id=char.pdf_character_id,
                    char_unicode=char.char_unicode,
                    box=Box(
                        x=x + (rel_x + self.formular.x_offset) * scale,
                        y=y + (rel_y + self.formular.y_offset) * scale,
                        x2=x
                        + (rel_x + (char.box.x2 - char.box.x) + self.formular.x_offset)
                        * scale,
                        y2=y
                        + (rel_y + (char.box.y2 - char.box.y) + self.formular.y_offset)
                        * scale,
                    ),
                    visual_bbox=il_version_1.VisualBbox(
                        box=Box(
                            x=x + (visual_rel_x + self.formular.x_offset) * scale,
                            y=y + (visual_rel_y + self.formular.y_offset) * scale,
                            x2=x
                            + (
                                visual_rel_x
                                + (char.visual_bbox.box.x2 - char.visual_bbox.box.x)
                                + self.formular.x_offset
                            )
                            * scale,
                            y2=y
                            + (
                                visual_rel_y
                                + (char.visual_bbox.box.y2 - char.visual_bbox.box.y)
                                + self.formular.y_offset
                            )
                            * scale,
                        ),
                    ),
                    pdf_style=PdfStyle(
                        font_id=char.pdf_style.font_id,
                        font_size=char.pdf_style.font_size * scale,
                        graphic_state=char.pdf_style.graphic_state,
                    ),
                    scale=scale,
                    vertical=char.vertical,
                    advance=char.advance * scale if char.advance else None,
                    xobj_id=char.xobj_id,
                )
                new_chars.append(new_char)

            # Calculate bounding box from new_chars
            min_x = min(char.visual_bbox.box.x for char in new_chars)
            min_y = min(char.visual_bbox.box.y for char in new_chars)
            max_x = max(char.visual_bbox.box.x2 for char in new_chars)
            max_y = max(char.visual_bbox.box.y2 for char in new_chars)

            new_formula = PdfFormula(
                box=Box(
                    x=min_x,
                    y=min_y,
                    x2=max_x,
                    y2=max_y,
                ),
                pdf_character=new_chars,
                x_offset=self.formular.x_offset * scale,
                y_offset=self.formular.y_offset * scale,
                x_advance=self.formular.x_advance * scale,
            )

            # Handle contained curves
            new_curves = []
            for curve in self.formular.pdf_curve:
                new_curve = self._transform_curve_for_relocation(
                    curve,
                    self.formular.box.x,
                    self.formular.box.y,
                    x,
                    y,
                    scale,
                )
                new_curves.append(new_curve)
            new_formula.pdf_curve = new_curves

            # Handle contained forms
            new_forms = []
            for form in self.formular.pdf_form:
                new_form = self._transform_form_for_relocation(
                    form, self.formular.box.x, self.formular.box.y, x, y, scale
                )
                new_forms.append(new_form)
            new_formula.pdf_form = new_forms

            update_formula_data(new_formula)

            new_tu = TypesettingUnit(formular=new_formula)
            new_tu.try_resue_cache(self)
            return new_tu

        elif self.unicode:
            # 对于 Unicode 字符，我们存储新的位置信息
            new_unit = TypesettingUnit(
                unicode=self.unicode,
                font=self.font,
                original_font=self.original_font,
                font_size=self.font_size * scale,
                style=self.style,
                xobj_id=self.xobj_id,
                debug_info=self.debug_info,
            )
            new_unit.x = x
            new_unit.y = y
            new_unit.scale = scale
            new_unit.try_resue_cache(self)
            return new_unit

    def _transform_curve_for_relocation(
        self,
        curve,
        original_formula_x: float,
        original_formula_y: float,
        new_x: float,
        new_y: float,
        scale: float,
    ):
        """Transform a curve for formula relocation."""
        new_curve = PdfCurve(
            box=curve.box,
            graphic_state=curve.graphic_state,
            pdf_path=list(curve.pdf_path),
            pdf_original_path=list(curve.pdf_original_path),
            pdf_original_path_primitive=curve.pdf_original_path_primitive,
            debug_info=curve.debug_info,
            fill_background=curve.fill_background,
            stroke_path=curve.stroke_path,
            evenodd=curve.evenodd,
            passthrough_paint=curve.passthrough_paint,
            xobj_id=curve.xobj_id,
            render_order=curve.render_order,
            ctm=list(curve.ctm),
            relocation_transform=list(curve.relocation_transform),
        )

        if new_curve.box:
            # Calculate relative position to formula's original position (same as chars)
            rel_x = new_curve.box.x - original_formula_x
            rel_y = new_curve.box.y - original_formula_y

            # Apply same transformation as characters
            new_curve.box = Box(
                x=new_x + (rel_x + self.formular.x_offset) * scale,
                y=new_y + (rel_y + self.formular.y_offset) * scale,
                x2=new_x
                + (
                    rel_x
                    + (new_curve.box.x2 - new_curve.box.x)
                    + self.formular.x_offset
                )
                * scale,
                y2=new_y
                + (
                    rel_y
                    + (new_curve.box.y2 - new_curve.box.y)
                    + self.formular.y_offset
                )
                * scale,
            )

        # Set relocation transform instead of modifying original CTM
        translation_x = (
            new_x + self.formular.x_offset * scale - original_formula_x * scale
        )
        translation_y = (
            new_y + self.formular.y_offset * scale - original_formula_y * scale
        )

        # Create relocation transformation matrix
        from babeldoc.format.pdf.document_il.utils.matrix_helper import (
            create_translation_and_scale_matrix,
        )

        relocation_matrix = create_translation_and_scale_matrix(
            translation_x, translation_y, scale
        )
        new_curve.relocation_transform = list(relocation_matrix)

        return new_curve

    def _transform_form_for_relocation(
        self,
        form,
        original_formula_x: float,
        original_formula_y: float,
        new_x: float,
        new_y: float,
        scale: float,
    ):
        """Transform a form for formula relocation."""
        new_form = PdfForm(
            box=form.box,
            graphic_state=form.graphic_state,
            pdf_matrix=form.pdf_matrix,
            pdf_affine_transform=form.pdf_affine_transform,
            pdf_form_subtype=form.pdf_form_subtype,
            xobj_id=form.xobj_id,
            ctm=list(form.ctm),
            relocation_transform=list(form.relocation_transform),
            render_order=form.render_order,
            form_type=form.form_type,
        )

        if new_form.box:
            # Calculate relative position to formula's original position (same as chars)
            rel_x = new_form.box.x - original_formula_x
            rel_y = new_form.box.y - original_formula_y

            # Apply same transformation as characters
            new_form.box = Box(
                x=new_x + (rel_x + self.formular.x_offset) * scale,
                y=new_y + (rel_y + self.formular.y_offset) * scale,
                x2=new_x
                + (rel_x + (new_form.box.x2 - new_form.box.x) + self.formular.x_offset)
                * scale,
                y2=new_y
                + (rel_y + (new_form.box.y2 - new_form.box.y) + self.formular.y_offset)
                * scale,
            )

        # Set relocation transform instead of modifying original matrices
        translation_x = (
            new_x + self.formular.x_offset * scale - original_formula_x * scale
        )
        translation_y = (
            new_y + self.formular.y_offset * scale - original_formula_y * scale
        )

        # Create relocation transformation matrix
        from babeldoc.format.pdf.document_il.utils.matrix_helper import (
            create_translation_and_scale_matrix,
        )

        relocation_matrix = create_translation_and_scale_matrix(
            translation_x, translation_y, scale
        )
        new_form.relocation_transform = list(relocation_matrix)

        return new_form

    def render(
        self,
    ) -> tuple[list[PdfCharacter], list[PdfCurve], list[PdfForm]]:
        """渲染排版单元为 PdfCharacter 列表

        Returns:
            PdfCharacter 列表
        """
        if self.can_passthrough:
            return self.passthrough()
        elif self.unicode:
            assert self.x is not None, (
                "x position must be set, should be set by `relocate`"
            )
            assert self.y is not None, (
                "y position must be set, should be set by `relocate`"
            )
            assert self.scale is not None, (
                "scale must be set, should be set by `relocate`"
            )
            x = self.x
            y = self.y
            # if self.original_font and self.font and hasattr(self.original_font, "descent") and hasattr(self.font, "descent_fontmap"):
            #     original_descent = self.original_font.descent
            #     new_descent = self.font.descent_fontmap
            #     y -= (original_descent - new_descent) * self.font_size / 1000

            # 计算字符宽度
            char_width = self.width

            new_char = PdfCharacter(
                pdf_character_id=self.font.has_glyph(ord(self.unicode)),
                char_unicode=self.unicode,
                box=Box(
                    x=x,  # 使用存储的位置
                    y=y,
                    x2=x + char_width,
                    y2=y + self.font_size,
                ),
                pdf_style=PdfStyle(
                    font_id=self.font_id,
                    font_size=self.font_size,
                    graphic_state=self.style.graphic_state,
                ),
                scale=self.scale,
                vertical=False,
                advance=char_width,
                xobj_id=self.xobj_id,
                debug_info=self.debug_info,
            )
            return [new_char], [], []
        else:
            logger.error(f"Unknown typesetting unit. TypesettingUnit: {self}. ")
            logger.error(f"Unknown typesetting unit. TypesettingUnit: {self}. ")
            return [], [], []


class Typesetting:
    stage_name = "Typesetting"
    _DEFAULT_LINE_SKIP_CJK = 1.50
    _DEFAULT_LINE_SKIP_NON_CJK = 1.3
    # Floor for scale search. 0.1 produced unreadable 1–4pt text when
    # exclusion zones left only a needle strip (Orgasms p.10/19/20).
    MIN_READABLE_SCALE = 0.55

    def __init__(self, translation_config: TranslationConfig):
        self.font_mapper = FontMapper(translation_config)
        self.translation_config = translation_config
        self.lang_code = self.translation_config.lang_out.upper()
        self.is_cjk = (
            # Why zh-CN/zh-HK/zh-TW here but not zh-Hans and so on?
            # See https://funstory-ai.github.io/BabelDOC/supported_languages/
            ("ZH" in self.lang_code)  # C
            or ("JA" in self.lang_code)
            or ("JP" in self.lang_code)  # J
            or ("KR" in self.lang_code)  # K
            or ("CN" in self.lang_code)
            or ("HK" in self.lang_code)
            or ("TW" in self.lang_code)
        )
        self._drop_all_figures_for_paragraph = False

    def preprocess_document(
        self,
        document: il_version_1.Document,
        pbar,
        build_zone_index: bool = False,
    ):
        """预处理文档，获取每个段落的最优缩放因子，不执行实际排版

        Args:
            document: 文档对象
            pbar: 进度条
            build_zone_index: 是否为每页构建排除区域索引（影响 scale 计算）
        """
        from babeldoc.format.pdf.document_il.midend.exclusion_zone import (
            ExclusionZoneBuilder,
            ExclusionZoneIndex,
        )

        all_scales: list[float] = []
        all_paragraphs: list[il_version_1.PdfParagraph] = []

        for page in document.page:
            if pbar is not None:
                pbar.advance()

            # 为当前页构建排除区域索引（优先使用缓存）
            if build_zone_index:
                cache = getattr(self, "_page_zone_cache", None)
                if cache and id(page) in cache:
                    self._current_zone_index = cache[id(page)]
                else:
                    zones = ExclusionZoneBuilder.build(page)
                    self._current_zone_index = (
                        ExclusionZoneIndex(zones) if zones else None
                    )
            else:
                self._current_zone_index = None

            # 准备字体信息（复制自 render_page 的逻辑）
            fonts: dict[
                str | int,
                il_version_1.PdfFont | dict[str, il_version_1.PdfFont],
            ] = {f.font_id: f for f in page.pdf_font if f.font_id}
            page_fonts = {f.font_id: f for f in page.pdf_font if f.font_id}
            for k, v in self.font_mapper.fontid2font.items():
                fonts[k] = v
            for xobj in page.pdf_xobject:
                if xobj.xobj_id is not None:
                    fonts[xobj.xobj_id] = page_fonts.copy()
                    for font in xobj.pdf_font:
                        if (
                            xobj.xobj_id in fonts
                            and isinstance(fonts[xobj.xobj_id], dict)
                            and font.font_id
                        ):
                            fonts[xobj.xobj_id][font.font_id] = font

            # 处理每个段落
            for paragraph in page.pdf_paragraph:
                all_paragraphs.append(paragraph)
                unit_count = 0
                try:
                    typesetting_units = self.create_typesetting_units(paragraph, fonts)
                    unit_count = len(typesetting_units)
                    for unit in typesetting_units:
                        if unit.formular:
                            unit_count += len(unit.formular.pdf_character) - 1

                    # 如果所有单元都可以直接传递，则 scale = 1.0
                    if all(unit.can_passthrough for unit in typesetting_units):
                        paragraph.optimal_scale = 1.0
                    else:
                        # 获取最优缩放因子
                        optimal_scale = self._get_optimal_scale(
                            paragraph, page, typesetting_units
                        )
                        paragraph.optimal_scale = optimal_scale
                except Exception as e:
                    # 如果预处理出错，默认使用 1.0 缩放因子
                    logger.warning(f"预处理段落时出错：{e}")
                    paragraph.optimal_scale = 1.0

                if paragraph.optimal_scale is not None:
                    all_scales.extend([paragraph.optimal_scale] * unit_count)

        # 获取缩放因子的众数
        if all_scales:
            try:
                modes = statistics.multimode(all_scales)
                mode_scale = min(modes)
            except statistics.StatisticsError:
                logger.warning(
                    "Could not find a mode for paragraph scales. Falling back to median."
                )
                mode_scale = statistics.median(all_scales)
            # 将所有大于众数的值修改为众数
            for paragraph in all_paragraphs:
                if (
                    paragraph.optimal_scale is not None
                    and paragraph.optimal_scale > mode_scale
                ):
                    paragraph.optimal_scale = mode_scale
        else:
            logger.error(
                "document_scales is empty, there seems no paragraph in this PDF"
            )

    def _find_optimal_scale_and_layout(
        self,
        paragraph: il_version_1.PdfParagraph,
        page: il_version_1.Page,
        typesetting_units: list[TypesettingUnit],
        initial_scale: float = 1.0,
        use_english_line_break: bool = True,
        apply_layout: bool = False,
        line_skip: float | None = None,
    ) -> tuple[float, list[TypesettingUnit] | None]:
        """查找最优缩放因子并可选择性地执行布局

        Args:
            paragraph: 段落对象
            page: 页面对象
            typesetting_units: 排版单元列表
            initial_scale: 初始缩放因子
            use_english_line_break: 是否使用英文换行规则
            apply_layout: 是否应用布局到 paragraph（True 时执行实际排版）

        Returns:
            tuple[float, list[TypesettingUnit] | None]: (最终缩放因子，排版后的单元列表或 None)
        """
        if not paragraph.box:
            return initial_scale, None

        # Ignore DocLayout figure zones that spill over this paragraph's own
        # box (false positives crush body text to unreadable scale).
        page_zones = getattr(self, "_current_zone_index", None)
        filtered_zones = page_zones
        if page_zones is not None and paragraph.box is not None:
            filtered_zones = page_zones.filter_for_paragraph(
                paragraph.box,
                drop_all_figures=getattr(
                    self, "_drop_all_figures_for_paragraph", False
                ),
            )
        prev_zones = page_zones
        self._current_zone_index = filtered_zones
        try:
            return self._find_optimal_scale_and_layout_inner(
                paragraph,
                page,
                typesetting_units,
                initial_scale,
                use_english_line_break,
                apply_layout,
                line_skip,
            )
        finally:
            self._current_zone_index = prev_zones

    def _find_optimal_scale_and_layout_inner(
        self,
        paragraph: il_version_1.PdfParagraph,
        page: il_version_1.Page,
        typesetting_units: list[TypesettingUnit],
        initial_scale: float = 1.0,
        use_english_line_break: bool = True,
        apply_layout: bool = False,
        line_skip: float | None = None,
    ) -> tuple[float, list[TypesettingUnit] | None]:
        """Core scale search + layout (zone index already filtered)."""
        box = paragraph.box
        scale = initial_scale
        if line_skip is None:
            line_skip = self._DEFAULT_LINE_SKIP_CJK if self.is_cjk else self._DEFAULT_LINE_SKIP_NON_CJK

        # 提取原版行宽，用于参考布局
        reference_widths = self._extract_original_line_widths(paragraph)
        if reference_widths:
            logger.debug(
                f"Reference layout: {len(reference_widths)} original lines, "
                f"widths={[f'{w:.1f}' for w in reference_widths]}"
            )
        min_scale = getattr(
            self.translation_config, "min_readable_scale", None
        )
        if min_scale is None:
            min_scale = self.MIN_READABLE_SCALE
        expand_space_flag = 0
        final_typeset_units = None
        last_typeset_units = None  # last layout attempt (may overflow box)

        # Pre-expand narrow boxes before scale search when translated content is
        # clearly wider than the original tight box (e.g. EN "Edging" → ZH
        # "边缘控制（Edging）"). Without this, scale is crushed to ~0.5 first
        # and expansion only runs after scale < 0.7.
        box = self._pre_expand_narrow_box(
            box, paragraph, page, typesetting_units, apply_layout=apply_layout
        )

        while scale >= min_scale:
            try:
                # 尝试布局排版单元
                typeset_units, all_units_fit = self._layout_typesetting_units(
                    typesetting_units,
                    box,
                    scale,
                    line_skip,
                    paragraph,
                    use_english_line_break,
                    reference_widths=reference_widths,
                )
                if typeset_units:
                    last_typeset_units = typeset_units

                # 如果所有单元都放得下
                if all_units_fit:
                    if apply_layout:
                        # DP 断行优化：在最终布局时尝试更优的断行方案
                        optimized_typeset_units = None
                        try:
                            # 计算必要的参数
                            font_sizes = []
                            for u in typesetting_units:
                                if u.font_size:
                                    font_sizes.append(u.font_size)
                                if u.char and u.char.pdf_style and u.char.pdf_style.font_size:
                                    font_sizes.append(u.char.pdf_style.font_size)
                            try:
                                font_size = statistics.mode(font_sizes) if font_sizes else 10
                            except statistics.StatisticsError:
                                # 多模态字号数据：使用均值作为回退
                                # 这可能 indicate 段落内有混合字号（如正文+脚注）
                                font_size = sum(font_sizes) / len(font_sizes) if font_sizes else 10
                                logger.warning(
                                    f"Ambiguous font sizes in paragraph, using mean: {font_size:.1f} "
                                    f"(sizes: {sorted(set(font_sizes))})"
                                )
                            opt_space_width = (
                                self.font_mapper.base_font.char_lengths("你", font_size * scale)[0] * 0.5
                            )
                            opt_tracking = (
                                paragraph.decorative_tracking * scale
                                if getattr(paragraph, "decorative_tracking", None)
                                else 0
                            )
                            unit_heights = [u.height for u in typesetting_units if u.height]
                            if unit_heights:
                                try:
                                    opt_avg_height = statistics.mode(unit_heights) * scale
                                except statistics.StatisticsError:
                                    opt_avg_height = sum(unit_heights) / len(unit_heights) * scale
                            else:
                                opt_avg_height = 0

                            if opt_avg_height > 0:
                                opt_breaks = self._compute_optimal_breaks(
                                    typesetting_units, box, scale, opt_avg_height,
                                    line_skip, opt_space_width, opt_tracking,
                                    reference_widths=reference_widths,
                                )
                                if opt_breaks:
                                    opt_units, opt_fit = self._layout_typesetting_units(
                                        typesetting_units, box, scale, line_skip,
                                        paragraph, use_english_line_break,
                                        break_points=opt_breaks,
                                        reference_widths=reference_widths,
                                    )
                                    if opt_fit and opt_units:
                                        optimized_typeset_units = opt_units
                        except Exception as e:
                            # DP 优化失败，使用贪心结果
                            logger.warning(f"DP line break optimization failed: {e}")

                        # === DIAGNOSTIC: DP 是否被采用 ===
                        if "在这些" in (paragraph.unicode or ""):
                            import os as _os
                            _diag_path = _os.environ.get("BABELDOC_DIAG_LOG", "/tmp/babeldoc_diag.log")
                            with open(_diag_path, "a", encoding="utf-8") as _f:
                                _f.write("=== DIAG DP adoption ===\n")
                                _f.write(f"  debug_id={getattr(paragraph, 'debug_id', None)}\n")
                                _f.write(f"  opt_breaks={opt_breaks}\n")
                                _f.write(f"  opt_fit={'N/A' if not opt_breaks else opt_fit}\n")
                                _f.write(f"  optimized_typeset_units={'yes' if optimized_typeset_units else 'no'}\n")
                                _f.write(f"  using={'DP' if optimized_typeset_units else 'GREEDY'}\n")
                                _f.write("=== END DIAG ===\n\n")
                        # === END DIAGNOSTIC ===

                        if optimized_typeset_units:
                            typeset_units = optimized_typeset_units

                        # 实际应用排版结果
                        paragraph.scale = scale
                        paragraph.pdf_paragraph_composition = []
                        for unit in typeset_units:
                            chars, curves, forms = unit.render()
                            for char in chars:
                                paragraph.pdf_paragraph_composition.append(
                                    PdfParagraphComposition(pdf_character=char),
                                )
                            for curve in curves:
                                page.pdf_curve.append(curve)
                            for form in forms:
                                page.pdf_form.append(form)
                        final_typeset_units = typeset_units

                        # 收缩段落 box 底部：译文可能比原文短，
                        # box.y 需要匹配实际渲染字符的底部，避免多余空白。
                        rendered_chars = [
                            c.pdf_character
                            for c in paragraph.pdf_paragraph_composition
                            if c.pdf_character
                            and c.pdf_character.box
                            and c.pdf_character.box.y is not None
                        ]
                        if rendered_chars:
                            actual_bottom = min(c.box.y for c in rendered_chars)
                            if actual_bottom > paragraph.box.y:
                                paragraph.box.y = actual_bottom

                    return scale, final_typeset_units
            except Exception:
                # 如果布局检查出错，继续尝试下一个缩放因子
                pass

            # 添加与原 retypeset 一致的逻辑检查
            if not hasattr(paragraph, "debug_id") or not paragraph.debug_id:
                # 如果 apply_layout 且尚未成功布局，不要提前返回
                # 否则调用者已清空 pdf_paragraph_composition 会导致空渲染
                if not apply_layout or final_typeset_units is not None:
                    return scale, final_typeset_units

            # Prefer expanding the box before crushing font size.
            # Order: right first (short EN titles → longer CJK), then down.
            # Trigger expansion as soon as scale drops below ~full size, not
            # only after scale < 0.7 (that was too late for "Edging"-class titles).
            if expand_space_flag < 2 and scale >= 0.85:
                space_expanded = False

                if expand_space_flag == 0:
                    # Expand right first
                    try:
                        max_x = self.get_max_right_space(box, page) - 5
                        if max_x > box.x2 + 1:
                            expanded_box = Box(x=box.x, y=box.y, x2=max_x, y2=box.y2)
                            box = expanded_box
                            if apply_layout:
                                paragraph.box = expanded_box
                            space_expanded = True
                    except Exception:
                        pass
                    expand_space_flag = 1
                    if space_expanded:
                        scale = initial_scale  # retry at full size with wider box
                        continue

                elif expand_space_flag == 1:
                    # Then expand downward
                    try:
                        min_y = self.get_max_bottom_space(box, page) + 2
                        if min_y < box.y:
                            expanded_box = Box(x=box.x, y=min_y, x2=box.x2, y2=box.y2)
                            box = expanded_box
                            if apply_layout:
                                paragraph.box = expanded_box
                            space_expanded = True
                    except Exception:
                        pass
                    expand_space_flag = 2
                    if space_expanded:
                        scale = initial_scale
                        continue

            # 减小缩放因子
            if scale > 0.6:
                scale -= 0.05
            else:
                scale -= 0.1

            # Late expansion fallback (legacy path) if early expand was skipped
            if scale < 0.7 and expand_space_flag < 2:
                space_expanded = False
                if expand_space_flag == 0:
                    try:
                        max_x = self.get_max_right_space(box, page) - 5
                        if max_x > box.x2 + 1:
                            expanded_box = Box(x=box.x, y=box.y, x2=max_x, y2=box.y2)
                            box = expanded_box
                            if apply_layout:
                                paragraph.box = expanded_box
                            space_expanded = True
                    except Exception:
                        pass
                    expand_space_flag = 1
                    if space_expanded:
                        scale = initial_scale
                        continue
                elif expand_space_flag == 1:
                    try:
                        min_y = self.get_max_bottom_space(box, page) + 2
                        if min_y < box.y:
                            expanded_box = Box(x=box.x, y=min_y, x2=box.x2, y2=box.y2)
                            box = expanded_box
                            if apply_layout:
                                paragraph.box = expanded_box
                            space_expanded = True
                    except Exception:
                        pass
                    expand_space_flag = 2
                    if space_expanded:
                        scale = initial_scale
                        continue

        # 如果仍然放不下，尝试去除英文换行限制
        if use_english_line_break:
            return self._find_optimal_scale_and_layout_inner(
                paragraph,
                page,
                typesetting_units,
                initial_scale,
                use_english_line_break=False,
                apply_layout=apply_layout,
                line_skip=line_skip,
            )

        # One more try: drop all figure exclusion zones and re-search.
        # Needle-thin residual strips (or false figures) can still leave text
        # unfittable at MIN_READABLE_SCALE; full width is better than empty.
        if (
            not getattr(self, "_drop_all_figures_for_paragraph", False)
            and getattr(self, "_current_zone_index", None) is not None
            and any(
                z.kind == "figure"
                for z in (self._current_zone_index.zones or [])
            )
        ):
            logger.debug(
                "Scale floor reached with figure zones still active; "
                "retrying without figure exclusion for this paragraph"
            )
            self._drop_all_figures_for_paragraph = True
            try:
                # Re-enter outer wrapper so filter_for_paragraph runs again
                return self._find_optimal_scale_and_layout(
                    paragraph,
                    page,
                    typesetting_units,
                    initial_scale,
                    use_english_line_break=True,
                    apply_layout=apply_layout,
                    line_skip=line_skip,
                )
            finally:
                self._drop_all_figures_for_paragraph = False

        # Force-apply at readable floor even if text overflows the box.
        # Never leave composition empty after apply_layout cleared it.
        if apply_layout and final_typeset_units is None:
            force_units = last_typeset_units
            if not force_units:
                force_units, _ = self._layout_typesetting_units(
                    typesetting_units,
                    box,
                    min_scale,
                    line_skip,
                    paragraph,
                    use_english_line_break=False,
                    reference_widths=self._extract_original_line_widths(paragraph),
                )
            if force_units:
                paragraph.scale = min_scale
                paragraph.pdf_paragraph_composition = []
                for unit in force_units:
                    chars, curves, forms = unit.render()
                    for char in chars:
                        paragraph.pdf_paragraph_composition.append(
                            PdfParagraphComposition(pdf_character=char),
                        )
                    for curve in curves:
                        page.pdf_curve.append(curve)
                    for form in forms:
                        page.pdf_form.append(form)
                final_typeset_units = force_units
                logger.warning(
                    "Applied layout at min readable scale %.2f with possible "
                    "overflow (paragraph debug_id=%s)",
                    min_scale,
                    getattr(paragraph, "debug_id", None),
                )

        return min_scale, final_typeset_units

    @staticmethod
    def _resolve_effective_alignment(
        paragraph: il_version_1.PdfParagraph,
        typesetting_units: list[TypesettingUnit] | None = None,
    ) -> str:
        """Return alignment to use for layout; never center long body text.

        Detection can mis-label multi-line body as center when InDesign
        geometry is noisy (Orgasms p.11 step-one body). Long translated
        paragraphs and near-full original line widths are forced left.
        """
        alignment = getattr(paragraph, "alignment", None) or "left"
        if alignment != "center":
            return alignment

        text = paragraph.unicode or ""
        # Substantial prose → body, not a centered title/quote
        if len(text.strip()) >= 36:
            return "left"

        rm = getattr(paragraph, "reference_metrics", None)
        box = paragraph.box
        if rm and box and getattr(rm, "avg_line_width", None):
            box_w = (box.x2 - box.x) if box.x2 is not None and box.x is not None else 0
            if box_w > 0 and rm.avg_line_width >= box_w * 0.7:
                return "left"

        if typesetting_units and len(typesetting_units) >= 36:
            return "left"

        return alignment

    @staticmethod
    def _effective_first_line_indent(
        paragraph: il_version_1.PdfParagraph,
        box: Box,
        available_x: float,
        available_x2: float,
        scale: float,
        typesetting_units: list[TypesettingUnit],
    ) -> float:
        """First-line indent in user space, capped so the first line stays usable.

        Prevents pathological indents (or indent + zone) from leaving only one
        CJK glyph on the first line (Orgasms p.12 title-style breaks).
        """
        raw = float(paragraph.first_line_indent or 0.0)
        if raw <= 0:
            return 0.0

        indent = raw * scale
        line_left = max(available_x, box.x + indent)
        remain = available_x2 - line_left
        # Target: room for at least ~4 glyphs at current scale
        unit_ws = [
            float(u.width or 0) * scale
            for u in (typesetting_units or [])[:8]
            if not getattr(u, "is_space", False)
        ]
        glyph = statistics.median(unit_ws) if unit_ws else 12.0 * scale
        min_remain = max(28.0 * scale, glyph * 4.0)
        if remain >= min_remain:
            return indent

        # Shrink or drop indent to keep a usable first line
        max_indent = available_x2 - available_x - min_remain
        if max_indent <= 0:
            return 0.0
        return max(0.0, min(indent, max_indent))

    def _pre_expand_narrow_box(
        self,
        box: Box,
        paragraph: il_version_1.PdfParagraph,
        page: il_version_1.Page,
        typesetting_units: list[TypesettingUnit],
        apply_layout: bool,
    ) -> Box:
        """Widen a tight original box when translated content is much longer.

        Classic case: English section heading "Edging" (~50pt wide) translates
        to "边缘控制（Edging）" which needs ~120pt+ at full size. Fitting the
        original box forces scale ~0.5 and ugly mid-word line breaks.
        """
        if not box or not typesetting_units:
            return box

        box_w = (box.x2 - box.x) if box.x2 is not None and box.x is not None else 0
        if box_w <= 0:
            return box

        # Estimate total content width at scale=1.0 (no wrapping)
        content_w = 0.0
        for u in typesetting_units:
            try:
                content_w += float(u.width or 0)
            except Exception:
                pass

        text = (paragraph.unicode or "").strip()
        label = (getattr(paragraph, "layout_label", None) or "").lower()
        # Short headings: expand sooner (1.15x). Body needs clearer overflow
        # (1.5x) so normal paragraphs are not stretched.
        is_short_heading = len(text) <= 40 or (
            label in ("title", "section_header") and len(text) <= 48
        )
        ratio_need = 1.15 if is_short_heading else 1.5
        if content_w < box_w * ratio_need:
            return box

        try:
            max_x = self.get_max_right_space(box, page) - 5
        except Exception:
            return box

        if max_x <= box.x2 + 1:
            return box

        expanded = Box(x=box.x, y=box.y, x2=max_x, y2=box.y2)
        logger.debug(
            "Pre-expanded narrow paragraph box: width %.1f → %.1f (content≈%.1f) text=%r",
            box_w,
            max_x - box.x,
            content_w,
            (paragraph.unicode or "")[:40],
        )
        if apply_layout:
            paragraph.box = expanded
        return expanded

    def _get_optimal_scale(
        self,
        paragraph: il_version_1.PdfParagraph,
        page: il_version_1.Page,
        typesetting_units: list[TypesettingUnit],
        use_english_line_break: bool = True,
        line_skip: float | None = None,
    ) -> float:
        """获取段落的最优缩放因子，不执行实际排版"""
        scale, _ = self._find_optimal_scale_and_layout(
            paragraph,
            page,
            typesetting_units,
            1.0,
            use_english_line_break,
            apply_layout=False,
            line_skip=line_skip,
        )
        return scale

    def retypeset_with_precomputed_scale(
        self,
        paragraph: il_version_1.PdfParagraph,
        page: il_version_1.Page,
        typesetting_units: list[TypesettingUnit],
        precomputed_scale: float,
        use_english_line_break: bool = True,
        line_skip: float | None = None,
    ):
        """使用预计算的缩放因子进行排版"""
        if not paragraph.box:
            return

        # 使用通用方法进行排版，传入预计算的缩放因子作为初始值
        self._find_optimal_scale_and_layout(
            paragraph,
            page,
            typesetting_units,
            precomputed_scale,
            use_english_line_break,
            apply_layout=True,
            line_skip=line_skip,
        )

    def typesetting_document(self, document: il_version_1.Document):
        from babeldoc.format.pdf.document_il.midend.exclusion_zone import (
            ExclusionZoneBuilder,
            ExclusionZoneIndex,
        )

        # 预先构建每页的排除区域缓存，避免重复构建
        self._page_zone_cache: dict[int, ExclusionZoneIndex | None] = {}
        for page in document.page:
            zones = ExclusionZoneBuilder.build(page)
            self._page_zone_cache[id(page)] = (
                ExclusionZoneIndex(zones) if zones else None
            )

        # 原有的排版逻辑
        if self.translation_config.progress_monitor:
            with self.translation_config.progress_monitor.stage_start(
                self.stage_name,
                len(document.page) * 2,
            ) as pbar:
                # 预处理：获取所有段落的最优缩放因子
                self.preprocess_document(document, pbar, build_zone_index=True)

                for page in document.page:
                    self.translation_config.raise_if_cancelled()
                    self._current_zone_index = self._page_zone_cache.get(id(page))
                    self.render_page(page)
                    pbar.advance()
        else:
            self.preprocess_document(document, None, build_zone_index=True)
            for page in document.page:
                self.translation_config.raise_if_cancelled()
                self._current_zone_index = self._page_zone_cache.get(id(page))
                self.render_page(page)

        # 清理缓存
        self._page_zone_cache.clear()

    def _collect_fonts_for_page(
        self, page: il_version_1.Page
    ) -> dict[str | int, il_version_1.PdfFont | dict[str, il_version_1.PdfFont]]:
        """提取自 render_page，供渲染主流程和重叠修正流程复用。"""
        fonts: dict[
            str | int,
            il_version_1.PdfFont | dict[str, il_version_1.PdfFont],
        ] = {f.font_id: f for f in page.pdf_font if f.font_id}
        page_fonts = {f.font_id: f for f in page.pdf_font if f.font_id}
        for k, v in self.font_mapper.fontid2font.items():
            fonts[k] = v
        for xobj in page.pdf_xobject:
            if xobj.xobj_id is not None:
                fonts[xobj.xobj_id] = page_fonts.copy()
                for font in xobj.pdf_font:
                    if font.font_id:
                        fonts[xobj.xobj_id][font.font_id] = font
        return fonts

    def retypeset_paragraph(
        self,
        paragraph: il_version_1.PdfParagraph,
        page: il_version_1.Page,
        line_skip: float | None = None,
    ) -> bool:
        """重新排版单个段落（异常安全，自动回滚）。

        用于 PostLayoutProcessor 的 OverlapFixer。
        Returns: True 成功，False 失败（已回滚）。
        """
        old_compositions = paragraph.pdf_paragraph_composition[:]
        # 保存并恢复 zone_index，确保使用目标页面的 zones
        old_zone_index = getattr(self, "_current_zone_index", None)
        try:
            from babeldoc.format.pdf.document_il.midend.exclusion_zone import (
                ExclusionZoneBuilder,
                ExclusionZoneIndex,
            )
            zones = ExclusionZoneBuilder.build(page)
            self._current_zone_index = (
                ExclusionZoneIndex(zones) if zones else None
            )

            fonts = self._collect_fonts_for_page(page)
            typesetting_units = self.create_typesetting_units(paragraph, fonts)
            precomputed_scale = paragraph.optimal_scale or 1.0
            paragraph.pdf_paragraph_composition = []
            self.retypeset_with_precomputed_scale(
                paragraph, page, typesetting_units, precomputed_scale,
                line_skip=line_skip,
            )
            self._update_paragraph_render_order(paragraph)
            return True
        except Exception:
            paragraph.pdf_paragraph_composition = old_compositions
            logger.warning(
                f"Failed to retypeset paragraph, rolled back."
            )
            return False
        finally:
            self._current_zone_index = old_zone_index

    def retypeset_with_scale_range(
        self,
        paragraph: il_version_1.PdfParagraph,
        page: il_version_1.Page,
        min_scale: float | None = None,
        max_scale: float = 1.0,
        line_skip: float | None = None,
    ) -> RetypesetResult:
        """Re-typeset with bidirectional scale search.

        Unlike retypeset_with_precomputed_scale which only searches DOWNWARD
        from initial_scale, this method searches the full [min_scale, max_scale]
        range to find the LARGEST scale where all text fits in the box.

        This is critical when box has been EXPANDED — the old optimal_scale
        may be too small, and the current search strategy would never discover
        that a larger scale is now possible.

        Returns RetypesetResult with success flag, best_scale, and reason.
        """
        if not paragraph.box:
            return RetypesetResult(success=False, reason="no box")

        if min_scale is None:
            min_scale = self.MIN_READABLE_SCALE

        old_compositions = paragraph.pdf_paragraph_composition[:]
        old_scale = getattr(paragraph, 'scale', None)
        old_box = paragraph.box
        try:
            fonts = self._collect_fonts_for_page(page)
            typesetting_units = self.create_typesetting_units(paragraph, fonts)
            if not typesetting_units:
                return RetypesetResult(success=False, reason="no typesetting units")

            if line_skip is None:
                line_skip = self._DEFAULT_LINE_SKIP_CJK if self.is_cjk else self._DEFAULT_LINE_SKIP_NON_CJK

            # Binary search for the largest scale where all text fits
            best_scale = None
            lo, hi = min_scale, max_scale

            while hi - lo > 0.02:
                mid = (lo + hi) / 2
                typeset_units, all_fit = self._layout_typesetting_units(
                    typesetting_units, paragraph.box, mid, line_skip, paragraph,
                )
                if all_fit:
                    best_scale = mid
                    lo = mid  # try larger
                else:
                    hi = mid  # try smaller

            # If no scale fits, try the minimum
            if best_scale is None:
                _, all_fit = self._layout_typesetting_units(
                    typesetting_units, paragraph.box, min_scale, line_skip, paragraph,
                )
                if all_fit:
                    best_scale = min_scale
                else:
                    # Even min_scale doesn't fit — fall back to downward search
                    # which handles box expansion
                    paragraph.pdf_paragraph_composition = []
                    self.retypeset_with_precomputed_scale(
                        paragraph, page, typesetting_units, max_scale,
                        line_skip=line_skip,
                    )
                    self._update_paragraph_render_order(paragraph)
                    # Read actual applied scale (set by _find_optimal_scale_and_layout)
                    actual_scale = getattr(paragraph, 'scale', None) or max_scale
                    return RetypesetResult(
                        success=True, best_scale=actual_scale,
                        reason="fallback to downward search with box expansion",
                    )

            # Apply layout with the best scale
            paragraph.pdf_paragraph_composition = []
            self._find_optimal_scale_and_layout(
                paragraph, page, typesetting_units, best_scale,
                apply_layout=True, line_skip=line_skip,
            )
            self._update_paragraph_render_order(paragraph)
            return RetypesetResult(success=True, best_scale=best_scale)

        except Exception:
            paragraph.pdf_paragraph_composition = old_compositions
            paragraph.scale = old_scale
            paragraph.box = old_box
            logger.warning(
                "Failed to retypeset paragraph with scale range, rolled back."
            )
            return RetypesetResult(success=False, reason="exception during retypeset")

    def render_page(self, page: il_version_1.Page):
        fonts = self._collect_fonts_for_page(page)
        if (
            page.page_number == 0
            and self.translation_config.watermark_output_mode
            == WatermarkOutputMode.Watermarked
        ):
            self.add_watermark(page)
        try:
            para_index = index.Index()
            para_map = {}
            #
            valid_paras = [
                p
                for p in page.pdf_paragraph
                if p.box
                and all(c is not None for c in [p.box.x, p.box.y, p.box.x2, p.box.y2])
            ]

            for i, para in enumerate(valid_paras):
                para_map[i] = para
                para_index.insert(i, box_to_tuple(para.box))

            for i, p_upper in para_map.items():
                if not (p_upper.box and p_upper.box.y is not None):
                    continue

                # Calculate paragraph height and set required gap accordingly
                para_height = p_upper.box.y2 - p_upper.box.y
                required_gap = 0.5 if para_height < 36 else 3

                check_area = il_version_1.Box(
                    x=p_upper.box.x,
                    y=p_upper.box.y - required_gap,
                    x2=p_upper.box.x2,
                    y2=p_upper.box.y,
                )

                candidate_ids = list(para_index.intersection(box_to_tuple(check_area)))

                conflicting_paras = []
                for para_id in candidate_ids:
                    if para_id == i:
                        continue
                    p_lower = para_map[para_id]
                    if not (
                        p_lower.box
                        and p_upper.box
                        and p_lower.box.x2 < p_upper.box.x
                        or p_lower.box.x > p_upper.box.x2
                    ):
                        conflicting_paras.append(p_lower)

                if conflicting_paras:
                    max_y2 = max(
                        p.box.y2
                        for p in conflicting_paras
                        if p.box and p.box.y2 is not None
                    )

                    new_y = max_y2 + required_gap
                    if p_upper.box and new_y < p_upper.box.y2:
                        p_upper.box.y = new_y
        except Exception as e:
            logger.warning(
                f"Failed to adjust paragraph positions on page {page.page_number}: {e}"
            )
        # 开始实际的渲染过程
        for paragraph in page.pdf_paragraph:
            self.render_paragraph(paragraph, page, fonts)

        # 译文排版完成后，基于「实际渲染结果」再做一次完整的二维重叠检测与修正。
        # 上面的 rtree 检测只能发现「紧贴边缘」的重叠（正文与正文首尾相接的场景），
        # 无法发现引用框/侧栏这类嵌在段落中段、与正文左右或纵向大范围重叠的情况——
        # 这类重叠是中文行距（1.5x）比英文（1.3x）更高、导致译文比原文占用更多纵向
        # 空间后才会出现的，必须在译文实际排版完成后才能检测到。
        try:
            self.fix_overlapping_paragraphs_post_typesetting(page)
        except Exception as e:
            logger.warning(
                f"Failed to fix post-typesetting paragraph overlaps on page "
                f"{page.page_number}: {e}"
            )

    def _recompute_rendered_box(
        self, paragraph: il_version_1.PdfParagraph
    ) -> Box | None:
        """根据段落译文渲染后的真实字符位置，重新计算紧密包围盒。

        算法与 paragraph_finder.py 的 update_paragraph_data() 一致，
        但作用对象是「译文排版完成后」的 pdf_paragraph_composition，
        而不是原文字符——用来发现因中文行距更高而产生的新增重叠。
        """
        chars = []
        for composition in paragraph.pdf_paragraph_composition or []:
            if composition.pdf_character:
                chars.append(composition.pdf_character)
            elif composition.pdf_line:
                chars.extend(composition.pdf_line.pdf_character)
            elif composition.pdf_formula:
                chars.extend(composition.pdf_formula.pdf_character)
            elif composition.pdf_same_style_characters:
                chars.extend(composition.pdf_same_style_characters.pdf_character)
            # pdf_same_style_unicode_characters 无 pdf_character 字段，跳过

        chars = [
            c
            for c in chars
            if c.box is not None
            and c.box.x is not None
            and c.box.y is not None
            and c.box.x2 is not None
            and c.box.y2 is not None
        ]
        if not chars:
            return None

        min_x = min(c.box.x for c in chars)
        min_y = min(c.box.y for c in chars)
        max_x = max(c.box.x2 for c in chars)
        max_y = max(c.box.y2 for c in chars)
        return Box(x=min_x, y=min_y, x2=max_x, y2=max_y)

    @staticmethod
    def _bbox_overlap(b1: Box, b2: Box) -> bool:
        return b1.x < b2.x2 and b1.x2 > b2.x and b1.y < b2.y2 and b1.y2 > b2.y

    @staticmethod
    def _is_bbox_contain_in_vertical(b1: Box, b2: Box) -> bool:
        b1_in_b2 = b1.y > b2.y and b1.y2 < b2.y2
        b2_in_b1 = b2.y > b1.y and b2.y2 < b1.y2
        return b1_in_b2 or b2_in_b1

    def fix_overlapping_paragraphs_post_typesetting(self, page: il_version_1.Page):
        """译文排版完成后，对实际渲染结果做完整的二维重叠检测与修正。

        发现重叠时不能像 paragraph_finder 那样简单挪动 box.y——译文字符已经
        画出来了。这里的策略是：保留 render_order 更靠前的段落不动，收缩
        render_order 更靠后的段落的可用高度，再用它已经算好的 optimal_scale
        重新排版一次（自动降低缩放/换行来避开冲突区域）。
        """
        paragraphs = [p for p in page.pdf_paragraph if p.pdf_paragraph_composition]
        if len(paragraphs) < 2:
            return

        rendered_boxes: dict[int, Box] = {}
        for p in paragraphs:
            box = self._recompute_rendered_box(p)
            if box is not None:
                rendered_boxes[id(p)] = box

        max_iterations = getattr(
            self.translation_config, "post_layout_max_iterations", 3
        )
        for _ in range(max_iterations):
            overlap_found = False

            for i in range(len(paragraphs)):
                for j in range(i + 1, len(paragraphs)):
                    p1, p2 = paragraphs[i], paragraphs[j]
                    if p1.xobj_id != p2.xobj_id:
                        continue
                    b1 = rendered_boxes.get(id(p1))
                    b2 = rendered_boxes.get(id(p2))
                    if b1 is None or b2 is None:
                        continue
                    if not self._bbox_overlap(b1, b2):
                        continue
                    if self._is_bbox_contain_in_vertical(b1, b2):
                        continue

                    overlap_found = True

                    if (p1.render_order or 0) <= (p2.render_order or 0):
                        keep_box, shrink, shrink_box = b1, p2, b2
                    else:
                        keep_box, shrink, shrink_box = b2, p1, b1

                    if shrink.box is None:
                        continue

                    if shrink_box.y < keep_box.y2:
                        # shrink 段落在 keep 段落之下 → 收缩 shrink 顶部
                        new_y2 = keep_box.y - 1
                        if new_y2 > shrink.box.y:
                            shrink.box = Box(
                                x=shrink.box.x,
                                y=shrink.box.y,
                                x2=shrink.box.x2,
                                y2=new_y2,
                            )
                    elif shrink_box.y2 > keep_box.y2:
                        # shrink 段落在 keep 段落之上 → 收缩 shrink 底部
                        new_y = keep_box.y2 + 1
                        if new_y < (shrink.box.y2 or float("inf")):
                            shrink.box = Box(
                                x=shrink.box.x,
                                y=new_y,
                                x2=shrink.box.x2,
                                y2=shrink.box.y2,
                            )
                        else:
                            continue
                    else:
                        continue

                    # 重新排版（异常安全：保存旧 composition 以便恢复）
                    old_compositions = shrink.pdf_paragraph_composition[:]
                    try:
                        fonts = self._collect_fonts_for_page(page)
                        typesetting_units = self.create_typesetting_units(
                            shrink, fonts
                        )
                        precomputed_scale = shrink.optimal_scale or 1.0
                        shrink.pdf_paragraph_composition = []
                        self.retypeset_with_precomputed_scale(
                            shrink, page, typesetting_units, precomputed_scale
                        )
                        self._update_paragraph_render_order(shrink)
                        new_box = self._recompute_rendered_box(shrink)
                        if new_box is not None:
                            rendered_boxes[id(shrink)] = new_box
                    except Exception:
                        shrink.pdf_paragraph_composition = old_compositions
                        logger.warning(
                            f"Page {page.page_number}: 段落重新排版失败，"
                            "已恢复原始 composition。"
                        )

            if not overlap_found:
                break
        else:
            logger.warning(
                f"Page {page.page_number}: 重叠修正达到最大迭代次数，"
                "可能仍存在未解决的重叠。"
            )

    def add_watermark(self, page: il_version_1.Page):
        page_width = page.cropbox.box.x2 - page.cropbox.box.x
        page_height = page.cropbox.box.y2 - page.cropbox.box.y
        style = il_version_1.PdfStyle(
            font_id="base",
            font_size=6,
            graphic_state=il_version_1.GraphicState(),
        )
        text = f"本文档由 funstory.ai 的开源 PDF 翻译库 BabelDOC {WATERMARK_VERSION} (https://github.com/funstory-ai/BabelDOC) 翻译，本仓库正在积极的建设当中，欢迎 star 和关注。"
        if self.translation_config.debug:
            text += "\n 当前为 DEBUG 模式，将显示更多辅助信息。请注意，部分框的位置对应原文，但在译文中可能不正确。"
        page.pdf_paragraph.append(
            il_version_1.PdfParagraph(
                first_line_indent=0.0,
                box=il_version_1.Box(
                    x=page.cropbox.box.x + page_width * 0.05,
                    y=page.cropbox.box.y,
                    x2=page.cropbox.box.x2,
                    y2=page.cropbox.box.y2 - page_height * 0.05,
                ),
                vertical=False,
                pdf_style=style,
                pdf_paragraph_composition=[
                    il_version_1.PdfParagraphComposition(
                        pdf_same_style_unicode_characters=il_version_1.PdfSameStyleUnicodeCharacters(
                            unicode=text,
                            pdf_style=style,
                        ),
                    ),
                ],
                xobj_id=-1,
            ),
        )

    def render_paragraph(
        self,
        paragraph: il_version_1.PdfParagraph,
        page: il_version_1.Page,
        fonts: dict[
            str | int,
            il_version_1.PdfFont | dict[str, il_version_1.PdfFont],
        ],
    ):
        # 诊断：记录原版段落的行结构
        rm = getattr(paragraph, 'reference_metrics', None)
        if rm:
            logger.debug(
                f"Original paragraph: {rm.line_count} lines, "
                f"avg_width={rm.avg_line_width:.1f}, "
                f"per_line_widths={[f'{w:.1f}' for w in (rm.per_line_widths or [])]}, "
                f"box=[{paragraph.box.x:.1f},{paragraph.box.y:.1f}]-[{paragraph.box.x2:.1f},{paragraph.box.y2:.1f}]"
                if paragraph.box else
                f"Original paragraph: {rm.line_count} lines, no box"
            )

        typesetting_units = self.create_typesetting_units(paragraph, fonts)
        # 如果所有单元都可以直接传递，则直接传递
        if all(unit.can_passthrough for unit in typesetting_units):
            paragraph.scale = 1.0
            paragraph.pdf_paragraph_composition = self.create_passthrough_composition(
                typesetting_units,
            )
        else:
            # 使用预计算的缩放因子进行重排版
            precomputed_scale = (
                paragraph.optimal_scale if paragraph.optimal_scale is not None else 1.0
            )

            # 如果有单元无法直接传递，则进行重排版
            paragraph.pdf_paragraph_composition = []
            self.retypeset_with_precomputed_scale(
                paragraph, page, typesetting_units, precomputed_scale
            )

            # 重排版后，重新设置段落各字符的 render order
            self._update_paragraph_render_order(paragraph)

    def _get_width_before_next_break_point(
        self, typesetting_units: list[TypesettingUnit], scale: float
    ) -> float:
        if not typesetting_units:
            return 0
        if typesetting_units[0].can_break_line:
            return 0

        total_width = 0
        for unit in typesetting_units:
            if unit.can_break_line:
                return total_width * scale
            total_width += unit.width
        return total_width * scale

    @staticmethod
    def _extract_original_line_widths(paragraph: il_version_1.PdfParagraph) -> list[float]:
        """从原版段落提取每行的宽度。

        优先从 reference_metrics（翻译前缓存）获取，
        回退到从 compositions 提取（翻译前调用时有效）。
        """
        # 优先使用翻译前缓存的 reference_metrics
        rm = getattr(paragraph, 'reference_metrics', None)
        if rm and rm.per_line_widths:
            return rm.per_line_widths

        # 回退：从 compositions 提取（仅在翻译前有效）
        widths = []
        for comp in paragraph.pdf_paragraph_composition or []:
            if comp.pdf_line and comp.pdf_line.box:
                w = comp.pdf_line.box.x2 - comp.pdf_line.box.x
                if w > 0:
                    widths.append(w)
        return widths

    def _estimate_line_widths(
        self,
        typesetting_units: list[TypesettingUnit],
        box: Box,
        scale: float,
        avg_height: float,
        line_skip: float,
        reference_widths: list[float] | None = None,
    ) -> list[float]:
        """估算每行的可用宽度（用于 DP 断行优化的近似值）。

        如果提供 reference_widths（原版行宽），则优先使用原版行宽作为目标，
        同时尊重 ExclusionZone 约束（取两者中较小值）。

        否则用 avg_height 步进 Y 位置，查询 ExclusionZone 得到每行可用宽度。
        """
        zone_index = getattr(self, "_current_zone_index", None)
        widths = []

        # 用段落中最高的 unit 修正查询高度
        max_unit_height = avg_height
        for u in typesetting_units:
            h = u.height * scale
            if h > max_unit_height:
                max_unit_height = h
        query_h = max(max_unit_height, avg_height)

        y = box.y2 - avg_height
        line_idx = 0
        while y > box.y:
            # 获取 zone 约束的宽度
            if zone_index and query_h > 0:
                x1, x2 = zone_index.get_available_x_range(
                    y, y + query_h, box.x, box.x2
                )
                if x1 >= x2:
                    x1, x2 = box.x, box.x2
            else:
                x1, x2 = box.x, box.x2
            zone_width = x2 - x1

            # Prefer original line widths (artistic taper around photos).
            # Extra CJK lines reuse median EN width — never fall back to full
            # page width when refs exist (that spilled text across p.8 photo).
            if reference_widths:
                ref_w = Typesetting._pick_reference_width(
                    reference_widths, line_idx
                )
                if ref_w is not None and ref_w >= 12.0:
                    width = min(ref_w, zone_width)
                else:
                    width = zone_width
            else:
                width = zone_width

            widths.append(width)
            y -= max(avg_height * line_skip, max_unit_height * 1.05)
            line_idx += 1

        return widths

    def _compute_optimal_breaks(
        self,
        typesetting_units: list[TypesettingUnit],
        box: Box,
        scale: float,
        avg_height: float,
        line_skip: float,
        space_width: float,
        decorative_tracking: float,
        reference_widths: list[float] | None = None,
    ) -> list[int] | None:
        """计算 DP 优化的断行位置。失败时返回 None。"""
        line_widths = self._estimate_line_widths(
            typesetting_units, box, scale, avg_height, line_skip,
            reference_widths=reference_widths,
        )
        if not line_widths:
            return None

        return optimal_line_break(
            units=typesetting_units,
            line_widths=line_widths,
            scale=scale,
            space_width=space_width,
            decorative_tracking=decorative_tracking,
        )

    @staticmethod
    def _pick_reference_width(
        reference_widths: list[float], line_idx: int
    ) -> float | None:
        """Pick EN line width for this layout line; median for overflow lines.

        Ignores only *absolutely* tiny refs (< 12pt), which are usually
        decorative digits — never treat a real wrap column (~120–220pt) as
        pathological just because the available box is page-wide (that bug
        made Orgasms p.8 Chinese lines spill across the side photo).
        """
        if not reference_widths:
            return None
        usable = [w for w in reference_widths if w >= 12.0]
        if not usable:
            usable = list(reference_widths)
        if line_idx < len(reference_widths) and reference_widths[line_idx] >= 12.0:
            return reference_widths[line_idx]
        return float(statistics.median(usable))

    @staticmethod
    def _cap_available_with_reference(
        box: Box,
        available_x: float,
        available_x2: float,
        reference_widths: list[float] | None,
        line_idx: int,
    ) -> tuple[float, float]:
        """Cap line right edge using original EN line widths (artistic taper).

        Extra lines past the EN count reuse the median reference width so CJK
        does not spill a full rectangular column into a photo.
        """
        if not reference_widths:
            return available_x, available_x2
        zone_w = available_x2 - available_x
        if zone_w <= 0:
            return available_x, available_x2

        ref_w = Typesetting._pick_reference_width(reference_widths, line_idx)
        if ref_w is None or ref_w < 12.0:
            return available_x, available_x2

        # Always prefer EN line width when it is a usable column. Do NOT skip
        # when ref_w << zone_w — after dropping artistic figure zones the
        # "zone" is often the full page width while EN lines stay ~150–220pt.
        cap_x2 = min(available_x2, box.x + ref_w)
        # Hard ceiling: never wider than the longest original line (+slack)
        max_ref = max(w for w in reference_widths if w >= 12.0) if any(
            w >= 12.0 for w in reference_widths
        ) else max(reference_widths)
        cap_x2 = min(cap_x2, box.x + max_ref * 1.15)

        if cap_x2 >= available_x + 8:
            return available_x, cap_x2
        return available_x, available_x2

    def _layout_typesetting_units(
        self,
        typesetting_units: list[TypesettingUnit],
        box: Box,
        scale: float,
        line_skip: float,
        paragraph: il_version_1.PdfParagraph,
        use_english_line_break: bool = True,
        break_points: list[int] | None = None,
        reference_widths: list[float] | None = None,
    ) -> tuple[list[TypesettingUnit], bool]:
        """布局排版单元。

        Args:
            typesetting_units: 要布局的排版单元列表
            box: 布局边界框
            scale: 缩放因子
            break_points: 可选的预计算断行位置列表（DP 优化结果）。
                         提供时在指定位置强制断行，否则使用贪心断行。
            reference_widths: 原版每行宽度；用于复现绕图的变宽行形。

        Returns:
            tuple[list[TypesettingUnit], bool]: (已布局的排版单元列表，是否所有单元都放得下)
        """
        # 预处理 break_points：转为 set 以加速 O(1) 查找
        if break_points is not None and not isinstance(break_points, set):
            break_points = set(break_points)
        if reference_widths is None:
            reference_widths = self._extract_original_line_widths(paragraph)
        layout_line_idx = 0

        # === DIAGNOSTIC: 写入独立 log 文件 ===
        _diag_text = paragraph.unicode or ""
        if "在这些" in _diag_text:
            import os as _os
            _diag_path = _os.environ.get("BABELDOC_DIAG_LOG", "/tmp/babeldoc_diag.log")
            with open(_diag_path, "a", encoding="utf-8") as _f:
                _f.write("=== DIAG typesetting_units ===\n")
                _f.write(f"  debug_id={getattr(paragraph, 'debug_id', None)}\n")
                _f.write(f"  unicode={_diag_text!r}\n")
                _f.write(f"  box=[{box.x:.1f},{box.y:.1f}]-[{box.x2:.1f},{box.y2:.1f}]\n")
                _f.write(f"  scale={scale}\n")
                _f.write(f"  break_points={break_points}\n")
                for _di, _du in enumerate(typesetting_units):
                    _du_unicode = _du.try_get_unicode() or "?"
                    _f.write(
                        f"  Unit[{_di}]: unicode={_du_unicode!r}, "
                        f"width={_du.width:.2f}, "
                        f"is_cjk={_du.is_cjk_char}, "
                        f"can_break={_du.can_break_line}, "
                        f"is_space={_du.is_space}\n"
                    )
                _f.write("=== END DIAG ===\n\n")
        # === END DIAGNOSTIC ===

        # === DIAGNOSTIC: 打印 zone_index 中的 zones ===
        if "在这些" in (paragraph.unicode or ""):
            _zone_index = getattr(self, "_current_zone_index", None)
            import os as _os
            _diag_path = _os.environ.get("BABELDOC_DIAG_LOG", "/tmp/babeldoc_diag.log")
            with open(_diag_path, "a", encoding="utf-8") as _f:
                _f.write("=== DIAG zone_index ===\n")
                if _zone_index and _zone_index.zones:
                    for _zi, _z in enumerate(_zone_index.zones):
                        _f.write(
                            f"  Zone[{_zi}]: box=[{_z.box.x:.1f},{_z.box.y:.1f}]-[{_z.box.x2:.1f},{_z.box.y2:.1f}] "
                            f"kind={_z.kind} priority={_z.priority}\n"
                        )
                else:
                    _f.write("  (no zones)\n")
                _f.write("=== END DIAG ===\n\n")
        # === END DIAGNOSTIC ===

        # 计算字号众数
        font_sizes = []
        for unit in typesetting_units:
            if unit.font_size:
                font_sizes.append(unit.font_size)
            if unit.char and unit.char.pdf_style and unit.char.pdf_style.font_size:
                font_sizes.append(unit.char.pdf_style.font_size)
        font_sizes.sort()
        try:
            font_size = statistics.mode(font_sizes)
        except statistics.StatisticsError:
            font_size = sum(font_sizes) / len(font_sizes) if font_sizes else 10.0

        space_width = (
            self.font_mapper.base_font.char_lengths("你", font_size * scale)[0] * 0.5
        )

        # 计算行高（使用众数）
        unit_heights = (
            [unit.height for unit in typesetting_units] if typesetting_units else []
        )
        if not unit_heights:
            avg_height = 0
        elif len(unit_heights) == 1:
            avg_height = unit_heights[0] * scale
        else:
            try:
                avg_height = statistics.mode(unit_heights) * scale
            except statistics.StatisticsError:
                # 如果没有众数（所有值都出现相同次数），则使用平均值
                avg_height = sum(unit_heights) / len(unit_heights) * scale

        # 初始化位置为右上角，并减去一个平均行高
        current_y = box.y2 - avg_height
        box = copy.deepcopy(box)

        # 动态行宽：查询排除区域，计算当前行的可用 x 范围
        zone_index = getattr(self, "_current_zone_index", None)
        if zone_index and zone_index.zones:
            logger.debug(
                f"Laying out paragraph with {len(zone_index.zones)} exclusion zones"
            )
        if zone_index and avg_height > 0:
            available_x, available_x2 = zone_index.get_available_x_range(
                current_y, current_y + avg_height, box.x, box.x2
            )
            # 防止反转区间（exclusion zones 从两侧收窄导致 available_x >= available_x2）
            if available_x >= available_x2:
                available_x, available_x2 = box.x, box.x2
        else:
            available_x, available_x2 = box.x, box.x2
        available_x, available_x2 = self._cap_available_with_reference(
            box, available_x, available_x2, reference_widths, layout_line_idx
        )
        current_x = available_x
        # box.y -= avg_height * (line_spacing - 1.01) # line_spacing 已被替换为 line_skip
        line_height = 0
        current_line_heights = []  # 存储当前行所有元素的高度

        # 存储已排版的单元
        typeset_units = []
        all_units_fit = True
        dp_break_mismatch = False  # DP 断行与实际行宽不匹配时置 True
        last_unit: TypesettingUnit | None = None
        line_ys = [current_y]
        # Horizontal alignment (captured from original geometry before translation)
        alignment = self._resolve_effective_alignment(paragraph, typesetting_units)
        # Index into typeset_units where the current line starts; used to shift
        # completed lines for center/right alignment after left-to-right placement.
        line_start_idx = 0
        # Track available x range for the line being built (for alignment finalize)
        line_available_x = available_x
        line_available_x2 = available_x2
        if paragraph.first_line_indent and paragraph.first_line_indent > 0:
            # 缩进相对于 box.x 而非 available_x，避免 zone 偏移叠加
            # Center/right aligned paragraphs should not apply first-line indent
            if alignment == "left":
                indent = self._effective_first_line_indent(
                    paragraph,
                    box,
                    available_x,
                    available_x2,
                    scale,
                    typesetting_units,
                )
                if indent > 0:
                    indented_x = box.x + indent
                    current_x = max(current_x, min(indented_x, available_x2))
        # 遍历所有排版单元
        # Decorative tracking: extra spacing between characters for art text
        # (e.g. "G e n t l y" → "轻 轻 地").  Scaled by the same factor as
        # the rest of the layout.
        decorative_tracking = (
            paragraph.decorative_tracking * scale
            if getattr(paragraph, "decorative_tracking", None)
            else 0
        )

        for i, unit in enumerate(typesetting_units):
            # 计算当前单元在当前缩放下的尺寸
            unit_width = unit.width * scale
            unit_height = unit.height * scale

            # 跳过行首的空格
            if current_x == available_x and unit.is_space:
                continue

            if (
                last_unit  # 有上一个单元
                and last_unit.is_cjk_char ^ unit.is_cjk_char  # 中英文交界处
                and (
                    last_unit.box
                    and last_unit.box.y
                    and current_y - 0.1
                    <= last_unit.box.y2
                    <= current_y + line_height + 0.1
                )  # 在同一行，且有垂直重叠
                and not last_unit.mixed_character_blacklist  # 不是混排空格黑名单字符
                and not unit.mixed_character_blacklist  # 同上
                and current_x > available_x  # 不是行首
                and unit.try_get_unicode() != " "  # 不是空格
                and last_unit.try_get_unicode() != " "  # 不是空格
                and last_unit.try_get_unicode()
                not in [
                    "。",
                    "！",
                    "？",
                    "；",
                    "：",
                    "，",
                ]
            ):
                current_x += space_width * 0.5
            if use_english_line_break:
                width_before_next_break_point = self._get_width_before_next_break_point(
                    typesetting_units[i:], scale
                )
            else:
                width_before_next_break_point = 0

            # 如果当前行放不下这个元素，换行
            # Include tracking in width calculation for accurate line breaks
            effective_width = unit_width + (decorative_tracking if not unit.is_space else 0)
            # DP 断行：在指定位置强制断行；否则使用贪心判断
            # DP 断行仍需检查 hung punctuation 守卫
            dp_break = (
                break_points is not None
                and i in break_points
                and not unit.is_hung_punctuation
            )
            need_break = dp_break or (
                not unit.is_hung_punctuation and (
                    (current_x + effective_width > available_x2)
                    or (
                        use_english_line_break
                        and current_x + effective_width + width_before_next_break_point > available_x2
                    )
                    or (
                        unit.is_cannot_appear_in_line_end_punctuation
                        and current_x + effective_width * 2 > available_x2
                    )
                )
            )
            # 行尾禁则：DP 断行不应将行尾禁用字符（如（【《）置于行末
            if dp_break and need_break and i > 0:
                prev_unicode = typesetting_units[i - 1].try_get_unicode()
                if prev_unicode and prev_unicode in _CJK_LINE_END_FORBIDDEN:
                    need_break = False
            # CJK 词组保护：如果当前字符在 CJK 词组内部（can_break_line=False），
            # 尝试将整个词组放在当前行。如果放不下，回退到词组起始位置换行。
            if (need_break and not dp_break and unit.is_cjk_char
                    and last_unit and last_unit.is_cjk_char
                    and not unit.can_break_line):
                # 在词组内部，尝试将剩余词组字符放在当前行
                word_end = i
                word_width = unit_width
                for k in range(i + 1, len(typesetting_units)):
                    w = typesetting_units[k]
                    if not w.is_cjk_char or w.can_break_line:
                        break
                    word_width += w.width * scale
                    word_end = k
                # 如果整个词组能放在当前行，不换行
                if current_x + word_width <= available_x2:
                    need_break = False
            # CJK 孤行保护：如果当前行只有 ≤2 个字符就要换行，
            # 标记为需要特殊处理（由 DP 在后续优化中处理）
            # 注意：不在贪心循环中强制溢出，避免布局问题
            if need_break:
                # 检测 DP 模式下贪心是否插入了额外断行
                if not dp_break and break_points is not None:
                    dp_break_mismatch = True
                # 换行
                if not current_line_heights:
                    return [], False
                max_height = max(current_line_heights)
                try:
                    mode_height = statistics.mode(current_line_heights)
                except statistics.StatisticsError:
                    mode_height = sum(current_line_heights) / len(current_line_heights)

                # Finalize horizontal alignment for the completed line
                self._apply_line_horizontal_alignment(
                    typeset_units,
                    line_start_idx,
                    len(typeset_units),
                    line_available_x,
                    line_available_x2,
                    alignment,
                )
                line_start_idx = len(typeset_units)

                current_y -= max(mode_height * line_skip, max_height * 1.05)
                line_ys.append(current_y)
                line_height = 0.0
                current_line_heights = []  # 清空当前行高度列表

                # 动态行宽：为新行计算可用 x 范围
                # 使用上一行的实际行高（max_height）而非 avg_height，避免高行遗漏 zone
                zone_query_height = max(max_height, avg_height) if max_height > 0 else avg_height
                if zone_index and zone_query_height > 0:
                    available_x, available_x2 = zone_index.get_available_x_range(
                        current_y, current_y + zone_query_height, box.x, box.x2
                    )
                    if available_x >= available_x2:
                        available_x, available_x2 = box.x, box.x2
                else:
                    available_x, available_x2 = box.x, box.x2
                layout_line_idx += 1
                available_x, available_x2 = self._cap_available_with_reference(
                    box, available_x, available_x2, reference_widths, layout_line_idx
                )
                # === DIAGNOSTIC: 每次换行时记录 available 范围 ===
                if "在这些" in (paragraph.unicode or ""):
                    _prev_chars = "".join(
                        (typesetting_units[k].try_get_unicode() or "?")
                        for k in range(max(0, i - 3), i)
                    )
                    _next_chars = "".join(
                        (typesetting_units[k].try_get_unicode() or "?")
                        for k in range(i, min(len(typesetting_units), i + 3))
                    )
                    import os as _os
                    _diag_path = _os.environ.get("BABELDOC_DIAG_LOG", "/tmp/babeldoc_diag.log")
                    with open(_diag_path, "a", encoding="utf-8") as _f:
                        _f.write(
                            f"  LINE_BREAK y={current_y:.1f} "
                            f"avail=[{available_x:.1f},{available_x2:.1f}] "
                            f"width={available_x2 - available_x:.1f} "
                            f"prev={_prev_chars!r} next={_next_chars!r}\n"
                        )
                # === END DIAGNOSTIC ===
                current_x = available_x
                line_available_x = available_x
                line_available_x2 = available_x2

                # 检查是否超出底部边界
                # if current_y - unit_height < box.y:
                if current_y < box.y:
                    all_units_fit = False
                    # 这里不要 break，继续排版剩余内容

                if unit.is_space:
                    line_height = max(line_height, unit_height)
                    continue

            # 放置当前单元
            relocated_unit = unit.relocate(current_x, current_y, scale)
            typeset_units.append(relocated_unit)

            # 更新行高（所有单元，不仅限空格），用于 CJK 混排间距判断
            line_height = max(line_height, unit_height)

            # 添加当前单元的高度到当前行高度列表
            if not unit.is_space:
                current_line_heights.append(unit_height)

            prev_x = current_x
            # 更新 x 坐标
            current_x = relocated_unit.box.x2
            # Apply decorative tracking: add extra spacing after each character
            if decorative_tracking and not unit.is_space:
                current_x += decorative_tracking
            if prev_x > current_x:
                logger.warning(f"坐标回绕！！！TypesettingUnit: {unit.box}, ")

            last_unit = relocated_unit

        # Finalize alignment for the last line
        if typeset_units and line_start_idx < len(typeset_units):
            self._apply_line_horizontal_alignment(
                typeset_units,
                line_start_idx,
                len(typeset_units),
                line_available_x,
                line_available_x2,
                alignment,
            )

        # DP 模式下如果贪心插入了额外断行，说明 DP 的行宽估算与实际不匹配，
        # 返回 all_units_fit=False 以触发回退到纯贪心布局。
        if dp_break_mismatch:
            logger.debug(
                "DP break mismatch: greedy inserted extra breaks, "
                "falling back to greedy layout."
            )
            return typeset_units, False

        return typeset_units, all_units_fit

    @staticmethod
    def _apply_line_horizontal_alignment(
        typeset_units: list[TypesettingUnit],
        start: int,
        end: int,
        available_x: float,
        available_x2: float,
        alignment: str,
    ) -> None:
        """Shift a completed line for center/right alignment.

        Units are first placed left-to-right starting at available_x.
        For center/right, compute the offset so the line sits correctly
        within [available_x, available_x2].
        """
        if alignment not in ("center", "right") or start >= end:
            return

        line_units = typeset_units[start:end]
        if not line_units:
            return

        xs = []
        x2s = []
        for u in line_units:
            b = u.box
            if b is None:
                continue
            xs.append(b.x)
            x2s.append(b.x2)
        if not xs:
            return

        line_left = min(xs)
        line_right = max(x2s)
        line_width = line_right - line_left
        avail_width = available_x2 - available_x
        if avail_width <= 0 or line_width >= avail_width - 0.5:
            return

        if alignment == "center":
            target_left = available_x + (avail_width - line_width) / 2.0
        else:  # right
            target_left = available_x2 - line_width

        offset = target_left - line_left
        if abs(offset) < 0.5:
            return

        for u in line_units:
            u.shift_x(offset)

    def create_typesetting_units(
        self,
        paragraph: il_version_1.PdfParagraph,
        fonts: dict[str, il_version_1.PdfFont],
    ) -> list[TypesettingUnit]:
        if not paragraph.pdf_paragraph_composition:
            return []
        result = []

        @cache
        def get_font(font_id: str, xobj_id: int | None):
            if xobj_id in fonts:
                font = fonts[xobj_id][font_id]
            else:
                font = fonts[font_id]
            return font

        for composition in paragraph.pdf_paragraph_composition:
            if composition is None:
                continue
            if composition.pdf_line:
                result.extend(
                    [
                        TypesettingUnit(char=char)
                        for char in composition.pdf_line.pdf_character
                    ],
                )
            elif composition.pdf_character:
                result.append(
                    TypesettingUnit(
                        char=composition.pdf_character,
                        debug_info=paragraph.debug_info,
                    ),
                )
            elif composition.pdf_same_style_characters:
                result.extend(
                    [
                        TypesettingUnit(char=char)
                        for char in composition.pdf_same_style_characters.pdf_character
                    ],
                )
            elif composition.pdf_same_style_unicode_characters:
                style = composition.pdf_same_style_unicode_characters.pdf_style
                if style is None:
                    logger.warning(
                        f"Style is None. "
                        f"Composition: {composition}. "
                        f"Paragraph: {paragraph}. ",
                    )
                    continue
                font_id = style.font_id
                if font_id is None:
                    logger.warning(
                        f"Font ID is None. "
                        f"Composition: {composition}. "
                        f"Paragraph: {paragraph}. ",
                    )
                    continue
                font = get_font(font_id, paragraph.xobj_id)
                # Log font info for all translated compositions (title detection + bold)
                if getattr(paragraph, "layout_label", None) == "title":
                    logger.warning(
                        "typesetting: TITLE font_id=%s name=%s bold=%s size=%.1f text=%r",
                        font_id, getattr(font, "name", "?"),
                        getattr(font, "bold", None),
                        style.font_size,
                        (composition.pdf_same_style_unicode_characters.unicode or "")[:40],
                    )
                elif getattr(font, "bold", None):
                    logger.warning(
                        "typesetting: BOLD font_id=%s name=%s size=%.1f text=%r",
                        font_id, getattr(font, "name", "?"),
                        style.font_size,
                        (composition.pdf_same_style_unicode_characters.unicode or "")[:40],
                    )
                if composition.pdf_same_style_unicode_characters.unicode:
                    result.extend(
                        [
                            TypesettingUnit(
                                unicode=char_unicode,
                                font=self.font_mapper.map(
                                    font,
                                    char_unicode,
                                ),
                                original_font=font,
                                font_size=style.font_size,
                                style=style,
                                xobj_id=paragraph.xobj_id,
                                debug_info=composition.pdf_same_style_unicode_characters.debug_info
                                or False,
                            )
                            for char_unicode in composition.pdf_same_style_unicode_characters.unicode
                            if char_unicode not in ("\n",)
                        ],
                    )
            elif composition.pdf_formula:
                result.extend([TypesettingUnit(formular=composition.pdf_formula)])
            else:
                logger.error(
                    f"Unknown composition type. "
                    f"Composition: {composition}. "
                    f"Paragraph: {paragraph}. ",
                )
                continue
        result = list(
            filter(
                lambda x: x.unicode is None or x.font is not None,
                result,
            ),
        )

        if any(x.width < 0 for x in result):
            logger.warning("有排版单元宽度小于 0，请检查字体映射是否正确。")

        # CJK 词组合并：标记词组内部字符为不可断行
        if self.is_cjk:
            result = merge_cjk_units(result)

        return result

    def create_passthrough_composition(
        self,
        typesetting_units: list[TypesettingUnit],
    ) -> list[PdfParagraphComposition]:
        """从排版单元创建直接传递的段落组合。

        Args:
            typesetting_units: 排版单元列表

        Returns:
            段落组合列表
        """
        composition = []
        for unit in typesetting_units:
            if unit.formular:
                # 对于公式单元，直接创建包含完整公式的组合
                composition.append(PdfParagraphComposition(pdf_formula=unit.formular))
            else:
                # 对于字符单元，使用原有逻辑
                chars, curves, forms = unit.passthrough()
                composition.extend(
                    [PdfParagraphComposition(pdf_character=char) for char in chars],
                )
        return composition

    def get_max_right_space(self, current_box: Box, page) -> float:
        """获取段落右侧最大可用空间

        Args:
            current_box: 当前段落的边界框
            page: 当前页面

        Returns:
            可以扩展到的最大 x 坐标
        """
        # 获取页面的裁剪框作为初始最大限制
        max_x = page.cropbox.box.x2 * 0.9

        # 检查所有可能的阻挡元素
        for para in page.pdf_paragraph:
            if para.box == current_box or para.box is None:  # 跳过当前段落
                continue
            # 只考虑在当前段落右侧且有垂直重叠的元素
            if para.box.x > current_box.x and not (
                para.box.y >= current_box.y2 or para.box.y2 <= current_box.y
            ):
                max_x = min(max_x, para.box.x)
        for char in page.pdf_character:
            if char.box.x > current_box.x and not (
                char.box.y >= current_box.y2 or char.box.y2 <= current_box.y
            ):
                max_x = min(max_x, char.box.x)
        # 检查图形
        for figure in page.pdf_figure:
            if figure.box.x > current_box.x and not (
                figure.box.y >= current_box.y2 or figure.box.y2 <= current_box.y
            ):
                max_x = min(max_x, figure.box.x)

        # 检查排除区域（Quote 等）
        zone_index = getattr(self, "_current_zone_index", None)
        if zone_index:
            for zone in zone_index.zones:
                if zone.box.x > current_box.x and not (
                    zone.box.y >= current_box.y2 or zone.box.y2 <= current_box.y
                ):
                    max_x = min(max_x, zone.box.x)

        return max_x

    def get_max_bottom_space(self, current_box: Box, page: il_version_1.Page) -> float:
        """获取段落下方最大可用空间

        Args:
            current_box: 当前段落的边界框
            page: 当前页面

        Returns:
            可以扩展到的最小 y 坐标
        """
        # 获取页面的裁剪框作为初始最小限制
        min_y = page.cropbox.box.y * 1.1

        # 检查所有可能的阻挡元素
        for para in page.pdf_paragraph:
            if para.box == current_box or para.box is None:  # 跳过当前段落
                continue
            # 只考虑在当前段落下方且有水平重叠的元素
            if para.box.y2 < current_box.y and not (
                para.box.x >= current_box.x2 or para.box.x2 <= current_box.x
            ):
                min_y = max(min_y, para.box.y2)
        for char in page.pdf_character:
            if char.box.y2 < current_box.y and not (
                char.box.x >= current_box.x2 or char.box.x2 <= current_box.x
            ):
                min_y = max(min_y, char.box.y2)
        # 检查图形
        for figure in page.pdf_figure:
            if figure.box.y2 < current_box.y and not (
                figure.box.x >= current_box.x2 or figure.box.x2 <= current_box.x
            ):
                min_y = max(min_y, figure.box.y2)

        # 检查排除区域（Quote 等）
        zone_index = getattr(self, "_current_zone_index", None)
        if zone_index:
            for zone in zone_index.zones:
                if zone.box.y2 < current_box.y and not (
                    zone.box.x >= current_box.x2 or zone.box.x2 <= current_box.x
                ):
                    min_y = max(min_y, zone.box.y2)

        return min_y

    def _update_paragraph_render_order(self, paragraph: il_version_1.PdfParagraph):
        """
        重新设置段落各字符的 render order
        主 render order 等于 paragraph 的 renderorder，sub render order 从 1 开始自增
        """
        if not hasattr(paragraph, "render_order") or paragraph.render_order is None:
            return

        main_render_order = paragraph.render_order
        sub_render_order = 1

        # 遍历段落的所有组成部分
        for composition in paragraph.pdf_paragraph_composition:
            # 检查单个字符
            if composition.pdf_character:
                char = composition.pdf_character
                char.render_order = main_render_order
                char.sub_render_order = sub_render_order
                sub_render_order += 1
