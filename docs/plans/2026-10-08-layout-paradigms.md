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
- 分类器里不出现某一页的左缘、字号或空隙。锥形判定只用通用几何：连续 ≥ 4 行，左缘每行增加 ≥ 6pt，右缘波动 ≤ 18pt。
- `PdfParagraph.layout_intent` 继续 `type="Ignore"`，新标记同样不进 XML。
- 不改切段、不拆对页、不修 CMap、不重译 OA 或 Vagina Masterclass。
- 本计划未接受前，不写入 `docs/PLAN-INDEX.md` 和 `docs/CURRENT-STATUS.md`。

## Review Focus

- 有侧图但左缘不内收的正文，应是 `rect_reflow`，现在会因缺省 `RIGHT_FIXED` 贴右。
- 单调锥形（右缘钉住、左缘内收）应仍是 `shaped_pocket`，不能被矩形规则拉直。
- `LEFT_FIXED` 与 `RIGHT_FIXED` 已明确且形状是锥形时，钉边方向保持原样。
- 引语、列表、页眉即使几何像短行，也不能标成 `shaped_pocket`。
- 低置信度必须落到 `rect_reflow` 并带原因，不能静默右钉。

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

覆盖：稳定左缘满栏 → `rect_reflow`，confidence ≥ 0.8，reason `stable_column`。四行左缘 100/112/124/136、右缘都在 570±10 → `shaped_pocket`，reason `taper`。三行内收不够 4 行 → `rect_reflow`，reason `taper_too_short`。`role` 为 `PULL_QUOTE`、`LIST`、`CHROME`、`TITLE` 时 → `KEEP_CURRENT`，即使行几何像锥形。`wrap_mode` 为 `RIGHT_FIXED` 且几何不是锥形 → `rect_reflow`，reason `shape_not_taper`。`wrap_mode` 为 `LEFT_FIXED` 且几何是锥形 → `shaped_pocket`。空行列表 → `rect_reflow`，confidence 0.4，reason `no_lines`。

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_placement_paradigm.py -q`  
Expected: 收集阶段失败，`placement_paradigm` 无法导入。

- [ ] **Step 3: 实现 `select_paradigm`**

锥形先数连续行：按 `y0` 从上到下，相邻行左缘差 ≥ 6 且右缘差 ≤ 18 才累加，否则断段。任一段长度 ≥ 4 即为锥形。`CHROME`、`TITLE`、`PULL_QUOTE`、`CALLOUT`、`LIST`、`SECTION_HEADER`、`FIGURE_CAPTION`、`DROPCAP`、`FORMULA` 一律 `KEEP_CURRENT`。其余角色里，锥形才是 `SHAPED_POCKET`。没有行时 confidence 为 0.4，其余成功路径 ≥ 0.8。

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
- Produces: 标记为 `RECT_REFLOW` 时，即使 `shape_present` 为真，`effective_wrap_mode` 也返回 `WrapMode.NONE`。标记为 `SHAPED_POCKET` 时保持该段原有的 `LEFT_FIXED` 或 `RIGHT_FIXED`。标记缺失时行为与改前一致。

- [ ] **Step 1: 写失败测试**

一段 `BODY`，行左缘都是 102、右缘都是 570，带一条合成的 `wrap_shape`，标记将是 `rect_reflow`。断言 `effective_wrap_mode` 为 `NONE`。另一段四行锥形、`wrap_mode` 已是 `RIGHT_FIXED`，断言仍为 `RIGHT_FIXED`。标记为 `None` 且 `shape_present` 为真，断言仍为 `RIGHT_FIXED`（旧调用方不受影响）。

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_placement_paradigm.py -q -k wrap_mode`  
Expected: 矩形加形状仍得到 `RIGHT_FIXED`。

- [ ] **Step 3: 改 `effective_wrap_mode`**

函数内部再导入 `PlacementParadigm`，避免 `line_interval_plan` 在模块加载时拉回 `placement_paradigm`。只在 `paradigm_mark.paradigm is RECT_REFLOW` 时把缺省右钉改成 `NONE`。不要删除标记缺失时的 `RIGHT_FIXED` 分支。`typesetting.py` 里 `wrap_flush_alignment` 仅在 `effective_wrap_mode` 不是 `NONE` 时把对齐改成贴边。

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
- 反例：Vagina Masterclass 第 8 页侧图正文若被标成 `shaped_pocket`，评估记失败。第 6、9 页的重复词列为切段问题，本计划不判放置失败。

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
- 切段、对页、整页图、坏编码写在规格的「不做」和计划末尾，没有假装本计划能减少那几类人工校正。
