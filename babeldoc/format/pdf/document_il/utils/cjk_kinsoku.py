"""CJK 禁则 (kinsoku) character sets for line breaking.

Used by ``merge_cjk_units`` (pre-mark ``can_break_line``) and by
``TypesettingUnit`` line-end / hung punctuation checks so rules stay in one place.

Convention (Japanese/Chinese typesetting):
- **Line-start forbidden**: must not begin a line (e.g. 。，）」)
- **Line-end forbidden**: must not end a line (e.g. （【「“)
"""

from __future__ import annotations

# 行首禁用：断行后下一行首字不能是这些
CJK_LINE_START_FORBIDDEN: frozenset[str] = frozenset(
    # 中文点号 / 结束标点
    "。．？！；：，、"
    # 结束括号 / 引号
    "）】》」』〗〉〕］｝"
    "”’"
    # 常见半角结束标点（混排）
    ")]}>.,;:!?"
    # 连接 / 间隔（行首难看）
    "・·‧～—–…％‰°"
    "%/／"
)

# 行尾禁用：该字不能作为行末（其后不应断行）
CJK_LINE_END_FORBIDDEN: frozenset[str] = frozenset(
    # 开始括号 / 引号
    "（【《「『〖〈〔［｛"
    "“‘"
    # 半角开始
    "([{<"
)


def is_cjk_line_start_forbidden(ch: str | None) -> bool:
    return bool(ch) and ch in CJK_LINE_START_FORBIDDEN


def is_cjk_line_end_forbidden(ch: str | None) -> bool:
    return bool(ch) and ch in CJK_LINE_END_FORBIDDEN
