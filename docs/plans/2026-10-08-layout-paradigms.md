# 版式范式 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给每个段落选一个放置范式，矩形正文走满栏左齐重排，只有真正的锥形才钉边。

**Architecture:** 不新增第二套角色。`select_paradigm` 读取已有 `LayoutIntent` 和行几何，写出运行时标记。`Typesetting` 只在 `rect_reflow` 与 `shaped_pocket` 两处改道。其余标记记为 `keep_current`。低置信度落到 `rect_reflow`。

**Tech Stack:** Python 3.12，现有 `LayoutIntent` / `LayoutIntentExtractor` / `Typesetting`，pytest。

**Spec:** `docs/plans/2026-10-08-layout-paradigms-spec.md`

## Global Constraints

- 基线提交 `398275a`，版本保持 `0.6.4.95`。
- `_DEFAULT_LINE_SKIP_CJK` 保持 `1.50`。`MIN_READABLE_SCALE` 保持 `0.55`。
- 页眉、页脚、分册名、网址保持英文。
- 分类器里不出现某一页的左缘、字号或空隙。锥形判定只用通用几何：去掉窄于本段峰值 60% 的短行后，满行 ≥ 4。右钉：右缘波动 ≤ 18pt，左缘极差 ≥ 24pt，6pt 桶的不同左缘 ≥ 4，相邻左缘向外跳超过 6pt 的比例 ≤ 30%。左钉：左缘波动 ≤ 18pt，右缘极差 ≥ 18pt，6pt 桶的不同右缘 ≥ 4，相邻右缘向外跳超过 6pt 的比例 ≤ 30%。右钉的左缘极差仍是 24pt。
- `PdfParagraph.layout_intent` 继续 `type="Ignore"`，新标记同样不进 XML。
- 不改切段、不拆对页、不修 CMap、不重译 OA 或 Vagina Masterclass。
- 本计划未接受前，不写入 `docs/PLAN-INDEX.md` 和 `docs/CURRENT-STATUS.md`。

## Review Focus

- 侧图旁的短项目（段内满行不足 4，或左缘极差不足 24pt）应是 `rect_reflow`。整页左缘在走，不能把这些短段合成一个 `shaped_pocket`。
- 同一段里的单调锥形应仍是 `shaped_pocket`。右缘钉住、左缘在走，或左缘钉住、右缘在走，都算。
- `LEFT_FIXED` 与 `RIGHT_FIXED` 已明确且形状是锥形时，钉边方向和口袋都保持原样。
- 几何不是锥形、但已经写了 `LEFT_FIXED` 或 `RIGHT_FIXED` 时，标记可以是 `rect_reflow`，口袋仍在，短行不贴钉边。没有存钉边、只有形状时，`rect_reflow` 仍取消缺省右钉，间隔计划不再吃这条形状。
- 引语、列表、页眉即使几何像短行或像锥形，也不能标成 `shaped_pocket`。
- 低置信度必须落到 `rect_reflow` 并带原因，不能静默右钉。

## 原型门

正式任务开始前，用 `tools/prototype/placement_paradigm_proto.py` 在本地 PDF 上跑同一套判定。原型只读行框，不翻译，不改 `Typesetting`。段落近似：先按 x 重叠分栏，再按字号和垂直空隙分段，不因为左缘移动而拆开锥形段。

通过条件写在 `docs/plans/2026-10-08-layout-paradigms-proto-eval.md`。不过门就不做 Task 1。门里的页码和路径只出现在评估文档和原型的用例表，不进分类函数。

差异要覆盖：矩形正文、同一段锥形、引语与正文分栏、侧图短项目、另一套左缘的矩形书、横开本、1224 对页、无文字层、坏编码。对页、无文字层、坏编码只报告输入门，不给放置范式。

---

### Task 1: 放置范式的选择函数

**Files:**
- Create: `babeldoc/format/pdf/document_il/utils/placement_paradigm.py`
- Test: `tests/test_placement_paradigm.py`

**Interfaces:**
- Consumes: `LayoutIntentRole`，`WrapMode`，行框列表 `(x0, x1, y0)`
- Produces:
  - `class PlacementParadigm(str, Enum)`：`RECT_REFLOW = "rect_reflow"`，`SHAPED_POCKET = "shaped_pocket"`，`KEEP_CURRENT = "keep_current"`
  - `@dataclass(slots=True) class ParadigmMark`：`paradigm: PlacementParadigm`，`confidence: float`，`reason: str`
  - `def select_paradigm(role: LayoutIntentRole, wrap_mode: WrapMode | None, line_boxes: list[tuple[float, float, float]]) -> ParadigmMark`

- [ ] **Step 1: 写失败测试**

覆盖：稳定左缘满栏 → `rect_reflow`，confidence ≥ 0.8，reason `stable_column`。四行左缘 100/112/124/136、右缘都在 570±10 → `shaped_pocket`，reason `taper`。三行内收不够 4 行 → `rect_reflow`，reason `taper_too_short`。悬挂缩进左缘只在 56/74/92 三档、右缘对齐、行数 ≥ 4 → `rect_reflow`，reason `not_taper`。`role` 为 `PULL_QUOTE`、`LIST`、`CHROME`、`TITLE` 时 → `KEEP_CURRENT`，即使行几何像锥形。`wrap_mode` 为 `RIGHT_FIXED` 且几何不是锥形 → `rect_reflow`，reason `shape_not_taper`。`wrap_mode` 为 `LEFT_FIXED` 且几何是锥形 → `shaped_pocket`。空行列表 → `rect_reflow`，confidence 0.4，reason `no_lines`。

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_placement_paradigm.py -q`  
Expected: 收集阶段失败，`placement_paradigm` 无法导入。

- [ ] **Step 3: 实现 `select_paradigm`**

先按角色：`CHROME`、`TITLE`、`PULL_QUOTE`、`CALLOUT`、`LIST`、`SECTION_HEADER`、`FIGURE_CAPTION`、`DROPCAP`、`FORMULA` 一律 `KEEP_CURRENT`，reason `keep_role`。其余角色里，满行是宽度 ≥ 本段峰值 60% 的行。锥形要满行 ≥ 4，并且是右钉或左钉之一。右钉：右缘极差 ≤ 18、左缘极差 ≥ 24、左缘按 6pt 取整后的不同值 ≥ 4、相邻左缘向外跳超过 6pt 的比例 ≤ 30%。左钉：左缘极差 ≤ 18、右缘极差 ≥ 18、右缘按 6pt 取整后的不同值 ≥ 4、相邻右缘向外跳超过 6pt 的比例 ≤ 30%。满行不足 4 但已满足对应钉边的极差时 reason 为 `taper_too_short`。左缘极差 ≤ 8 且不是上述短锥时 reason 为 `stable_column`。`wrap_mode` 已是 `LEFT_FIXED` 或 `RIGHT_FIXED` 而几何不是锥形时 reason 为 `shape_not_taper`，优先级高于 `stable_column`。其它矩形 reason 为 `not_taper`。没有行时 confidence 为 0.4，其余成功路径 ≥ 0.8。不要调用 `is_figure_wrap_taper`。

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/test_placement_paradigm.py -q`  
Expected: 全部通过。

- [ ] **Step 5: Commit**

```bash
git add babeldoc/format/pdf/document_il/utils/placement_paradigm.py tests/test_placement_paradigm.py
git commit -m "feat: select placement paradigm from role and line geometry"
```

### Task 2: 把标记挂到段落上，排版输出不变

**Files:**
- Modify: `babeldoc/format/pdf/document_il/utils/layout_intent.py`（`LayoutIntent` 增加字段）
- Modify: `babeldoc/format/pdf/document_il/utils/layout_intent_extractor.py`（`extract` 写标记）
- Test: `tests/test_placement_paradigm.py`

**Interfaces:**
- Consumes: `select_paradigm`
- Produces: `LayoutIntent.paradigm_mark: ParadigmMark | None`，默认 `None`。抽取之后非空。`Typesetting` 仍不读它。

- [ ] **Step 1: 写失败测试**

在 `tests/test_layout_intent_model.py` 的 `test_to_dict_roundtrip` 期望字典里增加 `"paradigm": None` 与 `"paradigm_reason": None`。扩展 `test_xml_serialization_omits_layout_intent`：标记设上之后，XML 仍不含 `layout_intent` 与 `paradigm_mark`。在 `tests/test_placement_paradigm.py` 增加 `test_extract_marks_rect_body`：复用 `tests/test_layout_intent_extractor.py` 里已有的正文段落夹具（与 `test_insets_from_visual_bbox` 同一构造方式），抽取后 `paradigm_mark.paradigm is PlacementParadigm.RECT_REFLOW`。用 `test_role_chrome` 的同一构造，断言 `KEEP_CURRENT`。

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_layout_intent_model.py::test_to_dict_roundtrip tests/test_placement_paradigm.py::test_extract_marks_rect_body -q`  
Expected: 期望字典多出的键失败，或 `paradigm_mark` 不存在。

- [ ] **Step 3: 挂字段并在抽取末尾赋值**

`paradigm_mark` 加在 `LayoutIntent.text_on_photo` 之后，默认 `None`。`layout_intent.py` 不要导入 `placement_paradigm`（避免循环）；字段注解用 `TYPE_CHECKING`。`to_dict` 增加 `paradigm` 与 `paradigm_reason`，标记为空时都是 `None`。`_from_dict` 读这两个键，缺键时保持 `None`。抽取器在 `extract` 末尾用该段行的视觉框调用 `select_paradigm`，写入 `paradigm_mark`。不要改 `wrap_mode`。

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/test_placement_paradigm.py tests/test_layout_intent_extractor.py tests/test_layout_intent_model.py -q`  
Expected: 通过。

- [ ] **Step 5: Commit**

```bash
git add babeldoc/format/pdf/document_il/utils/layout_intent.py babeldoc/format/pdf/document_il/utils/layout_intent_extractor.py tests/test_placement_paradigm.py
git commit -m "feat: store placement paradigm mark without changing layout"
```

### Task 3: 非锥形不再缺省右钉

**Files:**
- Modify: `babeldoc/format/pdf/document_il/utils/line_interval_plan.py`（`effective_wrap_mode`）
- Modify: `babeldoc/format/pdf/document_il/midend/typesetting.py`（读 `paradigm_mark` 的那一处绕图对齐）
- Test: `tests/test_placement_paradigm.py`

**Interfaces:**
- Consumes: `ParadigmMark`，现有 `effective_wrap_mode(paragraph, shape_present) -> WrapMode`
- Produces: 标记为 `RECT_REFLOW` 且没有存 `LEFT_FIXED` / `RIGHT_FIXED` 时，即使 `shape_present` 为真，`effective_wrap_mode` 也返回 `WrapMode.NONE`，间隔计划不再吃这条形状。已经写明的钉边保持原模式，口袋还在，但 `rect_reflow` 不把短行贴到钉边。标记为 `SHAPED_POCKET` 时保持该段原有的 `LEFT_FIXED` 或 `RIGHT_FIXED`，短行仍贴钉边。标记缺失时行为与改前一致。

- [ ] **Step 1: 写失败测试**

一段 `BODY`，行左缘都是 102、右缘都是 570，带一条合成的 `wrap_shape`，标记将是 `rect_reflow`。断言 `effective_wrap_mode` 为 `NONE`。另一段四行锥形、`wrap_mode` 已是 `RIGHT_FIXED`，断言仍为 `RIGHT_FIXED`。标记为 `None` 且 `shape_present` 为真，断言仍为 `RIGHT_FIXED`（旧调用方不受影响）。

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_placement_paradigm.py -q -k wrap_mode`  
Expected: 矩形加形状仍得到 `RIGHT_FIXED`。

- [ ] **Step 3: 改 `effective_wrap_mode`**

函数内部再导入 `PlacementParadigm`，避免 `line_interval_plan` 在模块加载时拉回 `placement_paradigm`。只在 `paradigm_mark.paradigm is RECT_REFLOW` 且没有存钉边时把缺省右钉改成 `NONE`。已经写明的 `LEFT_FIXED` / `RIGHT_FIXED` 留给间隔计划。不要删除标记缺失时的 `RIGHT_FIXED` 分支。`rect_reflow` 不贴钉边；`shaped_pocket` 和缺标记仍在 `effective_wrap_mode` 不是 `NONE` 时贴边。

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/test_placement_paradigm.py tests/test_line_interval_plan.py tests/test_wrap_fallback.py -q`  
Expected: 通过。

- [ ] **Step 5: Commit**

```bash
git add babeldoc/format/pdf/document_il/utils/line_interval_plan.py babeldoc/format/pdf/document_il/midend/typesetting.py tests/test_placement_paradigm.py
git commit -m "fix: keep non-taper body on rect reflow instead of right pin"
```

### Task 4: 本地评估脚本与金页清单

**Files:**
- Create: `tools/eval/placement_paradigm_score.py`
- Create: `docs/plans/2026-10-08-layout-paradigms-eval.md`
- Test: `tests/test_placement_paradigm_score.py`

**Interfaces:**
- Consumes: 两份 PDF 的页码与正文行框。脚本用 pymupdf，路径由参数传入。书不进 git。
- Produces: 命令 `python tools/eval/placement_paradigm_score.py --en PATH --zh PATH --pages 19,23,44`，stdout 为每页一行：`page paradigm_guess left_mode right_mode short_interior taper`。缺文件时退出码 2，不写盘。

- [ ] **Step 1: 写失败测试**

用两页合成 PDF（reportlab 或 pymupdf 画线，不依赖 OneDrive）。一页四行同一左缘，一页四行左缘内收、右缘对齐。断言脚本 stdout 含 `rect_reflow` 与 `shaped_pocket`，退出码 0。路径不存在时退出码 2。

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_placement_paradigm_score.py -q`  
Expected: 脚本不存在。

- [ ] **Step 3: 实现脚本并写评估说明**

脚本只做测量和 `select_paradigm` 猜测，不翻译。评估说明列出人工对照时要打开的文件，以及通过条件：

- 矩形参照：`Orgasmic Addiction.no_watermark.zh-CN.mono.pdf` 第 44 页正文。中文正文左缘与英文同一栏，中间行到达该栏右缘，短行只出现在段末。
- 锥形参照：同一中文单语第 19 页「主动掌控」。右缘钉住，左缘逐行内收。
- 引语参照：同一中文单语第 23 页。大字块与右栏是两个区域。
- 回归参照：0.6.4.95 OA dual（中文在左，canonical 路径见 `docs/CURRENT-STATUS.md`）第 19、59、91 页。p19 尖端仍右钉，p59 正文左缘仍在原稿栏，p91 引文与旁栏不重叠。数字以 `CURRENT-STATUS.md` 已写的测量为准，不抄进分类器。
- 反例：Vagina Masterclass 第 8 页。侧图使整页左缘下移，但每个项目自己不满 4 行锥形。任一项目被标成 `shaped_pocket`，或整页被合成一个 `shaped_pocket`，评估记失败。第 6、9 页的重复词列为切段问题，本计划不判放置失败。

说明里写纠正记录的格式：一行 JSON，`features`、`chosen`、`correct`、`page`。只追加，不自动改代码。

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/test_placement_paradigm_score.py tests/test_placement_paradigm.py -q`  
Expected: 通过。

- [ ] **Step 5: Commit**

```bash
git add tools/eval/placement_paradigm_score.py tests/test_placement_paradigm_score.py docs/plans/2026-10-08-layout-paradigms-eval.md
git commit -m "test: score placement paradigm guesses on local page pairs"
```

## 本计划之后才做

每一项单独开计划，沿用 `select_paradigm` 和评估脚本：

- 切段：同一视觉段一次翻译。解决重复词。
- `pull_quote`、`hanging_list`、`quote_mark`、`chapter_open`、`display_center`、`toc_entry` 各自的放置模块。
- 对页拆分、无文字层、坏 CMap。

## 自评

- 规格里的矩形栏、锥形、低置信度、不右钉、不写页特定常数、不改版本和行距，都有对应任务。
- 引语等角色只要求不被标成锥形，放置留在后续计划，与规格的 `keep_current` 一致。
- 切段、对页、整页图、坏编码写在规格的「不做」和计划末尾。原型只把它们报成输入门。
- Task 1 在原型门通过之后才开始。原型脚本不替代 `placement_paradigm.py`。
