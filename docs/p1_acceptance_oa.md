# P1 验收：OA dual ink gap（相对 EN）

| 项 | 值 |
|----|-----|
| 日期 | 2026-08-04 |
| 工具 | `python -m babeldoc.tools.p1_ink_gap_accept` |
| ε | 2.0 pt |
| max_jump | 24.0 pt |
| 抽样页 | [3, 7, 12, 19, 33, 40, 73] |

## 0.6.4.52 dual_layout（主验收）

- **status: `pass`**
- summary: `{'scored': 7, 'pass': 7, 'fail': 0, 'fail_clamped': 0, 'skipped': 0}`

| 页 | en_gap | zh_gap | |diff| | deficit | ε-pass | note |
|---:|---:|---:|---:|---:|:---:|---|
| 3 | 9.47 | 8.25 | 1.22 | 0.00 | True | pass |
| 7 | 18.03 | 31.44 | 13.41 | 0.00 | True | pass |
| 12 | 78.03 | 79.34 | 1.31 | 0.00 | True | pass |
| 19 | 18.03 | 29.28 | 11.26 | 0.00 | True | pass |
| 33 | 18.03 | 19.34 | 1.31 | 0.00 | True | pass |
| 40 | 78.03 | 86.55 | 8.52 | 0.00 | True | pass |
| 73 | 18.03 | 18.95 | 0.93 | 0.00 | True | pass |

## 对照 0.6.4.50 dual

- **status: `fail`**
- summary: `{'scored': 7, 'pass': 2, 'fail': 5, 'fail_clamped': 0, 'skipped': 0}`

| 页 | en_gap | zh_gap | |diff| | deficit | ε-pass | note |
|---:|---:|---:|---:|---:|:---:|---|
| 3 | 9.47 | 2.80 | 6.67 | 4.67 | False | fail_short |
| 7 | 18.03 | 31.44 | 13.41 | 0.00 | True | pass |
| 12 | 78.03 | 66.38 | 11.64 | 9.64 | False | fail_short |
| 19 | 18.03 | 29.28 | 11.26 | 0.00 | True | pass |
| 33 | 18.03 | 6.38 | 11.64 | 9.64 | False | fail_short |
| 40 | 78.03 | 73.60 | 4.43 | 2.43 | False | fail_short |
| 73 | 18.03 | 6.26 | 11.77 | 9.77 | False | fail_short |

## Done 判定

按 plan §6 + 工具 `done_rule`：

- **实现**：0.6.4.52 已合 main（gap 首遍 + 受限 enforce + audit）。
- **验收（本抽样）**：`pass` — scored=7 pass=7 fail=0。
- **P1 阶段**：实现 Done + 抽样验收 **pass** → 可进入 plan **P2**。

JSON 明细：

- `docs/p1_ink_gap_accept_oa_dual_layout.json`
- `docs/p1_ink_gap_accept_oa_dual_0.6.4.50.json`
