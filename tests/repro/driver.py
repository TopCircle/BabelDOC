"""Parameterized repro driver for the layout digest regression gate.

Replaces the old hardcoded ``/private/tmp/oa_review/repro_driver.py``: all
paths and page numbers come from the CLI, the translator is the in-repo
:class:`babeldoc.translator.fixed_map_translator.FixedMapTranslator`, and the
full pipeline is invoked through ``babeldoc.high_level.translate``.

Outputs (besides the mono PDF):

* ``<working-dir>/repro_typsetting_summary.json`` — canonical typsetting
  summary (see :func:`build_typsetting_summary`) plus the
  ``il_layout_fingerprint`` sha256 of the post-typeset document and the prior
  ``paragraph_finder`` debug_id set.

Line widths are **never** read from ``reference_metrics.per_line_widths``:
they are recomputed from ``pdf_character`` boxes clustered by y (plan §2).

Usage::

    python tests/repro/driver.py \
        --pdf path/to/page19.pdf --pages 19 \
        --working-dir /tmp/run --out-dir /tmp/run/out \
        --map-json oa_p19_map.json --translator fixedmap
"""

from __future__ import annotations

import argparse
import copy
import json
import random
import sys
from contextlib import contextmanager
from pathlib import Path

from babeldoc.format.pdf.document_il.utils.il_layout_fingerprint import (
    il_layout_fingerprint,
)
from babeldoc.format.pdf.document_il.xml_converter import XMLConverter
from babeldoc.format.pdf.high_level import translate
from babeldoc.format.pdf.translation_config import TranslationConfig
from babeldoc.format.pdf.translation_config import WatermarkOutputMode
from babeldoc.translator.fixed_map_translator import FixedMapTranslator

#: Summary artifact written into the user-facing working dir.
SUMMARY_FILENAME = "repro_typsetting_summary.json"

#: y-clustering tolerance for line reconstruction (points).
LINE_CLUSTER_TOLERANCE = 3.0

#: Fixed RNG seed for the pipeline run. BabelDOC's ParagraphFinder assigns
#: random base58 ``debug_id`` values (paragraph_finder.py:generate_base58_id),
#: which would make the prior debug_id set and the geometry fingerprint differ
#: between identical runs. Plan §2 asserts the prior debug_id set is unchanged,
#: so the repro harness pins the RNG around ``translate()`` (state restored
#: afterwards).
REPRO_RANDOM_SEED = 0

#: Default skip-header/footer geometry. Generic page defaults; the OA p19
#: local golden pass overrides via --header-height/--footer-height (see
#: README.md) instead of hardcoding OA-specific numbers here.
DEFAULT_HEADER_HEIGHT = 40.0
DEFAULT_FOOTER_HEIGHT = 40.0


def load_mapping(map_json: str | Path | None) -> dict[str, str]:
    """Load an exact-match ``{source: target}`` translation map."""
    if not map_json:
        return {}
    data = json.loads(Path(map_json).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"--map-json must be a JSON object, got {type(data).__name__}")
    return {str(k): str(v) for k, v in data.items()}


def make_translator(
    translator_name: str,
    mapping: dict[str, str],
) -> FixedMapTranslator:
    """Return a :class:`FixedMapTranslator` for the requested mode.

    ``identity`` ignores ``mapping`` (pure pass-through); ``fixedmap`` applies
    the exact-match mapping. Both reuse the in-repo translator.
    """
    if translator_name == "identity":
        return FixedMapTranslator({})
    if translator_name == "fixedmap":
        return FixedMapTranslator(mapping)
    raise ValueError(f"unknown translator: {translator_name!r}")


def _iter_composition_chars(comp: dict):
    """Yield character dicts from any supported composition kind."""
    ch = comp.get("pdf_character")
    if ch is not None:
        yield ch
        return
    same_style = comp.get("pdf_same_style_characters")
    if same_style is not None:
        for c in same_style.get("pdf_character") or []:
            yield c
        return
    line = comp.get("pdf_line")
    if line is not None:
        for c in line.get("pdf_character") or []:
            yield c


def _char_box(ch: dict) -> tuple[float, float, float, float] | None:
    box = ch.get("box")
    if not box:
        return None
    try:
        return (float(box["x"]), float(box["y"]), float(box["x2"]), float(box["y2"]))
    except (KeyError, TypeError, ValueError):
        return None


def compute_line_widths(paragraph: dict, tolerance: float = LINE_CLUSTER_TOLERANCE) -> list[float]:
    """Recompute per-line widths from ``pdf_character`` boxes by y-clustering.

    Plan §2 rule: this harness must **not** use
    ``reference_metrics.per_line_widths``. Characters are clustered on their
    baseline y (PDF y-up) with ``tolerance``; each cluster is one line and its
    width is ``max(x2) - min(x)``.
    """
    boxes = []
    for comp in paragraph.get("pdf_paragraph_composition") or []:
        for ch in _iter_composition_chars(comp):
            box = _char_box(ch)
            if box is not None:
                boxes.append(box)

    if not boxes:
        return []

    # Sort by baseline (y) top-to-bottom (PDF y-up: larger y = higher on
    # page), then top (y2), then left edge — deterministic reading order.
    boxes.sort(key=lambda b: (-b[1], b[3], b[0]))
    lines: list[list[tuple[float, float, float, float]]] = []
    for box in boxes:
        if not lines or abs(box[1] - lines[-1][0][1]) > tolerance:
            lines.append([box])
        else:
            lines[-1].append(box)
    return [max(b[2] for b in line) - min(b[0] for b in line) for line in lines]


def _paragraph_summary(paragraph: dict) -> dict:
    box = paragraph.get("box")
    return {
        "box": (
            [box["x"], box["y"], box["x2"], box["y2"]]
            if box
            else None
        ),
        "scale": paragraph.get("scale"),
        "optimal_scale": paragraph.get("optimal_scale"),
        "line_widths": compute_line_widths(paragraph),
    }


def _collect_debug_ids(prior_doc: dict) -> dict[str, list[str]]:
    """Map page_number -> sorted prior (paragraph_finder) debug_ids."""
    result: dict[str, list[str]] = {}
    for page in prior_doc.get("page") or []:
        page_no = str(page.get("page_number"))
        ids = sorted(
            p.get("debug_id")
            for p in page.get("pdf_paragraph") or []
            if p.get("debug_id")
        )
        result[page_no] = ids
    return result


def build_typsetting_summary(
    typsetting_path: Path,
    paragraph_finder_path: Path | None,
) -> dict:
    """Build the canonical typsetting summary from debug JSON.

    Shape (plan §2): ``{page: {debug_id: {box, scale, optimal_scale,
    line_widths[]}}}`` plus the prior debug_id set per page.
    """
    typsetting = json.loads(Path(typsetting_path).read_text(encoding="utf-8"))
    prior_debug_ids: dict[str, list[str]] = {}
    if paragraph_finder_path is not None and paragraph_finder_path.exists():
        prior_debug_ids = _collect_debug_ids(
            json.loads(paragraph_finder_path.read_text(encoding="utf-8"))
        )

    pages: dict[str, dict] = {}
    for page in typsetting.get("page") or []:
        page_no = str(page.get("page_number"))
        paragraphs: dict[str, dict] = {}
        for para in page.get("pdf_paragraph") or []:
            debug_id = para.get("debug_id")
            if not debug_id:
                # Fragment/line-level paragraphs (debug_id cleared) are not
                # part of the prior set and carry no stable identity — skip.
                continue
            paragraphs[debug_id] = _paragraph_summary(para)
        pages[page_no] = {
            "debug_ids": prior_debug_ids.get(page_no, []),
            "paragraphs": paragraphs,
        }
    return {"pages": pages}


def find_typsetting_json(working_dir: Path) -> Path | None:
    """Locate ``typsetting.json`` written by the pipeline.

    The pipeline appends the input-file stem to ``working_dir``, so search
    recursively (bounded) to stay robust across split/part layouts.
    """
    candidates = sorted(Path(working_dir).rglob("typsetting.json"))
    return candidates[0] if candidates else None


@contextmanager
def capture_layout_fingerprint():
    """Capture the post-typeset document fingerprint at typsetting write.

    ``translate()`` is a black box, so we hook ``XMLConverter.write_json``:
    when ``typsetting.json`` is flushed we fingerprint the in-memory
    :class:`~babeldoc.format.pdf.document_il.il_version_1.Document` (the same
    object the digest golden gates on).
    """
    captured: dict[str, str] = {}
    original = XMLConverter.write_json

    def wrapped(self, document, path):
        result = original(self, document, path)
        if (
            Path(path).name == "typsetting.json"
            and "fingerprint" not in captured
        ):
            captured["fingerprint"] = il_layout_fingerprint(copy.deepcopy(document))
        return result

    XMLConverter.write_json = wrapped
    try:
        yield captured
    finally:
        XMLConverter.write_json = original


def run_translate(
    pdf: str | Path,
    pages: str,
    working_dir: str | Path,
    out_dir: str | Path,
    *,
    mapping: dict[str, str] | None = None,
    map_json: str | Path | None = None,
    translator_name: str = "identity",
    lang_in: str = "en",
    lang_out: str = "zh-CN",
    skip_header: bool = True,
    header_height: float = DEFAULT_HEADER_HEIGHT,
    skip_footer: bool = True,
    footer_height: float = DEFAULT_FOOTER_HEIGHT,
) -> dict:
    """Run the full pipeline and return the repro summary (and write it)."""
    working_dir = Path(working_dir)
    out_dir = Path(out_dir)
    working_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    if mapping is None:
        mapping = load_mapping(map_json)
    translator = make_translator(translator_name, mapping)

    config = TranslationConfig(
        translator=translator,
        input_file=str(pdf),
        lang_in=lang_in,
        lang_out=lang_out,
        doc_layout_model=None,  # auto-loads cached ONNX assets
        pages=pages,
        output_dir=str(out_dir),
        working_dir=str(working_dir),
        debug=True,
        no_dual=True,
        watermark_output_mode=WatermarkOutputMode.NoWatermark,
        skip_header=skip_header,
        header_height=header_height,
        skip_footer=skip_footer,
        footer_height=footer_height,
    )

    rng_state = random.getstate()
    random.seed(REPRO_RANDOM_SEED)
    try:
        with capture_layout_fingerprint() as captured:
            result = translate(config)
            fingerprint = captured.get("fingerprint")
    finally:
        random.setstate(rng_state)
    if fingerprint is None:
        raise RuntimeError(
            "failed to capture post-typeset fingerprint "
            "(typsetting.json was never written?)"
        )

    typsetting_path = find_typsetting_json(working_dir)
    if typsetting_path is None:
        raise RuntimeError(f"typsetting.json not found under {working_dir}")
    summary = build_typsetting_summary(
        typsetting_path,
        typsetting_path.with_name("paragraph_finder.json"),
    )
    summary["source"] = str(Path(pdf).resolve())
    summary["fingerprint_sha256"] = fingerprint

    summary_path = working_dir / SUMMARY_FILENAME
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    return {
        "summary": summary,
        "summary_path": summary_path,
        "mono_pdf_path": result.mono_pdf_path,
        "typsetting_path": typsetting_path,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--pdf", required=True, help="input PDF path")
    parser.add_argument("--pages", default="1", help="pages spec, e.g. '19' or '1'")
    parser.add_argument("--working-dir", required=True, help="working directory")
    parser.add_argument("--out-dir", required=True, help="output directory (mono PDF)")
    parser.add_argument(
        "--map-json",
        default=None,
        help="JSON object {source: target} exact-match translation map",
    )
    parser.add_argument(
        "--translator",
        choices=("fixedmap", "identity"),
        default="identity",
        help="translator mode (both reuse FixedMapTranslator)",
    )
    parser.add_argument("--header-height", type=float, default=DEFAULT_HEADER_HEIGHT)
    parser.add_argument("--footer-height", type=float, default=DEFAULT_FOOTER_HEIGHT)
    parser.add_argument("--no-skip-header", action="store_true")
    parser.add_argument("--no-skip-footer", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    result = run_translate(
        pdf=args.pdf,
        pages=args.pages,
        working_dir=args.working_dir,
        out_dir=args.out_dir,
        map_json=args.map_json,
        translator_name=args.translator,
        skip_header=not args.no_skip_header,
        header_height=args.header_height,
        skip_footer=not args.no_skip_footer,
        footer_height=args.footer_height,
    )
    summary = result["summary"]
    print(f"mono pdf : {result['mono_pdf_path']}")
    print(f"summary  : {result['summary_path']}")
    print(f"pages    : {sorted(summary['pages'])}")
    print(f"fingerprint: {summary['fingerprint_sha256']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
