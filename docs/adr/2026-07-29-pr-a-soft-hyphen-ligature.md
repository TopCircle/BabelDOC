# ADR: PR-A Soft-hyphen / ligature cross-run recovery

## Status
Accepted — implementing 0.6.4.33

## Context
OA dual p7/46/71 show fragments: `di`/`ff`/`ﬃ`, `cli toral`, `di- ﬀerent` style
splits. MT then leaves EN crumbs on the ZH half.

## Decision
1. Keep ligature expand + hyphen soft-rejoin.
2. Add **space-split Latin rejoin**: `prefix\s+continuation` when
   `should_soft_rejoin(continuation)` (lowercase, not free-standing word).
3. Add **hyphen-no-space** soft rejoin: `prefix-continuation` same gate.
4. Apply only in `text_recovery` post-pass used by `get_char_unicode_string`.
5. Do **not** change `stream_order` or plain-text reorder.

## Consequences
- Fixes mid-word spaces from false word-boundary gaps after ligature expand.
- Risk of over-glue controlled by existing `should_soft_rejoin` / word list.
- Wrong paint order (`ff` before `di`) remains ParagraphFinder issue (out of scope).

## Acceptance
- Unit tests for di/fferent, cli/toral, Trigasm- actually refuse.
- `pytest tests/test_figure_il_invariants.py tests/test_stream_visual_order.py -q`
