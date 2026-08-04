"""Synthetic acceptance page for the layout repro harness.

The synthesised page deliberately mixes the four paragraph roles the
Layout-First P0 design cares about (``title`` + ``wrap_column`` + ``chrome``
+ ``body``) so the CI layout-repro job can exercise the midend without the
proprietary OA original.

Two artifacts are derived from the same ``SYNTH_PARAGRAPHS`` spec:

* :func:`write_synth_pdf` — a deterministic pymupdf-rendered PDF that the
  repro driver feeds to ``babeldoc.high_level.translate`` (full pipeline:
  parse → doclayout → paragraph finder → styles → translate → typesetting).
* :func:`build_synth_il_document` — the equivalent ``il_version_1.Document``
  (used by unit tests and as documentation of the intended page layout).

Nothing here may reference the OA original or any absolute path: the page is
fully self-contained so CI can run without network or proprietary assets.
"""

from __future__ import annotations

from dataclasses import dataclass

from babeldoc.format.pdf.document_il import il_version_1
from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import Page
from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraphComposition
from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
from babeldoc.format.pdf.document_il.il_version_1 import VisualBbox

#: Deterministic input PDF name produced by :func:`write_synth_pdf`.
SYNTH_PDF_NAME = "synth_page.pdf"

#: A4 portrait page size in points (pymupdf and IL share the same unit).
SYNTH_PAGE_WIDTH = 595.0
SYNTH_PAGE_HEIGHT = 842.0


@dataclass(frozen=True)
class SynthParagraph:
    """One paragraph of the synthetic page (both PDF and IL views)."""

    debug_id: str
    role: str
    layout_label: str
    font_size: float
    box: tuple[float, float, float, float]
    lines: tuple[str, ...]


#: Single source of truth for the synthetic page. Keep the order stable —
#: the digest golden is a byte-level gate, reordering would invalidate it.
SYNTH_PARAGRAPHS: tuple[SynthParagraph, ...] = (
    SynthParagraph(
        debug_id="synth_chrome_header",
        role="chrome",
        layout_label="header",
        font_size=9.0,
        box=(50.0, 800.0, 320.0, 812.0),
        lines=("ORGASMIC ADDICTION",),
    ),
    SynthParagraph(
        debug_id="synth_title",
        role="title",
        layout_label="title",
        font_size=24.0,
        box=(100.0, 700.0, 300.0, 728.0),
        lines=("Chapter 3",),
    ),
    SynthParagraph(
        debug_id="synth_wrap_column",
        role="wrap_column",
        layout_label="figure_wrap",
        font_size=10.0,
        box=(400.0, 420.0, 560.0, 480.0),
        lines=(
            "Women love a man with a plan.",
            "In fact, it is planning",
            "that is at the root of",
            "all good romance.",
        ),
    ),
    SynthParagraph(
        debug_id="synth_body",
        role="body",
        layout_label="plain text",
        font_size=10.0,
        box=(100.0, 300.0, 500.0, 410.0),
        lines=(
            "In order to work through the exercises in this book you",
            "will need to take charge of your sex life and start",
            "directing the flow of development in your relationship.",
            "Mindblowing orgasms and incredible intimacy await the",
            "man who is prepared to do the work plans and stick",
            "to the program.",
        ),
    ),
)


def _line_baselines(para: SynthParagraph) -> list[float]:
    """Baseline y (PDF y-up) for each rendered line of ``para``.

    Deterministic: first line sits near the box top, subsequent lines step
    down by ``1.2 * font_size``.
    """
    fs = para.font_size
    top = para.box[3]
    line_h = fs * 1.2
    return [top - fs * 0.2 - i * line_h for i in range(len(para.lines))]


def write_synth_pdf(path) -> None:
    """Render the synthetic page to a deterministic PDF at ``path``."""
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page(width=SYNTH_PAGE_WIDTH, height=SYNTH_PAGE_HEIGHT)
    for para in SYNTH_PARAGRAPHS:
        x0 = para.box[0]
        for line, baseline in zip(para.lines, _line_baselines(para), strict=True):
            page.insert_text(
                (x0, baseline),
                line,
                fontsize=para.font_size,
                fontname="helv",
            )
    doc.save(str(path))
    doc.close()


def build_synth_il_document() -> il_version_1.Document:
    """Build the ``il_version_1.Document`` mirroring the synthetic page."""
    paragraphs = []
    for para in SYNTH_PARAGRAPHS:
        fs = para.font_size
        style = PdfStyle(font_id="f0", font_size=fs, graphic_state=None)
        compositions = []
        for line, baseline in zip(para.lines, _line_baselines(para), strict=True):
            x = float(para.box[0])
            y = baseline - fs * 0.2
            for ch in line:
                width = fs * 0.6
                box = Box(x=x, y=y, x2=x + width, y2=baseline + fs * 0.8)
                compositions.append(
                    PdfParagraphComposition(
                        pdf_character=PdfCharacter(
                            pdf_character_id=None,
                            char_unicode=ch,
                            box=box,
                            visual_bbox=VisualBbox(box=box),
                            pdf_style=style,
                            scale=1.0,
                            advance=width,
                            vertical=False,
                            xobj_id=None,
                        )
                    )
                )
                x += width
        paragraphs.append(
            PdfParagraph(
                box=Box(*para.box),
                pdf_style=style,
                pdf_paragraph_composition=compositions,
                unicode=" ".join(para.lines),
                debug_id=para.debug_id,
                layout_label=para.layout_label,
            )
        )
    return il_version_1.Document(
        page=[
            Page(
                page_number=1,
                mediabox=Box(
                    x=0,
                    y=0,
                    x2=SYNTH_PAGE_WIDTH,
                    y2=SYNTH_PAGE_HEIGHT,
                ),
                pdf_paragraph=paragraphs,
            )
        ]
    )


def synth_roles() -> set[str]:
    """Roles covered by the synthetic page (used by unit tests)."""
    return {p.role for p in SYNTH_PARAGRAPHS}
