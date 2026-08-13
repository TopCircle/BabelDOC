"""Side-callout MT skip (pull-quote duplicate + ultra-narrow strip)."""

from __future__ import annotations

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import Page
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
from babeldoc.format.pdf.document_il.midend.il_translator import ILTranslator
from babeldoc.format.pdf.document_il.utils.side_callout_skip import find_pullquote_host
from babeldoc.format.pdf.document_il.utils.side_callout_skip import (
    is_near_full_pullquote,
)
from babeldoc.format.pdf.document_il.utils.side_callout_skip import (
    is_pullquote_duplicate_of_body,
)
from babeldoc.format.pdf.document_il.utils.side_callout_skip import (
    is_ultra_narrow_side_callout,
)
from babeldoc.format.pdf.document_il.utils.side_callout_skip import normalize_for_dup
from babeldoc.format.pdf.document_il.utils.side_callout_skip import (
    should_skip_side_callout_mt,
)
from babeldoc.format.pdf.document_il.utils.side_callout_skip import (
    side_callout_debug_extra,
)


def _para(
    text: str,
    *,
    x: float,
    x2: float,
    y: float = 100.0,
    y2: float | None = None,
    layout_label: str | None = None,
) -> PdfParagraph:
    top = y2 if y2 is not None else y + 40
    p = PdfParagraph(
        box=Box(x=x, y=y, x2=x2, y2=top),
        pdf_style=PdfStyle(font_id="base", font_size=12.0, graphic_state=None),
        pdf_paragraph_composition=[],
        unicode=text,
    )
    if layout_label is not None:
        p.layout_label = layout_label
    return p


def _page(*paras: PdfParagraph) -> Page:
    p = Page(
        page_number=0,
        mediabox=Box(x=0, y=0, x2=612, y2=792),
        cropbox=Box(x=0, y=0, x2=612, y2=792),
    )
    p.pdf_paragraph = list(paras)
    return p


QUOTE = (
    "Since her orgasm is essentially an intense contraction of her PC and "
    "pelvic floor muscles, strengthening them increases blood flow to the "
    "area and enables her to experience a deeper pleasure sensation and a "
    "repeated series of pulses"
)


def test_normalize_strips_punct():
    assert normalize_for_dup("Hello, World!") == "helloworld"


def test_side_callout_contained_in_body_is_duplicate():
    body = _para(
        f'"{QUOTE}," says Laura Berman, author of The Passion Prescription.',
        x=102,
        x2=360,
    )
    callout = _para(QUOTE, x=360, x2=560)  # right-side narrow band
    page = _page(body, callout)
    assert is_pullquote_duplicate_of_body(callout, page) is True
    assert is_pullquote_duplicate_of_body(body, page) is False
    assert find_pullquote_host(callout, page) is body
    # Host = quote + extra sentence → excerpt, not near-full; MT once.
    assert is_near_full_pullquote(callout, body) is False
    assert should_skip_side_callout_mt(callout, page) is False


def test_unique_body_not_duplicate():
    a = _para("Unique paragraph about Kegels and exercise.", x=102, x2=500)
    b = _para("Something completely different about foreplay.", x=102, x2=500)
    page = _page(a, b)
    assert is_pullquote_duplicate_of_body(a, page) is False


def test_ultra_narrow_tall_callout_skipped():
    """OA p8 red strip ~80×120 at x≈429 on letter — keep EN, do not tower ZH."""
    callout = _para(
        "The best way for you to learn the clit-stimulating techniques "
        "that work best for her is going to be by watching her pleasure herself!",
        x=429,
        x2=509,
        y=361,
        y2=481,
        layout_label="plain text",
    )
    page = _page(callout)
    assert is_ultra_narrow_side_callout(callout, page) is True
    # Default mode is expand → do not skip; keep_en still skips
    assert should_skip_side_callout_mt(callout, page) is False
    assert should_skip_side_callout_mt(callout, page, mode="keep_en") is True


def test_ultra_narrow_expand_mode_does_not_skip():
    """PR-D: expand mode sends ultra-narrow callout to MT."""
    from babeldoc.format.pdf.document_il.utils.side_callout_skip import (
        normalize_narrow_callout_mode,
    )

    callout = _para(
        "The best way for you to learn the clit-stimulating techniques "
        "that work best for her is going to be by watching her pleasure herself!",
        x=429,
        x2=509,
        y=361,
        y2=481,
        layout_label="plain text",
    )
    page = _page(callout)
    assert is_ultra_narrow_side_callout(callout, page) is True
    assert should_skip_side_callout_mt(callout, page, mode="expand") is False
    assert (
        should_skip_side_callout_mt(callout, page, mode="translate_body_column")
        is False
    )
    assert normalize_narrow_callout_mode("EXPAND") == "expand"
    assert normalize_narrow_callout_mode("bogus") == "expand"
    assert normalize_narrow_callout_mode("keep_en") == "keep_en"


def test_pullquote_always_skips_even_in_expand_mode():
    quote = (
        "Since her orgasm is essentially an intense contraction of her PC and "
        "pelvic floor muscles, strengthening them increases blood flow to the "
        "area and enables her to experience a deeper pleasure sensation and a "
        "repeated series of pulses"
    )
    # Short attribution → near-full (ratio >= 0.85); skip in every mode.
    body = _para(
        f'"{quote}," says Laura Berman.',
        x=102,
        x2=360,
    )
    callout = _para(quote, x=360, x2=560)
    page = _page(body, callout)
    assert is_near_full_pullquote(callout, body) is True
    assert should_skip_side_callout_mt(callout, page, mode="expand") is True
    assert should_skip_side_callout_mt(callout, page, mode="keep_en") is True


def test_left_column_body_not_ultra_narrow_callout():
    """OA p7 left column ~105pt at x≈102 — body beside photo, still translate."""
    body = _para(
        "Women like different things, the same as some men enjoy hard touch "
        "and some soft, some like a little anal play,",
        x=102,
        x2=207,
        y=78,
        y2=168,
        layout_label="plain text",
    )
    page = _page(body)
    assert is_ultra_narrow_side_callout(body, page) is False
    assert should_skip_side_callout_mt(body, page) is False


def test_right_half_narrow_width_alone_still_needs_height():
    """width_ratio < 0.18 on right half but short height is not a tall strip."""
    short = _para(
        "Short callout text that is long enough in chars but not tall enough.",
        x=430,
        x2=500,
        y=400,
        y2=420,  # h=20, w=70 → h/w < 0.9
        layout_label="plain text",
    )
    page = _page(short)
    assert is_ultra_narrow_side_callout(short, page) is False


def test_title_not_ultra_narrow_even_if_narrow_box():
    title = _para(
        "WHO HAS ORGASMS?",
        x=430,
        x2=510,
        y=300,
        y2=420,
        layout_label="title",
    )
    page = _page(title)
    assert is_ultra_narrow_side_callout(title, page) is False


def test_side_callout_debug_extra_is_bounded_geometry():
    """Helper exposes ratios/branch only — no text payload."""
    right = _para(QUOTE, x=360, x2=560)
    left = _para(QUOTE, x=0, x2=80)
    page = _page(right, left)
    right_extra = side_callout_debug_extra(right, page)
    left_extra = side_callout_debug_extra(left, page)
    assert right_extra is not None
    assert left_extra is not None
    assert set(right_extra) == {
        "left_ratio",
        "right_ratio",
        "width_ratio",
        "matched_branch",
    }
    assert right_extra["matched_branch"] == "right_margin_indent"
    assert left_extra["matched_branch"] == "left_margin_gutter"
    assert isinstance(right_extra["left_ratio"], float)
    assert "text" not in right_extra
    assert "unicode" not in right_extra
    assert side_callout_debug_extra(right, None) is None


def test_compat_reexport_from_pullquote_dedupe():
    """Older imports via pullquote_dedupe still resolve."""
    from babeldoc.format.pdf.document_il.utils import pullquote_dedupe as pq

    callout = _para(
        "The best way for you to learn the clit-stimulating techniques "
        "that work best for her is going to be by watching her pleasure herself!",
        x=429,
        x2=509,
        y=361,
        y2=481,
    )
    page = _page(callout)
    assert pq.is_ultra_narrow_side_callout(callout, page) is True
    # default expand → translate; keep_en still skips
    assert pq.should_skip_side_callout_mt(callout, page) is False
    assert pq.should_skip_side_callout_mt(callout, page, mode="keep_en") is True


def test_excerpt_pullquote_is_not_near_full_and_does_not_skip():
    """Host = quote + extra sentence: substring but ratio < 0.85 → MT once."""
    extra = (
        " This is an extra sentence about Kegels that makes the host "
        "substantially longer than the pull-quote itself."
    )
    body = _para(QUOTE + extra, x=102, x2=360)
    callout = _para(QUOTE, x=360, x2=560)
    page = _page(body, callout)
    assert is_pullquote_duplicate_of_body(callout, page) is True
    assert find_pullquote_host(callout, page) is body
    assert is_near_full_pullquote(QUOTE, QUOTE + extra) is False
    assert is_near_full_pullquote(callout, body) is False
    assert should_skip_side_callout_mt(callout, page) is False
    assert should_skip_side_callout_mt(callout, page, mode="expand") is False
    assert should_skip_side_callout_mt(callout, page, mode="keep_en") is False


def test_near_full_pullquote_skips_mt():
    """Quote ≈ host (ratio >= 0.85) → skip MT; copy host ZH later."""
    body = _para(f'"{QUOTE}," says Laura Berman.', x=102, x2=360)
    callout = _para(QUOTE, x=360, x2=560)
    page = _page(body, callout)
    assert is_near_full_pullquote(callout, body) is True
    assert is_near_full_pullquote(QUOTE, f'"{QUOTE}," says Laura Berman.') is True
    assert should_skip_side_callout_mt(callout, page) is True


def test_near_full_via_stripped_quotes_whitespace():
    assert is_near_full_pullquote(f'  "{QUOTE}"  ', QUOTE) is True


def test_apply_zh_to_quote_is_shorter_than_long_host_zh():
    """Excerpt never uses _apply; applied ZH must not be the full host."""
    quote = _para(QUOTE, x=360, x2=560)
    excerpt_zh = "加强它们会增加该区域的血流并带来更深的快感。"
    host_zh = excerpt_zh + "劳拉·伯曼，《激情处方》作者说。"
    ILTranslator._apply_zh_to_quote(quote, excerpt_zh)
    assert quote.unicode == excerpt_zh
    assert len(quote.unicode) < len(host_zh)
    comps = quote.pdf_paragraph_composition
    assert len(comps) == 1
    ssu = comps[0].pdf_same_style_unicode_characters
    assert ssu is not None
    assert ssu.unicode == excerpt_zh
    assert any("\u4e00" <= ch <= "\u9fff" for ch in ssu.unicode)
    assert ssu.pdf_style is quote.pdf_style


def test_apply_stashed_near_full_copies_host_zh_when_cjk():
    quote = _para(QUOTE, x=360, x2=560)
    host = _para(f'"{QUOTE}," says Laura Berman.', x=102, x2=360)
    host_zh = "由于她的高潮本质上是盆底肌的强烈收缩，劳拉·伯曼说。"
    host.unicode = host_zh
    page = _page(host, quote)
    tr = object.__new__(ILTranslator)
    tr.docs = type("Docs", (), {"page": [page]})()
    tr._near_full_pullquotes = {
        id(quote): {
            "host_obj_id": id(host),
            "quote_debug_id": getattr(quote, "debug_id", None),
            "host_debug_id": getattr(host, "debug_id", None),
            "kind": "near_full",
        }
    }
    tr._apply_stashed_near_full_pullquotes()
    assert quote.unicode == host_zh
    ssu = quote.pdf_paragraph_composition[0].pdf_same_style_unicode_characters
    assert ssu.unicode == host_zh
    assert ssu.pdf_style is quote.pdf_style
    assert tr._near_full_pullquotes == {}


def test_apply_stashed_near_full_leaves_en_when_host_has_no_cjk():
    quote = _para(QUOTE, x=360, x2=560)
    host = _para(f'"{QUOTE}," says Laura Berman.', x=102, x2=360)
    page = _page(host, quote)
    tr = object.__new__(ILTranslator)
    tr.docs = type("Docs", (), {"page": [page]})()
    tr._near_full_pullquotes = {
        id(quote): {
            "host_obj_id": id(host),
            "quote_debug_id": None,
            "host_debug_id": None,
            "kind": "near_full",
        }
    }
    tr._apply_stashed_near_full_pullquotes()
    assert quote.unicode == QUOTE
    assert quote.pdf_paragraph_composition == []
