# BabelDOC / OA dual — 当前状况（2026-09-04）

**HEAD:** `0c3d179` · **版本:** `0.6.4.93` · 仓库 `TopCircle/BabelDOC` `main`  
**本文件是当前操作员入口。** 若与旧 wave / layout-first 计划冲突，以本文件 + `PLAN-INDEX.md` 为准。

## 仓库卫生（同日）

- `0c3d179`：`docs/CURRENT-STATUS.md` 入口；旧计划 → `docs/archive/`；`tmp/` 清空并 gitignore；根目录 debug 脚本 → `tools/debug/`
- 根目录交接 prompt：`GROK_BOT_HANDOFF.md`（换账号粘贴即可接手；**每次 push 须同步更新**）

## 已完成（本轮 wrap / 引文 P0）

| 主题 | 结果 | 代表提交 / 版本 |
|------|------|-----------------|
| p19 RIGHT_FIXED 锥形 | 头宽≈252（近 EN）、断崖软化、尖端深度改善 | ~`71ae7bc` … `0.6.4.86` |
| p59 LEFT_FIXED | 左缘钉在 ≈101.9；envelope 软化；tip hoist | `f6db1ad` / `0ba4baf` / `c0a0012` |
| p91 左栏红引文 vs wrap | 不再右扩进 wrap；body x0≈245；callout 钳进 design | `094371a` … `0f7cc25` / `0.6.4.91` |
| MT 碎屑（p33/35） | `前戏艺术` / `就有功课` / `这里有机缘` | sanitize + DeepLX `post_clean` |
| 日志噪音 | 重叠重排 WARNING 汇总；探测类 INFO→DEBUG；默认关 debug | `84981ed` / `0.6.4.93` |

关键页扫视（7/12/19/33/35/59/91/120）：**系统级 wrap 碰撞 / 锥形 P0 已基本清完。**

## 运行配置（验证用）

- 脚本：`~/.config/pdf2zh/run_oa_dual.sh`（默认**不加** `--debug`）
- 要排版 dump：`OA_DEBUG=1 ~/.config/pdf2zh/run_oa_dual.sh …`
- 直播 toml：`~/.config/pdf2zh/oa-deeplx.toml` → `debug = false`
- DeepLX 生产脚本 / glossary：`~/.config/pdf2zh/`（及 Nextcloud 同步副本）；**不在** BabelDOC git 内
- 输出目录：`tmp/oa_w1_deeplx/`（本地临时，已 gitignore）

## 遗留问题（按优先级）

### 非阻塞 / backlog

1. **PR-B1i** — 章标题红色（装饰/色策略），未做  
2. **短末行微瑕** — 如 p91 `世界。`、p59 tip `度。`、p120 `内容`（2–3 字，多在 design 内）  
3. **p19 tip-band 可选加深** — 锥形已可接受；再填更深 tip 有碎屑风险  
4. **重叠修正重排失败** — 日志已收敛为每页 1 条汇总；根因（部分页 retypeset 异常）未修，dual 层/OCR 路径会 skip  

### 流程 / 配置

5. DeepLX `post_clean`（cache-hit 再 scrub）仅 live + Nextcloud，不在本仓  
6. 整本 dual 验证：用 `0.6.4.93` 重跑；旧 `tmp/` 中间产物已清理  

## 刻意不从旧文档排期

以下已迁到 `docs/archive/`，仅作历史证据，**不要**当工作队列：

- `oa-dual-quality-wave-0.6.4.69.md`（旧 wave）
- `layout-first-*.md` / `layout-engine-defects.md` / `line-interval-architecture.md`
- `architecture-optimization-plan.md` / `oa-dual-layout-pr-plan.md` / `p1_acceptance_oa.md`

仍有效：`docs/adr/*`、`docs/visual-layout-acceptance.md`（验收标准）、`tests/golden/SCORECARD.md`（冻结项）。
