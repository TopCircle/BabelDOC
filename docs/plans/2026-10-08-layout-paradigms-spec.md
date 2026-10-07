# 版式范式：规格

日期：2026-10-08。基线：`main` `398275a`（0.6.4.95）。  
状态：提案。不进入 `docs/PLAN-INDEX.md`，不改 `docs/CURRENT-STATUS.md`，未接受前不是操作队列。

## 目的

中文按段落盒子重排。盒子切对之后，还要选对「这一块怎么排」。现在缺的是这一层选择：有形状就默认右钉，矩形正文会被排成左缘参差。

目标是最大限度减少后期人工校正。范式按区域标记，模块独立，以后可以加。文档越多，只在纠正被记成范例时才更准。

## 已有代码

`LayoutIntentRole` 已经有 `BODY`、`TITLE`、`PULL_QUOTE`、`CALLOUT`、`CHROME`、`WRAP_COLUMN`、`LIST`、`DROPCAP`、`SECTION_HEADER`。`LayoutIntentExtractor.extract` 在 `StylesAndFormulas` 之后写入 `PdfParagraph.layout_intent`，不进 XML。

缺的是放置策略。`effective_wrap_mode` 在有形状但没有模式时返回 `RIGHT_FIXED`。英文把口袋排满，看不出钉边。中文更短，左缘就散开。

本规格不新建第二套角色名。放置范式从已有 `layout_intent` 加几何里选出来。

## 放置范式

| id | 何时 | 放置 |
|---|---|---|
| `rect_reflow` | 正文矩形栏。左缘稳定，右缘对齐，没有单调内收 | 整段一条流。中间行排满栏宽。只有段末行留短并靠左。行距沿用 `_DEFAULT_LINE_SKIP_CJK = 1.50` |
| `shaped_pocket` | 至少 4 行，左缘逐行内收 ≥ 6pt，右缘波动 ≤ 18pt，或已标记 `LEFT_FIXED` / `RIGHT_FIXED` 且形状是锥形 | 右缘或左缘钉住原稿。每一行排满当前口袋。该块最后一行可以留短并靠左 |
| `keep_current` | 本计划尚未单独立项的角色：引语、列表、章名、居中短句、目录、装饰引号、页眉页脚 | 分类要打上目标 id，放置仍走现有代码。不得套用 `shaped_pocket` |

页眉、页脚、分册名、网址保持英文，沿用现有 skip。不在本计划里翻译。

## 不做

- 不修切段。一段被切成两次翻译时，重复词不会被范式消掉。
- 不处理对页拆分、整页图片、坏 CMap。
- 不把某一页的左缘、字号、空隙写进分类器。验收页的测量只出现在评估文档。
- 不改 `__version__`、`MIN_READABLE_SCALE`（0.55）、`_DEFAULT_LINE_SKIP_CJK`（1.50）。
- 不合并、不部署。基线不含未合并的行对齐栈 `01fb616`。

## 扫描依据

2026-10-08 扫过 Gabrielle Moore 101 个目录、约 100 本英文原稿，每本抽中间页。多数是 612×792 单栏，左缘在 36、60、96、102 之间，规则相同。锥形、侧图、大字引语是页内局部。`The Perfect Trigasm` 等 3 本是 1224 宽对页。约 8 本没有可抽取文字层。`Turn Her On Faster`、`Forbidden Fruit` 抽取为乱码。这些输入问题另立计划。

人工修过的中文单语 `Orgasmic Addiction.no_watermark.zh-CN.mono.pdf` 是矩形栏、锥形、引语的视觉参照。0.6.4.95 的 OA dual（中文在左）是 p19 / p59 / p91 的回归参照。

## 成功标准

- 矩形正文不再因为「有形状」走右钉。
- 已确认的锥形（OA p19 右钉、p59 左钉、p91 引文旁栏）测量保持在 `docs/CURRENT-STATUS.md` 已记录的范围内。
- 新范式是一个模块加一组测试，不改调度函数的签名。
- 低置信度区域使用 `rect_reflow`，并出现在评估输出里。
