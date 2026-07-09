"""Flow Skeleton 提取器

从原版 PDF 提取出版社骨架（PublisherSkeleton）：
1. 提取 Visual Objects（图片、Quote、Header/Footer）
2. 提取 glyph 占位（或回退到 page_layout）
3. 构建 Flow Regions（阅读通道）
4. 分析拓扑状态机（FlowTopology）
5. 提取样式区域（StyleRegion）

核心思想：Flow Skeleton 从 glyph 占位 + 对象占位共同推导。
- glyph 占位 = 原版文字实际占用的空间
- 对象占位 = 图片/Quote 等占用的空间
- Flow 通道 = glyph 占位（原版文字实际走的路）
- 对象只解释"为什么 Flow 通道长这样"
"""

import logging
import statistics
from dataclasses import dataclass, field
from enum import Enum

from babeldoc.format.pdf.document_il import il_version_1
from babeldoc.format.pdf.document_il.utils.layout_helper import is_quote_block

logger = logging.getLogger(__name__)


# ============================================================
# 数据结构
# ============================================================

class FlowStateType(Enum):
    """Flow 状态类型"""
    FULL = "full"              # 全宽
    LEFT_WRAP = "left_wrap"    # 左侧收窄（右侧有图片）
    RIGHT_WRAP = "right_wrap"  # 右侧收窄（左侧有图片）
    MULTI_COLUMN = "multi"     # 多栏（图片在中间）
    HEADER = "header"          # 页眉区域
    FOOTER = "footer"          # 页脚区域
    QUOTE = "quote"            # Quote 区域
    FULL_IMAGE = "full_image"  # 整页图片，无可用空间


class ConstraintPriority(Enum):
    """约束优先级"""
    HARD = "hard"          # 绝对不可侵犯（Logo、页码）
    SOFT = "soft"          # 尽量保持（图片、Quote）
    RELAXABLE = "relaxable"  # 可以调整（正文间距、字号）


@dataclass
class FlowRegion:
    """一个 Flow 区域（阅读通道）"""
    region_id: int
    y_start: float
    y_end: float
    intervals: list[tuple[float, float]]
    state: FlowStateType
    xobj_id: int | None = None
    confidence: float = 1.0
    source: str = ""  # "glyph_extraction", "object_constraint", "layout_model"


@dataclass
class FlowState:
    """一个 Flow 状态"""
    type: FlowStateType
    y_start: float
    y_end: float
    intervals: list[tuple[float, float]]


@dataclass
class FlowTransition:
    """状态转换"""
    y: float
    from_state: FlowStateType
    to_state: FlowStateType
    trigger: str


@dataclass
class FlowTopology:
    """Flow 的拓扑状态机"""
    states: list[FlowState] = field(default_factory=list)
    transitions: list[FlowTransition] = field(default_factory=list)


@dataclass
class StyleRegion:
    """一个样式的区域"""
    y_start: float
    y_end: float
    font_size: float
    font_family: str
    font_weight: str   # "normal" / "bold"
    font_style: str    # "normal" / "italic"
    leading: float
    first_line_indent: float
    left_indent: float
    right_indent: float
    alignment: str  # "left" / "center" / "right" / "justify"
    space_before: float
    space_after: float
    xobj_id: int | None = None


@dataclass
class Padding:
    """内边距"""
    left: float = 0.0
    right: float = 0.0
    top: float = 0.0
    bottom: float = 0.0

    @staticmethod
    def uniform(value: float) -> 'Padding':
        return Padding(left=value, right=value, top=value, bottom=value)

    @staticmethod
    def adaptive(font_size: float) -> 'Padding':
        p = max(font_size * 0.5, 12)
        return Padding.uniform(p)


@dataclass
class VisualObject:
    """视觉对象的统一抽象"""
    kind: str  # "image", "quote", "caption", "sidebar", "header", "footer"
    bbox: il_version_1.Box
    padding: Padding
    priority: ConstraintPriority
    xobj_id: int | None = None


@dataclass
class PublisherSkeleton:
    """出版社骨架"""
    regions: list[FlowRegion] = field(default_factory=list)
    style_regions: list[StyleRegion] = field(default_factory=list)
    objects: list[VisualObject] = field(default_factory=list)
    topology: FlowTopology = field(default_factory=FlowTopology)
    page_x_min: float = 0.0
    page_x_max: float = 612.0
    page_y_min: float = 0.0
    page_y_max: float = 792.0
    xobj_id: int | None = None

    def get_intervals_at(self, y: float) -> list[tuple[float, float]]:
        """获取指定 y 坐标的区间集合。

        Args:
            y: y 坐标

        Returns:
            区间列表 [(x1, x2), ...]
        """
        for region in self.regions:
            if region.y_start <= y <= region.y_end:
                return region.intervals
        return []

    def get_style_at(self, y: float) -> StyleRegion | None:
        """获取指定 y 坐标的样式区域。

        Args:
            y: y 坐标

        Returns:
            样式区域，如果没有则返回 None
        """
        for style in self.style_regions:
            if style.y_start <= y <= style.y_end:
                return style
        return None

    def get_objects_at(self, y: float) -> list[VisualObject]:
        """获取指定 y 坐标的视觉对象。

        Args:
            y: y 坐标

        Returns:
            视觉对象列表
        """
        objects = []
        for obj in self.objects:
            if obj.bbox.y <= y <= obj.bbox.y2:
                objects.append(obj)
        return objects


# ============================================================
# 提取算法
# ============================================================

def extract_publisher_skeleton(page: il_version_1.Page) -> PublisherSkeleton:
    """
    从原版 PDF 提取出版社骨架。

    算法：
    1. 提取 Visual Objects（图片、Quote、Header/Footer）
    2. 提取 glyph 占位（或回退到 page_layout）
    3. 构建 Flow Regions（阅读通道）
    4. 分析拓扑状态机（FlowTopology）
    5. 提取样式区域（StyleRegion）
    """
    # 1. 提取 Visual Objects
    objects = extract_visual_objects(page)

    # 2. 提取 glyph 占位（扫描 PDF 回退到 page_layout）
    glyph_lines = extract_glyph_lines_or_fallback(page)

    # 3. 构建 Flow Regions
    regions = build_flow_regions(glyph_lines, objects, page)

    # 4. 分析拓扑
    topology = analyze_topology(regions)

    # 5. 提取样式（复用 StylesAndFormulas）
    style_regions = extract_style_regions(page)

    return PublisherSkeleton(
        regions=regions,
        style_regions=style_regions,
        objects=objects,
        topology=topology,
        page_x_min=page.cropbox.box.x,
        page_x_max=page.cropbox.box.x2,
        page_y_min=page.cropbox.box.y,
        page_y_max=page.cropbox.box.y2,
    )


def extract_visual_objects(page: il_version_1.Page) -> list[VisualObject]:
    """提取页面上的视觉对象"""
    objects = []

    # 图片
    for form in page.pdf_form:
        if form.box:
            objects.append(VisualObject(
                kind="image",
                bbox=form.box,
                padding=Padding.adaptive(get_page_font_size(page)),
                priority=ConstraintPriority.SOFT,
                xobj_id=getattr(form, 'xobj_id', None),
            ))

    # Figure
    for figure in page.pdf_figure:
        if figure.box:
            objects.append(VisualObject(
                kind="figure",
                bbox=figure.box,
                padding=Padding.uniform(12),
                priority=ConstraintPriority.SOFT,
            ))

    # Quote（复用 is_quote_block）
    page_width = page.cropbox.box.x2 - page.cropbox.box.x
    for para in page.pdf_paragraph:
        if is_quote_block(para, page_width):
            objects.append(VisualObject(
                kind="quote",
                bbox=para.box,
                padding=Padding(left=24, right=8, top=8, bottom=8),
                priority=ConstraintPriority.SOFT,
            ))

    # Header/Footer
    header, footer = detect_header_footer(page)
    if header:
        objects.append(VisualObject(
            kind="header",
            bbox=header,
            padding=Padding.uniform(0),
            priority=ConstraintPriority.HARD,
        ))
    if footer:
        objects.append(VisualObject(
            kind="footer",
            bbox=footer,
            padding=Padding.uniform(0),
            priority=ConstraintPriority.HARD,
        ))

    return objects


def get_page_font_size(page: il_version_1.Page) -> float:
    """获取页面的主要字号。从 PdfCharacter 的 pdf_style.font_size 取 mode。"""
    sizes = []
    for c in page.pdf_character:
        if c.pdf_style and c.pdf_style.font_size:
            sizes.append(c.pdf_style.font_size)
    if sizes:
        try:
            return statistics.mode(sizes)
        except statistics.StatisticsError:
            return sum(sizes) / len(sizes)
    return 10.0


def detect_header_footer(page: il_version_1.Page) -> tuple[il_version_1.Box | None, il_version_1.Box | None]:
    """检测页眉页脚区域"""
    page_height = page.cropbox.box.y2 - page.cropbox.box.y
    page_width = page.cropbox.box.x2 - page.cropbox.box.x

    # 顶部 5% 区域可能是页眉
    header_height = page_height * 0.05
    header_box = il_version_1.Box(
        x=page.cropbox.box.x,
        y=page.cropbox.box.y2 - header_height,
        x2=page.cropbox.box.x2,
        y2=page.cropbox.box.y2,
    )

    # 底部 5% 区域可能是页脚
    footer_height = page_height * 0.05
    footer_box = il_version_1.Box(
        x=page.cropbox.box.x,
        y=page.cropbox.box.y,
        x2=page.cropbox.box.x2,
        y2=page.cropbox.box.y + footer_height,
    )

    return header_box, footer_box


def extract_glyph_lines_or_fallback(page: il_version_1.Page) -> list[dict]:
    """
    提取原版 PDF 的 glyph 占位。

    优先从 PdfCharacter 提取。
    扫描 PDF（无 glyph）回退到 page_layout 区域。
    """
    if page.pdf_character:
        return extract_glyph_lines(page)
    else:
        # 扫描 PDF：从 page_layout 区域推导
        return extract_lines_from_layout_regions(page)


def extract_glyph_lines(page: il_version_1.Page) -> list[dict]:
    """
    提取原版 PDF 的 glyph 占位。

    返回: [{"y": float, "glyphs": [Box], "x_min": float, "x_max": float,
            "xobj_id": int|None}, ...]
    """
    # 按 xobj_id 分组，过滤掉没有 box 的字符
    chars_by_xobj = {}
    for char in page.pdf_character:
        if char.box is None:
            continue  # 跳过没有 box 的字符
        xobj_id = char.xobj_id
        if xobj_id not in chars_by_xobj:
            chars_by_xobj[xobj_id] = []
        chars_by_xobj[xobj_id].append(char)

    all_lines = []
    for xobj_id, chars in chars_by_xobj.items():
        # 按 y 坐标聚类
        lines = cluster_chars_into_lines(chars)
        for line_chars in lines:
            y_center = sum(c.box.y + c.box.y2 for c in line_chars) / (2 * len(line_chars))
            x_min = min(c.box.x for c in line_chars)
            x_max = max(c.box.x2 for c in line_chars)
            all_lines.append({
                "y": y_center,
                "glyphs": [c.box for c in line_chars],
                "x_min": x_min,
                "x_max": x_max,
                "xobj_id": xobj_id,
            })

    return sorted(all_lines, key=lambda l: l["y"])


def cluster_chars_into_lines(chars: list[il_version_1.PdfCharacter]) -> list[list[il_version_1.PdfCharacter]]:
    """
    按 y 坐标聚类成行。

    使用相对阈值：median_height * 0.5
    """
    # 过滤掉没有 box 的字符
    chars = [c for c in chars if c.box is not None]
    if not chars:
        return []

    sorted_chars = sorted(chars, key=lambda c: (c.box.y + c.box.y2) / 2)

    # 计算相对阈值
    heights = [c.box.y2 - c.box.y for c in sorted_chars if c.box.y2 > c.box.y]
    median_height = statistics.median(heights) if heights else 10.0
    y_threshold = median_height * 0.5

    lines = []
    current_line = [sorted_chars[0]]
    current_y = (sorted_chars[0].box.y + sorted_chars[0].box.y2) / 2

    for char in sorted_chars[1:]:
        char_y = (char.box.y + char.box.y2) / 2
        if abs(char_y - current_y) < y_threshold:
            current_line.append(char)
        else:
            lines.append(current_line)
            current_line = [char]
            current_y = char_y

    lines.append(current_line)
    return lines


def extract_lines_from_layout_regions(page: il_version_1.Page) -> list[dict]:
    """
    扫描 PDF 回退：从 page_layout 区域推导 glyph 占位。
    """
    lines = []
    for layout in page.page_layout:
        if not is_text_layout(layout):
            continue

        # 将布局区域视为一个大的 glyph 占位
        y_center = (layout.box.y + layout.box.y2) / 2
        lines.append({
            "y": y_center,
            "glyphs": [layout.box],
            "x_min": layout.box.x,
            "x_max": layout.box.x2,
            "xobj_id": None,
        })

    return sorted(lines, key=lambda l: l["y"])


def is_text_layout(layout: il_version_1.PageLayout) -> bool:
    """检查布局区域是否为文本区域"""
    if hasattr(layout, "class_name"):
        return layout.class_name in ["text", "title", "fallback_line"]
    return False


def build_flow_regions(glyph_lines: list[dict],
                       objects: list[VisualObject],
                       page: il_version_1.Page) -> list[FlowRegion]:
    """
    从 glyph 占位 + 对象占位构建 Flow Regions。

    核心逻辑：
    - glyph 占位 = 原版文字实际占用的空间
    - 对象占位 = 图片/Quote 等占用的空间
    - Flow 通道 = glyph 占位（原版文字实际走的路）
    - 对象只解释"为什么 Flow 通道长这样"
    """
    if not glyph_lines:
        return []

    page_width = page.cropbox.box.x2 - page.cropbox.box.x
    regions = []
    current_region = None
    region_id_counter = 0

    for line in glyph_lines:
        y = line["y"]
        x_min = line["x_min"]
        x_max = line["x_max"]
        xobj_id = line["xobj_id"]

        # 确定 Flow 状态
        state = determine_flow_state(x_min, x_max, page_width, page)

        # 确定区间（直接使用 glyph 占位）
        intervals = determine_intervals_from_glyphs(x_min, x_max, objects, page)

        # 尝试合并到当前区域
        if current_region and can_merge(current_region, state, intervals, y):
            current_region.y_end = y
        else:
            # 开始新区域
            if current_region:
                regions.append(current_region)
            region_id_counter += 1
            current_region = FlowRegion(
                region_id=region_id_counter,
                y_start=y,
                y_end=y,
                intervals=intervals,
                state=state,
                xobj_id=xobj_id,
                confidence=1.0 if page.pdf_character else 0.3,
                source="glyph_extraction" if page.pdf_character else "layout_model_fallback",
            )

    if current_region:
        regions.append(current_region)

    # 补充：对象区域中没有 glyph 的部分（如图片下方的空白）
    regions = supplement_regions_from_objects(regions, objects, page)

    return regions


def determine_flow_state(x_min: float, x_max: float,
                         page_width: float,
                         page: il_version_1.Page) -> FlowStateType:
    """
    确定一行的 Flow 状态。

    使用绝对宽度而非 ratio，避免误判。
    """
    line_width = x_max - x_min
    left_margin = x_min - page.cropbox.box.x
    right_margin = page.cropbox.box.x2 - x_max

    # 全宽：行宽接近页面宽度（允许 50pt 误差，覆盖正常页边距）
    if line_width >= page_width - 50:
        return FlowStateType.FULL

    # 双栏：行宽 < 页面宽度 60%，且左右都有大量空白
    if line_width < page_width * 0.6 and left_margin > 50 and right_margin > 50:
        return FlowStateType.MULTI_COLUMN

    # 左侧收窄：右边有大量空白（> 100pt）
    if right_margin > 100 and left_margin <= 50:
        return FlowStateType.LEFT_WRAP

    # 右侧收窄：左边有大量空白（> 100pt）
    if left_margin > 100 and right_margin <= 50:
        return FlowStateType.RIGHT_WRAP

    # 默认：视为全宽
    return FlowStateType.FULL


def determine_intervals_from_glyphs(x_min: float, x_max: float,
                                     objects: list[VisualObject],
                                     page: il_version_1.Page) -> list[tuple[float, float]]:
    """
    从 glyph 占位确定区间。

    直接使用 glyph 占位，不从全跨度减去对象。
    如果 glyph 已经绕过图片，x_min/x_max 自然就是正确的区间。
    只有当 glyph 跨度与对象重叠时，才需要分割。
    """
    # 基本区间 = glyph 占位
    intervals = [(x_min, x_max)]

    # 检查是否有对象在 glyph 跨度内（可能需要分割）
    for obj in objects:
        if obj.kind in ("header", "footer"):
            continue  # Header/Footer 不影响水平区间

        obj_left = obj.bbox.x - obj.padding.left
        obj_right = obj.bbox.x2 + obj.padding.right

        new_intervals = []
        for ix1, ix2 in intervals:
            if obj_left > ix1 and obj_right < ix2:
                # 对象在区间中间 → 分割为两个区间
                new_intervals.append((ix1, obj_left))
                new_intervals.append((obj_right, ix2))
            elif obj_left <= ix1 and obj_right >= ix1 and obj_right < ix2:
                # 对象覆盖区间左侧 → 收窄
                new_intervals.append((obj_right, ix2))
            elif obj_left > ix1 and obj_left <= ix2 and obj_right >= ix2:
                # 对象覆盖区间右侧 → 收窄
                new_intervals.append((ix1, obj_left))
            elif obj_left <= ix1 and obj_right >= ix2:
                # 对象完全覆盖区间 → 区间消失
                pass
            else:
                # 对象不在区间内
                new_intervals.append((ix1, ix2))

        intervals = new_intervals

    # 过滤掉太窄的区间（< 16pt，放不下任何文字）
    intervals = [(ix1, ix2) for ix1, ix2 in intervals if ix2 - ix1 >= 16]

    return intervals if intervals else [(x_min, x_max)]  # 至少保留原始区间


def can_merge(current: FlowRegion, new_state: FlowStateType,
              new_intervals: list[tuple[float, float]],
              new_y: float,
              line_height: float = 14.0) -> bool:
    """判断是否可以合并到当前区域。"""
    # 状态相同
    if current.state != new_state:
        return False

    # 区间数量相同
    if len(current.intervals) != len(new_intervals):
        return False

    # 区间宽度变化不大（< 20pt）
    for (cx1, cx2), (nx1, nx2) in zip(current.intervals, new_intervals):
        if abs((cx2 - cx1) - (nx2 - nx1)) > 20:
            return False

    # y 距离不超过 3 倍行高（避免合并相距很远的区域）
    if new_y - current.y_end > line_height * 3:
        return False

    return True


def supplement_regions_from_objects(regions: list[FlowRegion],
                                    objects: list[VisualObject],
                                    page: il_version_1.Page) -> list[FlowRegion]:
    """
    用对象信息补充 Flow Regions。

    例如：图片下方没有 glyph 的区域，补充为可用区间。
    """
    # 找出所有对象覆盖的 y 范围
    object_y_ranges = [(obj.bbox.y, obj.bbox.y2) for obj in objects
                       if obj.kind in ("image", "figure")]

    # 找出 regions 之间的空白区域
    supplemented = []
    for i in range(len(regions) - 1):
        gap_start = regions[i].y_end
        gap_end = regions[i + 1].y_start

        if gap_end - gap_start < 5:
            continue  # 间隙太小，跳过

        # 检查间隙是否与对象重叠
        is_object_area = any(
            obj_start <= gap_start and obj_end >= gap_end
            for obj_start, obj_end in object_y_ranges
        )

        if not is_object_area:
            # 间隙不是对象区域，补充为全宽区域
            supplemented.append(FlowRegion(
                region_id=len(regions) + len(supplemented) + 1,
                y_start=gap_start,
                y_end=gap_end,
                intervals=[(page.cropbox.box.x, page.cropbox.box.x2)],
                state=FlowStateType.FULL,
                confidence=0.5,
                source="object_supplement",
            ))

    return regions + supplemented


# ============================================================
# 拓扑分析
# ============================================================

def analyze_topology(regions: list[FlowRegion]) -> FlowTopology:
    """分析 Flow 的拓扑状态机。"""
    states = []
    transitions = []

    for i, region in enumerate(regions):
        states.append(FlowState(
            type=region.state,
            y_start=region.y_start,
            y_end=region.y_end,
            intervals=region.intervals,
        ))

        if i > 0:
            prev = regions[i - 1]
            if prev.state != region.state:
                transitions.append(FlowTransition(
                    y=region.y_start,
                    from_state=prev.state,
                    to_state=region.state,
                    trigger=determine_trigger(prev, region),
                ))

    return FlowTopology(states=states, transitions=transitions)


def determine_trigger(prev: FlowRegion, curr: FlowRegion) -> str:
    """确定状态转换的触发原因。"""
    triggers = {
        (FlowStateType.FULL, FlowStateType.RIGHT_WRAP): "image_start",
        (FlowStateType.RIGHT_WRAP, FlowStateType.FULL): "image_end",
        (FlowStateType.FULL, FlowStateType.LEFT_WRAP): "image_start",
        (FlowStateType.LEFT_WRAP, FlowStateType.FULL): "image_end",
        (FlowStateType.FULL, FlowStateType.MULTI_COLUMN): "column_start",
        (FlowStateType.MULTI_COLUMN, FlowStateType.FULL): "column_end",
        (FlowStateType.FULL, FlowStateType.QUOTE): "quote_start",
        (FlowStateType.QUOTE, FlowStateType.FULL): "quote_end",
        (FlowStateType.FULL, FlowStateType.HEADER): "header_start",
        (FlowStateType.FULL, FlowStateType.FOOTER): "footer_start",
        (FlowStateType.HEADER, FlowStateType.FULL): "header_end",
        (FlowStateType.FOOTER, FlowStateType.FULL): "footer_end",
    }
    return triggers.get((prev.state, curr.state), "unknown")


# ============================================================
# 样式提取
# ============================================================

def extract_style_regions(page: il_version_1.Page) -> list[StyleRegion]:
    """
    提取原版的样式区域。

    从 PdfCharacter 的 pdf_style 提取字体信息。
    """
    style_regions = []

    for para in page.pdf_paragraph:
        if not para.pdf_paragraph_composition:
            continue

        # 从 PdfCharacter 的 pdf_style 提取字体信息
        font_size = get_paragraph_font_size(para)
        font_family = get_paragraph_font_family(para)
        # 构建页面字体字典用于查找 bold/italic
        page_fonts = {f.font_id: f for f in page.pdf_font if f.font_id}
        font_weight = get_paragraph_font_weight(para, page_fonts)
        font_style = get_paragraph_font_style(para, page_fonts)

        # 从字符位置推导行距
        leading = compute_leading_from_chars(para)

        # 从字符位置推导缩进
        first_line_indent = compute_first_line_indent(para)
        left_indent = compute_left_indent(para)

        # 从字符位置推导对齐
        alignment = detect_alignment(para)

        # 段落间距（从相邻段落的 gap 推导）
        space_before, space_after = compute_paragraph_spacing(para, page)

        style_regions.append(StyleRegion(
            y_start=para.box.y,
            y_end=para.box.y2,
            font_size=font_size,
            font_family=font_family,
            font_weight=font_weight,
            font_style=font_style,
            leading=leading,
            first_line_indent=first_line_indent,
            left_indent=left_indent,
            right_indent=0,
            alignment=alignment,
            space_before=space_before,
            space_after=space_after,
        ))

    return style_regions


def get_chars_from_composition(comp: il_version_1.PdfParagraphComposition) -> list[il_version_1.PdfCharacter]:
    """从 PdfParagraphComposition 中提取 PdfCharacter 列表。"""
    if comp.pdf_character:
        return [comp.pdf_character]
    elif comp.pdf_line and comp.pdf_line.pdf_character:
        return comp.pdf_line.pdf_character
    elif comp.pdf_same_style_characters:
        return comp.pdf_same_style_characters.pdf_character
    elif comp.pdf_formula:
        return comp.pdf_formula.pdf_character
    return []


def get_all_chars(para: il_version_1.PdfParagraph) -> list[il_version_1.PdfCharacter]:
    """从段落中提取所有 PdfCharacter。"""
    chars = []
    for comp in para.pdf_paragraph_composition:
        chars.extend(get_chars_from_composition(comp))
    return chars


def get_paragraph_font_size(para: il_version_1.PdfParagraph) -> float:
    """从段落字符的 pdf_style.font_size 取 mode。"""
    sizes = []
    for comp in para.pdf_paragraph_composition:
        chars = get_chars_from_composition(comp)
        for c in chars:
            if c.pdf_style and c.pdf_style.font_size:
                sizes.append(c.pdf_style.font_size)
    if sizes:
        try:
            return statistics.mode(sizes)
        except statistics.StatisticsError:
            return sum(sizes) / len(sizes)
    return 10.0


def get_paragraph_font_family(para: il_version_1.PdfParagraph) -> str:
    """从段落字符的 pdf_style.font 取第一个。"""
    for comp in para.pdf_paragraph_composition:
        chars = get_chars_from_composition(comp)
        for c in chars:
            if c.pdf_style and c.pdf_style.font_id:
                return c.pdf_style.font_id
    return ""


def get_paragraph_font_weight(para: il_version_1.PdfParagraph, fonts: dict[str, il_version_1.PdfFont] | None = None) -> str:
    """从段落字符推断字体粗细。"""
    if not fonts:
        return "normal"
    for comp in para.pdf_paragraph_composition:
        chars = get_chars_from_composition(comp)
        for c in chars:
            if c.pdf_style and c.pdf_style.font_id:
                font = fonts.get(c.pdf_style.font_id)
                if font and font.bold:
                    return "bold"
    return "normal"


def get_paragraph_font_style(para: il_version_1.PdfParagraph, fonts: dict[str, il_version_1.PdfFont] | None = None) -> str:
    """从段落字符推断字体样式。"""
    if not fonts:
        return "normal"
    for comp in para.pdf_paragraph_composition:
        chars = get_chars_from_composition(comp)
        for c in chars:
            if c.pdf_style and c.pdf_style.font_id:
                font = fonts.get(c.pdf_style.font_id)
                if font and font.italic:
                    return "italic"
    return "normal"


def compute_leading_from_chars(para: il_version_1.PdfParagraph) -> float:
    """从字符位置推导行距。"""
    chars = get_all_chars(para)
    if len(chars) < 2:
        return 14.0  # 默认行距

    # 按 y 坐标排序
    sorted_chars = sorted(chars, key=lambda c: (c.box.y + c.box.y2) / 2)

    # 计算相邻行的 y 差值
    y_diffs = []
    for i in range(1, len(sorted_chars)):
        y1 = (sorted_chars[i-1].box.y + sorted_chars[i-1].box.y2) / 2
        y2 = (sorted_chars[i].box.y + sorted_chars[i].box.y2) / 2
        diff = abs(y2 - y1)
        if diff > 1:  # 过滤掉同行的字符
            y_diffs.append(diff)

    if y_diffs:
        return statistics.median(y_diffs)
    return 14.0


def compute_first_line_indent(para: il_version_1.PdfParagraph) -> float:
    """从字符位置推导首行缩进。

    只看第一行字符（y 坐标最高的字符），而非所有字符。
    """
    chars = get_all_chars(para)
    if not chars:
        return 0.0

    # 找到第一行字符（y 坐标最大的字符，PDF 坐标系 y 轴向上）
    # 先按 y 坐标降序排序，取 y 值最大的字符作为第一行
    sorted_chars = sorted(chars, key=lambda c: (c.box.y + c.box.y2) / 2, reverse=True)
    first_line_y = (sorted_chars[0].box.y + sorted_chars[0].box.y2) / 2

    # 聚类第一行字符（y 坐标接近的字符）
    heights = [c.box.y2 - c.box.y for c in sorted_chars if c.box.y2 > c.box.y]
    median_height = statistics.median(heights) if heights else 10.0
    y_threshold = median_height * 0.5

    first_line_chars = []
    for c in sorted_chars:
        char_y = (c.box.y + c.box.y2) / 2
        if abs(char_y - first_line_y) < y_threshold:
            first_line_chars.append(c)
        else:
            break  # 已经离开第一行

    if not first_line_chars:
        return 0.0

    # 首行缩进 = 第一行最左边字符的 x 坐标 - 段落左边框
    x_min = min(c.box.x for c in first_line_chars)
    return x_min - para.box.x


def compute_left_indent(para: il_version_1.PdfParagraph) -> float:
    """从字符位置推导左缩进。"""
    chars = get_all_chars(para)
    if not chars:
        return 0.0

    # 找到最左边的字符
    x_min = min(c.box.x for c in chars)

    # 左缩进 = 最左边字符的 x 坐标 - 段落左边框
    return x_min - para.box.x


def detect_alignment(para: il_version_1.PdfParagraph) -> str:
    """从字符位置推导对齐方式。"""
    chars = get_all_chars(para)
    if not chars:
        return "left"

    # 找到最左边和最右边的字符
    x_min = min(c.box.x for c in chars)
    x_max = max(c.box.x2 for c in chars)

    # 计算段落宽度
    para_width = para.box.x2 - para.box.x
    char_width = x_max - x_min

    # 如果字符宽度接近段落宽度，可能是两端对齐
    if abs(char_width - para_width) < 10:
        return "justify"

    # 如果字符集中在中间，可能是居中
    center = (x_min + x_max) / 2
    para_center = (para.box.x + para.box.x2) / 2
    if abs(center - para_center) < 10:
        return "center"

    # 如果字符靠右，可能是右对齐
    if abs(x_max - para.box.x2) < 10:
        return "right"

    return "left"


def compute_paragraph_spacing(para: il_version_1.PdfParagraph,
                              page: il_version_1.Page) -> tuple[float, float]:
    """计算段落间距（从相邻段落的 gap 推导）。"""
    paras = [p for p in page.pdf_paragraph if p.box]
    paras.sort(key=lambda p: p.box.y)

    space_before = 0.0
    space_after = 0.0

    for i, p in enumerate(paras):
        if p is para:
            if i > 0:
                space_before = para.box.y - paras[i-1].box.y2
            if i < len(paras) - 1:
                space_after = paras[i+1].box.y - para.box.y2
            break

    return max(space_before, 0), max(space_after, 0)
