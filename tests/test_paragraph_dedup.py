"""Same-sentence duplication guards for paragraph assembly and MT output.

Acceptance V4 (docs/visual-layout-acceptance.md): a column must not contain
the same sentence consecutively >=2 times.  Two defenses:

1. ``callout_merge`` keeps complete blocks (multi-row collapsed lines and
   pull-quote hosts) out of the stacked-line merge, so a pull-quote sentence
   is not merged into the body paragraph unicode a second time (p82 x4 wall).
2. ``ILTranslator.find_consecutive_duplicate_sentences`` warns / skips /
   falls back when a paragraph's MT input or output repeats a sentence.
"""

from __future__ import annotations

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter
from babeldoc.format.pdf.document_il.il_version_1 import PdfLine
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraphComposition
from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
from babeldoc.format.pdf.document_il.il_version_1 import VisualBbox
from babeldoc.format.pdf.document_il.midend.il_translator import ILTranslator
from babeldoc.format.pdf.document_il.utils.callout_merge import (
    merge_stacked_narrow_callout_paragraphs,
)
from babeldoc.format.pdf.document_il.utils.layout_helper import (
    get_char_unicode_string,
    get_paragraph_unicode,
)


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _char(ch: str, x: float, y: float, h: float = 12.0, w: float = 6.0) -> PdfCharacter:
    box = Box(x=x, y=y, x2=x + w, y2=y + h)
    return PdfCharacter(
        char_unicode=ch,
        box=box,
        visual_bbox=VisualBbox(box=box),
        pdf_style=PdfStyle(font_id="b", font_size=12.0, graphic_state=None),
        scale=1.0,
        advance=w,
    )


def _line_para(text: str, *, x: float, y: float, w: float) -> PdfParagraph:
    """Single-row paragraph (one composition line), like the body stack lines."""
    chars = []
    cx = x
    for ch in text:
        chars.append(_char(ch, cx, y))
        cx += 6
    line = PdfLine(box=Box(x=x, y=y, x2=x + w, y2=y + 12), pdf_character=chars)
    return PdfParagraph(
        box=Box(x=x, y=y, x2=x + w, y2=y + 12),
        pdf_paragraph_composition=[PdfParagraphComposition(pdf_line=line)],
        unicode=text,
        layout_label="plain text",
        xobj_id=-1,
    )


def _multi_row_block(texts: list[str], *, x0: float, y_start: float) -> PdfParagraph:
    """Collapsed multi-row block: ONE line whose chars span several y rows.

    Mirrors OA p82: line-splitting cannot find gaps between dense rows, so the
    whole pull-quote ends up as a single composition line painted bottom row
    first (stream order).
    """
    chars: list[PdfCharacter] = []
    y = y_start
    for text in texts:  # bottom row first = stream order
        cx = x0
        for ch in text:
            chars.append(_char(ch, cx, y))
            cx += 6
        y += 15
    ymin = min(c.visual_bbox.box.y for c in chars)
    ymax = max(c.visual_bbox.box.y2 for c in chars)
    xmin = min(c.visual_bbox.box.x for c in chars)
    xmax = max(c.visual_bbox.box.x2 for c in chars)
    line = PdfLine(box=Box(x=xmin, y=ymin, x2=xmax, y2=ymax), pdf_character=chars)
    return PdfParagraph(
        box=Box(x=xmin, y=ymin, x2=xmax, y2=ymax),
        pdf_paragraph_composition=[PdfParagraphComposition(pdf_line=line)],
        layout_label="plain text",
        xobj_id=-1,
    )


# --------------------------------------------------------------------------
# callout_merge guards
# --------------------------------------------------------------------------

def test_multi_row_pullquote_stays_separate_from_body_stack():
    # p82-like: body stack lines + a collapsed multi-row pull-quote below.
    callout = _multi_row_block(
        ["to go around. ", "ensure that there is plenty of lube ",
         "other vaginal stimulation, and ", "of opportunity to warm up with ",
         "Make sure she has had plenty "],
        x0=103.0, y_start=61.0,
    )
    body_lines = [  # stream order bottom-up, 15pt pitch like real p82
        _line_para("Approach her while she is bent over on the bed. ", x=102.0, y=156.0, w=200.0),
        _line_para("go around.", x=102.0, y=171.0, w=54.0),
        _line_para("ensure that there is plenty of lube to", x=102.0, y=186.0, w=190.0),
        _line_para("up with other vaginal stimulation, and", x=102.0, y=201.0, w=200.0),
        _line_para("she has had plenty of opportunity to warm", x=102.0, y=216.0, w=211.0),
    ]
    # stream order: callout first (bottom), then body lines bottom-up
    paras = [callout] + body_lines
    n = merge_stacked_narrow_callout_paragraphs(paras)
    assert n >= 1  # body lines still merge
    # callout stays a separate paragraph (not merged into the body stack)
    assert id(callout) in [id(p) for p in paras]
    # body merged into one paragraph containing the whole body text
    merged = [p for p in paras if p is not callout]
    assert len(merged) == 1
    body_unicode = get_paragraph_unicode(merged[0])
    assert "she has had plenty of opportunity to warm" in body_unicode
    assert "Approach her while she is bent" in body_unicode
    assert "go around." in body_unicode  # synthetic chars lack space glyphs


def test_pullquote_host_stays_separate_when_rows_are_split():
    # Even if the pull-quote rows are separate single-row paragraphs, a host
    # whose text contains another paragraph's text must not merge.
    host = _line_para(
        "Make sure she has had plenty of opportunity to warm up",
        x=103.0, y=61.0, w=250.0,
    )
    body_frag = _line_para(
        "she has had plenty of opportunity to warm up",
        x=102.0, y=156.0, w=220.0,
    )
    paras = [host, body_frag]
    n = merge_stacked_narrow_callout_paragraphs(paras)
    assert n == 0
    assert len(paras) == 2


def test_triangle_tips_still_merge():
    # OA TAKING CHARGE triangle rows are unique single-row lines — must still
    # merge into one MT unit (existing behavior).
    paras = [
        _line_para("the program.", x=450, y=100, w=80),
        _line_para("plans and stick", x=420, y=120, w=110),
        _line_para("In order to work", x=320, y=200, w=180),
    ]
    n = merge_stacked_narrow_callout_paragraphs(paras)
    assert n >= 1
    assert len(paras) < 3
    assert paras[0].box.x2 - paras[0].box.x > 100


# --------------------------------------------------------------------------
# V4 duplicate-sentence gate
# --------------------------------------------------------------------------

def test_detect_consecutive_exact_duplicate():
    text = (
        "Make sure she has had plenty of opportunity to warm up with other "
        "vaginal stimulation, and ensure that there is plenty of lube to go "
        "around. Make sure she has had plenty of opportunity to warm up with "
        "other vaginal stimulation, and ensure that there is plenty of lube "
        "to go around."
    )
    dups = ILTranslator.find_consecutive_duplicate_sentences(text)
    assert any(kind == "exact" for _, kind in dups)


def test_detect_consecutive_cjk_duplicate_without_spaces():
    # CJK sentences run together without spaces after 。: the splitter must
    # still find the back-to-back repeat (你好。你好。).
    text = "她说要先做好充分的准备。她说要先做好充分的准备。然后我们继续。"
    dups = ILTranslator.find_consecutive_duplicate_sentences(text)
    assert any(kind == "exact" for _, kind in dups)


def test_detect_near_duplicate_fragment():
    # Pull-quote fragment glued to its host: "we go around." followed by the
    # same opening in the next sentence ("we go around the block...").
    text = (
        "Spread her legs as much as you need to get between them. we go "
        "around. we go around the block and come back to the start."
    )
    dups = ILTranslator.find_consecutive_duplicate_sentences(text)
    assert any(kind == "near" for _, kind in dups)


def test_no_false_positive_on_normal_body():
    text = (
        "she has had plenty of opportunity to warm up with other vaginal "
        "stimulation, and ensure that there is plenty of lube to go around. "
        "Approach her while she is bent over on the bed, butt up in the air "
        "and face down on the mattress. Spread her legs as much as you need "
        "to get between them."
    )
    assert ILTranslator.find_consecutive_duplicate_sentences(text) == []


def test_fix_untranslated_chapter_markers():
    # p82 "Chapter9直接卷曲" class residue -> 第九章 直接卷曲 style output.
    assert ILTranslator.fix_untranslated_chapter_markers(
        "Chapter9直接卷曲"
    ) == "第九章直接卷曲"
    assert ILTranslator.fix_untranslated_chapter_markers(
        "Chapter 9 the dIrect curL 直接卷曲"
    ) == "第九章 the dIrect curL 直接卷曲"
    # Already-translated marker untouched.
    assert ILTranslator.fix_untranslated_chapter_markers("第九章 直接卷曲") == "第九章 直接卷曲"
    # Rich-text bold marker splits "Chapter " from "9" in the MT input
    # (p82 running header); the marker is dropped and the marker normalized.
    assert ILTranslator.fix_untranslated_chapter_markers(
        "〖B0〗Chapter 〖/B0〗9 the dIrect curL"
    ) == "第九章 the dIrect curL"
    # A complete style span must survive the chapter-marker rewrite so the
    # red chapter number remains red in the dual PDF.
    assert ILTranslator.fix_untranslated_chapter_markers(
        "〖B0〗Chapter 10〖/B0〗 the Indirect thrust"
    ) == "〖B0〗第十章〖/B0〗 the Indirect thrust"
    # Chinese-numeral conversion for teens / tens.
    assert ILTranslator._cn_numeral(3) == "三"
    assert ILTranslator._cn_numeral(9) == "九"
    assert ILTranslator._cn_numeral(19) == "十九"
    assert ILTranslator._cn_numeral(82) == "八十二"
    assert ILTranslator._cn_numeral(120) == "一百二十"
    # Non-marker text untouched.
    assert ILTranslator.fix_untranslated_chapter_markers("这是正文。") == "这是正文。"


def test_no_false_positive_on_short_echo():
    # "I love you all. I love you too." is legitimate dialogue, not a merge bug.
    text = "I love you all. I love you too. That is what I said."
    dups = ILTranslator.find_consecutive_duplicate_sentences(text)
    assert all(kind != "exact" for _, kind in dups)


# --------------------------------------------------------------------------
# reading-order recovery for drifted glyph rows
# --------------------------------------------------------------------------

def test_char_unicode_reading_order_with_drifted_rows():
    # OA p82 callout glyphs paint at ~3pt drifted baselines; the reading-order
    # recovery must keep each row intact (top-to-bottom, left-to-right).
    rows = [  # bottom row first = stream order (OA p82 pull-quote)
        "to go around. ",
        "ensure that there is plenty of lube ",
        "other vaginal stimulation, and ",
        "of opportunity to warm up with ",
        "Make sure she has had plenty ",
    ]
    chars: list[PdfCharacter] = []
    y = 61.0
    for text in rows:
        cx = 103.0
        for ch in text:
            # deterministic per-char baseline drift (0..2.9pt), like OA p82
            drift = (len(chars) % 30) / 10.0
            chars.append(_char(ch, cx, y + drift))
            cx += 6
        y += 15
    out = get_char_unicode_string(chars, para_width=156.0)
    assert "Make sure she has had plenty" in out
    assert "other vaginal stimulation, and" in out
    assert "to go around." in out
    assert out.index("Make sure") < out.index("to go around.")


def test_fix_untranslated_chapter_markers_lowercase_b_span():
    """OA running titles: 〖b0〗chapter〖/b0〗8 → 第八章, not Latin b08.

    Mid-caps lowercasing used to smash 〖B0〗 into 〖b0〗; DeepLX then
    concatenated leftover b0 with the chapter index (p35 b05 / p59 b08 /
    p120 b012).  Both the pre-MT split span and the post-MT residue must
    rewrite to 第N章.
    """
    fix = ILTranslator.fix_untranslated_chapter_markers
    # Real OA MT inputs (logged): lowercase b span around "chapter", number outside.
    assert fix("〖b0〗chapter〖/b0〗8 the direct thrust") == "第八章 the direct thrust"
    assert (
        fix("〖b0〗chapter 〖/b0〗5 sexual anatomy") == "第五章 sexual anatomy"
    )
    assert (
        fix("〖b0〗chapter〖/b0〗12 make your own moves!")
        == "第十二章 make your own moves!"
    )
    # Literal 〖b08〗 leftover (span-id fused with chapter 8) next to 章.
    assert fix("章〖b08〗直接推送") == "第八章直接推送"
    assert fix("〖b08〗 the direct thrust") == "第八章 the direct thrust"
    # Real OA MT outputs.
    assert fix("章b08 直接推送") == "第八章 直接推送"
    assert fix("章节b05 性解剖学") == "第五章 性解剖学"
    assert fix("章b012 创造你自己的动作") == "第十二章 创造你自己的动作"
    assert fix("章 b07 间接") == "第七章 间接"
    # Already-normalized 第N章 is stable.
    assert fix("第八章 直接推送") == "第八章 直接推送"
