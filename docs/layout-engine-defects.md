# Layout Engine 三大核心缺陷 — 排版质量提升路线图

> **状态**: Draft
> **优先级**: P0 (阻塞排版质量)
> **目标**: 将 Typesetting Engine 从"能用"提升到"接近原版"水平

---

## 概述

当前 BabelDOC 的排版质量存在三个相互关联的底层缺陷。它们不是翻译问题，而是 **Layout Engine** 的结构性问题。解决这三个问题后，整体排版质量会比继续增加新的布局识别算法带来更明显的提升。

| # | 缺陷 | 影响范围 | 优先级 |
|---|------|---------|--------|
| 1 | 中文段落重排失败 | 所有中文页面 | ⭐⭐⭐⭐⭐ |
| 2 | 图片文字环绕失败 | 所有图文混排页面 | ⭐⭐⭐⭐⭐ |
| 3 | Paragraph Style 丢失 | 所有页面的缩进/对齐 | ⭐⭐⭐⭐ |

---

## 缺陷 1：中文段落重排（Paragraph Typesetting）失败

### 现象

中文段落经常出现行长极不均匀的情况：

```
■■■■■■■■■■■■■■■■■■■■■■■■
■■
■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■
■■■
■■■■■■■■■■■■■■■■■■■■■■■
```

甚至出现错误断词：

```
保持收
缩状态

持续时
间

学习如何获得更持久、
更强烈的高潮……
```

### 期望效果

```
■■■■■■■■■■■■■■■■■■■■
■■■■■■■■■■■■■■■■■■■■
■■■■■■■■■■■■■■■■■■■■
■■■■■■■■■■■■■■■■■■■■
```

### 根本原因分析

当前排版流程：

```
OCR Lines
    │
    ▼
ParagraphFinder (合并行 → 段落)
    │
    ▼
ILTranslator (翻译)
    │
    ▼
Typesetting._layout_typesetting_units (重新排版)
    │
    ▼
生成新 Lines
```

**问题出在 `_layout_typesetting_units`** ([typesetting.py:1860](babeldoc/format/pdf/document_il/midend/typesetting.py#L1860))：

1. **断行逻辑以英文为主导**：`LINE_BREAK_REGEX` ([typesetting.py:33-89](babeldoc/format/pdf/document_il/midend/typesetting.py#L33-L89)) 定义了"不可断行"的字符集，但这只解决了"在哪里可以断"，没有解决"在哪里应该断"。

2. **缺少 CJK 词组保护**：当前逐字符判断 `can_break_line`，没有词组级别的保护。例如"收缩"、"持续"、"时间"等词组不应被拆开。

3. **缺少中文禁则处理**：中文排版有标点禁则（行首禁用句号、逗号等），当前只处理了 `is_hung_punctuation`（悬挂标点）和 `is_cannot_appear_in_line_end_punctuation`（行尾禁用标点），但缺少完整的行首禁则。

4. **DP 优化器的 cost 函数未区分中英文**：`line_break_optimizer.py` 的 `optimal_line_break` 使用 `(available_width - line_width)²` 作为 raggedness，这对中文不够——中文应追求"方块感"（每行等宽），而非英文的"最小 raggedness"。

### 修复方案

#### 1a. 增强 CJK 断行规则

在 `TypesettingUnit` 中增加词组保护逻辑：

```python
# typesetting.py - 新增
def calc_can_break_line(self):
    unicode = self.try_get_unicode()
    if not unicode:
        return True

    # CJK 字符默认可断行（除非是词组内部）
    if self.is_cjk_char:
        # 检查前后字符是否构成词组
        if self._is_in_cjk_word():
            return False
        return True

    # 非 CJK 字符使用现有 regex
    if LINE_BREAK_REGEX.match(unicode):
        return False
    return True
```

#### 1b. 中文禁则处理

增加行首/行尾禁则检查：

```python
# 禁则表
CJK_LINE_START_FORBIDDEN = set("。？！；：，、）】》」』〗〉")  # 行首禁用
CJK_LINE_END_FORBIDDEN = set("（【《「『〖〈")  # 行尾禁用
```

#### 1c. DP 优化器增加 CJK 模式

在 `optimal_line_break` 中增加 CJK 模式的 cost 函数：

```python
def _line_cost_cjk(line_width: float, available: float, ...) -> float:
    # 中文追求等宽：惩罚偏离平均宽度的程度
    ratio = line_width / available if available > 0 else 1.0
    # ratio 接近 1.0 最好，偏离越大惩罚越高
    return (1.0 - ratio) ** 2 * 1000
```

### 涉及文件

| 文件 | 修改内容 |
|------|---------|
| [typesetting.py](babeldoc/format/pdf/document_il/midend/typesetting.py) | `calc_can_break_line` 增加 CJK 词组保护 |
| [typesetting.py](babeldoc/format/pdf/document_il/midend/typesetting.py) | `_layout_typesetting_units` 增加行首/行尾禁则 |
| [line_break_optimizer.py](babeldoc/format/pdf/document_il/midend/line_break_optimizer.py) | `_line_cost` 增加 CJK 模式 |
| [typesetting.py](babeldoc/format/pdf/document/il/midend/typesetting.py) | `LINE_BREAK_REGEX` 补充 CJK 禁则字符 |

---

## 缺陷 2：图片文字环绕（Image Text Wrap）失败

### 现象

图片位于左侧时，文字直接跑到图片下方，右侧空间全部浪费：

```
██████████

██████████

██████████

■■■■■■■■■■■■■■■■■■■■■■
■■■■■■■■■■■■■■■■■■■■■■
```

### 期望效果

```
██████████■■■■■■■■■■■■■■■
██████████■■■■■■■■■■■■■■■
██████████■■■■■■■■■■■■■■■
██████████■■■■■■■■■■■■■■■

■■■■■■■■■■■■■■■■■■■■■■■■
■■■■■■■■■■■■■■■■■■■■■■■■
```

### 根本原因分析

当前代码中 **ExclusionZone 系统已经存在**，而且 `ExclusionZoneIndex.get_available_x_range` ([exclusion_zone.py:363](babeldoc/format/pdf/document_il/midend/exclusion_zone.py#L363)) 已经支持 per-line 的可用宽度查询。

**问题在于 Paragraph Box 的约束**：

1. **Paragraph Box 是全宽的**：`PdfParagraph.box` 在 `ParagraphFinder` 中被设置为所有字符的 bounding box。翻译后，段落的 box 通常覆盖整个页面宽度。

2. **ExclusionZone 只收窄单行**：在 `_layout_typesetting_units` ([typesetting.py:1922-1936](babeldoc/format/pdf/document_il/midend/typesetting.py#L1922-L1936)) 中，每行会查询 `zone_index.get_available_x_range`，但这个查询使用的是 `box.x` 和 `box.x2` 作为默认边界。

3. **关键 Bug**：当图片在左侧时，`get_available_x_range` 会返回 `(image.x2, box.x2)` 作为可用区间。但问题是 **paragraph 的 box.x 可能已经在图片右侧**，导致查询结果不正确。或者，paragraph 的 box 覆盖了整个页面，但第一行从 box.x（页面最左边）开始排版，而不是从图片右侧开始。

4. **更深层的问题**：`get_available_x_range` 返回的是**单个区间** `(available_x, available_x2)`，而不是多个区间。当图片在左侧时，它正确地收窄了 `available_x`。但当图片在中间时（将文本分为左右两栏），当前逻辑只保留更宽的一侧，而不是支持多栏排版。

### 修复方案

#### 2a. 确保 Paragraph Box 正确传递给排版器

当前 `typesetting.py:1929-1936` 的逻辑是正确的，但需要确保：
- Paragraph 的 box 覆盖了正确的区域（不是整个页面，而是该段落实际应出现的区域）
- 对于需要环绕图片的段落，box 应该覆盖图片周围的可用区域

#### 2b. 支持多区间排版（Multi-interval Layout）

当前 `get_available_x_range` 返回单个区间。需要支持返回多个区间，让排版器在当前区间放不下时，跳到下一个区间继续排版（而非直接换行）。

修改 `ExclusionZoneIndex.get_available_x_range` → `get_intervals_at`：

```python
def get_intervals_at(
    self,
    y_bottom: float,
    y_top: float,
    default_x: float,
    default_x2: float,
) -> list[tuple[float, float]]:
    """返回该 y 处所有可用的 x 区间列表。"""
    # ... 现有逻辑 ...
    # 返回所有可用子区间，而非最宽的一个
    return available_intervals
```

#### 2c. 修改 `_layout_typesetting_units` 支持多区间

```python
# 当前逻辑：单区间
available_x, available_x2 = zone_index.get_available_x_range(...)

# 修改为：多区间
intervals = zone_index.get_intervals_at(...)
current_interval_idx = 0
available_x, available_x2 = intervals[0]

# 当当前行放不下时，先尝试下一个区间
if current_x + unit_width > available_x2:
    if current_interval_idx + 1 < len(intervals):
        current_interval_idx += 1
        available_x, available_x2 = intervals[current_interval_idx]
        current_x = available_x
    else:
        # 所有区间都放不下，换行
        ...
```

### 涉及文件

| 文件 | 修改内容 |
|------|---------|
| [exclusion_zone.py](babeldoc/format/pdf/document_il/midend/exclusion_zone.py) | `get_available_x_range` → `get_intervals_at` 返回多区间 |
| [typesetting.py](babeldoc/format/pdf/document_il/midend/typesetting.py) | `_layout_typesetting_units` 支持多区间排版 |
| [layout_composer.py](babeldoc/format/pdf/document_il/midend/layout_composer.py) | `_estimate_line_widths_multi` 使用多区间 |
| [flow_skeleton.py](babeldoc/format/pdf/document_il/midend/flow_skeleton.py) | 确保 `FlowRegion.intervals` 正确传递 |

---

## 缺陷 3：Paragraph Style 丢失（随机缩进）

### 现象

原文没有缩进的段落，翻译后出现随机首行缩进：

```
        ■■■■■■■■■■■■■■■■
■■■■■■■■■■■■■■■■■■■■
■■■■■■■■■■■■■■■■■■■■
```

或者段落整体偏移：

```
■■■■■■■■■■■■■■

            ■■■■■■■■■■■■
```

### 期望效果

```
■■■■■■■■■■■■■■■■■■■■
■■■■■■■■■■■■■■■■■■■■
■■■■■■■■■■■■■■■■■■■■
```

### 根本原因分析

1. **`first_line_indent` 是 boolean，不是数值**：[il_version_1.py:1229](babeldoc/format/pdf/document_il/il_version_1.py#L1229) 定义 `first_line_indent: bool`，只记录"是否有缩进"，不记录缩进量。

2. **检测逻辑过于简单**：[paragraph_finder.py:171-181](babeldoc/format/pdf/document_il/midend/paragraph_finder.py#L171-L181) 检测缩进的条件是"第一个字符的 x 坐标 - 段落 box.x > 1pt"。这意味着：
   - 原文首行稍微偏右 1pt 就会被标记为"有缩进"
   - 翻译后会强制添加 `space_width * 4` 的缩进 ([typesetting.py:1949](babeldoc/format/pdf/document_il/midend/typesetting.py#L1949))

3. **缩进量不继承原文**：即使原文确实有缩进，翻译后的缩进量是固定的 `space_width * 4`，而非原文的实际缩进量。

4. **StyleRegion 未被使用**：`flow_skeleton.py` 的 `StyleRegion` 已经提取了 `first_line_indent`、`left_indent`、`alignment` 等样式信息，但这些信息 **没有被传递给 Typesetting 阶段**。

5. **翻译后 Paragraph Box 被重算**：`ParagraphFinder.update_paragraph_data` 会根据字符位置重算 `paragraph.box`，这会丢失原文的几何信息。

### 修复方案

#### 3a. 将 `first_line_indent` 从 bool 改为 float

```python
# il_version_1.py
@dataclass(slots=True)
class PdfParagraph:
    # ...
    first_line_indent: float | None = field(  # 改为 float
        default=None,
        metadata={"name": "FirstLineIndent", "type": "Attribute"},
    )
```

#### 3b. 保存原文的实际缩进量

在 `ParagraphFinder.update_paragraph_data` 中：

```python
# 计算实际缩进量（而非 bool）
if paragraph.pdf_paragraph_composition and ...:
    first_char_x = paragraph.pdf_paragraph_composition[0].pdf_line.pdf_character[0].visual_bbox.box.x
    indent = first_char_x - paragraph.box.x
    paragraph.first_line_indent = indent if indent > 1 else 0.0
```

#### 3c. 在 Typesetting 中使用实际缩进量

```python
# typesetting.py:1947-1950
if paragraph.first_line_indent and paragraph.first_line_indent > 0:
    current_x = available_x + paragraph.first_line_indent * scale
```

#### 3d. 继承 StyleRegion 的样式

在排版前，从 `PublisherSkeleton` 获取该段落位置的 `StyleRegion`，继承其 `alignment`、`left_indent` 等属性。

### 涉及文件

| 文件 | 修改内容 |
|------|---------|
| [il_version_1.py](babeldoc/format/pdf/document_il/il_version_1.py) | `first_line_indent: bool` → `float` |
| [paragraph_finder.py](babeldoc/format/pdf/document_il/midend/paragraph_finder.py) | 保存实际缩进量 |
| [typesetting.py](babeldoc/format/pdf/document/il/midend/typesetting.py) | 使用实际缩进量排版 |
| [flow_skeleton.py](babeldoc/format/pdf/document_il/midend/flow_skeleton.py) | 确保 StyleRegion 正确传递 |

---

## 实施顺序

```
① Paragraph Reconstruction (段落重建 + CJK 断行)
            ↓
② Text Wrap / Exclusion Zone (多区间环绕)
            ↓
③ Paragraph Style Preserve (缩进/对齐/间距继承)
```

### Phase 1: CJK 断行优化（1-2 周）

- [ ] 增加 CJK 词组保护（基于 jieba 或简单词典）
- [ ] 增加行首/行尾禁则
- [ ] DP 优化器增加 CJK 模式的 cost 函数
- [ ] 添加 CJK 排版的单元测试

### Phase 2: 多区间环绕（1-2 周）

- [ ] `ExclusionZoneIndex.get_intervals_at` 返回多区间
- [ ] `_layout_typesetting_units` 支持多区间排版
- [ ] 处理"图片在左"和"图片在右"两种场景
- [ ] 处理 Quote 作为排除区域的场景

### Phase 3: Paragraph Style 继承（1 周）

- [ ] `first_line_indent` 从 bool 改为 float
- [ ] 保存并继承原文的实际缩进量
- [ ] 继承 `alignment`、`left_indent`、`right_indent`
- [ ] 添加回归测试

---

## 排版质量评估指标

建议增加自动化的排版质量评分，用于回归测试：

| 指标 | 计算方法 | 目标 |
|------|---------|------|
| 行宽均匀度 | `std(line_widths) / mean(line_widths)` | < 0.15 |
| 文字覆盖率 | `text_area / available_area` | > 0.85 |
| 图片环绕利用率 | `text_area_near_image / available_area_near_image` | > 0.7 |
| 缩进一致性 | `abs(actual_indent - original_indent)` | < 2pt |
| 对象重叠率 | `overlapping_area / total_area` | = 0 |

---

## 与现有代码的关系

### 已有能力（可复用）

- **ExclusionZone 系统**：已实现 R-tree 索引、per-line 查询、polygon 支持
- **FlowSkeleton**：已提取 StyleRegion（含 first_line_indent、alignment 等）
- **Knuth-Plass DP 优化器**：已实现，只需增加 CJK 模式
- **PostLayoutProcessor**：已实现重叠检测和修复框架

### 需要新增

- CJK 词组保护逻辑
- 多区间排版支持
- Paragraph Style 的保存和继承机制

### 不需要新增

- 新的 Pattern/Skeleton 类型
- 新的布局检测算法
- 新的 PDF 解析能力

---

## 结论

这三个问题解决后，BabelDOC 的排版质量会有质的飞跃：

1. **中文断行**：从"随机断开"到"词组保护 + 禁则处理"
2. **图片环绕**：从"文字躲着图片"到"文字环绕图片"
3. **样式继承**：从"随机缩进"到"完全还原原版样式"

建议 **下一阶段不要继续增加新功能**（例如更多 Pattern、更多 Layout 类型），而是优先把 **Typesetting Engine** 做稳定。
