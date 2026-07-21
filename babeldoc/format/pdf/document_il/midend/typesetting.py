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
from babeldoc.format.pdf.document_il import PdfSameStyleUnicodeCharacters
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
from babeldoc.format.pdf.document_il.utils.cjk_kinsoku import (
    CJK_LINE_END_FORBIDDEN as _CJK_LINE_END_FORBIDDEN,
)
from babeldoc.format.pdf.document_il.utils.cjk_kinsoku import (
    CJK_LINE_START_FORBIDDEN as _CJK_LINE_START_FORBIDDEN,
)
from babeldoc.format.pdf.document_il.utils.cjk_kinsoku import (
    is_cjk_line_end_forbidden,
    is_cjk_line_start_forbidden,
)
from babeldoc.format.pdf.translation_config import TranslationConfig
from babeldoc.format.pdf.translation_config import WatermarkOutputMode

logger = logging.getLogger(__name__)


def line_advance_distance(
    font_size: float,
    scale: float,
    line_skip: float,
    mode_height: float,
    max_height: float,
) -> float:
    """How far to step ``current_y`` down after finishing a typeset line.

    Floors the advance with the paragraph's dominant em (``font_size * scale``)
    so an all-Latin line with short glyph boxes cannot shrink the skip and let
    the next CJK line overlap (upstream v0.6.4).
    """
    return max(
        font_size * scale * line_skip,
        mode_height * line_skip,
        max_height * 1.05,
    )


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


# 序数/量词：与数字粘连成「第11卷」「1989年」等不可拆片段
_CJK_MEASURE_AFTER_DIGIT = frozenset("卷章节页条款项年月日时分秒")
_CJK_ORDINAL_BEFORE_DIGIT = frozenset("第")


def _unit_char(unit: 'TypesettingUnit') -> str:
    return unit.try_get_unicode() or ""


def _is_digit_unit(unit: 'TypesettingUnit') -> bool:
    ch = _unit_char(unit)
    return len(ch) == 1 and ch.isdigit()


def merge_cjk_units(units: list['TypesettingUnit']) -> list['TypesettingUnit']:
    """标记 CJK 词组边界 + 禁则 + 数字量词粘连，使 DP/贪心不在非法位置断开。

    策略：
    1. 二字/三字词典：词组内部 ``can_break_line=False``（标在首字上）
    2. 行首禁则：。，）」/的地得… 前的字符不可断（避免标点/助词落行首）
    3. 行尾禁则：（【「/和与及… 本身不可断（避免开括号/连词落行尾）
    4. 数字粘连：连续数字不拆；「第」+ 数字 +「卷/年…」整段不拆

    ATU dual p22–23 goldens: ``这些背|带`` / ``乳|房`` / ``她|的背部`` /
    ``肩膀和|前方`` — fixed via dict + particle/conj kinsoku.
    """
    if not units:
        return units

    # 收集 CJK 字符的位置和 unicode
    cjk_positions = []  # (index, unicode_char)
    for i, unit in enumerate(units):
        if unit.is_cjk_char:
            unicode = unit.try_get_unicode()
            if unicode:
                cjk_positions.append((i, unicode))

    # 词组保护需要至少两个相邻 CJK；禁则对全序列仍要跑
    word_internal: set[int] = set()
    if len(cjk_positions) >= 2:
        cjk_text = "".join(ch for _, ch in cjk_positions)
        cjk_indices = [idx for idx, _ in cjk_positions]

        for cjk_pos in range(1, len(cjk_text)):
            if cjk_indices[cjk_pos] - cjk_indices[cjk_pos - 1] != 1:
                continue

            # can_break_line = "may break AFTER this unit". Mark the *first*
            # char of a multi-char word so we never break 感|情 / 社会|主义.
            word2 = cjk_text[cjk_pos - 1 : cjk_pos + 1]
            if is_cjk_two_char_word(word2):
                word_internal.add(cjk_indices[cjk_pos - 1])
                continue

            if (
                cjk_pos >= 2
                and cjk_indices[cjk_pos - 1] - cjk_indices[cjk_pos - 2] == 1
            ):
                word3 = cjk_text[cjk_pos - 2 : cjk_pos + 1]
                if is_cjk_three_char_word(word3):
                    word_internal.add(cjk_indices[cjk_pos - 2])
                    word_internal.add(cjk_indices[cjk_pos - 1])

    for i, unit in enumerate(units):
        if i in word_internal:
            unit.can_break_line_cache = False

        unicode = unit.try_get_unicode()
        if not unicode:
            continue

        # 行首禁则：禁止在「行首禁用字」前断开（含数字/空格前的 年 等）
        # 旧逻辑只看前一 unit 是否 CJK，导致「（1989 | 年）」仍被拆开。
        if is_cjk_line_start_forbidden(unicode) and i > 0:
            j = i - 1
            while j >= 0 and getattr(units[j], "is_space", False):
                units[j].can_break_line_cache = False
                j -= 1
            if j >= 0:
                units[j].can_break_line_cache = False

        # 行尾禁则：开括号/开引号本身不可作为断行点
        if is_cjk_line_end_forbidden(unicode):
            unit.can_break_line_cache = False

    # 数字 / 序数 / 量词粘连：第11卷、1989年、第 11 卷（含空格）
    n = len(units)
    i = 0
    while i < n:
        ch = _unit_char(units[i])
        # 「第」+ 可选空格 + 数字… + 可选空格 + 量词
        if ch in _CJK_ORDINAL_BEFORE_DIGIT:
            j = i + 1
            while j < n and getattr(units[j], "is_space", False):
                units[i].can_break_line_cache = False
                units[j].can_break_line_cache = False
                j += 1
            if j < n and _is_digit_unit(units[j]):
                units[i].can_break_line_cache = False
                while j < n and _is_digit_unit(units[j]):
                    units[j].can_break_line_cache = False
                    j += 1
                    # trailing spaces inside the run stay glued
                    while j < n and getattr(units[j], "is_space", False):
                        units[j].can_break_line_cache = False
                        j += 1
                if j < n and _unit_char(units[j]) in _CJK_MEASURE_AFTER_DIGIT:
                    # measure may end the atomic run (break after measure OK)
                    j += 1
                i = j
                continue
        # 连续数字（含中间空格）+ 可选量词
        if _is_digit_unit(units[i]):
            j = i
            while j < n and (
                _is_digit_unit(units[j]) or getattr(units[j], "is_space", False)
            ):
                if j + 1 < n and (
                    _is_digit_unit(units[j + 1])
                    or getattr(units[j + 1], "is_space", False)
                    or _unit_char(units[j + 1]) in _CJK_MEASURE_AFTER_DIGIT
                ):
                    units[j].can_break_line_cache = False
                j += 1
            if j < n and _unit_char(units[j]) in _CJK_MEASURE_AFTER_DIGIT:
                j += 1
            i = max(j, i + 1)
            continue
        i += 1

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
        return is_cjk_line_end_forbidden(unicode)

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

    def shift_y(self, dy: float) -> None:
        """Shift this unit vertically in place (after relocate)."""
        if abs(dy) < 1e-6:
            return
        if self.char and self.char.box:
            self.char.box.y += dy
            self.char.box.y2 += dy
            if self.char.visual_bbox and self.char.visual_bbox.box:
                self.char.visual_bbox.box.y += dy
                self.char.visual_bbox.box.y2 += dy
        elif self.formular:
            if self.formular.box:
                self.formular.box.y += dy
                self.formular.box.y2 += dy
            for char in self.formular.pdf_character or []:
                if char.box:
                    char.box.y += dy
                    char.box.y2 += dy
                if char.visual_bbox and char.visual_bbox.box:
                    char.visual_bbox.box.y += dy
                    char.visual_bbox.box.y2 += dy
            for curve in self.formular.pdf_curve or []:
                if curve.box:
                    curve.box.y += dy
                    curve.box.y2 += dy
                if curve.relocation_transform and len(curve.relocation_transform) >= 6:
                    rt = list(curve.relocation_transform)
                    rt[5] += dy  # CTM translation f
                    curve.relocation_transform = rt
            for form in self.formular.pdf_form or []:
                if form.box:
                    form.box.y += dy
                    form.box.y2 += dy
                if form.relocation_transform and len(form.relocation_transform) >= 6:
                    rt = list(form.relocation_transform)
                    rt[5] += dy
                    form.relocation_transform = rt
        elif self.unicode is not None and self.y is not None:
            self.y += dy
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
    # OCR dual-layer: slightly tighter than default CJK leading so long ZH
    # body can keep a larger scale inside the original/white-fill box.
    _OCR_LINE_SKIP_CJK = 1.30
    # Floor scale under OCR — prefer expanding the white-fill box over
    # unreadable ~0.55 crushing. 0.88 was too high: long body overflowed,
    # overlap retypeset failed, and headers/body looked empty or EN-restored.
    _OCR_MIN_SCALE = 0.70
    # Body text smaller than this (pt) is treated as OCR noise (e.g. Courier
    # 7.5) and lifted toward the paragraph median when ocr_workaround is on.
    _OCR_MIN_BODY_FONT_PT = 10.0

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

    def _quote_zone_config(self):
        """Build QuoteZoneConfig from TranslationConfig (main-path + retypeset).

        PostLayout already receives quote_* thresholds; typesetting previously
        called ExclusionZoneBuilder.build(page) with defaults only.
        Margin fields stay at QuoteZoneConfig defaults (not on TranslationConfig).
        """
        from babeldoc.format.pdf.document_il.midend.exclusion_zone import (
            QuoteZoneConfig,
        )

        tc = self.translation_config
        return QuoteZoneConfig(
            narrow_threshold=tc.quote_narrow_threshold,
            indent_threshold=tc.quote_indent_threshold,
            right_margin_threshold=tc.quote_right_margin_threshold,
        )

    def _build_page_exclusion_zones(self, page: il_version_1.Page):
        """Build exclusion zones for a page using config quote thresholds."""
        from babeldoc.format.pdf.document_il.midend.exclusion_zone import (
            ExclusionZoneBuilder,
        )

        return ExclusionZoneBuilder.build(page, self._quote_zone_config())

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
                    zones = self._build_page_exclusion_zones(page)
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

        # Cap all paragraphs to the mode scale so a page stays visually uniform.
        # OCR / searchable-image dual-layer is an exception: long body runs often
        # need a lower scale than titles, and demoting titles/body to that mode
        # leaves body text tiny inside a tall white fill (empty band under ZH).
        if getattr(self.translation_config, "ocr_workaround", False):
            logger.debug(
                "ocr_workaround: keep per-paragraph optimal_scale (no mode demotion)"
            )
        elif all_scales:
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
        self._ocr_normalize_paragraph_geometry(paragraph)
        box = paragraph.box
        scale = initial_scale
        ocr_mode = bool(
            getattr(self.translation_config, "ocr_workaround", False)
        )
        if line_skip is None:
            if self.is_cjk:
                # Slightly tighter leading under OCR so more lines fit at a
                # larger scale inside the white-fill box (dual-layer PDFs).
                line_skip = (
                    self._OCR_LINE_SKIP_CJK if ocr_mode else self._DEFAULT_LINE_SKIP_CJK
                )
            else:
                line_skip = self._DEFAULT_LINE_SKIP_NON_CJK

        # 提取原版行宽，用于参考布局.
        # OCR dual-layer: ignore EN line-width taper. OCR "lines" are noisy and
        # often include short Courier runs; capping to those widths forces many
        # wraps and crushes scale into a tiny top strip over empty white fill.
        if ocr_mode:
            reference_widths = None
        else:
            reference_widths = self._extract_original_line_widths(paragraph)
            # Layout-first (CJK dual): uniform full measure — not EN tail
            # widths, not word-level micro-tuning. ATU p22–23 长短参差.
            if self.is_cjk and reference_widths:
                reference_widths = Typesetting._uniform_cjk_reference_widths(
                    reference_widths
                )
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
        # OCR: do not crush below this for body readability; prefer expand box.
        if ocr_mode:
            min_scale = max(min_scale, self._OCR_MIN_SCALE)
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

        # OCR dual-layer: claim free width/height before crushing scale so ZH
        # can use the white-fill region instead of shrinking into the top band.
        if ocr_mode and box is not None:
            box = self._ocr_pre_expand_box(box, paragraph, page, apply_layout)
            typesetting_units = self._ocr_normalize_unit_font_sizes(
                typesetting_units
            )

        # OCR: always search from full size so expand-before-shrink runs; a low
        # precomputed_scale would otherwise accept tiny type immediately.
        if ocr_mode and apply_layout and scale < 1.0:
            scale = 1.0

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
                        opt_breaks: list[int] | None = None
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
                                    paragraph=paragraph,
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
                                    else:
                                        # S3: DP plan rejected — place used different
                                        # capacity or inserted extra breaks.
                                        logger.info(
                                            "DP_REJECT reason=place_mismatch "
                                            "debug_id=%s breaks=%s opt_fit=%s "
                                            "n_units=%s scale=%.3f",
                                            getattr(paragraph, "debug_id", None),
                                            opt_breaks,
                                            opt_fit,
                                            len(typesetting_units),
                                            scale,
                                        )
                                else:
                                    logger.debug(
                                        "DP_REJECT reason=no_breaks debug_id=%s "
                                        "n_units=%s scale=%.3f",
                                        getattr(paragraph, "debug_id", None),
                                        len(typesetting_units),
                                        scale,
                                    )
                        except Exception as e:
                            # DP 优化失败，使用贪心结果
                            logger.warning(
                                "DP_REJECT reason=exception debug_id=%s err=%s",
                                getattr(paragraph, "debug_id", None),
                                e,
                            )

                        if optimized_typeset_units:
                            typeset_units = optimized_typeset_units
                            logger.debug(
                                "DP_ADOPT debug_id=%s breaks=%s",
                                getattr(paragraph, "debug_id", None),
                                opt_breaks,
                            )

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
            # OCR dual-layer: expand down first so body can use the white-fill
            # height instead of only growing sideways.
            # Trigger expansion as soon as scale drops below ~full size, not
            # only after scale < 0.7 (that was too late for "Edging"-class titles).
            if expand_space_flag < 2 and scale >= 0.85:
                space_expanded = False
                expand_down_first = ocr_mode
                retry_scale = 1.0 if ocr_mode else initial_scale

                if expand_space_flag == 0:
                    if expand_down_first:
                        try:
                            min_y = self.get_max_bottom_space(box, page) + 2
                            if min_y < box.y:
                                expanded_box = Box(
                                    x=box.x, y=min_y, x2=box.x2, y2=box.y2
                                )
                                box = expanded_box
                                if apply_layout:
                                    paragraph.box = expanded_box
                                space_expanded = True
                        except Exception:
                            pass
                    else:
                        try:
                            max_x = self.get_max_right_space(box, page) - 5
                            if max_x > box.x2 + 1:
                                expanded_box = Box(
                                    x=box.x, y=box.y, x2=max_x, y2=box.y2
                                )
                                box = expanded_box
                                if apply_layout:
                                    paragraph.box = expanded_box
                                space_expanded = True
                        except Exception:
                            pass
                    expand_space_flag = 1
                    if space_expanded:
                        scale = retry_scale
                        continue

                elif expand_space_flag == 1:
                    if expand_down_first:
                        try:
                            max_x = self.get_max_right_space(box, page) - 5
                            if max_x > box.x2 + 1:
                                expanded_box = Box(
                                    x=box.x, y=box.y, x2=max_x, y2=box.y2
                                )
                                box = expanded_box
                                if apply_layout:
                                    paragraph.box = expanded_box
                                space_expanded = True
                        except Exception:
                            pass
                    else:
                        try:
                            min_y = self.get_max_bottom_space(box, page) + 2
                            if min_y < box.y:
                                expanded_box = Box(
                                    x=box.x, y=min_y, x2=box.x2, y2=box.y2
                                )
                                box = expanded_box
                                if apply_layout:
                                    paragraph.box = expanded_box
                                space_expanded = True
                        except Exception:
                            pass
                    expand_space_flag = 2
                    if space_expanded:
                        scale = retry_scale
                        continue

            # 减小缩放因子
            if scale > 0.6:
                scale -= 0.05
            else:
                scale -= 0.1

            # Late expansion fallback (legacy path) if early expand was skipped
            if scale < 0.7 and expand_space_flag < 2:
                space_expanded = False
                expand_down_first = ocr_mode
                retry_scale = 1.0 if ocr_mode else initial_scale
                if expand_space_flag == 0:
                    if expand_down_first:
                        try:
                            min_y = self.get_max_bottom_space(box, page) + 2
                            if min_y < box.y:
                                expanded_box = Box(
                                    x=box.x, y=min_y, x2=box.x2, y2=box.y2
                                )
                                box = expanded_box
                                if apply_layout:
                                    paragraph.box = expanded_box
                                space_expanded = True
                        except Exception:
                            pass
                    else:
                        try:
                            max_x = self.get_max_right_space(box, page) - 5
                            if max_x > box.x2 + 1:
                                expanded_box = Box(
                                    x=box.x, y=box.y, x2=max_x, y2=box.y2
                                )
                                box = expanded_box
                                if apply_layout:
                                    paragraph.box = expanded_box
                                space_expanded = True
                        except Exception:
                            pass
                    expand_space_flag = 1
                    if space_expanded:
                        scale = retry_scale
                        continue
                elif expand_space_flag == 1:
                    if expand_down_first:
                        try:
                            max_x = self.get_max_right_space(box, page) - 5
                            if max_x > box.x2 + 1:
                                expanded_box = Box(
                                    x=box.x, y=box.y, x2=max_x, y2=box.y2
                                )
                                box = expanded_box
                                if apply_layout:
                                    paragraph.box = expanded_box
                                space_expanded = True
                        except Exception:
                            pass
                    else:
                        try:
                            min_y = self.get_max_bottom_space(box, page) + 2
                            if min_y < box.y:
                                expanded_box = Box(
                                    x=box.x, y=min_y, x2=box.x2, y2=box.y2
                                )
                                box = expanded_box
                                if apply_layout:
                                    paragraph.box = expanded_box
                                space_expanded = True
                        except Exception:
                            pass
                    expand_space_flag = 2
                    if space_expanded:
                        scale = retry_scale
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
                # OCR dual-layer: never reintroduce EN reference_widths here —
                # same reason as the main search path (noisy short OCR lines).
                force_ref = (
                    None
                    if getattr(self.translation_config, "ocr_workaround", False)
                    else self._extract_original_line_widths(paragraph)
                )
                if self.is_cjk and force_ref:
                    force_ref = Typesetting._uniform_cjk_reference_widths(force_ref)
                force_units, _ = self._layout_typesetting_units(
                    typesetting_units,
                    box,
                    min_scale,
                    line_skip,
                    paragraph,
                    use_english_line_break=False,
                    reference_widths=force_ref,
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

    # Leading marker for numbered list items (EN/CJK dual hanging indent).
    # Include ideographic ``。`` — DeepLX/MT often rewrites ``2.`` → ``2。``.
    _LIST_MARKER_RE = re.compile(
        r"^(?:"
        r"\d{1,3}\s*[\.．。、\)]\s*"  # 1.  1． 1。 1、  1)
        r"|\(\s*\d{1,3}\s*\)\s*"  # (1)
        r"|[①-⑳]\s*"
        r")"
    )
    # Next-item serial glued onto the previous item's last sentence
    # (All Tied Up dual p21: item 3 ends ``恰到好处。4.`` / item 4 ends ``垂下来。5.``).
    # Require a sentence terminator immediately before the serial so prose like
    # ``The answer is 42.`` is not stripped.
    _TRAILING_LIST_MARKER_RE = re.compile(
        r"(?P<body>.*[。．.!?！？])\s*(?P<marker>\d{1,3}\s*[\.．。、\)])\s*$",
        re.DOTALL,
    )
    # Leading serial with CJK/fullwidth punct that MT rewrote from ``1.``
    _LEADING_LIST_MARKER_DOT_RE = re.compile(
        r"^(?P<lead>\s*)(?P<num>\d{1,3})\s*(?P<punct>[。．、])\s*"
    )
    # ~4 CJK glyphs at scale≈1 — shared min body column after hang/indent.
    _MIN_LINE_BODY_PT = 48.0

    @staticmethod
    def _looks_like_numbered_list_item(paragraph: il_version_1.PdfParagraph) -> bool:
        """True when translated/source text starts like ``1.`` / ``1、`` / ``2。``."""
        text = (getattr(paragraph, "unicode", None) or "").strip()
        if not text:
            return False
        # NBSP / thin space after marker still counts as list
        text = text.replace("\xa0", " ").replace("\u2009", " ")
        return bool(Typesetting._LIST_MARKER_RE.match(text))

    @staticmethod
    def _marker_digit(marker: str) -> str | None:
        m = re.match(r"(\d{1,3})", (marker or "").strip())
        return m.group(1) if m else None

    @staticmethod
    def _normalize_list_marker_token(marker: str) -> str:
        """Force list serial to ASCII ``N.`` (never ``N。`` from DeepLX)."""
        digit = Typesetting._marker_digit(marker)
        if not digit:
            return (marker or "").strip()
        return f"{digit}."

    @staticmethod
    def _normalize_leading_list_marker_text(text: str | None) -> str | None:
        """Rewrite leading ``1。`` / ``1．`` / ``1、`` → ``1.`` for list items.

        DeepLX often localizes the list period to ideographic ``。``, which
        looks like a Chinese sentence end and breaks hang-width consistency.
        Only the *leading* serial is touched — body ``句号。`` stays.
        """
        if text is None:
            return None
        if not text:
            return text
        # NBSP from MT
        t = text.replace("\xa0", " ").replace("\u2009", " ")
        m = Typesetting._LEADING_LIST_MARKER_DOT_RE.match(t)
        if not m:
            return text
        # Keep original leading whitespace; body after marker
        rest = t[m.end() :]
        # CJK body: no space after ``1.`` (same as EN dual ``1.Start`` often);
        # Latin body: one space.
        if rest and not rest[0].isspace():
            o = ord(rest[0])
            is_cjk = (
                0x4E00 <= o <= 0x9FFF
                or 0x3400 <= o <= 0x4DBF
                or 0x3040 <= o <= 0x30FF
                or 0xAC00 <= o <= 0xD7AF
            )
            if not is_cjk:
                rest = " " + rest
        return f"{m.group('lead')}{m.group('num')}.{rest}"

    @staticmethod
    def _join_list_marker_to_body(marker: str, body: str) -> str:
        """Prepend normalized ``4.`` to body without double spaces; CJK needs no gap."""
        m = Typesetting._normalize_list_marker_token(marker)
        b = body or ""
        if not m:
            return b
        if not b:
            return m
        if m[-1:].isspace() or b[0].isspace():
            return m + b
        # Ideographic body (CJK) — ``1.先将…`` (ASCII period, no space)
        o = ord(b[0])
        if (
            0x4E00 <= o <= 0x9FFF
            or 0x3400 <= o <= 0x4DBF
            or 0x3040 <= o <= 0x30FF
            or 0xAC00 <= o <= 0xD7AF
        ):
            return m + b
        return m + " " + b

    @staticmethod
    def _strip_trailing_marker_from_compositions(
        paragraph: il_version_1.PdfParagraph,
        marker: str,
    ) -> bool:
        """Remove trailing serial from compositions. Returns True if a composition changed."""
        want_digit = Typesetting._marker_digit(marker)
        if not want_digit or not paragraph.pdf_paragraph_composition:
            return False
        comps = paragraph.pdf_paragraph_composition
        for i in range(len(comps) - 1, -1, -1):
            comp = comps[i]
            ssu = comp.pdf_same_style_unicode_characters
            if ssu is not None and ssu.unicode:
                text = ssu.unicode
                m = Typesetting._TRAILING_LIST_MARKER_RE.search(text.rstrip())
                if m and Typesetting._marker_digit(m.group("marker")) == want_digit:
                    # Keep body including its sentence terminator; drop marker.
                    new_text = m.group("body").rstrip()
                    ssu.unicode = new_text
                    if not ssu.unicode.strip():
                        del comps[i]
                    return True
            formula = comp.pdf_formula
            if formula is not None and formula.pdf_character:
                ftext = "".join(
                    (c.char_unicode or "") for c in formula.pdf_character
                ).strip()
                if Typesetting._marker_digit(ftext) == want_digit and re.fullmatch(
                    r"\d{1,3}\s*[\.．。、\)]?", ftext
                ):
                    del comps[i]
                    return True
        return False

    @staticmethod
    def _prepend_marker_to_compositions(
        paragraph: il_version_1.PdfParagraph,
        marker: str,
        style: PdfStyle | None = None,
    ) -> None:
        """Ensure leading serial exists on compositions (and matches ``unicode``)."""
        marker = Typesetting._normalize_list_marker_token(marker)
        if not marker:
            return
        comps = paragraph.pdf_paragraph_composition
        if comps is None:
            paragraph.pdf_paragraph_composition = []
            comps = paragraph.pdf_paragraph_composition

        # Prefer mutating the first unicode span.
        if comps:
            ssu = comps[0].pdf_same_style_unicode_characters
            if ssu is not None and ssu.unicode is not None:
                body = ssu.unicode
                if Typesetting._LIST_MARKER_RE.match(body.lstrip()):
                    # Already has a serial — still normalize ``4。`` → ``4.``
                    ssu.unicode = Typesetting._normalize_leading_list_marker_text(
                        body
                    )
                    return
                ssu.unicode = Typesetting._join_list_marker_to_body(marker, body)
                return

        use_style = style or getattr(paragraph, "pdf_style", None)
        ssu = PdfSameStyleUnicodeCharacters(unicode=marker, pdf_style=use_style)
        comps.insert(0, PdfParagraphComposition(pdf_same_style_unicode_characters=ssu))

    @staticmethod
    def _normalize_list_marker_on_paragraph(
        paragraph: il_version_1.PdfParagraph,
    ) -> bool:
        """Normalize leading list punct on unicode + first composition. True if changed."""
        changed = False
        old_u = getattr(paragraph, "unicode", None)
        new_u = Typesetting._normalize_leading_list_marker_text(old_u)
        if new_u is not None and new_u != old_u:
            paragraph.unicode = new_u
            changed = True
        comps = paragraph.pdf_paragraph_composition or []
        if comps:
            ssu = comps[0].pdf_same_style_unicode_characters
            if ssu is not None and ssu.unicode is not None:
                new_c = Typesetting._normalize_leading_list_marker_text(ssu.unicode)
                if new_c is not None and new_c != ssu.unicode:
                    ssu.unicode = new_c
                    changed = True
        return changed

    @staticmethod
    def reattach_trailing_list_markers(
        paragraphs: list[il_version_1.PdfParagraph] | None,
    ) -> int:
        """Strip trailing glued serials; move onto next item when it lacks one.

        ATU dual p21 cases:
        * Item 3 ends ``…恰到好处。4.`` and item 4 body has no leading serial
          → move ``4.`` to item 4 start.
        * Item 4 *already* starts with ``4。`` but item 3 still ends with ``4.``
          (duplicate after partial fix / MT) → **still strip** trailing from 3.

        Always normalize leading serials to ASCII ``N.`` (not ``N。``).
        """
        if not paragraphs or len(paragraphs) < 2:
            return 0
        moved = 0
        for i in range(len(paragraphs) - 1):
            prev = paragraphs[i]
            nxt = paragraphs[i + 1]
            prev_text = (getattr(prev, "unicode", None) or "").replace("\xa0", " ")
            next_text = (getattr(nxt, "unicode", None) or "").replace("\xa0", " ")
            if not prev_text.strip():
                continue
            m = Typesetting._TRAILING_LIST_MARKER_RE.search(prev_text.rstrip())
            if not m:
                continue
            marker_raw = m.group("marker").strip()
            marker = Typesetting._normalize_list_marker_token(marker_raw)
            body_prev = m.group("body").rstrip()
            if len(body_prev) < 8:
                continue

            next_has_marker = Typesetting._looks_like_numbered_list_item(nxt)
            # Strip trailing serial from prev always (dedupe when next already
            # has the leading marker — ATU p21 after partial reattach).
            prev.unicode = body_prev
            Typesetting._strip_trailing_marker_from_compositions(prev, marker_raw)
            # Sync first composition if strip missed multi-span residual
            if (prev.unicode or "").rstrip() != body_prev:
                prev.unicode = body_prev
            comps = prev.pdf_paragraph_composition or []
            if comps:
                ssu = comps[-1].pdf_same_style_unicode_characters
                if ssu is not None and ssu.unicode:
                    tm = Typesetting._TRAILING_LIST_MARKER_RE.search(
                        ssu.unicode.rstrip()
                    )
                    if tm and Typesetting._marker_digit(
                        tm.group("marker")
                    ) == Typesetting._marker_digit(marker):
                        ssu.unicode = tm.group("body").rstrip()

            if not next_has_marker:
                if len((next_text or "").strip()) < 6:
                    # Stripped prev only; next too short to own the serial
                    moved += 1
                    continue
                nxt.unicode = Typesetting._join_list_marker_to_body(
                    marker, next_text.lstrip()
                )
                Typesetting._prepend_marker_to_compositions(
                    nxt, marker, style=getattr(nxt, "pdf_style", None)
                )
                if (
                    prev.box is not None
                    and nxt.box is not None
                    and prev.box.x is not None
                    and nxt.box.x is not None
                    and float(nxt.box.x) > float(prev.box.x) + 4.0
                ):
                    nxt.box.x = float(prev.box.x)
                try:
                    nxt.first_line_indent = 0.0
                except Exception:
                    pass
            else:
                # Next already has a leading serial — just normalize its punct
                Typesetting._normalize_list_marker_on_paragraph(nxt)

            moved += 1
            logger.debug(
                "List marker glue: stripped trailing %r from prev; next_has=%s",
                marker,
                next_has_marker,
            )
        return moved

    @staticmethod
    def normalize_list_markers_on_document(
        document: il_version_1.Document,
    ) -> int:
        """Normalize leading ``N。`` → ``N.`` on every list-like paragraph."""
        n = 0
        for page in document.page or []:
            for para in page.pdf_paragraph or []:
                if Typesetting._normalize_list_marker_on_paragraph(para):
                    n += 1
        if n:
            logger.info(
                "Normalized %d leading list marker(s) to ASCII period", n
            )
        return n

    @staticmethod
    def reattach_trailing_list_markers_on_document(
        document: il_version_1.Document,
    ) -> int:
        """Page-wise pass; call once before typesetting."""
        total = 0
        for page in document.page or []:
            total += Typesetting.reattach_trailing_list_markers(
                page.pdf_paragraph
            )
        # Always normalize leading list dots after reattach (and for clean items)
        Typesetting.normalize_list_markers_on_document(document)
        if total:
            logger.info(
                "Reattached/stripped %d trailing list marker(s) before typesetting",
                total,
            )
        return total

    @staticmethod
    def _list_marker_hang_width(
        paragraph: il_version_1.PdfParagraph,
        typesetting_units: list[TypesettingUnit] | None,
        scale: float,
    ) -> float:
        """Pure width of leading ``1. `` / ``2、`` from typesetting units.

        Policy (OCR, line index, span cap) lives in ``_numbered_list_hang_inset``.
        """
        if not Typesetting._looks_like_numbered_list_item(paragraph):
            return 0.0

        parts: list[tuple[str, float]] = []
        for u in typesetting_units or []:
            ch = u.try_get_unicode() if hasattr(u, "try_get_unicode") else None
            if not ch:
                continue
            parts.append((ch, float(getattr(u, "width", 0.0) or 0.0) * scale))
        if not parts:
            return 0.0

        full = "".join(ch for ch, _ in parts)
        lstripped = full.lstrip()
        lead = len(full) - len(lstripped)
        m = Typesetting._LIST_MARKER_RE.match(lstripped)
        if not m:
            return 0.0

        end = lead + len(m.group(0))
        hang = 0.0
        pos = 0
        for ch, w in parts:
            if pos >= end:
                break
            n = len(ch)
            if pos + n <= end:
                hang += w
            else:
                hang += w * ((end - pos) / max(1, n))
            pos += n
        return hang if hang > 0.5 else 0.0

    @staticmethod
    def _numbered_list_hang_inset(
        paragraph: il_version_1.PdfParagraph | None,
        typesetting_units: list[TypesettingUnit] | None,
        scale: float,
        *,
        line_idx: int,
        alignment: str,
        ocr_workaround: bool,
        pocket_span: float,
    ) -> float:
        """Left inset for wrap lines of numbered lists (0 on first line / OCR / non-left).

        EN dual lists hang under body after the serial; ZH reflow used to flush
        wrap lines under the digit (All Tied Up safety list / golden screenshot).
        """
        if (
            ocr_workaround
            or alignment != "left"
            or line_idx <= 0
            or paragraph is None
        ):
            return 0.0
        hang = Typesetting._list_marker_hang_width(
            paragraph, typesetting_units, scale
        )
        if hang <= 0.5:
            return 0.0
        if pocket_span > 1.0:
            min_body = Typesetting._MIN_LINE_BODY_PT * max(scale, 0.5)
            hang = min(hang, max(0.0, pocket_span - min_body))
        return hang if hang > 0.5 else 0.0

    @staticmethod
    def _inset_leftmost_interval(
        intervals: list[tuple[float, float]],
        inset: float,
    ) -> list[tuple[float, float]]:
        """Shrink leftmost pocket from the left (hanging / content column)."""
        if inset <= 0.5 or not intervals:
            return intervals
        ix1, ix2 = intervals[0]
        nx1 = min(ix1 + inset, ix2)
        if nx1 <= ix1 + 1e-9:
            return intervals
        return [(nx1, ix2), *intervals[1:]]

    @staticmethod
    def _resolve_effective_alignment(
        paragraph: il_version_1.PdfParagraph,
        typesetting_units: list[TypesettingUnit] | None = None,
        *,
        ocr_workaround: bool = False,
        is_cjk: bool = False,
    ) -> str:
        """Return alignment for layout; keep geometric center when it is real.

        ``detect_paragraph_alignment`` already set ``paragraph.alignment`` from
        **original** geometry. We demote center→left when:

        * original lines look like a filled body column (Orgasms false center), or
        * **CJK long body** from a short centered EN block (All Tied Up p5/p14) —
          reflow flush-left; keep center for short titles and arXiv-style headers
          (few original lines that do **not** fill the para span).
        """
        # OCR: geometry is too noisy; multi-line body false-centers short tails.
        if ocr_workaround:
            label = (getattr(paragraph, "layout_label", None) or "").lower()
            text = (paragraph.unicode or "").strip()
            if label == "title" and len(text) <= 40:
                return getattr(paragraph, "alignment", None) or "left"
            return "left"

        # Numbered list steps must stay flush-left with hang on wrap lines.
        # Short EN hanging items often detect as center → ZH block centers
        # (All Tied Up safety list items 2/5); hang only runs for left.
        if Typesetting._looks_like_numbered_list_item(paragraph):
            return "left"

        alignment = getattr(paragraph, "alignment", None) or "left"
        if alignment != "center":
            return alignment

        label = (getattr(paragraph, "layout_label", None) or "").lower()
        text = (paragraph.unicode or "").strip()
        text_len = len(text)
        unit_n = len(typesetting_units) if typesetting_units is not None else 0

        rm = getattr(paragraph, "reference_metrics", None)
        box = paragraph.box
        box_w = 0.0
        para_left = 0.0
        if box is not None and box.x2 is not None and box.x is not None:
            box_w = float(box.x2 - box.x)
            para_left = float(box.x)

        # Short title/heading may stay centered — but only when EN box is not
        # flush-left full-measure (ATU TECHNIQUE 1 / ebook section heads).
        if label == "title" and text_len <= 48 and unit_n <= 48:
            flush_left_wide = para_left < 62.0 and box_w >= 400.0
            if not flush_left_wide:
                return alignment

        line_count = 0
        fullish = 0.0
        last_ratio = 1.0
        if rm is not None and box_w > 1.0:
            line_count = int(getattr(rm, "line_count", 0) or 0)
            avg = getattr(rm, "avg_line_width", None)
            widths = getattr(rm, "per_line_widths", None) or []
            last_ratio = float(getattr(rm, "last_line_ratio", 1.0) or 1.0)

            if widths:
                fullish = sum(
                    1 for w in widths if float(w) >= box_w * 0.85
                ) / len(widths)
            elif avg is not None:
                fullish = 1.0 if float(avg) >= box_w * 0.85 else 0.0
            else:
                fullish = 0.0

            widths_f = [float(w) for w in widths] if widths else []
            if not widths_f and avg is not None:
                widths_f = [float(avg)]
            max_w = max(widths_f) if widths_f else 0.0
            min_w = min(widths_f) if widths_f else 0.0

            # Ebook full-measure body (ATU p4/p7/p13): EN ~480–500pt wide at
            # left margin ~56. arXiv page-centered titles start ~x=64 with
            # symmetric margins — require flush-left box to avoid demoting them.
            para_left = float(box.x) if box is not None and box.x is not None else 0.0
            flush_left = para_left < 62.0
            ebook_full_measure = flush_left and (
                max_w >= 470.0
                or (box_w >= 450.0 and avg is not None and float(avg) >= 400.0)
            )
            # Short ZH (p7 ~23 chars, p13 title ~8) still demotes when EN was
            # full-measure flush-left.
            if is_cjk and text_len >= 4 and ebook_full_measure:
                return "left"

            # Single-line EN centered block → often becomes multi-line ZH.
            # If ZH is wider than the original line box, reflow left
            # (All Tied Up p5 pull-quotes). Flush-left wide EN → left even for
            # short ZH / title labels (TECHNIQUE 1).
            if line_count <= 1:
                flush_left_wide = box_w >= 400.0 and flush_left
                if (
                    is_cjk
                    and text_len >= 4
                    and box_w > 1.0
                    and (
                        text_len * 11.0 > box_w * 1.15
                        or flush_left_wide
                        or (box_w >= 400.0 and text_len >= 20 and flush_left)
                    )
                ):
                    return "left"
                return alignment

            # Multi-line demotion (Orgasms false-center body):
            # majority of lines fill the para span AND there is a clearly
            # short last line. Do NOT demote 2-line arXiv affiliation blocks:
            # after date split their tight bbox makes fullish≈1.0 even though
            # every original line is page-centered (golden figure PDF header
            # lines 3–4 were forced left by the old fullish-only rule).
            if (
                fullish >= 0.5
                and line_count >= 3
                and last_ratio < 0.65
            ):
                return "left"

            # L3 / All Tied Up: long CJK from short *centered* EN marketing.
            # Keep arXiv multi-line headers only when tight bbox or strong
            # width pyramid (author/date), not uniform short pull-quotes.
            if is_cjk and text_len >= 36:
                pyramid = max_w > 1.0 and (min_w / max_w) < 0.35
                avg_fill = (
                    float(avg) / box_w
                    if avg is not None and box_w > 1.0
                    else fullish
                )
                # fullish alone is true for both arXiv tight headers AND ebook
                # body — require NOT full-measure ebook width.
                tight_header = (
                    line_count <= 4
                    and fullish >= 0.55
                    and not ebook_full_measure
                )
                tapering_header = (
                    line_count <= 4
                    and fullish < 0.5
                    and last_ratio < 0.40
                    and pyramid
                    and avg_fill >= 0.55
                )
                # Will ZH wrap far beyond original total line budget?
                orig_budget = sum(widths_f) if widths_f else box_w
                zh_overflow = text_len * 11.0 > orig_budget * 1.5
                if zh_overflow and not (tight_header or tapering_header):
                    return "left"
                if not (tight_header or tapering_header) and text_len >= 48:
                    return "left"

            return alignment

        # No reference metrics (legacy / skipped capture): weak length fallback
        # only — prefer keeping short centers; long unknown text → left.
        if text_len >= 36:
            return "left"
        if typesetting_units is not None and unit_n >= 36:
            return "left"
        return alignment

    @staticmethod
    def _parse_first_line_indent(paragraph: il_version_1.PdfParagraph) -> float:
        """Normalize paragraph.first_line_indent to a non-negative float.

        Accepts float/int, bool (legacy), and XML strings ("true"/"12.0").
        """
        val = getattr(paragraph, "first_line_indent", None)
        if val is None:
            return 0.0
        if isinstance(val, bool):
            return 12.0 if val else 0.0
        if isinstance(val, (int, float)):
            return max(0.0, float(val))
        if isinstance(val, str):
            low = val.strip().lower()
            if low in ("", "false", "none", "null"):
                return 0.0
            if low == "true":
                return 12.0
            try:
                return max(0.0, float(low))
            except ValueError:
                return 0.0
        try:
            return max(0.0, float(val))
        except (TypeError, ValueError):
            return 0.0

    def _ocr_normalize_paragraph_geometry(
        self, paragraph: il_version_1.PdfParagraph
    ) -> None:
        """OCR dual-layer: drop noisy indent/center from invisible text geometry.

        font.unknown-style OCR has jittery left edges → false first-line indents
        and false center on short last lines. Paper body should stay flush-left;
        keep center only for short single-line title labels.
        """
        if not getattr(self.translation_config, "ocr_workaround", False):
            return
        paragraph.first_line_indent = 0.0
        label = (getattr(paragraph, "layout_label", None) or "").lower()
        text = (paragraph.unicode or "").strip()
        # Single-line short title may stay centered; everything else left.
        n_lines = 0
        for comp in paragraph.pdf_paragraph_composition or []:
            if comp.pdf_line or comp.pdf_character or comp.pdf_same_style_unicode_characters:
                n_lines += 1
        if label == "title" and len(text) <= 40 and n_lines <= 1:
            return
        if len(text) >= 24 or n_lines >= 2:
            paragraph.alignment = "left"

    @staticmethod
    def _effective_first_line_indent(
        paragraph: il_version_1.PdfParagraph,
        box: Box,
        available_x: float,
        available_x2: float,
        scale: float,
        typesetting_units: list[TypesettingUnit],
        *,
        ocr_workaround: bool = False,
    ) -> float:
        """First-line indent in **absolute user space**, capped for usability.

        Indent is measured from original EN geometry (pt) and must not shrink
        with glyph ``scale`` — box coordinates are unscaled. Cap still uses
        scaled glyph size so a tight first line keeps ~4 CJK characters
        (Orgasms p.12 title-style breaks).
        """
        if ocr_workaround:
            return 0.0
        raw = Typesetting._parse_first_line_indent(paragraph)
        if raw <= 0:
            return 0.0

        # L3: numbered list items — source hanging/list geometry must not add
        # a large first-line indent on top of "1. " (All Tied Up p14 steps).
        if Typesetting._looks_like_numbered_list_item(paragraph):
            return 0.0

        # Absolute indent (same space as box.x / available_x). Placement uses
        # current_x = max(available_x, box.x + indent).
        indent = raw

        # L3: after center→left demotion, large "indent" is often a centered
        # short first line, not a real body first-line indent — drop extremes.
        box_w = max(0.0, float(box.x2 - box.x)) if box and box.x2 is not None else 0.0
        if box_w > 1.0 and indent > max(36.0, box_w * 0.12):
            # Keep classic ~1–2em indents only
            if indent > box_w * 0.18:
                return 0.0

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

        # Residual too tight even without indent → drop
        if available_x2 - available_x < min_remain:
            return 0.0
        # Cap so box.x + indent leaves min_remain (indent is from box.x, not
        # from available_x — important when a zone already pushed available_x).
        max_indent = available_x2 - min_remain - box.x
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

    def _ocr_pre_expand_box(
        self,
        box: Box,
        paragraph: il_version_1.PdfParagraph,
        page: il_version_1.Page,
        apply_layout: bool,
    ) -> Box:
        """Widen/deepen the layout box before OCR scale search.

        Searchable dual-layer pages keep a tall white fill over the EN image.
        Claiming free right/bottom space up front lets ZH keep a larger scale
        and fill more of that band instead of shrinking into the top edge.
        """
        if not box:
            return box
        x, y, x2, y2 = box.x, box.y, box.x2, box.y2
        changed = False
        try:
            max_x = self.get_max_right_space(box, page) - 5
            if max_x > x2 + 1:
                x2 = max_x
                changed = True
        except Exception:
            pass
        try:
            min_y = self.get_max_bottom_space(box, page) + 2
            if min_y < y - 1:
                y = min_y
                changed = True
        except Exception:
            pass
        if not changed:
            return box
        expanded = Box(x=x, y=y, x2=x2, y2=y2)
        if apply_layout:
            paragraph.box = expanded
        return expanded

    def _ocr_normalize_unit_font_sizes(
        self,
        typesetting_units: list[TypesettingUnit],
    ) -> list[TypesettingUnit]:
        """Lift undersized OCR runs (Courier 7.5) toward body size.

        Dual-layer PDFs often mix ~11pt body with ~7.5pt mono. After translate
        that small size either becomes the whole para style or drags mixed
        runs down; floor them so scale=1 yields readable ZH.
        """
        if not typesetting_units:
            return typesetting_units
        sizes: list[float] = []
        for u in typesetting_units:
            fs = getattr(u, "font_size", None)
            if fs is None and getattr(u, "char", None) is not None:
                style = getattr(u.char, "pdf_style", None)
                fs = getattr(style, "font_size", None) if style else None
            if fs is not None and fs > 0:
                sizes.append(float(fs))
        if not sizes:
            return typesetting_units
        try:
            med = float(statistics.median(sizes))
        except statistics.StatisticsError:
            med = max(sizes)
        target = max(med, self._OCR_MIN_BODY_FONT_PT)
        # Don't inflate true small print (footnotes) that dominate the para.
        if med < self._OCR_MIN_BODY_FONT_PT * 0.85 and max(sizes) < self._OCR_MIN_BODY_FONT_PT:
            target = max(med, 9.0)
        for u in typesetting_units:
            if getattr(u, "formular", None):
                continue
            fs = getattr(u, "font_size", None)
            if fs is not None and 0 < fs < target * 0.92:
                u.font_size = target
            if getattr(u, "char", None) is not None and u.char.pdf_style is not None:
                cfs = u.char.pdf_style.font_size
                if cfs is not None and 0 < cfs < target * 0.92:
                    u.char.pdf_style.font_size = target
            if getattr(u, "style", None) is not None:
                sfs = u.style.font_size
                if sfs is not None and 0 < sfs < target * 0.92:
                    u.style.font_size = target
        return typesetting_units

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
            ExclusionZoneIndex,
        )

        # ATU dual p21: serials glued to prior item ends → reattach so hang runs.
        Typesetting.reattach_trailing_list_markers_on_document(document)

        # 预先构建每页的排除区域缓存，避免重复构建
        self._page_zone_cache: dict[int, ExclusionZoneIndex | None] = {}
        for page in document.page:
            zones = self._build_page_exclusion_zones(page)
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
                ExclusionZoneIndex,
            )
            zones = self._build_page_exclusion_zones(page)
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
        # Dual-layer / OCR white-fill path: retypeset-on-overlap often fails at
        # the raised min scale and restores compositions while leaving layout
        # worse (title empty, body scrambled). Prefer first-pass layout.
        if getattr(self.translation_config, "ocr_workaround", False):
            logger.debug(
                "ocr_workaround: skip post-typesetting overlap retypeset"
            )
            return

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

        self._ocr_normalize_paragraph_geometry(paragraph)
        typesetting_units = self.create_typesetting_units(paragraph, fonts)
        # OCR dual-layer: never passthrough original (often invisible 3 Tr)
        # units. Passthrough + white fill = blank title/author while body
        # (retypeset ZH) looks fine. Always retypeset so glyphs are painted.
        ocr_mode = bool(
            getattr(self.translation_config, "ocr_workaround", False)
        )
        if (
            not ocr_mode
            and typesetting_units
            and all(unit.can_passthrough for unit in typesetting_units)
        ):
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

    @staticmethod
    def _uniform_cjk_reference_widths(
        reference_widths: list[float] | None,
        *,
        fullish_ratio: float = 0.85,
    ) -> list[float] | None:
        """**Layout-first** for CJK dual: one full measure for every line.

        Priority: rectangular column (English-style body) over replaying EN
        per-line raggedness or word-collocation micro-breaks.

        EN paragraphs often end with a short last line ``[500, 500, 200]``.
        ZH is longer, so line index 2 became an *intermediate* Chinese line
        capped at 200pt — severe 长短参差 (ATU p22–23). Collapse to the max of
        EN lines ≥ ``fullish_ratio * max`` so intermediate ZH lines share one
        width; only the final ZH line may stay short by content.

        Narrow figure columns (all lines short but equal) keep that column.
        """
        if not reference_widths:
            return reference_widths
        usable = [float(w) for w in reference_widths if w is not None and float(w) >= 12.0]
        if not usable:
            return reference_widths
        peak = max(usable)
        fullish = [w for w in usable if w >= peak * fullish_ratio]
        measure = max(fullish) if fullish else peak
        return [measure]

    def _query_line_intervals(
        self,
        y_bottom: float,
        y_top: float,
        box: Box,
    ) -> list[tuple[float, float]]:
        """Residual x intervals for a horizontal band (multi-interval wrap).

        Empty ``get_intervals_at`` (all pockets thinner than min_width) falls
        back to the full paragraph box — same spirit as single-interval
        needle-strip fallback.
        """
        zone_index = getattr(self, "_current_zone_index", None)
        if zone_index and zone_index.zones and y_top > y_bottom:
            intervals = zone_index.get_intervals_at(
                y_bottom, y_top, box.x, box.x2
            )
            if intervals:
                return list(intervals)
        return [(box.x, box.x2)]

    @staticmethod
    def _cap_leftmost_interval_with_reference(
        box: Box,
        intervals: list[tuple[float, float]],
        reference_widths: list[float] | None,
        line_idx: int,
        *,
        alignment: str | None = None,
    ) -> list[tuple[float, float]]:
        """Apply EN reference-width cap only on the leftmost residual pocket.

        Spec (PR-06): do not sum ref caps across intervals; taper applies to
        the primary (left) column that still starts near the body edge.
        """
        if not intervals:
            return [(box.x, box.x2)]
        if not reference_widths:
            return intervals
        ix1, ix2 = intervals[0]
        cx1, cx2 = Typesetting._cap_available_with_reference(
            box,
            ix1,
            ix2,
            reference_widths,
            line_idx,
            alignment=alignment,
        )
        if (cx1, cx2) == (ix1, ix2):
            return intervals
        return [(cx1, cx2), *intervals[1:]]

    @staticmethod
    def _remaining_capacity_on_line(
        current_x: float,
        intervals: list[tuple[float, float]],
        interval_idx: int,
    ) -> float:
        """Horizontal capacity left on this layout line across remaining pockets."""
        if interval_idx < 0 or interval_idx >= len(intervals):
            return 0.0
        rem = 0.0
        for j in range(interval_idx, len(intervals)):
            jx1, jx2 = intervals[j]
            if j == interval_idx:
                rem += max(0.0, jx2 - max(current_x, jx1))
            else:
                rem += max(0.0, jx2 - jx1)
        return rem

    @staticmethod
    def _try_advance_interval_for_unit(
        unit_width: float,
        intervals: list[tuple[float, float]],
        interval_idx: int,
        current_x: float,
        available_x2: float,
    ) -> tuple[int, float, float, float] | None:
        """If unit does not fit the current pocket, jump to the next that fits.

        Returns ``(new_idx, available_x, available_x2, current_x)`` or None.
        """
        if current_x + unit_width <= available_x2:
            return None  # already fits — caller should not advance
        for next_i in range(interval_idx + 1, len(intervals)):
            nix1, nix2 = intervals[next_i]
            if unit_width <= (nix2 - nix1) + 1e-6:
                return next_i, nix1, nix2, nix1
        return None

    def _line_capacity_like_place(
        self,
        *,
        box: Box,
        y_bottom: float,
        y_top: float,
        line_idx: int,
        reference_widths: list[float] | None,
        alignment: str,
        paragraph: il_version_1.PdfParagraph | None,
        typesetting_units: list[TypesettingUnit],
        scale: float,
    ) -> tuple[float, list[tuple[float, float]]]:
        """S3: capacity + intervals identical to ``_layout_typesetting_units``.

        1. query residual pockets for the y-band
        2. cap **leftmost** pocket with EN reference width (not min(ref, sum))
        3. numbered-list hang: shrink leftmost pocket on wrap lines (same as place)
        4. first-line indent reduces capacity on the left pocket only

        Returns ``(capacity, capped_intervals)``.
        """
        ocr_mode = bool(
            getattr(self.translation_config, "ocr_workaround", False)
        )
        intervals = self._query_line_intervals(y_bottom, y_top, box)
        intervals = self._cap_leftmost_interval_with_reference(
            box,
            intervals,
            reference_widths,
            line_idx,
            alignment=alignment,
        )
        if not intervals:
            return 0.0, [(box.x, box.x2)]

        # Match placement: hang = leftmost inset on wrap lines (not a parallel x)
        ix1, ix2 = intervals[0]
        hang = Typesetting._numbered_list_hang_inset(
            paragraph,
            typesetting_units,
            scale,
            line_idx=line_idx,
            alignment=alignment,
            ocr_workaround=ocr_mode,
            pocket_span=max(0.0, ix2 - ix1),
        )
        if hang > 0:
            intervals = Typesetting._inset_leftmost_interval(intervals, hang)

        capacity = sum(max(0.0, ix2 - ix1) for ix1, ix2 in intervals)

        # Match placement: first-line indent starts after max(left, box.x+indent)
        if (
            line_idx == 0
            and paragraph is not None
            and alignment == "left"
            and self._parse_first_line_indent(paragraph) > 0
        ):
            ix1, ix2 = intervals[0]
            indent = self._effective_first_line_indent(
                paragraph,
                box,
                ix1,
                ix2,
                scale,
                typesetting_units,
                ocr_workaround=ocr_mode,
            )
            if indent > 0:
                line_start = max(ix1, box.x + indent)
                lost = max(0.0, line_start - ix1)
                capacity = max(0.0, capacity - lost)

        return capacity, intervals

    def _estimate_line_widths(
        self,
        typesetting_units: list[TypesettingUnit],
        box: Box,
        scale: float,
        avg_height: float,
        line_skip: float,
        reference_widths: list[float] | None = None,
        paragraph: il_version_1.PdfParagraph | None = None,
    ) -> list[float]:
        """估算每行的可用宽度（用于 DP 断行优化）。

        S3 closed loop: each line width is the **same** multi-interval capacity
        that placement uses (sum of pockets after left ref-cap + first indent),
        not ``min(ref_w, sum(raw_pockets))`` which under-counted wrap-around.
        """
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
        align = (
            self._resolve_effective_alignment(
                paragraph,
                typesetting_units,
                ocr_workaround=bool(
                    getattr(self.translation_config, "ocr_workaround", False)
                ),
                is_cjk=bool(self.is_cjk),
            )
            if paragraph is not None
            else "left"
        )
        while y > box.y:
            capacity, _intervals = self._line_capacity_like_place(
                box=box,
                y_bottom=y,
                y_top=y + query_h,
                line_idx=line_idx,
                reference_widths=reference_widths,
                alignment=align,
                paragraph=paragraph,
                typesetting_units=typesetting_units,
                scale=scale,
            )
            widths.append(capacity)
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
        paragraph: il_version_1.PdfParagraph | None = None,
    ) -> list[int] | None:
        """计算 DP 优化的断行位置。失败时返回 None。"""
        line_widths = self._estimate_line_widths(
            typesetting_units, box, scale, avg_height, line_skip,
            reference_widths=reference_widths,
            paragraph=paragraph,
        )
        if not line_widths:
            return None

        return optimal_line_break(
            units=typesetting_units,
            line_widths=line_widths,
            scale=scale,
            space_width=space_width,
            decorative_tracking=decorative_tracking,
            # Explicit when typesetting to zh/ja/ko — do not rely only on auto-detect
            # of unit ratios (mixed Latin titles can mis-detect as non-CJK).
            cjk_mode=True if self.is_cjk else None,
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
        *,
        alignment: str | None = None,
    ) -> tuple[float, float]:
        """Cap line right edge using original EN line widths (artistic taper).

        Extra lines past the EN count reuse the median reference width so CJK
        does not spill a full rectangular column into a photo.

        Important: cap width from the **actual line start** (``available_x``),
        not only ``box.x``.  If an exclusion zone pushed ``available_x`` to the
        right of ``box.x``, using ``box.x + ref_w`` can make the cap fall
        *left* of the start and the old code fell back to the full residual —
        that put Orgasms p.21 Chinese mid-photo (x≈330) instead of the EN
        freeform column (x≈110).
        """
        if not reference_widths:
            return available_x, available_x2
        zone_w = available_x2 - available_x
        if zone_w <= 0:
            return available_x, available_x2

        ref_w = Typesetting._pick_reference_width(reference_widths, line_idx)
        if ref_w is None or ref_w < 12.0:
            return available_x, available_x2

        max_ref = max(w for w in reference_widths if w >= 12.0) if any(
            w >= 12.0 for w in reference_widths
        ) else max(reference_widths)

        # Left-aligned freeform body: if a zone shoved the start right of the
        # original paragraph left edge, snap back so we rebuild the EN column
        # at box.x rather than a mid-photo strip (Orgasms p.21).
        align = (alignment or "left").lower()
        line_start = available_x
        if (
            align == "left"
            and box.x is not None
            and available_x > box.x + 8.0
            and (box.x2 - box.x) >= ref_w * 0.8
        ):
            # Only snap when the original box can host the EN column
            line_start = box.x

        # Cap from the line start (after optional snap), and never past the
        # longest original EN line measured from the original box left.
        cap_x2 = min(available_x2, line_start + ref_w)
        if box.x is not None:
            cap_x2 = min(cap_x2, box.x + max_ref * 1.15)

        if cap_x2 >= line_start + 8:
            return line_start, cap_x2
        # Last resort: keep zone range but still try EN width from available_x
        cap2 = min(available_x2, available_x + ref_w)
        if cap2 >= available_x + 8:
            return available_x, cap2
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

        # Multi-interval pockets for this y-band (PR-06)
        zone_index = getattr(self, "_current_zone_index", None)
        if zone_index and zone_index.zones:
            logger.debug(
                f"Laying out paragraph with {len(zone_index.zones)} exclusion zones"
            )
        ocr_mode = bool(
            getattr(self.translation_config, "ocr_workaround", False)
        )
        alignment = self._resolve_effective_alignment(
            paragraph,
            typesetting_units,
            ocr_workaround=ocr_mode,
            is_cjk=bool(self.is_cjk),
        )
        query_h0 = avg_height if avg_height > 0 else 1.0
        intervals = self._query_line_intervals(current_y, current_y + query_h0, box)
        intervals = self._cap_leftmost_interval_with_reference(
            box,
            intervals,
            reference_widths,
            layout_line_idx,
            alignment=alignment,
        )
        # line 0: no list hang (marker sits at left edge)
        interval_idx = 0
        available_x, available_x2 = intervals[0]
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
        # Index into typeset_units where the current line starts; used to shift
        # completed lines for center/right alignment after left-to-right placement.
        line_start_idx = 0
        # Alignment uses the primary (leftmost) pocket only — spanning figure
        # gap would shift center/right lines into the hole (PR-06 review).
        line_available_x = intervals[0][0]
        line_available_x2 = intervals[0][1]
        # First-line indent: absolute user-space from box.x (PR-07).
        # Center/right skip indent; left body matches EN visual indent.
        # OCR: skip (noisy OCR edges → false indent on every para).
        if (
            not ocr_mode
            and alignment == "left"
            and self._parse_first_line_indent(paragraph) > 0
        ):
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

            # 跳过行首 / 区间首的空格
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
            # English lookahead packs "don't break mid-word" runs. On CJK / OCR
            # dual-layer it is harmful: kinsoku glues long unbreakable spans
            # (e.g. （1989年）) so remaining < unit+lookahead forces *early*
            # wraps → short tails like 「第11卷（」/「里），」 mid-sentence.
            ocr_mode = bool(
                getattr(self.translation_config, "ocr_workaround", False)
            )
            use_lookahead = (
                use_english_line_break
                and not ocr_mode
                and not self.is_cjk
            )
            if use_lookahead:
                width_before_next_break_point = self._get_width_before_next_break_point(
                    typesetting_units[i:], scale
                )
            else:
                width_before_next_break_point = 0

            # 如果当前行放不下这个元素，换行
            # Include tracking in width calculation for accurate line breaks
            effective_width = unit_width + (decorative_tracking if not unit.is_space else 0)
            # Multi-interval: try next pocket on the same y before wrapping
            advanced = self._try_advance_interval_for_unit(
                effective_width,
                intervals,
                interval_idx,
                current_x,
                available_x2,
            )
            if advanced is not None:
                interval_idx, available_x, available_x2, current_x = advanced
            fits_current = current_x + effective_width <= available_x2 + 1e-6
            remaining = self._remaining_capacity_on_line(
                current_x, intervals, interval_idx
            )
            # DP 断行：在指定位置强制断行；否则使用贪心判断
            # DP 断行仍需检查 hung punctuation 守卫
            dp_break = (
                break_points is not None
                and i in break_points
                and not unit.is_hung_punctuation
            )
            # Greedy wrap only when the unit cannot sit in the current pocket.
            # Skip English "2× open-paren" early wrap on CJK/OCR — that left
            # 「第11卷（」 alone on a line before 1989.
            need_break = dp_break or (
                not unit.is_hung_punctuation and (
                    (not fits_current)
                    or (
                        use_lookahead
                        and remaining
                        < effective_width + width_before_next_break_point - 1e-6
                    )
                    or (
                        (not ocr_mode)
                        and (not self.is_cjk)
                        and unit.is_cannot_appear_in_line_end_punctuation
                        and remaining < effective_width * 2 - 1e-6
                    )
                )
            )
            # Units re-emitted on the next line when we pull illegal EOL tails
            # (open paren / mid-word / mid-number) back off the finished line.
            pull_to_next: list[TypesettingUnit] = []
            if need_break and current_line_heights:
                # If breaking here would end the line after a non-breakable unit
                # (感|情, 第11卷（|1989), pull that tail onto the new line.
                while len(typeset_units) > line_start_idx:
                    tail = typeset_units[-1]
                    tail_ch = tail.try_get_unicode() or ""
                    illegal_eol = (not tail.can_break_line) or is_cjk_line_end_forbidden(
                        tail_ch
                    )
                    if not illegal_eol:
                        break
                    pull_to_next.append(typeset_units.pop())
                pull_to_next.reverse()
                if pull_to_next:
                    # Rebuild line height state after pull-back
                    current_line_heights = [
                        u.height
                        for u in typeset_units[line_start_idx:]
                        if not u.is_space
                    ]
                    if not current_line_heights:
                        # Whole line was an unbreakable run — put back and overflow
                        typeset_units.extend(pull_to_next)
                        pull_to_next = []
                        current_line_heights = [
                            u.height
                            for u in typeset_units[line_start_idx:]
                            if not u.is_space
                        ]
                        need_break = False
                        all_units_fit = False
                    else:
                        last_kept = typeset_units[-1]
                        current_x = last_kept.box.x2 if last_kept.box else available_x
                        last_unit = last_kept
                        line_height = max(current_line_heights)
            # CJK 孤行保护：如果当前行只有 ≤2 个字符就要换行，
            # 标记为需要特殊处理（由 DP 在后续优化中处理）
            # 注意：不在贪心循环中强制溢出，避免布局问题
            if need_break:
                # 换行
                if not current_line_heights:
                    # Nothing on this line yet — cannot wrap. English lookahead
                    # may set need_break while the unit still fits the current
                    # pocket; keep left residual in that case (do not snap to
                    # the rightmost pocket under the figure).
                    if fits_current:
                        pass  # fall through and place on current pocket
                    else:
                        # Find any pocket that can host this single unit
                        placed_in_pocket = False
                        for j, (jx1, jx2) in enumerate(intervals):
                            if effective_width <= (jx2 - jx1) + 1e-6:
                                interval_idx = j
                                available_x, available_x2 = jx1, jx2
                                current_x = jx1
                                placed_in_pocket = True
                                break
                        if not placed_in_pocket:
                            if not intervals:
                                return [], False
                            # Force-overflow on last pocket; mark scale retry
                            available_x, available_x2 = intervals[-1]
                            interval_idx = len(intervals) - 1
                            current_x = available_x
                            all_units_fit = False
                else:
                    # 检测 DP 模式下贪心是否插入了额外断行
                    if not dp_break and break_points is not None:
                        dp_break_mismatch = True
                    max_height = max(current_line_heights)
                    try:
                        mode_height = statistics.mode(current_line_heights)
                    except statistics.StatisticsError:
                        mode_height = sum(current_line_heights) / len(
                            current_line_heights
                        )

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

                    current_y -= line_advance_distance(
                        font_size, scale, line_skip, mode_height, max_height
                    )
                    line_ys.append(current_y)
                    line_height = 0.0
                    current_line_heights = []  # 清空当前行高度列表

                    # 动态行宽：多区间 residual + 左口袋 reference cap
                    zone_query_height = (
                        max(max_height, avg_height) if max_height > 0 else avg_height
                    )
                    if zone_query_height <= 0:
                        zone_query_height = 1.0
                    layout_line_idx += 1
                    intervals = self._query_line_intervals(
                        current_y, current_y + zone_query_height, box
                    )
                    intervals = self._cap_leftmost_interval_with_reference(
                        box,
                        intervals,
                        reference_widths,
                        layout_line_idx,
                        alignment=alignment,
                    )
                    # Numbered-list hang: shrink leftmost pocket so available_x
                    # is already the body column (same as capacity path / S3).
                    _ix1, _ix2 = intervals[0]
                    _hang = Typesetting._numbered_list_hang_inset(
                        paragraph,
                        typesetting_units,
                        scale,
                        line_idx=layout_line_idx,
                        alignment=alignment,
                        ocr_workaround=ocr_mode,
                        pocket_span=max(0.0, _ix2 - _ix1),
                    )
                    if _hang > 0:
                        intervals = Typesetting._inset_leftmost_interval(
                            intervals, _hang
                        )
                    interval_idx = 0
                    available_x, available_x2 = intervals[0]
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
                        _diag_path = _os.environ.get(
                            "BABELDOC_DIAG_LOG", "/tmp/babeldoc_diag.log"
                        )
                        with open(_diag_path, "a", encoding="utf-8") as _f:
                            _f.write(
                                f"  LINE_BREAK y={current_y:.1f} "
                                f"intervals={[(round(a,1), round(b,1)) for a, b in intervals]} "
                                f"prev={_prev_chars!r} next={_next_chars!r}\n"
                            )
                    # === END DIAGNOSTIC ===
                    current_x = available_x
                    line_available_x = intervals[0][0]
                    line_available_x2 = intervals[0][1]

                    # 检查是否超出底部边界
                    # if current_y - unit_height < box.y:
                    if current_y < box.y:
                        all_units_fit = False
                        # 这里不要 break，继续排版剩余内容

                    # Re-place units pulled off the previous line (e.g. 「（」 before 1989).
                    # Already relocated once — only shift geometry, never re-scale.
                    for pu in pull_to_next:
                        pu_w = pu.width  # already scaled by prior relocate
                        pu_h = pu.height
                        advanced_p = self._try_advance_interval_for_unit(
                            pu_w,
                            intervals,
                            interval_idx,
                            current_x,
                            available_x2,
                        )
                        if advanced_p is not None:
                            interval_idx, available_x, available_x2, current_x = advanced_p
                        old_x = pu.box.x if pu.box else current_x
                        old_y = pu.box.y if pu.box else current_y
                        pu.shift_x(current_x - old_x)
                        pu.shift_y(current_y - old_y)
                        typeset_units.append(pu)
                        if not pu.is_space:
                            current_line_heights.append(pu_h)
                        line_height = max(line_height, pu_h)
                        current_x = pu.box.x2 if pu.box else current_x + pu_w
                        last_unit = pu
                    pull_to_next = []

                    if unit.is_space:
                        line_height = max(line_height, unit_height)
                        continue

                    # After wrap, try advance again on the new line's pockets
                    advanced = self._try_advance_interval_for_unit(
                        effective_width,
                        intervals,
                        interval_idx,
                        current_x,
                        available_x2,
                    )
                    if advanced is not None:
                        interval_idx, available_x, available_x2, current_x = advanced
                    elif current_x + effective_width > available_x2 + 1e-6:
                        # Still no pocket: prefer any later pocket that fits,
                        # else force-overflow on last.
                        forced = False
                        for j, (jx1, jx2) in enumerate(intervals):
                            if effective_width <= (jx2 - jx1) + 1e-6:
                                interval_idx = j
                                available_x, available_x2 = jx1, jx2
                                current_x = jx1
                                forced = True
                                break
                        if not forced:
                            available_x, available_x2 = intervals[-1]
                            interval_idx = len(intervals) - 1
                            current_x = available_x
                            all_units_fit = False

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
            logger.info(
                "DP_REJECT reason=extra_greedy_breaks "
                "debug_id=%s n_placed=%s (S3 width loop mismatch)",
                getattr(paragraph, "debug_id", None),
                len(typeset_units),
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
                    # Skip C0 controls (esp. U+0001 SOH) — they render as
                    # empty standalone spans in dual PDFs (Orgasms ~63 hits).
                    def _keep_glyph(ch: str) -> bool:
                        if ch in ("\n", "\r"):
                            return False
                        if ch == "\t":
                            return True
                        o = ord(ch)
                        return not (o < 32 or o == 127 or 0x80 <= o <= 0x9F)

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
                            if _keep_glyph(char_unicode)
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
