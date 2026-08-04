# tests/repro — Layout digest regression infrastructure

Repro 基建（Layout-First P0 前置，见 `docs/layout-first-coding-plan.md` §2）。
目标是给排版行为一个可提交、可对比的**几何指纹门槛**：任何改变排版
几何的改动都必须让 digest Δ=0，否则 CI/本地对比失败。

## 目录

```
tests/repro/
├── README.md                       # 本文件：生成/对比/更新 golden 用法
├── driver.py                       # 参数化 CLI，跑完整 babeldoc 流水线
├── synth_page.py                   # 合成验收页（title+wrap_column+chrome+body）
├── digest.py                       # canonical sha256 + fingerprint sha，Δ=0 判定
├── test_synth_digest_stable.py     # 默认运行的稳定性测试（+ 快速单测）
└── golden/
    └── synth_layout.json           # 合成页 digest 金样（CI 默认对比对象）
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
  重算（`driver.compute_line_widths`）。**禁止**使用
  `reference_metrics.per_line_widths`（plan §7 数据源规则）。
- **debug_id 确定性**：BabelDOC 的 `ParagraphFinder` 用 `random.choice`
  生成 base58 debug_id；为满足"先验 debug_id 集合不变"，driver 在
  `translate()` 前后固定 `random` 种子（`REPRO_RANDOM_SEED=0`，调用后恢复
  原状态）。不要改动该种子，否则金样会失配。

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
    --header-height 160 --footer-height 70
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
  （canonical 摘要 + fingerprint + 先验 debug_id 集合）。

### 4. 运行测试

```bash
# 默认跑（含完整流水线的 test_synth_digest_stable，需 assets 缓存）
HOME=<assets-cache-home> TMPDIR=<tmp> .venv/bin/python -m pytest tests/repro/ -q
```

## 何时更新 golden

仅在**有意**改变排版行为（例如 Layout-First P1+ 合入、修复排版 bug）时
用 `--update-golden` 刷新。任何未预期的 digest 变化都应先诊断再刷新；
不要在调试过程中随手覆盖金样。

## CI

`.github/workflows/checks.yml` 追加了**可选** `layout-repro` job：
`workflow_dispatch` 或 PR 带 `layout` label 时触发，复用 assets cache
（key `babeldoc-assets-<hash>`），命令即上文 §2 的默认对比命令。默认
`checks` job 不跑该 job；`pytest tests/` 会包含 `tests/repro/` 的默认测试。
