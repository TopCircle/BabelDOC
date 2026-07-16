"""CJK 禁则 (kinsoku) character sets for line breaking.

Used by ``merge_cjk_units`` (pre-mark ``can_break_line``) and by
``TypesettingUnit`` line-end checks so rules stay in one place.

Convention (Japanese/Chinese typesetting):
- **Line-start forbidden**: must not begin a line (e.g. 。，）」)
- **Line-end forbidden**: must not end a line (e.g. （【「“)

**Do not** put ASCII ``.,;:!?%/`` in line-start: CJK+Latin mixed text
(e.g. ``约 50%`` / ``见 3.2``) would glue digits and Latin too aggressively
when the previous unit is CJK.
"""

from __future__ import annotations

# 行首禁用：断行后下一行首字不能是这些（以全角/CJK 标点为主）
CJK_LINE_START_FORBIDDEN: frozenset[str] = frozenset(
    # 中文点号 / 结束标点
    "。．？！；：，、"
    # 结束括号 / 引号
    "）】》」』〗〉〕］｝"
    "”’"
    # 全角连接 / 间隔 / 省略（行首难看）；不含半角 .,%/
    "・·‧～—–…％‰°"
    "／"  # fullwidth solidus only
)

# 行尾禁用：该字不能作为行末（其后不应断行）
# 含半角开括号：与历史 is_cannot_appear_in_line_end 一致，混排「(注」不拆到行末
CJK_LINE_END_FORBIDDEN: frozenset[str] = frozenset(
    "（【《「『〖〈〔［｛"
    "“‘"
    "([{<"
)


def is_cjk_line_start_forbidden(ch: str | None) -> bool:
    return bool(ch) and ch in CJK_LINE_START_FORBIDDEN


def is_cjk_line_end_forbidden(ch: str | None) -> bool:
    return bool(ch) and ch in CJK_LINE_END_FORBIDDEN
