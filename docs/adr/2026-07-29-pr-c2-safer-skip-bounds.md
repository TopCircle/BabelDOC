# ADR: PR-C2 Safer header / figure skip bounds

## Status
Accepted — implementing 0.6.4.37

## Context
C1 emits `skip_report.json` but does not fix false skips. OA dual still leaves
body EN when:

1. **Header band** (`skip_header` + `header_height`) catches long `plain text`
   that only geometrically sits in the top strip (first body paragraph / tall
   band), not running chrome.
2. **Figure spatial path** treats shortish body overlapping a large figure
   layout box as in-figure labels (`is_figure_text_paragraph`).

Title was already exempt from header skip; section headers and body-like
prose were not. A stale unit test expected title to be header-skipped
(contradicts SCORECARD / code).

## Decision
1. Shared helpers in ``region_skip.py`` (single source for ILTranslator +
   ParagraphFinder white-fill band).
2. **Header/footer skip** only when geometry is fully in band **and** text is
   chrome-like:
   - Never: `title`, `section_header`, OCR workaround
   - Never: body labels with long unicode (≥48) or tall multi-line body block
   - Yes: short running headers / footers in band
3. **Figure spatial path** (not explicit `figure_text` label):
   - Cap spatial length at 48 (was 64)
   - Reject wide body columns (width ≥ 22% page)
   - Reject prose-like text (several spaces + sentence punct)
4. Pull-quote / ultra-narrow / C1 report unchanged.

## Consequences
- More body MT near page top and beside figures.
- True chrome ("Chapter N / Learn The Trigasm") still short → still skipped.
- Risk: long running header strings could translate — rare; operators can
  raise `header_height` carefully.

## Acceptance
- Unit: long plain text in header band **not** skipped; short chrome **is**.
- Spatial figure: prose body overlapping figure **not** skipped; short label is.
- Title not header-skipped; figure IL + stream_order green.
