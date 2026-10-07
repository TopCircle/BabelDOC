# 放置范式评估

日期：2026-10-08。脚本：`tools/eval/placement_paradigm_score.py`。只读行框，调用正式的 `select_paradigm`，不翻译，不写盘。

```bash
python tools/eval/placement_paradigm_score.py --en PATH --zh PATH --pages 19,23,44
```

每一页一行：`page paradigm_guess left_mode right_mode short_interior taper`。文件不存在时退出码 2。页宽 ≥ 1000 的对页打印 `spread`，不送进分类器。

书在本机 Gabrielle Moore 目录，不进 git。根目录：`/Users/yun/Library/CloudStorage/OneDrive-Personal/Documentos/Books/Gabrielle Moore`。

## 打开这些页

- 矩形参照：`Orgasmic Addiction/Orgasmic Addiction.no_watermark.zh-CN.mono.pdf` 第 44 页正文。中文正文左缘与英文同一栏，中间行到达该栏右缘，短行只出现在段末。英文对照：`Orgasmic Addiction/Orgasmic Addiction.pdf` 同一页。
- 锥形参照：同一中文单语第 19 页「主动掌控」。右缘钉住，左缘逐行内收。脚本里这一段应为 `shaped_pocket`，`taper` 为 1。
- 引语参照：同一中文单语第 23 页。大字块与右栏是两个区域，都不该是 `shaped_pocket`。
- 回归参照：0.6.4.95 OA dual（中文在左）。Canonical 路径见 `docs/CURRENT-STATUS.md`：`Anal Pleasure For Her/Orgasmic Addiction.no_watermark.zh-CN.dual.pdf`。第 19、59、91 页。p19 尖端仍右钉，p59 正文左缘仍在原稿栏，p91 引文与旁栏不重叠。数字以 `CURRENT-STATUS.md` 已写的测量为准，不抄进分类器。
- 反例：`Vagina Masterclass/Vagina Masterclass.pdf` 第 8 页。侧图使整页左缘下移，但每个项目自己不满 4 行锥形。任一项目被标成 `shaped_pocket`，或整页被合成一个 `shaped_pocket`，评估记失败。第 6、9 页的重复词列为切段问题，本计划不判放置失败。

## 通过条件

- 第 44 页正文 `paradigm_guess` 为 `rect_reflow`，`taper` 为 0。短行计在段末，`short_interior` 不为正文中间行的主项。
- 第 19 页锥形段 `shaped_pocket`，右缘 `pinned`，`taper` 为 1。已确认的锥形仍用原来的左钉或右钉，本评估不要求改钉向。
- 第 23 页引语与正文都不是 `shaped_pocket`。
- Vagina Masterclass 第 8 页没有 `shaped_pocket`。
- 对页、整页图、坏编码不在本脚本的通过条件里。对页只打印 `spread`。

## 纠正记录

人工判定和脚本不一致时，追加一行 JSON，不改代码：

```json
{"features": {"lefts": [], "rights": [], "role": "body"}, "chosen": "rect_reflow", "correct": "shaped_pocket", "page": "oa-zh-19"}
```

字段是 `features`、`chosen`、`correct`、`page`。只追加。下一轮计划再决定要不要把这些例子收进分类器。
