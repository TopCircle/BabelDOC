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

### Regression probe (hard gate — dual-layer recover Phase 0+)

Same source dual, frozen translation cache, compare vs accepted figure dual:

| Metric (ZH half) | Baseline-ish | Flag as regression |
|------------------|--------------|--------------------|
| Affil mid vs page center 306 | ≈306 | \|mid−306\| &gt; 25 |
| Chars &lt; 7pt / total | ~1% | &gt; 10% |
| Max left-col vertical gap (body) | ~76pt | &gt; 120pt |
| Long body block contains fig labels | no | yes (混段) |

**CLI (no pipeline side effects):**

```bash
# local operator dual (gitignored *.pdf)
python -m babeldoc.tools.figure_baseline_probe \
  --dual tests/golden/translate.cli.text.with.figure.no_watermark.zh-CN.dual.pdf

# synthetic smoke (CI-safe)
python -m babeldoc.tools.figure_baseline_probe --self-check
```

Exit **0** = hard gates pass; exit **1** = regression. Unit tests:
`tests/test_figure_baseline_probe.py`.

**Recorded snapshot (local dual @ Phase 0, tip after figure-text skip):**

| Metric | Value (ZH left half) |
|--------|----------------------|
| half | left (CJK auto) |
| crush_ratio | ~0.016 |
| max_left_col_gap | ~32pt (threshold 120) |
| affil_mid | ~305 (center 306) |
| fig_label_hits | none |

Figure labels stay in the source language by default (`translate_figure_text=False`;
UI: **Translate figure text** off). Opt in to translate chart annotations.
Independent of **Translate table text** (RapidOCR table path).

### Dual-layer recover gates (do not skip)

Resume dual-layer / `font.unknown` **only** with independent PRs. **Never** bulk
cherry-pick `7e9a984..004ba7b`. **Never** mix PR-08 package extract into this track.

| Phase | Scope | Merge only if |
|-------|--------|----------------|
| **0** | Probe + this checklist (no behavior change) | ✅ unit + `--self-check` green (`f713179`) |
| **A** | Detect searchable image → auto `ocr_workaround` only | ✅ figure not dual-layer; enable flags; figure dual probe still green |
| **B** | Font split policy: hard on born-digital; soft only if `ocr_workaround` | ✅ unit + policy; figure dual probe still green |
| **C** | OCR typesetting (scale/box/ref_width) **gated** on `ocr_workaround` | ✅ OCR unit tests; figure dual probe still green |
| **D** | Optional OCR reflow / single face / glyph hygiene | figure still green; backlog items one PR each |

#### Phase A status

- **In:** `page_has_fullpage_image` + `page_has_invisible_text_layer` +
  `is_searchable_image_pdf` + `enable_ocr_workaround_for_searchable_image`
  (`detect_scanned_file.py`); hook in `_do_translate_single` **before** IL parse.
- **Out:** paragraph font-switch soft/hard policy; OCR scale/box typesetting.
- **Tests:** `tests/test_searchable_image_pdf.py` — font.unknown True; plain +
  **figure** False; enable sets `ocr_workaround` / `skip_scanned_detection` /
  `disable_rich_text_translate` / `auto_enabled_ocr_workaround`.
- **Operator note:** figure dual PDF need **not** be regenerated for Phase A
  (born-digital path unchanged). font.unknown dual may gain white-fill earlier
  in the pipeline; body scale still Phase C.

#### Phase B status

- **In:** `paragraph_split_policy` (TOC / short-line / bullet / **font face** /
  date-tail); `ParagraphFinder` wires `soft_mid_sentence_font_split =
  ocr_workaround`; Courier-name → mono → CJK **sans** stand-in in `FontMapper`.
- **Semantics:**
  - `ocr_workaround=False`: any dominant `font_id` change splits (arXiv Arial
    labels vs body).
  - `ocr_workaround=True`: face change splits only if previous line is
    sentence-final (keep mid-clause Times→Courier for MT).
- **Out:** OCR scale / box / `reference_widths` (Phase C).
- **Tests:** `tests/test_font_switch_paragraph.py`.

#### Phase C status

- **In (all `if ocr_workaround`):** no mode-scale demotion; CJK leading
  `_OCR_LINE_SKIP_CJK=1.30`; ignore EN `reference_widths`; min scale
  `_OCR_MIN_SCALE=0.88`; search from 1.0; pre-expand box (down-first expand
  order); `_ocr_normalize_unit_font_sizes` lifts ~7.5pt Courier runs; white-fill
  aligns `paragraph.box` to layout rect (`add_text_fill_background`).
- **Out:** mega-paragraph vertical reflow / single face / OCR glyph hygiene
  (Phase D backlog).
- **Tests:** `tests/test_ocr_layout_scale.py`.
- **Operator:** regenerate **font.unknown** dual to judge size/span; **do not**
  require figure dual regen for merge (born-digital path unchanged).

#### Phase C follow-up (title / messy dual fix)

Symptom after first Phase C land: `font.unknown` dual lost ZH title (EN image
showed through), author glued to uni (`SchudsonUNIVERSITY`), body scrambled.

| Cause | Fix |
|-------|-----|
| Title/author/uni share **same Times face**, only size differs → soft face keep never splits | `should_split_on_font_size_jump` (≥1.18×) always in `should_split_line_pair` |
| Soft OCR face keep glued short header lines | Soft path still hard-splits size ratio / short lines |
| `_OCR_MIN_SCALE=0.88` → mass overflow | Floor lowered to **0.70** |
| Force-layout reintroduced EN `reference_widths` under OCR | Force path uses `None` when `ocr_workaround` |
| Post-typeset overlap retypeset failed and scrambled dual-layer | **Skip** `fix_overlapping_paragraphs_post_typesetting` when `ocr_workaround` |

After pull: **re-translate** `translate.cli.font.unknown.pdf` (old dual is stale).
Expect ZH title line separate from author/uni; body not mid-line scrambled.

#### font.unknown red-mark follow-up (shared layout box)

Updated dual still showed: EN title/author ghost; body **head/tail stacked**
(`研究新闻…` under `哗众取宠…永远不会伪造新闻`).

**Cause:** `add_text_fill_background` assigned `paragraph.box = layout∪para`
for every para. Body paras share one tall layout band → all typeset from the
same top edge (tail and head overlap). White fill must stay on the union rect;
typeset boxes stay per-paragraph; vertical room via `_ocr_pre_expand_box`.

#### Title blank after body-stack fix

Body stack fixed (tail at correct y). Title/author/uni still blank white on ZH
half while EN residual OCR text remains extractable.

| Cause | Fix |
|-------|-----|
| `skip_header` + 40pt band treats paper title/author as header | OCR dual-layer: **never** header/footer skip; never skip `layout_label=title` |
| White fill still painted on skipped top paras | White fill skips header/footer skip bands |
| Passthrough of invisible OCR units under white fill | OCR mode: **always retypeset** (no passthrough) |

**Red decision tree:** fix or `git revert` **current Phase PR only** — no `reset --hard` of the whole branch.

**Out of track:** PR-08 typesetting package split; drop-cap fixes (separate PR + same figure probe).

### ⏸ FREEZE (2026-07-20): font.unknown CJK mid-word / citation wraps — **paused**

Operator judgment: **current approach has not closed the gap**; stop iterating for now.
Resume only with a **new plan** (not more one-off glue / dict / pull-back patches).

| Field | Value |
|-------|--------|
| Sample | `tests/golden/translate.cli.font.unknown.pdf` → dual ZH half |
| Code tip when frozen | `357beee` (`fix(cjk): pull-back…`) on dual-layer track after Phases 0–C + title/indent/courier |
| Operator status | **Paused / not accepted** — user: 「这个你是改不好了」 |
| Figure baseline | Keep independent; do **not** break figure probe while resuming |

#### Still broken (repro on dual ZH half — circled by operator)

| ID | Symptom | Example |
|----|---------|---------|
| F1 | Mid-word CJK wrap | `感` / `情用事` (感情用事) |
| F2 | Citation open-paren at EOL | `第11卷（` then next line `1989年），263-282页` |
| F3 | Place-name / related | historically `德` / `里`（新德里）; may recur with other names |
| F4 | Related body orphans | short tails mid-sentence after OCR narrow box + greedy/DP mismatch |

**What already works on this track (do not re-break):** ZH title/author painted; body not fully stacked; indent/center less wrong; some 感情/年 glue in unit sim — **production dual still shows F1–F2**.

#### What was tried (do not blindly re-apply)

| Layer | Change (commits / WIP) | Limit |
|-------|------------------------|--------|
| Word mark | `merge_cjk_units` mark **first** char of 二字词 `can_break=False` (`67fd9d2`) | Dict incomplete; DP/greedy width mismatch still wraps |
| Kinsoku | line-end forbidden on `（`; glue `年` after digits (`34aeb00`+) | Cancel-break → overflow path still ends with `（` on real duals |
| Pull-back | On wrap, pop illegal EOL tail to next line (`357beee`) | Unit sim OK; **operator dual still fails** (path/scale/DP adopt / not loaded?) |
| EN lookahead off | OCR/CJK disable lookahead + 2× paren early wrap | Helps sim; not sufficient alone |
| Dict | `感情`/`伪造`/`德里`/`新德里`… | Whack-a-mole; not a general CJK engine |
| Digit glue | `第`+digits+`卷` / `1989年` in `merge_cjk_units` | Same: sim green, dual red |

#### Likely structural gaps (for next designer — not confirmed fixed)

1. **Two layout passes:** greedy then optional DP; if DP rejected (`opt_fit` / width estimate), bad greedy remains.
2. **Estimated `line_widths` ≠ real multi-interval OCR box** → DP illegal or unused; greedy inserts extra breaks.
3. **Pull-back / glue only on in-process units** — verify GUI/PDFMathTranslate actually runs **editable fork** at tip (not pip 0.6.x).
4. **Half-space / NBSP / hyphenated OCR source** → unit stream may not match dict adjacency.
5. **Scale search accepts mid-word wraps** as long as `all_units_fit` (break is “legal” to fit metric).

#### Resume checklist (next session)

- [ ] Confirm runtime: `babeldoc.__file__` → this fork; git tip ≥ freeze commit or rebased plan.
- [ ] Capture **one** failing dual + IL dump (`typsetting.json` / debug) for the two circled regions only.
- [ ] Prefer **one** mechanism: e.g. CJK-only break cost in DP + single layout path under `ocr_workaround`, not more ad-hoc `if` in the greedy loop.
- [ ] Gate: figure `figure_baseline_probe` still green; unit tests for F1/F2 strings under OCR-like `box_w`.
- [ ] Operator sign-off on **new** dual screenshots only (old `_circ_*.png` / `_fu_*.png` are stale evidence).

**Local evidence (gitignored / untracked):** `tests/golden/_circ_p1.png`, `_circ_end.png`, `_circ_full.png`, `_fu_latest_left.png`.

**Out of track:** PR-08 typesetting package split; drop-cap; figure golden re-baseline.

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
