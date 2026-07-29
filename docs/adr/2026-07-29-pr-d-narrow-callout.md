# ADR: PR-D Configurable narrow-callout mode

## Status
Accepted — implementing 0.6.4.36

## Context
OA dual p8 red figure-adjacent strip (~80pt tall column) cannot fit CJK:
translating yields a vertical one-char-per-line tower. Current code always
skips MT (`keep_en`). Operators sometimes want to force translate + expand
the box instead.

Pull-quote duplicates of body text are a separate product: always keep EN
(skip MT) regardless of mode.

## Decision
1. Config / CLI: ``narrow_callout_mode`` =
   - **`keep_en`** (default): skip MT for ultra-narrow tall right strips
   - **`expand`**: translate; typesetting uses aggressive down-first expand
   - **`translate_body_column`**: same as expand for v1 (width claim via
     existing right/down policy; reserved name for future left-claim)
2. ``should_skip_side_callout_mt(..., mode=...)``:
   - pullquote duplicate → always skip
   - ultra-narrow → skip **only** when mode is ``keep_en``
3. ``box_expand``: ultra-narrow geometry (width &lt; 100pt **or**
   ``is_ultra_narrow``-like tall thin) uses lower content ratio (1.05) and
   always prefers down when right blocked.
4. Default remains **keep_en** so OA dual regenerations stay clean EN chrome
   without tower ZH unless the operator opts in.

## Consequences
- Product is explicit; SCORECARD documents OA p8 default.
- expand mode may still overflow on pathological boxes (no keep_en fallback
  mid-typeset in v1 — operator can switch mode).

## Acceptance
- Unit: keep_en skips ultra-narrow; expand does not; pullquote always skips.
- box_expand ultra-narrow prefers down / lower ratio.
- figure IL + existing side_callout / box_expand tests green.
