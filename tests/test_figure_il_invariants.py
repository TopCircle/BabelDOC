"""Figure golden IL invariants — text integrity before MT.

Hard gate after any change to paragraph_finder / stream_order / text_recovery:

  * Key science phrases must survive into paragraph_finder unicode.
  * Descender-smashed fragments (seudo / operah) must not appear as the
    only form of those words.

Full pipeline to paragraph_finder needs layout assets; skip if missing.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

GOLDEN_SRC = (
    Path(__file__).resolve().parent
    / "golden"
    / "translate.cli.text.with.figure.pdf"
)

# Must appear (substring, case-insensitive) in joined paragraph unicode.
# Hyphen optional: soft-hyphen recovery may normalize spacing around it.
REQUIRED_PHRASE_RES = (
    re.compile(r"pseudo[-\s]?syndrome", re.I),
    re.compile(r"syndrome\s+detection", re.I),
    re.compile(r"composite\s+operation", re.I),
)

# If present without a nearby healthy form, treat as regression.
# "seudo" alone is allowed only as part of "pseudo".
FORBIDDEN_FRAGMENT_RES = (
    re.compile(r"(?<![pP])seudo"),  # seudo not preceded by p
    re.compile(r"operah"),
    re.compile(r"markin\s+techni"),  # split marking technique
    re.compile(r"s\s+ndrome"),  # s ndrome
)


def _joined_paragraph_unicode(paragraph_finder_json: Path) -> str:
    data = json.loads(paragraph_finder_json.read_text(encoding="utf-8"))
    parts: list[str] = []
    for page in data.get("page") or []:
        for para in page.get("pdf_paragraph") or []:
            u = para.get("unicode") or ""
            if u:
                parts.append(u)
    return "\n".join(parts)


def test_figure_golden_paragraph_finder_key_phrases(tmp_path: Path):
    """Run figure source through IL → paragraph_finder; assert text integrity."""
    if not GOLDEN_SRC.is_file():
        pytest.skip(f"missing golden source: {GOLDEN_SRC}")

    work = tmp_path / "work"
    out = tmp_path / "out"
    work.mkdir()
    out.mkdir()

    cmd = [
        sys.executable,
        "-m",
        "babeldoc.main",
        "--files",
        str(GOLDEN_SRC),
        "--lang-in",
        "en",
        "--lang-out",
        "zh-CN",
        "--skip-translation",
        "--openai",
        "--openai-api-key",
        "dummy",
        "--openai-model",
        "gpt-4o-mini",
        "--debug",
        "--no-watermark",
        "--skip-scanned-detection",
        "--no-auto-extract-glossary",
        "--no-dual",
        "--working-dir",
        str(work),
        "--output",
        str(out),
    ]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(Path(__file__).resolve().parents[1]),
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except subprocess.TimeoutExpired:
        pytest.fail("babeldoc figure IL pipeline timed out (>180s)")

    if proc.returncode != 0:
        # Missing layout assets / onnx → skip rather than fail bare CI
        err = (proc.stderr or "") + (proc.stdout or "")
        if any(
            k in err.lower()
            for k in ("onnx", "doclayout", "warmup", "no such file", "cannot open")
        ):
            pytest.skip(f"layout assets unavailable: {err[-500:]}")
        pytest.fail(
            f"babeldoc failed rc={proc.returncode}\n"
            f"stdout tail:\n{(proc.stdout or '')[-800:]}\n"
            f"stderr tail:\n{(proc.stderr or '')[-800:]}"
        )

    dumps = list(work.rglob("paragraph_finder.json"))
    assert dumps, f"no paragraph_finder.json under {work}"
    joined = _joined_paragraph_unicode(dumps[0])
    assert joined.strip(), "empty paragraph unicode"

    for rx in REQUIRED_PHRASE_RES:
        assert rx.search(joined), (
            f"missing required phrase /{rx.pattern}/ in paragraph_finder unicode "
            f"(len={len(joined)}). Sample:\n{joined[:600]}"
        )
    # Prefer hyphenated compound kept (not glued to pseudosyndrome)
    assert "pseudosyndrome" not in joined.lower().replace(" ", ""), (
        "intentional compound pseudo-syndrome was glued to pseudosyndrome"
    )

    for rx in FORBIDDEN_FRAGMENT_RES:
        m = rx.search(joined)
        assert m is None, (
            f"forbidden fragment {rx.pattern!r} matched {m.group(0)!r} — "
            f"stream_order/paragraph_finder likely smashed body text.\n"
            f"Context: …{joined[max(0, m.start() - 40) : m.end() + 40]}…"
        )


def test_figure_il_invariants_unit_plain_text_gate():
    """Fast gate: plain text never reorders reverse decorative geometry."""
    from babeldoc.format.pdf.document_il.il_version_1 import Box
    from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter
    from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
    from babeldoc.format.pdf.document_il.il_version_1 import VisualBbox
    from babeldoc.format.pdf.document_il.utils.stream_order import (
        is_stream_visually_reversed,
        maybe_reorder_reversed_stream,
    )

    def ch(text: str, x: float) -> PdfCharacter:
        box = Box(x=x, y=100, x2=x + 8, y2=112)
        return PdfCharacter(
            pdf_character_id=None,
            char_unicode=text,
            box=box,
            visual_bbox=VisualBbox(box=box),
            pdf_style=PdfStyle(font_id="base", font_size=12.0, graphic_state=None),
            scale=1.0,
            advance=8.0,
            vertical=False,
            xobj_id=None,
        )

    letters = list("Who haS orgaSMS?")
    xs = list(range(100, 100 + 10 * len(letters), 10))
    stream = [ch(c, x) for c, x in zip(reversed(letters), reversed(xs))]
    assert is_stream_visually_reversed(stream)
    assert maybe_reorder_reversed_stream(stream, layout_label="plain text") is stream
    assert maybe_reorder_reversed_stream(stream, layout_label="title") is not stream
