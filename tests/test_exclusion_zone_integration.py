"""ExclusionZone 集成测试。

测试 ExclusionZone 在排版中的实际效果：
- Quote zone 是否正确检测
- Zone 是否正确收窄可用宽度
- 多 zone 的交互
"""

import pytest
from babeldoc.format.pdf.document_il import il_version_1
from babeldoc.format.pdf.document_il.midend.exclusion_zone import (
    ExclusionZone,
    ExclusionZoneIndex,
    ZONE_QUOTE,
    ZONE_FIGURE,
)
from babeldoc.format.pdf.document_il.utils.layout_helper import is_quote_block


class TestIsQuoteBlock:
    """测试 is_quote_block 检测逻辑。"""

    def _make_para(self, x, y, x2, y2):
        """创建一个测试段落。"""
        para = il_version_1.PdfParagraph()
        para.box = il_version_1.Box(x=x, y=y, x2=x2, y2=y2)
        para.pdf_paragraph_composition = []
        return para

    def test_typical_quote_detected(self):
        """典型的 Quote 段落应该被检测到。"""
        # 页面宽度 612（标准 Letter）
        # Quote 段落：宽度约 60% 页面宽度，左侧缩进 15%，右侧留白 25%
        para = self._make_para(92, 400, 462, 500)
        assert is_quote_block(para, page_width=612) is True

    def test_full_width_not_quote(self):
        """全宽段落不是 Quote。"""
        para = self._make_para(0, 400, 612, 500)
        assert is_quote_block(para, page_width=612) is False

    def test_slightly_narrow_not_quote(self):
        """稍微窄一点但不够窄的段落不是 Quote。"""
        # 宽度 90% 页面宽度
        para = self._make_para(30, 400, 582, 500)
        assert is_quote_block(para, page_width=612) is False

    def test_narrow_but_no_indent_not_quote(self):
        """窄但没有缩进的段落不是 Quote。"""
        # 左侧无缩进
        para = self._make_para(0, 400, 400, 500)
        assert is_quote_block(para, page_width=612) is False

    def test_narrow_but_no_right_margin_not_quote(self):
        """窄但右侧无留白的段落不是 Quote。"""
        # 右侧无留白
        para = self._make_para(100, 400, 612, 500)
        assert is_quote_block(para, page_width=612) is False

    def test_none_box_returns_false(self):
        """没有 box 的段落返回 False。"""
        para = il_version_1.PdfParagraph()
        para.box = None
        assert is_quote_block(para, page_width=612) is False


class TestExclusionZoneIndex:
    """测试 ExclusionZoneIndex 的宽度收窄逻辑。"""

    def _make_zone(self, x, y, x2, y2, kind=ZONE_QUOTE):
        """创建一个测试 zone。"""
        return ExclusionZone(
            box=il_version_1.Box(x=x, y=y, x2=x2, y2=y2),
            kind=kind,
            priority=10,
        )

    def test_no_zones_returns_default(self):
        """没有 zone 时返回默认宽度。"""
        index = ExclusionZoneIndex([])
        x1, x2 = index.get_available_x_range(100, 200, 0, 612)
        assert x1 == 0
        assert x2 == 612

    def test_zone_narrows_right_side(self):
        """右侧 zone 收窄可用宽度。"""
        # Quote zone 在右侧 (400-550)
        zone = self._make_zone(400, 100, 550, 300)
        index = ExclusionZoneIndex([zone])

        # 行在 zone 的 y 范围内
        x1, x2 = index.get_available_x_range(150, 250, 0, 612)
        assert x1 == 0
        assert x2 == 400  # 被 zone 的左边界收窄

    def test_zone_narrows_left_side(self):
        """左侧 zone 收窄可用宽度。"""
        # zone 在左侧 (50-200)
        zone = self._make_zone(50, 100, 200, 300)
        index = ExclusionZoneIndex([zone])

        x1, x2 = index.get_available_x_range(150, 250, 0, 612)
        assert x1 == 200  # 被 zone 的右边界收窄
        assert x2 == 612

    def test_zone_inside_text_chooses_wider_side(self):
        """zone 在文本区域内时，选择更宽的一侧。"""
        # zone 在中间 (200-400)
        zone = self._make_zone(200, 100, 400, 300)
        index = ExclusionZoneIndex([zone])

        # 左侧 200，右侧 212，右侧更宽
        x1, x2 = index.get_available_x_range(150, 250, 0, 612)
        assert x1 == 400  # 保留右侧
        assert x2 == 612

    def test_zone_outside_y_range_no_effect(self):
        """zone 在行的 y 范围外不影响宽度。"""
        zone = self._make_zone(200, 500, 400, 700)  # y 很高
        index = ExclusionZoneIndex([zone])

        x1, x2 = index.get_available_x_range(100, 200, 0, 612)  # 行在低处
        assert x1 == 0
        assert x2 == 612

    def test_zone_outside_x_range_no_effect(self):
        """zone 在文本区域外不影响宽度。"""
        zone = self._make_zone(700, 100, 800, 300)  # x 超出文本区域
        index = ExclusionZoneIndex([zone])

        x1, x2 = index.get_available_x_range(150, 250, 0, 612)
        assert x1 == 0
        assert x2 == 612

    def test_multiple_zones(self):
        """多个 zone 同时收窄宽度。"""
        # 左侧 zone (50-150) 和右侧 zone (400-550)
        zone_left = self._make_zone(50, 100, 150, 300)
        zone_right = self._make_zone(400, 100, 550, 300)
        index = ExclusionZoneIndex([zone_left, zone_right])

        x1, x2 = index.get_available_x_range(150, 250, 0, 612)
        assert x1 == 150  # 左侧 zone 收窄
        assert x2 == 400  # 右侧 zone 收窄

    def test_zone_fully_covers_text_area(self):
        """zone 完全覆盖文本区域时，可用宽度为零。"""
        zone = self._make_zone(0, 100, 612, 300)
        index = ExclusionZoneIndex([zone])

        x1, x2 = index.get_available_x_range(150, 250, 0, 612)
        assert x1 == x2  # 零宽度


class TestQuoteZoneInTypesetting:
    """测试 Quote zone 在排版中的实际效果。"""

    def test_quote_zone_narrows_text_paragraph(self):
        """Quote zone 应该收窄文本段落的可用宽度。"""
        # 模拟：Quote 在右侧 (400-550)，文本段落全宽 (0-612)
        zone = ExclusionZone(
            box=il_version_1.Box(x=400, y=100, x2=550, y2=300),
            kind=ZONE_QUOTE,
            priority=20,
        )
        index = ExclusionZoneIndex([zone])

        # 文本段落的第一行（在 zone 的 y 范围内）
        x1, x2 = index.get_available_x_range(150, 250, 0, 612)
        assert x2 == 400  # 右侧被 Quote zone 收窄

        # 文本段落的行（在 zone 的 y 范围外）
        x1, x2 = index.get_available_x_range(50, 100, 0, 612)
        assert x2 == 612  # 不受影响

    def test_quote_zone_with_margin(self):
        """Quote zone 包含 margin 时，收窄效果更大。"""
        # Quote box 是 (400, 100, 550, 300)，margin 各 10pt
        zone = ExclusionZone(
            box=il_version_1.Box(x=390, y=90, x2=560, y2=310),
            kind=ZONE_QUOTE,
            priority=20,
            margins=(10, 10, 10, 10),
        )
        index = ExclusionZoneIndex([zone])

        x1, x2 = index.get_available_x_range(150, 250, 0, 612)
        assert x2 == 390  # 被 zone 的左边界（含 margin）收窄
