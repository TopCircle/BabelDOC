"""Recover missing word boundaries and TeX soft hyphens from PDF geometry.

PDF often omits explicit space glyphs; TeX author lines use ~3.6pt gaps that
fall just under the classic 0.5× width threshold (``S.Hazra`` / ``andM.H.``).
Line wraps also leave soft hyphens (``ap-`` + ``proximation``).

Latin presentation ligatures (``ﬁ``/``ﬂ``/``ﬀ``/``ﬃ``/``ﬄ``) sometimes
survive as single codepoints and break DeepLX / residual EN scans; expand
them to ASCII sequences before MT.

Used by ``layout_helper.get_char_unicode_string`` and dummy-space insertion.
"""

from __future__ import annotations

import regex

from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter

# Latin presentation forms (FB00–FB04). NFKC usually expands these; keep an
# explicit map so partial/broken pipelines and char-level paths still recover.
_LATIN_LIGATURES = str.maketrans(
    {
        "\ufb00": "ff",  # ﬀ
        "\ufb01": "fi",  # ﬁ
        "\ufb02": "fl",  # ﬂ
        "\ufb03": "ffi",  # ﬃ
        "\ufb04": "ffl",  # ﬄ
        "\ufb05": "ft",  # long s + t (rare)
        "\ufb06": "st",  # st
    }
)


def expand_latin_ligatures(text: str | None) -> str:
    """Expand Latin presentation ligatures to ASCII letter sequences.

    Safe on ``None``/empty. Idempotent for already-expanded text.
    """
    if not text:
        return "" if text is None else text
    return text.translate(_LATIN_LIGATURES)

# Default: gap > 50% of the *wider* glyph (avoids "There"→"The re").
SPACE_WIDTH_RATIO = 0.5
# TeX author lines (figure dual): inter-word gaps ~3.6pt sit just under
# 0.5× wide capitals (H/D/M thr≈3.7–5.1) → ``S.Hazra`` / ``andM.H.Devoret``.
# Relaxed Latin-only path uses 35% + absolute floor without reopening CJK glue.
LATIN_WORD_GAP_RATIO = 0.35
LATIN_WORD_MIN_GAP_PT = 2.0

# Candidate soft-hyphen after style regroup: ``ap- proximation``.
# Captures the full continuation token (mixed-case allowed) so we can reject
# free English words. Decorative TOC fonts often yield ``acTuaLLy``; matching
# only ``[a-z]+`` would capture ``ac`` (len<4), rejoin to ``TrigasMacTuaLLy``.
SOFT_HYPHEN_CANDIDATE_RE = regex.compile(
    r"(?<=[A-Za-z])-\s+([A-Za-z][A-Za-z']*)"
)

# High-frequency free-standing English words (len>=4). Soft-hyphen
# continuations are almost never these (``proximation``, ``ence``, ``tion``
# stems are low-freq / non-words). Used to block false rejoins on intentional
# dashes: ``Trigasm- actually``, ``well- known``-style prose.
# Short suffixes that also appear as words (ing/ed/ly/er) are omitted so
# ``walk- ing`` still rejoins.
_HIGH_FREQ_EN_WORDS = frozenset(
    """
    about above across actual actually after again against almost already also
    always among amount another answer anyone anything around because become
    before begin being below between both bring build business call called came
    cannot cause center change child children city clear close come comes coming
    common company complete control could country course cover create current
    different does doing during each early earth education effect either else
    enough entire especially even ever every everyone everything example
    experience face fact family father feel field figure final find first five
    follow food force form found four free from full further future game general
    give given going good government great group grow hand hard have having head
    health hear help here high himself history hold home however human idea
    important include including increase information instead interest into issue
    itself just keep kind know known large last later lead learn least leave left
    less letter level life light like likely line list little live local long
    look looking made make makes making many mark market material matter maybe
    mean means media might mind minute money month more morning most mother
    move much music must name nation national need never next night nothing
    number offer office often once only open order other others over own page
    paper part particular party past people percent period person personal
    place plan play please point political possible power present press pretty
    private probably problem process produce product program provide public
    rather read ready real really reason recent remember report research result
    return right room rule same school second section seem seen send sense
    service several shall share she should show side since small social some
    someone something sometimes soon sound south space special stand start state
    still stop story street strong student study such system take taken taking
    talk teacher team tell term test than that their them themselves then there
    these they thing things think third this those though thought three through
    thus time today together told too took toward town trade turn under
    understand until upon used using usually value various very view want water
    week well went were what when where whether which while white whole whose
    will with within without woman women word work working world would write
    year years young your yourself
    able about above accept according account across action activity actually
    address allow almost alone along already also although always among amount
    analysis another answer anyone anything appear apply area areas around ask
    available away based become becomes been before begin beginning behind being
    believe best better between beyond big bill black board body book both
    break bring brought build building built business call came campaign cancer
    candidate capital car care case cases cause center central century certain
    certainly challenge chance change changes character charge check child
    children choice choose church city class clear clearly close club coach
    cold college color come comes coming comment common community company
    compare complete completely computer concern condition conference congress
    consider continue control cost could council country couple course court
    cover create crime cultural culture current currently cut dark data daughter
    day days dead deal death debate decade decide decision deep defense degree
    democrat democratic describe design despite detail determine develop
    development die difference different difficult dinner direction director
    discover discuss discussion disease doctor dog door down draw dream drive
    drop drug during each early east easy economic economy edge education
    effect effort eight either election else employee end energy enough enter
    entire environment especially establish even evening event ever every
    everybody everyone everything evidence exactly example executive exist
    expect experience expert explain eye eyes face fact factor fail fall family
    far farm fast father fear federal feel feeling few field fight figure fill
    film final finally financial find fine finger finish fire firm first fish
    five floor fly focus follow food foot force foreign forget form former
    forward four free friend from front full fund future game garden gas
    general generation get girl give glass go goes going gone good government
    great green ground group grow growth guess gun guy hair half hand hang
    happen happy hard have he head health hear heart heat heavy help her here
    herself high him himself his history hit hold home hope hospital hot hotel
    hour house how however huge human hundred husband idea identify if image
    imagine impact important improve in include including increase indeed
    indicate individual industry information inside instead institution
    interest interesting international interview into involve issue it item its
    itself job join just keep key kid kill kind kitchen know knowledge land
    language large last late later laugh law lawyer lay lead leader learn least
    leave left leg legal less let letter level lie life light like likely line
    list listen little live local long look looking lose loss lot love low
    machine magazine main maintain major make man manage management manager
    many market marriage material matter may maybe me mean measures media
    medical meet meeting member memory mention message method middle might
    military million mind minute miss mission model modern moment money month
    more morning most mother mouth move movement movie much music must my
    myself name nation national natural nature near nearly necessary need
    network never new news next nice night no none nor north not note nothing
    notice now number occur of off offer office officer often oh oil ok old on
    once one only onto open operation opportunity or order organization other
    others our out outside over own page pain paper parent part particular
    particularly partner party pass past patient pattern pay peace people per
    perform performance perhaps period person personal phone physical pick
    picture piece place plan plant play player please plus point police policy
    political politics poor popular population position positive possible
    potential power practice prepare present president pressure pretty prevent
    price private probably problem process produce product production
    professional professor program project property protect prove provide
    public pull purpose push put quality question quickly quite race radio
    raise range rate rather reach read ready real reality realize really reason
    receive recent recently recognize record red reduce reflect region relate
    relationship religious remain remember remove report represent republican
    require research resource respond response responsibility rest result
    return reveal rich right rise risk road rock role room rule run safe same
    save say scene school science scientist score sea season seat second
    section security see seek seem seem seen sell send senior sense series
    serious serve service set seven several sex sexual shake share she shoot
    short shot should shoulder show side sign significant similar simple simply
    since sing single sister sit site situation six size skill skin small smile
    so social society soldier some someone something sometimes son song soon
    sort sound source south southern space speak special specific speech spend
    sport spring staff stage stand standard star start state statement station
    stay step still stock stop store story strategy street strong structure
    student study stuff style subject success successful such suddenly suffer
    suggest summer support sure surface system table take talk task tax teach
    teacher team technology television tell ten tend term test than thank that
    the their them themselves then theory there these they thing things think
    third this those though thought thousand threat three through throughout
    throw thus time to today together too top total tough toward town trade
    traditional training travel treat treatment tree trial trip trouble true
    truth try turn TV two type under understand unit until up upon us use used
    useful user using usually value various very victim view violence visit
    voice vote wait walk wall want war watch water way we weapon wear week
    weight well west western what whatever when where whether which while white
    who whole whom whose why wide wife will win wind window wish with within
    without woman women wonder word work worker working world worry would
    write writer wrong yard yeah year years yes yet you young your yourself
    """.split()
)


def is_ascii_alpha(ch: str | None) -> bool:
    return bool(ch) and ch[0].isalpha() and ord(ch[0]) < 128


def is_standalone_en_word(token: str | None) -> bool:
    """True if *token* is a free-standing high-frequency English word.

    Used to refuse soft-hyphen rejoin when the right-hand side is a real word
    (``actually``) rather than a TeX line-wrap fragment (``proximation``).
    Only tokens of length ≥ 4 are checked so short soft-hyphen tails
    (``ing`` / ``ed`` / ``ly``) still rejoin.
    """
    if not token:
        return False
    t = token.lower().strip("'")
    if len(t) < 4 or not t.isalpha():
        return False
    return t in _HIGH_FREQ_EN_WORDS


def gap_is_word_boundary(
    prev: PdfCharacter,
    next_ch: PdfCharacter,
    distance: float,
) -> bool:
    """Whether ``distance`` between two chars should insert a word space.

    Standard rule: ``distance > 0.5 * max(widths)``.
    Latin token rule (figure dual authors): after ``.``/``,`` before a letter,
    or lower→Upper (``and M``), accept slightly tighter TeX gaps (≥2pt and
    ``> 0.35 * max width``).
    """
    if distance <= 0:
        return False
    if not prev.box or not next_ch.box:
        return False
    curr_w = prev.box.x2 - prev.box.x
    next_w = next_ch.box.x2 - next_ch.box.x
    max_w = max(curr_w, next_w)
    if max_w <= 0:
        return False
    if distance > max_w * SPACE_WIDTH_RATIO:
        return True
    if distance < LATIN_WORD_MIN_GAP_PT or distance <= max_w * LATIN_WORD_GAP_RATIO:
        return False
    prev_u = prev.char_unicode or ""
    next_u = next_ch.char_unicode or ""
    if not next_u:
        return False
    # ``S. Hazra`` / ``P. D.`` / ``M. H.``
    if prev_u == "." and next_u[0].isupper() and ord(next_u[0]) < 128:
        return True
    # ``and M`` (lowercase then capital)
    if (
        prev_u
        and prev_u[-1].islower()
        and ord(prev_u[-1]) < 128
        and next_u[0].isupper()
        and ord(next_u[0]) < 128
    ):
        return True
    # ``Hazra,1`` usually no space before digit; ``1, ∗`` thin — skip comma+digit
    # ``Frunzio,1 and`` — comma then space glyph usually present
    if prev_u == "," and is_ascii_alpha(next_u):
        return True
    return False


# Continuations that look like soft-hyphen tails (not full words).
_SOFT_HYPHEN_SUFFIXES = (
    "tion",
    "sion",
    "ness",
    "ment",
    "able",
    "ible",
    "ence",
    "ance",
    "ally",
    "ially",
    "ing",
    "ers",
    "ies",
    "ous",
    "ive",
    "ized",
    "ised",
    "ular",  # particular → …
    "ent",
)
_SOFT_HYPHEN_DOUBLE_START = frozenset(
    {
        "ff",
        "fi",
        "fl",
        "ss",
        "ll",
        "tt",
        "pp",
        "rr",
        "nn",
        "mm",
        "cc",
        "dd",
        "gg",
    }
)


def should_soft_rejoin(continuation: str | None) -> bool:
    """Whether ``word- cont`` is a TeX soft hyphen that should glue.

    Rejoin tails like ``proximation`` / ``fferent`` / ``ence``.  Refuse:
      * free English words (``actually``)
      * decorative mixed case (``acTuaLLy``)
      * full words after intentional hyphens (``pseudo- syndrome`` → keep)
    """
    if not continuation:
        return False
    # Pure lowercase only — mixed/Title/UPPER stays as intentional dash.
    if not continuation.islower():
        return False
    if is_standalone_en_word(continuation):
        return False
    # Ligature-style / double-consonant line wraps (di- fferent)
    if len(continuation) >= 2 and continuation[:2] in _SOFT_HYPHEN_DOUBLE_START:
        return True
    if any(continuation.endswith(s) for s in _SOFT_HYPHEN_SUFFIXES):
        return True
    # Short pure tails (ing/ed already partially covered); keep len 2–5 open
    if 2 <= len(continuation) <= 5:
        return True
    # Longer tokens without suffix shape are full words (syndrome, detection)
    return False


def is_soft_hyphen_line_wrap(
    prev: PdfCharacter,
    next_ch: PdfCharacter,
    next_word: str | None = None,
) -> bool:
    """TeX soft hyphen at line wrap: ``ap-`` + ``proximation`` → join without space.

    Geometry: prev is ``-`` and next starts a Latin letter run.  Semantics
    deferred to :func:`should_soft_rejoin` on the peeked continuation token.
    """
    prev_u = prev.char_unicode or ""
    next_u = next_ch.char_unicode or ""
    if prev_u not in "-‐‑" or not next_u or not next_u[0].isalpha():
        return False
    token = next_word if next_word is not None else next_u
    m = regex.match(r"[A-Za-z']+", token or "")
    cont = m.group(0) if m else (token or "")
    return should_soft_rejoin(cont)


def rejoin_soft_hyphens_in_text(text: str) -> str:
    """Collapse ``ap- proximation`` style soft hyphens left after style regroup.

    Keeps intentional dashes before free English words / decorative casing:
    ``Trigasm- actually`` / ``TrigasM- acTuaLLy`` must not glue.

    Ligatures in the continuation (``di- ﬃcult``) are expanded first so the
    free-word blocklist and rejoin logic see ``fficult`` not a private-use char.
    """
    if not text:
        return text
    text = expand_latin_ligatures(text)
    if "-" not in text:
        return text

    def _sub(m: regex.Match[str]) -> str:
        cont = expand_latin_ligatures(m.group(1))
        if should_soft_rejoin(cont):
            return cont  # drop "- " and glue
        return m.group(0)  # keep hyphen + space

    return SOFT_HYPHEN_CANDIDATE_RE.sub(_sub, text)


# After ligature expand: ``di fferent`` / ``di ﬀerent`` (false word gap).
# Only short left stems (1–3 letters): ``di``/``pro`` — not full words
# (``like fferent`` must stay two tokens until orphan repair).
_LIGATURE_SPACE_CONT_RE = regex.compile(
    r"\b([A-Za-z]{1,3})\s+((?:ff|fi|fl|ffi|ffl)[a-z]*)",
    regex.IGNORECASE,
)

# Hyphen without space: ``di-fferent`` / ``ap-proximation``.
_SOFT_HYPHEN_TIGHT_RE = regex.compile(
    r"(?<=[A-Za-z])-([a-z]{2,})"
)

# Full words often split by PDF gaps / soft hyphens in design ebooks (OA dual).
# Only join when prefix+suffix exactly matches — avoids ``the cult`` / ``to the``.
_KNOWN_SPLIT_WORDS = frozenset(
    {
        "different",
        "difficult",
        "clitoral",
        "proficient",
        "sufficient",
        "efficient",
        "efficiently",
        "effectively",
        "exceptionally",
        "approximately",
        "discrimination",
        "stimulation",
        "measurement",
        "characteristics",
        "particularly",
        "immediately",
        "successfully",
        "overwhelmingly",
        "understanding",
        "selfunderstanding",  # after hyphen strip variants
    }
)

def rejoin_ligature_space_splits(text: str) -> str:
    """Glue ``di fferent`` / ``di ﬀerent`` after ligature expand (no hyphen)."""
    if not text:
        return text
    text = expand_latin_ligatures(text)

    def _sub(m: regex.Match[str]) -> str:
        # group1 short stem + group2 ff… tail
        return m.group(1) + m.group(2)

    return _LIGATURE_SPACE_CONT_RE.sub(_sub, text)


def rejoin_soft_hyphen_tight(text: str) -> str:
    """Glue ``di-fferent`` when continuation passes :func:`should_soft_rejoin`."""
    if not text or "-" not in text:
        return text

    def _sub(m: regex.Match[str]) -> str:
        cont = m.group(1)
        if should_soft_rejoin(cont):
            return cont
        return m.group(0)

    return _SOFT_HYPHEN_TIGHT_RE.sub(_sub, text)


def rejoin_known_split_latin_words(text: str) -> str:
    """Glue ``cli toral`` / ``di fferent`` when the joined token is a known word.

    Tokenizes into alpha / non-alpha runs and joins adjacent alpha tokens
    separated only by whitespace when ``left+right`` is in the dictionary.
    Scans left-to-right with restart so ``direct cli toral`` becomes
    ``direct clitoral`` (not a failed ``directcli``).
    """
    if not text:
        return text
    text = expand_latin_ligatures(text)
    # Keep whitespace runs as separate tokens
    parts: list[str] = regex.findall(r"[A-Za-z]+|\s+|[^A-Za-z\s]+", text)
    changed = True
    while changed:
        changed = False
        i = 0
        while i < len(parts) - 2:
            left, mid, right = parts[i], parts[i + 1], parts[i + 2]
            if (
                left.isalpha()
                and right.isalpha()
                and mid.isspace()
                and right.islower()
                and (left + right).lower() in _KNOWN_SPLIT_WORDS
            ):
                parts[i] = left + right
                del parts[i + 1 : i + 3]
                changed = True
                # restart from i to allow chain joins
                continue
            i += 1
    return "".join(parts)


# When the left stem is lost (formula split / OCR), ligature expansion leaves
# orphan tails: ``ﬀerent`` → ``fferent``. Map common OA/design-PDF tails back
# to full words at token boundaries only.
# High-precision only: short tails like ``low``/``ffer`` are real English
# words and must not be rewritten at token boundaries.
_ORPHAN_LIGATURE_STEMS: dict[str, str] = {
    "fferent": "different",
    "fficult": "difficult",
    "fficulty": "difficulty",
    "fficient": "efficient",
    "fficiency": "efficiency",
    "fficiently": "efficiently",
    "ffective": "effective",
    "ffectively": "effectively",
    "xceptionally": "exceptionally",  # lost leading 'e' after OCR
    "pproximation": "approximation",
    "rofessional": "professional",
    "ufficient": "sufficient",
}

_ORPHAN_STEM_RE = regex.compile(
    r"(?<![A-Za-z])("
    + "|".join(
        sorted((regex.escape(k) for k in _ORPHAN_LIGATURE_STEMS), key=len, reverse=True)
    )
    + r")(?![A-Za-z])",
    regex.IGNORECASE,
)


def repair_orphan_ligature_stems(text: str) -> str:
    """Repair ``fferent`` / ``fficult`` when the left stem was lost before MT.

    Design PDFs often isolate presentation ligatures into their own run; after
    expand the tail looks like a free token (``fferent``) and DeepLX leaves
    ``erent`` / ``ff`` debris in ZH. Only known tails are rewritten.
    """
    if not text:
        return text
    text = expand_latin_ligatures(text)

    def _sub(m: regex.Match[str]) -> str:
        raw = m.group(1)
        key = raw.lower()
        full = _ORPHAN_LIGATURE_STEMS.get(key)
        if not full:
            return raw
        # Preserve all-caps / title-ish casing loosely
        if raw.isupper():
            return full.upper()
        if raw[0].isupper():
            return full[0].upper() + full[1:]
        return full

    return _ORPHAN_STEM_RE.sub(_sub, text)


# Mid-word capitals from reverse-paint / microstyle fonts: ``anSWer``,
# ``acrobatIc``, ``trIgaSM``. Lowercase those tokens so MT sees real words.
# Requires a lower→Upper or multi-cap interior run (``iPhone`` is also
# lowercased — acceptable for MT input).
_MID_CAP_TOKEN_RE = regex.compile(r"\b[A-Za-z]{3,}\b")


def normalize_mid_word_cap_tokens(text: str) -> str:
    """Lowercase Latin tokens that show decorative mid-word capitals.

    Does **not** lowercase ordinary Title Case (``Women``) or ALLCAPS
    (``THIS``) tokens — only mixed interior shapes typical of design PDFs.
    """
    if not text:
        return text

    def _fix(m: regex.Match[str]) -> str:
        w = m.group(0)
        # Require mixed case (both lower and upper) so ALLCAPS / Title Case stay.
        if not any(c.islower() for c in w) or not any(c.isupper() for c in w):
            return w
        has_mid_cap = bool(regex.search(r"[a-z][A-Z]", w))
        has_inner_caps = bool(regex.search(r"[A-Za-z][A-Z]{2,}", w))
        if has_mid_cap or has_inner_caps:
            return w.lower()
        return w

    return _MID_CAP_TOKEN_RE.sub(_fix, text)


# OA / design PDFs: "Chapter1" after digit reorder or tight kerning.
# Chapter + 1–3 digits not already spaced; stops before a 4th digit.
_CHAPTER_DIGIT_RE = regex.compile(
    r"(?i)\b(chapter)(\d{1,3})(?!\d)"
)
# After "Chapter 1" glue a space before CJK (``Chapter 1爱`` → ``Chapter 1 爱``).
_CHAPTER_CJK_RE = regex.compile(
    r"(?i)\b(chapter\s+\d{1,3})([\u4e00-\u9fff\u3400-\u4dbf])"
)


def space_chapter_number(text: str) -> str:
    """Insert a space in ``Chapter1`` / ``CHAPTER12`` → ``Chapter 1``.

    Safe on body text: only matches the word Chapter immediately followed by
    1–3 digits (typical chapter index). Idempotent when already spaced
    (``Chapter 1`` has a non-digit gap). Also splits before CJK
    (``Chapter1爱`` → ``Chapter 1 爱``).
    """
    if not text or "hapter" not in text.lower():
        return text

    def _sub(m: regex.Match) -> str:
        return f"{m.group(1)} {m.group(2)}"

    text = _CHAPTER_DIGIT_RE.sub(_sub, text)
    text = _CHAPTER_CJK_RE.sub(r"\1 \2", text)
    return text


def normalize_decorative_title_case(text: str) -> str:
    """Normalize design-font mixed case for MT readability.

    Microstyle / reverse-paint titles often yield ``Who haS orgaSMS?`` which
    DeepLX mangles into ``WhohaSorgaSMS``. Lowercase short Latin titles that
    show mid-word capitals so MT sees ``who has orgasms?``.

    Guards: length ≤ 80, mostly ASCII letters, mid-word capitals or internal
    ALLCAPS run; does not touch normal prose (``iPhone`` alone is not enough
    without other decorative signals when length is long).
    """
    if not text or len(text) > 80:
        return text
    letters = [c for c in text if c.isalpha()]
    if len(letters) < 4:
        return text
    ascii_letters = [c for c in letters if ord(c) < 128]
    if len(ascii_letters) < max(4, int(0.8 * len(letters))):
        return text
    # Mid-word capital (haS) or internal multi-cap run (orgaSMS / SMS)
    has_mid_cap = bool(regex.search(r"[a-z][A-Z]", text))
    has_inner_caps = bool(regex.search(r"[A-Za-z][A-Z]{2,}", text))
    if not has_mid_cap and not has_inner_caps:
        return text
    # Preserve trailing punctuation; lowercase body.
    return text.lower()


def recover_latin_word_fragments(text: str) -> str:
    """Full post-pass: ligatures, soft hyphens, known mid-word space splits.

    Call after assembling paragraph unicode and before MT.
    Drop-cap ``I f`` rejoins run in ``drop_cap.rejoin_drop_cap_in_text``
    (usually before this, from ``get_char_unicode_string``).
    """
    if not text:
        return text
    # Late safety if callers skip layout_helper drop-cap pass
    from babeldoc.format.pdf.document_il.utils.drop_cap import rejoin_drop_cap_in_text

    text = expand_latin_ligatures(text)
    text = rejoin_drop_cap_in_text(text)
    text = rejoin_soft_hyphens_in_text(text)
    text = rejoin_soft_hyphen_tight(text)
    text = rejoin_ligature_space_splits(text)
    text = rejoin_known_split_latin_words(text)
    text = repair_orphan_ligature_stems(text)
    text = normalize_mid_word_cap_tokens(text)
    text = space_chapter_number(text)
    # Decorative mixed-case titles: apply normalize_decorative_title_case at
    # the call site when geometry/label is decorative (see layout_helper).
    text = expand_latin_ligatures(text)
    return text
