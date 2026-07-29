# ADR: PR-B Decorative title / chapter header readability

## Status
Accepted — implementing 0.6.4.35

## Context
OA dual shows:
- reverse-paint titles as `WhohaSorgaSMS` / `Sou Loyre a` when layout
  labels them `plain text` (title-only reorder never runs)
- `Chapter1` glued (digit misplaced or no space before number)
- Chapter bar + title as separate short paras → `Chapter1爱与性` after MT

**Hard constraint:** never reopen global plain-text visual reorder
(figure golden `pseudo` → `seudo`).

## Decision
1. **Top-band exception for reverse reorder:** if a run is short single-letter
   decorative **and** reverse/misplaced-digit **and** the paragraph sits in the
   page top band (~12% / ≥72pt), allow reorder even when label is
   `plain text` / `text`. Title and `section_header` unchanged.
2. **Chapter digit spacing:** post-string `Chapter`+digit → `Chapter N`
   (case-insensitive) in text recovery used by `get_char_unicode_string`.
3. **Chapter+title merge:** same-page adjacent short paras: `Chapter N` +
   short title line in top band → one paragraph (space join). Geometric
   guards: both in top band, title not long body, y-overlap/near.
4. Do **not** change skip_header product default; do **not** expand
   reorder to mid-page plain text.

## Consequences
- Mis-labeled chapter titles become readable EN before MT.
- Risk: rare reverse-looking chrome in top band reorders — acceptable.
- Figure body mid-page remains title-gated → invariants stay green.

## Acceptance
- Unit: reverse plain-text mid-page **identity**; top-band plain-text
  reverse **reorders**; Chapter1 → Chapter 1; merge Chapter+title.
- `pytest tests/test_stream_visual_order.py tests/test_figure_il_invariants.py
  tests/test_pr_b_title_header.py -q`
