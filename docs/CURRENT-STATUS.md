# BabelDOC — 当前状况（2026-10-26）

**布局树:** `/Users/yun/workspace/BabelDOC-layout-paradigms` · 分支 `plan/layout-paradigms-20261008` · HEAD `80ffec9`（已推送 origin）  
**版本:** `0.6.4.95`（`babeldoc/const.py` 与 `pyproject.toml`，未 bump）  
**main:** `/Users/yun/Nextcloud/Project/PDFMathTranslate-next/BabelDOC` 在 `398275a`。当前 Grok worktree 同一提交。产品改动只进布局树。`/Users/yun/workspace/BabelDOC` 已不在。  
**本文件是当前操作员入口。** 换账号粘贴全文是仓库根目录 `GROK_BOT_HANDOFF.md`。两份冲突时以快照日期更新的一方为准，并立刻同步另一份。不要从 `docs/archive/` 排期。`docs/PLAN-INDEX.md` 这次未改。

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
