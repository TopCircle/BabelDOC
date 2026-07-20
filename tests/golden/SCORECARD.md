# Dual quality operator scorecard

Local checklist for Orgasms-class dual PDFs. **Not required for CI green.**

## Current operator baseline (2026-07-20) — freeze here

**Code baseline (layout intent):** fork tip on **`7e9a984` figure golden quality**, plus
merged upstream **v0.6.4** (raster pixel budget + Latin/CJK line-advance floor).
Re-check figure dual after the 0.6.4 line-spacing change if vertical layout shifts.

**Figure golden (vector arXiv) — primary layout baseline**

| Item | Value |
|------|--------|
| Source | `tests/golden/translate.cli.text.with.figure.pdf` |
| Dual (local, gitignored `*.pdf`) | `translate.cli.text.with.figure.no_watermark.zh-CN.dual.pdf` |
| Operator status | **Normal / accepted baseline** (regenerated 2026-07-20) |
| Expect | Header title/author/affil/date page-centered on ZH half; body ~9–10pt; left-col readable (no ~6pt crush / huge white band) |

**Do not** treat later WIP commits as the bar for this PDF until re-baselined.

### Paused: dual-layer / searchable-image work (font.unknown)

Commits after `7e9a984` (font-face split, auto OCR, OCR scale, PR-08 package extract, …) were aimed at **searchable dual-layer PDFs** (e.g. `translate.cli.font.unknown.pdf`). That track is **not finished** and was **paused**.

| Item | Notes |
|------|--------|
| Why paused | Incomplete quality; also regressed figure golden when re-tested (soft mid-sentence font split, etc.) |
| `main` disposition | Force-reset to `7e9a984` (2026-07-20); tip history still in reflog (`004ba7b` …) if needed |
| Resume later | Bisect / re-land dual-layer fixes **without** breaking figure baseline metrics (affil center, crush ratio, left-col gap) |
| Prior notes | font.unknown OCR backlog was documented under earlier SCORECARD revisions; re-add when that track resumes |

### Regression probe (when dual-layer work resumes)

Same source dual, frozen translation cache, compare vs `7e9a984` dual:

| Metric (ZH half) | Baseline-ish | Flag as regression |
|------------------|--------------|--------------------|
| Affil mid vs page center 306 | ≈306 | \|mid−306\| &gt; 25 |
| Chars &lt; 7pt / total | ~1% | &gt; 10% |
| Max left-col vertical gap (body) | ~76pt | &gt; 120pt |
| Long body block contains fig labels | no | yes (混段) |

Figure labels stay in the source language by default (`translate_figure_text=False`;
UI: **Translate figure text** off). Opt in to translate chart annotations.
Independent of **Translate table text** (RapidOCR table path).

## Rating scale

| Score | Meaning |
|------:|---------|
| 1 | Unreadable / broken (missing body, mid-photo text, SOH spam) |
| 2 | Major defects on multiple pages |
| 3 | Usable with obvious layout defects |
| 4 | Minor defects only |
| 5 | Near original layout quality |

## How to run a baseline (local)

1. Translate with frozen / FixedMap or your production DeepLX config.
2. Export dual PDF + optional debug IL JSON (`typsetting.json`).
3. Optionally: `python -m babeldoc.tools.dual_quality_check --self-check`
4. Fill the table below (PDF page numbers as in a viewer, 1-based).

## Documents

### Longer Stronger Orgasms For Him

| PDF page | Defect class | Baseline (1–5) | After PR | Notes / artifact paths |
|---------:|--------------|----------------:|---------:|------------------------|
| *TBD* | figure_wrap | | | e.g. mid-photo body |
| *TBD* | cjk_ragged | | | |
| *TBD* | quote | | | |
| *TBD* | style / bold | | | |

### Module 1

| PDF page | Defect class | Baseline (1–5) | After PR | Notes / artifact paths |
|---------:|--------------|----------------:|---------:|------------------------|
| *TBD* | ocr / extract | | | prefer `module_1_OCR.pdf` when needed |
| *TBD* | figure_wrap | | | |

## Defect classes

- `figure_wrap` — body collides with photo / wrong residual strip
- `cjk_ragged` — poor CJK line breaks / scale crushed / 词组断开 / 标点行首行尾
- `quote` — quote column vs body collision
- `style` — bold markers lost / B0B1 debris
- `soh` — U+0001 spaces in extractable dual text
- `missing` — paragraph empty or merged wrong

## PR-04 CJK notes (local check)

After rebuild with BabelDOC main ≥ PR-04:

- Prefer **fuller intermediate Chinese lines** (DP `cjk_mode` + fill weight).
- **Kinsoku**: fullwidth `。，）」` not at line start; `（【「` not at line end.
  Half-width `.,%/` are **not** line-start forbidden (mixed CJK+Latin glue risk).
- zh/ja/ko typesetting forces `cjk_mode=True` even for mixed Latin titles.
- Still score real dual pages by eye; no CI pixmap gate for Orgasms.

## PR-06 multi-interval wrap (local check)

After rebuild with BabelDOC main ≥ PR-06:

- **Synth:** mid-figure should place body on **both** residual pockets (unit test
  `test_multi_interval_layout.py`); left-only figure still starts at figure right edge.
- **Orgasms photo taper:** pages with EN `reference_widths` must not spill full
  rectangular columns into side photos — DP still uses `min(ref, sum(intervals))`,
  placement caps the **leftmost** pocket only.
- **Mid-figure without EN taper:** text may continue into the right pocket on the
  same line (intentional multi-interval wrap). Score `figure_wrap` pages by eye.

## PR-07 paragraph style (local check)

After rebuild with BabelDOC main ≥ PR-07:

- **First-line indent:** body paragraphs keep EN visual indent (absolute pt, not
  shrunk by glyph scale). Flush-left EN must not gain a random indent after ZH.
- **Center/right:** page-centered EN headers (arXiv title/author) stay centered
  after long ZH translation; left-aligned section titles stay left; body-like
  multi-line false centers still forced left (majority near-full original lines).
- **DP consistency:** first estimated line width subtracts indent so DP breaks
  match placement.
- **Golden:** `translate.cli.text.with.figure` — ZH title/author mid near page
  center of the mono/left half, not flush to original left edge.

## CI vs local

| Gate | CI | Local |
|------|----|-------|
| Unit tests + synth fingerprint | yes | yes |
| Orgasms full dual pixmap | no | scorecard |
| SSIM vs previous golden PNG | later quality PRs | optional |
