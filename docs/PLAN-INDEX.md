# Plan / review index (operator)

Last updated: 2026-08-17。**If two docs disagree on what to do next, this table wins.**  
**On main:** W1+B4a+B1e+W4e+formula `{vN}` restore + B4b + **B4e** p91 quote 右侧左齐。**In flight:** **PR-B4c** figure-wrap 撕碎（`execute-plan/pr-b4c-figure-wrap`，已叠在 B4e 上）。**Queued:** **PR-B1i** 章题颜色。**Next:** 操作员 dual 验 p19/p33 后合 B4c，或 B1i。

## Current

| Doc | Role |
|-----|------|
| **[`oa-dual-quality-wave-0.6.4.69.md`](oa-dual-quality-wave-0.6.4.69.md)** | **Active work queue.** Wave order, page gates, PR split (BabelDOC vs DeepLX/CSV). Baseline dual: 0.6.4.69 (`6486fae`). |
| [`../tests/golden/SCORECARD.md`](../tests/golden/SCORECARD.md) | Dual-quality operator checklist + F1–F4 freeze. Queue pointer now follows the wave doc. |
| [`../AGENTS.md`](../AGENTS.md) | Commit bar + pointer to the wave doc. |
| **R0 local harness** | `scripts/oa_r0_skip_report.py` + worktree `/Users/yun/workspace/BabelDOC-oa-r0` (PR-B0). Output: `tmp/oa_r0/`. Identity MT, no DeepLX. |

## Historical (do not schedule from these)

Keep as evidence / architecture background. Status banners at the top of each file.

| Doc | What it was | Why not the queue |
|-----|-------------|-------------------|
| [`architecture-optimization-plan.md`](architecture-optimization-plan.md) | Long-horizon architecture (S1–S3 / L3 done) | “Next L4” is stale; L4 only if wave B4d skip_report proves header kill |
| [`oa-dual-layout-pr-plan.md`](oa-dual-layout-pr-plan.md) | 0.6.4.37 PR-A–D (ligature / title / skip / callout) | A–D landed; remaining OA P0s are in the wave doc |
| [`layout-first-plan.md`](layout-first-plan.md) | LayoutIntent design v2.1 | P0–P2 mostly landed; leftover wrap bugs = wave W4c |
| [`layout-first-coding-plan.md`](layout-first-coding-plan.md) | P0–P2 coding notes | Same |
| [`layout-first-plan-review.md`](layout-first-plan-review.md) | External review of v2 (0.6.4.50) | Snapshot, not a queue |
| [`line-interval-architecture.md`](line-interval-architecture.md) | C0–C3 LineIntervalPlan | C0–C3 landed 0.6.4.64–66; remaining shreds = W4c |
| [`layout-engine-defects.md`](layout-engine-defects.md) | Early wrap/CJK/style defect list | Superseded by layout-first + wave |
| [`p1_acceptance_oa.md`](p1_acceptance_oa.md) | P1 ink-gap accept (0.6.4.50/52) | Closed phase |
| [`visual-layout-acceptance.md`](visual-layout-acceptance.md) | V1–V5 visual bars | Still useful as **criteria**; not a work queue |
| `/Users/yun/workspace/babeldoc_pipeline_review.md` | Three-layer contract review | Keep; §3.2 `{vN}` “unprotected” is **stale** (script now QFOR-protects) |

## OA book-folder reviews

All dated `REVIEW-*` / `PANEL-*` under the Orgasmic Addiction OneDrive folder are **historical snapshots**. Index: that folder’s `README.md`. Do not treat 0.6.4.67 reviews as the current defect list.

## ADRs (still in force)

`docs/adr/2026-07-29-pr-*.md` — skip_report, safer skip, decorative title, narrow callout, ligature. Wave PRs must not reopen those policies unless the wave doc says so.
