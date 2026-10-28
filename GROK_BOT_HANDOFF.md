# BabelDOC — 当前状况（2026-10-28）

**布局树:** `/Users/yun/workspace/BabelDOC-layout-paradigms` · 分支 `plan/layout-paradigms-20261008`
**版本:** `0.6.4.95`（`babeldoc/const.py` 与 `pyproject.toml`，未 bump）  
**main:** `/Users/yun/Nextcloud/Project/PDFMathTranslate-next/BabelDOC` 在 `398275a`。当前 Grok worktree 同一提交。产品改动只进布局树。`/Users/yun/workspace/BabelDOC` 已不在。  
**本文件是当前操作员入口。** 换账号粘贴全文是仓库根目录 `GROK_BOT_HANDOFF.md`。两份冲突时以快照日期更新的一方为准，并立刻同步另一份。不要从 `docs/archive/` 排期。`docs/PLAN-INDEX.md` 这次未改。

## 2026-10-28 — 轮廓约束抑制伪列表悬挂与 mark/serial_plain 范式落地

1. **轮廓约束抑制假列表悬挂 (`typesetting.py`)**：
   - 之前 `_numbered_list_hang_inset` 仅在 `levels[1].left > levels[0].left + 1.0`（存在悬挂）时返回 0.0；而对于 `mark/serial_plain` / `mark/bullet_plain` 等原生平直列表（`levels[1].left == levels[0].left`），因未满足该分支条件而错误穿透执行了通用列表悬挂计算，强制在折行添加了 10.5pt 的假悬挂缩进；
   - 调整为只要段落显式附带 `line_edges is not None` 轮廓约束，即严格遵照轮廓给定的左缘（直边或台阶），抑制额外的启发式悬挂，使直边序号列表折行 100% 保持在左缘齐平。
2. **自动化测试保障 (`tests/test_layout_plan.py`)**：
   - 增加对 `line_edges` 存在时抑制 `_numbered_list_hang_inset` 假悬挂的断言，确保直边列表不发生多余位移。
3. **双语试页核验与过关 (`mark/serial_plain`)**：
   - 样本 1：《Forbidden Female Fantasies》第 29 页（`a. Plan your fun...` 长文本列表项），11 行中文全部严格左对齐于 `726.0 pt`，残差 0.00，平直度完全还原英文，Circle 确认「过」；
   - 样本 2：《Mastering Her G-Spot》第 55 页（`1.` ~ `8.` 步骤序号列表），首行统一严格对齐于 `726.4 pt`，排版规整，Circle 确认「过」。

## 2026-10-28 — 复合列表编号正则增强与 mark/serial_repeated 范式落地

1. **复合列表编号（`1.)` / `8.)` / `1.）` / `a.)`）支持与悬挂缩进恢复 (`list_marker_repair.py`)**：
   - 之前 `LIST_MARKER_RE` 与 `TRAILING_LIST_MARKER_RE` 仅匹配单字符后置标点（`[\.．。、\)]`），遇到点加括号的复合序号（如 `8.)`）时仅截取 `8.`，导致括号 `)` 被当作正文首字推移至缩进位置而与数字割裂；同时导致 `_list_marker_hang_width` 计算缩进时漏计括号与空格宽度（仅 8.3pt），使续行对齐在括号下方而非正文下方；
   - 将数字及字母正则增强为支持 `(?:[\.．]\s*[\)）]|[\.．。、\)])`，复合编号整体保留在行首一体排版，且折行精确挂接在正文字符正下方。
2. **自动化测试与回归保障 (`tests/test_paragraph_alignment.py`)**：
   - 新增 `test_layout_compound_dot_paren_numbered_list_hang_indent`，自动化验证复合序号 `8.) ` 不撕裂、正文字符首字索引识别准确、折行悬挂缩进完全覆盖标记宽度。
3. **双语试页核验与过关 (`mark/serial_repeated`)**：
   - 样本 1：《Female Orgasm Secrets Revealed》第 75 页（`1) ... 2) ...` 共用区块列表），折行精确悬挂 18.0pt，避头尾正常，Circle 确认「过」；
   - 样本 2：《Last All Night Vol 2》第 37 页（`1.) ... 8.) ...` 复合编号列表），复合序号完整无撕裂，条目 5 单段完整合流无纵向断层，续行精准悬挂对齐，Circle 确认「过」。

## 2026-10-28 — 标点避头尾修复、小标题间距与跟随解耦、圆点字形尺寸与 mark/bullet_repeated 范式落地

1. **中文行首禁则全面覆盖 (`cjk_kinsoku.py` / `typesetting.py`)**：
   - 将常用半角标点（`.`, `,`, `)`, `"` 等）纳入 `_CJK_LINE_START_FORBIDDEN`，避免 CJK 混排时半角符号孤立出现在行首；
   - 在 `typesetting.py` 自动折行检查中加入 `first_on_next` 前瞻探测：折行点若使下一行以行首禁止符开头，则自动向后回拉前置字符至下一行，彻底根除行首出现孤立标点符号。
2. **小标题上方间距保证与正文解耦 (`vertical_gap.py`)**：
   - 增加 `find_content_above` 向上寻找最近非保护段落，计算 `deficit_above = target_gap_above - zh_gap_above`；
   - 当小标题因上方列表扩展而与上方内容拥挤时，推动小标题向下移入下方预留充足的留白区（`dy_above`），且仅推移小标题本身而不强行推挤下游正文，消除《Blown Away》第 15 页 `要吞下还是不要吞下` 与上方列表项紧贴（间距 -0.9pt）且脱离下方正文（间距 43.1pt）的问题，修复后上方留白 15.7pt，下方间距 6.0pt。
3. **Ubuntu 字体特征识别与中文圆点字形恢复 (`face_traits.py` / `fontmap.py` / `il_translator.py`)**：
   - `_SANS_TOKENS` 增加 `"ubuntu"`，防止 `Ubuntu-Light` / `Ubuntu-Bold` 错误降级为衬线宋体；
   - 针对列表项目符号（`•·‧●▪▫◦‣⁃`），强制映射到无衬线黑体字族（`SourceHanSansCN`），字号与笔画粗细完美还原英文字体（直径从 1.63pt 恢复至 2.97pt ~ 3.58pt）；
   - 在翻译阶段正则清洗 MT 偶发的连字符 `-` / 中点替换，恢复源文本原生圆点。
4. **公式单元特殊项目符号悬挂缩进支持 (`typesetting.py`)**：
   - 在 `_is_leading_bullet` 中对保留为公式单元（`formular`）的符号字族（如 Webdings `\x12`、PUA `\uf643`）字符编码进行 `_BULLET_HANG_CHARS` 穿透识别；
   - 确保特殊列表符号不仅完整保留，而且第 2 行起精准应用 14.88pt 悬挂缩进，修复《Oral Fingering Fantasy》第 7 页列表续行未缩进问题。
5. **双语试页核验与过关**：
   - 样本 1：《Blown Away》第 15 页（小标题间距与圆点大小）Circle 确认「过」；
   - 样本 2：《Oral Fingering Fantasy》第 7 页（13 项 Webdings 列表与悬挂缩进）全部验证通过。

## 2026-10-27 — 悬挂列表项角色阻断修复与 mark/serial_hang 范式落地（commit e5e6d72）

1. **列表项段落角色阻断修复 (`rect_flow_stack.py`)**：
   - 之前在 `_role_of` 中仅对 `role == "formula"` 的列表项清理 tag，而当解析或意图标注产生 `role == "list"` 且首行具备列表特征 (`_opens_as_list`) 时，由于 `_GEOMETRY_ROLES` 严密限制不含 `list`，导致该段落因 `protected_role` 被拒绝进入 list_flow；
   - 扩展判定为 `if (role == "formula" or role == "list") and _opens_as_list(paragraph): return None`，使候选段落能够顺利由 `list_flow` 进行 marker 识别与悬挂阶梯派发；
   - 同时严格保留 `geometry.py:_GEOMETRY_ROLES` 对无 marker 纯文本的保护，杜绝无 marker 列表被 `rect_flow` 误收割。
2. **范式落地与双语核验 (`mark/serial_hang`)**：
   - 样本 1：《Last Longer Tonight》第 19 页（block `96460e`，`c)` 挤压法）：首行左缘 `740.0 pt`（`128.0 + 612.0`），续行严格缩进至 `758.0 pt`（`146.0 + 612.0`），悬挂缩进量精准为 **18.0 pt**，行高 `16.8 pt`，零碰撞；
   - 样本 2：《Orgasmic Rocket Fuel》第 12 页（block `a0448f`，`b)` 确定肌肉位置）：首行左缘 `740.0 pt`，续行缩进至 `758.0 pt`，悬挂量精准为 **18.0 pt**，标点避头尾与分行规整；
   - 真实双语渲染图及裁切对比已由 Circle 确认「过」。
3. **测试与质量把关**：
   - `ruff check` 与单元测试（包括 `test_layout_plan.py`、`test_style_marker_recover.py` 等 101 项测试）全部通过。

## 2026-10-27 — 字母目录项粘连错位修复、标题排除区误建消除与列垂直间距级联推移（commit 2ad6b6f）

1. **字母序列粘连拆分与全角句点规范化 (`list_marker_repair.py`)**：
   - 扩展 `_MID_OPTION_SPLIT_RE` 与 `_MID_OPTION_LOOSE_RE` 匹配全字母范围 `[a-zA-Z]` 及 `B.。大`、`E.。现实检查` 等全半角混排句号变体；
   - 增加 `paragraph_opens_as_list(para)` 判定，涵盖首字符为图形符号圆点（Wingdings / Symbol）与字母列表项的段落；
   - 修复后《Bigger & Deeper》第 4 页 TOC 目录项 A..G 全部 7 个选项严格左对齐于 `x0 = 648.1 pt`，消除粘连和向右半页错位跳跃。
2. **章节标题排除区误判消除 (`exclusion_zone.py` / `layout_helper.py` / `layout_intent_extractor.py`)**：
   - 章节标题、TOC 目录项与列表项一律禁止建立 quote / pull_quote 排除区；
   - 消除《Double Fingering Delight》第 4 页 `Part 1: Introduction` 产生的伪 quote 排除框对下方正文的水平横向推挤。
3. **展示标题垂直间距与列内跟随级联 (`vertical_gap.py`)**：
   - 在 `is_display_title` 中增加中文章节标题模式（`第\s*\d+\s*[部分章节卷]|技巧\s*\d+`）与字号阈值保护；
   - 在 `enforce_title_body_gaps` 推移段落时，增加同列下游段落跟随级联（follower cascade），首项与全部 24 个列表项及后接 Part 2 协同推移；
   - 消除首项与次项碰撞叠压问题，修复《Double Fingering Delight》第 4 页标题与列表项之间过小的垂直间距。
4. **范式与测试**：
   - `mark/bullet_plain` 双语试页核验完成；
   - `ruff check` 与单元测试全部通过。

## 2026-10-26 — 悬挂列表双重缩进修复、底图贯穿识别与自然参差避让消除（commit 3784e71）

1. **贯穿背景底图识别与栏宽误切排除 (`column_chain.py`)**：
   - 在 `_figure_gap` 增加贯穿底图检测，当文本行跨越图片边界超过 40pt 时，识别为背景层，禁止切分列宽或将整段强行收窄。
2. **文本右侧自然参差收窄误判消除 (`placement_paradigm.py`)**：
   - 严密收紧 `_is_left_pin_taper` 与 `_is_right_pin_taper`，要求内缩步数严格多于外扩步数（`inward > outward`）且具备明确阶梯极值，普通自然参差判定回退为 `RECT_REFLOW / stable_column`，修复《Ten Minute Stamina Boost》p21 第一段假避让。
3. **圆点列表悬挂双重缩进消除与正文基准对齐 (`typesetting.py`)**：
   - 当 `line_edges` 已具备悬挂阶梯时，`_numbered_list_hang_inset` 自动停用冗余偏移，消除第 2 行起叠加缩进；
   - 增加 `_first_body_unit_index` 与 `_line_edges_body_left`，在首行排完标记与空格后对齐正文起点至 `target_body_left`（92.0pt），《Ten Minute Stamina Boost》p21 圆点列表项悬挂完美对齐。
4. **范式与测试**：
   - `mark/bullet_hang` 填充核验通过，175 项排版单元测试 100% 通过。

## 2026-10-26 — 序号乱码修复、首字下沉保护、引言避让与范式技能（commit 53112ab, dee1fdc）

1. **Step 序号倒装与丢字根治 (`drop_cap.py` / `list_marker_repair.py`)**：
   - 增加 `is_drop_cap_candidate` 严密门禁，避免将 `Step 4.` / `Step 6.` 首字母误判为下沉大字抽离导致的 `4. tep S`、`6. tep S` 乱码；
   - 在 `list_marker_repair.py` 中对 `步骤` / `第` 等中文步骤前缀实施保护，禁止将其拆解重组为 `5. 步骤`；
   - 修复后《Forbidden Female Fantasies》p29 步骤标题统一呈现为规范的 `步骤 4.`、`步骤 5.`、`步骤 6.`。
2. **正文与右侧引言（Pull Quote）避让恢复 (`typesetting.py`)**：
   - 恢复 `has_obstacle` 障碍物裁切边界，Step 6 左列正文止于 `x2 = 943.3`，与右侧斜体引言（`x1 = 968.0`）保持 24.7pt 规整间距，零重叠。
3. **CoreML 降级容错 (`doclayout.py`)**：
   - 增加 CoreML 初始化异常捕获，macOS 缓存写入异常时平滑回退至 `CPUExecutionProvider`。
4. **范式与工作流技能**：
   - 《Forbidden Female Fantasies》p29 底部列表项命中 `mark/serial_plain`（残差 0.0）核验通过；
   - 新增 Workspace Skill `.agents/skills/layout-paradigm-workflow/SKILL.md`。

## 2026-10-26 — 序列标题粗体保留、垂直重叠保护与排除区伪标注修复（commit 80ffec9）

1. **粗体样式标记保留 (`normalize_translated_text` / `ILTranslator`)**：
   - 增加 `keep_style_markers=True`，防止富文本格式标记 `〖B0〗` 被过早正则清洗，修复《Oral Rapture》p18 等标题粗体样式在后处理阶段丢失的问题。
2. **段落垂直重叠标题锚点保护 (`typesetting.py`)**：
   - 在 `_resolve_paragraph_vertical_overlaps` 中确立标题/页眉的固定锚点地位，并在反向推移时加入守卫，禁止下方溢出段落将上方标题推入上一节或发生单行黏连。
3. **单行小标题排除区伪标注修复 (`layout_intent_extractor.py`)**：
   - 限制 `Rule 8` 中 `CALLOUT` 判定必须为多行文本（`n_lines >= 2`），防止像《Double Fingering Delight》p4 中的单行章节子标题（如 `Prepping for G-spot Fingering`）误建侧栏 quote 排除区域，从而避免排除区外扩将下方左对齐小标题（`Technique 1`）强行右推到页面中央的假居中问题。
4. **吸附列宽保护 (`typesetting.py`)**：
   - 修正 `_cap_available_with_reference`，当段落吸附回原始左列（`line_start < available_x`）时，保留基于 `ref_w` 的列宽上限，不受右侧障碍物干扰。
5. **测试与验证**：
   - 全部 223 项核心排版测试通过。
   - 真实双语渲染图核对通过并已推送 `origin/plan/layout-paradigms-20261008`。

## 2026-10-20 — step/right_spur 小腿框已过（版本仍 0.6.4.95）

范式试页是 **EN 左 | ZH 右**。下面的 OA 整本 canonical 是另一份产品，**ZH 左 | EN 右**，不要混用，也不要覆盖。

- Erotic Massage《For Better Sex》印刷页 57 的小腿框填充，Circle 于 2026-10-20 说「过」。dual：`tmp/fill-right-spur/erotic-massage-p57-frame3/Erotic Massage For Better Sex.no_watermark.zh-CN.dual.pdf`（546009 字节）。不要覆盖，不要重渲。
- 中文四行、12pt。前两行左缘 102，右端 511.6 与 510.0。照片缩进从「起来时」起，左缘 231，右端 511.2。末行右端 387，不拉满。「接下来」停在 y-down 371.8。距的搁板收到 596.8，「弯曲位置）」停在 614.6。页脚和 URL 仍是英文。
- 未填充的源框也已过，不要重画：`tmp/paradigm-map/right-spur-erotic-massage-p57.png`、`tmp/paradigm-map/right-spur-naughtyfingers-p109.png`。小腿在距框上方，不要为填小腿去改距的填充。
- 同页更早的 dual 留在磁盘上，不是这一次的结果：`tmp/fill-right-spur/erotic-massage-p57/` 以及 `p57-fix`、`p57-clear`、`p57-join`、`p57-fill`、`p57-frame`。
- 两半源行拼起来对上一个轮廓时，字进那个轮廓。用的是 `taper/right_pin` 已有的恒等填充。没有新范式，排版也不按范式名字分支。`seal.py` 未改。`right_pin`、`light_column`、距的填充未重调。
- 审查 f24df175（2 个缺陷、2 条建议）已在 2026-10-20 修完：缺 id 时各自用 `shared-frame-{id(paragraph)}`；没有存下的源行边就不再用框左缘去发明左缘；页门不是 `single_page` 时不装框。`tests/test_indented_sentence_continue.py` 18 项通过。接受的 dual 没有为这次修复重渲。
- 渲染须先 `cd` 到布局树，并在同一条 shell 里 `export PYTHONPATH` 指向该树。`.pth` 指向的是 Nextcloud 主仓。不要传 `--ignore-cache`，不要 cat 翻译日志，不要打印 settings。
- 下一模块是 `bow/right_inset`。还没开始。等 Circle 说「继续」。

同一批已经过、不要覆盖的试页：Erotic Massage 页 22 下半 `tmp/fill-p22-struct/`（引言先停）；`taper/left_pin` 的 `tmp/fill-left-pin/dhdm3-p37/` 与 `oa-p29/`；段距 `tmp/fill-para-seat/dhdm3-p37/`；`rect/light_column` 的 `tmp/fill-left-pin/reverse-cowgirl-p22-dip/`；页 72 `tmp/fill-right-pin/erotic-massage-p72-stitch7/`（503587 字节）；Tantric Touch 页 101 `tmp/fill-right-edge/tantric-touch-p101-face/`；Forbidden Anal Sex 页 6 `tmp/fill-left-edge/forbidden-anal-p6/`；Forbidden Sex Toys 页 28 `tmp/fill-upper-wide/forbidden-toys-p28/`（454288 字节）；Erotic Massage 页 42 `tmp/fill-upper-wide/erotic-massage-p42/`（496406 字节）。

停着、没有过：`center/axis` 引言（`tmp/fill-center-axis/erotic-massage-p22-p72-share/`，先这样，后续再优化）；Erotic Massage 印刷页 34 的 `rag/right_edge`。不要重渲页 34。

## 2026-10-07 — 中段修复已推 main（版本仍 0.6.4.95）

- 大标题用 em 框顶作行高，斜体不再拆成两行。同一基线的后绘段落下移 1.5pt。目录项目符号，以及图形状态整串不同的行，不再并成一段。跨段拉丁连字符在翻译前只接同一栏紧邻的下一段。
- 代码审查通过。OA 与 Vagina Masterclass 未重译。术语表（宫颈、射精、阴阜：阴茎、您/你）未做。
- VPS `pdfmt-next-app` 已按 `80fab28` 重建（2026-10-07）。7870 返回 200。容器内可 import `hyphen_paragraph_merge` 与 `same_baseline`。版本号仍是 0.6.4.95。

## 验证 dual（Circle 整本 · 0.6.4.95 · 已确认）

- **Canonical 路径:** `/Users/yun/Library/CloudStorage/OneDrive-Personal/Documentos/Books/Gabrielle Moore/Anal Pleasure For Her/Orgasmic Addiction.no_watermark.zh-CN.dual.pdf`
- **Producer:** `BabelDOCv0.6.4.95_…` · **121 页** · 页幅 `1224×792`（对页）· mtime **2026-09-07 ~13:17 CST**
- **朝向:** **ZH 左 | EN 右**（`mid=612`）
- **页码映射（121 页）:** 有页脚内容页约 `book_page ≈ pdf_idx + 1`（例：书 p19→pdf[18]，p59→[58]，p91→[90]；「内容」orphan→pdf[119]）
- **旧 dual 勿用:** `…/Orgasmic Addiction/Orgasmic Addiction.no_watermark.zh-CN.dual.pdf` 仍为 **0.6.4.93 / 118 页**。同目录有 symlink `….dual.0.6.4.95.pdf` → canonical，以及 `README-DUAL-PATH-0.6.4.95.txt`
- **证据:** `tmp/oa_w1_deeplx/s31-verify/` · 汇总 JSON：`tmp/oa_w1_deeplx/s31-residual-scan.json`（gitignore）；对照基线 `s29-residual-scan.json`（0.6.4.93，48 MT suspects）

## 仓库卫生（此前）

- `f8cc557`：`docs/CURRENT-STATUS.md` 入口；旧计划 → `docs/archive/`；`tmp/` 清空并 gitignore；根目录 debug 脚本 → `tools/debug/`
- 根目录交接 prompt：`GROK_BOT_HANDOFF.md`（换账号粘贴即可接手；**每次 push 须同步更新**）

## 已完成（wrap / 引文 P0 — s31 复核仍成立）

| 主题 | 结果 | 代表提交 / 版本 |
|------|------|-----------------|
| p19 RIGHT_FIXED 锥形 | **仍好**：tip band x0≈330→456，宽≈240→132 | ~`71ae7bc` … `0.6.4.86` |
| p59 LEFT_FIXED | **仍好**：正文左缘 median **101.87**（目标≈101.9）；与图 gutter 干净 | `f6db1ad` / `0ba4baf` / `c0a0012` |
| p91 引文 vs wrap | **仍好**：callout x0≈54 / x1≈182–197；wrap-body x0 **≈245.3**；无碰撞 | `094371a` … `0f7cc25` / `0.6.4.91` |
| MT 碎屑（全书） | **s31：48→4**（−44）；s29 示例词全部清掉；剩 BDSM×2 / majora / allin — **非系统 P1，不 bump** | s30 scrub + DeepLX `post_clean` / `0.6.4.95` |
| 日志噪音 | 重叠重排 WARNING 汇总；探测类 INFO→DEBUG；默认关 debug | `84981ed` / `0.6.4.93` |

焦点扫视（7/12/19/33/35/59/91）：**系统级 wrap 碰撞 / 锥形 P0 仍清完；无新 P0 排版回归。**

## 运行配置（验证用）

- 脚本：`~/.config/pdf2zh/run_oa_dual.sh`（默认**不加** `--debug`）
- 要排版 dump：`OA_DEBUG=1 ~/.config/pdf2zh/run_oa_dual.sh …`
- 直播 toml：`~/.config/pdf2zh/oa-deeplx.toml` → `debug = false`
- DeepLX 生产脚本 / glossary：`~/.config/pdf2zh/`（及 Nextcloud 同步副本）；**不在** BabelDOC git 内
- 输出目录：`tmp/oa_w1_deeplx/`（本地临时，已 gitignore）

## 遗留问题（按优先级 · s31 2026-09-07）

### P1

1. **重叠修正 retypeset 失败根因** — 静态 dual 不可见；日志已收敛；dual/OCR 路径会 skip。仍为潜伏系统项。

### P2 / backlog

2. **Latin MT 碎屑（s30/s31 已大幅清）** — 全书 suspects **4**（s29 为 48）。剩余：`BDSM`×2（外来语，或可接受）、`majora`(pdf96)、`allin`(pdf107)。s29 示例词（enjoyable/inandout/vag/Stim/her/enemas/…/commented）**已全部清除**。非系统，不 bump。
3. **短末行微瑕** — **仍在**：p59 tip「度。」(pdf 58)、p91 callout「世界。」(pdf 90)、近末「内容」(pdf 119)
4. **p19 tip-band 可选加深** — 锥形可接受；尖端宽平台≈132；再填有碎屑风险
5. **PR-B1i 红色** — 装饰/色策略；ZH 章题多为黑，红多在 EN part 头 / 小节题 / callout（源设计 `#d12027`）

### 启发式备注（勿当 P0）

6. **wide_on_photo 矩形 bbox** — 轮廓绕排走廊会被算进图 bbox，中心点命中≠真叠字；p19/p59 目视 gutter 干净。需光栅确认才升级。

## 刻意不从旧文档排期

以下已迁到 `docs/archive/`，仅作历史证据，**不要**当工作队列：

- `layout-first-*.md` / `layout-engine-defects.md` / `line-interval-architecture.md`
- `architecture-optimization-plan.md` / `oa-dual-layout-pr-plan.md` / `p1_acceptance_oa.md`

仍有效：`docs/adr/*`、`docs/visual-layout-acceptance.md`（验收标准）、`tests/golden/SCORECARD.md`（冻结项）。
