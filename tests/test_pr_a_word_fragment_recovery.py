"""PR-A: soft-hyphen / ligature / known-word space-split recovery."""

from __future__ import annotations

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter
from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
from babeldoc.format.pdf.document_il.il_version_1 import VisualBbox
from babeldoc.format.pdf.document_il.utils.layout_helper import (
    get_char_unicode_string,
)
from babeldoc.format.pdf.document_il.utils.text_recovery import (
    recover_latin_word_fragments,
)
from babeldoc.format.pdf.document_il.utils.text_recovery import (
    rejoin_known_split_latin_words,
)
from babeldoc.format.pdf.document_il.utils.text_recovery import (
    rejoin_ligature_space_splits,
)
from babeldoc.format.pdf.document_il.utils.text_recovery import (
    rejoin_soft_hyphen_tight,
)
from babeldoc.format.pdf.document_il.utils.text_recovery import (
    rejoin_soft_hyphens_in_text,
)


def test_di_ff_ligature_space_becomes_different():
    assert rejoin_ligature_space_splits("di ﬀerent") == "different"
    assert rejoin_ligature_space_splits("di fferent") == "different"
    assert recover_latin_word_fragments("Women like di ﬀerent things") == (
        "Women like different things"
    )


def test_cli_toral_known_word():
    assert rejoin_known_split_latin_words("direct cli toral stimulation") == (
        "direct clitoral stimulation"
    )
    assert recover_latin_word_fragments("cli toral") == "clitoral"


def test_soft_hyphen_space_and_tight():
    assert rejoin_soft_hyphens_in_text("di- ﬃcult") == "difficult"
    assert rejoin_soft_hyphen_tight("di-fferent") == "different"
    assert recover_latin_word_fragments("ap- proximation") == "approximation"


def test_refuse_free_word_after_dash():
    assert "actually" in rejoin_soft_hyphens_in_text("Trigasm- actually")
    assert "-" in rejoin_soft_hyphens_in_text("Trigasm- actually")
    # must not become Trigasmatually
    assert "Trigasmatually" not in recover_latin_word_fragments(
        "Trigasm- actually"
    )


def test_refuse_common_two_word_phrase():
    # must not glue function/content pairs that are real bigrams
    assert recover_latin_word_fragments("to the left") == "to the left"
    assert recover_latin_word_fragments("the cult of") == "the cult of"
    assert recover_latin_word_fragments("go away now") == "go away now"


def test_refuse_intentional_hyphenated_compound():
    """figure golden: pseudo- syndrome must not become pseudosyndrome."""
    out = recover_latin_word_fragments("pseudo- syndrome detection")
    assert "pseudosyndrome" not in out.replace(" ", "")
    # hyphen may remain or become single token with hyphen
    assert "syndrome" in out
    assert "pseudo" in out


def test_full_recover_pipeline_oa_fragments():
    s = "proﬁcient partner; di ﬀerent touch; cli toral focus"
    out = recover_latin_word_fragments(s)
    assert "proficient" in out
    assert "different" in out
    assert "clitoral" in out
    assert "ﬀ" not in out and "ﬁ" not in out


def _ch(text: str, x: float) -> PdfCharacter:
    box = Box(x=x, y=100, x2=x + max(4.0, 2.0 * len(text)), y2=112)
    return PdfCharacter(
        pdf_character_id=None,
        char_unicode=text,
        box=box,
        visual_bbox=VisualBbox(box=box),
        pdf_style=PdfStyle(font_id="base", font_size=12.0, graphic_state=None),
        scale=1.0,
        advance=box.x2 - box.x,
        vertical=False,
        xobj_id=None,
    )


def test_get_char_unicode_string_rejoins_cross_run_ligature_gap():
    # Large gap would insert a space between di and ﬀerent
    chars = [
        _ch("d", 10),
        _ch("i", 16),
        _ch("ﬀ", 40),  # gap from 16 → 40
        _ch("e", 48),
        _ch("r", 54),
        _ch("e", 60),
        _ch("n", 66),
        _ch("t", 72),
    ]
    text = get_char_unicode_string(chars)
    assert "different" in text.replace(" ", "") or "different" in text
    assert "ﬀ" not in text


def test_orphan_tail_derived_from_known_words():
    from babeldoc.format.pdf.document_il.utils.text_recovery import (
        _ORPHAN_TAIL_TO_WORD,
        repair_orphan_split_tails,
    )

    # Derived from _KNOWN_SPLIT_WORDS − short prefixes (not a second whitelist)
    assert _ORPHAN_TAIL_TO_WORD.get("fferent") == "different"
    assert _ORPHAN_TAIL_TO_WORD.get("fficult") == "difficult"
    assert repair_orphan_split_tails("ﬀerent every night") == "different every night"
    assert repair_orphan_split_tails("fferent every night") == "different every night"
    # Exceptionally − e → xceptionally (OCR missing first letter, still derived)
    assert repair_orphan_split_tails("xceptionally rare") == "exceptionally rare"
    # Must not rewrite real short / ambiguous tails
    assert repair_orphan_split_tails("low effort") == "low effort"
    assert repair_orphan_split_tails("the ffer is bad") == "the ffer is bad"


def test_ligature_space_only_joins_known_words():
    from babeldoc.format.pdf.document_il.utils.text_recovery import (
        rejoin_ligature_space_splits,
    )

    assert rejoin_ligature_space_splits("di fferent") == "different"
    # Full word left of space must not glue
    assert rejoin_ligature_space_splits("like fferent") == "like fferent"
    # Orphan pass still repairs after known-split path in recover
    assert recover_latin_word_fragments("like ﬀerent things") == (
        "like different things"
    )


def test_decorative_mid_caps_predicate_and_title_path():
    from babeldoc.format.pdf.document_il.utils.text_recovery import (
        has_decorative_mid_caps,
        normalize_decorative_title_case,
    )

    assert has_decorative_mid_caps("anSWer")
    assert has_decorative_mid_caps("Who haS orgaSMS")
    assert not has_decorative_mid_caps("Women")
    assert not has_decorative_mid_caps("THIS")
    assert normalize_decorative_title_case("Who haS orgaSMS?") == "who has orgasms?"
    # Body recover must NOT smash brands (geometry-gated title path only)
    assert "iPhone" in recover_latin_word_fragments("The iPhone works today.")


def test_full_recover_orphan_without_body_mid_cap():
    out = recover_latin_word_fragments(
        "Women like ﬀerent things and di fficult tasks."
    )
    assert "different" in out
    assert "difficult" in out
    assert "ﬀ" not in out
    # Mid-cap body slogans stay for decorative call sites, not recover
    assert "anSWer" in recover_latin_word_fragments("this is the anSWer")


def test_midcap_normalize_surfaces_oa_s6():
    """OA S6: CamelCase splits; mid-caps soup only lowers (no hump split)."""
    from babeldoc.format.pdf.document_il.utils.text_recovery import (
        has_decorative_mid_caps,
        normalize_decorative_title_case,
    )

    assert has_decorative_mid_caps("LearnTheTrigasmBasics")
    assert has_decorative_mid_caps("SLoWcoMfortaBLe")
    assert has_decorative_mid_caps("beanactIonMan")
    assert has_decorative_mid_caps("otWart")
    assert (
        normalize_decorative_title_case("LearnTheTrigasmBasics")
        == "learn the trigasm basics"
    )
    assert normalize_decorative_title_case("SLoWcoMfortaBLe") == "slowcomfortable"
    assert normalize_decorative_title_case("beanactIonMan") == "beanactionman"
    assert normalize_decorative_title_case("otWart") == "otwart"
    tags = normalize_decorative_title_case("dIrect, thruSt, Soft Touch, acRoBaTic")
    assert tags == "direct, thrust, soft touch, acrobatic"


def test_stu_ff_hyphen_ligature_becomes_stuff():
    """OA p12: PDF split ``stu-`` / ``ff`` ligature must reach MT as stuff."""
    from babeldoc.format.pdf.document_il.utils.text_recovery import (
        should_join_hyphen_wrap,
    )

    assert recover_latin_word_fragments("stu-ff") == "stuff"
    assert recover_latin_word_fragments("stu- ff") == "stuff"
    assert recover_latin_word_fragments("stu-\ufb00") == "stuff"
    assert recover_latin_word_fragments("stu\u00adff") == "stuff"
    assert recover_latin_word_fragments("stu ff") == "stuff"
    assert should_join_hyphen_wrap("stu-", "\ufb00")
    assert should_join_hyphen_wrap("stu-", "ff")


def test_stu_ff_across_style_markers():
    """Adjacent same-paragraph spans wrap 〖Bn〗 around the ligature tail."""
    marked = "stu-\u3016B0\u3017\ufb00\u3016/B0\u3017"
    out = recover_latin_word_fragments(marked)
    assert "stuff" in out
    assert "stu" not in out or "stuff" in out
    assert "\ufb00" not in out
    spaced = "stu- \u3016B0\u3017ff\u3016/B0\u3017"
    assert "stuff" in recover_latin_word_fragments(spaced)


def test_g_spot_not_glued():
    from babeldoc.format.pdf.document_il.utils.text_recovery import (
        should_join_hyphen_wrap,
    )

    assert recover_latin_word_fragments("g-spot") == "g-spot"
    assert "gspot" not in recover_latin_word_fragments("the g-spot is")
    assert not should_join_hyphen_wrap("g-", "spot")


def test_get_char_unicode_string_hyphen_wrap_ligature():
    """Geometric wrap: ``stu-`` EOL + ligature ﬀ at left margin → stuff."""
    chars = [
        _ch("s", 50),
        _ch("t", 56),
        _ch("u", 62),
        _ch("-", 68),
        _ch("\ufb00", 50),  # overwritten below with lower y
    ]
    # Fix last char as newline (lower y, x jumps left). Need pdf_character_id
    # so Layout.is_newline does not ignore formula-height-id-less chars.
    lig = chars[-1]
    lig.box.x = 50
    lig.box.x2 = 58
    lig.box.y = 85
    lig.box.y2 = 97
    lig.visual_bbox.box = lig.box
    lig.pdf_character_id = 1
    for c in chars:
        c.pdf_character_id = 1
        c.box.y = 100 if c.char_unicode != "\ufb00" else 85
        c.box.y2 = 112 if c.char_unicode != "\ufb00" else 97
        c.visual_bbox.box = c.box
    text = get_char_unicode_string(chars)
    assert "stuff" in text.replace(" ", "")
    assert "stu" not in text or "stuff" in text
    assert "\ufb00" not in text


def test_get_char_unicode_string_hyphen_wrap_across_markers():
    chars = [
        _ch("s", 50),
        _ch("t", 56),
        _ch("u", 62),
        _ch("-", 68),
        "\u3016B0\u3017",
        _ch("\ufb00", 50),
        "\u3016/B0\u3017",
    ]
    for c in chars:
        if not isinstance(c, PdfCharacter):
            continue
        c.pdf_character_id = 1
        if c.char_unicode == "\ufb00":
            c.box.y = 85
            c.box.y2 = 97
            c.visual_bbox.box = c.box
    text = get_char_unicode_string(chars)
    assert "stuff" in text.replace(" ", "")
    assert "\ufb00" not in text


def test_cli_toris_known_word():
    assert recover_latin_word_fragments("cli toris") == "clitoris"
