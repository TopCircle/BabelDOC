# Dual quality operator scorecard

Local checklist for Orgasms-class dual PDFs. **Not required for CI green.**

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
