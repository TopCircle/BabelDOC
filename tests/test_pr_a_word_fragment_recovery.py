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