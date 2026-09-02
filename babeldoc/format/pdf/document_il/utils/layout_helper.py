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
from babeldoc.format.pdf.document_il.utils import text_recovery
from babeldoc.format.pdf.document_il.utils.decorative_spacing import (
    compute_decorative_tracking,
    decorative_word_gap_threshold,
    gap_is_decorative_word_boundary,
    is_decorative_text,
)
from babeldoc.format.pdf.document_il.utils.drop_cap import (
    rejoin_drop_cap_in_text,
    should_suppress_space_after_drop_cap,
)

# Back-compat aliases (paragraph_finder imports private names).
_is_decorative_text = is_decorative_text
_decorative_word_gap_threshold = decorative_word_gap_threshold

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

# ``\uf643`` is the private-use glyph used by the Gabrielle Moore source
# PDFs for the red hollow-circle list marker.  pdfminer preserves that code
# point instead of mapping it to the usual ``•`` character.
BULLET_POINT_PATTERN = re.compile(
    r"[■•⚫⬤◆◇○●◦‣⁃▪▫∗†‡¹²³⁴⁵⁶⁷⁸⁹⁰₁₂₃₄₅₆₇₈₉₀ᵃᵇᶜᵈᵉᶠᵍʰⁱʲᵏˡᵐⁿᵒᵖʳˢᵗᵘᵛʷˣʸᶻ¶※⁑⁂⁕⁎⁜❧☙⁋‖‽·\uf643]"
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


def _is_cjk_char(ch: str | None) -> bool:
    """True if the first codepoint is CJK (no inter-word space at line wrap)."""
    if not ch:
        return False
    o = ord(ch[0])
    return (
        0x4E00 <= o <= 0x9FFF  # CJK Unified
        or 0x3400 <= o <= 0x4DBF  # CJK Ext A
        or 0x3040 <= o <= 0x30FF  # Hiragana / Katakana
        or 0xAC00 <= o <= 0xD7AF  # Hangul syllables
        or 0xF900 <= o <= 0xFAFF  # CJK Compatibility
    )


# Text recovery (word-gap + soft-hyphen) lives in ``text_recovery``.
# Keep private aliases so internal call sites stay stable.
_SPACE_WIDTH_RATIO = text_recovery.SPACE_WIDTH_RATIO
_LATIN_WORD_GAP_RATIO = text_recovery.LATIN_WORD_GAP_RATIO
_LATIN_WORD_MIN_GAP_PT = text_recovery.LATIN_WORD_MIN_GAP_PT
_is_ascii_alpha = text_recovery.is_ascii_alpha
_gap_is_word_boundary = text_recovery.gap_is_word_boundary


def strip_ascii_controls(text: str | None) -> str:
    """Remove C0/C1 control characters that leak into dual-PDF text as SOH spans.

    Observed in production (Orgasms dual): standalone U+0001 spans between
    bold lead-ins and dashes (``气味\\x01‑\\x01点燃``), around numbers
    (``从\\x015\\x01组``), and in sticky names (``GABRIELLE\\x01MOORE``).

    Keeps newline / carriage return / tab. Safe on ``None`` / empty.
    """
    if not text:
        return "" if text is None else text
    out: list[str] = []
    for ch in text:
        o = ord(ch)
        if ch in "\n\r\t":
            out.append(ch)
        elif o < 32 or o == 127 or 0x80 <= o <= 0x9F:
            continue
        else:
            out.append(ch)
    return "".join(out)


def _sort_chars_into_reading_order(
    chars: list[PdfCharacter],
    *,
    y_tol: float = 7.5,
) -> list[PdfCharacter]:
    """Top-to-bottom, left-to-right sort robust to per-char baseline drift.

    ``stream_order.sort_chars_visual_order`` buckets glyphs by
    ``round(y2 / y_tol)``; when a design block paints glyphs at slightly
    drifted baselines (~3pt, e.g. OA p82 pull-quote rows), one visual row
    splits across two buckets and the rows interleave.  Cluster on proximity
    instead (tolerance must stay below the row pitch, ~15pt), then sort each
    row left-to-right.
    """
    from babeldoc.format.pdf.document_il.utils.stream_order import char_visual_xy

    if len(chars) < 2:
        return list(chars)
    items: list[tuple[int, float, float, PdfCharacter]] = []
    for i, ch in enumerate(chars):
        xy = char_visual_xy(ch)
        if xy is None:
            items.append((i, 0.0, float(i), ch))
        else:
            items.append((i, xy[1], xy[0], ch))
    items.sort(key=lambda t: t[1], reverse=True)
    clusters: list[list[tuple[int, float, float, PdfCharacter]]] = []
    cluster_means: list[float] = []
    for item in items:
        placed = False
        for ci, mean in enumerate(cluster_means):
            if abs(mean - item[1]) <= y_tol:
                clusters[ci].append(item)
                n = len(clusters[ci])
                cluster_means[ci] = (mean * (n - 1) + item[1]) / n
                placed = True
                break
        if not placed:
            clusters.append([item])
            cluster_means.append(item[1])
    ordered: list[PdfCharacter] = []
    for ci in sorted(range(len(clusters)), key=lambda i: cluster_means[i], reverse=True):
        row = sorted(clusters[ci], key=lambda t: (t[2], t[0]))
        ordered.extend(t[3] for t in row)
    return ordered


_STYLE_OPEN_RE = re.compile(r"^〖B(\d+)〗$")


def _group_mt_tokens(
    chars: list[PdfCharacter | str],
) -> list[list[PdfCharacter | str]]:
    """Keep 〖Bn〗…〖/Bn〗 runs together so drop-cap prep can move the unit."""
    groups: list[list[PdfCharacter | str]] = []
    i = 0
    n = len(chars)
    while i < n:
        item = chars[i]
        if isinstance(item, str):
            matched = _STYLE_OPEN_RE.match(item)
            if matched:
                close = f"〖/B{matched.group(1)}〗"
                group: list[PdfCharacter | str] = [item]
                i += 1
                while i < n and chars[i] != close:
                    group.append(chars[i])
                    i += 1
                if i < n:
                    group.append(chars[i])
                    i += 1
                groups.append(group)
                continue
        groups.append([item])
        i += 1
    return groups


def _attach_string_groups(
    groups: list[list[PdfCharacter | str]],
) -> list[list[PdfCharacter | str]]:
    """Keep formula placeholders next to the preceding character group."""
    merged: list[list[PdfCharacter | str]] = []
    prefix: list[PdfCharacter | str] = []
    for group in groups:
        if any(isinstance(item, PdfCharacter) for item in group):
            merged.append(prefix + group)
            prefix = []
        elif merged:
            merged[-1].extend(group)
        else:
            prefix.extend(group)
    if prefix:
        if merged:
            merged[-1].extend(prefix)
        else:
            merged.append(prefix)
    return merged


def _apply_prepared_order_to_mixed(
    chars: list[PdfCharacter | str],
    prepared: list[PdfCharacter],
) -> list[PdfCharacter | str]:
    """Replay climb/drop-cap order onto a mixed marker+char token list."""
    from babeldoc.format.pdf.document_il.utils.drop_cap import (
        is_drop_cap_letter,
        is_drop_cap_pair,
    )

    groups = _attach_string_groups(_group_mt_tokens(chars))
    id_to_group: dict[int, int] = {}
    for group_i, group in enumerate(groups):
        for item in group:
            if isinstance(item, PdfCharacter):
                id_to_group[id(item)] = group_i
    prep_index = {id(char): idx for idx, char in enumerate(prepared)}
    emitted: set[int] = set()
    out: list[PdfCharacter | str] = []
    for char in prepared:
        group_i = id_to_group.get(id(char))
        if group_i is None:
            out.append(char)
            continue
        if group_i in emitted:
            continue
        emitted.add(group_i)
        group = groups[group_i]
        # Drop-cap sidebearing spaces must not ride along inside 〖Bn〗.
        drop_letters = [
            item
            for item in group
            if isinstance(item, PdfCharacter) and is_drop_cap_letter(item)
        ]
        if drop_letters:
            rest = [
                c
                for c in prepared
                if c is not drop_letters[0] and not (c.char_unicode or "").isspace()
            ]
            if rest and is_drop_cap_pair(drop_letters[0], rest[0]):
                group = [
                    item
                    for item in group
                    if not (
                        isinstance(item, PdfCharacter)
                        and (item.char_unicode or "").isspace()
                    )
                ]
        char_items = [item for item in group if isinstance(item, PdfCharacter)]
        if len(char_items) > 1:
            char_items.sort(key=lambda item: prep_index.get(id(item), 0))
            rebuilt: list[PdfCharacter | str] = []
            inserted = False
            for item in group:
                if isinstance(item, PdfCharacter):
                    if not inserted:
                        rebuilt.extend(char_items)
                        inserted = True
                else:
                    rebuilt.append(item)
            group = rebuilt
        out.extend(group)
    for group_i, group in enumerate(groups):
        if group_i not in emitted:
            out.extend(group)
    return out


def prepare_chars_for_mt(
    chars: list[PdfCharacter],
    *,
    para_width: float | None = None,
) -> list[PdfCharacter]:
    """Single MT prep: multi-line climb reorder, then drop-cap adjacency.

    Call sites that need visual reading order for translation should go through
    this helper (via ``get_char_unicode_string``) rather than re-applying climb
    / place_drop_caps independently.
    """
    if not chars:
        return chars
    from babeldoc.format.pdf.document_il.utils.drop_cap import (
        place_drop_caps_before_continuations,
    )
    from babeldoc.format.pdf.document_il.utils.stream_order import (
        maybe_reorder_multiline_stream_climb,
    )

    climbed = maybe_reorder_multiline_stream_climb(chars, para_width=para_width)
    if climbed is not None and climbed is not chars:
        # Climb reorder uses fixed-width y buckets that split drifted rows;
        # re-stabilize into clean top-to-bottom, left-to-right rows.
        chars = _sort_chars_into_reading_order(climbed)
    from babeldoc.format.pdf.document_il.utils.drop_cap import (
        strip_drop_cap_padding,
    )

    return strip_drop_cap_padding(place_drop_caps_before_continuations(chars))


def get_char_unicode_string(
    chars: list[PdfCharacter | str],
    *,
    para_width: float | None = None,
) -> str:
    """
    将字符列表转换为 Unicode 字符串，根据字符间距自动插入空格。
    有些 PDF 不会显式编码空格，这时需要根据间距自动插入空格。

    Space detection uses a character-width-relative threshold instead of
    a global median: a gap is treated as a word boundary when it exceeds
    40% of the wider of the two adjacent characters' widths.  Using the
    wider character avoids false positives from narrow chars (like 'r' at
    2pt) pulling the threshold too low next to wide chars (like 'e' at 5pt),
    which previously split words like "There" → "The re".

    Pure PdfCharacter lists are first prepared for MT (stream climb + drop-cap
    placement).  Optional *para_width* enables the wide-body climb gate.

    Args:
        chars: 字符列表，可以是 PdfCharacter 对象或字符串
        para_width: optional paragraph width for climb width gating

    Returns:
        str: 处理后的 Unicode 字符串
    """
    # Decorative letter-spacing: letter gaps skipped; word outliers still split.
    pdf_only = [c for c in chars if isinstance(c, PdfCharacter)]
    # Climb + drop-cap even when ILTranslator mixed in 〖Bn〗 / {vN} strings.
    # Pure-char lists used to be the only path; style markers skipped prep and
    # left OA p3 as ``elcome … 〖B0〗W 〖/B0〗``.
    if pdf_only:
        prepared = prepare_chars_for_mt(pdf_only, para_width=para_width)
        if len(pdf_only) == len(chars):
            chars = prepared
        else:
            chars = _apply_prepared_order_to_mixed(chars, prepared)
        pdf_only = [c for c in chars if isinstance(c, PdfCharacter)]
    is_decorative = is_decorative_text(pdf_only)
    decorative_word_gap = (
        decorative_word_gap_threshold(pdf_only) if is_decorative else None
    )

    # 构建 unicode 字符串，根据间距插入空格
    unicode_chars = []
    for i in range(len(chars)):
        # 如果不是字符对象，直接添加，一般来说这个时候 chars[i] 是字符串
        if not isinstance(chars[i], PdfCharacter):
            unicode_chars.append(chars[i])
            continue

        # use unicode regex to replace all space with " "
        raw_u = chars[i].char_unicode or ""
        # Expand Latin ligatures (ﬁ/ﬂ/ﬀ/ﬃ) before NFKC so residual EN scans
        # and DeepLX never see presentation-form codepoints.
        raw_u = text_recovery.expand_latin_ligatures(raw_u)
        unicode_chars.append(
            regex.sub(
                r"\s+",
                " ",
                unicodedata.normalize("NFKC", raw_u),
            )
        )

        # 如果是空格，跳过
        if chars[i].char_unicode == " ":
            continue

        # Next PdfCharacter, skipping style-marker strings (〖Bn〗).
        next_ch = None
        next_i = None
        skipped_space = False
        for k in range(i + 1, len(chars)):
            item = chars[k]
            if isinstance(item, str):
                continue
            if isinstance(item, PdfCharacter):
                if (item.char_unicode or "").isspace():
                    skipped_space = True
                    continue
                next_ch = item
                next_i = k
                break
            break

        if next_ch is None or next_i is None:
            continue

        is_hyphen = (chars[i].char_unicode or "") in text_recovery.HYPHEN_CHARS
        # Explicit space between two letters: do not insert another.
        # Hyphen wraps still peek past a dummy wrap-space to the tail.
        if skipped_space and not is_hyphen:
            continue

        distance = next_ch.box.x - chars[i].box.x2
        # Line wraps jump back to the left margin → distance << 0.
        # Must still insert a word-boundary space (ATU intro: "Is"+"it"
        # → "Isit", "of"+"Grey" → "ofGrey") when process_paragraph_spacing
        # has stripped the trailing space glyph on the previous line.
        is_nl = Layout.is_newline(chars[i], next_ch)
        gap_is_word_boundary = _gap_is_word_boundary(
            chars[i], next_ch, distance
        )
        # Soft hyphen wrap: peek Latin continuation across 〖Bn〗 and
        # expand ligatures (``stu-`` + ``ff`` ligature → stuff).
        next_word = text_recovery.peek_latin_continuation(chars, next_i)
        stem = "".join(unicode_chars)
        if text_recovery.should_join_hyphen_wrap(stem, next_word):
            # Immediate next is the tail: drop hyphen, no wrap space.
            if next_i == i + 1:
                if unicode_chars and unicode_chars[-1] in text_recovery.HYPHEN_CHARS:
                    unicode_chars.pop()
            # Else markers / dummy space sit between stem and tail — keep
            # the hyphen so recover_latin_word_fragments glues across them.
            continue
        # Drop-cap: never insert space between large ``I`` and ``f you…``
        # Peek across 〖Bn〗 strings — ILTranslator may wrap the cap.
        if should_suppress_space_after_drop_cap(chars[i], next_ch):
            continue
        peeked = next_ch
        for k in range(i + 1, len(chars)):
            item = chars[k]
            if isinstance(item, str):
                continue
            if isinstance(item, PdfCharacter):
                if (item.char_unicode or "").isspace():
                    continue
                peeked = item
            break
        if peeked is not next_ch and should_suppress_space_after_drop_cap(
            chars[i], peeked
        ):
            continue
        if is_decorative:
            insert = is_nl or gap_is_decorative_word_boundary(
                distance, decorative_word_gap
            )
        else:
            insert = is_nl or gap_is_word_boundary
        if insert:
            # Avoid CJK line-wrap spaces (source Chinese has no inter-word space).
            if is_nl and _is_cjk_char(chars[i].char_unicode) and _is_cjk_char(
                next_ch.char_unicode
            ):
                continue
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
    # Drop-cap text cleanup then ligature / soft-hyphen recovery
    result = rejoin_drop_cap_in_text(result)
    # Soft hyphens, ligature gaps, known mid-word splits (OA di/ff, cli toral)
    result = text_recovery.recover_latin_word_fragments(result)
    # Decorative mixed-case titles only (not global body: iPhone / eBay safe)
    if is_decorative:
        result = text_recovery.normalize_decorative_title_case(result)
    normalize = unicodedata.normalize("NFKC", result)
    result = SPACE_REGEX.sub(" ", normalize).strip()
    return result


def assemble_midcap_title_unicode(
    paragraph: PdfParagraph,
    chars: list,
    *,
    para_width: float | None = None,
) -> str:
    """Build MT unicode for a paragraph, applying mid-caps title normalize.

    Visual-sorts glyphs when the mid-caps title gate fires so wrapped tag
    lines (OA p59 ``S`` of SOFT last in stream) read as real words before MT.
    No-op for 12pt body (gate false).
    """
    pdf_chars = [c for c in chars if isinstance(c, PdfCharacter)]
    mixed = len(pdf_chars) != len(chars)
    raw = get_char_unicode_string(chars, para_width=para_width)
    if not text_recovery.should_normalize_midcap_title(paragraph, text=raw):
        return raw
    # Only visual-sort pure glyph lists; placeholder strings must stay put.
    if pdf_chars and not mixed:
        raw = get_char_unicode_string(
            _sort_chars_into_reading_order(pdf_chars),
            para_width=para_width,
        )
    return text_recovery.normalize_decorative_title_case(raw)


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
        # 使用与 _add_space_dummy_chars_to_list 一致的 width-relative 阈值。
        # Line wraps have distance << 0; still insert via is_newline (same as
        # get_char_unicode_string) so trailing-space strip does not glue words.
        if next_first_char.char_unicode and next_first_char.char_unicode.isspace():
            continue
        if curr_last_char.char_unicode and curr_last_char.char_unicode.isspace():
            continue
        distance = next_first_char.box.x - curr_last_char.box.x2
        curr_w = curr_last_char.box.x2 - curr_last_char.box.x
        is_nl = Layout.is_newline(curr_last_char, next_first_char)
        gap_is_word_boundary = _gap_is_word_boundary(
            curr_last_char, next_first_char, distance
        )
        if not (is_nl or gap_is_word_boundary):
            continue
        if is_nl and _is_cjk_char(curr_last_char.char_unicode) and _is_cjk_char(
            next_first_char.char_unicode
        ):
            continue
        # Dummy width: real gap when positive; else a small advance for wraps.
        gap_w = distance if distance > 0 else max(curr_w * 0.25, 1.0)
        space_box = Box(
            x=curr_last_char.box.x2,
            y=curr_last_char.box.y,
            x2=curr_last_char.box.x2 + gap_w,
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

    # Decorative letter-spacing: skip letter gaps; still insert dummy spaces
    # at word-gap outliers (same policy as get_char_unicode_string).
    decorative_word_gap = None
    if is_decorative_text(chars):
        decorative_word_gap = decorative_word_gap_threshold(chars)
        if decorative_word_gap is None:
            return

    i = 0
    while i < len(chars) - 1:
        curr_char = chars[i]
        next_char = chars[i + 1]

        if next_char.char_unicode and next_char.char_unicode.isspace():
            i += 1
            continue
        if curr_char.char_unicode and curr_char.char_unicode.isspace():
            i += 1
            continue

        distance = next_char.box.x - curr_char.box.x2
        curr_w = curr_char.box.x2 - curr_char.box.x
        is_nl = Layout.is_newline(curr_char, next_char)
        if decorative_word_gap is not None:
            gap_is_word_boundary = gap_is_decorative_word_boundary(
                distance, decorative_word_gap
            )
        else:
            gap_is_word_boundary = _gap_is_word_boundary(
                curr_char, next_char, distance
            )
        # distance <= 0 is normal at line wrap (next char returns to left margin).
        # Previously we `continue`d here and never hit is_newline → "Isit"/"ofGrey".
        if not (is_nl or gap_is_word_boundary):
            i += 1
            continue
        if is_nl and _is_cjk_char(curr_char.char_unicode) and _is_cjk_char(
            next_char.char_unicode
        ):
            i += 1
            continue

        gap_w = distance if distance > 0 else max(curr_w * 0.25, 1.0)
        # 创建一个 dummy 字符作为空格
        space_box = Box(
            x=curr_char.box.x2,
            y=curr_char.box.y,
            x2=curr_char.box.x2 + gap_w,
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


# Layout labels that are in-figure annotations (not captions).
FIGURE_TEXT_LAYOUT_LABELS = frozenset(
    {
        "figure_text",
        "figure_text_hybrid",
    }
)
# Layout regions that contain figures (used for spatial fallback).
FIGURE_CONTAINER_LAYOUT_NAMES = frozenset(
    {
        "figure",
        "image",
    }
)
# Explicit figure_text labels: keep a slightly higher cap.
_FIGURE_LABEL_MAX_CHARS = 64
# Spatial path (no figure_text label): tighter — body callouts sit near figures.
_FIGURE_SPATIAL_MAX_CHARS = 48
# Spatial path: fraction of the *paragraph* box that must lie inside a figure
# box (``calculate_iou_for_boxes`` = inter/|para|, not Jaccard IoU).
FIGURE_TEXT_COVERAGE_THRESHOLD = 0.5
# Reject spatial match when para is a body column (PR-C2 OA side prose).
_FIGURE_SPATIAL_MAX_WIDTH_RATIO = 0.22


def _looks_like_body_prose(text: str) -> bool:
    """True for multi-word sentences — not chart tick labels (PR-C2)."""
    t = (text or "").strip()
    if len(t) < 20:
        return False
    spaces = t.count(" ")
    if spaces >= 5:
        return True
    if spaces >= 3 and t[-1] in ".!?…":
        return True
    return False


def is_figure_text_paragraph(
    paragraph: PdfParagraph,
    page: il_version_1.Page | None = None,
    *,
    coverage_threshold: float = FIGURE_TEXT_COVERAGE_THRESHOLD,
) -> bool:
    """True if *paragraph* is figure-internal text (default: skip MT).

    Matches when:

    1. ``layout_label`` is ``figure_text`` / hybrid, or
    2. Short non-prose text whose box is mostly covered by a ``figure``/``image``
       layout (mis-labels like plain ``text`` on arXiv diagram annotations).

    Spatial test uses **coverage of the paragraph**
    (``inter / |paragraph.box|`` via ``calculate_iou_for_boxes(para, fig)``),
    not classical Jaccard IoU — a tiny label fully inside a large figure
    scores ~1.0.

    Captions (``figure_caption`` / ``figure_title``) are **not** matched.
    PR-C2: spatial path rejects body prose and wide columns.
    """
    label = (getattr(paragraph, "layout_label", None) or "").strip()
    if label in FIGURE_TEXT_LAYOUT_LABELS:
        return True

    text = (getattr(paragraph, "unicode", None) or "").strip()
    if not text or len(text) > _FIGURE_SPATIAL_MAX_CHARS:
        return False
    # Explicit long labels under the old 64 cap still skip only via label path.
    if _looks_like_body_prose(text):
        return False
    if page is None or not paragraph.box:
        return False

    # Wide body columns beside a full-bleed figure are not chart labels.
    page_box = None
    for attr in ("cropbox", "mediabox"):
        cb = getattr(page, attr, None)
        if cb is None:
            continue
        page_box = cb.box if hasattr(cb, "box") and cb.box is not None else cb
        if page_box is not None and getattr(page_box, "x2", None) is not None:
            break
    if (
        page_box is not None
        and paragraph.box.x is not None
        and paragraph.box.x2 is not None
        and page_box.x is not None
        and page_box.x2 is not None
        and page_box.x2 > page_box.x
    ):
        para_w = float(paragraph.box.x2) - float(paragraph.box.x)
        page_w = float(page_box.x2) - float(page_box.x)
        if page_w > 0 and para_w / page_w >= _FIGURE_SPATIAL_MAX_WIDTH_RATIO:
            return False

    thr = float(coverage_threshold)
    for layout in page.page_layout or []:
        name = getattr(layout, "class_name", None) or getattr(layout, "name", None)
        if name not in FIGURE_CONTAINER_LAYOUT_NAMES:
            continue
        layout_box = getattr(layout, "box", None)
        if layout_box is None:
            continue
        # Coverage of paragraph inside figure (see calculate_iou_for_boxes).
        if calculate_iou_for_boxes(paragraph.box, layout_box) >= thr:
            return True
    return False


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


# Paragraph alignment lives in ``paragraph_alignment`` (body-column +
# page-symmetric center). Re-export for stable import paths.
from babeldoc.format.pdf.document_il.utils.paragraph_alignment import (  # noqa: E402
    detect_paragraph_alignment,
    dominant_body_column_left,
    flush_with_body_column,
)


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


from babeldoc.format.pdf.document_il.utils.figure_wrap import (
    is_figure_wrap_paragraph,
    is_figure_wrap_taper,
)


def is_quote_block(
    para: PdfParagraph,
    page_width: float,
    *,
    narrow_threshold: float = 0.70,
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
        narrow_threshold: 段落宽度 / 页面宽度 < 此值视为窄段落。
            默认 0.70：过滤 OA 一类 ~77% 页宽的正文栏（470/612），
            保留典型 pull-quote（通常 ≲ 0.50）。
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

    # 规则 1.5: 锥形绕图列（右缘贴页边 + 多行左缘步进）不是 Quote
    # 绕图正文列（图片在左、正文右缘贴页边）几何上"窄 + 深缩进 + 少量留白"，
    # 容易命中规则 1/2/3 被误判为 pull-quote（OA p19 TAKING CHARGE）。
    # 右缘贴页边本身不足以排除（右侧 pull-quote 同样深缩进且右缘靠页边），
    # 因此同时要求"多行左缘步进 + 右缘固定"的锥形签名。
    if box.x2 is not None and box.x2 > page_width * 0.9:
        if is_figure_wrap_paragraph(para):
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
        page_width * left_margin,   # right (body-side gap for left gutter)
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
