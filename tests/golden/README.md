# Golden / dual-quality fixtures

## What exists (PR-01)

| Piece | Role |
|-------|------|
| `il_layout_fingerprint(doc)` | Geometry-only refactor gate (no char unicode) |
| `FixedMapTranslator` | Deterministic non-LLM stub (`babeldoc.translator`) |
| `python -m babeldoc.tools.dual_quality_check --self-check` | Smoke: empty-doc fingerprint |
| `--mode ssim --actual-png … --expected-png …` | Optional pixmap SSIM compare |

## What is **not** here yet

- PDF → translate → dual E2E golden
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
