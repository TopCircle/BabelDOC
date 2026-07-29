# ADR: PR-C1 Skip-reason audit report (zero behavior change)

## Status
Accepted — implementing 0.6.4.34

## Context
OA dual ZH half shows many untranslated EN blocks (p8/9/41…). Operators
cannot tell intentional skip (header, ultra-narrow callout, figure label)
from silent MT drop. PR-C plans both **audit** and **skip-bound fixes**;
changing skip predicates without observability caused prior whack-a-mole.

## Decision
1. **C1 only**: emit `skip_report.json` under working dir when
   `debug` or `working_dir` is set (same gate as `translate_tracking.json`).
2. Enumerate skip reasons at **existing** early-return sites; do **not**
   change any skip predicate truth value.
3. Reasons (stable string values):
   - `figure_text`, `header`, `footer`
   - `ultra_narrow`, `pullquote`
   - `pure_numeric`, `placeholder_only`, `too_short`, `vertical`
   - `empty_composition`
4. Each event: `page_number`, `paragraph_id` (`debug_id`), `reason`,
   `unicode_preview` (≤80 chars), optional `layout_label`.
5. **C2** (separate PR) may tighten false-positive skips using this report.

## Consequences
- Zero layout / translation behavior change when report is disabled or enabled.
- Thread-safe collector (MT runs in pool).
- LLM-only path records via the same `ILTranslator.skip_report` instance.

## Acceptance
- Unit tests: reason enum, record+JSON shape, header vs figure classify.
- `pytest tests/test_figure_il_invariants.py tests/test_skip_audit.py -q`
- No change to `stream_order` / plain-text reorder.
