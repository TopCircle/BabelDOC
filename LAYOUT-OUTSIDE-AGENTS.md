# 外部 agent 任务：三个未填充范式

你是维护 BabelDOC 布局分支的执行 agent。只做分配给你的那一份。先核对当前代码，再改。不要把推断当成用户授权。用户说「过」才表示那一页或那张源框收下了。你自己不要说「过」，也不要宣布页面完成。

仓库：`/Users/yun/workspace/BabelDOC-layout-paradigms`  
分支：`plan/layout-paradigms-20261008`  
远程：`git@github.com:TopCircle/BabelDOC.git`  
开工前 `git pull`。只在这个目录改产品代码。不要改 Grok worktree，不要改 Nextcloud 那份 BabelDOC。

## 放出去的只有这三份

| 编号 | 模块 | 现在的状态 |
| --- | --- | --- |
| A | `hang/repeated` | pause（填充过不了，已挂起）。源框已收下。 |
| B | `rect/full_column` | 已收下（双页 p2, p6 用户已过）。已完成。 |
| C | 六个 `mark/*` | 认领已有。样例页未指定。填充都没写。 |

除此之外的范式都不要动。已收下的包括 `hang/shallow`、`hang/deep`、`bow/right_inset`、`bow/right_bulge` 的 Energy Orgasms 第 4 页、`step/right_spur`、`taper/left_pin`、`taper/right_pin`。`center/axis` 的第 72 页左栏已收下。

## 共同规则

- 只改分配给你的模块和它的测试。一个认领不得调用另一个认领。排版不得按范式名字分支。
- 不要改认领规则、`THRESHOLD`、`FOUNDING_PARADIGMS`、`stand_down`。`rect/full_column` 是奠基范式，低于阈值时后面的形状会让位。
- 不要改 `seal.py`、术语表 CSV、`GROK_BOT_HANDOFF.md`、`docs/CURRENT-STATUS.md`、`docs/README.md`。
- 不要改 `tmp/layout-corpus`、`tmp/layout-index`、`tmp/layout-index-gen2`。不要重扫，不要新造一页。
- 不要改 OneDrive 里的原书。渲完核对源 PDF 的 mtime 没变。
- 不要 `--ignore-cache`。不要 commit，不要 push，不要改版本号。
- 填充沿用 `hang/deep`：每一行留下扫描到的 `(x0, x1)`，有第三个数就留下 top。不要另写一套行距或字号。
- 接上填充后，把模块名加进 `tests/test_line_edges.py` 的 `test_only_wired_modules_carry_a_fill`。用合成行测，测试不打开 PDF。
- 中文短回复，三段：做了什么，下一步看什么，只有真要决定时才问。

书根目录：`/Users/yun/OneDrive/Documentos/Books/Gabrielle Moore/`。  
印刷页 = `page_index + 1`。`--pages` 用印刷页。  
双页是左英右中，1224×792。新渲放到新目录，不要覆盖已有双页和源框。

渲一页：

```bash
cd /Users/yun/workspace/BabelDOC-layout-paradigms
PYTHONPATH=/Users/yun/workspace/BabelDOC-layout-paradigms \
  /Users/yun/Nextcloud/Project/PDFMathTranslate-next/BabelDOC/.venv/bin/pdf2zh_next \
  --config-file ~/.config/pdf2zh/oa-deeplx.toml \
  --pages <印刷页> \
  --output tmp/fill-<模块短名>/<书>-p<印刷页> \
  "<原书.pdf>"
```

样例从 `topics` 不读。规则写在这里：

1. 本提示已经写了页，就用这页。不要换书。
2. 没写页的，读 `tmp/layout-index-gen2/blocks.jsonl`。只要 `status` 为 `matched` 且 `paradigm` 等于本模块的行。两本书各取一块。优先残差 0、行数多、坐在页中。
3. 索引没有这个名字，不要重扫，也不要编一页。

开一个还没有源框的模块：先画两张源框，停下来等用户看。用户没有说「过」之前不要填充，不要渲双页。源框画法与 `tmp/paradigm-map/hang-deep-magic-hands-p10.pdf` 相同：命中块的每一行用蓝色框 `(0.10, 0.35, 0.95)`、线宽 0.9；同页其他索引行用灰框 `(0.25, 0.25, 0.25)`、线宽 0.4；行高 15.28pt；索引的 y 是自下向上的顶，fitz 顶 = 页高 − y。标签用 7pt，写在块上方，例如 `hang/repeated 0.00 23 lines`。源框同时存 pdf 和 png，放在 `tmp/paradigm-map/`。不要覆盖已有文件。

## A. `hang/repeated`

状态：**pause（填充过不了，已挂起）**。源框已收下，暂不渲双页。

只改：

- `babeldoc/format/pdf/document_il/utils/layout_plan/paradigms/hang/repeated/__init__.py`
- `tests/test_line_edges.py` 里把 `hang/repeated` 加入已接线集合，并加一条合成行测试

不要改 `hang/shallow`、`hang/deep`，也不要改 `outline.hang`。

形状：正文行不止一次回到左缘，缩进只有一档。认领已经是 `hang(edges, lines, "repeated")`。

源框已收下，不要重画：

- `tmp/paradigm-map/hang-repeated-hot-licks-p39.png`
- `tmp/paradigm-map/hang-repeated-mastering-her-g-spot-p107.png`

直接写填充，然后渲这两页，各放一个新目录：

- Hot Licks `Hot Licks/hot-licks-module4.pdf` 印刷页 39（`page_index` 38，块 `130f30db4200f241`，23 行，残差 0，缩进 18pt）
- Mastering Her G-Spot `Mastering Her G-Spot/Mastering Her G-Spot.pdf` 印刷页 107（`page_index` 106，块 `e7d78ace2a0426db`，23 行，残差 0，缩进 18pt）

渲完用 venv 里的 fitz 核对：日志里这两块仍是 `hang/repeated`、残差 0；中文在右半页；每一行的左缘跟着扫描到的那一档，没有被拉成整栏。源 PDF 的 mtime 保持 `1395679366.0` 和 `1790945197.7540257`。把两份双页的路径交给用户看。

## B. `rect/full_column`

只改：

- `babeldoc/format/pdf/document_il/utils/layout_plan/paradigms/rect/full_column/__init__.py`
- `tests/test_line_edges.py` 里把 `rect/full_column` 加入已接线集合，并加一条合成行测试

不要改 `rect/light_column`。不要把 `THRESHOLD` 从 1.0 改掉。不要把它移出 `FOUNDING_PARADIGMS`。

形状：左右缘都落在 1pt 以内。满行少于两行不是它。短尾去掉之后右缘仍有台阶，也不是它。

样例只用这两页，不要换书：

- `Bigger & Deeper/Bigger & Deeper.pdf` 印刷页 2（`page_index` 1，块 `bfada19375a1da0f`）
- `Deep Anal Penetration/Deep Anal Penetration.pdf` 印刷页 6（`page_index` 5，块 `3d3a1a86e2a93d9c`）

先画两张源框，停下来等用户看。用户没有说「过」之前不要填充，不要渲双页。源框文件名：

- `tmp/paradigm-map/full-column-bigger-deeper-p2.png`
- `tmp/paradigm-map/full-column-deep-anal-penetration-p6.png`

## C. 六个 `mark/*`

这一份包含下面六个，不要拆开，也不要改别的范式：

| 模块 | 形状 | 索引命中 |
| --- | --- | --- |
| `mark/bullet_hang` | 圆点悬挂，后面的行共用一档缩进 | 563 |
| `mark/bullet_plain` | 圆点，左缘是直的 | 103 |
| `mark/bullet_repeated` | 多条圆点共用一块、一档缩进 | 24 |
| `mark/serial_hang` | 序号悬挂，后面的行共用一档缩进 | 307 |
| `mark/serial_plain` | 序号，左缘是直的 | 234 |
| `mark/serial_repeated` | 多条序号共用一块、一档缩进 | 6 |

只改这六个 `__init__.py`，以及 `tests/test_line_edges.py` 里对应的接线名和合成行测试。不要改 `outline.marked`。不要把 en dash 写进 `is_bullet_point`、`BULLET_POINT_PATTERN` 或 `LIST_MARKER_RE`。

每个模块从 gen2 取两本书。先画源框，十二张一起交给用户看。用户没有说「过」之前不要填充，不要渲双页。源框放在 `tmp/paradigm-map/`，文件名用模块短名、书名和印刷页，不要覆盖已有文件。

## 不要放出去

这些已经有填充，或双页已经收下。外部 agent 不要打开它们：

`rect/light_column`、`rag/right_edge`、`rag/left_edge`、`rag/deep_right`、`step/right_upper_wide`、`step/right_lower_wide`、`step/right_spur`、`bow/right_inset`、`bow/right_bulge`、`taper/left_pin`、`taper/right_pin`、`both/wider_below`、`center/axis`、`hang/shallow`、`hang/deep`。
