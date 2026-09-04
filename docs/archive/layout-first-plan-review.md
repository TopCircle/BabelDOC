# Layout-First 方案评审（相对当前架构与源码）

> **2026-08-13 — Snapshot** of the 2026-08-03 review (baseline 0.6.4.50). Not a work queue.  
> Active: [`oa-dual-quality-wave-0.6.4.69.md`](oa-dual-quality-wave-0.6.4.69.md)

| 字段 | 值 |
|------|-----|
| 被评文档 | [`docs/layout-first-plan.md`](layout-first-plan.md) v2 |
| 评审日期 | 2026-08-03 |
| 代码基线 | `5cf4962`（0.6.4.50；与 plan 基线一致） |
| 评审范围 | 方向 / 与生产管线契合度 / 语义契约 / 落地风险 / 与既有文档关系 / 建议修订 |
| 结论 | **方向成立，建议有条件采纳（Approve with changes）** |

---

## 0. 一句话结论

方案准确抓住了当前质量债的**架构根因**（「先排再推挤」），与仓库里 `vertical_gap` / `box_expand` / `figure_wrap` / post-typesetting 叠 pass 的事实一致；P0–P5 增量与验收契约也比「再加一个启发式」更可持续。

但相对 **生产管线挂点、盒模型、keep_en 预判可行性、god-file 容量、以及 OA dual 已暴露的非排版缺陷（连字残片 / 编码）**，v2 仍有若干**必须写死**的缺口——否则 P1–P2 会再次变成「意图层 + 旧 pass 双轨」。

**建议：P0 可开工；P1 前先补齐下文「阻断项」；P2 前完成盒模型与 wrap 消费端设计笔记。**

---

## 1. 与当前生产架构的对照

### 1.1 生产管线（`high_level._do_translate_single`，已核实）

```text
Parse → LayoutParser → ParagraphFinder
  → compute_reference_metrics          # layout_helper，翻译前
  → StylesAndFormulas                  # 会改 composition / style
  → [debug] FlowDebugSvg
  → ILTranslator | LLMOnly
  → [debug] AddDebugInformation
  → Typesetting.typesetting_document   # 含 pre-expand / layout / post-overlap / enforce_title_body_gaps
  → [opt] PostLayoutProcessor
  → PDFCreater (mono/dual)
```

Plan 目标流水线：

```text
… → ParagraphFinder → ReferenceMetrics
  → LayoutIntentExtractor   # 新增
  → ILTranslator
  → Typesetting（契约驱动）
  → PostLayout（审计+受限）
```

### 1.2 契合点（强）

| Plan 主张 | 源码事实 | 评价 |
|-----------|----------|------|
| 后置 gap pass 级联伤 chrome/标题 | `vertical_gap.enforce_title_body_gaps` 仍会 shift follower；0.6.4.50 已 exclude chrome/debug-stub，但全局 `min_gap=14` 与「还原 EN ink 间距」仍是两套目标 | 根因诊断正确 |
| quote 几何误判 → 自锁排除区 | `exclusion_zone` / `is_quote_block` 与 `is_figure_wrap_paragraph` 并行；figure_wrap 注释明确 taper 不得当 quote | role 唯一源正确 |
| 镜像锥形 / 右缘收窄 | `_cap_available_with_reference` 从 **line_start + ref_w** 截右缘；真正 wrap 是「右缘钉、左缘步进」（`figure_wrap.py` 已文档化） | wrap_shape 语义裁定正确 |
| 翻译后 EN composition 不可恢复 | `PdfParagraph.pdf_paragraph_composition` 被译后替换；`ReferenceMetrics` 仅存行宽统计 | keep_en 不是排版时选项 — 裁定正确 |
| 意图派生、非新数据源 | `layout_label` / `reference_metrics` / `is_chrome_paragraph` / `is_figure_wrap_*` 已存在 | 与 additive-only IL 原则一致 |
| 指纹忽略 runtime-only | `il_layout_fingerprint` 只哈希几何 box | P0b 兼容可做 |

### 1.3 偏离 / 缺口（必须处理）

| 问题 | 说明 | 严重度 |
|------|------|--------|
| **StylesAndFormulas 在意图提取中的位置未写死** | 生产上 RefMetrics 之后立刻 StylesAndFormulas，会改 composition/formula/style。若 Intent 在 Styles 之前提取，`wrap_shape` 几何信号与最终进 MT 的段可能不一致；若之后提取，文档未写 | **阻断** |
| **`design_box` vs 运行时 `paragraph.box`** | 现状 typesetting 多处 `paragraph.box = expanded`（`_pre_expand_narrow_box`）。Plan 要求 design_box 只读，但未定义 **layout_box / result_box** 写回字段与 PDFCreater 消费哪个 | **阻断** |
| **`ConstraintIndex` 尚未存在** | 生产只有 `ExclusionZoneIndex`（`exclusion_zone.py`）。Plan 写「limits 查 ConstraintIndex」——是演进目标还是 P1 假依赖？需标明 = ExclusionZoneIndex 演进或适配层 | 高 |
| **`LayoutContext` vs `LayoutIntent`** | `architecture-optimization-plan` 的 LayoutContext 是 **Not on IL / 每页上下文**；本方案是 **段级 runtime 字段**。差异已声明，但消费 API（页级 index vs 段级 intent）交互未画清 | 中 |
| **role 枚举偏窄** | 仅 body/title/subtitle_overlay/pull_quote/callout/figure_caption/chrome/wrap_column；生产还有 formula、list、table 残迹、drop-cap 邻接、section_header、OCR 等 | 中 |
| **与 OA dual 非排版 P0 的边界** | 连字残片 `ff`/`erent`、CJK 兼容字、标题误译等见 `oa-dual-layout-pr-plan` PR-A 与实书 review；本方案 scope 正确但应 **显式 Non-goal + 交叉依赖**，避免「Layout-First 做完 dual 仍不可读」 | 高（产品预期） |

---

## 2. 分节评审

### 2.1 问题证据（§1）— **通过**

- p19 级联描述与 `enforce_title_body_gaps` + follower shift 机制吻合。
- 25.7pt EN 设计间距 vs 14.0 全局 min_gap：代码常量 `DEFAULT_MIN_GAP_PT = 14.0` 可证伪/可验收。
- 「镜像锥形」相对 `_cap_available_with_reference` 的实现叙述正确（宽度 cap 从起点向右，不是左缘步进）。

建议：把 p19 的 **debug_id / 段 unicode 摘要 / 排版前 box** 写进 `tests/repro/` 设计，避免只写页码。

### 2.2 目标与非目标（§2）— **通过，小补**

- 与 AGENTS.md「dual 优先 + DeepLX」一致。
- 非目标（不重写 IL schema / 不用 LLM 修排版）正确。
- **建议增补 Non-goal**：不在本方案内解决 MT 质量、连字恢复、字体 cmap/兼容区；交叉引用 `oa-dual-layout-pr-plan` PR-A 与 dual 文本层质检。

### 2.3 LayoutIntent 模型（§3）— **有条件通过**

**优点**

- 字段覆盖了当前最痛的轴：role / wrap / gap / chrome / expansion / overflow。
- 三个语义裁定（wrap 左缘步进、gap ink-to-ink、keep_en 时机）都对准真实 bug。
- quote 区只来自 `role=pull_quote` 可消掉 figure-wrap 自锁。

**必须补齐**

1. **不可变的边界**  
   - 不可变的是「翻译前快照」；排版结果写哪里？建议：
     - `layout_intent: LayoutIntent`（只读）
     - 排版写 `paragraph.box`（结果盒）或显式 `layout_result_box`
   - 禁止「扩轴时改 design_box」。

2. **`wrap_shape` 提取失败策略**  
   - 今日 `is_figure_wrap_paragraph` 有 taper + 左右缘 spread 双信号；Intent 提取应 **复用同一函数**（plan 已要求），并规定：提取失败 → `wrap_shape=None` → 走多区间回退，**不得**静默写成均匀宽。

3. **`overflow_policy` / keep_en 预判（§3.1a）**  
   - 「CJK 宽度预估不满足 → skip」在 ILTranslator 很脆：无真译文宽度，只能用 ratio/字符数启发式，易误 skip 正文。  
   - 建议 P0 只落地 **(b) snapshot 可选** 或 **narrow_callout 既有 keep_en 路径**；全文预判 skip 放到 P3+ 且默认关。

4. **`text_on_photo` / `stack` 分类规则过薄**  
   - 无几何阈值易误判；建议 P0 只填 chrome + wrap_column + title/subtitle_overlay（overlay 用现有 vertical_gap 的「整段落在标题 ink 内」判定），callout/text_on_photo 延后。

5. **`expansion_limits: tuple[str, ...]` 存来源不存数值**  
   - 合理，但需约定 **ConstraintIndex 查询时点**（每行 vs 段级）与缓存失效（邻居段扩轴后）。

### 2.4 目标流水线与 PostLayout（§4）— **有条件通过**

| 转变 | 评价 |
|------|------|
| gap 进排版时预留 | 正确方向；P1 落地时需改 `_layout_typesetting_units` 的初始 y / line_skip，不是只改 enforce |
| expansion_policy 限额 | 应对齐并最终 **删除/旁路** `try_pre_expand_for_content` 的左扩 callout 路径（0.6.4.49 已止血，Intent 应接管） |
| 块间零互移 | 真·P3；P1 仍保留受限 enforce 时，文档应写「过渡态允许单跳，非终态契约」 |
| PostLayoutProcessor 必须消费 Intent | 正确；现状 `enable_post_layout_optimization` 默认关，契约测试要覆盖 retypeset 入口 |

**顺序风险**：现网 post 顺序是  
`fix_overlapping_paragraphs_post_typesetting` → `enforce_title_body_gaps`。  
Plan 把 gap 审计写在前。迁移时应用 **同一顺序的金测**，避免「先 gap 再 overlap」与现状对拍失败。

### 2.5 阶段契约与调试（§5）— **通过**

- Intent 总是生成、dump 仅 `--debug`：与 `paragraph_finder.json` 体积问题匹配。
- `design_box` = ParagraphFinder + RefMetrics 后快照（含 Finder 自身移动）：语义诚实，优于假装「原版 PDF 坐标」。
- `LayoutAuditReport` 仿 `skip_report.json`：与 PR-C1 一致，可复用模式。
- repro + FixedMap：仓库已有 `fixed_map_translator` / dual_quality 工具，可复用而非重造。

### 2.6 分阶段落地（§6）— **通过，调整优先级建议**

| 阶段 | 评价 | 建议调整 |
|------|------|----------|
| **前置 repro** | 必须，且应先于任何 Intent 字段 | 同意；固定 OA p7/p19 + 1 合成页 |
| **P0 骨架 Δ=0** | 正确的「只加字段不改行为」 | 挂点写清：`StylesAndFormulas` 之后、`ILTranslator` 之前（推荐）或说明为何在 Styles 前 |
| **P1 gap** | 价值高，对准 p19 标题压正文 | 验收勿写死 25.7 单点：用 **\|zh_ink_gap − en_ink_gap\| ≤ ε** |
| **P2 wrap_shape** | 对准缺陷 #2 + 镜像锥形；触及三个消费函数 | **P2 设计笔记** 先写清 `_cap_available` 替换矩阵再改代码；否则易双轨 |
| **P3 零互移 + dual smoke** | dual smoke 偏晚 | **P1 起** 加 mono 几何闸 + **可选 dual 页尺寸/左右半断言**；P3 再加视觉/行缘 |
| **P4 样式** | 对齐缺陷 #3；`first_line_indent: str\|None` 属实 | XML 兼容需 migration 表 |
| **P5 CJK 断行** | 对齐缺陷 #1；重跑 P2 闸正确 | 与 architecture M4 重叠，勿两套 cost |

**God file（4157 行 typesetting.py）**  
K13 允许继续堆，但 P1+P2 同时改 gap + wrap 会显著增大冲突面。建议：

- P0：新文件 `layout_intent.py` + `layout_intent_extractor.py`（**不要**塞进 typesetting）
- P1–P2：typesetting 仅加消费钩子
- P3 前：机械抽取 wrap/gap 消费到 `typesetting/wrap_shape.py` 等，指纹闸保护

### 2.7 验收（§7）— **强，微调**

- 禁止用 `reference_metrics.per_line_widths` 做译后行宽断言：正确。
- chrome Δ=0 用 role ∩ skip_report：正确方向；实现时注意 **skip 了但仍排版的段** vs **完全不进 typesetting** 的身份差（今日 chrome 多是「不译但可能仍被 shift」）。
- 针尖缝定义清楚；wrap_column 改查右缘 x2：正确。
- dual smoke 与 mono 分离：正确。

### 2.8 风险表（§8）— **通过，补三条**

| 补遗风险 | 缓解 |
|----------|------|
| Intent 与 StylesAndFormulas 竞态 | 固定提取时点；Styles 后若改 box 需 re-snapshot design_box 或禁止 Styles 改几何 |
| CJK 预估宽度误 skip | 默认不启用全局 keep_en 预判；callout 沿用 `narrow_callout_mode` |
| 方案成功但 dual 文本仍垃圾 | 并行 PR-A 连字/soft-hyphen；发布闸同时看 layout 指标 + 文本层 metrics |
| ExclusionZone 与 Intent 双轨 | P2 完成前允许回退；完成后 quote 几何路径 feature-flag 默认关 |

### 2.9 与既有文档（§9）— **通过**

| 文档 | 关系 | 评审意见 |
|------|------|----------|
| `architecture-optimization-plan.md` | Phase2 / MVP M3–M6 具体化 | 同意；建议在 arch 文档加反向链接与「LayoutIntent ≠ LayoutContext」一行 |
| `layout-engine-defects.md` | #1→P5 #2→P2 #3→P4 | 同意；P2 应更新缺陷文「镜像锥形」条目 |
| `oa-dual-layout-pr-plan.md` | skip/标题/窄栏并入 role | 同意；**PR-A 恢复不得被本方案挤出队列** |

---

## 3. 与「当前头痛」的映射（Orgasmic Addiction dual）

| dual review 问题类 | Layout-First 能否覆盖 | 说明 |
|--------------------|----------------------|------|
| 标题/正文重叠、页脚被拖 | **P1/P3 主战场** | 直接对应 §1 级联 |
| 绕图针尖竖条、压照片 | **P2 主战场** | wrap_shape + 禁 left 扩 |
| callout 碎栏/左扩毁版 | **P0 role + P2/P3 expansion** | 已有 0.6.4.49 止血，Intent 固化 |
| chrome 误动 | **P0 is_chrome + P3 零互移** | 0.6.4.50 已部分落地，Intent 契约化 |
| `ff`/`erent`/连字残片 | **否（上游 recovery）** | 保持 PR-A |
| CJK 兼容字 不/更 | **否（字体/后处理）** | 独立轨 |
| 标题胡译「不正确和不正确」 | **否（MT/术语）** | glossary / 人工；role=title 仅影响排版策略 |
| 页眉 160pt 跳过与正文顶区冲突 | **部分** | role/chrome 与 skip 边界；L4 语义 |

→ 方案是 **版面轨主线**，不能单独作为 dual 发布闸的充分条件。

---

## 4. 阻断项清单（P0 开工前 / P1 前）

### 阻断 · P0 前

1. **写死提取挂点**  
   推荐：
   ```text
   ParagraphFinder → compute_reference_metrics → StylesAndFormulas
     → LayoutIntentExtractor → ILTranslator → …
   ```
   并说明：若 Styles 修改 box/行几何，design_box 以 Styles 后为准。

2. **IL 字段挂载方式**  
   `PdfParagraph.layout_intent: LayoutIntent | None`（runtime-only，无 XML metadata），与 `reference_metrics` / `alignment` 同模式；**禁止**塞进 XML 序列化。

3. **指纹忽略列表**  
   显式：`layout_intent` 及一切新增 runtime 字段不进 `il_layout_fingerprint`（指纹只几何，本就安全，但 Intent dump 测试勿误用指纹当 Intent 相等）。

4. **repro 最小集入库**  
   FixedMap + OA p19（或合成等价）+ digest 脚本路径写进 plan 表。

### 阻断 · P1 前

5. **双盒模型**  
   `design_box`（只读） vs 排版写回的 `paragraph.box`；审计与 Δ 断言以谁为基准写死。

6. **P1 过渡契约**  
   「终态零互移」vs「P1 仍允许 dy≤24 单跳」分页标注，避免测试与文档互殴。

7. **gap 验收公式**  
   相对 EN ink gap，而非绝对 25.7pt。

### 阻断 · P2 前

8. **消费端替换矩阵**（一页纸即可）  

   | 函数 | 有 wrap_shape | 无 wrap_shape |
   |------|---------------|---------------|
   | `_uniform_cjk_reference_widths` | 忽略或仅作 min 钳 | 现状 |
   | `_query_line_intervals` | 意图优先于 zone？交集？ | 现状多区间 |
   | `_cap_available_with_reference` | **不走**；改用 wrap 行缘 | 现状 |
   | `try_pre_expand_for_content` | wrap_column **禁用** | policy 驱动 |

9. **删除或 flag 掉** 与 Intent 冲突的左扩 callout 启发式默认路径。

---

## 5. 建议的落地顺序（在 plan 上微调）

```text
0. repro + golden + digest（plan 前置）
1. P0 LayoutIntent 骨架（新模块，挂 Styles 后）+ dump + 审计空壳
   并行不阻塞：PR-A 连字恢复、CJK 兼容字后处理（产品轨）
2. P1 gap_contract 进排版 + enforce → 审计/单跳
3. P2 wrap_shape 消费（含 _cap 替换）+ design_box 冻结
4. 薄抽取 typesetting 子模块（指纹闸）—— 不要等 P5
5. P3 零互移 + dual smoke
6. P4 样式 / P5 CJK 断行（P5 后重跑 P2）
```

与 solo 容量：一次只开一个「改 typesetting 行为」的阶段；P0 可与 PR-A 并行。

---

## 6. 评审决议

| 项 | 决议 |
|----|------|
| 总体方向 | **采纳** |
| 是否可直接按 v2 开写 P1 | **否** — 先完成 §4 阻断项 1–4，再 P0 |
| P0 | **批准开工**（行为 Δ=0） |
| P1–P2 | **有条件批准**（补双盒、挂点、消费矩阵、相对 gap 验收） |
| 与 architecture MVP | **兼容**；本方案视为 dual 质量主线的「约束契约化」升级，不替代 M4/M5 技术债条目，而是收编 |
| 与 oa-dual PR-A | **并行保留**；Layout-First 不宣称覆盖文本恢复 |

### 修订建议（请作者合入 layout-first-plan v2.1）

1. §4 流水线补上 `StylesAndFormulas` 与 Intent 的相对顺序。  
2. §3 增加「design_box 只读 / paragraph.box 为结果」双盒说明。  
3. §3.1 keep_en：默认策略改为「callout 既有模式 + 可选 snapshot」；删除或降级全局 CJK 预估 skip。  
4. §6 P0 验收：挂点 + 新文件落点（`utils/layout_intent*.py`）。  
5. §6 P1 验收：相对 EN ink gap；标明过渡态单跳。  
6. §6 P2 前增加「消费端替换矩阵」子节。  
7. §2 非目标：显式 MT/连字/编码。  
8. §8 风险：Styles 竞态、误 skip、双轨 ExclusionZone。  
9. God-file：P0 禁止继续堆进 `typesetting.py` 主体逻辑。  
10. 在 `architecture-optimization-plan.md` 增加双向链接与 LayoutIntent 一行定义。

---

## 7. 源码锚点（便于作者/实施对照）

| 主题 | 路径 |
|------|------|
| 管线顺序 | `babeldoc/format/pdf/high_level.py` ~L999–1095 |
| RefMetrics | `il_version_1.ReferenceMetrics`；`layout_helper.compute_reference_metrics` |
| 标题间距 pass | `utils/vertical_gap.enforce_title_body_gaps` |
| 盒扩张 | `utils/box_expand.try_pre_expand_for_content`；`typesetting._pre_expand_narrow_box` |
| 绕图判定 | `utils/figure_wrap.is_figure_wrap_paragraph` |
| 行宽 cap | `typesetting._cap_available_with_reference` |
| 排除区 | `midend/exclusion_zone.ExclusionZoneIndex` |
| chrome | `utils/region_skip.is_chrome_paragraph` |
| 后处理重叠 | `typesetting.fix_overlapping_paragraphs_post_typesetting` |
| 指纹 | `utils/il_layout_fingerprint.il_layout_fingerprint` |
| 窄栏 keep_en | `translation_config.narrow_callout_mode`；`il_translator` skip 分支 |

---

## 8. 评分（评审用）

| 维度 | 分（10） | 说明 |
|------|---------|------|
| 问题诊断 | 9 | 与源码/现象高度对齐 |
| 方案完备性 | 7 | Intent 模型强；挂点/双盒/Constraint 演进弱 |
| 可增量落地 | 8 | P0–P5 清楚；god-file 与 P2 面偏大 |
| 验收可测性 | 8 | 几何断言强；绝对 25.7 宜改相对 |
| 与既有路线图一致 | 8 | 与 arch/defects/oa-plan 可收编 |
| 风险意识 | 7 | v2 已吸收多轮；仍缺 MT 边界与 Styles 时序 |
| **综合** | **7.8** | **Approve with changes** |

---

*评审基于 `5cf4962` 工作区只读核对；实施时若 HEAD 前进，请重核 `vertical_gap` / `figure_wrap` / `high_level` 挂点是否漂移。*
