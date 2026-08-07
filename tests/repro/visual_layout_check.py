"""V1-V5 visual layout acceptance assertions (docs/visual-layout-acceptance.md §1).

Turns the five acceptance dimensions into per-page, per-item pass/fail checks
against a repro **run-dir** (the debug JSONs the pipeline already writes) plus
an **EN reference** golden (``tests/repro/golden/en_pXX_blocks.json``) that
captures the original English page geometry.

Data-source rules (same as the digest harness, plan §2):

* Line widths / right edges are recomputed from ``pdf_character`` boxes
  clustered by y — never read from ``reference_metrics.per_line_widths``.
* Roles / design boxes / ``wrap_mode`` / ``min_scale`` / ``gap_contract`` come
  from ``layout_intent`` (inline on ``typsetting.json`` paragraphs, falling
  back to ``layout_intent.json`` keyed by ``debug_id`` or ``para_N``).
* Translated text for V4/V5 comes from the typeset paragraph ``unicode``.

Checks (thresholds are the acceptance-doc constants):

* **V1 anchors** — chapter-title / section-title / body-first-line top vs EN:
  ``|run_box_top - en_top| <= 4`` (run side uses the paragraph box top
  ``box.y2``, i.e. the layout anchor the typesetter places; EN side is the
  glyph top measured on the original PDF).
* **V2 gap** — first title-like paragraph immediately above the first body
  block: ``|zh_ink_gap - en_ref| <= 2`` where
  ``zh_ink_gap = title_ink_bottom - first_body_box_top`` and ``en_ref`` is
  the pipeline's own ``gap_contract`` (the EN-derived contract the typesetter
  must reproduce; acceptance doc V2 defines ``en_ink_gap := gap_contract``).
  The golden direct EN measurement is kept as an advisory sanity cross-check
  (``V2.gap_sanity`` WARN) so a broken extractor cannot silently pass.
* **V3 wrap** — for ``right_fixed`` wrap paragraphs every line's ink right
  edge stays within ``0.5`` of the design right edge; no single-char orphan
  line (``line_width < 1.6 * font_size``, last line exempt); effective font
  size ``>= min_scale * en_original_font_size[role]``.
* **V4 content** — no sentence repeated ``>= 2`` times consecutively in the
  translated character sequence, no line starting with a sentence-end
  punctuation (dangling), no line ending with an opening bracket.
* **V5 structure** — callout sentences must not duplicate body sentences
  (one-to-one, no cross-repeat); running-header chrome in the top band must
  contain no CJK (skip in effect).

The module is intentionally standalone (no ``babeldoc`` import): unit tests
feed hand-built JSON documents without running the pipeline.

CLI::

    python tests/repro/visual_layout_check.py \\
        --run-dir /path/to/run --en-reference tests/repro/golden/en_p19_blocks.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# --------------------------------------------------------------------------
# Constants / thresholds (acceptance doc §1; do not change casually)
# --------------------------------------------------------------------------

SCHEMA = "babeldoc-repro-visual-layout/v1"

#: V1: anchor top deviation (pt).
ANCHOR_DY = 4.0
#: V1: run paragraph must be within this window of the EN anchor to be
#: considered the same block (drifted layout should still be diagnosed,
#: not silently unmatched).
ANCHOR_MATCH_WINDOW = 80.0
#: V2: |zh gap - en gap| tolerance (pt).
GAP_EPS = 2.0
#: V3: wrap right edge tolerance vs design right edge (pt).
RIGHT_EDGE_EPS = 0.5
#: V3: line width below this multiple of the font size is an orphan line.
ORPHAN_WIDTH_RATIO = 1.6
#: V4: a sentence repeated this many times consecutively is a blocker.
REPEAT_MIN = 2
#: V5: header band measured from the page top (pt); chrome inside it must
#: stay English (skip in effect).
HEADER_ZONE = 200.0

#: layout_intent roles used by each V1 anchor kind.
ANCHOR_ROLES: dict[str, set[str]] = {
    "chapter_title": {"title", "callout"},
    "section_title": {"title", "section_header"},
    "body_first_line": {"body", "pull_quote"},
}

#: body-like roles (main text, incl. pull-quote styled body on OA pages).
BODY_LIKE_ROLES = {"body", "pull_quote"}

#: title-like roles (incl. callout, where chapter titles live on OA pages).
TITLE_LIKE_ROLES = {"title", "section_header", "callout"}

#: placeholder unicode produced for layout stubs — never treated as content.
_PLACEHOLDER_TEXTS = frozenset({"plain text", "title", "abandon", "fallback_line"})

#: CJK Unified Ideographs (incl. Ext A) — used by the header "no Chinese" check.
_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")

#: Sentence separators used by V4 (CJK + basic Latin).
_SENTENCE_RE = re.compile(r"[。！？!?；;\n]+")

#: Punctuation that must not open a line (dangling sentence end).
_LINE_OPEN_BAD = frozenset("。，、；：！？）」』…")
#: Opening brackets that must not close a line.
_LINE_CLOSE_BAD = frozenset("（「『“‘（〈《")

_LINE_CLUSTER_TOLERANCE = 3.0


# --------------------------------------------------------------------------
# Data model
# --------------------------------------------------------------------------


@dataclass
class LineData:
    """One y-clustered line of a typeset paragraph (PDF y-up geometry)."""

    text: str
    x0: float
    x1: float
    width: float
    top: float  # max char y2 (ink top, y-up)
    bottom: float  # min char y (ink bottom, y-up)


@dataclass
class ParaData:
    """A post-typeset paragraph with everything V1-V5 need."""

    index: int
    debug_id: str | None
    role: str | None
    box: tuple[float, float, float, float] | None
    design_box: tuple[float, float, float, float] | None
    wrap_mode: str | None
    min_scale: float
    gap_contract: float | None
    unicode: str
    font_size: float | None
    scale: float
    lines: list[LineData]
    has_intent: bool

    @property
    def effective_font(self) -> float | None:
        if self.font_size is None:
            return None
        return self.font_size * (self.scale or 1.0)

    @property
    def ink_top(self) -> float | None:
        return max((ln.top for ln in self.lines), default=None)

    @property
    def ink_bottom(self) -> float | None:
        return min((ln.bottom for ln in self.lines), default=None)

    @property
    def box_top(self) -> float | None:
        return self.box[3] if self.box else None

    @property
    def box_bottom(self) -> float | None:
        return self.box[1] if self.box else None


@dataclass
class PageRun:
    """One page of run data (typsetting + paragraph_finder + layout_intent)."""

    page_key: str
    page_height: float | None
    paragraphs: list[ParaData]


@dataclass
class CheckResult:
    """One assertion outcome (V1..V5, per page, per item)."""

    item: str
    status: str  # PASS | FAIL | SKIP | WARN
    value: object = None
    threshold: str | None = None
    detail: str = ""

    def to_dict(self) -> dict:
        return {
            "item": self.item,
            "status": self.status,
            "value": self.value,
            "threshold": self.threshold,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class Thresholds:
    """All tunable assertion tolerances (defaults mirror the acceptance doc)."""

    anchor_dy: float = ANCHOR_DY
    anchor_match_window: float = ANCHOR_MATCH_WINDOW
    gap_eps: float = GAP_EPS
    right_edge_eps: float = RIGHT_EDGE_EPS
    orphan_width_ratio: float = ORPHAN_WIDTH_RATIO
    orphan_exclude_last_line: bool = True
    repeat_min: int = REPEAT_MIN
    header_zone: float = HEADER_ZONE


# --------------------------------------------------------------------------
# JSON loading
# --------------------------------------------------------------------------


def _rglob_first(run_dir: Path, name: str) -> Path | None:
    candidates = sorted(run_dir.rglob(name))
    return candidates[0] if candidates else None


def load_run(run_dir: str | Path) -> dict:
    """Parse a run-dir into ``{"pages": {page_key: PageRun}}``.

    Requires ``typsetting.json`` (searched recursively, same as the driver);
    ``paragraph_finder.json`` and ``layout_intent.json`` are optional
    siblings and provide fallback role/intent data only — the inline
    ``layout_intent`` on typsetting paragraphs is authoritative.
    """
    run_dir = Path(run_dir)
    typsetting_path = _rglob_first(run_dir, "typsetting.json")
    if typsetting_path is None:
        raise FileNotFoundError(f"typsetting.json not found under {run_dir}")
    typsetting = json.loads(typsetting_path.read_text(encoding="utf-8"))
    layout_intent = {}
    li_path = _rglob_first(run_dir, "layout_intent.json")
    if li_path is not None:
        layout_intent = json.loads(li_path.read_text(encoding="utf-8")).get("pages", {})
    paragraphs_finder = []
    pf_path = _rglob_first(run_dir, "paragraph_finder.json")
    if pf_path is not None:
        paragraphs_finder = json.loads(pf_path.read_text(encoding="utf-8")).get("page", [])

    prior_by_page = {
        str(p.get("page_number")): p.get("pdf_paragraph") or []
        for p in paragraphs_finder
    }

    pages: dict[str, PageRun] = {}
    for page in typsetting.get("page") or []:
        page_key = str(page.get("page_number"))
        mediabox = page.get("mediabox") or {}
        page_height = float(mediabox.get("y2")) if mediabox.get("y2") is not None else None
        li_entries = layout_intent.get(page_key, {})
        paras: list[ParaData] = []
        for i, para in enumerate(page.get("pdf_paragraph") or []):
            paras.append(_parse_para(i, para, li_entries))
        pages[page_key] = PageRun(
            page_key=page_key,
            page_height=page_height,
            paragraphs=paras,
        )
    return {"pages": pages}


def _parse_para(index: int, para: dict, li_entries: dict) -> ParaData:
    """Build a :class:`ParaData` from one typsetting paragraph dict."""
    intent = para.get("layout_intent")
    if intent is None:
        key = para.get("debug_id") or f"para_{index}"
        intent = li_entries.get(key)
    role = (intent or {}).get("role")
    design_box = _box_tuple((intent or {}).get("design_box"))
    wrap_mode = (intent or {}).get("wrap_mode")
    min_scale = float((intent or {}).get("min_scale") or 0.55)
    gap_contract = (intent or {}).get("gap_contract")
    style = para.get("pdf_style") or {}
    font_size = style.get("font_size")
    if font_size is not None:
        font_size = float(font_size)
    scale = float(para.get("scale") or 1.0)
    lines = line_clusters(para, tolerance=_LINE_CLUSTER_TOLERANCE)
    return ParaData(
        index=index,
        debug_id=para.get("debug_id"),
        role=role,
        box=_box_tuple(para.get("box")),
        design_box=design_box,
        wrap_mode=wrap_mode,
        min_scale=min_scale,
        gap_contract=gap_contract,
        unicode=str(para.get("unicode") or ""),
        font_size=font_size,
        scale=scale,
        lines=lines,
        has_intent=bool(intent),
    )


def _box_tuple(box) -> tuple[float, float, float, float] | None:
    if not box:
        return None
    try:
        return (float(box["x"]), float(box["y"]), float(box["x2"]), float(box["y2"]))
    except (KeyError, TypeError, ValueError):
        try:
            return (float(box[0]), float(box[1]), float(box[2]), float(box[3]))
        except (TypeError, ValueError, IndexError):
            return None


def _iter_chars(para: dict):
    """Yield character dicts from any supported composition kind (driver rule)."""
    for comp in para.get("pdf_paragraph_composition") or []:
        ch = comp.get("pdf_character")
        if ch is not None:
            yield ch
            continue
        same_style = comp.get("pdf_same_style_characters")
        if same_style is not None:
            for c in same_style.get("pdf_character") or []:
                yield c
            continue
        line = comp.get("pdf_line")
        if line is not None:
            for c in line.get("pdf_character") or []:
                yield c


def _char_box(ch: dict) -> tuple[float, float, float, float] | None:
    box = ch.get("box")
    if not box:
        return None
    try:
        return (
            float(box["x"]),
            float(box["y"]),
            float(box["x2"]),
            float(box["y2"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def line_clusters(paragraph: dict, tolerance: float = _LINE_CLUSTER_TOLERANCE) -> list[LineData]:
    """Recompute per-line (text, width, right edge, ink top/bottom) from chars.

    Mirrors ``driver.compute_line_widths`` y-clustering (tolerance 3.0) so the
    V3 orphan/right-edge numbers are identical to the digest's line widths.
    """
    boxes = []
    for ch in _iter_chars(paragraph):
        box = _char_box(ch)
        if box is not None:
            boxes.append((str(ch.get("char_unicode") or ""), box))

    if not boxes:
        return []

    # Sort by baseline y top-to-bottom (PDF y-up: larger y = higher), then by
    # ink top (y2), then left edge — deterministic reading order.
    boxes.sort(key=lambda b: (-b[1][1], b[1][3], b[1][0]))
    lines: list[list[tuple[str, tuple[float, float, float, float]]]] = []
    for text, box in boxes:
        if not lines or abs(box[1] - lines[-1][0][1][1]) > tolerance:
            lines.append([(text, box)])
        else:
            lines[-1].append((text, box))

    result: list[LineData] = []
    for line in lines:
        ordered = sorted(line, key=lambda b: b[1][0])
        text = "".join(t for t, _ in ordered)
        x0 = min(b[1][0] for b in line)
        x1 = max(b[1][2] for b in line)
        top = max(b[1][3] for b in line)
        bottom = min(b[1][1] for b in line)
        result.append(LineData(text=text, x0=x0, x1=x1, width=x1 - x0, top=top, bottom=bottom))
    return result


# --------------------------------------------------------------------------
# EN reference
# --------------------------------------------------------------------------


def load_en_reference(path: str | Path) -> dict:
    """Load and validate an EN block reference golden."""
    ref = json.loads(Path(path).read_text(encoding="utf-8"))
    if ref.get("schema") != "babeldoc-repro-en-blocks/v1":
        raise ValueError(f"{path}: unsupported EN reference schema {ref.get('schema')!r}")
    if "anchors" not in ref or "invariants" not in ref:
        raise ValueError(f"{path}: EN reference must contain anchors and invariants")
    return ref


def en_page_for_run(ref: dict, page_key: str) -> dict | None:
    """Return *ref* when it describes *page_key* (run page numbering)."""
    if str(ref.get("run_page_key")) == page_key:
        return ref
    page_no = ref.get("page_no")
    if page_no is None:
        return None
    if str(page_no) == page_key or str(int(page_no) - 1) == page_key:
        return ref
    return None


# --------------------------------------------------------------------------
# V1-V5 checks
# --------------------------------------------------------------------------


def _content_paras(page: PageRun) -> list[ParaData]:
    """Paragraphs with real translated content (intent + non-placeholder text)."""
    out = []
    for p in page.paragraphs:
        if not p.has_intent:
            continue
        text = p.unicode.strip()
        if len(text) < 2 or text.lower() in _PLACEHOLDER_TEXTS:
            continue
        out.append(p)
    return out


def _normalize(s: str) -> str:
    s = re.sub(r"\s+", "", s)
    return s.strip("。！？!?；;，、.… ").lower()


def split_sentences(text: str) -> list[str]:
    """Split *text* into sentences on CJK/Latin sentence separators."""
    parts = _SENTENCE_RE.split(text)
    return [p for p in (part.strip() for part in parts) if p]


def check_v1_anchors(page: PageRun, en: dict, th: Thresholds) -> list[CheckResult]:
    results: list[CheckResult] = []
    for anchor in en.get("anchors") or []:
        kind = anchor.get("kind")
        en_top = anchor.get("top")
        if en_top is None:
            continue
        roles = ANCHOR_ROLES.get(kind)
        if roles is None:
            continue
        item = f"V1.{anchor.get('id') or kind}"
        candidates = [
            p
            for p in _content_paras(page)
            if p.role in roles and p.box_top is not None
        ]
        in_window = [
            p for p in candidates if abs(p.box_top - en_top) <= th.anchor_match_window
        ]
        if not in_window:
            results.append(
                CheckResult(
                    item=item,
                    status="SKIP",
                    value=None,
                    threshold=f"<= {th.anchor_dy}",
                    detail=(
                        f"no run {sorted(roles)} paragraph within "
                        f"{th.anchor_match_window}pt of en_top={en_top}"
                    ),
                )
            )
            continue
        best = min(in_window, key=lambda p: (abs(p.box_top - en_top), p.box_top))
        dy = abs(best.box_top - en_top)
        status = "PASS" if dy <= th.anchor_dy else "FAIL"
        results.append(
            CheckResult(
                item=item,
                status=status,
                value=round(dy, 2),
                threshold=f"<= {th.anchor_dy}",
                detail=(
                    f"run_top={best.box_top:.1f} (debug_id={best.debug_id}, "
                    f"role={best.role}) en_top={en_top:.1f} "
                    f"ink_top={best.ink_top:.1f}"
                ),
            )
        )
    return results


def check_v2_gap(page: PageRun, en: dict, th: Thresholds) -> list[CheckResult]:
    """Big-title → body ink gap vs EN (ordinal 0 of title_to_body_gaps)."""
    bodies = [
        p
        for p in _content_paras(page)
        if p.role in BODY_LIKE_ROLES and p.box_top is not None
    ]
    if not bodies:
        return [CheckResult("V2.gap", "SKIP", detail="no body-like paragraph")]
    first_body = max(bodies, key=lambda p: p.box_top)
    titles = [
        p
        for p in _content_paras(page)
        if p.role in TITLE_LIKE_ROLES and p.box_bottom is not None
        and p.box_bottom >= first_body.box_top - 1.0
    ]
    if not titles:
        return [CheckResult("V2.gap", "SKIP", detail="no title-like paragraph above first body")]
    nearest = min(titles, key=lambda p: (p.box_bottom - first_body.box_top, p.box_bottom))
    title_ink_bottom = nearest.ink_bottom if nearest.ink_bottom is not None else nearest.box_bottom
    zh_gap = title_ink_bottom - first_body.box_top
    en_gaps = (en.get("invariants") or {}).get("title_to_body_gaps") or []
    # EN reference per acceptance doc V2: en_ink_gap := the pipeline's own
    # gap_contract (extracted from the EN layout, drop-cap-excluded). The
    # golden direct measurement is a different unit (pymupdf line bbox
    # includes font ascent/descent, which CJK em boxes do not) and would
    # overstate the deviation (p19: |20.07-18.0|=2.07 vs doc |0.53|).
    en_ref: float | None = nearest.gap_contract
    en_ref_src = "gap_contract"
    if en_ref is None:
        if not en_gaps:
            return [CheckResult("V2.gap", "SKIP", value=round(zh_gap, 2), detail="no EN gap in reference")]
        en_ref = float(en_gaps[0])
        en_ref_src = "golden"
    delta = abs(zh_gap - en_ref)
    status = "PASS" if delta <= th.gap_eps else "FAIL"
    results = [
        CheckResult(
            item="V2.gap",
            status=status,
            value=round(delta, 2),
            threshold=f"<= {th.gap_eps}",
            detail=(
                f"zh_gap={zh_gap:.2f} (title={nearest.debug_id}, role={nearest.role}, "
                f"gap_contract={nearest.gap_contract}) en_ref={en_ref:.2f} "
                f"({en_ref_src}) first_body={first_body.debug_id}"
            ),
        )
    ]
    # Extractor sanity (advisory): when the run carries a contract, the golden
    # direct measurement should agree within a loose band. A broken extractor
    # (e.g. drop-cap-inclusive 11.2pt on p19) surfaces here as WARN instead of
    # silently passing the contract gate.
    if en_ref_src == "gap_contract" and en_gaps:
        sanity = abs(en_ref - float(en_gaps[0]))
        if sanity > 3.0:
            results.append(
                CheckResult(
                    item="V2.gap_sanity",
                    status="WARN",
                    value=round(sanity, 2),
                    threshold="<= 3.0 (advisory)",
                    detail=(
                        f"gap_contract={en_ref:.2f} vs golden en_gap={float(en_gaps[0]):.2f} "
                        "(extractor may be regressing)"
                    ),
                )
            )
    return results


def check_v3_wrap_right(page: PageRun, en: dict, th: Thresholds) -> list[CheckResult]:
    """Wrap-column lines must pin to the design right edge (±0.5)."""
    violations: list[str] = []
    wrap_paras = [
        p
        for p in page.paragraphs
        if p.has_intent and p.wrap_mode == "right_fixed" and p.design_box is not None
    ]
    if not wrap_paras:
        return [CheckResult("V3.wrap_right", "SKIP", detail="no right_fixed wrap paragraph")]
    for p in wrap_paras:
        design_right = p.design_box[2]
        for line in p.lines:
            dev = abs(line.x1 - design_right)
            if dev > th.right_edge_eps:
                violations.append(
                    f"debug_id={p.debug_id} line={line.text!r} right={line.x1:.2f} "
                    f"design_right={design_right:.2f} dev={dev:.2f}"
                )
    status = "PASS" if not violations else "FAIL"
    return [
        CheckResult(
            item="V3.wrap_right",
            status=status,
            value=violations,
            threshold=f"<= {th.right_edge_eps}",
            detail=f"{len(wrap_paras)} right_fixed paragraph(s), {len(violations)} violation(s)",
        )
    ]


def check_v3_orphan(page: PageRun, en: dict, th: Thresholds) -> list[CheckResult]:
    """No single-char orphan line (width < 1.6 * font_size; last line exempt)."""
    orphans: list[str] = []
    targets = [
        p
        for p in _content_paras(page)
        if p.role in BODY_LIKE_ROLES | {"title", "section_header", "callout", "wrap_column"}
        and p.lines
    ]
    for p in targets:
        fs = p.effective_font
        if not fs:
            continue
        limit = th.orphan_width_ratio * fs
        lines = p.lines
        if th.orphan_exclude_last_line and len(lines) > 1:
            lines = lines[:-1]
        for line in lines:
            if line.width < limit:
                orphans.append(
                    f"debug_id={p.debug_id} line={line.text!r} width={line.width:.1f} "
                    f"limit={limit:.1f} (font_size={fs:.1f})"
                )
    status = "PASS" if not orphans else "FAIL"
    return [
        CheckResult(
            item="V3.orphan",
            status=status,
            value=orphans,
            threshold=f"< {th.orphan_width_ratio} * font_size",
            detail=f"{len(orphans)} orphan line(s) across {len(targets)} paragraph(s)",
        )
    ]


def check_v3_font_scale(page: PageRun, en: dict, th: Thresholds) -> list[CheckResult]:
    """Effective font size must stay >= min_scale * EN original (per role)."""
    orig_sizes = (en.get("invariants") or {}).get("original_font_sizes") or {}
    fails: list[str] = []
    checked = 0
    for p in page.paragraphs:
        if not p.has_intent or not p.role or p.effective_font is None:
            continue
        en_size = orig_sizes.get(p.role)
        if en_size is None:
            continue
        checked += 1
        floor = p.min_scale * float(en_size)
        if p.effective_font < floor - 1e-9:
            fails.append(
                f"debug_id={p.debug_id} role={p.role} effective_font={p.effective_font:.2f} "
                f"< min_scale={p.min_scale} * en={en_size:.1f} = {floor:.2f}"
            )
    if checked == 0:
        return [CheckResult("V3.font_scale", "SKIP", detail="no role-matched paragraph with font size")]
    status = "PASS" if not fails else "FAIL"
    return [
        CheckResult(
            item="V3.font_scale",
            status=status,
            value=fails,
            threshold=">= min_scale * en_font_size",
            detail=f"{checked} paragraph(s) checked, {len(fails)} below floor",
        )
    ]


def check_v4_repeats(page: PageRun, en: dict, th: Thresholds) -> list[CheckResult]:
    """No sentence (or line) repeated >= repeat_min times consecutively."""
    paragraphs = _content_paras(page)
    text = "\n".join(p.unicode for p in paragraphs)
    sentences = split_sentences(text)
    normalized = [_normalize(s) for s in sentences]
    dup_sentences: list[str] = []
    for i in range(1, len(normalized)):
        if normalized[i] and normalized[i] == normalized[i - 1]:
            dup_sentences.append(sentences[i])
    # Also detect consecutive duplicate lines inside a single paragraph.
    dup_lines: list[str] = []
    for p in paragraphs:
        line_texts = [ln.text for ln in p.lines]
        for i in range(1, len(line_texts)):
            if _normalize(line_texts[i]) and _normalize(line_texts[i]) == _normalize(line_texts[i - 1]):
                dup_lines.append(f"debug_id={p.debug_id} line={line_texts[i]!r}")
    value = {"sentences": dup_sentences, "lines": dup_lines}
    status = "PASS" if not dup_sentences and not dup_lines else "FAIL"
    return [
        CheckResult(
            item="V4.repeat",
            status=status,
            value=value,
            threshold=f"< {th.repeat_min} consecutive",
            detail=f"{len(dup_sentences)} duplicated sentence(s), {len(dup_lines)} duplicated line(s)",
        )
    ]


def check_v4_dangling(page: PageRun, en: dict, th: Thresholds) -> list[CheckResult]:
    """No dangling punctuation: line must not open with sentence-end punct or
    close with an opening bracket, and must not be punctuation alone."""
    bad: list[str] = []
    for p in page.paragraphs:
        for line in p.lines:
            text = line.text.strip()
            if not text:
                continue
            if text[0] in _LINE_OPEN_BAD:
                bad.append(f"debug_id={p.debug_id} opens with {text[0]!r}: {text!r}")
            if text[-1] in _LINE_CLOSE_BAD:
                bad.append(f"debug_id={p.debug_id} closes with {text[-1]!r}: {text!r}")
            if all(c in _LINE_OPEN_BAD | _LINE_CLOSE_BAD | set("'\"") for c in text):
                bad.append(f"debug_id={p.debug_id} punctuation-only line: {text!r}")
    status = "PASS" if not bad else "FAIL"
    return [
        CheckResult(
            item="V4.dangling",
            status=status,
            value=bad,
            threshold="no line starts/ends with dangling punctuation",
            detail=f"{len(bad)} dangling punctuation line(s)",
        )
    ]


def check_v5_callout(page: PageRun, en: dict, th: Thresholds) -> list[CheckResult]:
    """Callout sentences must not duplicate body sentences (one-to-one)."""
    callouts = [
        p for p in _content_paras(page) if p.role == "callout"
    ]
    bodies = [
        p for p in _content_paras(page) if p.role in BODY_LIKE_ROLES
    ]
    body_sentences = {
        _normalize(s)
        for p in bodies
        for s in split_sentences(p.unicode)
        if _normalize(s)
    }
    cross: list[str] = []
    intra: list[str] = []
    for c in callouts:
        sentences = split_sentences(c.unicode)
        normalized = [_normalize(s) for s in sentences]
        for s, n in zip(sentences, normalized):
            if n and n in body_sentences:
                cross.append(f"callout {c.debug_id}: {s!r} also in body")
        for i in range(1, len(normalized)):
            if normalized[i] and normalized[i] == normalized[i - 1]:
                intra.append(f"callout {c.debug_id}: {sentences[i]!r} repeated")
    en_count = (en.get("invariants") or {}).get("callout_count")
    notes: list[str] = []
    if en_count is not None and len(callouts) != int(en_count):
        notes.append(f"count {len(callouts)} != en {en_count} (informational)")
    violations = cross + intra
    status = "PASS" if not violations else "FAIL"
    results = [
        CheckResult(
            item="V5.callout",
            status=status,
            value=violations,
            threshold="no callout/body sentence duplication",
            detail=f"{len(callouts)} callout(s), {len(cross)} cross-dup, {len(intra)} intra-dup"
            + (f"; {notes[0]}" if notes else ""),
        )
    ]
    if notes:
        results.append(CheckResult("V5.callout_count", "WARN", value=len(callouts), detail=notes[0]))
    return results


def check_v5_header(page: PageRun, en: dict, th: Thresholds) -> list[CheckResult]:
    """Running-header chrome in the top band must contain no CJK (skip works)."""
    page_height = page.page_height
    if page_height is None:
        en_size = en.get("page_size") or []
        page_height = float(en_size[1]) if len(en_size) > 1 else None
    if page_height is None:
        return [CheckResult("V5.header", "SKIP", detail="unknown page height")]
    band = page_height - th.header_zone
    headers = [
        p
        for p in page.paragraphs
        if p.has_intent and p.role == "chrome" and p.box_top is not None
        and p.box_top >= band
    ]
    if not headers:
        return [CheckResult("V5.header", "SKIP", detail=f"no chrome paragraph in top {th.header_zone}pt")]
    bad = [
        f"debug_id={p.debug_id} cjk={_CJK_RE.findall(p.unicode)} text={p.unicode[:40]!r}"
        for p in headers
        if _CJK_RE.search(p.unicode)
    ]
    status = "PASS" if not bad else "FAIL"
    return [
        CheckResult(
            item="V5.header",
            status=status,
            value=bad,
            threshold="no CJK in header-band chrome",
            detail=f"{len(headers)} header paragraph(s), {len(bad)} with CJK",
        )
    ]


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------

PAGE_CHECKERS = (
    check_v1_anchors,
    check_v2_gap,
    check_v3_wrap_right,
    check_v3_orphan,
    check_v3_font_scale,
    check_v4_repeats,
    check_v4_dangling,
    check_v5_callout,
    check_v5_header,
)


def check_page(page: PageRun, en: dict, th: Thresholds | None = None) -> list[CheckResult]:
    th = th or Thresholds()
    results: list[CheckResult] = []
    for checker in PAGE_CHECKERS:
        results.extend(checker(page, en, th))
    return results


def check_run_dir(
    run_dir: str | Path,
    en_reference: str | Path | dict,
    *,
    thresholds: Thresholds | None = None,
    page_keys: list[str] | None = None,
) -> dict:
    """Run V1-V5 checks for a run-dir against an EN reference golden.

    Returns a structured report dict (see module docstring for schema).
    """
    run = load_run(run_dir)
    if isinstance(en_reference, (str, Path)):
        en_reference = load_en_reference(en_reference)
    th = thresholds or Thresholds()

    pages_report: dict[str, dict] = {}
    totals = {"pass": 0, "fail": 0, "skip": 0, "warn": 0}
    for page_key in sorted(run["pages"]):
        if page_keys is not None and page_key not in page_keys:
            continue
        en = en_page_for_run(en_reference, page_key)
        if en is None:
            pages_report[page_key] = {
                "checks": [
                    CheckResult(
                        "reference",
                        "SKIP",
                        detail="no EN reference for this run page",
                    ).to_dict()
                ],
                "summary": {"pass": 0, "fail": 0, "skip": 1, "warn": 0},
            }
            totals["skip"] += 1
            continue
        results = check_page(run["pages"][page_key], en, th)
        summary = {"pass": 0, "fail": 0, "skip": 0, "warn": 0}
        for r in results:
            summary[r.status.lower()] += 1
            totals[r.status.lower()] += 1
        pages_report[page_key] = {
            "checks": [r.to_dict() for r in results],
            "summary": summary,
        }

    all_pass = totals["fail"] == 0
    return {
        "schema": SCHEMA,
        "run_dir": str(Path(run_dir).resolve()),
        "en_reference": (
            str(Path(en_reference).resolve())
            if isinstance(en_reference, (str, Path))
            else "(inline)"
        ),
        "thresholds": {
            "anchor_dy": th.anchor_dy,
            "gap_eps": th.gap_eps,
            "right_edge_eps": th.right_edge_eps,
            "orphan_width_ratio": th.orphan_width_ratio,
            "repeat_min": th.repeat_min,
            "header_zone": th.header_zone,
        },
        "pages": pages_report,
        "summary": totals,
        "all_pass": all_pass,
    }


def format_report(report: dict) -> str:
    lines = [
        f"visual layout check: {report['summary']['pass']} pass / "
        f"{report['summary']['fail']} fail / {report['summary']['skip']} skip / "
        f"{report['summary']['warn']} warn"
    ]
    for page_key in sorted(report["pages"]):
        page = report["pages"][page_key]
        lines.append(f"  page {page_key}:")
        for check in page["checks"]:
            value = check.get("value")
            if isinstance(value, list) and value:
                value = f"{len(value)} item(s)"
            elif value is None:
                value = ""
            lines.append(
                f"    {check['item']:<22} {check['status']:<5} "
                f"th={check.get('threshold') or '-':<34} val={value} {check.get('detail')}"
            )
    lines.append(f"all_pass={report['all_pass']}")
    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--run-dir", required=True, help="repro run dir (typsetting.json + siblings)")
    parser.add_argument(
        "--en-reference",
        required=True,
        help="EN block reference golden (tests/repro/golden/en_pXX_blocks.json)",
    )
    parser.add_argument("--json", action="store_true", help="print the raw report as JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    report = check_run_dir(args.run_dir, args.en_reference)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(format_report(report))
    return 0 if report["all_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
