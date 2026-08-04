# BabelDOC 排版优先（Layout-First）整体方案 v2.1

| 字段 | 值 |
|------|-----|
| 状态 | Draft v2.1（内部 3 人评审 + 外部评审两轮修订） |
| 日期 | 2026-08-03 |
| 基线 | 5cf4962（0.6.4.50） |
| 内部评审 | 架构/语义/实施 3 人组：v2 已吸收 9 高/13 中/6 低 |
| 外部评审 | [`layout-first-plan-review.md`](layout-first-plan-review.md)：综合 7.8/10，**Approve with changes**；阻断项已全部合入本节 |
| 评审结论 | P0 批准开工；P1–P2 有条件批准（须先补挂点/双盒/消费矩阵/相对 gap） |

---

## 1. 问题证据（为什么要改）

第 19 页（Orgasmic Addiction）这轮暴露的级联，全部来自"先排好、再拿启发式 pass 修补"：

```
基础排版
 ├─ enforce_title_body_gaps(0.6.4.46)
 │    · 把叠在 32pt 标题带内的 15pt 副标题当"正文" → dy=-45.3
 │    · 连带 56pt 主标题被拖走 → 又触发它的 gap pass → dy=-52.6
 │    · 页脚（已 skip 的 chrome）作为 follower 被拖出页面 dy=-97.9（PDF y=-56）
 ├─ box_expand.try_pre_expand_for_content
 │    · 绕图正文列被 is_quote_block 误判 pull-quote → 自锁排除区
 │    · 右挡误判(0.9×cropbox) → 左扩 100pt 压到照片 → 7.2pt 针尖竖条
 ├─ fix_overlapping_paragraphs_post_typesetting（与 gap pass 叠加，位置不可预期）
 └─ 隐式契约：ReferenceMetrics / layout_label / xobj_id 语义漂移
```

**根因不是某个 pass 的 bug，而是架构：排版不理解原版设计意图，靠事后猜测修补。**

评审补充的事实基线（v2 据此修正）：
- 原版 56pt 标题→正文设计间距 = **25.7pt**（墨迹），现状被 enforce 成 14.0——现状从未还原原版间距；
- 原版绕图是"右缘钉页边、左缘逐行右移"，而 `_cap_available_with_reference` 按起点截宽（右缘收窄）——**现有实现输出的是镜像锥形**；
- 翻译后 `pdf_paragraph_composition` 被整体替换，原 EN 字形/字体丢失——"排版后保留英文"机制不存在。

---

## 2. 目标与非目标

### 目标
1. **每个段落一次排好**：首遍排版即满足设计位置与间距，不再"排完再移"。
2. **设计意图是一等公民**：新增 `LayoutIntent`（版面意图），解析后、翻译前提取，排版器消费。
3. **阶段契约化**：每个阶段明确 pre/post 条件；意图/排版产物总是可导出。
4. **保持 dual 质量优先 + DeepLX 非 LLM 路径**。
5. **增量落地**：solo 容量，每阶段独立验收。

### 非目标
- 重写 IL schema / parser / PDF 后端；改 dual 拼接产品形态。
- 用 LLM 修排版。
- **文本恢复/编码（产品轨，并行，不阻塞本方案）**：
  - Latin 连字残片 `ff/erent/anSWer`（oa-dual PR-A：soft-hyphen/连字跨 run 恢复）；
  - CJK 兼容字 U+F9xx（翻译后 NFKC 规范化）；
  - 标题胡译/解剖误译（MT 术语/人工，role 只影响排版策略）。
  - 说明：**Layout-First 是版面轨主线，不能单独作为 dual 发布闸的充分条件**。

---

## 3. 核心概念：LayoutIntent（版面意图）

翻译前为每个段落生成**不可变**意图对象（运行时字段；固定时点 = ParagraphFinder + compute_reference_metrics 之后）。它是既有信号的**派生投影**，不是新数据源：

- `role` 派生自 `layout_label` + 几何 + 既有判定（`is_figure_wrap_paragraph` 为 taper 唯一派生源，禁止第二处复算）；
- `ReferenceMetrics` 保持原始捕获不变（它是翻译前英文参考，不是意图）；
- `is_layout_debug_stub` / `is_chrome_paragraph` 直接复用（0.6.4.50）。

```python
@dataclass(slots=True)
class LayoutIntent:
    role: str                     # body | title | subtitle_overlay | pull_quote
                                  # | callout | figure_caption | chrome | wrap_column
    design_box: Box               # 排版前快照（StylesAndFormulas 之后），排版中只读
    top_inset: float              # EN 首行墨迹相对盒顶偏移（ink_top 对齐用）
    bottom_inset: float           # EN 末行墨迹相对盒底偏移
    wrap_shape: list[tuple[float, float]] | None  # 每行 (left_offset, width)：
                                  #   右缘=design 右缘，左缘=右缘−width（表达左缘步进，非镜像）
    overlays_band: str | None     # 叠在哪条带上（subtitle → title）
    stack: int = 0                # 设计重叠组（≥1 行高容差的连通分量归组；组内不互推）
    expansion_policy: tuple[str, ...]  # 可扩轴向按序：(right, down)；wrap_column 禁 left；chrome 全禁
    expansion_limits: tuple[str, ...]  # 约束来源（page_margin/photo/next_block）——数值排版时查 ConstraintIndex
    overflow_policy: str          # scale_down | expand；keep_en 不是排版时选项（见 §3.1）
    min_scale: float              # 段级缩放下限（默认全局 0.55）
    gap_contract: float | None    # 与下一块的 ink-to-ink 设计间距（组底墨迹起算，翻译前提取，排除 debug stub）
    is_chrome: bool               # 永不翻译、永不移动
    text_on_photo: bool           # 艺术叠图（压照片的正文）；溢出优先 scale_down/艺术重叠
```

### 3.0 双盒模型与字段挂载（外部评审阻断项）
- **design_box（只读意图）** vs **paragraph.box（排版结果）**：排版器只读 `design_box`，扩轴/缩放结果写回 `paragraph.box`（现状多处 `paragraph.box = expanded` 改为写布局结果，不再改意图）；PDFCreater 与审计 Δ 断言以 `paragraph.box` 为基准、以 `design_box` 为参照。
- 挂载：`PdfParagraph.layout_intent: LayoutIntent | None`（runtime-only，与 `reference_metrics`/`alignment` 同模式，**无 XML metadata、不进 `il_layout_fingerprint`**）。
- 新代码落点：`utils/layout_intent*.py`（模型 + 提取器），**P0 禁止向 typesetting.py（4157 行）堆主体逻辑**。

### 3.1 三个语义裁定（评审高项，v2 定死）
1. **wrap_shape 表达左缘步进**：存每行 `(left_offset, width)`；消费端"右缘 = design 右缘、左缘 = 右缘 − width"。禁止用宽度列表（那会产出镜像锥形）。
2. **gap_contract 是 ink-to-ink**：翻译前从 EN 字形 ink 提取目标间距；排版时按首行字形 ascent 落位（`top_inset`），不是盒间距。CJK 行高更高时盒间距会失真。
3. **keep_en 不是排版时选项**：翻译后 EN 字形已不可恢复。默认策略（外部评审修正）：
   - **默认不启用全局 CJK 宽度预估 skip**（预估过脆，误 skip 风险 > 收益）；
   - keep_en 仅沿用既有 `narrow_callout_mode`（窄栏模式）通道；
   - 可选（后续）：段级 source snapshot（unicode+composition+字体）支持排版后 restore，作为独立特性评估。
   `text_on_photo` 段落不落入 keep_en（优先 scale_down/艺术重叠）。

### 3.2 排除区与 ConstraintIndex 的分工（评审高项）
- `ExclusionZoneIndex` 仍是**每页唯一几何排除区提供者**（`get_intervals_at` 多区间继续量产）；
- **quote 区只来自 `role=pull_quote`**（不再几何误判）；figure 区继续来自 `PdfFigure` / `PdfForm(image)`（可加 zone 级 role 标注）；
- **有 wrap_shape 的段落走意图重放；无意图 / OCR 段落回退多区间**，优先级按此执行；
- 无 wrap_shape 的段落仍消费 `_uniform_cjk_reference_widths` / `_query_line_intervals` / `_cap_available_with_reference`（P2 一并改造，不另起第二套）。

---

## 4. 目标流水线（排版优先）

```
Parse → ParagraphFinder → compute_reference_metrics → StylesAndFormulas
        ↓ 新增（固定时点：Styles 之后、翻译之前；design_box 以 Styles 后为准）
   LayoutIntentExtractor（utils/layout_intent*.py，新文件）
        ├─ role / design_box / wrap_shape / stack / gap_contract / top_inset
        ├─ chrome / text_on_photo / expansion_policy / overflow_policy
        └─ 规则：只读；异常吞掉并告警；dump 仅 --debug；提取失败记入审计
        ↓
   ILTranslator（skip 决策 = role + 翻译前预判；keep_en 不是排版时选项）
        ↓
   Typesetting（契约驱动，一次排好）
        ├─ 首遍：scale=1 放入 design_box，按 wrap_shape 逐行（右缘钉设计右缘）
        ├─ 溢出：按 expansion_policy 有序扩轴（limits 查 ConstraintIndex）→ 再按 min_scale 缩放
        ├─ 间距：gap_contract 按 ink/top_inset 预留，块间互不移动
        └─ 禁止：移动其它段落、移动 chrome、跨组级联、改 design_box
        ↓
   PostLayout（统一降级为 LayoutAuditReport + 受限修复）
        ├─ enforce_title_body_gaps → ink 审计兜底：仅当墨迹真实重叠且候选非
        │    chrome/display-title/subtitle_overlay 时，单跳、dy≤24pt、级联长度≤1
        ├─ fix_overlapping_paragraphs_post_typesetting → 局部化（不级联、不碰 chrome/标题）
        └─ PostLayoutProcessor（默认关）与 retypeset_paragraph 必须消费 LayoutIntent，否则视为违反契约
   ※ post 顺序金测：现网为 fix_overlapping → enforce_title_body_gaps；迁移阶段用同一顺序对拍，避免「先 gap 再 overlap」与现状不符。
```

### 关键转变
| 现状 | 排版优先 |
|------|----------|
| 全局 `min_gap=14` 后置推挤 | `gap_contract`（ink-to-ink）排版时预留 |
| `box_expand` 事后左扩 | `expansion_policy` 限额扩张（limits 存来源，数值查 ConstraintIndex） |
| quote 几何误判产生自锁区 | quote 区只来自 role |
| 移动 pass 级联 11–23 段 | 块间零互移；仅真实墨迹重叠时单跳修复（dy≤24pt） |
| 镜像锥形（右缘收窄） | wrap_shape 左缘步进、右缘钉设计右缘 |

---

## 5. 阶段契约与可调试

1. `LayoutIntent` 总是生成（不只 --debug）；debug 时 dump `layout_intent.json`。
2. **design_box 捕获点**：ParagraphFinder + compute_reference_metrics 之后（等价 `add_debug_information.json` 语义）；它不是"原版"位置，已含 ParagraphFinder 自身移动，且排版中只读。
3. `retypeset_paragraph` 与 PostLayoutProcessor 必须消费 LayoutIntent（契约测试）。
4. `LayoutAuditReport`（仿 `skip_report.json` 先例）：结构化输出 gap/overlap 违例，替代 `logger.debug`/返回 int。
5. **IL 指纹回归**：`il_layout_fingerprint(doc)` 按 P0b 规则**忽略 runtime-only 字段**；显式忽略列表含 `layout_intent` 及一切新增 runtime 字段（Intent dump 测试勿用指纹当 Intent 相等）。
6. repro driver（FixedMap）入库 `tests/repro/`：参数化 driver、映射表、digest 断言脚本、golden。

---

> 具体编码设计见 [`layout-first-coding-plan.md`](layout-first-coding-plan.md)（P0 可直接照写代码；§4 决策点待拍板）。

## 6. 分阶段落地（增量，每阶段独立验收）

### 落地前置条件（P0 前）
- repro driver + golden + 断言脚本入 `tests/repro/`；CI 增加可选 layout job（复用 assets cache）；
- `test_skip_audit` known-failure 基线：修复或 `--deselect` 登记，文档写明基线版本；
- 明确指纹忽略 runtime-only 字段。

| 阶段 | 内容 | 验收（OA 页） | 回归闸 |
|------|------|--------------|--------|
| **P0** | LayoutIntent 骨架（**新文件 `utils/layout_intent*.py`**；role/design_box/chrome/text_on_photo/gap_contract/top_inset 提取 + dump + 审计空壳；**挂点 = StylesAndFormulas 之后**）；行为不变 | 全页位置 Δ=0（对照入库 golden） | 全量 pytest + repro digest Δ=0 + 指纹不变 |
| **P1** | gap_contract(ink/top_inset) 进排版；`enforce_title_body_gaps` 改为 **审计+受限修复**（非纯审计）：单跳、dy≤24pt、级联长度≤1、不碰 chrome/display-title/subtitle_overlay；`test_vertical_gap` 迁移（旧行为保留 `_legacy` 供 P3 前 Δ 对比）；**过渡态标注**：终态零互移，P1 允许单跳 dy≤24（分页写明） | **\|zh_ink_gap − en_ink_gap\| ≤ ε（相对 EN ink 间距）**，不写死绝对值 | test_vertical_gap 新语义 + LayoutAuditReport 违例计数 |
| **P2** | wrap_shape `(left_offset, width)` 消费端改造；`_uniform_cjk_reference_widths` / `_query_line_intervals` / `_cap_available_with_reference` 一并入范围；`paragraph.box` 冻结（design_box 只读，扩轴仅经 expansion_policy 写布局结果） | p19 绕图段左缘步进序列与 EN 一致（±2pt），右缘钉设计右缘 | test_figure_wrap_policy + 行缘坐标断言 |
| **P2**（前置：消费端替换矩阵） | wrap_shape `(left_offset, width)` 消费端改造；先写死替换矩阵再改码 | 见矩阵 | — |
| **P3** | 首遍无碰撞；`fix_overlapping` 局部化；retypeset/PostLayoutProcessor 消费 intent；**多页（≥2 页）与 dual smoke 纳入验收** | p19 页脚/页码永不动 + 第 7/8 页抽样 | test_vertical_gap + dual smoke |
| **P4** | 样式继承：`first_line_indent` 数值化（现状 `str|None`，含 XML 序列化兼容与旧值迁移）、alignment 契约 | p7/15 缩进 | test_first_line_indent |
| **P5** | CJK 断行：词组保护/禁则/DP cost（缺陷 #1）；**明确 P5 后重跑 P2 闸**（断行器改写可能推翻 wrap_shape 验收） | 全页行宽均匀度 | test_cjk_line_break + P2 回归 |

#### 消费端替换矩阵（P2 前写死，外部评审阻断项 8）

| 函数 | 有 wrap_shape（wrap_column） | 无 wrap_shape |
|------|------------------------------|---------------|
| `_uniform_cjk_reference_widths` | 忽略，或仅作 min 钳 | 现状（taper 保留 / 统一拉平） |
| `_query_line_intervals` | 意图优先于 zone？交集？（P2 设计笔记定） | 现状多区间 |
| `_cap_available_with_reference` | **不走**；改用 wrap 行缘（右缘钉设计右缘） | 现状 |
| `try_pre_expand_for_content` | wrap_column **禁用** | policy 驱动 |

P2 完成前允许回退旧路径（不双轨并存于同一段落）；完成后 quote 几何路径 feature-flag 默认关。

god file 策略：`typesetting.py` 已 4157 行，P1–P5 继续落此文件属已知代价（K13）；**P0 禁止向 typesetting.py 堆主体逻辑（新代码在 `utils/layout_intent*.py`）**；P3 前插一步机械抽取（IL 指纹闸，主计划 PR-08 模式），不要等 P5。

---

## 7. 验收与回归（页面断言，替代"目视截图驱动"）

**数据源规则（评审高项，v2 定死）**：
- design_box 取排版前快照（`add_debug_information.json` 语义）；
- 断言仅针对 **debug_id 键控段落**，先断言 id 集合不变；豁免必须引用 `layout_intent.json` 的 policy/limits（段、轴、pt 数），禁止"全声明为扩张"击穿；
- 行宽一律从 `pdf_character` 按 y 聚类重算，**禁止使用 `reference_metrics.per_line_widths`**（翻译前英文参考值）。

对每个验收页断言：
1. 每块 box 与 design_box 偏差 ≤4pt（除契约允许的扩张/缩放）；
2. chrome（页脚/页码/URL/abandon）位置 Δ=0（身份取 role ∩ skip_report reason 交集；基线用排版前快照 box；含 scale==1）；
3. 针尖缝：任一段实际行宽 < design_box 宽 × 段 scale × min_scale 即判；wrap_column 段豁免宽度断言，改查右缘 x2 与 design 偏差 ≤0.5pt；
4. 绕图：**逐行左右缘坐标与 EN 原版一致（±2pt）**（删除纯宽度 ±10%，防镜像骗过）；
5. dual smoke：mono 断言不覆盖 dual 合成，另加一条 dual 页级断言（左右页数量/尺寸一致）。

---

## 8. 风险

| 风险 | 缓解 |
|------|------|
| role 分类误判 → 比现状更糟 | 保守默认（未知→body）+ layout_intent.json 审计 + 误判即修提取规则 |
| 双布局机制（wrap_shape vs 多区间） | §3.2 优先级写死；P2 一并改造三个消费函数，不另起第二套 |
| CJK 断行改写推翻 P2 验收 | P5 明确重跑 P2 闸 |
| 多页/多文档回归不足（仅 p19） | P3 起 ≥2 页 + 抽样页验收 |
| 性能（layout_intent.json 序列化；paragraph_finder.json 已 2.5MB/页） | 序列化仅 --debug；提取逻辑只读轻量 |
| DeepLX 缓存交互（role 改变段落切分 → 缓存 key 变化） | role 派生自既有字段，切分不变则 key 不变；变更时记录迁移说明 |
| Intent 与 StylesAndFormulas 竞态 | 固定提取时点（Styles 之后）；若 Styles 改 box/行几何，design_box 以 Styles 后为准或禁止 Styles 改几何 |
| CJK 预估宽度误 skip | 默认不启用全局 keep_en 预判；callout 沿用 `narrow_callout_mode` |
| ExclusionZone 与 Intent 双轨 | P2 完成前允许回退；完成后 quote 几何路径 feature-flag 默认关 |
| 指纹与 P0 新增字段冲突 | 指纹按 P0b 规则忽略 runtime-only 字段 |
| 现有 565 测试语义过时（min_gap 全局假设） | P1 显式迁移（_legacy 保留 + 新语义测试） |

---

## 9. 与既有文档的关系

- `architecture-optimization-plan.md`：本方案是其 Phase 2 的具体化；**`LayoutContext` 明确 "Not on IL"（827 行），本方案 `LayoutIntent` 是 IL 运行时字段（派生投影）——差异已显式声明（LayoutIntent ≠ LayoutContext：段级意图 vs 页级上下文）**；吸收 MVP M3–M6，M7/PR-08（机械抽取）纳入 god file 策略；已在 arch 文档加反向链接（§9.1）。
- `layout-engine-defects.md`：缺陷 #2（环绕）→ P2（含镜像锥形修正），缺陷 #1（CJK 重排）→ P5，缺陷 #3（样式）→ P4；
- `oa-dual-layout-pr-plan.md`：PR-B/C/D 的 skip/标题/窄栏策略并入 P0 role 提取。
