# tests/repro — Layout digest regression infrastructure

Repro 基建（Layout-First P0 前置，见 `docs/layout-first-coding-plan.md` §2，
视觉验收见 `docs/visual-layout-acceptance.md`）。
目标是给排版行为一个可提交、可对比的**几何指纹门槛**：任何改变排版
几何的改动都必须让 digest Δ=0，否则 CI/本地对比失败；V1–V5 视觉验收
则把"锚点对位/间距/绕排/内容/结构"变成可自动化的页面断言。

## 目录

```
tests/repro/
├── README.md                       # 本文件：生成/对比/更新 golden 用法
├── driver.py                       # 参数化 CLI，跑完整 babeldoc 流水线
├── synth_page.py                   # 合成验收页（title+wrap_column+chrome+body）
├── digest.py                       # canonical sha256 + fingerprint sha，Δ=0 判定
├── visual_layout_check.py          # V1–V5 视觉版式验收断言（新增，P2 验收基建）
├── test_synth_digest_stable.py     # 默认运行的稳定性测试（+ 快速单测）
├── test_visual_layout_check.py     # V1–V5 断言逻辑单测（合成页 + 负例）
└── golden/
    ├── synth_layout.json           # 合成页 digest 金样（CI 默认对比对象）
    ├── en_p19_blocks.json          # p19 原版 EN 几何参考（固定验收页）
    └── en_p82_blocks.json          # p82 原版 EN 几何参考（固定验收页）
```

## 概念

- **canonical digest**：对 typsetting 摘要 `pages` 做 sort_keys + 紧凑
  JSON 序列化后的 sha256（`digest.canonical_sha256`）。摘要逐段含
  `box`、`scale`、`optimal_scale`、`line_widths[]`。
- **fingerprint digest**：`il_layout_fingerprint` 对排版后内存
  Document 的**纯几何** sha256（只含 page/debug_id/char box，3 位小数）。
- **Δ=0 判定（默认 CI）**：canonical sha 一致 **且** 先验
  （`paragraph_finder`）debug_id 集合一致。
- **fingerprint（默认 advisory）**：全页 `il_layout_fingerprint` 含
  DocLayout/LayoutParser stub 几何，跨 ONNX 提供方/机器易漂。默认失配只
  打 `WARN`；本地深查加 `--strict-fingerprint` 才硬失败。
- **行宽数据源**：一律从 `typsetting.json` 的 `pdf_character` 按 y 聚类
  重算（`driver.compute_line_widths` / `visual_layout_check.line_clusters`）。
  **禁止**使用 `reference_metrics.per_line_widths`（plan §7 数据源规则）。
- **debug_id 确定性**：BabelDOC 的 `ParagraphFinder` 用 `random.choice`
  生成 base58 debug_id；为满足"先验 debug_id 集合不变"，driver 在
  `translate()` 前后固定 `random` 种子（`REPRO_RANDOM_SEED=0`，调用后恢复
  原状态）。不要改动该种子，否则金样会失配。

## V1–V5 视觉版式验收（`visual_layout_check.py`）

把 `docs/visual-layout-acceptance.md` 的五条验收维度变成每页每项的
pass/fail 断言。输入：一个 run-dir（`typsetting.json` +
`paragraph_finder.json` + `layout_intent.json`）+ 原版 EN 几何参考
（`golden/en_pXX_blocks.json`）。输出：结构化报告（每页：每项 status +
数值 + 阈值）。p19 / p82 是固定验收页。

| 项 | 断言 | 阈值 |
|---|---|---|
| V1.anchors | 章/节标题顶、正文首行顶 vs EN（run 取段落 box 顶 `box.y2`） | \|Δy\| ≤ 4 |
| V2.gap | 大标题→正文 ink gap vs EN（`title_ink_bottom − first_body_box_top`，EN 参考 = 管线自身 `gap_contract`，golden 直测仅作 sanity WARN） | \|Δ\| ≤ 2 |
| V3.wrap_right | 绕图行右缘 vs design 右缘（`right_fixed` wrap 的 `design_box.x2`） | ±0.5 |
| V3.orphan | 行宽 < 1.6×字号（末行豁免） | 无孤行 |
| V3.font_scale | 有效字号（font_size×scale）≥ min_scale×原版字号 | ≥ |
| V4.repeat | 译文字符序列无同句连续重复 ≥2（含同行重复） | 无 |
| V4.dangling | 行首不得是句末标点、行末不得是开括号、不得纯标点 | 无 |
| V5.callout | callout 句子不得与主文句子重复（一一对应）；callout 数 mismatch 仅 WARN | 无重复 |
| V5.header | 页眉区（页顶 200pt 内）chrome 不得含中文（skip 生效） | 无 CJK |

### 用法

```bash
# 单跑一个已有 run 的 V1–V5 检查（不重跑流水线）
python tests/repro/visual_layout_check.py \
    --run-dir /path/to/run \
    --en-reference tests/repro/golden/en_p19_blocks.json

# JSON 报告（给脚本/CI 解析）
python tests/repro/visual_layout_check.py \
    --run-dir /path/to/run --en-reference tests/repro/golden/en_p82_blocks.json --json

# 挂在 digest 上（advisory；--visual-gate 才让 FAIL 改变退出码）
python tests/repro/digest.py \
    --golden tests/repro/golden/oa_p19_typsetting.json \
    --run-dir /path/to/run --visual-check --visual-gate
```

- `--visual-check`：digest 对比后追加 V1–V5 报告；EN 参考默认按 run 页号
  自动挑选 `golden/en_p19_blocks.json`（run key `18`）或
  `en_p82_blocks.json`（run key `81`），也可用 `--en-reference` 显式指定。
- 默认 advisory：visual FAIL 只打印，不改 digest 退出码（Δ=0 gate 语义
  不变）；加 `--visual-gate` 才在任一断言 FAIL 时退出 1。
- 合成页（page key `0`）没有 EN 参考 → visual check 自动 SKIP，不打扰
  CI 默认 job。

### EN 参考 golden 生成（p19/p82）

`en_p19_blocks.json` / `en_p82_blocks.json` 从原版 PDF 提取块/行位置：
`top`/`bottom` 为 PDF y-up 点（`page_height − y0` / `page_height − y1`）。
`lines` 是 pymupdf 提取的原始行簇；`anchors` 是按验收定义手工锚定的
标题/正文首行；`invariants` 存 EN 大标题→正文 gap、绕图右缘、callout 数、
各角色原版字号。

生成命令（需原版 PDF；`pymupdf` 已在 `.venv`）：

```bash
python - <<'PY'
import pymupdf, json
PDF = "/path/to/Orgasmic Addiction.pdf"   # 原版 EN
doc = pymupdf.open(PDF)
for pno in (19, 82):
    page = doc[pno - 1]
    H = page.rect.height
    lines = []
    for block in page.get_text("dict")["blocks"]:
        if block["type"] != 0:
            continue
        for line in block["lines"]:
            spans = line["spans"]
            if not spans or not "".join(s["text"] for s in spans).strip():
                continue
            lines.append({
                "top": round(H - min(s["bbox"][1] for s in spans), 1),
                "bottom": round(H - max(s["bbox"][3] for s in spans), 1),
                "x0": round(min(s["bbox"][0] for s in spans), 1),
                "x1": round(max(s["bbox"][2] for s in spans), 1),
                "font_size": round(max(s["size"] for s in spans), 1),
                "text": "".join(s["text"] for s in spans),
            })
    lines.sort(key=lambda t: (-t["top"], t["x1"]))
    # 再人工把 lines 里对应行锚进 anchors / invariants（见现有 golden 结构）
    print(pno, len(lines), "lines")
PY
```

`anchors` / `invariants` 是**按验收定义人工锚定**的（自动提取无法可靠判
角色）；改动验收页时应先核对 `lines`，再更新锚定值与数值。

## 常用命令

### 1. 生成/刷新 golden（合成页，CI 默认验收对象）

```bash
# 首次生成或有意刷新
python tests/repro/digest.py \
    --golden tests/repro/golden/synth_layout.json \
    --update-golden
```

`--update-golden` 会跑完整流水线（需要 assets 缓存）并把结果写回金样。
金样自校验：`digest_sha256 == canonical_sha256(pages)`。

### 2. 对比（Δ=0 判定）

```bash
# 默认：跑合成页并与金样对比（CI layout-repro job 同款命令）
python tests/repro/digest.py --golden tests/repro/golden/synth_layout.json

# 只对比一个已跑过的 run，不再重跑流水线
python tests/repro/digest.py --golden tests/repro/golden/synth_layout.json \
    --run-dir /path/to/run-dir

# 本地 OA p19（固定验收页，需 OA 原件与对应 map）
python tests/repro/digest.py \
    --golden tests/repro/golden/oa_p19_typsetting.json \
    --pdf "/path/to/Orgasmic Addiction.pdf" \
    --pages 19 \
    --working-dir /tmp/oa --out-dir /tmp/oa/out \
    --map-json /path/to/oa_p19_map.json \
    --translator fixedmap \
    --header-height 160 --footer-height 70 \
    --visual-check
```

失败时打印逐段 diff（新增/删除 debug_id、box/scale/line_widths 变化、
fingerprint 失配），退出码 1。

### 3. driver 单独使用

```bash
python tests/repro/driver.py \
    --pdf path/to/page19.pdf --pages 19 \
    --working-dir /tmp/run --out-dir /tmp/run/out \
    --map-json map.json --translator fixedmap
```

- `--translator {fixedmap,identity}`：两者都复用
  `babeldoc.translator.fixed_map_translator.FixedMapTranslator`；
  `identity` 忽略 `--map-json`（纯透传），`fixedmap` 使用精确匹配映射。
- `--map-json`：JSON 对象 `{"英文原文": "中文译文", ...}`。
- 产物：mono PDF（`no_dual=True`）+ `<working-dir>/repro_typsetting_summary.json`
  （canonical 摘要 + fingerprint + 先验 debug_id 集合），以及
  `typsetting.json` / `paragraph_finder.json` / `layout_intent.json`
  （`--debug` 固定开启，V1–V5 检查的数据源）。

### 4. 运行测试

```bash
# 默认跑（含完整流水线的 test_synth_digest_stable，需 assets 缓存；
# 以及不依赖流水线的 test_visual_layout_check.py）
HOME=<assets-cache-home> TMPDIR=<tmp> .venv/bin/python -m pytest tests/repro/ -q
```

## 何时更新 golden

仅在**有意**改变排版行为（例如 Layout-First P1+ 合入、修复排版 bug）时
用 `--update-golden` 刷新。任何未预期的 digest 变化都应先诊断再刷新；
不要在调试过程中随手覆盖金样。V1–V5 断言数值来自 run-dir 调试 JSON 与
EN 参考，与 digest 金样独立；若修复了 p19/p82 的版式问题，报告里对应项
应从 FAIL 翻绿，而 `en_pXX_blocks.json` 的锚定值本身不应随手改动。

## CI

`.github/workflows/checks.yml` 追加了**可选** `layout-repro` job：
`workflow_dispatch` 或 PR 带 `layout` label 时触发，复用 assets cache
（key `babeldoc-assets-<hash>`），命令即上文 §2 的默认对比命令。默认
`checks` job 不跑该 job；`pytest tests/` 会包含 `tests/repro/` 的默认测试。
