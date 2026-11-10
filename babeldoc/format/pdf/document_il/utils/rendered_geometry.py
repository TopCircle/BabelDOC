"""Geometry from one consistent set of positioned, valid rendered characters."""

from __future__ import annotations

from babeldoc.format.pdf.document_il.il_version_1 import Box, PdfCharacter, PdfParagraph


def extract_rendered_chars(para: PdfParagraph) -> list:
    """从段落 composition 中提取所有可渲染字符。

    覆盖全部 5 种 composition 类型：
    pdf_character, pdf_line, pdf_formula, pdf_same_style_characters,
    pdf_same_style_unicode_characters（无字符坐标，跳过）。
    """
    chars = []
    for comp in para.pdf_paragraph_composition or []:
        if comp.pdf_character:
            chars.append(comp.pdf_character)
        elif comp.pdf_line:
            chars.extend(comp.pdf_line.pdf_character)
        elif comp.pdf_formula:
            chars.extend(comp.pdf_formula.pdf_character)
        elif comp.pdf_same_style_characters:
            chars.extend(comp.pdf_same_style_characters.pdf_character)
        # pdf_same_style_unicode_characters 无 pdf_character 字段，跳过
    return chars


def char_has_valid_box(c) -> bool:
    """检查字符的 box 字段是否完整可用。"""
    return (
        c.box is not None
        and c.box.x is not None
        and c.box.y is not None
        and c.box.x2 is not None
        and c.box.y2 is not None
    )


def compute_rendered_box(para: PdfParagraph) -> tuple[Box | None, list]:
    """从段落实际字符坐标计算紧密包围盒。

    Returns (box, valid_chars) — the bounding box and the filtered chars used
    to compute it, so callers can reuse the char list without re-extracting.
    """
    chars = [c for c in extract_rendered_chars(para) if char_has_valid_box(c)]
    if not chars:
        return None, []
    return Box(
        x=min(c.box.x for c in chars),
        y=min(c.box.y for c in chars),
        x2=max(c.box.x2 for c in chars),
        y2=max(c.box.y2 for c in chars),
    ), chars


def rendered_line_boxes(chars: list[PdfCharacter]) -> tuple[Box, ...]:
    """Group valid characters without discarding small positive-height glyphs."""
    ordered = sorted(chars, key=lambda char: char.box.y2, reverse=True)
    groups: list[list[PdfCharacter]] = []
    for char in ordered:
        if not groups or groups[-1][0].box.y2 - char.box.y2 > 1.5:
            groups.append([char])
        else:
            groups[-1].append(char)
    return tuple(
        Box(
            x=min(c.box.x for c in group),
            y=min(c.box.y for c in group),
            x2=max(c.box.x2 for c in group),
            y2=max(c.box.y2 for c in group),
        )
        for group in groups
    )
