# Architecture: LayoutIntent → LineInterval → Typesetting

| Field | Value |
|-------|--------|
| Status | **In implementation** — C0/C1 landed 0.6.4.64; C2 attempt cleanup next |
| Date | 2026-08-07 |
| Baseline | TopCircle/BabelDOC `main` @ 0.6.4.63 (`0afa0c9`) |
| Supersedes (direction) | Ad-hoc wrap/residual flag retries (0.6.4.61–63) as *architecture* |
| Relates | [`layout-first-plan.md`](layout-first-plan.md), [`layout-first-coding-plan.md`](layout-first-coding-plan.md) |
| Primary failure evidence | OA dual p82: left wall `x≈5 w≈189`, phrase ×4; Producer 0.6.4.63 unchanged |

---

## 0. One-sentence contract

> **Typesetting may only break lines against a `LineIntervalPlan`.  
> `LayoutIntent` is valuable only insofar as it produces a correct plan.  
> Fields that do not change intervals (or vertical spacing) are not deliverables.**

---

## 1. Problem statement (architect view)

### 1.1 What the product needs

Dual PDF = left ZH re-typeset + right original EN. “Layout alignment” means:

- Same **reading structure** (body / wrap / callout / list / title roles)
- Same **spatial relationship to figures** (which side, taper direction)
- Acceptable **overflow strategy** when ZH is longer than EN (not “needle wall”)

### 1.2 What the system actually does today

```text
LayoutIntentExtractor (pre-MT)
  → layout_intent { role, design_box, wrap_shape, gap_contract, expansion_* , … }

Typesetting (post-MT)
  → _resolve_line_intervals:
        if active wrap:  typeset_wrap_line  # RIGHT-PIN ONLY, width-only
        else:            ExclusionZone residual + reference_width cap
  → scale loop / force / DP
  → on failure or “fit but too many lines”:
        recurse with wrap_enabled=False, drop_figure_zones=True  # 61–63
```

### 1.3 Architectural defect (not a bug list)

| Layer | Defect |
|-------|--------|
| **Problem definition** | Treats EN `paragraph.box` as a fixed fill container; overflow = scale/force/flags |
| **Contract** | Intent fields exist but **line geometry is not a first-class output** |
| **Consumption** | Four competing interval sources (wrap pin, zone residual, ref cap, flag re-entry) composed by `if`s inside a 4.4k-line god file |
| **Wrap model** | Detection can mark WRAP_COLUMN; **consumer hard-codes right-pin** (figure-left text-right). OA p82 is **left-fixed taper** (figure-right) |
| **Expansion** | `expansion_policy` / `overflow_policy` mostly **do not rebuild line intervals** → dead data for line breaking |
| **Patches 61–63** | Encode capacity failure as boolean recursion; **empirically failed p82**; grow spaghetti in `_find_optimal_scale_and_layout` |

**Root cause (precise):** missing **LayoutIntent → LineIntervalPlan → Typesetting** consumption chain.  
Not “missing more intent fields.” Not “PostLayout too weak.” Not “scale floor too high.”

### 1.4 Non-goals

- Rewriting PDF parser / dual splice product
- LLM layout
- Text-layer scrub / ToUnicode (parallel track)
- Replacing gap_contract P1 (already a closed vertical loop; keep it)
- Global “expand every narrow box” without measure policy

---

## 2. Design principles

1. **Single geometry API for line breaking**  
   All horizontal constraints collapse into `LineIntervalPlan.intervals_at(...)`.

2. **Intent is input; Plan is runtime**  
   Intent is immutable, pre-MT. Plan is resolved post-MT per paragraph per *attempt*.

3. **Overflow = next attempt (new Plan), not flag recursion**  
   `PRIMARY → FULL_MEASURE → BELOW_FIGURE` (names fixed below). No `wrap_enabled`/`drop_figure_zones` re-entry into the scale god-loop as the architecture.

4. **Typesetting is an executor**  
   No product-specific “CJK abandon narrow column” philosophy inside the scale success path. Capacity checks live next to Plan construction.

5. **Do not grow `typesetting.py`**  
   New logic in `utils/line_interval_plan.py` (name locked). Typesetting only wires.

6. **Deliverable = observable intervals**  
   Success criteria are interval sequences (and dual visuals), not “field present in JSON.”

7. **Extend Layout-First; do not invent a second Intent type**  
   No parallel `ParagraphLayoutIntent`. Extend `LayoutIntent` only with fields **required to build plans**.

---

## 3. Domain model

### 3.1 LineInterval (atomic)

```python
@dataclass(frozen=True, slots=True)
class LineInterval:
    """One horizontal pocket for a y-band (PDF coordinates)."""
    x1: float
    x2: float

    def width(self) -> float:
        return max(0.0, self.x2 - self.x1)
```

Multi-pocket lines (text on both sides of a float) return `list[LineInterval]` ordered L→R.  
**Primary measure** for body flow = leftmost pocket with width ≥ min usable (existing `min_usable_line_width` policy stays in zone layer inputs, not duplicated).

### 3.2 LayoutAttempt (overflow chain)

```python
class LayoutAttempt(str, Enum):
    PRIMARY = "primary"           # honor wrap + obstacles as intent says
    FULL_MEASURE = "full_measure" # design/body full width; ignore float carve for this para
    BELOW_FIGURE = "below_figure" # optional later: y-band only below float; full width
```

Ordered default chain for float-wrap body (CJK long text):

```text
PRIMARY → FULL_MEASURE
```

`BELOW_FIGURE` is **phase-gated** (C2+); not required for first green of p82 if FULL_MEASURE already yields non-wall layout.

### 3.3 WrapMode (intent material for intervals only)

```python
class WrapMode(str, Enum):
    NONE = "none"
    RIGHT_FIXED = "right_fixed"  # pin x2 = design.x2; x1 = x2 - width  (p19 class)
    LEFT_FIXED = "left_fixed"    # pin x1 = design.x;  x2 = x1 + width  (p82 class)
```

**Extraction rule (normative):** from EN multi-line boxes (or synth widths + edge spreads):

| Signal | WrapMode |
|--------|----------|
| `right_spread ≤ 4pt` and `left_spread ≥ 12pt` | `RIGHT_FIXED` |
| `left_spread ≤ 4pt` and `right_spread ≥ 12pt` | `LEFT_FIXED` |
| width taper only, spreads ambiguous | Prefer edge-spread; if still ambiguous → `NONE` (do **not** force pin) |
| not WRAP_COLUMN | `NONE` |

`figure_wrap.is_figure_wrap_paragraph` remains **WRAP_COLUMN role** detector; **mode** is a separate measurement so taper alone cannot force wrong pin.

### 3.4 LineIntervalPlan (runtime)

```python
@dataclass(slots=True)
class LineIntervalPlan:
    """Resolved geometry for one paragraph + one LayoutAttempt."""

    attempt: LayoutAttempt
    design_box: Box                 # from intent.design_box (read-only copy ref)
    layout_box: Box                 # current paragraph.box (may expand across attempts)
    wrap_mode: WrapMode
    wrap_shape: list[tuple[float, float]] | None  # (left_offset, width) EN units
    # obstacles: opaque handle or prefiltered ExclusionZoneIndex
    # source tags for dump only

    def intervals_at(
        self,
        y_bottom: float,
        y_top: float,
        *,
        line_idx: int,
    ) -> list[tuple[float, float]]:
        """Canonical API consumed by Typesetting. Returns [(x1,x2), ...]."""
        ...

    def primary_width(self, line_idx: int, y_bottom: float, y_top: float) -> float:
        ints = self.intervals_at(y_bottom, y_top, line_idx=line_idx)
        return max((x2 - x1 for x1, x2 in ints), default=0.0)
```

### 3.5 Capacity (when to advance attempt)

Pure functions (may absorb / replace `should_fallback_wrap_to_block` and residual helpers):

```python
def plan_exceeds_line_budget(
    plan: LineIntervalPlan,
    typeset_units | None,
    *,
    all_units_fit: bool,
    en_line_hint: int | None,
) -> bool:
    """True → caller should try next LayoutAttempt, not force-needle."""
```

Budget sources:

- If `wrap_shape`: `max(len(shape)+4, 10)` (existing wrap budget) for PRIMARY only  
- If residual-like primary width `< 0.75 * layout_box.width`: residual budget curve (existing residual helper, moved here)  
- FULL_MEASURE: no wrap residual budget (only box height / scale)

**Forbidden:** calling this from “all_units_fit success” only to recurse the entire scale search with flags.  
**Allowed:** before accepting a layout, or at scale floor, choose next attempt and **rebuild plan once**.

### 3.6 LayoutIntent extensions (minimal)

Add only what Generator needs:

| Field | Type | Required for |
|-------|------|----------------|
| `wrap_mode` | `WrapMode` | LEFT vs RIGHT interval math |
| `figure_side` | `none \| left \| right` | attempt policy + debugging (optional if mode solid) |

**Do not add** in v1: `allow_expand`, `quote_mode`, `figure_margin` as free-floating knobs.  
Express expand as **attempt chain membership** derived from role + wrap_mode:

| Role / mode | Attempt chain |
|-------------|----------------|
| WRAP_COLUMN + LEFT/RIGHT_FIXED | PRIMARY → FULL_MEASURE |
| WRAP_COLUMN + NONE | PRIMARY (zones+ref only) → FULL_MEASURE if residual-thin + CJK |
| CALLOUT / PULL_QUOTE | PRIMARY only (no FULL_MEASURE steal of body) in v1 |
| BODY + thin residual | PRIMARY → FULL_MEASURE (CJK only gate, in Generator policy not typesetting ifs) |
| CHROME | no typeset |

`expansion_policy` remains documentation of axes for box expand pass; **FULL_MEASURE** sets layout_box width to body measure / design full width **before** intervals are computed so expansion actually feeds line break.

---

## 4. LineIntervalGenerator (normative algorithm)

**Module:** `babeldoc/format/pdf/document_il/utils/line_interval_plan.py`  
**Owner of:** wrap line math, merge with obstacles, ref-width cap, attempt variants  
**Not owner of:** glyph placement, scale search, MT text

### 4.1 `resolve_plan(...)`

```text
resolve_plan(paragraph, page_zone_index, attempt) -> LineIntervalPlan
```

Inputs:

- `paragraph.layout_intent` (may be None → degraded plan)
- `paragraph.box` as `layout_box`
- `attempt: LayoutAttempt`
- page exclusion index (figures/quotes)

### 4.2 `intervals_at` algorithm

```text
function intervals_at(plan, y_bottom, y_top, line_idx):
    box = plan.layout_box

    // 1) Base pocket(s) from attempt
    if plan.attempt == FULL_MEASURE:
        base = [(box.x, box.x2)]
        // intentionally ignore figure obstacles for this paragraph attempt
    else if plan.attempt == BELOW_FIGURE:
        // v2: if y-band intersects figure, return empty or skip band;
        //      if below all figures, full width
        base = full_or_empty_by_y(...)
    else:  // PRIMARY
        if plan.wrap_mode in (LEFT_FIXED, RIGHT_FIXED) and plan.wrap_shape:
            base = [wrap_interval(plan, line_idx)]  // single pocket
        else:
            base = zone_intervals(page_zones, y_bottom, y_top, box)
            base = cap_leftmost_with_reference(base, ref_widths, line_idx)

    // 2) Clamp every pocket into layout_box
    base = clamp_to_box(base, box)

    // 3) Enforce min width: drop needle pockets; if none left, full box
    //    (reuse exclusion_zone min_usable policy via shared helper)
    return sanitize(base)
```

### 4.3 `wrap_interval` (replaces asymmetric typeset_wrap_line)

```text
function wrap_interval(plan, line_idx) -> (x1, x2):
    (off, width) = shape_entry(plan.wrap_shape, line_idx)
    width = max(width, 8.0)
    d = plan.design_box   // pin reference; NOT layout_box for pin edges
                         // unless design missing

    if plan.wrap_mode == RIGHT_FIXED:
        x2 = d.x2
        x1 = x2 - width
    else if plan.wrap_mode == LEFT_FIXED:
        x1 = d.x
        x2 = x1 + width
    else:
        unreachable

    // CRITICAL: clamp to design_box and layout_box intersection
    x1, x2 = clamp(x1, x2, intersect(d, plan.layout_box))
    // CRITICAL: if width requested > available, shrink width, do NOT shift
    //           opposite edge past page (prevents x≈5 from huge width)
    return (x1, x2)
```

**Deprecation:** `typeset_wrap_line` becomes a thin wrapper calling `wrap_interval` with `RIGHT_FIXED` for one release, then deleted.

### 4.4 Interaction with ExclusionZone

- Zones remain the **obstacle index** (quotes, figures).
- PRIMARY + wrap_mode FIXED: wrap pocket is authoritative for that paragraph; **do not double-apply** figure residual that fights pin (today: wrap path skips zone — keep that).
- PRIMARY + wrap_mode NONE: zone residual + ref cap (today’s non-wrap path).
- FULL_MEASURE: **ignore figure zones for this paragraph only** (semantic successor of `drop_figure_zones=True`), still respect quote zones if product requires (v1: drop figures only, keep quote — match 63 intent).

### 4.5 Interaction with gap_contract (unchanged)

```text
pre_typeset_gap_pass  → may move paragraph.box vertically
resolve_plan          → uses updated layout_box
line break            → intervals only
```

Vertical and horizontal concerns stay separated. **Do not** fold gap into LineIntervalPlan v1.

---

## 5. Typesetting integration (executor contract)

### 5.1 Replace `_resolve_line_intervals` body

```python
# typesetting.py — wiring only
def _resolve_line_intervals(...):
    plan = self._current_line_plan  # set for this paragraph attempt
    if plan is None:
        plan = resolve_plan(...)    # lazy safe default
    return plan.intervals_at(y_bottom, y_top, line_idx=line_idx)
```

### 5.2 Scale / layout loop ownership

```text
for attempt in attempt_chain(intent):
    plan = resolve_plan(para, zones, attempt)
    self._current_line_plan = plan
    maybe expand layout_box for FULL_MEASURE (write paragraph.box only)
    run existing scale search + layout_units using plan only
    if success and not plan_exceeds_line_budget(...):
        accept
        break
    if success and exceeds budget:
        continue  # next attempt — do not force needle accept
    # scale floor failure → next attempt
else:
    force apply last plan at min_scale (existing force path)
```

**Delete as architecture:**

- Recursive `_find_optimal_scale_and_layout(..., wrap_enabled=, drop_figure_zones=)`
- Call-scoped `self._wrap_enabled` as the feature switch (config flag `enable_layout_intent_wrap` may still disable FIXED wrap → mode NONE)
- Fit-path `_cjk_should_abandon_narrow_column` embedded in `if all_units_fit`

**Migrate:**

- `should_fallback_*` → `plan_exceeds_line_budget` + attempt selection

### 5.3 File size law

| Change | Rule |
|--------|------|
| New wrap/interval/attempt logic | **Must** land in `line_interval_plan.py` (or tests) |
| `typesetting.py` net lines for this project | **≤ 0** preferred; hard cap **+80** wiring only |
| Crossing another ad-hoc branch in scale loop | **PR rejected** |

---

## 6. Observability (non-optional)

### 6.1 Debug dump (per paragraph, `--debug` or env)

```json
{
  "debug_id": "...",
  "role": "wrap_column",
  "wrap_mode": "left_fixed",
  "attempt": "primary",
  "design_box": [x,y,x2,y2],
  "layout_box": [x,y,x2,y2],
  "wrap_shape_head": [[off,w], ...],
  "sample_intervals": [
    {"line_idx": 0, "y": 400, "pockets": [[102, 427]]},
    {"line_idx": 5, "y": 475, "pockets": [[102, 291]]}
  ],
  "budget_exceeded": false,
  "next_attempt": null
}
```

### 6.2 p82 acceptance probes

| Probe | Pass |
|-------|------|
| PRIMARY LEFT_FIXED first body line after CLAW | `x1 ∈ [100, 105]` (EN 102) |
| PRIMARY taper | `x2` decreases along EN shape (monotonic non-increase, tol 4pt) |
| No pocket with `x1 < design.x - 2` | forbids x≈5 drift |
| If still budget-exceeded → FULL_MEASURE | primary width ≥ 0.75 × body measure; no ×3 identical 15-char CJK runs in left column wall |

Phrase ×4 may partly be **composition/callout merge** (C4). FULL_MEASURE clears **geometry wall**; callout dedupe is separate PR.

---

## 7. Phased delivery (strict order)

| Phase | Name | Behavior change | Exit criteria |
|-------|------|-----------------|---------------|
| **C0** | Extract Plan API | **None** (right-pin + zone path bit-identical) | All line intervals go through `LineIntervalPlan`; dump works; tests green |
| **C1** | LEFT_FIXED + clamp | Yes | p19 RIGHT regression; p82 left edge ~102 on PRIMARY; no x&lt;design.x |
| **C2** | Attempt chain; remove flag recursion | Yes | 61–63 flags gone; capacity → next attempt; typesetting loop simplified |
| **C3** | FULL_MEASURE box write feeds intervals | Yes | expansion meaningful; p82 wall gone or only content-dupe remains |
| **C4** | Callout independent band | Yes | structure-level duplicate reduction |

**Hard ban:** shipping “wrap_mode field only” without C0 Plan wiring.  
**Hard ban:** residual flag v2 before C0–C1.

---

## 8. Mapping from 61–63 (migration, not celebration)

| Old | New |
|-----|-----|
| `wrap_enabled=False` | Attempt FULL_MEASURE or wrap_mode forced NONE inside PRIMARY rebuild |
| `drop_figure_zones=True` | FULL_MEASURE ignores figure obstacles |
| `should_fallback_wrap_to_block` | `plan_exceeds_line_budget` on PRIMARY+shape |
| `should_fallback_residual_to_block` | budget on thin primary width |
| `_cjk_should_abandon_narrow_column` | attempt chain policy in Generator |
| fit-then-reject recurse | continue attempt loop |

---

## 9. Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Wrong WrapMode misclassifies body | Ambiguous → NONE; dump + golden intervals on p10/p19/p82 |
| FULL_MEASURE paints over photo | Accept for v1 (better than wall); C2.1 BELOW_FIGURE later |
| C0 behavior drift | Golden interval unit tests from current right-pin + zone fixtures |
| typesetting.py keeps growing | CI or review rule: reject net +interval logic in typesetting |
| Callout merge still duplicates text | Explicit C4; do not block C1 on full text dedupe |
| Intent None on some paras | Degraded plan = today’s zone+ref path |

---

## 10. Alternatives considered

| Alternative | Why rejected |
|-------------|--------------|
| More flags on scale search | Failed p82; spaghetti; wrong abstraction |
| PostLayout BoxExpandFixer as main fix | After-the-fact; cannot fix wrong intervals during break |
| Only add wrap_mode field on Intent | Dead field without LineInterval chain |
| New parallel Intent type | Duplicates Layout-First; confusion |
| Always FULL_MEASURE for CJK wrap | Destroys good p19 pin; need mode+budget |
| Zone residual as only model | Cannot express EN left-fixed taper cleanly; already failed dual track |

---

## 11. Key Decisions

1. **Canonical line-break input is `LineIntervalPlan`, not raw wrap_shape or zones.**  
   Rationale: one API; composable attempts; testable without god-file.

2. **Wrap has two modes (LEFT_FIXED / RIGHT_FIXED); width-only right-pin is not universal.**  
   Rationale: OA p19 vs p82 are opposite pin edges; single formula is a design bug.

3. **Overflow is an ordered attempt chain that rebuilds the plan.**  
   Rationale: deletes flag recursion; makes FULL_MEASURE an interval fact.

4. **Minimal Intent extension (`wrap_mode`); no field sprawl.**  
   Rationale: user/architect consensus — chain over catalog.

5. **gap_contract stays a separate closed vertical loop.**  
   Rationale: already works; do not entangle with horizontal plan v1.

6. **No new logic bulk in `typesetting.py`.**  
   Rationale: 4428-line file is already past healthy size; 61–63 proved the failure mode.

7. **61–63 behavior may be re-expressed via attempts; architecture of flags is retired.**  
   Rationale: preserve useful capacity math; delete control-flow debt.

8. **Success = correct interval sequences + dual visual probes, not JSON field presence.**  
   Rationale: prevent “intent theater.”

---

## 12. Open Questions (need product/owner if disputed)

1. **FULL_MEASURE over photo vs BELOW_FIGURE first for p82**  
   - Default in this doc: FULL_MEASURE first (simpler, matches drop-figures intent).  
   - BELOW_FIGURE if over-photo is product-unacceptable.

2. **CJK-only vs all languages for attempt chain**  
   - Default: chain enabled when `is_cjk` OR wrap_mode FIXED (EN wrap rarely needs FULL_MEASURE).

3. **Quote zones under FULL_MEASURE**  
   - Default: keep quote obstacles; drop figures only.

---

## 13. PR Plan

### PR-A — C0: LineIntervalPlan extraction (behavior-neutral)

- **Title:** `refactor(layout): LineIntervalPlan single entry for line pockets`
- **Files:**  
  - add `utils/line_interval_plan.py`  
  - move/wrap `typeset_wrap_line`, zone+cap path  
  - `typesetting._resolve_line_intervals` → plan only  
  - tests: port figure_wrap_policy + interval goldens  
- **Deps:** none  
- **Must not:** change pin math; add wrap_mode yet

### PR-B — C1: WrapMode extract + LEFT_FIXED + clamp

- **Title:** `feat(layout): LEFT_FIXED wrap intervals (intent → plan)`
- **Files:**  
  - `layout_intent.py` + extractor `wrap_mode`  
  - `line_interval_plan.wrap_interval` dual mode + clamp  
  - `figure_wrap` or extractor edge-spread rules  
  - tests: synthetic p82 left-fixed; p19 right-fixed regression  
- **Deps:** PR-A  
- **Accept:** interval probes; optional OA p82 single-page if available

### PR-C — C2: Attempt chain; remove wrap/drop recursion

- **Title:** `refactor(layout): layout attempts replace wrap/drop flags`
- **Files:**  
  - attempt loop around scale search (thin)  
  - delete `_wrap_enabled` call-scoped feature path / dual kwargs recursion  
  - migrate `should_fallback_*` into budget helpers  
  - update `test_wrap_fallback.py`  
- **Deps:** PR-B  
- **Accept:** no recursive flag API; capacity advances attempt

### PR-D — C3: FULL_MEASURE feeds real width + p82 layout gate

- **Title:** `fix(layout): FULL_MEASURE attempt for float-wrap overflow`
- **Files:** plan FULL_MEASURE; box width policy; dump; OA p82 checklist  
- **Deps:** PR-C  
- **Accept:** p82 no residual wall geometry

### PR-E — C4: Callout band (optional stack)

- **Title:** `feat(layout): callout independent of body line plan`
- **Deps:** PR-D  
- **Accept:** reduced structural duplicate on p82/p5/p108

---

## 14. Relationship to Layout-First coding plan

| Coding-plan item | This architecture |
|------------------|-------------------|
| P2 wrap_shape “Done” right-pin only | **Re-open:** P2 is partial; C0–C1 complete horizontal wrap |
| P0 Intent fields | Keep; add only `wrap_mode` |
| P1 gap_contract | Unchanged |
| P3 PostLayout retypeset | Must receive same Plan API when retypesetting |
| enable_layout_intent_wrap | Still kills FIXED modes → NONE |

Update `layout-first-coding-plan.md` status after PR-A merges: mark P2 wrap as **partial**, link this doc.

---

## 15. Implementation checklist (engineer)

- [ ] PR-A: Plan API + wiring; zero intentional behavior change  
- [ ] PR-B: `wrap_mode` + LEFT_FIXED + clamp; p19/p82 interval tests  
- [ ] PR-C: attempts; delete flag recursion  
- [ ] PR-D: FULL_MEASURE; p82 visual/geometry gate  
- [ ] PR-E: callout (if still needed)  
- [ ] Doc: coding-plan P2 status + this ADR link  
- [ ] Review bar: any new interval `if` in typesetting scale loop → reject  

---

## 16. Final architectural statement

```text
LayoutIntent  ──extract──►  materials (role, design_box, wrap_shape, wrap_mode, …)
                │
                ▼
LineIntervalGenerator + LayoutAttempt  ──resolve──►  LineIntervalPlan
                │
                ▼
Typesetting  ──breaks lines only against──►  plan.intervals_at(...)
                │
                ▼
            glyphs / dual
```

**If a change does not alter `intervals_at` (or gap spacing), it is not a layout fix.**

---

*End of architecture document.*
