"""Line-wrap word boundaries must not glue words (All Tied Up intro).

PDF often encodes a trailing space at EOL; process_paragraph_spacing strips it.
get_char_unicode_string / add_space_dummy_chars must still insert a space when
the next char jumps back to the left margin (distance << 0).
"""

from __future__ import annotations

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter
from babeldoc.format.pdf.document_il.il_version_1 import PdfLine
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraphComposition
from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
from babeldoc.format.pdf.document_il.il_version_1 import VisualBbox
from babeldoc.format.pdf.document_il.utils.layout_helper import (
    _add_space_dummy_chars_to_list,
)
from babeldoc.format.pdf.document_il.utils.layout_helper import add_space_dummy_chars
from babeldoc.format.pdf.document_il.utils.layout_helper import get_char_unicode_string
from babeldoc.format.pdf.document_il.utils.layout_helper import get_paragraph_unicode


class TestSoftHyphenJoin:
    """TeX line-wrap soft hyphens must rejoin before translate (figure dual)."""

    def test_ap_proximation_rejoins(self):
        # Line1 ends with ``ap-``, line2 starts ``proximation`` at left margin
        chars = [
            _ch("a", 50, y=200),
            _ch("p", 56, y=200),
            _ch("-", 62, y=200),
            _ch("p", 50, y=185, w=6),  # newline: lower y, x jumps left
            _ch("r", 56, y=185),
            _ch("o", 62, y=185),
            _ch("x", 68, y=185),
        ]
        text = get_char_unicode_string(chars)
        # Soft hyphen dropped and no wrap space: ap- + prox → approx
        assert text.replace(" ", "") == "approx"
        assert "-" not in text

    def test_intentional_dash_before_actually_not_glued(self):
        """Day6 TOC: ``Trigasm- actually`` must not become ``Trigasmactually``.

        That glue produced mono garbage ``TrigasMacTuaLLy`` after MT casing.
        """
        from babeldoc.format.pdf.document_il.utils import text_recovery

        src = "4. Trigasm- actually, make hers triple, please!"
        out = text_recovery.rejoin_soft_hyphens_in_text(src)
        assert "Trigasmactually" not in out
        assert "Trigasm- actually" in out
        # Decorative mixed-case TOC (per-glyph style) — regression for 0.6.4.18
        # which only captured lowercase ``ac`` and glued to TrigasMacTuaLLy.
        deco = "4. TrigasM- acTuaLLy, Make Hers TripLe, pLease!"
        deco_out = text_recovery.rejoin_soft_hyphens_in_text(deco)
        assert "TrigasMacTuaLLy" not in deco_out
        assert "acTuaLLy" in deco_out
        # True soft hyphen still rejoins
        assert (
            text_recovery.rejoin_soft_hyphens_in_text(
                "dispersive ap- proximation breaks"
            )
            == "dispersive approximation breaks"
        )

    def test_line_wrap_before_free_word_keeps_space(self):
        # ``Trigasm-`` EOL then ``actually`` — intentional dash, not soft hyphen
        chars = [
            _ch("T", 50, y=200),
            _ch("r", 56, y=200),
            _ch("i", 62, y=200),
            _ch("g", 68, y=200),
            _ch("a", 74, y=200),
            _ch("s", 80, y=200),
            _ch("m", 86, y=200),
            _ch("-", 92, y=200),
            _ch("a", 50, y=185),  # wrap
            _ch("c", 56, y=185),
            _ch("t", 62, y=185),
            _ch("u", 68, y=185),
            _ch("a", 74, y=185),
            _ch("l", 80, y=185),
            _ch("l", 86, y=185),
            _ch("y", 92, y=185),
        ]
        text = get_char_unicode_string(chars)
        assert "Trigasmactually" not in text
        assert "actually" in text
        # Hyphen may remain or become space; words must stay separate
        assert "Trigasm" in text


class TestLatinAuthorSpaces:
    """Figure dual authors: TeX gaps ~3.6pt under 0.5× wide-capital threshold."""

    def test_initial_dot_before_surname(self):
        # ``S.`` then gap 3.61 then ``H`` (w≈7.5) — thr0.5=3.74 misses, thr0.35 hits
        # S:78.6–84.1  .:84.1–86.9  H:90.51–98.0  a:98.0–
        chars = [
            _ch("S", 78.6, w=5.5),
            _ch(".", 84.1, w=2.8),
            _ch("H", 90.51, w=7.5),
            _ch("a", 98.0, w=5.0),
        ]
        text = get_char_unicode_string(chars)
        assert text.startswith("S. H")

    def test_and_before_initial(self):
        # ``and`` + gap 3.61 + ``M`` (wide capital thr0.5=4.57)
        # d ends 445.5, M at 449.11
        chars = [
            _ch("a", 430.0, w=5.0),
            _ch("n", 435.0, w=5.5),
            _ch("d", 440.5, w=5.0),
            _ch("M", 449.11, w=9.1),
            _ch(".", 458.2, w=2.8),
        ]
        text = get_char_unicode_string(chars)
        assert "and M" in text

    def test_no_false_split_inside_word(self):
        # Intra-word gaps ~0 must not insert spaces
        chars = [
            _ch("T", 0, w=6),
            _ch("h", 6.2, w=5),
            _ch("e", 11.5, w=5),
            _ch("r", 16.5, w=4),
            _ch("e", 20.5, w=5),
        ]
        assert get_char_unicode_string(chars) == "There"


def _ch(
    u: str,
    x: float,
    y: float = 100.0,
    w: float = 6.0,
    h: float = 12.0,
    *,
    cid: int = 1,
) -> PdfCharacter:
    # pdf_character_id must be set: Layout.is_newline ignores formula-height
    # chars when id is None (formular_height_ignore_char).
    box = Box(x=x, y=y, x2=x + w, y2=y + h)
    return PdfCharacter(
        char_unicode=u,
        box=box,
        visual_bbox=VisualBbox(box=box),
        pdf_style=PdfStyle(font_id="f0", font_size=12.0),
        scale=1.0,
        advance=w,
        pdf_character_id=cid,
    )


class TestGetCharUnicodeStringLineWrap:
    def test_atu_intro_wraps_insert_spaces(self):
        # Line 1 ends at x≈376 "Is", line 2 starts x=56 "it" (y lower).
        # Without fix: "Isit"
        chars = [
            _ch("I", 370, y=646),
            _ch("s", 376, y=646),
            _ch("i", 56, y=630),
            _ch("t", 62, y=630),
        ]
        assert get_char_unicode_string(chars) == "Is it"

    def test_of_grey_wrap(self):
        chars = [
            _ch("o", 340, y=614),
            _ch("f", 346, y=614),
            _ch("G", 56, y=598),
            _ch("r", 62, y=598),
        ]
        assert get_char_unicode_string(chars) == "of Gr"

    def test_question_or_wrap(self):
        # ages? | Or
        chars = [
            _ch("?", 370, y=630, w=5),
            _ch("O", 56, y=614),
            _ch("r", 62, y=614),
        ]
        assert get_char_unicode_string(chars) == "? Or"

    def test_same_line_no_false_space_on_overlap(self):
        # Adjacent letters same baseline, normal tight kerning (distance ~0.5 < 0.5*w)
        chars = [
            _ch("T", 10, y=100, w=6),
            _ch("h", 15.5, y=100, w=6),  # distance 15.5-16 = -0.5 → no gap space
        ]
        # negative distance same line: not newline (same y), no space
        assert get_char_unicode_string(chars) == "Th"

    def test_cjk_wrap_no_space(self):
        chars = [
            _ch("中", 300, y=200, w=12),
            _ch("文", 56, y=180, w=12),
        ]
        assert get_char_unicode_string(chars) == "中文"

    def test_explicit_space_not_doubled(self):
        chars = [
            _ch("s", 370, y=646),
            _ch(" ", 376, y=646, w=3),
            _ch("i", 56, y=630),
        ]
        assert get_char_unicode_string(chars) == "s i"


class TestAddSpaceDummyCharsLineWrap:
    def test_flat_list_inserts_dummy_at_wrap(self):
        chars = [
            _ch("s", 376, y=646),
            _ch("i", 56, y=630),
        ]
        _add_space_dummy_chars_to_list(chars)
        assert [c.char_unicode for c in chars] == ["s", " ", "i"]

    def test_inter_line_compositions(self):
        line1 = PdfLine(pdf_character=[_ch("s", 376, y=646)])
        line2 = PdfLine(pdf_character=[_ch("i", 56, y=630)])
        para = PdfParagraph(
            pdf_paragraph_composition=[
                PdfParagraphComposition(pdf_line=line1),
                PdfParagraphComposition(pdf_line=line2),
            ]
        )
        add_space_dummy_chars(para)
        assert line1.pdf_character[-1].char_unicode == " "
        assert get_paragraph_unicode(para) == "s i"
