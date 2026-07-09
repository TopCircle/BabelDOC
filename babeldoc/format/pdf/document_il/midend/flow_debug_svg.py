"""Flow Debug SVG 生成器

为每页生成独立 SVG 文件，可视化布局分析结果：
- 页面边界（灰色细线）
- 占位体/Obstacle（蓝色半透明填充 + 蓝色边框）
- 流体行（绿色细线）
- Flow Region / Free Space（蓝色半透明填充 + 蓝色边框 + 虚线）
- 装饰体（紫色半透明填充 + 紫色边框 + 虚线）
- 合并区域（橙色虚线边框）
- 页面标签（右上角）

坐标系：SVG 原点左上，y 轴向下。PDF 坐标系原点左下，y 轴向上。
转换公式：svg_y = page_height - pdf_y

用法：
    from babeldoc.format.pdf.document_il.midend.flow_debug_svg import FlowDebugSvg
    FlowDebugSvg(config).process_page(page, "/tmp/debug")
"""

import logging
from pathlib import Path

from babeldoc.format.pdf.document_il import il_version_1
from babeldoc.format.pdf.translation_config import TranslationConfig

logger = logging.getLogger(__name__)

# SVG 颜色常量
OCCUPIER_COLOR = "blue"         # 占位体边框
OCCUPIER_FILL = "rgba(0,0,255,0.1)"  # 占位体填充
FLOW_LINE_COLOR = "green"       # 流体行
FLOW_REGION_COLOR = "blue"      # Flow Region 边框
FLOW_REGION_FILL = "rgba(0,100,255,0.08)"  # Flow Region 填充
DECORATION_COLOR = "purple"     # 装饰体边框
DECORATION_FILL = "rgba(128,0,128,0.1)"  # 装饰体填充
MERGED_COLOR = "orange"         # 合并区域边框
MERGED_FILL = "rgba(255,165,0,0.05)"  # 合并区域填充
PAGE_BORDER_COLOR = "#cccccc"   # 页面边框
LABEL_COLOR = "#333333"         # 标签文字颜色


class FlowDebugSvg:
    """生成 Flow Debug SVG 文件"""

    stage_name = "Generate Flow Debug SVG"

    def __init__(self, translation_config: TranslationConfig):
        self.translation_config = translation_config

    def process(self, docs: il_version_1.Document, debug_dir: str):
        """为文档的每一页生成 SVG 文件

        Args:
            docs: 文档对象
            debug_dir: SVG 文件输出目录
        """
        if not self.translation_config.debug:
            return

        debug_path = Path(debug_dir)
        debug_path.mkdir(parents=True, exist_ok=True)

        for page in docs.page:
            self.process_page(page, debug_dir)

    def process_page(self, page: il_version_1.Page, debug_dir: str):
        """为单页生成 SVG 文件

        Args:
            page: 页面对象
            debug_dir: SVG 文件输出目录
        """
        if not self.translation_config.debug:
            return

        debug_path = Path(debug_dir)
        debug_path.mkdir(parents=True, exist_ok=True)

        # 获取页面尺寸（带 null 检查）
        if not page.cropbox or not page.cropbox.box:
            logger.warning("Page cropbox is None, skipping SVG debug for this page")
            return
        page_width = page.cropbox.box.x2 - page.cropbox.box.x
        page_height = page.cropbox.box.y2 - page.cropbox.box.y

        # 创建 SVG
        svg = SvgBuilder(page_width, page_height)

        # 1. 页面边界
        svg.add_rect(0, 0, page_width, page_height,
                     stroke=PAGE_BORDER_COLOR, fill="none", stroke_width=0.5)

        # 2. 占位体（蓝色）- 图片、图表、Pull Quote 等
        for obj in self._get_occupiers(page):
            self._draw_occupier(svg, obj, page_height)

        # 3. 流体行（绿色）- 文本行
        for char in self._get_flow_lines(page):
            self._draw_flow_line(svg, char, page_height)

        # 4. Flow Region（蓝色虚线）
        for region in self._get_flow_regions(page):
            self._draw_flow_region(svg, region, page_height)

        # 5. 装饰体（紫色虚线）
        for decoration in self._get_decorations(page):
            self._draw_decoration(svg, decoration, page_height)

        # 6. 合并区域（橙色虚线）
        for merged in self._get_merged_areas(page):
            self._draw_merged_area(svg, merged, page_height)

        # 7. 页面标签（右上角）
        label = f"Page {page.page_number + 1}"
        svg.add_text(page_width - 10, 15, label,
                     font_size=12, fill=LABEL_COLOR, anchor="end")

        # 输出 SVG
        output_path = debug_path / f"flow_debug_page_{page.page_number + 1}.svg"
        svg.save(str(output_path))
        logger.debug(f"Generated flow debug SVG: {output_path}")

    def _get_occupiers(self, page: il_version_1.Page) -> list:
        """获取页面上的占位体（图片、图表、表格、Pull Quote 等）

        占位体是文本流需要绕排的物体。
        """
        occupiers = []

        # 图片
        for figure in page.pdf_figure:
            if figure.box:
                occupiers.append({
                    "type": "figure",
                    "box": figure.box,
                    "label": "figure",
                })

        # XObject（嵌入的内容）
        for xobj in page.pdf_xobject:
            if xobj.box:
                occupiers.append({
                    "type": "xobject",
                    "box": xobj.box,
                    "label": "xobject",
                })

        # 表格
        for table in getattr(page, "pdf_table", []):
            if table.box:
                occupiers.append({
                    "type": "table",
                    "box": table.box,
                    "label": "table",
                })

        return occupiers

    def _get_flow_lines(self, page: il_version_1.Page) -> list:
        """获取页面上的流体行（文本字符）

        返回每个字符的位置，用于绘制文本行。
        """
        chars = []
        for char in page.pdf_character:
            if char.box and not char.debug_info:
                chars.append(char)
        return chars

    def _get_flow_regions(self, page: il_version_1.Page) -> list:
        """获取页面上的 Flow Region（阅读通道）

        Flow Region 是文本流的允许区域。
        """
        # 从页面布局中提取文本区域
        regions = []
        for layout in page.page_layout:
            if hasattr(layout, "class_name") and layout.class_name in ["text", "title"]:
                if layout.box:
                    regions.append({
                        "type": "text_region",
                        "box": layout.box,
                        "label": layout.class_name,
                    })
        return regions

    def _get_decorations(self, page: il_version_1.Page) -> list:
        """获取页面上的装饰体（页码、Logo 等）

        装饰体不参与文本绕排。
        """
        decorations = []

        # 页眉页脚区域（通常是页面顶部和底部的窄条）
        page_height = page.cropbox.box.y2 - page.cropbox.box.y
        page_width = page.cropbox.box.x2 - page.cropbox.box.x

        # 顶部 5% 区域可能是页眉
        header_height = page_height * 0.05
        decorations.append({
            "type": "header_zone",
            "box": il_version_1.Box(
                x=page.cropbox.box.x,
                y=page.cropbox.box.y2 - header_height,
                x2=page.cropbox.box.x2,
                y2=page.cropbox.box.y2,
            ),
            "label": "header zone",
        })

        # 底部 5% 区域可能是页脚
        footer_height = page_height * 0.05
        decorations.append({
            "type": "footer_zone",
            "box": il_version_1.Box(
                x=page.cropbox.box.x,
                y=page.cropbox.box.y,
                x2=page.cropbox.box.x2,
                y2=page.cropbox.box.y + footer_height,
            ),
            "label": "footer zone",
        })

        return decorations

    def _get_merged_areas(self, page: il_version_1.Page) -> list:
        """获取合并区域（多个小区域合并后的结果）

        合并区域是通过 can_merge 规则合并的相邻文本区域。
        """
        # 这里简化处理，实际应该从 Flow Skeleton 提取
        return []

    def _draw_occupier(self, svg: "SvgBuilder", obj: dict, page_height: float):
        """绘制占位体"""
        box = obj["box"]
        x, y = self._pdf_to_svg(box.x, box.y2, page_height)
        w = box.x2 - box.x
        h = box.y2 - box.y

        svg.add_rect(x, y, w, h,
                     stroke=OCCUPIER_COLOR, fill=OCCUPIER_FILL, stroke_width=1)
        svg.add_text(x + 3, y + 12, obj["label"],
                     font_size=8, fill=OCCUPIER_COLOR)

    def _draw_flow_line(self, svg: "SvgBuilder", char: il_version_1.PdfCharacter,
                        page_height: float):
        """绘制流体行（单个字符）"""
        if not char.box:
            return

        x, y = self._pdf_to_svg(char.box.x, char.box.y2, page_height)
        w = char.box.x2 - char.box.x
        h = char.box.y2 - char.box.y

        # 用小矩形表示字符
        svg.add_rect(x, y, max(w, 1), max(h, 1),
                     stroke="none", fill=FLOW_LINE_COLOR, opacity=0.3)

    def _draw_flow_region(self, svg: "SvgBuilder", region: dict, page_height: float):
        """绘制 Flow Region"""
        box = region["box"]
        x, y = self._pdf_to_svg(box.x, box.y2, page_height)
        w = box.x2 - box.x
        h = box.y2 - box.y

        svg.add_rect(x, y, w, h,
                     stroke=FLOW_REGION_COLOR, fill=FLOW_REGION_FILL,
                     stroke_width=0.5, stroke_dasharray="3,3")
        svg.add_text(x + 3, y + 10, region["label"],
                     font_size=7, fill=FLOW_REGION_COLOR)

    def _draw_decoration(self, svg: "SvgBuilder", decoration: dict, page_height: float):
        """绘制装饰体"""
        box = decoration["box"]
        x, y = self._pdf_to_svg(box.x, box.y2, page_height)
        w = box.x2 - box.x
        h = box.y2 - box.y

        svg.add_rect(x, y, w, h,
                     stroke=DECORATION_COLOR, fill=DECORATION_FILL,
                     stroke_width=0.5, stroke_dasharray="5,5")
        svg.add_text(x + 3, y + 10, decoration["label"],
                     font_size=7, fill=DECORATION_COLOR)

    def _draw_merged_area(self, svg: "SvgBuilder", merged: dict, page_height: float):
        """绘制合并区域"""
        box = merged["box"]
        x, y = self._pdf_to_svg(box.x, box.y2, page_height)
        w = box.x2 - box.x
        h = box.y2 - box.y

        svg.add_rect(x, y, w, h,
                     stroke=MERGED_COLOR, fill=MERGED_FILL,
                     stroke_width=1, stroke_dasharray="8,4")

    def _pdf_to_svg(self, pdf_x: float, pdf_y: float, page_height: float) -> tuple[float, float]:
        """将 PDF 坐标转换为 SVG 坐标

        PDF 坐标系：原点左下，y 轴向上
        SVG 坐标系：原点左上，y 轴向下

        Args:
            pdf_x: PDF x 坐标
            pdf_y: PDF y 坐标（注意：这里传入的是 PDF 坐标系的 y 值）
            page_height: 页面高度

        Returns:
            (svg_x, svg_y) SVG 坐标
        """
        svg_x = pdf_x
        svg_y = page_height - pdf_y
        return svg_x, svg_y


class SvgBuilder:
    """SVG 文件构建器"""

    def __init__(self, width: float, height: float):
        """初始化 SVG 构建器

        Args:
            width: SVG 宽度（pt）
            height: SVG 高度（pt）
        """
        self.width = width
        self.height = height
        self.elements: list[str] = []

    def add_rect(self, x: float, y: float, width: float, height: float,
                 stroke: str = "black", fill: str = "none",
                 stroke_width: float = 1, stroke_dasharray: str = "",
                 opacity: float = 1.0):
        """添加矩形元素

        Args:
            x: 左上角 x 坐标
            y: 左上角 y 坐标
            width: 宽度
            height: 高度
            stroke: 边框颜色
            fill: 填充颜色
            stroke_width: 边框宽度
            stroke_dasharray: 虚线模式
            opacity: 透明度
        """
        attrs = [
            f'x="{x:.2f}"',
            f'y="{y:.2f}"',
            f'width="{width:.2f}"',
            f'height="{height:.2f}"',
            f'stroke="{stroke}"',
            f'fill="{fill}"',
            f'stroke-width="{stroke_width}"',
        ]
        if stroke_dasharray:
            attrs.append(f'stroke-dasharray="{stroke_dasharray}"')
        if opacity < 1.0:
            attrs.append(f'opacity="{opacity}"')

        self.elements.append(f'<rect {" ".join(attrs)} />')

    def add_text(self, x: float, y: float, text: str,
                 font_size: float = 12, fill: str = "black",
                 anchor: str = "start"):
        """添加文本元素

        Args:
            x: 文本 x 坐标
            y: 文本 y 坐标
            text: 文本内容
            font_size: 字体大小
            fill: 文本颜色
            anchor: 文本锚点（start/middle/end）
        """
        # 转义 XML 特殊字符
        text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        self.elements.append(
            f'<text x="{x:.2f}" y="{y:.2f}" font-size="{font_size}" '
            f'fill="{fill}" text-anchor="{anchor}" font-family="sans-serif">{text}</text>'
        )

    def add_line(self, x1: float, y1: float, x2: float, y2: float,
                 stroke: str = "black", stroke_width: float = 1,
                 stroke_dasharray: str = ""):
        """添加线条元素

        Args:
            x1: 起点 x 坐标
            y1: 起点 y 坐标
            x2: 终点 x 坐标
            y2: 终点 y 坐标
            stroke: 线条颜色
            stroke_width: 线条宽度
            stroke_dasharray: 虚线模式
        """
        attrs = [
            f'x1="{x1:.2f}"',
            f'y1="{y1:.2f}"',
            f'x2="{x2:.2f}"',
            f'y2="{y2:.2f}"',
            f'stroke="{stroke}"',
            f'stroke-width="{stroke_width}"',
        ]
        if stroke_dasharray:
            attrs.append(f'stroke-dasharray="{stroke_dasharray}"')

        self.elements.append(f'<line {" ".join(attrs)} />')

    def add_polygon(self, points: list[tuple[float, float]],
                    stroke: str = "black", fill: str = "none",
                    stroke_width: float = 1, stroke_dasharray: str = ""):
        """添加多边形元素

        Args:
            points: 多边形顶点列表 [(x, y), ...]
            stroke: 边框颜色
            fill: 填充颜色
            stroke_width: 边框宽度
            stroke_dasharray: 虚线模式
        """
        points_str = " ".join(f"{x:.2f},{y:.2f}" for x, y in points)
        attrs = [
            f'points="{points_str}"',
            f'stroke="{stroke}"',
            f'fill="{fill}"',
            f'stroke-width="{stroke_width}"',
        ]
        if stroke_dasharray:
            attrs.append(f'stroke-dasharray="{stroke_dasharray}"')

        self.elements.append(f'<polygon {" ".join(attrs)} />')

    def save(self, file_path: str):
        """保存 SVG 文件

        Args:
            file_path: 输出文件路径
        """
        svg_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg"
     width="{self.width:.2f}pt" height="{self.height:.2f}pt"
     viewBox="0 0 {self.width:.2f} {self.height:.2f}">
<style>
  rect {{ shape-rendering: crispEdges; }}
</style>
{chr(10).join(self.elements)}
</svg>"""

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(svg_content)
