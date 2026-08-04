# Layout-First 编码方案（layout-first-coding-plan v1）

| 字段 | 值 |
|------|-----|
| 状态 | P0 ✅ · P1 ✅ · **P2 in progress (0.6.4.53)** |
| 基线 | `2fe458f` / 0.6.4.52（P1 close）→ P2 `0.6.4.53` |
| 上游 | [`layout-first-plan.md`](layout-first-plan.md) v2.1 + [`layout-first-plan-review.md`](layout-first-plan-review.md) |
| 硬约束 | **P0 只加字段+提取，禁止改 typesetting/box_expand/vertical_gap 行为路径**；P1–P5 接口本次定死，防止 P0 画死角 |

---

## 1. P0 编码设计

### 1.1 新文件清单与职责

| 文件 | 职责 |
|---|---|
| `babeldoc/format/pdf/document_il/utils/layout_intent.py` | `LayoutIntent` + `LayoutIntentRole`（str Enum）+ `to_dict()`；纯模型，不 import 提取器 |
| `babeldoc/format/pdf/document_il/utils/layout_intent_extractor.py` | `LayoutIntentExtractor`：遍历页/段、分类、快照、gap/stack 计算、debug dump；只读 |
| `tests/test_layout_intent_model.py` / `tests/test_layout_intent_extractor.py` | P0 验收 |

### 1.2 LayoutIntent（精确定义）

```python
class LayoutIntentRole(str, Enum):
    BODY = "body"; TITLE = "title"; SUBTITLE_OVERLAY = "subtitle_overlay"
    PULL_QUOTE = "pull_quote"; CALLOUT = "callout"; FIGURE_CAPTION = "figure_caption"
    CHROME = "chrome"; WRAP_COLUMN = "wrap_column"
    # 预声明成员（评审"枚举偏窄"阻断项）：P0 仅产出 FORMULA/SECTION_HEADER，
    # 其余保留默认 body，防 P2+ 枚举返工
    FORMULA = "formula"; SECTION_HEADER = "section_header"
    LIST = "list"; DROPCAP = "dropcap"; OCR = "ocr"

@dataclass(slots=True)
class LayoutIntent:
    """翻译前派生投影，不可变契约（消费方不得改）。全部 runtime-only。"""
    role: LayoutIntentRole         # 分类结果；未知一律 BODY
    design_box: Box                # Styles 之后 para.box 的深拷贝；排版只读
    top_inset: float               # design_box.y2 − 首行墨迹顶(y2 max)，PDF y-up
    bottom_inset: float            # 末行墨迹底(y min) − design_box.y
    wrap_shape: list[tuple[float, float]] | None = None  # 每行 (left_offset, width)；右缘=design 右缘，左缘=右缘−width
    overlays_band: str | None = None   # SUBTITLE_OVERLAY → 所叠 TITLE 的 debug_id
    stack: int = 0                 # 设计重叠连通组（组内不互推）；仅组底段带 gap_contract
    expansion_policy: tuple[str, ...] = ("right", "down")  # 可扩轴向按序；chrome=()；wrap_column 禁 left
    expansion_limits: tuple[str, ...] = ("page_margin",)   # 符号来源；P1+ 查 ExclusionZoneIndex 数值
    overflow_policy: str = "scale_down"  # scale_down | expand
    min_scale: float = 0.55        # 段级缩放下限（全局默认）
    gap_contract: float | None = None  # 本段墨迹底 − 下一内容块墨迹顶（可负=重叠）；排除 stub/chrome
    is_chrome: bool = False
    text_on_photo: bool = False

    def to_dict(self) -> dict: ...  # Box→[x,y,x2,y2]；wrap_shape→[[l,w],…]；role→value
```

### 1.3 PdfParagraph.layout_intent（runtime-only，仿 reference_metrics）

`il_version_1.py`（reference_metrics 之后）追加：

```python
    # Runtime-only; xsdata type="Ignore" is required so a set LayoutIntent
    # is never emitted as an XML element (unlike bare reference_metrics/alignment).
    layout_intent: "LayoutIntent | None" = field(
        default=None, metadata={"type": "Ignore"}
    )
```

文件顶部须 **运行时** `from ...utils.layout_intent import LayoutIntent`（xsdata
`get_type_hints` 要解析注解；该文件无 `from __future__ import annotations`）。
`layout_intent.py` 对 `Box` 仅 TYPE_CHECKING import ⇒ 不成环。

### 1.4 LayoutIntentExtractor.extract

```python
class LayoutIntentExtractor:
    def __init__(self, translation_config: TranslationConfig): ...
    def extract(self, document: Document) -> None   # 入口；逐页 try/except
    # 内部：_extract_page / _classify_role / _line_boxes / _extract_insets /
    #       _extract_wrap_shape / _compute_gap_contracts / _compute_stacks /
    #       _is_on_photo / _ink_rect / _dump
```

- **design_box**：`para.box` 深拷贝；`para.box is None` → 不挂 intent，audit.no_box+1。
- **role 规则**（严格按序，首中即定）：
  1. `is_chrome_paragraph(para, page)`（region_skip.py:214）→ CHROME
  2. composition 含 `pdf_formula` → FORMULA
  3. `is_figure_wrap_paragraph(para)`（figure_wrap.py:42，**唯一** taper 源，禁第二处复算）→ WRAP_COLUMN
  4. layout_label ∈ {figure_caption, figure_title, figure_text} → FIGURE_CAPTION
  5. layout_label ∈ {section_header, paragraph_title} → SECTION_HEADER；label==title 且 `is_display_title`（vertical_gap.py:84）→ TITLE
  6. 墨迹 y 区间与 TITLE 重叠 ≥0.5×行高、字号<标题字号、非 title 类标签 → SUBTITLE_OVERLAY（overlays_band=该 TITLE 的 debug_id）
  7. `is_quote_block(para, page_width)`（layout_helper 既有启发式）→ PULL_QUOTE（P0 单源；P2 才切消费端）
  8. label=="callout" 或 `is_callout_column(box)`（box_expand 既有）→ CALLOUT
  9. 其余 → BODY
  - **stub 短路（先于 1–9）**：`is_layout_debug_stub` → 固定 BODY（禁止再走 callout/quote 启发式）；并**排除** gap/stack/photo
- **_ink_rect(para)**：首选 `visual_bbox.box`，缺失回退 char box（理由见决策点 1）；**insets**：首行=墨迹 y2 最大、末行=墨迹 y 最小；**_line_boxes**：comp.pdf_line.box 优先，退化按 char y2 聚类（容差 max(font_size)×0.25）。
- **wrap_shape**：仅 role==WRAP_COLUMN 且 ≥2 行：每行 `(line.x − design_box.x, line.x2 − line.x)`。
- **gap_contract**（页级一次算）：候选=墨迹在本段下方（`ink.y2 < 本段 ink.y`）且 x 重叠（slack=8，仿 vertical_gap._x_overlap:95）的非 chrome/非 stub 段，取 ink.y2 最大者；`gap = 本段 ink.y − 候选 ink.y2`；同 stack 仅组底（ink.y 最小）计算，候选须低于整组底；无候选→None。
- **stack**：非 chrome/非 stub 段连通分量（y 重叠 ≥0.5×min(行高) 且 x 重叠 slack=8），union-find，id 从 0。
- **text_on_photo**：墨迹与 `page.pdf_figure` / `pdf_form(image)` box 的 IoU ≥0.30（`calculate_box_iou`，layout_helper.py:83）；CHROME 不判。
- **policy 投影**（P0 只描述现状，不改行为）：CHROME→(()、()、scale_down)；WRAP_COLUMN→(("right","down")、("photo","page_margin")、scale_down)；CALLOUT→(("left","down","right")、("page_margin",)、expand)（镜像 box_expand 现序）；其余默认。

### 1.5 挂点（high_level.py 行号级）

插入 **L1026 之后、L1028 FlowDebugSvg 之前**（L1020 `StylesAndFormulas.process`；L1024–1026 styles_and_formulas.json dump；L1044–1056 ILTranslator；L1086 Typesetting）：

```python
    # Layout-First P0: intent 提取（Styles 后、翻译前）。只读；失败仅告警不阻断。
    try:
        from babeldoc.format.pdf.document_il.utils.layout_intent_extractor import (
            LayoutIntentExtractor,
        )
        LayoutIntentExtractor(translation_config).extract(docs)
    except Exception:
        logger.warning(
            "layout_intent extraction failed; continuing without intent", exc_info=True
        )
```

异常语义：extract 内部按页 try/except（单页失败→audit.pages_skipped+1 + warning），入口再兜底；挂在 ILTranslator 之前 ⇒ skip_translation 路径天然覆盖。

### 1.6 debug dump（仅 --debug）

extract 内按 `translation_config.debug` 写 `get_working_file_path("layout_intent.json")`；自序列化（xml_converter 不认 runtime 字段）：

```json
{"version":1,"baseline":"5cf4962","pages":{"19":{"<debug_id>":{
 "role":"wrap_column","design_box":[x,y,x2,y2],"top_inset":2.1,"bottom_inset":1.8,
 "wrap_shape":[[4.0,194.0],[6.5,174.0]],"overlays_band":null,"stack":0,
 "expansion_policy":["right","down"],"expansion_limits":["photo","page_margin"],
 "overflow_policy":"scale_down","min_scale":0.55,"gap_contract":12.3,
 "is_chrome":false,"text_on_photo":true}}},
 "audit":{"pages_skipped":0,"no_box":1,"extract_errors":0}}
```

### 1.7 指纹

`il_layout_fingerprint`（il_layout_fingerprint.py:63）只哈希 3 位小数字符几何，本就忽略 runtime 字段 ⇒ **无需改指纹函数**；补单测：同 doc 挂/不挂 layout_intent 指纹相等。

### 1.8 行为不变保障与验收

改动面=新增 2 文件 + il_version_1 加 1 字段 + high_level 加 1 try 块；typesetting/box_expand/vertical_gap 零改动。验收：
- `tests/test_layout_intent_model.py`：`test_role_enum_values`、`test_to_dict_roundtrip`、`test_pdf_paragraph_layout_intent_default_none`、`test_xml_serialization_omits_layout_intent`
- `tests/test_layout_intent_extractor.py`：`test_role_chrome`、`test_role_wrap_column_single_source`（monkeypatch is_figure_wrap_paragraph）、`test_role_subtitle_overlay`、`test_role_pull_quote_single_source`、`test_design_box_is_deep_copy`、`test_insets_from_visual_bbox`、`test_wrap_shape_left_offset_width`、`test_gap_contract_excludes_stub_chrome`、`test_gap_contract_stack_bottom_only`、`test_text_on_photo_iou`、`test_extract_failure_is_silent`、`test_dump_only_debug`、`test_fingerprint_ignores_layout_intent`
- 闸：全量 `uv run pytest tests/ -q` 全绿 + repro digest Δ=0（§2）+ 指纹 sha 与基线一致

---

## 2. repro 基建（P0 前置）

```
tests/repro/
├── README.md            # 生成/对比/更新 golden 用法
├── driver.py            # 参数化 CLI：--pdf --pages --working-dir --out-dir --map-json --translator {fixedmap,identity}
│                        # 复用 babeldoc.translator.fixed_map_translator.FixedMapTranslator（已入库），删硬编码路径
├── synth_page.py        # 合成验收页：title+wrap_column+chrome+body 的 IL Document（CI 可跑，免 OA 原件）
├── golden/
│   ├── oa_p19_typsetting.json  # 摘要 {page:{debug_id:{box:[x,y,x2,y2],scale,optimal_scale,line_widths[]}}}
│   └── synth_layout.json
└── digest.py            # --golden/--run-dir 对比：canonical 序列化 sha256 + il_layout_fingerprint sha；Δ=0 判定；--update-golden
```

- 行宽**禁止**用 `reference_metrics.per_line_widths`，一律从 typsetting.json 的 pdf_character 按 y 聚类重算（plan §7 数据源规则）；断言先验 debug_id 集合不变。
- 固定验收页：**OA p19**（本地生成 golden）+ **合成页**（CI 默认）。`tests/repro/test_synth_digest_stable.py::test_synth_digest_stable` 默认跑；OA p19 对比仅本地/手动。
- CI `checks.yml` 追加**可选** job（不默认跑，复用 assets cache，同 key `babeldoc-assets-${{ hashFiles('babeldoc/assets/embedding_assets_metadata.py') }}`）：

```yaml
  layout-repro:
    if: ${{ github.event_name == 'workflow_dispatch' || contains(github.event.pull_request.labels.*.name, 'layout') }}
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
        with: {persist-credentials: false}
      - uses: actions/cache@v5
        with: {path: ~/.cache/babeldoc, key: babeldoc-assets-${{ hashFiles('babeldoc/assets/embedding_assets_metadata.py') }}}
      - uses: astral-sh/setup-uv@85856786d1ce8acfbcc2f13a5f3fbd6b938f9f41
        with: {python-version: "3.12", enable-cache: true, cache-dependency-glob: "uv.lock", activate-environment: true}
      - run: uv sync
      - run: uv run python tests/repro/digest.py --golden tests/repro/golden/synth_layout.json
```

---

## 3. P1–P5 接口预留

### 3.1 gap_contract 消费（P1）— **实现 + 抽样验收 Done（0.6.4.52）**

- **新文件**（主体逻辑不进 typesetting）：
  - `utils/layout_audit.py` — `LayoutAuditReport`（**actions=预留** / **violations=修复** / shifts / cascade_len）
  - `utils/gap_contract_pass.py` — first-pass：只改下一正文 `paragraph.box`；**仅 dy&lt;0 下移**；**|dy|≤24 与 post 一致**；`is_display_title` 不可当 body
  - `utils/layout_gap_hooks.py` — `pre_typeset_gap_pass` / `post_typeset_gap_pass`（typesetting 两行钩子）
  - `tools/p1_ink_gap_accept.py` — dual 左右半 title→body ink gap 验收（`deficit≤0`）
- **共享**：`layout_box` / `boxes_x_overlap` / `find_content_below` / `is_gap_protected`（含 display title）/ `resolve_en_gap_contract` / `gap_deficit`
- **钩子**：`render_page` → pre → glyphs → `fix_overlapping` → post
- **`enforce_title_body_gaps`**：单跳 `|dy|≤24`、cascade≤1；目标=`gap_deficit`（相对 EN）
- **`enforce_title_body_gaps_legacy`**：旧级联保留
- **验收**：
  - 单测：`test_vertical_gap` + `test_p1_ink_gap_accept`
  - OA 抽样：`docs/p1_acceptance_oa.md` — dual_layout **7/7 pass**（0.6.4.50 同页 2/7 pass）
  - 命令：`python -m babeldoc.tools.p1_ink_gap_accept --pdf <dual.pdf> --pages 3,7,12,19,33,40,73`

### 3.2 wrap_shape 消费（P2）— ✅ 0.6.4.53

- 入口：`Typesetting._typeset_wrap_line(design_box, wrap_shape, line_idx) -> (left, right)`
  - 右缘钉 `design_box.x2`；左缘 = 右缘 − width（左缘步进，**不镜像**）
  - 超长行复用 shape 末行 width
- 统一替换矩阵经 `_resolve_line_intervals`：

| 函数 | 有 wrap_shape（且 `enable_layout_intent_wrap`） | 无 wrap_shape |
|---|---|---|
| `_uniform_cjk_reference_widths` | **不调用**（wrap 路径拥有行形） | 现状 |
| `_query_line_intervals` | **跳过**；意图单区间优先于 zone | 现状多区间 |
| `_cap_available_with_reference` | **不走**；改 `_typeset_wrap_line` | 现状 |
| `_pre_expand_narrow_box` | wrap_shape / WRAP_COLUMN **禁用**（保留 taper 安全网） | 现状 |

- 开关：`TranslationConfig.enable_layout_intent_wrap: bool = True`（P2 默认开）
- 验收：`tests/test_figure_wrap_policy.py` — `test_wrap_line_pins_right_edge`、`test_wrap_line_left_steps_not_mirror`、`test_replace_matrix_no_wrap_shape_unchanged`、wrap 覆盖 reference cap、flag off 回退

### 3.3 双盒写回（P0 定死）

`design_box` 只读意图；`paragraph.box` 写排版结果。现状 7 处 `paragraph.box = expanded`（typesetting.py:1578/1603/1616/1634/1647/2222/2260）保持写 paragraph.box，P1+ 禁止 `design_box.* =`（code-review 规则）；PDFCreater/审计/Δ 断言读 paragraph.box、比 design_box。

### 3.4 retypeset_paragraph / PostLayoutProcessor（P3）

契约：`retypeset_paragraph(paragraph, page, line_skip=None)`（typesetting.py:2412）入参必须带 layout_intent（缺→告警走旧路径）；初始 box=intent.design_box、行宽=wrap_shape（若有）、y=gap_contract 落位；返回 bool 语义不变。PostLayoutProcessor 同契约，禁止无 intent 移动 chrome/标题。验收：`tests/test_post_layout_processor.py` 增 `test_retypeset_respects_intent`、`test_retypeset_rejects_moving_chrome`。

### 3.5 特征开关

- `TranslationConfig.enable_layout_intent_wrap: bool = True`：P2 合入后默认开；`False` 回退 reference-width cap。
- `TranslationConfig.enable_legacy_quote_geometry: bool = False`：P2 完成后默认关（旧 quote 几何路径回退用，防双轨并存）；命名仿 `enable_post_layout_optimization` 模式。

---

## 4. 风险与决策点（需主线程拍板）

1. **top/bottom_inset 数据源**：建议 **visual_bbox**（缺失回退 char box）。理由：ParagraphFinder 即用 visual_bbox 生成 para.box（paragraph_finder.py:103-104、358-361），与 design_box 同坐标系、inset 自洽；char box 含字体行距，恰是 CJK 行高失真源。备选：char box（与 vertical_gap.ink_box 现语义一致，P1 需迁移 ink 语义）。
2. **gap_contract 相邻块判定**：建议"下方墨迹中 x 重叠(slack=8)的最近非 chrome/非 stub 段；stack 仅组底计算"。备选：按 render_order 相邻（不按几何，噪声大）。
3. **role 枚举扩展**：建议加 formula/section_header/list/dropcap/ocr 预声明（评审"枚举偏窄"阻断项），P0 仅产出 formula/section_header 两个无歧义信号。
4. **text_on_photo IoU 阈值**：建议 ≥0.30（calculate_box_iou），需 p19 实测校准。
5. **pull_quote P0 单源**：建议沿用 is_quote_block 启发式派生 role；若 P0 就要"不再几何误判"须先改 box_expand，违反行为不变，不建议。
6. **subtitle_overlay 判据**：y 重叠 ≥0.5×行高 + 字号<标题 + 非 title 标签（待 p19 校验）。
7. **P1 过渡态数值**：dy≤24pt 单跳、级联≤1 是否接受（评审阻断 6，需分页标注）。

风险：role 误判→保守 BODY+dump 审计；Styles 竞态→挂点固定 Styles 后、design_box 以 Styles 后为准；visual_bbox 缺失→回退 char box 并在 dump 记 source；layout_intent.json 体积→仅 --debug。
