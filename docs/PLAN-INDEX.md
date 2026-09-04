# Plan / review index (operator)

Last updated: 2026-09-04。**If two docs disagree on what to do next, this table wins.**

**On main:** wrap / callout P0 cleared through **0.6.4.93** (`84981ed`).  
**In flight:** Circle full-book dual verify.  
**Queued (non-blocking):** PR-B1i 章题红；短末行微瑕；可选 p19 tip-band。

## Current

| Doc | Role |
|-----|------|
| **[`CURRENT-STATUS.md`](CURRENT-STATUS.md)** | **Active status + residuals.** Start here. |
| [`../GROK_BOT_HANDOFF.md`](../GROK_BOT_HANDOFF.md) | **换账号粘贴 prompt**；每次 push 必须同步更新。 |
| [`../tests/golden/SCORECARD.md`](../tests/golden/SCORECARD.md) | Dual-quality checklist + F1–F4 freeze (criteria, not a work queue). |
| [`../AGENTS.md`](../AGENTS.md) | Commit bar + pointer to CURRENT-STATUS. |
| [`visual-layout-acceptance.md`](visual-layout-acceptance.md) | V1–V5 visual bars (criteria). |

## Historical (archived — do not schedule from these)

Moved under [`archive/`](archive/). Status banners / filenames only; not the queue.

| Doc | What it was |
|------|-------------|
| `archive/oa-dual-quality-wave-0.6.4.69.md` | Wave queue @ 0.6.4.69 (superseded 2026-09-04) |
| `archive/architecture-optimization-plan.md` | Long-horizon S1–S3 / L3 |
| `archive/oa-dual-layout-pr-plan.md` | 0.6.4.37 PR-A–D |
| `archive/layout-first-plan.md` (+ coding / review) | LayoutIntent design |
| `archive/line-interval-architecture.md` | C0–C3 LineIntervalPlan |
| `archive/layout-engine-defects.md` | Early defect list |
| `archive/p1_acceptance_oa.md` (+ ink-gap JSON) | P1 ink-gap accept |

## ADRs (still in force)

`docs/adr/2026-07-29-pr-*.md` — skip_report, safer skip, decorative title, narrow callout, ligature.
