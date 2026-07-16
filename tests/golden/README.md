# Golden / dual-quality fixtures

- **CI:** unit tests only (`tests/test_dual_golden_synth.py` + existing midend units).
- **Local scorecard:** large PDFs under `tests/` (Orgasms, Module 1) — see `SCORECARD.md`.
- **Do not** commit multi-10MB dual binaries to public PRs for pixel gates.

Harness scaffold:

```bash
python -m babeldoc.tools.dual_quality_check --self-check
python -m babeldoc.tools.dual_quality_check --mode ssim \
  --actual-png out/p0.png --expected-png golden/p0.png \
  --work-dir /tmp/dual_diff
```
