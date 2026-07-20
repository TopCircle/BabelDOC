# Golden / dual-quality fixtures

## Baseline source PDFs (operator regression set)

These three inputs under `tests/golden/` are the **canonical visual/layout
baseline documents** for dual quality (local scorecard + future E2E):

| File | Role |
|------|------|
| `translate.cli.plain.text.pdf` | Plain text layout |
| `translate.cli.font.unknown.pdf` | Unknown / odd fonts |
| `translate.cli.text.with.figure.pdf` | arXiv-style page: centered header + figure |

Regenerate duals after typesetting changes (example name):

`translate.cli.text.with.figure.no_watermark.zh-CN.dual.pdf`

**Operator baseline (2026-07-20):** BabelDOC **`7e9a984`** layout intent (plus later
safe stacks: v0.6.4, figure-text skip). The figure dual regenerated for that bar
is the **accepted layout baseline**. Dual-layer / `font.unknown` work is
**paused** and resumes only under Phase A–D gates in [`SCORECARD.md`](SCORECARD.md).

**Header checklist** (figure PDF): ZH title/author/affil/date should each be
**page-centered** on the mono half; `(Dated: …)` must be its **own** short
centered line, not glued onto the last affiliation line.

## What exists (PR-01 + Phase 0 + S1.1)

| Piece | Role |
|-------|------|
| `il_layout_fingerprint(doc)` | Geometry-only refactor gate (no char unicode) |
| `FixedMapTranslator` | Deterministic non-LLM stub (`babeldoc.translator`) |
| `python -m babeldoc.tools.dual_quality_check --self-check` | Smoke: empty-doc fingerprint |
| `--mode ssim --actual-png … --expected-png …` | Optional pixmap SSIM compare |
| **`dual_quality_check --dual PATH`** | **S1.1** multi-page text-layer metrics (crush / min font / SOH hard; vgap soft) |
| `python -m babeldoc.tools.figure_baseline_probe --dual …` | **Phase 0 hard gate:** affil center / crush / left-col gap / fig-label 混段 |
| `figure_baseline_probe --self-check` | CI-safe synthetic dual smoke |

### Which CLI?

| Goal | Command |
|------|---------|
| General dual (multi-page, e.g. All Tied Up 4–26) | `dual_quality_check --dual … --pages 4-26` (**pages are 1-based**) |
| Figure golden single-page hard gate | `figure_baseline_probe --dual … --page 0` (**page is 0-based**) |

Shared geometry helpers live in `babeldoc/tools/dual_layout_metrics.py` (crush + left-col gap).

## What is **not** here yet

- Full PDF → translate → dual E2E golden in CI
- Loading `typsetting.json` / debug IL dumps (write-only JSON today)
- Orgasms/Module-1 CI pixel gates (local scorecard only — see `SCORECARD.md`)
- Dual-layer Phase D (OCR reflow / single face / glyph hygiene) — optional
  (Phase A–C: detect, font-split, OCR scale/box are on main)
- S1.2 EN-residue / open-paren metrics; S1.3 `--profile figure` parity

## Commands

```bash
# library / unit
uv run pytest tests/test_dual_golden_synth.py tests/test_figure_baseline_probe.py \
  tests/test_dual_layout_metrics.py -q

# CLI smoke
python -m babeldoc.tools.dual_quality_check --self-check
python -m babeldoc.tools.figure_baseline_probe --self-check

# S1.1 — multi-page dual metrics (text layer only; no translate)
python -m babeldoc.tools.dual_quality_check \
  --dual path/to/book.no_watermark.zh-CN.dual.pdf \
  --pages 4-26 \
  --half left \
  --profile default \
  --json-out /tmp/dual_report.json

# hard gate on local figure dual (gitignored output PDF)
python -m babeldoc.tools.figure_baseline_probe \
  --dual tests/golden/translate.cli.text.with.figure.no_watermark.zh-CN.dual.pdf

# optional SSIM (mutually exclusive with --dual)
python -m babeldoc.tools.dual_quality_check --mode ssim \
  --actual-png out/p0.png --expected-png golden/p0.png \
  --work-dir /tmp/dual_diff
```
