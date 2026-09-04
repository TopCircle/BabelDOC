# Orgasmic Addiction Dual 版面修复 — PR 拆分计划

> **2026-08-13 — Superseded as the OA queue.** PR-A–D landed around 0.6.4.37.  
> **Current OA work:** [`oa-dual-quality-wave-0.6.4.69.md`](oa-dual-quality-wave-0.6.4.69.md)  
> Keep this file for the A→D dependency story and page evidence. Do not open a new PR-E from this list.

> **基线 dual（historical）**：`Orgasmic Addiction.no_watermark.zh-CN.dual.pdf`（2025-07-29 再生）  
> **对照页**：3–120（中文左半 / 英文右半）  
> **原则**：每个 PR 可独立 merge、有明确验收页与测试；**先修 IL 输入，再修 skip 策略，最后修 box 重排**。  
> **禁止**：在未过 figure IL 不变性 + OA 抽样页前扩大 `stream_order` 触发面。

**当时代码基线**：`0.6.4.37`（A recovery + B title + C1 report + C2 safer skip + D narrow_callout；figure IL invariants）

---

## 依赖图

```text
PR-A soft-hyphen/ligature cross-run     ──┐
PR-B decorative/header title policy      ─┼─► PR-E technique glossary (optional parallel after A)
PR-C untranslated-block audit / skip     ─┤
PR-D narrow-callout product + box        ─┘
         │
         ▼
   Regen OA dual p7/8/15/41/46 + figure golden
```

| PR | 可并行？ | 依赖 |
|----|----------|------|
| A | 可先做 | 无 |
| B | 可与 A 并行 | 无（勿动 plain-text reorder 默认） |
| C | 依赖 A 部分效果更准 | 建议 A 后，或并行但验收分开 |
| D | 可与 B 并行 | 无 |
| E | 可最后 / 与 C 后并行 | A 更好 |

---

## PR-A — 软连字符 + 连字跨 run 恢复（P0）

### 目标
消灭 `di` / `ff` / `ﬃ` / `somewheredi` / `cli toral` 类碎片，降低「半段 EN + 半段中文」。

### 覆盖问题类
- 类别 5 连字/软连字符碎片（~24 页）
- 部分类别 4 未译/半译（碎片导致 skip 或胡译）

### 主要改动
| 区域 | 内容 |
|------|------|
| `text_recovery.py` | 跨 composition / 跨行 soft-hyphen：`word-` + 下一 run 小写续写 → 粘合；连字展开已有则保 |
| `layout_helper.get_char_unicode_string` | 保证粘合发生在 MT 之前；避免只处理单 line 内 |
| `styles_and_formulas`（若需） | 避免把 `proﬁcient` 拆成 formula 与正文两段导致粘合失败 |
| 测试 | 合成 `di`+`ﬀ`+`erent`、`ap-`+`proximation`；可选 OA p7 金句 `different` / `difficult` |

### 验收页（OA dual 左半）
| 页 | 期望 |
|----|------|
| 7 | 不再出现 `ff 女人喜欢 di`、`ffi away somewheredi ceptionally` |
| 46 | `clitoral` 完整或合理中文，非 `cli toral` |
| 71 | 减少 `ﬁnger` 碎片独立残留 |

### 回归闸
```bash
pytest tests/test_figure_il_invariants.py tests/test_stream_visual_order.py -q
# 新增 text_recovery 单测
```

### 风险
粘合过猛 → `Trigasm- actually` 类误粘（沿用 `should_soft_rejoin` 词表）。

### 建议标题
`fix(recovery): cross-run soft-hyphen and ligature rejoin for design PDFs`

---

## PR-B — 装饰标题 / 页眉章节条策略（P0/P1）

### 目标
章首页与 running header 可读：减少 `WhohaSorgaSMS`、`Sou Loyre a`、`Chapter1爱与性`、每页 `Learn The Trigasm` 噪音。

### 覆盖问题类
- 类别 2 Chapter 粘连（~96 页）
- 类别 3 装饰标题乱码（~28 页）
- 类别 1 页眉 chrome 一部分（与 C 分工：B 管「标题形态」，C 管「是否翻译」）

### 主要改动
| 区域 | 内容 |
|------|------|
| `ParagraphFinder` | 同页短 title 条：Chapter+数字+标题 合并策略；running header 识别（顶带、重复、小字号） |
| `stream_order` | **禁止**对 plain text 放开；可对 `title`/`section_header` 加强空格插入（词边界） |
| `get_char_unicode_string` / tracking | 装饰 tracking 下仍尽量插词间空格（Who has…） |
| 可选 UI/config | `translate_running_header: bool`（默认 false 则遮罩/保留 EN 二选一，写清产品） |

### 验收页
| 页 | 期望 |
|----|------|
| 7 | 大标题接近「第 1 章 / 爱与性」或「Chapter 1 · 爱与性」可读；`Who has orgasms?` 可读（中或英） |
| 8 | `Are You Lost at Sea?` 不再 `Sou Loyre a` |
| 9+ | running `Chapter N …` 不与正文糊成一团 |

### 回归闸
```bash
pytest tests/test_figure_il_invariants.py tests/test_stream_visual_order.py -q
# 新增：装饰标题合成 case（reverse + 空格）
```

### 风险
标题合并过猛 → 把相邻正文并进标题。用几何（顶带、字号众数）约束。

### 建议标题
`fix(layout): chapter header merge and decorative title spacing`

---

## PR-C — 未译块审计与 skip 边界（P0）

### 目标
明确「为何英文留在中文页」；修正误 skip；产品上故意不译的写进日志/指标。

### 覆盖问题类
- 类别 4 整段/半段 EN（~67 页）
- 类别 1 页眉 chrome EN（~92 页）— 与 B 协同：skip 则统一不译，不 skip 则进 MT

### 主要改动
| 区域 | 内容 |
|------|------|
| `ILTranslator` | 统一 skip 原因枚举：`header` / `figure_text` / `ultra_narrow` / `pullquote` / `placeholder` / `short` |
| debug | `--debug` 输出 `skip_report.json`：页码、paragraph id、reason、unicode 前 80 字 |
| 逻辑修正 | 误标 figure 的正文旁注；段首正文被 header band 误杀（title 已有例外，扩展 body） |
| 工具 | `babeldoc.tools.skip_audit` 或扩展 `dual_quality_check`：统计左半纯 EN 行比例 |

### 验收页
| 页 | 期望 |
|----|------|
| 8 | 段首「testicles massaged…」要么译出，要么在 skip_report 标 `ultra_narrow`/`figure` 且合理 |
| 9 | 段尾完整 EN 句有 reason，非静默丢失 |
| 41 | 段首科学句 EN 有 reason 或被译 |

### 回归闸
- 单测：header band 不跳过 `layout_label=plain text` 且在正文 y 范围  
- figure golden IL 不变性仍绿  

### 建议标题
`feat(translator): skip-reason audit and safer header/figure skip bounds`

---

## PR-D — 窄旁注产品策略 + box 扩展（P1）

### 目标
图旁/红字栏不再「中文竖条一字一行」；产品默认写死：**过窄则保留 EN 或扩框/降级**，二选一可配置。

### 覆盖问题类
- 类别 6 窄栏/图旁（少页高痛）
- 与 4b 故意 EN 旁注的产品文档

### 主要改动
| 区域 | 内容 |
|------|------|
| `side_callout_skip` / config | `narrow_callout_mode: keep_en \| expand \| translate_body_column` |
| `box_expand` / `Typesetting` | 窄栏 + 右挡：向下扩阈值可调；失败则 fallback keep_en |
| 文档 | SCORECARD / layout-engine-defects 写明 OA p8 行为 |

### 验收页
| 页 | 期望 |
|----|------|
| 7 | 侧栏中文不再严重 `di/ff` 竖条（配合 A） |
| 8 | 红字栏：要么整洁 EN，要么可读中文（非一字一行） |
| 88 | TIP 旁中文可读 |

### 回归闸
```bash
pytest tests/test_box_expand.py tests/test_side_callout_skip.py -q
pytest tests/test_figure_il_invariants.py -q
```

### 建议标题
`fix(typesetting): configurable narrow-callout mode (keep_en / expand)`

---

## PR-E — 技法名 / 体位 glossary（P2，可选）

### 目标
`Flicking` / `Stroking` / `Indirect Curl` 等稳定译名或稳定保留。

### 覆盖问题类
- 类别 7 技法名中英夹杂（~21 页）
- 部分类别 8 语义

### 主要改动
- `glossaries` / `proper_nouns`（部署侧）+ 引擎 flex protect 已有能力复测  
- 可选：检测 `CamelCase` 技法标题 span，强制 protect 或查表  

### 验收页
46, 71, 102 — 技法标签一致。

### 建议标题
`chore(glossary): sex-technique terms for Gabrielle Moore line`

---

## 每个 PR 的强制检查清单（防止改 A 坏 B）

合并前 **全部** 勾选：

- [ ] `pytest tests/test_figure_il_invariants.py tests/test_stream_visual_order.py -q`
- [ ] 未扩大 `stream_order` 对 `plain text` 的 reorder
- [ ] OA 抽样目视：**p7, p8, p15, p41, p46**（左半）
- [ ] figure golden 源 PDF IL 关键句仍在（invariants）
- [ ] 若改 typesetting/box：`pytest tests/test_box_expand.py -q`

**推荐命令（PR 说明里复制）：**

```bash
pytest tests/test_figure_il_invariants.py tests/test_stream_visual_order.py \
  tests/test_box_expand.py tests/test_side_callout_skip.py -q
```

---

## 建议落地顺序（迭代）

| Sprint | PR | 版本暗示 |
|--------|-----|----------|
| 1 | **A** 软连字符/连字 | 0.6.4.33 |
| 1 | **C1** skip 审计 report | 0.6.4.34 |
| 2 | **B** 标题/页眉 | 0.6.4.35 |
| 2 | **D** 窄旁注 | 0.6.4.36 |
| 2 | **C2** 收紧误 skip | 0.6.4.37 |
| 3 | **E** glossary + 全量重生 dual 3–120 对照 | — |

**C 可拆两刀：**  
- **C1** 仅 `skip_report.json`（零行为风险）  
- **C2** 收紧误 skip  

---

## 非目标（明确不做）

- 改 dual 左右拼接为逐段对照  
- 用 DeepLX 提示词硬修「邪教」类语义而不修 IL  
- 默认打开 `enable_post_layout_optimization` 当银弹  
- 对 plain text 重新启用全局 visual reorder  

---

## 验收总表（全 PR 合完后）

| 页 | 必须改善 |
|----|----------|
| 7 | 标题可读；侧栏/连字碎片↓；Who has… 可读 |
| 8 | 段首/红字有策略（译或整洁 EN）；无 `Sou Loyre a` |
| 15 | 步骤 callout 序可读或整段策略一致 |
| 41 | 段首不整页 EN 无 reason |
| 46 | 动作说明中文为主；Flicking/Stroking 一致 |
| 每页 chrome | 产品决策：译 / 不译 / 遮罩，全篇一致 |

---

## 文档与追踪

| 文档 | 用途 |
|------|------|
| 本文 | PR 拆分与依赖 |
| `docs/layout-engine-defects.md` | 结构性缺陷（可链到 PR-A/D） |
| `tests/golden/SCORECARD.md` | figure + reading-order 闸 |

Issue 标题模板：

```text
[OA dual] PR-A soft-hyphen/ligature
[OA dual] PR-B decorative/chapter header
[OA dual] PR-C skip audit
[OA dual] PR-D narrow callout mode
[OA dual] PR-E technique glossary
```
