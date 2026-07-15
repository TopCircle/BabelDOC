import logging
import math
import re
import unicodedata
from typing import Literal

import regex
from pymupdf import Font

from babeldoc.format.pdf.document_il import GraphicState
from babeldoc.format.pdf.document_il import il_version_1
from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraphComposition

logger = logging.getLogger(__name__)
# HEIGHT_NOT_USFUL_CHAR_IN_CHAR = (
#     "∑︁",
#     # 暂时假设 cid:17 和 cid 16 是特殊情况
#     # 来源于 arXiv:2310.18608v2 第九页公式大括号
#     "(cid:17)",
#     "(cid:16)",
#     # arXiv:2411.19509v2 第四页 []
#     "(cid:104)",
#     "(cid:105)",
#     # arXiv:2411.19509v2 第四页 公式的 | 竖线
#     "(cid:13)",
#     "∑︁",
#     # arXiv:2412.05265 27 页 累加号
#     "(cid:88)",
#     # arXiv:2412.05265 16 页 累乘号
#     "(cid:89)",
#     # arXiv:2412.05265 27 页 积分
#     "(cid:90)",
#     # arXiv:2412.05265 32 页 公式左右的中括号
#     "(cid:2)",
#     "(cid:3)",
#     "·",
#     "√",
# )

# 由于我们有一套 bbox 解析机制了，所以现在不需要这个东西了。
HEIGHT_NOT_USFUL_CHAR_IN_CHAR = (None,)


LEFT_BRACKET = ("(cid:8)", "(", "(cid:16)", "{", "[", "(cid:104)", "(cid:2)")
RIGHT_BRACKET = ("(cid:9)", ")", "(cid:17)", "}", "]", "(cid:105)", "(cid:3)")

BULLET_POINT_PATTERN = re.compile(
    r"[■•⚫⬤◆◇○●◦‣⁃▪▫∗†‡¹²³⁴⁵⁶⁷⁸⁹⁰₁₂₃₄₅₆₇₈₉₀ᵃᵇᶜᵈᵉᶠᵍʰⁱʲᵏˡᵐⁿᵒᵖʳˢᵗᵘᵛʷˣʸᶻ¶※⁑⁂⁕⁎⁜❧☙⁋‖‽·]"
)


def is_bullet_point(char: PdfCharacter) -> bool:
    """Check if the character is a bullet point.

    Args:
        char: The character to check

    Returns:
        bool: True if the character is a bullet point
    """
    is_bullet = bool(BULLET_POINT_PATTERN.match(char.char_unicode))
    return is_bullet


def calculate_box_iou(box1: Box, box2: Box) -> float:
    """Calculate the Intersection over Union (IOU) between two boxes.

    Args:
        box1: First box
        box2: Second box

    Returns:
        float: IOU value between 0 and 1
    """
    if box1 is None or box2 is None:
        return 0.0

    # Calculate intersection
    x_left = max(box1.x, box2.x)
    y_top = max(box1.y, box2.y)
    x_right = min(box1.x2, box2.x2)
    y_bottom = min(box1.y2, box2.y2)

    # Check if there's no intersection
    if x_left >= x_right or y_top >= y_bottom:
        return 0.0

    # Calculate intersection area
    intersection_area = (x_right - x_left) * (y_bottom - y_top)

    # Calculate areas of both boxes
    box1_area = (box1.x2 - box1.x) * (box1.y2 - box1.y)
    box2_area = (box2.x2 - box2.x) * (box2.y2 - box2.y)

    # Calculate union area
    union_area = box1_area + box2_area - intersection_area

    # Avoid division by zero
    if union_area <= 0:
        return 0.0

    return intersection_area / union_area


def formular_height_ignore_char(char: PdfCharacter):
    return (
        char.pdf_character_id is None
        or char.char_unicode in HEIGHT_NOT_USFUL_CHAR_IN_CHAR
    )


def box_to_tuple(box: Box) -> tuple[float, float, float, float]:
    """Converts a Box object to a tuple of its coordinates."""
    if box is None:
        return (0, 0, 0, 0)
    return (box.x, box.y, box.x2, box.y2)


class Layout:
    def __init__(self, layout_id, name):
        self.id = layout_id
        self.name = name

    @staticmethod
    def is_newline(prev_char: PdfCharacter, curr_char: PdfCharacter) -> bool:
        # 如果没有前一个字符，不是换行
        if prev_char is None:
            return False

        # 获取两个字符的中心 y 坐标
        # prev_y = (prev_char.box.y + prev_char.box.y2) / 2
        # curr_y = (curr_char.box.y + curr_char.box.y2) / 2

        # 如果当前字符的 y 坐标明显低于前一个字符，说明换行了
        # 这里使用字符高度的一半作为阈值
        char_height = max(
            curr_char.box.y2 - curr_char.box.y,
            prev_char.box.y2 - prev_char.box.y,
        )
        char_width = max(
            curr_char.box.x2 - curr_char.box.x,
            prev_char.box.x2 - prev_char.box.x,
        )
        should_new_line = (
            curr_char.box.y2 < prev_char.box.y
            or curr_char.box.x2 < prev_char.box.x - char_width * 10
        )
        if should_new_line and (
            formular_height_ignore_char(curr_char)
            or formular_height_ignore_char(prev_char)
        ):
            return False
        return should_new_line


def get_paragraph_length_except(
    paragraph: PdfParagraph,
    except_chars: str,
    font: Font,
) -> int:
    length = 0
    for composition in paragraph.pdf_paragraph_composition:
        if composition.pdf_character:
            length += (
                composition.pdf_character[0].box.x2 - composition.pdf_character[0].box.x
            )
        elif composition.pdf_same_style_characters:
            for pdf_char in composition.pdf_same_style_characters.pdf_character:
                if pdf_char.char_unicode in except_chars:
                    continue
                length += pdf_char.box.x2 - pdf_char.box.x
        elif composition.pdf_same_style_unicode_characters:
            for char_unicode in composition.pdf_same_style_unicode_characters.unicode:
                if char_unicode in except_chars:
                    continue
                length += font.char_lengths(
                    char_unicode,
                    composition.pdf_same_style_unicode_characters.pdf_style.font_size,
                )[0]
        elif composition.pdf_line:
            for pdf_char in composition.pdf_line.pdf_character:
                if pdf_char.char_unicode in except_chars:
                    continue
                length += pdf_char.box.x2 - pdf_char.box.x
        elif composition.pdf_formula:
            length += composition.pdf_formula.box.x2 - composition.pdf_formula.box.x
        else:
            logger.error(
                f"Unknown composition type. "
                f"Composition: {composition}. "
                f"Paragraph: {paragraph}. ",
            )
            continue
    return length


def get_paragraph_unicode(paragraph: PdfParagraph) -> str:
    chars = []
    for composition in paragraph.pdf_paragraph_composition:
        if composition.pdf_line:
            chars.extend(composition.pdf_line.pdf_character)
        elif composition.pdf_same_style_characters:
            chars.extend(composition.pdf_same_style_characters.pdf_character)
        elif composition.pdf_same_style_unicode_characters:
            chars.extend(composition.pdf_same_style_unicode_characters.unicode)
        elif composition.pdf_formula:
            chars.extend(composition.pdf_formula.pdf_character)
        elif composition.pdf_character:
            chars.append(composition.pdf_character)
        else:
            logger.error(
                f"Unknown composition type. "
                f"Composition: {composition}. "
                f"Paragraph: {paragraph}. ",
            )
            continue
    return get_char_unicode_string(chars)


SPACE_REGEX = regex.compile(r"\s+", regex.UNICODE)


def get_char_unicode_string(chars: list[PdfCharacter | str]) -> str:
    """
    将字符列表转换为 Unicode 字符串，根据字符间距自动插入空格。
    有些 PDF 不会显式编码空格，这时需要根据间距自动插入空格。

    Space detection uses a character-width-relative threshold instead of
    a global median: a gap is treated as a word boundary when it exceeds
    40% of the wider of the two adjacent characters' widths.  Using the
    wider character avoids false positives from narrow chars (like 'r' at
    2pt) pulling the threshold too low next to wide chars (like 'e' at 5pt),
    which previously split words like "There" → "The re".

    Args:
        chars: 字符列表，可以是 PdfCharacter 对象或字符串

    Returns:
        str: 处理后的 Unicode 字符串
    """
    # Space threshold: gap must exceed this fraction of the wider character's
    # width.  Using max(w1,w2) instead of avg(w1,w2) prevents narrow characters
    # (e.g. 'r'=2pt beside 'e'=5pt) from pulling the threshold too low, which
    # would falsely split words like "There" → "The re".  Raised from 0.4 to
    # 0.5 to fix residual fragments like "li ke" (from "like") and "ther"
    # (from "There") caused by fonts with wider intra-word kerning.
    SPACE_WIDTH_RATIO = 0.5

    # Decorative text detection: skip space insertion for art layouts
    # like "G e n t l y" where gaps are intentionally large.
    skip_space_insertion = _is_decorative_text(
        [c for c in chars if isinstance(c, PdfCharacter)]
    )

    # 构建 unicode 字符串，根据间距插入空格
    unicode_chars = []
    for i in range(len(chars)):
        # 如果不是字符对象，直接添加，一般来说这个时候 chars[i] 是字符串
        if not isinstance(chars[i], PdfCharacter):
            unicode_chars.append(chars[i])
            continue

        # use unicode regex to replace all space with " "
        unicode_chars.append(
            regex.sub(
                r"\s+",
                " ",
                unicodedata.normalize("NFKC", chars[i].char_unicode),
            )
        )

        # 如果是空格，跳过
        if chars[i].char_unicode == " ":
            continue

        # 如果两个字符都是 PdfCharacter，检查间距
        if i < len(chars) - 1 and isinstance(chars[i + 1], PdfCharacter):
            distance = chars[i + 1].box.x - chars[i].box.x2
            if distance <= 0:
                continue
            curr_w = chars[i].box.x2 - chars[i].box.x
            next_w = chars[i + 1].box.x2 - chars[i + 1].box.x
            max_w = max(curr_w, next_w)
            if not skip_space_insertion and (
                (max_w > 0 and distance > max_w * SPACE_WIDTH_RATIO)
                or Layout.is_newline(chars[i], chars[i + 1])
            ):
                unicode_chars.append(" ")  # 添加空格

    result = "".join(unicode_chars)
    # Normalize inline whitespace: TAB, NBSP (U+00A0), em-space (U+2003),
    # en-space (U+2002), thin-space (U+2009), etc. → regular space.
    # NFKC handles most; explicit replacements catch the rest.
    result = result.replace("\t", " ")
    result = result.replace(" ", " ")  # NBSP
    result = result.replace(" ", " ")  # EN SPACE
    result = result.replace(" ", " ")  # EM SPACE
    result = result.replace(" ", " ")  # THIN SPACE
    result = result.replace("​", "")   # ZERO-WIDTH SPACE (remove)
    result = result.replace(" ", " ")  # NARROW NO-BREAK SPACE
    result = result.replace(" ", " ")  # MEDIUM MATHEMATICAL SPACE
    normalize = unicodedata.normalize("NFKC", result)
    result = SPACE_REGEX.sub(" ", normalize).strip()
    return result


def get_paragraph_max_height(paragraph: PdfParagraph) -> float:
    """
    获取段落中最高的排版单元高度。

    Args:
        paragraph: PDF 段落对象

    Returns:
        float: 最大高度值
    """
    max_height = 0.0
    for composition in paragraph.pdf_paragraph_composition:
        if composition is None:
            continue
        if composition.pdf_character:
            char_height = (
                composition.pdf_character[0].box.y2 - composition.pdf_character[0].box.y
            )
            max_height = max(max_height, char_height)
        elif composition.pdf_same_style_characters:
            for pdf_char in composition.pdf_same_style_characters.pdf_character:
                char_height = pdf_char.box.y2 - pdf_char.box.y
                max_height = max(max_height, char_height)
        elif composition.pdf_same_style_unicode_characters:
            # 对于纯 Unicode 字符，我们使用其样式中的字体大小作为高度估计
            font_size = (
                composition.pdf_same_style_unicode_characters.pdf_style.font_size
            )
            max_height = max(max_height, font_size)
        elif composition.pdf_line:
            for pdf_char in composition.pdf_line.pdf_character:
                char_height = pdf_char.box.y2 - pdf_char.box.y
                max_height = max(max_height, char_height)
        elif composition.pdf_formula:
            formula_height = (
                composition.pdf_formula.box.y2 - composition.pdf_formula.box.y
            )
            max_height = max(max_height, formula_height)
        else:
            logger.error(
                f"Unknown composition type. "
                f"Composition: {composition}. "
                f"Paragraph: {paragraph}. ",
            )
            continue
    return max_height


def is_same_style(style1, style2) -> bool:
    """判断两个样式是否相同"""
    if style1 is None or style2 is None:
        return style1 is style2

    return (
        style1.font_id == style2.font_id
        and math.fabs(style1.font_size - style2.font_size) < 0.02
        and is_same_graphic_state(style1.graphic_state, style2.graphic_state)
    )


def is_same_style_except_size(style1, style2) -> bool:
    """判断两个样式是否相同"""
    if style1 is None or style2 is None:
        return style1 is style2

    return (
        style1.font_id == style2.font_id
        and 0.7 < math.fabs(style1.font_size / style2.font_size) < 1.3
        and is_same_graphic_state(style1.graphic_state, style2.graphic_state)
    )


def is_same_style_except_font(style1, style2) -> bool:
    """判断两个样式是否相同"""
    if style1 is None or style2 is None:
        return style1 is style2

    return math.fabs(
        style1.font_size - style2.font_size,
    ) < 0.02 and is_same_graphic_state(style1.graphic_state, style2.graphic_state)


def is_same_graphic_state(state1: GraphicState, state2: GraphicState) -> bool:
    """判断两个 GraphicState 是否相同"""
    if state1 is None or state2 is None:
        return state1 is state2

    return (
        state1.passthrough_per_char_instruction
        == state2.passthrough_per_char_instruction
    )


def add_space_dummy_chars(paragraph: PdfParagraph) -> None:
    """
    在 PDF 段落中添加表示空格的 dummy 字符。
    这个函数会直接修改传入的 paragraph 对象，在需要空格的地方添加 dummy 字符。
    同时也会处理不同组成部分之间的空格。

    Args:
        paragraph: 需要处理的 PDF 段落对象
    """
    # 首先处理每个组成部分内部的空格
    for composition in paragraph.pdf_paragraph_composition:
        if composition.pdf_line:
            chars = composition.pdf_line.pdf_character
            _add_space_dummy_chars_to_list(chars)
        elif composition.pdf_same_style_characters:
            chars = composition.pdf_same_style_characters.pdf_character
            _add_space_dummy_chars_to_list(chars)
        elif composition.pdf_same_style_unicode_characters:
            # 对于 unicode 字符，不需要处理。
            # 这种类型只会出现在翻译好的结果中
            continue
        elif composition.pdf_formula:
            chars = composition.pdf_formula.pdf_character
            _add_space_dummy_chars_to_list(chars)

    # 然后处理组成部分之间的空格
    for i in range(len(paragraph.pdf_paragraph_composition) - 1):
        curr_comp = paragraph.pdf_paragraph_composition[i]
        next_comp = paragraph.pdf_paragraph_composition[i + 1]

        # 获取当前组成部分的最后一个字符
        curr_last_char = _get_last_char_from_composition(curr_comp)
        if not curr_last_char:
            continue

        # 获取下一个组成部分的第一个字符
        next_first_char = _get_first_char_from_composition(next_comp)
        if not next_first_char:
            continue

        # 检查两个组成部分之间是否需要添加空格
        # 使用与 _add_space_dummy_chars_to_list 一致的 width-relative 阈值
        distance = next_first_char.box.x - curr_last_char.box.x2
        if distance > 0:
            curr_w = curr_last_char.box.x2 - curr_last_char.box.x
            next_w = next_first_char.box.x2 - next_first_char.box.x
            max_w = max(curr_w, next_w)
            SPACE_WIDTH_RATIO = 0.5
            if not (max_w > 0 and distance > max_w * SPACE_WIDTH_RATIO):
                continue
            # 创建一个 dummy 字符作为空格
            space_box = Box(
                x=curr_last_char.box.x2,
                y=curr_last_char.box.y,
                x2=curr_last_char.box.x2 + distance,
                y2=curr_last_char.box.y2,
            )

            space_char = PdfCharacter(
                pdf_style=curr_last_char.pdf_style,
                box=space_box,
                char_unicode=" ",
                scale=curr_last_char.scale,
                advance=space_box.x2 - space_box.x,
                visual_bbox=il_version_1.VisualBbox(box=space_box),
            )

            # 将空格添加到当前组成部分的末尾
            if curr_comp.pdf_line:
                curr_comp.pdf_line.pdf_character.append(space_char)
            elif curr_comp.pdf_same_style_characters:
                curr_comp.pdf_same_style_characters.pdf_character.append(space_char)
            elif curr_comp.pdf_formula:
                curr_comp.pdf_formula.pdf_character.append(space_char)


def _get_first_char_from_composition(
    comp: PdfParagraphComposition,
) -> PdfCharacter | None:
    """获取组成部分的第一个字符"""
    if comp.pdf_line and comp.pdf_line.pdf_character:
        return comp.pdf_line.pdf_character[0]
    elif (
        comp.pdf_same_style_characters and comp.pdf_same_style_characters.pdf_character
    ):
        return comp.pdf_same_style_characters.pdf_character[0]
    elif comp.pdf_formula and comp.pdf_formula.pdf_character:
        return comp.pdf_formula.pdf_character[0]
    elif comp.pdf_character:
        return comp.pdf_character
    return None


def _get_last_char_from_composition(
    comp: PdfParagraphComposition,
) -> PdfCharacter | None:
    """获取组成部分的最后一个字符"""
    if comp.pdf_line and comp.pdf_line.pdf_character:
        return comp.pdf_line.pdf_character[-1]
    elif (
        comp.pdf_same_style_characters and comp.pdf_same_style_characters.pdf_character
    ):
        return comp.pdf_same_style_characters.pdf_character[-1]
    elif comp.pdf_formula and comp.pdf_formula.pdf_character:
        return comp.pdf_formula.pdf_character[-1]
    elif comp.pdf_character:
        return comp.pdf_character
    return None


def _is_decorative_text(chars: list[PdfCharacter]) -> bool:
    """Detect decorative/artistic text layouts like 'G e n t l y'.

    All conditions must hold simultaneously:
      1. ≥70% of characters are single letters (A, B, C...)
      2. ≥50% of inter-character gaps exceed 2× average char width
      3. Font size consistency: max/min ratio < 1.10 (±10%)
      4. Baseline consistency: max baseline spread < 1pt

    This prevents false positives on body text, mixed-font paragraphs,
    and vertically staggered art layouts.
    """
    if len(chars) < 3:
        return False

    pdf_chars = [c for c in chars if isinstance(c, PdfCharacter) and c.visual_bbox]
    if len(pdf_chars) < 3:
        return False

    # Condition 1: ≥70% single letters
    single_letter_count = sum(
        1 for c in pdf_chars
        if len((c.char_unicode or "").strip()) == 1
        and (c.char_unicode or "").strip().isalpha()
    )
    if single_letter_count / len(pdf_chars) < 0.7:
        return False

    # Condition 2: ≥50% large gaps (>2× avg char width)
    large_gap_count = 0
    total_gaps = 0
    for i in range(len(pdf_chars) - 1):
        c1, c2 = pdf_chars[i], pdf_chars[i + 1]
        gap = c2.visual_bbox.box.x - c1.visual_bbox.box.x2
        if gap <= 0:
            continue
        total_gaps += 1
        w1 = c1.visual_bbox.box.x2 - c1.visual_bbox.box.x
        w2 = c2.visual_bbox.box.x2 - c2.visual_bbox.box.x
        avg_w = (w1 + w2) / 2
        if avg_w > 0 and gap > avg_w * 2.0:
            large_gap_count += 1

    if total_gaps < 2 or large_gap_count / total_gaps < 0.5:
        return False

    # Condition 3: font size consistency (max/min ratio < 1.10)
    sizes = [c.pdf_style.font_size for c in pdf_chars if c.pdf_style and c.pdf_style.font_size]
    if sizes:
        min_s, max_s = min(sizes), max(sizes)
        if min_s > 0 and max_s / min_s > 1.10:
            return False

    # Condition 4: baseline consistency (max spread < 1pt)
    baselines = [c.visual_bbox.box.y for c in pdf_chars]
    if baselines and (max(baselines) - min(baselines)) > 1.0:
        return False

    return True


def compute_decorative_tracking(chars: list[PdfCharacter]) -> float | None:
    """Compute average letter-spacing (tracking) for decorative text.

    Returns the average inter-character gap in points, or None if not
    decorative or insufficient data.  Used to re-lay out translated text
    with matching visual rhythm.
    """
    pdf_chars = [c for c in chars if isinstance(c, PdfCharacter) and c.visual_bbox]
    if len(pdf_chars) < 2:
        return None

    gaps = []
    for i in range(len(pdf_chars) - 1):
        gap = pdf_chars[i + 1].visual_bbox.box.x - pdf_chars[i].visual_bbox.box.x2
        if gap > 0:
            gaps.append(gap)

    return sum(gaps) / len(gaps) if gaps else None


def _add_space_dummy_chars_to_list(chars: list[PdfCharacter]) -> None:
    """
    在字符列表中的适当位置添加表示空格的 dummy 字符。

    使用基于字符宽度的相对阈值（与 get_char_unicode_string 一致），
    而非全局中位数。避免窄字符（如 'r'=2pt）拉低阈值导致
    "There" → "The re" 的错误拆分。

    Args:
        chars: PdfCharacter 对象列表
    """
    if not chars:
        return

    # Decorative text detection: "G e n t l y", "C O N T E N T S", "D A Y"
    # Pattern: most characters are single letters with gaps >> char width.
    # If detected, skip space insertion entirely — these are art layouts,
    # not word boundaries.
    if _is_decorative_text(chars):
        return

    # Space threshold: gap must exceed this fraction of the wider character's
    # width, matching get_char_unicode_string's approach.
    SPACE_WIDTH_RATIO = 0.5

    i = 0
    while i < len(chars) - 1:
        curr_char = chars[i]
        next_char = chars[i + 1]

        distance = next_char.box.x - curr_char.box.x2
        if distance <= 0:
            i += 1
            continue

        curr_w = curr_char.box.x2 - curr_char.box.x
        next_w = next_char.box.x2 - next_char.box.x
        max_w = max(curr_w, next_w)

        if (max_w > 0 and distance > max_w * SPACE_WIDTH_RATIO) or Layout.is_newline(
            curr_char, next_char
        ):
            # 创建一个 dummy 字符作为空格
            space_box = Box(
                x=curr_char.box.x2,
                y=curr_char.box.y,
                x2=curr_char.box.x2 + distance,
                y2=curr_char.box.y2,
            )

            space_char = PdfCharacter(
                pdf_style=curr_char.pdf_style,
                box=space_box,
                char_unicode=" ",
                scale=curr_char.scale,
                advance=space_box.x2 - space_box.x,
                visual_bbox=il_version_1.VisualBbox(box=space_box),
            )

            # 在当前位置后插入空格字符
            chars.insert(i + 1, space_char)
            i += 2  # 跳过刚插入的空格
        else:
            i += 1


def build_layout_index(page):
    """Builds an R-tree index for all layouts on the page."""
    from rtree import index

    layout_index = index.Index()
    layout_map = {}
    for i, layout in enumerate(page.page_layout):
        layout_map[i] = layout
        if layout.box:
            layout_index.insert(i, box_to_tuple(layout.box))
    return layout_index, layout_map


def calculate_iou_for_boxes(box1: Box, box2: Box) -> float:
    """Calculate the intersection area divided by the first box area."""
    x_left = max(box1.x, box2.x)
    y_bottom = max(box1.y, box2.y)
    x_right = min(box1.x2, box2.x2)
    y_top = min(box1.y2, box2.y2)

    if x_right <= x_left or y_top <= y_bottom:
        return 0.0

    # Calculate intersection area
    intersection_area = (x_right - x_left) * (y_top - y_bottom)

    # Calculate area of first box
    first_box_area = (box1.x2 - box1.x) * (box1.y2 - box1.y)

    # Return intersection divided by first box area, handle division by zero
    if first_box_area <= 0:
        return 0.0

    return intersection_area / first_box_area


def calculate_y_iou_for_boxes(box1: Box, box2: Box) -> float:
    """Calculate the intersection ratio in y-axis direction divided by the first box height.

    Args:
        box1: First box
        box2: Second box

    Returns:
        float: Intersection ratio in y-axis direction between 0 and 1
    """
    y_bottom = max(box1.y, box2.y)
    y_top = min(box1.y2, box2.y2)

    if y_top <= y_bottom:
        return 0.0

    # Calculate intersection height
    intersection_height = y_top - y_bottom

    # Calculate height of first box
    first_box_height = box1.y2 - box1.y

    # Return intersection divided by first box height, handle division by zero
    if first_box_height <= 0:
        return 0.0

    return intersection_height / first_box_height


def calculate_y_true_iou_for_boxes(box1: Box, box2: Box) -> float:
    """Calculate the intersection ratio in y-axis direction divided by the first box height.

    Args:
        box1: First box
        box2: Second box

    Returns:
        float: Intersection ratio in y-axis direction between 0 and 1
    """
    y_bottom = max(box1.y, box2.y)
    y_top = min(box1.y2, box2.y2)

    if y_top <= y_bottom:
        return 0.0

    # Calculate intersection height
    intersection_height = y_top - y_bottom

    # Calculate height of first box
    first_box_height = box1.y2 - box1.y
    second_box_height = box2.y2 - box2.y

    min_height = min(first_box_height, second_box_height)

    # Return intersection divided by first box height, handle division by zero
    if first_box_height <= 0:
        return 0.0

    return intersection_height / min_height


def get_character_layout(
    char,
    layout_index,
    layout_map,
    layout_priority=None,
    _bbox_mode: Literal["auto", "visual", "box"] = "auto",
):
    """Get the layout for a character based on priority and IoU."""
    if layout_priority is None:
        layout_priority = [
            "number",
            "reference",
            "reference_content",
            "algorithm",
            "formula_caption",
            "isolate_formula",
            "table_footnote",
            "table_caption",
            "figure_caption",
            "figure_title",
            "chart_title",
            "table_title",
            "table_cell_hybrid",
            "table_text",
            "wireless_table_cell",
            "wired_table_cell",
            "abandon",
            "title",
            "abstract",
            "paragraph_title",
            "content",
            "doc_title",
            "footnote",
            "header",
            "footer",
            "seal",
            "plain text",
            "tiny text",
            "author_info_hybrid",
            "list_item_hybrid",
            "text",
            "paragraph_hybrid",
            "paragraph",
            "table_cell",
            "figure_text",
            "list_item",
            "title",
            "caption",
            "footnote_hybrid",
            "footnote",
            "formula",
            "formula_hybrid",
            "page_header",
            "page_footer",
            # --- hybrid labels ---
            "reference_hybrid",
            "document_hybrid",
            "academic_paper_hybrid",
            "form_or_table_hybrid",
            "presentation_slide_hybrid",
            "webpage_screenshot_hybrid",
            "manga_or_comic_hybrid",
            "advertisement_hybrid",
            "magazine_or_newspaper_hybrid",
            "other_hybrid",
            "table_cell_hybrid",
            "figure_text_hybrid",
            "title_hybrid",
            "caption_hybrid",
            "code_algo_hybrid",
            "line_number_hybrid",
            "page_header_hybrid",
            "page_footer_hybrid",
            "page_number_hybrid",
            "unknown_hybrid",
            "fallback_line",
            "table",
            "figure",
            "image",
        ]

    char_box = char.visual_bbox.box
    # char_box2 = char.box
    # if bbox_mode == "auto":
    #     # Calculate IOU to decide which box to use
    #     intersection_area = max(
    #         0, min(char_box.x2, char_box2.x2) - max(char_box.x, char_box2.x)
    #     ) * max(0, min(char_box.y2, char_box2.y2) - max(char_box.y, char_box2.y))
    #     char_box_area = (char_box.x2 - char_box.x) * (char_box.y2 - char_box.y)
    #
    #     if char_box_area > 0:
    #         iou = intersection_area / char_box_area
    #         if iou < 0.2:
    #             char_box = char_box2
    # elif bbox_mode == "box":
    #     char_box = char_box2

    # Collect all intersecting layouts and their IoU values
    matching_layouts = []
    candidate_ids = list(layout_index.intersection(box_to_tuple(char_box)))
    candidate_layouts = [layout_map[i] for i in candidate_ids]

    for layout in candidate_layouts:
        # Calculate IoU
        intersection_area = max(
            0, min(char_box.x2, layout.box.x2) - max(char_box.x, layout.box.x)
        ) * max(0, min(char_box.y2, layout.box.y2) - max(char_box.y, layout.box.y))
        char_area = (char_box.x2 - char_box.x) * (char_box.y2 - char_box.y)

        if char_area > 0:
            iou = intersection_area / char_area
            if iou > 0:
                matching_layouts.append(
                    {
                        "layout": Layout(layout.id, layout.class_name),
                        "priority": (
                            layout_priority.index(layout.class_name)
                            if layout.class_name in layout_priority
                            else len(layout_priority)
                        ),
                        "iou": iou,
                    }
                )

    if not matching_layouts:
        return None

    # Sort by priority (ascending) and IoU value (descending)
    matching_layouts.sort(key=lambda x: (x["priority"], -x["iou"]))

    # non_hybrid_table_label = None
    # for layout in matching_layouts:
    #     layout = layout["layout"]
    #     label = layout.name
    #     if is_text_layout(layout) and label not in (
    #         "table_cell_hybrid",
    #         "table_text",
    #         "wireless_table_cell",
    #         "wired_table_cell",
    #         "fallback_line",
    #         "unknown_hybrid",
    #     ):
    #         non_hybrid_table_label = layout
    #         break
    #
    # if non_hybrid_table_label:
    #     return non_hybrid_table_label

    return matching_layouts[0]["layout"]


def is_text_layout(layout: Layout):
    """Check if a layout is a text layout."""
    return layout is not None and layout.name in [
        "plain text",
        "tiny text",
        "title",
        "abandon",
        "figure_caption",
        "table_caption",
        "table_text",
        "table_footnote",
        # "reference",
        "title",
        "paragraph_title",
        "abstract",
        "content",
        "figure_title",
        "table_title",
        "doc_title",
        "footnote",
        "header",
        "footer",
        "seal",
        "text",
        "chart_title",
        "paragraph",
        "table_cell",
        "figure_text",
        "list_item",
        "title",
        "caption",
        "footnote",
        "page_header",
        "page_footer",
        "wired_table_cell",
        "wireless_table_cell",
        "paragraph_hybrid",
        "table_cell_hybrid",
        "caption_hybrid",
        "unknown_hybrid",
        "figure_text_hybrid",
        "list_item_hybrid",
        "title_hybrid",
        "fallback_line",
        "author_info_hybrid",
        "page_header_hybrid",
        "page_footer_hybrid",
        "footnote_hybrid",
    ]


def is_character_in_formula_layout(
    char: il_version_1.PdfCharacter,
    _page: il_version_1.Page,
    layout_index,
    layout_map,
) -> int | None:
    """Check if character is contained within any formula-related layout."""
    formula_layout_types = {"formula"}

    char_box = char.visual_bbox.box
    char_box2 = char.box

    if calculate_iou_for_boxes(char_box, char_box2) < 0.2:
        char_box = char_box2

    # Get all candidate layouts that intersect with the character
    candidate_ids = list(layout_index.intersection(box_to_tuple(char_box)))
    candidate_layouts: list[il_version_1.PageLayout] = [
        layout_map[i] for i in candidate_ids
    ]

    # Check if any intersecting layout is a formula type
    for layout in candidate_layouts:
        if layout.class_name in formula_layout_types:
            iou = calculate_iou_for_boxes(char_box, layout.box)
            if iou > 0.4:  # Character has overlap with formula layout
                return layout.id

    return None


def is_curve_in_figure_table_layout(
    curve, layout_index, layout_map, protection_threshold: float = 0.3
) -> bool:
    """Check if curve is within figure/table layout areas.

    Args:
        curve: The curve object to check
        layout_index: Spatial index for layouts
        layout_map: Mapping from layout IDs to layout objects
        protection_threshold: IoU threshold for figure/table protection

    Returns:
        True if curve is within figure/table layout areas
    """
    if not curve.box:
        return False

    # Figure/table related layout types
    figure_table_layouts = {
        "figure",
        "table",
        "figure_text",
        "table_text",
        "figure_caption",
        "table_caption",
        "figure_title",
        "table_title",
        "chart_title",
        "table_cell",
        "table_cell_hybrid",
        "wired_table_cell",
        "wireless_table_cell",
        "table_footnote",
    }

    # Get candidate layouts that intersect with curve
    candidate_ids = list(layout_index.intersection(box_to_tuple(curve.box)))
    candidate_layouts = [layout_map[i] for i in candidate_ids]

    for layout in candidate_layouts:
        if layout.class_name in figure_table_layouts:
            # Check if curve has significant overlap with figure/table layout
            iou = calculate_iou_for_boxes(curve.box, layout.box)
            if iou > protection_threshold:
                return True

    return False


def is_curve_overlapping_with_paragraphs(
    curve, paragraphs: list, overlap_threshold: float = 0.2
) -> bool:
    """Check if curve overlaps with text paragraph areas.

    Args:
        curve: The curve object to check
        paragraphs: List of paragraph objects
        overlap_threshold: IoU threshold for paragraph overlap detection

    Returns:
        True if curve overlaps with any paragraph area
    """
    if not curve.box:
        return False

    for paragraph in paragraphs:
        para_box = get_paragraph_bounding_box(paragraph)
        if para_box:
            iou = calculate_iou_for_boxes(curve.box, para_box)
            if iou > overlap_threshold:
                return True

    return False


def get_paragraph_bounding_box(paragraph) -> Box | None:
    """Calculate the bounding box of a paragraph from its compositions.

    Args:
        paragraph: The paragraph object

    Returns:
        Box object representing the paragraph bounds, or None if no valid bounds
    """
    if not paragraph.pdf_paragraph_composition:
        return None

    min_x = float("inf")
    min_y = float("inf")
    max_x = float("-inf")
    max_y = float("-inf")

    has_valid_box = False

    for composition in paragraph.pdf_paragraph_composition:
        comp_box = None

        if composition.pdf_line and composition.pdf_line.box:
            comp_box = composition.pdf_line.box
        elif composition.pdf_formula and composition.pdf_formula.box:
            comp_box = composition.pdf_formula.box
        elif (
            composition.pdf_same_style_characters
            and composition.pdf_same_style_characters.box
        ):
            comp_box = composition.pdf_same_style_characters.box
        elif composition.pdf_character and len(composition.pdf_character) > 0:
            # Calculate box from character list
            char_boxes = [
                char.visual_bbox.box
                for char in composition.pdf_character
                if char.visual_bbox and char.visual_bbox.box
            ]
            if char_boxes:
                comp_min_x = min(box.x for box in char_boxes)
                comp_min_y = min(box.y for box in char_boxes)
                comp_max_x = max(box.x2 for box in char_boxes)
                comp_max_y = max(box.y2 for box in char_boxes)
                comp_box = Box(comp_min_x, comp_min_y, comp_max_x, comp_max_y)

        if comp_box:
            min_x = min(min_x, comp_box.x)
            min_y = min(min_y, comp_box.y)
            max_x = max(max_x, comp_box.x2)
            max_y = max(max_y, comp_box.y2)
            has_valid_box = True

    if not has_valid_box:
        return None

    return Box(min_x, min_y, max_x, max_y)


def _extract_chars_from_compositions(para: PdfParagraph) -> list:
    """Extract all characters from paragraph compositions.

    Handles pdf_line, pdf_character, pdf_same_style_characters, and pdf_formula.
    """
    chars = []
    for comp in para.pdf_paragraph_composition or []:
        if comp.pdf_line:
            chars.extend(comp.pdf_line.pdf_character or [])
        elif comp.pdf_character:
            chars.append(comp.pdf_character)
        elif comp.pdf_same_style_characters:
            chars.extend(comp.pdf_same_style_characters.pdf_character or [])
        elif comp.pdf_formula and comp.pdf_formula.pdf_character:
            chars.extend(comp.pdf_formula.pdf_character)
    return chars


def _cluster_chars_by_line(para: PdfParagraph) -> list[list]:
    """Cluster paragraph characters into visual lines by y-coordinate.

    Returns a list of char groups, one per visual line (top to bottom).
    Uses PdfLine compositions when available; falls back to y-clustering.
    """
    # Fast path: use PdfLine compositions directly
    pdf_lines = []
    has_non_line = False
    for comp in para.pdf_paragraph_composition or []:
        if comp.pdf_line:
            pdf_lines.append(comp.pdf_line)
        elif comp.pdf_character or comp.pdf_same_style_characters or comp.pdf_formula:
            has_non_line = True

    if pdf_lines and not has_non_line:
        # Pure PdfLine compositions — authoritative
        return [line.pdf_character or [] for line in pdf_lines]

    # Fallback: y-coordinate clustering
    all_chars = _extract_chars_from_compositions(para)
    all_chars = [
        c for c in all_chars
        if c.box and c.box.y is not None and c.box.y2 is not None
        and c.box.x is not None and c.box.x2 is not None
    ]
    if not all_chars:
        return []

    all_chars.sort(key=lambda c: -(c.box.y + c.box.y2) / 2)

    heights = [c.box.y2 - c.box.y for c in all_chars if c.box.y2 > c.box.y]
    if not heights:
        return [all_chars]

    median_height = sorted(heights)[len(heights) // 2]
    threshold = median_height * 0.5

    clusters = [[all_chars[0]]]
    for i in range(1, len(all_chars)):
        prev_center = (all_chars[i - 1].box.y + all_chars[i - 1].box.y2) / 2
        curr_center = (all_chars[i].box.y + all_chars[i].box.y2) / 2
        if abs(prev_center - curr_center) > threshold:
            clusters.append([all_chars[i]])
        else:
            clusters[-1].append(all_chars[i])

    return clusters


def count_lines_from_compositions(para: PdfParagraph) -> int:
    """Count the number of visual lines in a paragraph.

    Uses PdfLine compositions when available (accurate).
    Falls back to y-coordinate clustering for other composition types.
    """
    # Count formula compositions (each counts as one line unit)
    formula_count = sum(
        1 for comp in para.pdf_paragraph_composition or []
        if comp.pdf_formula
    )

    clusters = _cluster_chars_by_line(para)
    if not clusters:
        return max(formula_count, 0)

    return max(formula_count, len(clusters))


def compute_per_line_widths(para: PdfParagraph) -> list[float]:
    """Compute the width of each line in a paragraph.

    Uses PdfLine.box when available. Falls back to char-based computation.
    """
    # Fast path: use PdfLine/PdfFormula box directly
    widths = []
    for comp in para.pdf_paragraph_composition or []:
        if comp.pdf_line and comp.pdf_line.box:
            widths.append(comp.pdf_line.box.x2 - comp.pdf_line.box.x)
        elif comp.pdf_formula and comp.pdf_formula.box:
            widths.append(comp.pdf_formula.box.x2 - comp.pdf_formula.box.x)

    if widths:
        return widths

    # Fallback: cluster chars by y, compute per-cluster width
    clusters = _cluster_chars_by_line(para)
    widths = []
    for cluster in clusters:
        if cluster:
            line_min_x = min(c.box.x for c in cluster)
            line_max_x = max(c.box.x2 for c in cluster)
            widths.append(line_max_x - line_min_x)

    return widths


def _line_x_ranges_from_para(para: PdfParagraph) -> list[tuple[float, float]]:
    """Return (x_min, x_max) for each visual line in the paragraph."""
    ranges: list[tuple[float, float]] = []

    # Prefer PdfLine boxes when available and pure-line
    pdf_line_ranges = []
    has_non_line = False
    for comp in para.pdf_paragraph_composition or []:
        if comp.pdf_line and comp.pdf_line.box:
            b = comp.pdf_line.box
            pdf_line_ranges.append((b.x, b.x2))
        elif comp.pdf_character or comp.pdf_same_style_characters or comp.pdf_formula:
            has_non_line = True

    if pdf_line_ranges and not has_non_line:
        return pdf_line_ranges

    clusters = _cluster_chars_by_line(para)
    for cluster in clusters:
        valid = [
            c
            for c in cluster
            if c.box and c.box.x is not None and c.box.x2 is not None
        ]
        if not valid:
            continue
        ranges.append(
            (min(c.box.x for c in valid), max(c.box.x2 for c in valid))
        )
    return ranges


def detect_paragraph_alignment(
    para: PdfParagraph,
    page=None,
    *,
    edge_tolerance: float = 8.0,
    page_center_tolerance: float = 20.0,
) -> str:
    """Detect horizontal alignment from original paragraph geometry.

    Prefer edge consistency over "L≈R within bbox" (which falsely marks
    left-aligned body text as center: full lines have lm≈rm≈0, and a short
    last line creates width variation).

    Multi-line rules (priority):
      1. Line left edges cluster  → left
      2. Line right edges cluster → right
      3. Line centers cluster AND short lines are inset on both sides → center

    Single-line / fallback:
      - page-centered short line → center
      - default → left

    Note: layout_label == "title" is NOT forced to center. Many ebooks use
    left-aligned section headings that DocLayout still labels "title"; forcing
    center made those headings (and short labels like "IMPORTANT NOTE:") float
    to the middle of their original wide box after translation.

    Returns:
        One of "left", "center", "right".
    """
    line_ranges = _line_x_ranges_from_para(para)
    if not line_ranges:
        return "left"

    para_left = min(x for x, _ in line_ranges)
    para_right = max(x2 for _, x2 in line_ranges)
    para_width = para_right - para_left
    if para_width <= 1:
        return "left"

    tol = max(edge_tolerance, para_width * 0.03)
    n = len(line_ranges)
    lefts = [x for x, _ in line_ranges]
    rights = [x2 for _, x2 in line_ranges]
    centers = [(x + x2) / 2.0 for x, x2 in line_ranges]
    widths = [x2 - x for x, x2 in line_ranges]
    max_w = max(widths)

    def _cluster_ratio(values: list[float], ref: float) -> float:
        if not values:
            return 0.0
        return sum(1 for v in values if abs(v - ref) <= tol) / len(values)

    if n >= 2:
        # 1) Shared left edge → left-aligned body (most common)
        # Use the leftmost edge as reference (flush-left column).
        # Slightly lenient (0.65): InDesign ebooks often have one wrap line
        # inset by a few points without being true center text.
        left_ratio = _cluster_ratio(lefts, para_left)
        if left_ratio >= 0.65:
            return "left"

        # 2) Shared right edge → right-aligned
        right_ratio = _cluster_ratio(rights, para_right)
        if right_ratio >= 0.7:
            return "right"

        # 3) Shared centers + short lines inset both sides → center
        # Median center is robust when one line is an outlier
        sorted_centers = sorted(centers)
        mid_c = sorted_centers[len(sorted_centers) // 2]
        center_ratio = _cluster_ratio(centers, mid_c)
        if center_ratio >= 0.75:
            # Longest line nearly fills the paragraph span → body, not
            # a centered pull-quote/title block (Orgasms p.11 step body).
            if max_w >= para_width * 0.85 and left_ratio >= 0.4:
                return "left"

            # Require at least one clearly short line that is inset on BOTH
            # sides. Full lines always have lm≈rm≈0 and must not alone prove
            # center (that was the body-text false positive).
            short_both_inset = 0
            short_total = 0
            for x, x2 in line_ranges:
                w = x2 - x
                if w >= max_w * 0.9:
                    continue  # nearly full-width line
                short_total += 1
                lm = x - para_left
                rm = para_right - x2
                if lm > tol and rm > tol and abs(lm - rm) <= tol * 2:
                    short_both_inset += 1
            # Need a clear majority of short lines inset both sides
            if short_total >= 2 and short_both_inset >= max(2, int(short_total * 0.6)):
                return "center"
            # Centers align but short lines flush-left → still left
            return "left"

    # Single-line or ambiguous multi-line: use page geometry
    if page is not None:
        page_box = None
        if getattr(page, "cropbox", None) and page.cropbox.box:
            page_box = page.cropbox.box
        elif getattr(page, "mediabox", None) and page.mediabox.box:
            page_box = page.mediabox.box
        if page_box and page_box.x2 > page_box.x:
            page_center = (page_box.x + page_box.x2) / 2.0
            page_width = page_box.x2 - page_box.x
            all_centered = True
            for x, x2 in line_ranges:
                line_center = (x + x2) / 2.0
                line_width = x2 - x
                if abs(line_center - page_center) > page_center_tolerance:
                    all_centered = False
                    break
                # Near-full-page lines are body text, not centered titles
                if line_width > page_width * 0.85:
                    all_centered = False
                    break
            if all_centered:
                return "center"

    return "left"


def compute_reference_metrics(para: PdfParagraph, page=None):
    """Compute and attach ReferenceMetrics to a paragraph.

    Call this AFTER ParagraphFinder, BEFORE ILTranslator.
    Requires para.box and para.pdf_paragraph_composition to be set.

    Also detects and stores para.alignment from original geometry.
    """
    from babeldoc.format.pdf.document_il.il_version_1 import ReferenceMetrics

    if not para.box or not para.pdf_paragraph_composition:
        return

    width = para.box.x2 - para.box.x
    if width <= 0:
        return

    line_count = count_lines_from_compositions(para)
    per_line_widths = compute_per_line_widths(para)

    avg_line_width = sum(per_line_widths) / len(per_line_widths) if per_line_widths else width
    last_line_width = per_line_widths[-1] if per_line_widths else width
    last_line_ratio = last_line_width / avg_line_width if avg_line_width > 0 else 1.0

    # Compute font size mode from characters
    font_sizes = []
    for comp in para.pdf_paragraph_composition or []:
        chars = []
        if comp.pdf_line:
            chars = comp.pdf_line.pdf_character or []
        elif comp.pdf_character:
            chars = [comp.pdf_character]
        elif comp.pdf_same_style_characters:
            chars = comp.pdf_same_style_characters.pdf_character or []
        for c in chars:
            if c.pdf_style and c.pdf_style.font_size is not None:
                font_sizes.append(c.pdf_style.font_size)

    if font_sizes:
        import statistics
        try:
            font_size = statistics.mode(font_sizes)
        except statistics.StatisticsError:
            font_size = statistics.median(font_sizes)
    else:
        font_size = 0.0

    para.reference_metrics = ReferenceMetrics(
        line_count=line_count,
        avg_line_width=avg_line_width,
        last_line_width=last_line_width,
        last_line_ratio=last_line_ratio,
        font_size=font_size,
        per_line_widths=per_line_widths,
    )

    # Capture alignment from original geometry (before translation)
    try:
        para.alignment = detect_paragraph_alignment(para, page)
    except Exception:
        para.alignment = "left"


def is_quote_block(
    para: PdfParagraph,
    page_width: float,
    *,
    narrow_threshold: float = 0.8,
    indent_threshold: float = 0.15,
    right_margin_threshold: float = 0.05,
) -> bool:
    """启发式判断段落是否为 Quote（引文框 / pull-quote）块。

    Quote 块的典型特征：
    1. 段落宽度明显窄于页面宽度（两侧有留白）
    2. 左侧有明显缩进（显著大于正文页边距）
    3. 右侧有明显留白
    4. 不是「左侧绕排正文」：与浮动块并排的左栏正文虽窄，但左缘贴正文页边

    错误地把左栏绕排正文当成 Quote 会导致 ExclusionZone 把可用宽度推到
    右侧，上一整段溢出时出现「半行在左、半行跳到右」的旁绕排崩坏
    （见 Longer Stronger Orgasms p.5）。

    Args:
        para: 要判断的段落
        page_width: 页面宽度（cropbox.x2 - cropbox.x）
        narrow_threshold: 段落宽度 / 页面宽度 < 此值视为窄段落
        indent_threshold: 左侧缩进 / 页面宽度 > 此值视为有缩进。
            默认 0.15：过滤 ~5–12% 的正文页边距，保留真正的 pull-quote
            （通常 indent ≳ 0.25–0.5）。
        right_margin_threshold: 右侧留白 / 页面宽度 > 此值视为有留白

    Returns:
        True 如果段落被判断为 Quote 块
    """
    if not para.box or page_width <= 0:
        return False

    box = para.box
    if any(v is None for v in [box.x, box.y, box.x2, box.y2]):
        return False

    para_width = box.x2 - box.x
    if para_width <= 0:
        return False

    # 规则 1: 段落宽度明显窄于页面宽度
    width_ratio = para_width / page_width
    if width_ratio >= narrow_threshold:
        return False

    # 规则 2: 左侧有明显缩进（须显著大于正文页边距）
    left_indent = box.x
    indent_ratio = left_indent / page_width
    if indent_ratio < indent_threshold:
        return False

    # 规则 3: 右侧有明显留白
    right_margin = page_width - box.x2
    margin_ratio = right_margin / page_width
    if margin_ratio < right_margin_threshold:
        return False

    # 辅助规则: 检查文本内容是否包含引号标记
    # 这不是硬性要求，但可以增加置信度
    has_quote_marks = False
    try:
        text = get_paragraph_unicode(para)
        if text:
            # 检查中英文引号
            quote_chars = {'"', '“', '”', "'", '‘', '’',
                           '「', '」', '『', '』',
                           '《', '》'}
            first_char = text.strip()[:1] if text.strip() else ''
            last_char = text.strip()[-1:] if text.strip() else ''
            has_quote_marks = (
                first_char in quote_chars or last_char in quote_chars
            )
    except (UnicodeDecodeError, AttributeError, IndexError):
        pass

    # 如果满足几何规则（窄 + 深缩进 + 留白），认为是 Quote 块。
    # indent_threshold 默认 0.15 已过滤「贴正文页边的左栏绕排」假阳性。
    # 引号标记只是辅助，不作为必要条件
    return True


def get_quote_exclusion_margins(
    para: PdfParagraph,
    page_width: float,
    page_height: float,
    *,
    left_margin: float = 0.02,
    top_margin: float = 0.01,
    bottom_margin: float = 0.01,
) -> tuple[float, float, float, float]:
    """获取 Quote 块的排斥区域边距（绝对值）。

    Args:
        para: Quote 块段落
        page_width: 页面宽度
        page_height: 页面高度
        left_margin: 左侧边距比例（相对于页面宽度）
        top_margin: 上方边距比例（相对于页面高度）
        bottom_margin: 下方边距比例（相对于页面高度）

    Returns:
        (left, top, right, bottom) 边距（绝对值）
    """
    if not para.box or page_width <= 0 or page_height <= 0:
        return (0.0, 0.0, 0.0, 0.0)

    return (
        page_width * left_margin,   # left
        page_height * top_margin,   # top
        0.0,                        # right
        page_height * bottom_margin, # bottom
    )


def get_adaptive_image_padding(font_size: float, default: float = 28.0) -> float:
    """根据字号自适应计算图片与文字的间距。

    英文原文的图文间距通常只有 12-15px，而固定 28px 会浪费太多空间。
    自适应规则：不超过字号的一半，最小 12px。

    Args:
        font_size: 当前字号
        default: 默认间距（当 font_size 无效时使用）

    Returns:
        自适应间距值
    """
    if font_size <= 0:
        return default
    return max(font_size * 0.5, 12.0)
