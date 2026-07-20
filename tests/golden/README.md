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

## What exists (PR-01 + Phase 0)

| Piece | Role |
|-------|------|
| `il_layout_fingerprint(doc)` | Geometry-only refactor gate (no char unicode) |
| `FixedMapTranslator` | Deterministic non-LLM stub (`babeldoc.translator`) |
| `python -m babeldoc.tools.dual_quality_check --self-check` | Smoke: empty-doc fingerprint |
| `--mode ssim --actual-png … --expected-png …` | Optional pixmap SSIM compare |
| `python -m babeldoc.tools.figure_baseline_probe --dual …` | **Hard gate:** affil center / crush / left-col gap / fig-label 混段 |
| `figure_baseline_probe --self-check` | CI-safe synthetic dual smoke |

## What is **not** here yet

- Full PDF → translate → dual E2E golden in CI
- Loading `typsetting.json` / debug IL dumps (write-only JSON today)
- Orgasms/Module-1 CI pixel gates (local scorecard only — see `SCORECARD.md`)
- Dual-layer Phase A+ (auto OCR detect, OCR-gated typesetting) — **not started**

## Commands

```bash
# library / unit
uv run pytest tests/test_dual_golden_synth.py tests/test_figure_baseline_probe.py -q

# CLI smoke
python -m babeldoc.tools.dual_quality_check --self-check
python -m babeldoc.tools.figure_baseline_probe --self-check

# hard gate on local figure dual (gitignored output PDF)
python -m babeldoc.tools.figure_baseline_probe \
  --dual tests/golden/translate.cli.text.with.figure.no_watermark.zh-CN.dual.pdf

# optional SSIM
python -m babeldoc.tools.dual_quality_check --mode ssim \
  --actual-png out/p0.png --expected-png golden/p0.png \
  --work-dir /tmp/dual_diff
```
