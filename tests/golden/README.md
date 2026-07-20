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

**Operator baseline (2026-07-20):** BabelDOC **`7e9a984`**. The figure dual
regenerated on that commit is the **accepted layout baseline**. Dual-layer /
`font.unknown` work after that tip is **paused** (incomplete; regressed figure
when re-tested). Details and resume metrics: [`SCORECARD.md`](SCORECARD.md).

**Header checklist** (figure PDF): ZH title/author/affil/date should each be
**page-centered** on the mono half; `(Dated: …)` must be its **own** short
centered line, not glued onto the last affiliation line.

## What exists (PR-01)

| Piece | Role |
|-------|------|
| `il_layout_fingerprint(doc)` | Geometry-only refactor gate (no char unicode) |
| `FixedMapTranslator` | Deterministic non-LLM stub (`babeldoc.translator`) |
| `python -m babeldoc.tools.dual_quality_check --self-check` | Smoke: empty-doc fingerprint |
| `--mode ssim --actual-png … --expected-png …` | Optional pixmap SSIM compare |

## What is **not** here yet

- Full PDF → translate → dual E2E golden in CI
- Loading `typsetting.json` / debug IL dumps (write-only JSON today)
- Orgasms/Module-1 CI pixel gates (local scorecard only — see `SCORECARD.md`)

## Commands

```bash
# library / unit
uv run pytest tests/test_dual_golden_synth.py -q

# CLI smoke
python -m babeldoc.tools.dual_quality_check --self-check

# optional SSIM
python -m babeldoc.tools.dual_quality_check --mode ssim \
  --actual-png out/p0.png --expected-png golden/p0.png \
  --work-dir /tmp/dual_diff
```
