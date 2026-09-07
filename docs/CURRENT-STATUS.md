# BabelDOC / OA dual — 当前状况（2026-09-07）

**HEAD:** 以 main 尖端为准 · **版本:** `0.6.4.95`（s30 Latin crumb scrub；s31 整本复核） · 仓库 `TopCircle/BabelDOC` `main`  
**本文件是当前操作员入口。** 若与旧 wave / layout-first 计划冲突，以本文件 + `PLAN-INDEX.md` 为准。

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

- `oa-dual-quality-wave-0.6.4.69.md`（旧 wave）
- `layout-first-*.md` / `layout-engine-defects.md` / `line-interval-architecture.md`
- `architecture-optimization-plan.md` / `oa-dual-layout-pr-plan.md` / `p1_acceptance_oa.md`

仍有效：`docs/adr/*`、`docs/visual-layout-acceptance.md`（验收标准）、`tests/golden/SCORECARD.md`（冻结项）。
