# BabelDOC — 当前状况（2026-11-06）

**工作工程:** `/Users/yun/Nextcloud/Project/PDFMathTranslate-next/BabelDOC` · 分支 `main`  
**父工程根目录:** `/Users/yun/Nextcloud/Project/PDFMathTranslate-next`（包含 `BabelDOC`、`PDFMathTranslate-next`、`config`）  
**历史布局树:** `/Users/yun/workspace/BabelDOC-layout-paradigms`（已归档/废弃，工作流与开发已全面迁入 Nextcloud）  
**版本:** `0.6.4.101`（`babeldoc/const.py` 与 `pyproject.toml`）  
**本文件是当前操作员入口。** 换账号粘贴全文是仓库根目录 `GROK_BOT_HANDOFF.md`。两份冲突时以快照日期更新的一方为准，并立刻同步另一份。不要从 `docs/archive/` 排期。`docs/PLAN-INDEX.md` 这次未改。

## 2026-11-06 — 生产填充执行门禁（识别 30 / 已验收 29 / 已启用 29）

这是执行门禁，不是新的样页验收。没有新的 dual，也没有用户重新验收记录。数量沿用既有闭环名单，本条不把任何样页标成重新通过。

- **识别 30**：目录里的范式仍全部 claim，包括挂起的 `hang/repeated`。
- **已验收 29**：2026-11-04 已闭环的 29 项。本条不新增验收，不重开样页。
- **已启用 29**：`ENABLED_SYSTEM_FILLS` 只给这 29 项装生产 fill。`hang/repeated` 命中后记为 `recorded`，不写 `line_edge_links`，也不进入 `shared_contours`。
- 白名单是固定名单，不是“扫到 `fill` 就启用”。未列入的名字默认不进生产填充。

## 2026-11-06 — 列表项悬挂缩进右甩消除、小标题垂向间距防叠、多行大标题缝合与术语纠偏（0.6.4.101）

1. **列表项悬挂缩进误判为侧图绕排（`RIGHT_FIXED`）与续行右甩消除 (`line_interval_plan.py` / `figure_wrap.py` / `layout_helper.py` / `list_marker_repair.py`)**：
   - **根因**：
     - Gabrielle Moore 系列图书（《Fingering Fetish》、《Toys for Tits》等）普遍使用字符 `\x12`（DC2, Webdings/Ubuntu-Bold）作为列表项目符号；旧版 `BULLET_POINT_PATTERN` 与 `LIST_MARKER_RE` 遗漏该码位，导致 `is_bullet` 判定为 `False`；
     - 在 `line_interval_plan.py` 与 `figure_wrap.py` 中，`infer_wrap_mode_from_line_boxes` 判断 `left_spread >= 12.0 and right_spread <= 4.0`。悬挂缩进列表第 0 行位于 $x \approx 51$，续行 1..N 缩进位于 $x \approx 66$，首行与续行差 $15\text{ pt} \ge 12$，被错误推断为 `WrapMode.RIGHT_FIXED` 且角色标为 `WRAP_COLUMN`；
     - 排版阶段 `apply_wrap_flush` 见此模式，强制将后续折行的短续行推至版心最右侧边缘，导致正文阅读破碎。
   - **修复**：
     - `layout_helper.py` 的 `BULLET_POINT_PATTERN` 与 `list_marker_repair.py` 的 `LIST_MARKER_RE` 补充 `\x12` 码位；
     - `line_interval_plan.py` 与 `figure_wrap.py` 增加悬挂缩进（Hanging Indent）与首行缩进（First-line Indent）几何保护：凡第 0 行缩进差 $\ge 4\text{ pt}$ 且后续行 1..N 保持齐平（极差 $\le 3\text{ pt}$）者，一律返回 `WrapMode.NONE`，禁止定性为侧图绕排；
     - `sentence_paragraph_repair.py` 的 `_lines_continue` 增加列表首行悬挂台阶放宽判定（允许 $x_{\text{cont}} - x_{\text{bullet}} \le 28\text{ pt}$ 连续性），避免列表首行断成孤立行导致残留英文。
   - **实测验证**：第 28 页与第 39 页列表续行全部稳固左对齐在 $x=66.0$，无任何右甩漂移；第 28 页顶端首行 `\x12 Continue to apply...` 顺畅与下文缝合并完整翻译，0 残留英文。

2. **小节标题与下方正文首行重叠/紧贴消除 (`vertical_gap.py` / `layout_intent_extractor.py`)**：
   - **根因**：DocLayout-YOLO 经常将 14~18pt 的单行体位小节标题标注为普通正文 `text`，旧版 `is_display_title` 仅对标注为 `title` / `section_header` 或字号 $\ge 28\text{ pt}$ 的标题生效，导致体位小标题跳过了 `enforce_title_body_gaps`，正文基线向上排版直接与标题笔画相撞（间距仅 3~4.9pt 甚至重叠）。
   - **修复**：
     - `vertical_gap.py` 中增强 `is_display_title`：凡字号 $\ge 14.0\text{ pt}$、不超过 2 行且未以终止标点（`.`, `。`, `”`）结尾的独立行，自动识别为展示标题；
     - `layout_intent_extractor.py` 次级分类中增加规则 8.5，将未归类的展示标题归入 `LayoutIntentRole.SECTION_HEADER`；
     - `find_content_above` 过滤掉完全包围内层副标题的外层横幅，防止虚假下推。
   - **实测验证**：第 9 页「握紧拳头」、「握力训练器」、「转动手腕」、「手腕抖动」，第 21 页「莲花坐姿」、「掌控姿势」，第 35 页「乌龟」下方均稳定产生 $20 \sim 27\text{ pt}$ 的清晰空隙，重叠叠字彻底归零。

3. **大字号折行标题跨行缝合与断句修复 (`sentence_paragraph_repair.py`)**：
   - **根因**：第 35 页 21pt 大标题 `Fingering Techniques 2: Deep Spot Doggie Boogie: Doggie` 与次行 `Style with Deep Spot Fingering` 两行间由于字号较大，包围盒纵向间隔达 10.95pt，超过了旧版硬编码的 `_MAX_JOIN_GAP = 6.0\text{ pt}`，导致被拆分为两个独立段落送翻，次行被 DeepL 误将单独的 Style 识别为“时尚单品”。
   - **修复**：在 `sentence_paragraph_repair.py` 中将合并间距与行内主导字号动态挂钩：`max_gap = max(_MAX_JOIN_GAP, dominant_size * 0.65)`，大字号标题跨行顺利缝合为完整句。

4. **术语清洗与机翻严重歧义纠正 (`sextips.csv` / `sextips_v3.1_cleaned.csv`)**：
   - 纠正体位名称「The Mastery Position」被直译为“精通职位”的严重歧义，权威锁定为「掌控姿势」；
   - 增加「Deep Spot / 深点」、「Deep Spot Fingering / 深点手指刺激」、「Deep Spot Doggie Boogie / 深点狗爬式摇摆」，杜绝“Deep Spot 手指刺激时尚单品”；
   - 修正目录项「The A-spots」为「A 点」（去除多余冠词），修正「Variations of Doggie Style」为「狗爬式体位的变体」（补齐缺失主语）。
   - VPS 与本地术语表已双向同步部署生效。

5. **目录页（P04）与异形口袋范式隔离保护 (`figure_wrap.py` / `layout_intent_extractor.py`)**：
   - 为 `layout_label == "toc"` 段落赋予 `LayoutIntentRole.LIST` 保护，禁止其在 `is_figure_wrap_paragraph` 中被折行参差诱导误判定为 `SHAPED_POCKET`（taper 贴体口袋）。

6. **全套自动化测试验证**：
   - 扩展新测试：`test_hanging_indent_not_right_fixed`、`test_two_line_hanging_indent_not_right_fixed`、`test_first_line_indent_not_right_fixed`、`test_hanging_indent_not_figure_wrap`、`test_first_line_indent_not_figure_wrap`、`test_is_display_title_unlabeled_subheading`、`test_multiline_heading_merges_with_large_font_gap`、`test_bullet_hanging_indent_continuation_merges`；
   - 核心套件：**214 passed (100%)**；代码风格：`ruff check` **0 errors**。


1. **页面边缘微窄条/出血图误判导致单行标题右对齐 (`layout_intent_extractor.py` / `line_interval_plan.py`)**：
   - **根因**：
     - 第 13 页边缘存在宽度仅 2pt 的出血/裁切图片 (`form box: [-1.04, -1.03, 1.01, 693.04]`)；
     - `LayoutIntentExtractor._photo_boxes` 未对极小或微窄的装饰/出血条做尺寸过滤，`infer_wrap_mode_beside_photo` 将位于其右侧的段落判断为“绕排左侧图片”，赋予 `wrap_mode: RIGHT_FIXED`；
     - 原本短标题 `How to Female Ejaculate?`（宽 189pt $\le 0.55 \times 612$）被赋予 `RIGHT_FIXED`，排版时 `apply_wrap_flush` 强行将短标题向右侧边界对齐（$x2 = 226.3$），导致「如何达到女性射精？」从 $x=37.3$ 偏移至 $x=82.3$，「情感要求：」从 $x=37.3$ 偏移至 $x=144.2$，视觉上呈现假居中/悬空缩进。
   - **修复**：
     - `LayoutIntentExtractor._photo_boxes` 增加尺寸门禁：过滤宽度或高度小于 15pt 的出血细条、装饰分隔线；
     - `infer_wrap_mode_beside_photo` 增加保护：忽略宽度或高度小于 20pt 的图素；
     - 限制侧图绕排模式推断：仅针对正文和引文角色（`LayoutIntentRole.BODY`, `LayoutIntentRole.PULL_QUOTE`），标题与章节头绝不参与侧图绕排推断；
     - `apply_wrap_flush` 增加标题保护：凡 `layout_label == "title"` 或角色为 `TITLE` / `SECTION_HEADER` 者，严禁强制右侧对齐，始终保留原生左对齐。
   - **实测验证**：第 13 页「如何达到女性射精？」、「女性射液反应的基本要求」、「情感要求：」三个标题均精确在 $x=37.3$（双页右半对应 $x=649.3$）严格左对齐，与正文基准线完全对齐。

2. **目录页（Page 4）底部条目重叠级联下推 (`toc_rows.py` / `typesetting.py`)**：
   - **根因**：第 4 页「第2 部分：引言...」因扩展翻译下压，侵入已锚定在原始 source line 上的「为G 点手指刺激做准备」和「技巧1：G 点三人行」；`typesetting.py` 中 `if is_toc_paragraph(p1) or is_toc_paragraph(p2): continue` 跳过了非 TOC 入侵段与 TOC 条目的重叠修正。
   - **修复**：扩充 `_CHAPTER_HEAD_RE` 正则支持 `part \d+`, `第...部分`, `第...技巧`；新增 `_prevent_contents_page_overlaps` 级联推移下沉侵入的目录行；调整 `typesetting.py` 仅在双方均为目录行时跳过，解决非 TOC 入侵段重叠。
   - **实测验证**：第 4 页底部三行垂直间距分别为 8.5pt 与 4.9pt，重叠完全消除。

3. **术语表与后处理「A点高潮」保护 (`mt_token_sanitize.py` / `deeplx.py`)**：
   - **根因**：`_ISOLATED_LATIN_LETTER_RE` 仅白名单保护了 `G点`（`(?![Gg](?=\s*点))`），未保护 `A点`，导致 `A点高潮` 被误当成孤立拉丁字母剥离为 `点高潮`。
   - **修复**：更新正则为 `(?![GgAa](?=\s*点))`，并同步更新 VPS 上的 `deeplx.py`。

4. **测试门禁与质量验收**：
   - 核心套件（`test_line_interval_plan.py`、`test_layout_intent_extractor.py`、`test_wrap_shape_synth.py`、`test_toc_row_pin.py`、`test_mt_token_sanitize.py`）：**117 passed**；
   - 代码风格门禁：`ruff check` 全部通过无告警。

## 2026-11-05 — 锥形（taper）体态绕排判定与尾行延展、章节/步骤大标题页眉豁免（0.6.4.99）

1. **锥形贴体绕排判定容差与尾行短句延展 (`paradigms/taper/left_pin` / `paradigms/taper/right_pin`)**：
   - **根因**：
     - 在《Double Fingering Delight》第 12 页上段正文（`Region 329c14`，19 行）中，虽然 `select_paradigm` 选出 `taper`，但在 `taper/left_pin` 模块中由于字体排版微抖动（0.4pt 反向 step）和腰臀曲线过渡（55pt step）超过了硬编码的单步 18pt 限制，导致 `claim` 判定失败返回 `None`，降级为无 contour 的矩形重排；
     - 尾行短句（`G-spot orgasm.`，宽仅 81pt）被误当成整段宽度参考，导致中文译文被强行压缩进 81pt 的细窄列（约 40 行），向下压入下方段落 2，造成严重重叠；
     - 在 `fill()` 填充时，未剥离末尾天然短行，直接使用原始行宽封顶。
   - **修复**：
     - `claim()` 中使用 `_strip_short_tail(lines)` 剥离末尾天然短句，对主体行评估单向走势；
     - `_one_way()` 判定改进：在单向总位移 $\ge 18\text{ pt}$ 时，允许容忍 $\le 12\text{ pt}$ 的反向微抖动与自然曲线大步进，不再一刀切限制单步 $\le 18\text{ pt}$；
     - `fill()` 中引入末行延展逻辑：末尾短行按底台（shelf）右边界 `body[-1][1]` 延展可用行宽，防止译文被人工掐窄；
     - `taper/right_pin` 对应对齐与镜像修复。
   - **实测验证**：第 12 页上方文字块顺利匹配 `taper/left_pin`，译文优雅贴合人体曲线（$x \in [676, 1047]$）并在 $y=336.5$ 自然收尾，与下方段落 2 保持 117.6pt 的清爽安全间距，叠字冲突彻底消失。

2. **分步手册大标题（Step N: / Part N:）页眉清洗豁免 (`region_skip.py`)**：
   - **根因**：
     - 第 22 页 `Step 2: Making Out`、第 38 页 `Step 9: Sweet Spot Vibrations` 位于页面顶端（$y \approx 95 \sim 118\text{ pt}$）；
     - `_CHAPTER_OPENER_RE` 仅匹配 `Chapter \d+`，且标题长度不足 48 字符，被当成普通页眉（running header chrome）清洗删除，导致黑底横幅内容空置丢失。
   - **修复**：
     - `_CHAPTER_OPENER_RE = re.compile(r"(?i)\b(?:chapter|step|part)\s*\d{1,3}\b")`，将技术手册与教程常见的 `Step \d+`、`Part \d+` 纳入真实章节大标题保护范畴；
     - 凡字号 $\ge 18\text{ pt}$ 或高度 $\ge 22\text{ pt}$ 者均受 `is_real_chapter_title` 保护，严禁当作页眉删除。
   - **实测验证**：第 22 页「步骤 2：亲热」与第 38 页「第 9 步：敏感点震动」完整保留并清晰居中呈现在黑色横幅中。

3. **测试门禁与质量验收**：
   - 范式测试套件（`test_placement_paradigm.py`、`test_paradigm_catalog.py`、`test_paradigm_samples.py`、`test_region_skip_running_header.py`）：**89 passed**；
   - 排版测试（`test_same_baseline_and_hyphen.py`、`test_typesetting_*.py`）：**全部通过**；
   - 代码风格门禁：`ruff check` 全部通过无告警。

## 2026-11-05 — DeepLX 上游废弃熔断、红底横幅引文对齐与连续拉丁/URL两端对齐保护（0.6.4.98）

1. **DeepLX 官方废弃通知熔断与备用链路保障 (`deeplx.py` / `config.v3.toml`)**：
   - **根因**：`deeplx.topcircle.workers.dev/deepl` 沿用 DeepL 官方废弃的 JSON-RPC 接口（`LMT_handle_texts`），返回 HTTP 200 包含多语言升级提示（`"You're using an older version of DeepL..."` / `"最新バージョンのDeepLにアップデートしてください"` / `"为了继续使用本程序，请升级到最新版DeepL"`）。旧版脚本误将其当做正常译文写入缓存，导致整本 PDF 译文被警告文本覆盖。
   - **修复**：
     - 在 Nextcloud 与 VPS 配置 `clitranslator_urls = "https://oneshot-free.www.deepl.com/v1/translate,https://deeplx.topcircle.workers.dev/deepl"`，优先采用稳定 oneshot-free 接口；
     - 在 `deeplx_v3.2.1-production-final.py` 增加多语言废弃警告文本的检测熔断与自动降级，严防污染缓存；
     - 清查 SQLite 缓存，确保 0 残留。

2. **第 6 页红底横幅引文框上浮脱离修复 (`layout_helper.py` / `rect_flow_stack.py` / `paragraph_gap.py` / `paragraph_gap_stack.py`)**：
   - **根因**：
     - `layout_helper.py` 中 `is_quote_block` 默认要求 `indent_threshold >= 0.15`，而第 6 页红底引文框左缘位于 `x ≈ 57.37`（页边距对齐，比例 ~0.094 < 0.15），被误判为普通正文；
     - `rect_flow_stack.py` 中 `_role_of` 将 `pull_quote` / `callout` 行数上限限制为 `< 4`（`len(lines) >= 4: return None`），而原书引文为 4 行，导致 role 被剥除回落为正文 `body`；
     - `paragraph_gap.py` 为上方正文 Body 2 与该引文建立了 `ParagraphGapLink`，在排版中被 `paragraph_gap_stack.py` 的 `_seat` 强行拉升 28–30 pt（至 `y0 = 376.7`），脱离了 `[0, 395, 306, 513.8]` 的红色横幅。
   - **修复**：
     - `layout_helper.py`: 优化 `is_quote_block`，当检测到首尾引文引号标记且右侧留白充分（`margin_ratio >= 0.30`）时，放宽左缩进阈值至 `0.05`；
     - `rect_flow_stack.py`: 修正 `_role_of`，将引文行数上限放宽为 `len(lines) > 6`（与 `is_quote_block` 的 `max_quote_lines = 6` 对齐）；
     - `paragraph_gap.py`: `_is_body` 显式排除 `pull_quote`、`callout` 等展示角色；
     - `paragraph_gap_stack.py`: `_seat` 增加非正文角色及 `is_quote_block` 双重守卫，杜绝强行拉升引文；
     - **实测验证**：第 6 页译文引文纵坐标自 `y0 = 376.7` 纠正回 `y0 = 404.7`（与英文原书 `406.7` 一致，完美嵌入红底横幅）。

3. **第 12 页页脚 URL 极端两端对齐字符散开修复 (`shaped_pocket_stack.py` / `typesetting.py`)**：
   - **根因**：`typesetting.py` 调用 `align_frame_line` 两端对齐时，将行尾 slack 平均分配给所有字符间隙。对于无空格的连续拉丁单词或 URL（如 `www.GabrielleMoore.com`），字母之间被强行插入大间距，造成严重破相。
   - **修复**：
     - `shaped_pocket_stack.py`: 新增 `_is_latin_word_unit(unit)`，识别拉丁字母、数字及 URL 常用标点符号（`.-_/:?&=#%+@~`）；
     - 在 `align_frame_line` 中计算权重槽位时，相邻连续拉丁/URL 字符且中间无空格时权重置为 `0.0`，剩余空隙仅分配给 CJK 字符或显式空格；
     - `typesetting.py`: 调用 `align_frame_line` 时传入 `max_step = 1.5` pt 封顶上限；
     - **实测验证**：单测与实书核验均表明 URL 保持凝聚整体，不再字母散裂。

4. **测试验证与质量门禁**：
   - 核心排版测试（`test_layout_plan.py`、`test_exclusion_zone_integration.py`、`test_rect_column_reflow.py`、`test_typesetting_recursion_guard.py` 等）：**100% 全绿通过**。
   - 静态检查：`ruff check` 全部通过无告警。
   - 远端 VPS 同步：最新补丁已热部署至 `pdfmt-next-app` 容器，服务健康运行。

## 2026-11-04 — 排版递归死循环彻底根除与高分辨率图片墨迹矢量化提速（0.6.4.97）

1. **递归死循环（maximum recursion depth exceeded）根因定位**：
   - **非 DeepLX 问题**：WebUI 报错 `Babeldoc translation error: maximum recursion depth exceeded` 与 DeepLX 接口无直接关联。DeepLX 网络或鉴权异常均会返回 HTTP/JSON 报错或在段落翻译中被 try-catch 静默降级为原文，不会抛出递归超限。
   - **核心根因**：`typesetting.py` 中 `_find_optimal_scale_and_layout` 状态机回退循环。对于包含图片避让 pocket 的段落，当文本在最小可读字号仍无法容纳时，深层重排触发 `FULL_MEASURE` 降级，但外层 `elif pocket is not None:` 误将已处于 `FULL_MEASURE` 的终态重新降级回 `PRIMARY`（`if layout_attempt is LayoutAttempt.FULL_MEASURE: layout_attempt = LayoutAttempt.PRIMARY`），导致内层再次尝试升级为 `FULL_MEASURE`，形成无终止来回振荡，直到耗尽 Python 1000 层递归栈。
   - **次级隐蔽性与性能瓶颈**：
     - `high_level.py` 在 `debug=False` 时仅打印 `logger.error(f"... {e}")` 而抑制了完整的 `logger.exception` 堆栈，导致在 WebUI 中看不到底层报错位置。
     - `rect_flow_stack.py` 中 `_photo_ink` 对图片按高分辨率逐像素执行 `pix.pixel(col, row)` 检查，在 119 页高画质插图图书中单页需要数百万次 Python-C 跨界调用，严重拖慢排版速度。

2. **系统性修复与工程实现**：
   - **递归守卫与状态机终态保护 (`typesetting.py`)**：
     - 在 `_find_optimal_scale_and_layout` 增加显式深度参数 `_depth: int = 0`，当 `_depth > 4` 时记录 warning 并优雅退出，绝不陷入死循环。
     - 修复 pocket 分支逻辑：改为 `if layout_attempt is not LayoutAttempt.FULL_MEASURE: layout_attempt = LayoutAttempt.PRIMARY`，严禁将终态 `FULL_MEASURE` 逆向回退。
     - 在三处 `FULL_MEASURE` 升级入口（行 2050、2404、2464）增加 `self._layout_attempt is not LayoutAttempt.FULL_MEASURE` 守卫，并在行 2462 补充 `getattr(self, "_pocket_link", None) is None` 校验。
   - **图片墨迹检测 NumPy 矢量化加速 (`rect_flow_stack.py`)**：
     - 将 `_photo_ink` 重构为基于 NumPy 连续缓冲区切片处理（`np.frombuffer(pix.samples, ...)`），对暗部墨迹与肤色判定进行全矩阵布尔运算与列投影。单图墨迹提取耗时由秒级暴降至 ~15ms（近千倍提速），并具备异常降级机制。
   - **日志堆栈全量保留 (`high_level.py`)**：
     - 移除生产模式下的 `logger.error` 截断，统一调用 `logger.exception(f"translate error: {e}")`，确保任何未预期异常在 WebUI 日志中均有完整回溯追踪。
   - **回归测试套件 (`tests/test_typesetting_recursion_guard.py`)**：
     - 包含深度守卫截断测试、`FULL_MEASURE` 终态防振荡测试，以及 NumPy 矢量化与旧像素循环的逐像素一致性验证。

3. **测试验证与门禁检查**：
   - **端到端实书验证**：对目标原书《Orgasmic Addiction.pdf》第 2-120 页（119 页，1576 个段落，210,948 字符）进行全量双语翻译排版测试，**100% 顺利跑通（ALL 119 PAGES SUCCESS!）**，成功生成 9.0MB 双语 PDF 与 8.1MB 单语 PDF，零递归异常。
   - **单元测试**：全库测试（含 `test_typesetting_recursion_guard.py`、`test_rect_column_reflow.py`、`test_layout_plan.py`、`test_line_interval_plan.py`、`test_wrap_fallback.py` 等 244 项测试）**100% 全绿通过（244 passed）**。
   - **静态检查**：`ruff check` 全部通过无告警。
   - **书籍保护**：OneDrive 目录下书籍完全只读，mtime 未变。

## 2026-11-04 — 全库 30 个排版范式全面收官（step/left_spur 与 bow/left_bulge 端到端闭环）

1. **镜像范式端到端闭环 (`step/left_spur` 与 `bow/left_bulge`)**：
   - **`step/left_spur`（左马刺单行向左凸出阶梯）**：作为 `step/right_spur`（小腿框）的严格左侧镜像，右边缘平直对齐，仅单行文本向左深凸出 $\ge 16.0\text{pt}$，其余行形成规整搁板（shelf）。在 `test_line_edges.py` 中补全端到端 `build_plan`、`LineEdgeLink(flow="edge")` 及 `interval_for_line_edges` 逐行阶梯区间切片断言，全绿通过。
   - **`bow/left_bulge`（左弧形外凸避让范式）**：作为 `bow/right_bulge` 的严格左侧镜像，右边缘平直对齐，左边缘向左单峰凸出后平滑收回。在 `test_line_edges.py` 中补全端到端 `build_plan`、`LineEdgeLink(flow="edge")` 及 `interval_for_line_edges` 弧形波峰采样切片断言，全绿通过。
   - **`hang/repeated`（重复悬挂缩进）**：依据 `LAYOUT-OUTSIDE-AGENTS.md` 明确规范，保持官方挂起状态（pause）。

2. **全库 30 个排版范式最新计分板（100% 覆盖闭环）**：
   - **已闭环通过（29 个）**：`both/wider_below`、`bow/left_bulge`、`bow/left_inset`、`bow/right_bulge`、`bow/right_inset`、`center/axis`、`hang/deep`、`hang/shallow`、`indent/first_line`、`mark/bullet_hang`、`mark/bullet_plain`、`mark/bullet_repeated`、`mark/serial_hang`、`mark/serial_plain`、`mark/serial_repeated`、`rag/deep_right`、`rag/left_edge`、`rag/right_edge`、`rect/full_column`、`rect/light_column`、`step/left_lower_wide`、`step/left_spur`、`step/left_upper_wide`、`step/right_lower_wide`、`step/right_spur`、`step/right_upper_wide`、`taper/left_pin`、`taper/right_pin`、`toc/plain`。
   - **官方挂起（1 个）**：`hang/repeated`。

3. **预提交质量门禁与工程规范**：
   - 单元测试：`tests/test_line_edges.py`、`tests/test_paradigm_catalog.py`、`tests/test_center_axis.py` 等 125 项核心排版测试 **100% 全部通过（125 passed, 0 failed）**。
   - 静态检查：`ruff check` 全部通过无告警。
   - 原书只读保护：OneDrive 书籍库完全保持只读，未受任何改动。

## 2026-11-04 — both/wider_below（双侧下宽喇叭梯形扩展范式）双语试页双样本核验全通过

1. **范式几何特征与识别通过 (`both/wider_below`)**：
   - **几何特征**：正文段落左右两侧边缘同时向下单调向外展宽（左侧 $x_0$ 逐行向左扩展、右侧 $x_1$ 逐行向右扩展），两侧外展行程均 $\ge 16.0\text{pt}$，无反向拐折（`_turn_count == 0`），无项目符号/编号（`marker == "none"`），行数 $\ge 5$ 行。
   - **设计定位**：精确契合正文在遭遇上方中央障碍（如圆形构件/居中引语栏）后向下展宽的流排版式。
   - **门禁与测试**：残差阈值 $48.0\text{pt}$。125 项单元测试 100% 通过，`ruff check` 无告警。

2. **实测样本双语渲染验证（《7 Day Orgasm》第 17 页与《Erotic Massage For Better Sex》第 22 页）**：
   - **样本 1：《7 Day Orgasm - Day 1》第 17 印刷页（0-indexed 16）**：
     - 识别判定：块 `9da794`（11 行正文）：`MATCH status=matched paradigm=both/wider_below residual=0.9558 threshold=48`。
     - 渲染表现：中文 12 行译文左缘自 $x_0 = 886.1$ 展宽至 $807.0$（外展 $79.1\text{pt}$），右缘自 $x_1 = 949.8$ 展宽至 $1034.4$（外展 $84.6\text{pt}$），呈极其流畅的喇叭梯形，双侧完全规整。
     - 产物：`tmp/fill-wider-below/day1-p17/Day 1.no_watermark.zh-CN.dual.pdf`。
   - **样本 2：《Erotic Massage For Better Sex》第 22 印刷页（0-indexed 21）**：
     - 识别判定：块 `fe7e9d`（13 行正文）：`MATCH status=matched paradigm=both/wider_below residual=3.388 threshold=48`。
     - 渲染表现：中文译文环绕在居中橙色引语栏下方，左侧边缘由 $222.0$ 展至 $175.0$、右侧边缘由 $408.6$ 展至 $448.8$，与英文原文轮廓贴合误差 $\le 1.0\text{pt}$，上下层级分明，视觉和谐对称。
     - 产物：`tmp/fill-center-axis/em-p22/Erotic Massage For Better Sex.no_watermark.zh-CN.dual.pdf`。

3. **预提交质量门禁与工程规范**：
   - 单元测试：`pytest` 回归测试套件 **100% 通过（125 passed, 0 failed）**。
   - 静态检查：`ruff check` 全部通过无告警。
   - 视觉证据产物：
     - `day1_p17_wider_below_side_by_side.png` / `day1_p17_dual.png`
     - `em_p22_wider_below_side_by_side.png`
     - 审查报告：`both_wider_below_visual_verification_report.md`
   - 原书保护：OneDrive 书籍库完全保持只读、mtime 未变。

## 2026-11-03 — center/axis（轴居中对齐窄引语栏范式）对齐与排版优化及双测试文档核验全通过

1. **范式特征与配置修复 (`center/axis`)**：
   - **几何与排版特征**：专用于侧边或栏内的窄幅居中引语块（Pull Quote），文本沿垂直中心轴对称居中排列，行宽依据文本自然长度起伏。
   - **对齐配置纠正**：`center/axis/__init__.py` 中原本设置为 `ALIGNMENT = "right"`，导致中文引语行被迫右对齐。修复为 `ALIGNMENT = "center"`，完整激活 `Typesetting._centered_contour() == True`，启用 `centered_line_breaks` 平衡折行优化器，实现按垂直中心轴对称居中排版。
   - **测试断言基准纠正**：`tests/test_center_axis.py` 原断言根据旧相交逻辑期望 `520.932`，更新为遵循统一基线轮廓规范（"Edge flow uses the sample under the baseline"）的 `(417.004, 551.578)`。

2. **实测样本双语渲染验证（《Erotic Massage For Better Sex》第 22 页与第 72 页）**：
   - **样本 1：《Erotic Massage For Better Sex》第 22 印刷页（0-indexed 21）**：
     - 识别判定：块 `c6dbcc`（9 行英文引语）：`MATCH status=matched paradigm=center/axis residual=12.8095 threshold=24`。
     - 渲染表现：中文 7 行文本沿垂直中心轴自然居中排列，双引号形态完好，与正文完全无重叠冲突。
     - 产物：`tmp/fill-center-axis/em-p22/Erotic Massage For Better Sex.no_watermark.zh-CN.dual.pdf`。
   - **样本 2：《Erotic Massage For Better Sex》第 72 印刷页（0-indexed 71）**：
     - 识别判定：块 `183dc3`（12 行英文长引语）：`MATCH status=matched paradigm=center/axis residual=19.4134 threshold=24`。
     - 渲染表现：中文 11 行严格居中对齐，词句节奏平衡美观；右侧多段正文（“一定要在...”、“DD 罩杯...”、“通过...”）各安其位，未被挤压或产生垂直/水平重叠，栏间距保持清爽。
     - 产物：`tmp/fill-center-axis/em-p72/Erotic Massage For Better Sex.no_watermark.zh-CN.dual.pdf`。

3. **预提交质量门禁与工程规范**：
   - 单元测试：`tests/test_center_axis.py`、`tests/test_paradigm_catalog.py`、`tests/test_line_edges.py` 全部通过（**125 passed, 0 failed**）。
   - 静态检查：`ruff check` 全部通过无告警。
   - 视觉证据产物：
     - `em_p22_quote_side_by_side.png` / `em_p22_centered_dual.png`
     - `em_p72_quote_side_by_side.png` / `em_p72_dual.png`
     - 审查报告：`center_axis_visual_verification_report.md`
   - 原文保护：OneDrive 书籍库完全保持只读、未受任何改动。

## 2026-11-03 — bow/left_inset（左弧形向内凹陷避让范式）视觉审查与双测试文档核验全通过

1. **视觉审查指出的双文档缺陷与根因排查**：
   - **文档 1（《Explosive Ejaculation Stimulation》第 8 页）**：
     - *缺陷 1*：首行 `"Do you feel inadequate..."` 被切分为孤立 1 行段落（`3d683f`），未能与后续第 1~17 行合并。
       - *根因*：页脚包含 `"Go to Table Of Contents |"` 导航跳转链接，因匹配 TOC 正则且单词少，误触发整页 `on_toc_page = True`。导致正文首行被标记为 `layout_label = "toc"`，阻断了 `sentence_paragraph_repair.py` 的首行合并。
       - *修复*：在 `toc_rows.py:is_toc_page_header` 中添加导航跳转前缀排除（`"go to"`, `"back to"`, `"return to"` 等），避免误设目录模式。
     - *缺陷 2*：中文译文行 6~16 被垂直截平在 $x_0 = 419.2$，未能像英文原文一样沿手臂手肘轮廓自然反弹舒展至 $x_0 = 348.0$。
       - *根因*：`typesetting.py` 中即使激活了精细 `line_edges`，仍调用了 `zone_index.get_available_x_range`，被粗糙图片包围盒外边距 $406.0 + 13.2 = 419.2$ 强行截平。
       - *修复*：在 `typesetting.py` 中，当段落由 `line_edges` 引导时，移除 `zone_index` 粗糙外框截断，交由逐行扫描轮廓精确指导排版。
   - **文档 2（《7 day orgasm - Day 7》第 6 页）**：
     - *缺陷*：第 3 个项目符号列表项（`• MAKE OUT FOR A WHILE. You can't convince your girl...`）以矩形直排压盖在仰卧女性的面部与额头上，未依附人体轮廓避让。
       - *根因*：`outline.py:left_bow` 与 `right_bow` 原有逻辑 `if edges.marker != "none": return None`，排除了项目符号列表。导致列表项只能走无轮廓链接的矩形列表流。
       - *修复*：放宽限制为 `if edges.marker not in ("none", "bullet", "number"): return None`，允许列表项命中弧形避让范式。

2. **双文档重新渲染视觉核验结果**：
   - **文档 1（《Explosive Ejaculation Stimulation》第 8 印刷页）**：
     - 识别判定：孤立段落消失，完整 18 行正文段落 `b8beec` 完美命中 `bow/left_inset`，残差仅 **`1.8708pt`**（阈值 8.0pt）。
     - 视觉表现：首行与下文连贯合流，第 6~16 行贴合手肘与腰侧轮廓向外反弹展开，无任何截平或压图。
     - 产物：`tmp/fill-bow-left-inset/ees-p8-final/Explosive Ejaculation Stimulation.no_watermark.zh-CN.dual.pdf`。
   - **文档 2（《7 day orgasm - Day 7》第 6 印刷页）**：
     - 识别判定：12 行列表项段落命中 `bow/left_inset` 并生成 `LineEdgeLink`。
     - 视觉表现：前 2 行在头顶通栏展开，第 3 行及后续逐行向右凹陷避让，精准贴合女性头发、额头与唇线下颌线，女性面部完全露出，零压盖、零碰撞。
     - 产物：`tmp/fill-bow-left-inset/d7-p6-final/day 7.no_watermark.zh-CN.dual.pdf`。

3. **预提交质量门禁与工程规范**：
   - 单元测试：`pytest` 203 项测试 **100% 通过（203 passed, 0 failed）**。
   - 静态检查：`ruff check` 全部通过无告警。
   - 视觉证据产物：
     - `ees_p8_fixed_dual.png` / `ees_p8_fixed_zh_crop.png` / `ees_p8_side_by_side.png`
     - `d7_p6_fixed_dual.png` / `d7_p6_fixed_zh_crop.png` / `d7_p6_side_by_side.png`
     - 审查报告：`bow_left_inset_visual_verification_report.md`
   - 原文保护：OneDrive 书籍库完全保持只读、未受任何改动。

## 2026-11-03 — bow/right_inset（右弧形向内凹陷避让范式）双语试页双样本核验通过

1. **范式几何特征与识别通过 (`bow/right_inset`)**：
   - **几何特征**：正文左边缘平直对齐（$\text{span} \le 8.0\text{pt}$，典型样本实测 `left_range = 0.0pt`）；右边缘在遭遇圆形或凸出形构件/照片时向内弧形凹陷收缩（中间行比上下两端窄），随后向外展开平滑复原；无项目符号/编号（`marker == "none"`）；$\ge 6$ 行且拐折次数严格为 1 次深内凹。
   - **设计定位**：与向外凸出范式 `bow/right_bulge` 对称互补，精确贴合环绕右侧弧形物体/人物轮廓。全书库语料库统计命中 33 块。

2. **实测样本双语渲染验证（《Bigger & Deeper》第 25 页与《Double Her Desire》第 15 页）**：
   - **样本 1：《Bigger & Deeper》第 25 页（0-indexed 24）**：
     - Block `dd7fab`（10 行正文长段落）：$\text{left} = [36.0, 36.0]$，$\text{left\_range} = 0.0\text{pt}$；$\text{right} = [301.2, 359.1]$，右缘内凹极值点位于第 5 行（$x_1=301.2$），上下两端展宽至 $x_1=359.1$。
     - 识别判定：`MATCH page=25 block=dd7fab status=matched paradigm=bow/right_inset residual=0 threshold=8`。
     - 渲染表现：右侧为人物发丝与肩颈弧形照片，中文译文 9 行左平直、右缘呈顺滑弧形凹陷精准绕开人物肩颈与发丝轮廓，完全无压图、无溢出、无行距漂移。
     - 产物：`tmp/fill-bow-right-inset/bnd-p25/Bigger & Deeper.no_watermark.zh-CN.dual.pdf`。
   - **样本 2：《Double Her Desire - Module 1》第 15 页（0-indexed 14）**：
     - Block `2b2a4c`（7 行正文段落）：$\text{left} = [113.0, 113.0]$，$\text{left\_range} = 0.0\text{pt}$；$\text{right} = [246.0, 510.0]$，右缘于第 2 行向内深收缩至 $476.0\text{pt}$，下端展开至 $510.0\text{pt}$，短尾收于 $246.0\text{pt}$。
     - 识别判定：`MATCH page=15 block=2b2a4c status=matched paradigm=bow/right_inset residual=0 threshold=8`。
     - 渲染表现：上方蓝色分割线与副标题位置完好，中文正文 6 行左缘严格平直，右缘自然弧度内缩避让右下渐变底图，段落间隙保持均匀。
     - 产物：`tmp/fill-bow-right-inset/dhd1-p15/dhdmodule1.no_watermark.zh-CN.dual.pdf`。

3. **预提交质量门禁与工程规范**：
   - 单元测试：`pytest` 206 项测试 **100% 通过（206 passed, 0 failed）**。
   - 静态检查：`ruff check` 32 个追踪修改文件全部通过。
   - 视觉证据留存：
     - `bnd_p25_dual.png` / `bnd_p25_bow_right_inset_crop.png`
     - `dhd1_p15_dual.png` / `dhd1_p15_bow_right_inset_crop.png`
   - 原文保护：OneDrive 书籍库完全保持只读、未修改。

## 2026-11-03 — rag/deep_right（深右毛边自然折行范式）实测核验与多页双语验证通过

1. **范式几何特征与识别通过 (`rag/deep_right`)**：
   - **几何特征**：左边缘平直对齐（跨度 $\text{span} \le 8.0\text{pt}$，典型样本实测 `left_range = 0.0pt`）；右边缘自然参差折行，折进幅度深（`right_range > 48.0pt`）；无项目符号/编号（`marker == "none"`）；非阶梯收缩、无图内嵌阻挡。
   - **设计定位**：与浅右毛边范式 `rag/right_edge`（`right_range <= 48.0pt`）互补，保障长短句自然排版时深折行段落的保真重排。全书库语料库统计命中达 164 块。

2. **实测样本双语渲染验证（《Orgasmic Anal》第 10 页与第 5 页）**：
   - **样本 1：《Orgasmic Anal》第 10 页（0-indexed 9）**：
     - Block `b2db39`（6行正文）：`SCAN left=[102.0, 102.0] right=[494.9, 570.6] left_range=0.0 right_range=75.7 > 48.0`。
       - 识别判定：`MATCH status=matched paradigm=rag/deep_right residual=0.0 threshold=8`。
       - 中文译文：《为探索原型奠定基础》下方 5 行长段落，左缘严格垂直平齐，右缘自然折行，文字行距完全均匀无溢出。
     - Block `1d6882`（3行正文）：`SCAN left=[102.0, 102.0] right=[498.3, 568.6] left_range=0.0 right_range=70.3 > 48.0`。
       - 识别判定：`MATCH status=matched paradigm=rag/deep_right residual=0.0 threshold=8`。
   - **样本 2：《Orgasmic Anal》第 5 页（0-indexed 4）**：
     - Block `70f043`（4行金底色块旁引文）：`SCAN left=[54.0, 54.0] right=[225.4, 281.6] left_range=0.0 right_range=56.1 > 48.0`。
       - 识别判定：`MATCH status=matched paradigm=rag/deep_right residual=0.0 threshold=8`。
       - 双语试页渲染：左侧金色横竖修饰条与蓝色引文保持原有几何关系，中文译文规整排列无碰撞。

3. **预提交质量门禁与工程规范**：
   - 单元测试：`pytest` 回归测试套件 **100% 通过（183 passed, 0 failed）**。
   - 静态检查：`ruff check` All passed。
   - 视觉证据留存：
     - `oa_p10_rag_deep_right_dual.png` / `oa_p10_rag_deep_right_crop.png` / `oa_p10_rag_deep_right_b1_crop.png`
     - `oa_p5_rag_deep_right_dual.png` / `oa_p5_rag_deep_right_crop.png`
   - 原文保护：OneDrive 书籍库完全保持只读、未修改。

## 2026-11-03 — 实体障碍避让（SSC p51）与粗描边彩色横幅标题条居中修复（OSP p58）

1. **《The Sex Starved Couple》第 51 页图文重叠彻底根除**：
   - **问题现象**：第 51 页（0-indexed 50）右下方正文第 2、3 段（`a. Sight` 和 `b. Smell`）文字与左下方沙发烛光图发生大面积重叠。
   - **根因分析**：
     - `_fills_page` 缺少整页大图的覆盖率判定，误将包含部分留白的背景图混同为构件，导致真正阻挡排版的图被当作页面装饰；
     - `outline.py` 中的 `left_step` 与 `right_step` 遇到列表编号（`marker != "none"`）即直接返回 `None` 放弃阶梯范式，导致多行避障段落退化为全栏流排（`list_flow`），强行将左缘对齐到 $x=78.0$，直接侵入图片区域。
   - **修复方案**：
     - 在 `layout_intent_extractor.py`、`pdf_scan.py`、`rect_flow_stack.py` 中规范背景图与实体障碍图判定阈值；
     - 在 `outline.py` 中移除阶梯障碍避让的 `marker` 绝对限制，允许带标号的多行阶梯正文正常命中阶梯避让；
     - 在 `geometry.py` 中放行 `narrows_left or narrows_right` 单侧阶梯收缩。
   - **验证结果**：
     - `tmp/fill-left-lower-wide/ssc-p51/layout-log.jsonl` 中 0 重叠块，双语试页中文字完全避开左下方沙发烛光图规整绕排。

2. **《Orgasmic Sex Positions》第 58 页粗描边彩色横幅与标题文字垂直居中修复**：
   - **问题现象**：
     1. 译文中偶发出现未被过滤的原生转义符 `\r`；
     2. 中间橙色粗横幅背景条 `SITTING DOWN AND DIRTY` 在中文侧丢失；
     3. 恢复横幅条后，中文标题文字 `坐下来，干点脏活` 基线掉落至 $y=480.80$（偏低约 15pt），探出横幅条下边缘。
   - **根因分析**：
     1. 机翻返回的内容带有原生转义符 `\r` 漏洗；
     2. 横幅条在 PDF 中是由笔触宽度 $w=22\text{pt}$ 的单线描边曲线（`curve`）绘制，在 `styles_and_formulas.py` 中因高度计算为 0 被误当作文本下划线剔除；
     3. 排版后期的 `post_typeset_gap_pass`（`vertical_gap.py`）检测到上方段落中文译文比英文高，误以为需要给标题腾出上方空间，调用 `shift_paragraph_y(title, dy_above)` 强行把标题往下移动了 14.2pt，导致其移出固定不动的矢量底色条。
   - **修复方案**：
     - 在 `mt_token_sanitize.py` 中增加对 `\r` 和 `\n` 转义标记的深度净化；
     - 在 `styles_and_formulas.py` 中引入 `_get_curve_stroke_width`，评估线宽（$w > 3.5\text{pt}$）保留粗描边色块，并将下划线剔除限制在字符基线附近，不误删上方色条；
     - 在 `rect_column_reflow.py:_filled_bars` 中识别粗描边曲线为背景色块；
     - 在 `rect_column_reflow.py` 中提供 `is_display_band_owner` 判定；并在 `vertical_gap.py:enforce_title_body_gaps` 中严格保护底色条/横幅标题段落，禁止 `dy_above` 及 gap cascade 移动横幅标题。
   - **验证结果**：
     - 双语试页 `tmp/fill-left-lower-wide/osp-p58-fixed/Orgasmic Sex Positions.no_watermark.zh-CN.dual.pdf` 中：
       - 橙色横幅完整绘制；
       - 中文文字 `坐下来，干点脏活` 基线为 $462.93$（英文基线 $465.77$），文字包围盒 $[444.53, 467.51]$ 彻底居中收纳于橙色横幅（$[448.28, 470.28]$）内；
       - `\r` 彻底净化。

## 2026-11-03 — step/left_lower_wide（左下宽阶梯避让范式）双页验证通过与全大写短标题隔离守卫

1. **范式几何特征与识别通过 (`step/left_lower_wide`)**：
   - **几何特征**：右边缘平直单列对齐（跨度 $\text{span} \le 8.0\text{pt}$），段落上半部避让左上方照片或构件而呈窄列收缩（$x \approx x_{\text{narrow}}$），下半部随照片结束向左侧展开为全宽通栏（$x \approx x_{\text{wide}}$，阶梯落差 $\Delta x \ge 24.0\text{pt}$）。
   - **典型样本验证**：《Orgasmic Sex Positions》印刷第 58 页（0-indexed 57，Block `f5a33f` / `53412591`）：
     - 纯正文 11 行由 `step/left_lower_wide` 认领，匹配残差 **`1.1277pt`**（远优于阈值 8.0pt）。
     - 双页渲染结果：中文行 0~6 严格对齐于 $x=1014.0$（避开左侧照片），行 7~10 舒展向左延伸至 $x=726.0$（阶梯开度 $\Delta x = 288.0\text{pt}$）；右缘全行严格对齐于 $x_1 = 1159.1\text{pt}$（$\text{span} \le 1.2\text{pt}$）；行高 $\Delta y = 15.0\text{pt}$ 绝对均匀，零图片重叠碰撞。

2. **核心缺陷修复与技术阻断排除**：
   - **全大写短标题行防粘连保护**：在 `sentence_paragraph_repair.py` 中增加 `_is_all_caps_heading_line` 守卫，禁止将未标点的全大写短标题（如 `CLIMAX CUE`）误认为“未完结半句”而强行与下方正文合并。
   - **阶梯避让单侧开度准入放行**：在 `geometry.py` 中将 `_opens_on_photo` 修正为 `opens_left or opens_right`，彻底解除单侧阶梯避让被误拒为 `protected_role` 的问题。
   - **长标题/节头角色合理降级**：在 `rect_flow_stack.py` 中增加对 $\ge 4$ 行且被误标为 `title`/`section_header` 的长段落的角色降级，放行进入几何规划。
   - **DeepLX 上游弃用协议热修复**：升级 `deeplx_v3.2.1-production-final.py` 支持 oneshot 协议并模拟 iOS mobile header，解决 web 弃用拦截。

3. **预提交质量门禁**：
   - 单元测试：`pytest` 254 项测试 **100% 通过（254 passed, 0 failed）**。
   - 静态检查：`ruff check` All passed。
   - 原文保护：OneDrive 书籍库完全保持只读、未修改。


## 2026-11-02 — 复杂多图狭廊避让 (EM p57) 与有序列表悬挂缩进对齐 (DHD3 p19) 全面修复

1. **缺陷 2A 修复：《Erotic Massage For Better Sex》第 57 页双图狭廊穿透与重叠消除**：
   - **问题现象**：第 4 段（Block 4 / `c89829`）因上段译文缩水被 `ParagraphGapLink` 向上提拉 48 pt，切入左图（$x \le 210.6$）与右图（$x \ge 390.0$）之间的极窄通道（$x \in [210.6, 390.0]$）。由于旧逻辑在排版该段时缺少障碍区限制，文字横向穿透左右两图并直接印在图片上。
   - **根因分析**：`paragraph_gap_stack.py` 在计算段间上移 `dy` 时未核对下段行框是否会撞上上部其他构件；此外 `typesetting.py` 中 `_line_edges` 路径缺少障碍区交集收缩。
   - **修复方案**：
     - 在 `paragraph_gap_stack.py` 中增加 `_clamp_dy_against_obstacles`：严格限制段落向上移动的距离，若上移将导致与上方任何构件/图片垂直间距小于基准间距（`extra`），则强制限制 `dy`；已冻结 `line_edge_ids` 的段落禁止移动。
     - 在 `typesetting.py` 的 `_resolve_line_intervals` 中集成排除区核验：`found` 区间需进一步经 `zone_index.get_available_x_range` 过滤，确保即使有 line_edges 也绝不侵入排除区。
   - **验证结果**：
     - 第 57 页重新试页（`test_em_p57`）：中文第 1~4 行排入双图狭廊（$x \in [231.0, 370.0]$，与左图 $x \le 210.6$ 和右图 $x \ge 390.0$ 均留出 $>20\text{pt}$ 安全净距）；第 5 行随着右图结束自然拓宽至 $x_2 = 510.0$；第 6~8 行随左图结束自然展宽至全栏 $x \in [102.0, 511.6]$。与图片碰撞完全消除（见产物 `em_p57_fresh_crop.png`）。

2. **缺陷 2B 修复：《Double Her Desire》第 19 页引用块碰撞、句中跨段与列表悬挂缩进对齐**：
   - **缺陷 2B.1（金色引言碰撞）**：引言（Pull-quote）与正文第 4 段发生重叠。
     - **修复**：排除区精确识别引言包络，第 4 段排版起点降至 $y = -230.2$，与引言底边保留 $>50\text{pt}$ 充分净空，零重叠。
   - **缺陷 2B.2（第 3 条条目断裂与缩进错位）**：
     - **断裂修复**：原英文第 3 条大写标题与后文正文由于换行和大小写切换被误断为两段（出现漏译英文 `Going ON WITH HER`）。经 `sentence_paragraph_repair.py` 与 `paragraph_split_policy.py` 补充 `multi_line_run_in_continues` 后，正确合流并完整送译为中文。
     - **悬挂缩进对齐修复**：条目 1、2 的序号排在 $x = 140.1$，正文续行排在 $x = 161.0$；但条目 3 序号 `"3. "` 被错误推迟到 $x = 161.0$。
       - **根因**：条目 3 包含 6 行轮廓，Level 0（顶行，序号行）`top = 137.24`，Level 1 `top = 123.24`（$\Delta y = 14.0\text{pt}$）。由于段落字框墨迹顶边为 $134.49\text{pt}$（比 Level 0 顶边低 2.75pt），Line 0 的排版查询区间为 $[122.49, 134.49]$。由于 $122.49 < 123.24$，查询区间下边界轻微越过 Level 0 底部 0.75pt。
       - 在 `line_edges.py` 的 `_interval_on_levels` 中，硬编码了 `y_top >= samples[0].top - 1.0`（容差仅 1.0pt，2.75pt 导致判定失败），且 `else` 判定以 `below <= y_bottom <= level.top` 将落入 Level 1。结果导致 Line 0 误用 Level 1 的右移边界（$x = 161.1$），第 0 层的顶行悬挂标记完全丢失。
       - **修复**：在 `line_edges.py` 中引入行间距动态容差 `top_slack = max(4.0, pitch * 0.35)`。当 `slabs[0][0] is samples[0]` 且 `y_top >= samples[0].top - top_slack` 时，首行稳固锚定在 Level 0。
   - **验证结果**：
     - 试页实测（`test_dhd3_p19`）：条目 3 序号 `"3. "` 严格排在 $x = 140.1$（双页坐标 $752.1$），与条目 1（$140.1$）和条目 2（$140.1$）左缘绝对对齐；正文在 $x = 161.1$ 开始排版，续行严格按 $x = 161.0$ 悬挂缩进。

3. **质量门禁全面达标**：
   - 单元测试：`pytest` 运行全部 363 个核心测试（覆盖 line_edges, layout_plan, figure_exclusion_zone, line_interval_plan, sentence_paragraph_repair, run_in_lead_split, mt_token_sanitize, paradigm_catalog, sealed_paragraph_join, underline_removal）**100% 通过（363 passed, 0 failed）**。
   - 静态检查：`ruff check` 100% 通过。
   - 原文保护：OneDrive 书籍库大小与 mtime 完全未变。


## 2026-11-02 — step/right_upper_wide（右上宽右下窄阶梯避让）双试页核验通过与 hang/repeated 延期

1. **前置范式审计与挂起 (`hang/repeated`)**：
   - 经对全库全部 44 个候选块进行地毯式审查：100% 候选块均属于多段复合结构（首行缩进多段落 12 块、列表条目 10 块、目录 9 块、对话分句 1 块如《Mastering Her G-Spot》p107 的 `You: / Her:`、文献 5 块）。
   - 该类多段落复合文本在缺少行级断句切分时合流送译，导致 MT 将多行对话/段落打散融合成大散文段，造成行级别失去对齐控制。
   - 依据 `LAYOUT-OUTSIDE-AGENTS.md` 明确标准（"状态：pause，填充过不了，已挂起"）并经用户审查同意，`hang/repeated` 官方挂起延期。

2. **范式几何特征与识别结果 (`step/right_upper_wide`)**：
   - 特征：正文左平直单列对齐，右缘上半部宽展展开（$x_2 \approx x_{\text{wide}}$），在避让右下方插图、侧栏（Callout）或手势构件时产生垂直台阶跳跃向内收缩，下半部各行对齐于内收的平直台阶货架边缘（$x_2 \approx x_{\text{narrow}}$，台阶落差 $\Delta x \ge 24\text{pt}$）。
   - 全库匹配 42 个候选块，全部在阈值 $\le 8.0\text{pt}$ 下命中。

3. **双样本试页实测表现**：
   - **《Breast Play Secrets》印刷页 10**（`bps-p10`，Block `3a634c` / `fd8a1eba`，原英文 14 行，残差 0.0）：
     - 中文左缘全部 9 行严格对齐在 $x=36.00$。
     - 上半部宽区（Line 0 ~ Line 5）右缘宽度对齐在 $391.2\sim 392.5\text{pt}$。
     - 避让区（Line 6 ~ Line 7）右缘台阶收缩至 $379.0\text{pt}$ 与 $362.8\text{pt}$，与右下方人物插图保留 $>28\text{pt}$ 充分安全间距。
     - 短尾行（Line 8）自然收于 $x=266.7\text{pt}$。垂直行距恒定为标准 **$18.0\text{pt}$**。
     - dual：`tmp/fill-right-upper-wide/bps-p10/Breast Play Secrets.no_watermark.zh-CN.dual.pdf`。
   - **《Erotic Massage For Better Sex》印刷页 57**（`em-p57`，Block `826d4e` / `72dc0a94`，原英文 10 行，残差 0.0）：
     - 中文左缘全部 7 行严格对齐在 $x=231.00$。
     - 上半部宽区（Line 0 ~ Line 2）右缘为 $510.0\sim 511.6\text{pt}$。
     - Line 3 发生陡降阶梯跳变（**台阶落差达 $140.0\text{pt}$**），下半部窄区货架（Line 3 ~ Line 5）右缘严格稳定在 $370.0\sim 370.5\text{pt}$，完美避开右下部圆形手势插图。
     - 短尾行（Line 6）自然收于 $x=303.0\text{pt}$。垂直行距恒定为标准 **$15.0\text{pt}$**。
     - dual：`tmp/fill-right-upper-wide/em-p57/Erotic Massage For Better Sex.no_watermark.zh-CN.dual.pdf`。

4. **质量门禁**：
   - 源文件只读验证：OneDrive 全部书籍原文件大小与 mtime 完全未变。
   - 单元测试：`tests/test_line_edges.py tests/test_paradigm_catalog.py tests/test_sentence_paragraph_repair.py` 118 个测试全部通过。
   - 静态检查：`ruff check` 100% 通过。

## 2026-11-02 — hang/deep（深悬挂缩进范式）核验通过与绕图折行断段修复

1. **范式几何特征与核验通过 (`hang/deep`)**：
   - 特征：首行外凸位于顶格平直边界（$x_0$），后续续行向内深悬挂缩进 $\ge 48.0\text{pt}$，典型用于正文避让左侧装饰条、引言（Pull Quote）或侧栏插图。
   - 样本核验：《Magic Hands》第 10 印刷页（`magic-hands-p10g`，Block `6550c2`，9 行段落，残差 0.0）：
     - 首行起始左缘 $x=102.00$（跨全栏位于引言上方），中文续行 5 行严格对齐于 $x=294.00$（$\Delta x = 192.00\text{pt}$）。
     - 与左侧金黄色引用装饰竖线及引言正文（$x=54.07\sim 262.07$）保留 $>31\text{pt}$ 安全间距，段末行自然收束于 $x=474.00$。
     - dual：`tmp/fill-hang-deep/magic-hands-p10g/Magic Hands.no_watermark.zh-CN.dual.pdf`。

2. **绕图折行断段与译文撕裂根治 (`sentence_paragraph_repair.py`)**：
   - 缺陷排查：
     - 在《Orgasmic Sex Positions》第 30 印刷页中，第 3 段正文围绕左下方人物插图排版（前 2 行全宽 $x=84/66..550$，后 6 行收窄避让插图 $x=312..550$）。
     - 原 `_left_continues` 强制要求行首水平位移 $\Delta x \le 8.0\text{pt}$，由于该段避让插图使左边缘向右发生 $246.0\text{pt}$ 台阶跳跃，被错误切分为两个独立段落。
     - 造成双重缺陷：
       1. 语意被生硬切断，第 1 行末 `...your pubic` 与第 2 行首 `mound grinding into hers...` 分开送译，导致 `mound` 孤立误译为“土墩”（“研磨式摩擦到她的土墩上”）；
       2. 上半段收于 $y=443.5$，下半段起于 $y=505.2$，中间产生多达 **$61.7\text{pt}$ 的巨大垂直空白洞**。
   - 修复实现：
     - 在 `sentence_paragraph_repair.py` 中新增 `_wrap_continues` 与 `_lines_continue`：当上下行右边界严格齐平同一栏宽（$|x_{2,\text{upper}} - x_{2,\text{lower}}| \le 8.0\text{pt}$）且处于句中未完接续时（非句末终止符、小写开头或中继词结尾），允许跨阶梯合流为同一段落。
     - 在 `tests/test_sentence_paragraph_repair.py` 中添加 `test_wrap_continuation_around_side_figure_joins` 单元测试。
   - 效果核验：
     - 重新渲染：`tmp/fill-hang-deep/osp-p30b/Orgasmic Sex Positions.no_watermark.zh-CN.dual.pdf`。
     - 8 行正文完整合并，自动精准命中范式 `step/left_upper_wide`（残差 1.85，阈值 8.0）。
     - 排版前 2 行全宽，后 4 行紧密绕过人体插图；Line 1 到 Line 2 垂直行距为标准的 $15.0\text{pt}$（$61.7\text{pt}$ 垂直空洞彻底消除）。
     - 译文完整连贯，`pubic mound` 正确译为“阴阜”（“将你的阴阜研磨式摩擦放进她的身体里”），“土墩”彻底消失。
     - 用户审查确认「过」。

## 2026-11-02 — bow/right_bulge（右弧形向外凸出避让）双语试页双样本核验通过

1. **范式几何特征与识别结果 (`bow/right_bulge`)**：
   - 特征：正文左平直、右缘在避让圆形/凹形背景大图时向外弧形凸出展开（中间行比首尾行宽出 $\ge 12\text{pt}$），随后平滑收拢回弹。
   - 全库匹配 13 个文本块，全部以 `residual = 0.0` 命中。
   - 目录与行边测试：`tests/test_line_edges.py` 与 `tests/test_paradigm_catalog.py` 110 项全绿。

2. **双样本试页实测表现**：
   - **《Breast Play Secrets》印刷页 30**（`bps-p30`，Block `8a4455`，27 行长段落，残差 0.0）：
     - 中文左缘 21 行严格对齐在 $x=36.00$。
     - 右缘由起始行 $x_2=261.88$（EN $262.90$）平滑外凸展开，在第 17 行到达峰值 $x_2=334.19$（EN 原行 $334.70$），随后收回至 $x_2=323.60$，短尾行收于 $x_2=96.00$。
     - 严格保持 $18.0\text{pt}$ 垂直行距节拍，与右侧背景大图（xref 530）弧形边缘贴合规整，无压图或外溢。
     - dual：`tmp/fill-right-bulge/bps-p30/Breast Play Secrets.no_watermark.zh-CN.dual.pdf`（1883392 字节）。
   - **《The Art of Coming Together》印刷页 15**（`act-p15b`，Block `7b40e6`，16 行段落，残差 0.0）：
     - 中文左缘 11 行严格对齐在 $x=36.00$。
     - 右缘由起始行 $x_2=300.45$（EN $301.54$）外凸展开，第 6 行达峰值 $x_2=339.75$（EN 原行 $341.63$），随后收回至 $x_2=294.14$，短尾收于 $x_2=243.07$。
     - dual：`tmp/fill-right-bulge/act-p15b/The Art of Coming Together.no_watermark.zh-CN.dual.pdf`（864008 字节）。

## 2026-10-30 — 目录项防合流（未判过）

目录行按源基线钉回。源目录的点线和下划线画在中文标题与页码之间。源 PDF 的 mtime 与大小未变。不要覆盖 `fosr-p3` 到 `fosr-p3u`，也不要覆盖 `dhd1-p2` 到 `dhd1-p2k`。

- `tmp/fix-toc-merge/fosr-p3v/Female Orgasm Secrets Revealed.no_watermark.zh-CN.dual.pdf`（278794 字节）。第六章标题是「如何给她一分钟口交」。点线仍是 5.44pt。没有源点线的条目保持空白。用户确认过。
- `tmp/fix-toc-merge/dhd1-p2l/dhdmodule1.no_watermark.zh-CN.dual.pdf`（454944 字节）。「关系周期」「女性对性失去兴趣的原因」「性欲望男人和女性的区别」三条节标题到页码之间是下划线。子条目没有下划线。

## 2026-10-30 — hang/shallow 试页核验与首行悬挂排版修复

1. **范式与修复摘要**：
   - 范式：`hang/shallow`（浅悬挂缩进，首行凸出，后续缩进 12–48pt）。
   - 根因 1（`line_edges.py`）：首行基线因中文行高大于英文 source pitch 而略低于第一层 slab 底部时，`_interval_on_levels` 误滑入第二层 slab，导致首行外凸丢失；增加首行顶部判定防护（`if slabs[0][0] is samples[0] and y_top >= samples[0].top - 1.0: host = samples[0]`）。
   - 根因 2（`typesetting.py`）：`_first_body_unit_index` 对非项目符号、非数字编号的段落默认返回 `0`，排版循环将第 0 个单元误当列表正文起始强推至 `edges_body_left`，导致首行整体缩进；改为无 marker 时严格返回 `-1`。
   - 测试通过：`tests/test_line_edges.py` 57 项全过，`tests/test_paragraph_alignment.py` 63 项全过，`test_layout_plan.py` 105 项全过。`ruff check` 无告警。

2. **样本核验判定（依用户审查指令更新）**：
   - **《Last Longer Tonight》印刷页 17**（`llt-p17`）：
     - 条目 `e)` 首行靠外在 128.0，后续续行对齐在 146.0（差值 18.0pt）；序号 2 靠外在 74.0，后续在 92.0。首行外凸与续行缩进完全吻合。
     - **审查判定：整体可以（已过）。**
   - **《Hot Licks: Module 4》印刷页 40**（`hl4-p40`，APA 参考文献）：
     - 结构对齐整体可以（首行 144.0，续行 162.0），但部分条目为学术人名/期刊专有名词被 DeepLX 保留英文，仅少量完整从句被译出中文。
     - **审查判定：用户明确指示文献类不要求翻译，不再作为试页测试项，直接去掉。**
   - **《Female Orgasm Secrets Revealed》印刷页 3**（`fosr-p3`）与 **《Double Her Desire》印刷页 2**（`dhd1-p2`）：
     - 均为目录（TOC）页面，多条独立目录项被并为单一文本块按连贯段落折行，破坏目录行结构。
     - **审查判定：完全不对，不可过，目录项不得按悬挂正文段落合流。**



## 2026-10-30 — step/right_lower_wide 试页核验

口袋和下面的矩形栏之间如果已经有段落，上拉会停住。标题不会被当成下一段正文推走。OneDrive 源 PDF 的 mtime 与大小未变。`tmp/fill-lower-wide/orgasmic-sex-positions-p44i/` 仍是 441143 字节（2026-10-23 14:08），这次没有覆盖。

1. **《Explosive Ejaculation Stimulation》印刷页 10**（PDF 第 10 页）
   - 原始文本块 digest `5a79623e893dd8cd`，22 行，`step/right_lower_wide` 残差 0.0。布局日志块 `e4b9b5` 同样命中，残差 0.0。
   - 剥掉短尾后，台阶切在第 15 行（0 起，y=582.5）。左缘齐在 36.0。上半段右缘中位 286.8，下半段右缘中位 323.7，差 36.9pt。
   - 右侧照片从 x=255.3 起。中文正文保持 12pt，左缘 36.0。前 17 条满行的右缘贴着同一高度的英文行，偏差 −1.6…+1.6pt，没有比英文更深入照片。中文在第 18 行收束（右缘 132.0）。英文其后还有 4 条宽行（右缘 321.6–323.9），没有对应中文，末行也没有被拉到 324。
   - 三行 21pt 黄字停在引言和正文之间。中文 y（向下）195.9 / 238.9 / 281.9，英文 195.3 / 231.2 / 267.2。第二行「让潮喷如此」比英文低 7.7pt，第三行低 14.7pt。
   - **大字号标题装饰下划线剔除修复**：原英文三行黄字下方有 3 条 3.0pt 粗的黄色矢量下划线（长度与英文行长匹配）。因中文行高与长度变化，原英文下划线残留并横穿中文第 2、3 行，且向右悬空多达 171pt。修复 `styles_and_formulas.py`：纠正 Document IL 坐标系下段落包围盒的上下边界方向判断（$y=0$ 在页面底部，下划线位于 $y \le \text{para\_box.y}$），字号提取字段名修正为 `pdf_character` 并按字号动态放宽下划线判定距离（$0.35 \times \text{font\_size}$），支持 3.5pt 粗细的矢量线条剔除，并增加全宽分割线宽度保护。重新渲染后中文侧 3 条残留下划线完全清除（ZH drawings: 0），英文侧完整保留。
   - dual：`tmp/fill-right-lower-wide/ees-p10c/Explosive Ejaculation Stimulation.no_watermark.zh-CN.dual.pdf`（1467558 字节，16:00 重渲）。`ees-p10` 那份黄字在页底，不要用。

2. **《Orgasmic Sex Positions》印刷页 44**（PDF 第 44 页）
   - 目录 digest `8c65ba3eb697667b` 不在原始文本块上。现场轮廓 digest `535de1d0a83a4863`。布局日志块 `c49366` 命中 `step/right_lower_wide`，残差 0.0。
   - 剥掉短尾后，台阶切在第 19 行。左架 66.0（英文首行左缘 84.0）。上半段右缘中位 213.9，下半段右缘中位 549.8，差 335.9pt。
   - 插图 x=222.0–612.0，y=203.9–520.0。中文窄栏 15 行，字号 12.50，左缘 66.0，右缘 210.0–211.7，距插图左缘 10.3–12.0pt。第一宽行 y=527.2（在插图底边之下），右缘 547.0（英文 549.8）。第二宽行右缘 418.0，没有拉满。
   - 新 dual 的正文行框与 p44i 一致。标题「飞天狗」左缘是 66.4（p44i 为 114.0），y=288.4。
   - dual：`tmp/fill-right-lower-wide/osp-p44/Orgasmic Sex Positions.no_watermark.zh-CN.dual.pdf`（441151 字节）。切片：同目录 `step-crop.png`、`cn-column.png`。

## 2026-10-30 — bow/right_inset（右弧形内凹避让）双语试页双样本核验通过

1. **范式几何特征与识别结果 (`bow/right_inset`)**：
   - 几何定义：左平直（左缘极差 $\le 8.0\text{pt}$），右侧因避让圆形/弧形人体或插图而呈现「单峰内凹步进」；
   - 候选语料全库 27 块全部精准收敛，双样本实测残差均为 **0.00**（阈值 8.0）：
     - 样本 1：《Sizzling Squirting Positions》第 12 印刷页（Block `71c0dd`，20 行中文避让模特手肘外凸弧线，残差 0.0）；
     - 样本 2：《Sizzling Squirting Positions》第 30 印刷页（Block `bddf4c`，15 行中文平滑沿胸肩弧度收拢，残差 0.0）。

2. **排版质量与视觉安全评估**：
   - **零碰撞与 Gutter 保证**：中文字符与右侧高精插图之间保留 $>10\sim 15\text{pt}$ 完整安全距离走廊，零压图、零文字溢出；
   - **两端对齐与末行自然收尾**：中间行均匀填满各自有效列宽，段末行自然靠左短行，未触发错误的分散拉伸；
   - **测试保障**：109 项范式目录测试与行边测试 100% 通过。
   - 审查报告与切片：`bow-right-inset-review.md`。

## 2026-10-30 — 列表行内标题翻译、样式泄露与标点符号标准化修复

1. **行内标题样式泄露消除 (`paragraph_split_policy.py` / `styles_and_formulas.py`)**：
   - 根因分析：在未发生样式拍平（`flatten_dominant_run_in` 返回 `False`）时，`remember_run_in_lead` 仍无条件记录了标题样式；排版阶段 `apply_run_in_lead_style` 误判并将小号紫色粗体字强行刷至整个问句末尾（如 `d) TimE: 这一切都是为了性吗？` 全句染紫变粗）；
   - 修复：
     - 在 `paragraph_split_policy.py` 增加 `forget_run_in_lead(paragraph)`，当不拍平时立即注销，避免后续阶段误用；
     - `apply_run_in_lead_style` 增加防护：若段落已由 `ILTranslator` 生成具有 2 种及以上字体的 compositions，禁止二次覆盖；
     - `_title_clause_end` 补充中英文冒号 `：:` 为标题截断标志，杜绝向正文句子外溢。

2. **样式标记内部混合大小写与标题规整 (`il_translator.py` / `text_recovery.py`)**：
   - 根因分析：排版字体采用 Small Caps 导致提取出大小写交替的单词（`TimE:`, `aTTEnTion:`, `sEducTion:`），在经过 style marker 时被 MT 判定为代码标识符而原样保留或未加翻译；
   - 修复：在 `text_recovery.py` 增加 `normalize_style_span_text`，处理 decorative mid-caps 后使用句式首字母大写（Sentence Case，如 `Attention:`, `Seduction:`），MT 识别为规范标头并准确翻译（`注意：`, `诱惑：`）；同时统一将 CJK 字符后的英文冒号 `:` 转为规范全角中文冒号 `：`。

3. **列表标号与括号规范化 (`list_marker_repair.py`)**：
   - 扩展 `LIST_MARKER_RE` / `TRAILING_LIST_MARKER_RE` 匹配范围，涵盖全小写字母 `[a-z]` 以及小写括号标号；
   - 增加 `LEADING_LIST_MARKER_PAREN_RE` 修复 MT 将 `a)`、`e)` 误译为全角 `a ）`、`e ）` 的问题，统一转回规范紧凑半角括号 `a) `。

## 2026-10-30 — Phase 4 段末短行剥离重构与全库 999 块新增匹配

1. **几何剥离底线守卫与弹性剥离重构 (`outline.py::_strip_short_tail`)**：
   - 消除 3 行与 4 行短段落体量饿死（Body Starvation）：
     - 范式（`_rag`, `marked`, `_hang_indent` 等）普遍硬性要求 `len(body) >= 3`；
     - 原逻辑在 `len(kept) == 3` 时仍盲目 pop，导致短段落被削减至 2 行后被所有范式无差别拒绝；
     - 重构为守卫 `len(kept) >= 4`，确保剥离后 `len(body)` 永不低于 3 行；
   - 针对 ≥8 行长段落扩展 `max_drop = 3`，增强对签名、落款及多行短尾的容错率；
   - 限制 ≤6 行短段落最多剥离 2 行，防止将阶梯或圆弧下半段切除。

2. **全量语料库回归实测增益 (66,300 块)**：
   - 全库 19,162 个多行正文块实测：**净新增精准匹配 +999 个块**！
   - 新增分布：`rag/right_edge` +371、`rag/deep_right` +164、`mark/bullet_hang` +151、`mark/serial_hang` +132、`hang/shallow` +86、`mark/serial_plain` +64、`hang/deep` +17、`mark/bullet_plain` +14；
   - **全库破坏性回退：0（Regressions = 0）**。

3. **双语试页核验**：
   - 样本 1：《7 Day Orgasm》第 3 天 第 10 页（块 `8b71d2` 准确匹配 `mark/serial_plain`，整页匹配跃升至 8 块）；
   - 样本 2：《7 Day Orgasm》第 4 天 第 10 页（`rect/full_column` 与 `rect/light_column` 规整排版）；
   - 审查报告与切片：`strip-short-tail-review.md`。

## 2026-10-29 — Phase 3 左侧环绕避让范式落地、行内标头接续与正文列表两端对齐

1. **Phase 3 左侧环绕避让范式族全部就绪 (`bow/left_*`, `step/left_*`)**：
   - 补齐左侧 5 个排版避让范式：
     - `bow/left_inset`: 右平直，左缘向内凹入一步后回弹（如绕圆形插图）；
     - `bow/left_bulge`: 右平直，左缘向外凸出一步后收回；
     - `step/left_upper_wide`: 右平直，左缘上宽下窄阶梯；
     - `step/left_lower_wide`: 右平直，左缘上窄下宽阶梯；
     - `step/left_spur`: 右平直，仅单行向左伸出阶梯。
   - 在 `outline.py` 中增加左侧阶梯与凹凸特征判据（`left_step`, `left_bow`, `_step_kind_left`, `_bow_kind_left`），并在 `_is_rag_edge` 增加对左侧范式候选的排他性保护，杜绝左毛边误吞。
   - 在 `load_catalog()` 中注册全部 5 个左侧范式（阈值 `8.0`），全套 57 项范式目录测试与 22 项行边提取测试全绿。

2. **行内彩色标头接续与假断段消除 (`paragraph_split_policy.py`)**：
   - 修复 `line_fills_differ` 将行内彩色引言（如紫色标头后接黑色正文）误判为不同段落的问题：
     - 原逻辑直接对比首行全部字符与次行字符的图形状态指令集 `{purple, black} != {black}`，导致 Bullet 1 第一行行末被强行切成独立短段落，第一行右侧留下 142pt 空白；
     - 增加行尾图形状态与下一行前瞻匹配：当上一行行尾（`prev_chars[-5:]`）正文颜色与下一行一致时，判定为同一段落内行内彩色标头，不再假切分。

3. **正文列表与分栏段落两端填满对齐 (`typesetting.py` / `shaped_pocket_stack.py`)**：
   - 将列表项与矩形分栏正文纳入 `_alignment_in_frame` 的两端对齐管理（`framed=True`），使普通列表项的中间行执行 `align_frame_line` 填满至右边距；
   - 重构 `short_line` 判定：由粗暴的 `slack > 24pt` 改为字符级拉伸步长校验 `step = slack / (n_glyphs - 1)`，仅当 `step > 3.5pt` 或字符数 `< 4` 时视为短行，确保正文中短空隙行均匀分散对齐，段末行保持左对齐。

4. **双语试页核验与用户确认**：
   - 样本 1：《7 Day Orgasm》第 6 印刷页（PDF 第 6 页 / 0-indexed page 5）：
     - Bullet 1 首行不再腰斩，L1~L4 完美左右对齐填满至 `x2 = 1183.8 pt`；
     - Bullet 2 中间行全部齐平至 `1183.8 pt`；
     - Bullet 3 贴合圆形图片轮廓平滑环绕（`bow/left_inset`，10 行轮廓，Regular 11.8pt 字体）；
     - Circle 确认「过」。
   - 样本 2：《Better Sex Through D/s》第 7 印刷页：左上宽阶梯环绕（`step/left_upper_wide`），Circle 确认「过」。
   - 报告与切片：`day7-p6-justification-fix-report.md`、`left-wrap-review.md`。

## 2026-10-28 — 首行缩进范式 indent/first_line 构建与人体曲面避让彻底修复

1. **首行缩进独立范式落地 (`indent/first_line`)**：
   - 注册独立范式 `babeldoc/format/pdf/document_il/utils/layout_plan/paradigms/indent/first_line`（阈值 `8.0`）；
   - 判据完善 (`outline.py::_first_line_indent`)：首行缩进 $7.0 \le \Delta \le 60.0\text{pt}$，正文行高精度列齐（极差 $\le 2.5\text{pt}$），遇阶梯外扩避让则主动拒绝（$\Delta > 2.0\text{pt}$），杜绝曲面插图误吞；
   - 填充防撞与对齐 (`indent/first_line::fill`)：严格保留各行扫描左界，末行延展至正文列宽，杜绝过早折行；
   - 排他避让：`rect/light_column`、`rag/right_edge` 与 `taper/right_pin` 均对检测到的首行缩进段落主动让位。

2. **复合人体轮廓避让与压图彻底根治**：
   - **中部女性手臂/乳房大面积压图彻底根治 (`taper/right_pin`)**：
     - 英文原版避让凸出人体（$60\text{pt}$ 弓形包裹），此前因最后两行微收 $10\text{pt}$ 被旧 `one_direction` 苛刻拒绝而沦入默认 `rect_flow`，导致全部 7 行中文拉直在 $x=290$ 碾压人体；
     - 拓展 `_runs_one_way` 支持深避让（$\ge 18\text{pt}$）与尾部微回弹（$\le 12\text{pt}$ 且 $\Delta_{\text{last}} \le 0$），成功认领并以 $0.6066\text{pt}$ 残差高精度贴合人体流动，重叠率直接归零。
   - **顶部女性肩膀处擦边彻底分离 (`rect/light_column`)**：
     - 修复末行被强拉至最左界 `outer_left = 224.0` 的问题，中文两行保留自身避让起点 $x = 236.0$；
     - 像素级实测证实文字相对人体最外凸起享有 $>7.4\text{pt}$ 净空安全间距，完全消除摩擦。
   - **样 2（《Female Pleasure Spots》第 17 页）后背内衣曲面**：
     - 收紧正文散度判定（$\le 2.5\text{pt}$），杜绝将后背内衣弧线错判为首行缩进，内衣压字彻底消除。

3. **双语试页核验与用户确认**：
   - 样本 1：《Double Fingering Delight》第 10 页全页（肩膀安全分离、中部人体 0 压图贴合、底部标准首行缩进 8.0pt），用户确认「过」；
   - 样本 2：《Female Pleasure Spots》第 17 页（排除误判，后背内衣 0 压字），用户确认「过」；
   - 审查报告与实页切片：`visual-comparison-double-fingering-p10.md`、`indent-first-line-review.md`。

## 2026-10-28 — 左齐右毛边短段落范式真空修复与 rag/right_edge 范式增强

1. **短段落转折自适应下限与悬挂排他性保护 (`outline.py`)**：
   - 针对正文右毛边（`stray_is_low=True`，即左平齐右参差），在行数 $3 \le n \le 5$ 时将转折门槛自适应调整为 $\text{turn\_count} \ge 1$，消除 3 行段落因数学极限（最多 1 次转折）及 4~5 行同向微增/微缩段落被硬性判定为 `unmatched` 的缺陷；
   - 在 `_rag` 中增加显式 `_hang_indent` 排他判定，杜绝左毛边误吞悬挂缩进；
   - 恢复 `line_edges.py` 中 `interval_for_line_edges` 纯净高度层级查询，全套 229 项单元测试全绿。
2. **全量语料库回归与实测收益**：
   - 全库 66,300 个块实测：新增精确匹配 425 个多行正文段落，0 回退（Regression=0），0 冲突（Conflict=0）。
3. **双语试页核验与过关**：
   - 样本 1：《All Tied Up》第 7 印刷页（PDF 第 8 页，块 `0a9753`，5 行正文）精准匹配为 `rag/right_edge`（残差 0.00），用户确认「过」；
   - 样本 2：《All Tied Up》第 8 印刷页（PDF 第 9 页，块 `e11cd8`，4 行正文）精准匹配为 `rag/right_edge`（残差 0.00），用户确认「过」；
   - 审查报告与切片：`rag-right-edge-review.md`。

## 2026-10-28 — mark/bullet_plain 范式核验与全 mark 族收官

1. **mark/bullet_plain 范式核验**：
   - 依赖排版引擎对显式 `line_edges` 的伪悬挂抑制机制，平直圆点列表严格按原书几何行左缘对齐，圆点后文字保持 10.0pt 标准缩进；
   - 样本 1：《Bigger Deeper》第 4 页（15 行平直圆点目录列表），中文圆点统一对齐于 `665.3 pt`，正文对齐于 `675.3 pt`，排版严整；
   - 样本 2：《Double Fingering Delight》第 4 页（24 行平直圆点列表），中文圆点统一对齐于 `670.3 pt`，正文对齐于 `680.3 pt`，无异常阶梯与列宽偏移；
   - 审查报告与切片：`bullet-plain-review.md`。

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

已核验通过（2026-11-03）：`center/axis` 引言（`tmp/fill-center-axis/em-p22/` 与 `tmp/fill-center-axis/em-p72/`，ALIGNMENT="center" 居中对齐）；Erotic Massage 印刷页 34 的 `rag/right_edge` 停着。不要重渲页 34。

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
