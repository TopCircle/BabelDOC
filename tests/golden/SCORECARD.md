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
- `cjk_ragged` — poor CJK line breaks / scale crushed
- `quote` — quote column vs body collision
- `style` — bold markers lost / B0B1 debris
- `soh` — U+0001 spaces in extractable dual text
- `missing` — paragraph empty or merged wrong

## CI vs local

| Gate | CI | Local |
|------|----|-------|
| Unit tests + synth fingerprint | yes | yes |
| Orgasms full dual pixmap | no | scorecard |
| SSIM vs previous golden PNG | later quality PRs | optional |
