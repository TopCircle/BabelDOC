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
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph

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

# ASCII hyphen, Unicode hyphen/NB hyphen, and TeX soft hyphen (U+00AD).
HYPHEN_CHARS = frozenset("-\u2010\u2011\u00ad")

# Candidate soft-hyphen after style regroup: ``ap- proximation``.
# Captures the full continuation token (mixed-case allowed) so we can reject
# free English words. Decorative TOC fonts often yield ``acTuaLLy``; matching
# only ``[a-z]+`` would capture ``ac`` (len<4), rejoin to ``TrigasMacTuaLLy``.
# OA S7: also join across ILTranslator style markers and U+00AD, and require
# a 2+ letter stem so ``g-spot`` / ``e-mail`` stay hyphenated.
_STYLE_OPEN_RE = "(?:\u3016B\\d+\u3017)"
_STYLE_CLOSE_RE = "(?:\u3016/B\\d+\u3017)"
SOFT_HYPHEN_CANDIDATE_RE = regex.compile(
    r"(?<=[A-Za-z]{2})"
    "[-\u2010\u2011\u00ad]"
    r"\s*"
    r"(?:" + _STYLE_OPEN_RE + r"\s*)?"
    r"([A-Za-z][A-Za-z']*)"
    r"(?:\s*" + _STYLE_CLOSE_RE + r")?"
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



def latin_continuation_token(text: str | None) -> str:
    """First Latin token of *text* after ligature expand (soft-hyphen tail)."""
    if not text:
        return ""
    text = expand_latin_ligatures(text.lstrip())
    m = regex.match(r"[A-Za-z']+", text)
    return m.group(0) if m else ""


def peek_latin_continuation(chars: list, start: int) -> str:
    """Collect a Latin token from *chars[start:]*, skipping ``str`` markers.

    Ligatures are expanded so ``\ufb00`` counts as ``ff``. Used when a hyphen
    wrap is interrupted by style markers (non-LLM wrap) or dummy wrap spaces.
    """
    parts: list[str] = []
    j = start
    n = len(chars)
    while j < n:
        item = chars[j]
        if isinstance(item, str):
            j += 1
            continue
        u = getattr(item, "char_unicode", None)
        if u is None:
            break
        u = expand_latin_ligatures(u)
        if not u or u.isspace():
            j += 1
            continue
        m = regex.match(r"[A-Za-z']+", u)
        if not m:
            break
        parts.append(m.group(0))
        if m.end() < len(u):
            break
        j += 1
        if sum(len(p) for p in parts) >= 48:
            break
    return "".join(parts)


def mixed_chars_stem(chars: list) -> str:
    """Rough unicode of mixed PdfCharacter/str lists (hyphen-wrap stem)."""
    parts: list[str] = []
    for item in chars:
        if isinstance(item, str):
            parts.append(item)
            continue
        u = getattr(item, "char_unicode", None)
        if u is None:
            continue
        parts.append(expand_latin_ligatures(u))
    return "".join(parts)


def should_join_hyphen_wrap(left: str | None, continuation: str | None) -> bool:
    """True when *left* ends with a hyphenated Latin stem and *continuation*
    is a TeX line-wrap tail (not ``g-spot`` / ``Trigasm- actually``).

    Same-paragraph adjacent spans/compositions use this before MT so
    ``stu-`` + ligature ``ff`` becomes one token. Separate ``translate()``
    calls (true two-paragraph splits) cannot join.
    """
    if not left:
        return False
    text = expand_latin_ligatures(left)
    text = regex.sub("(?:\u3016/?B\\d+\u3017)+\\s*$", "", text.rstrip())
    text = text.rstrip()
    if not text or text[-1] not in HYPHEN_CHARS:
        return False
    stem = regex.sub("(?:\u3016/?B\\d+\u3017)+\\s*$", "", text[:-1])
    m = regex.search(r"[A-Za-z]+$", stem)
    if not m or len(m.group(0)) < 2:
        return False
    return should_soft_rejoin(latin_continuation_token(continuation))


def is_soft_hyphen_line_wrap(
    prev: PdfCharacter,
    next_ch: PdfCharacter,
    next_word: str | None = None,
) -> bool:
    """TeX soft hyphen at line wrap: ``ap-`` + ``proximation`` \u2192 join without space.

    Geometry: prev is ``-`` / U+00AD and next starts a Latin letter run.
    Semantics deferred to :func:`should_soft_rejoin` on the peeked
    continuation token (ligatures expanded). Prefer
    :func:`should_join_hyphen_wrap` when the left stem is available so
    ``g-spot`` is not glued.
    """
    prev_u = prev.char_unicode or ""
    next_u = expand_latin_ligatures(next_ch.char_unicode or "")
    if prev_u not in HYPHEN_CHARS or not next_u or not next_u[0].isalpha():
        return False
    token = next_word if next_word else next_u
    return should_soft_rejoin(latin_continuation_token(token))


def rejoin_soft_hyphens_in_text(text: str) -> str:
    """Collapse ``ap- proximation`` style soft hyphens left after style regroup.

    Keeps intentional dashes before free English words / decorative casing:
    ``Trigasm- actually`` / ``TrigasM- acTuaLLy`` must not glue.

    Ligatures in the continuation (``di- \ufb03cult``) are expanded first so the
    free-word blocklist and rejoin logic see ``fficult`` not a private-use char.

    OA S7: also joins style-marker wraps and U+00AD in one string.
    """
    if not text:
        return text
    text = expand_latin_ligatures(text)
    if not any(h in text for h in HYPHEN_CHARS):
        return text

    def _sub(m: regex.Match[str]) -> str:
        cont = expand_latin_ligatures(m.group(1))
        if should_soft_rejoin(cont):
            return cont  # drop hyphen / markers and glue
        return m.group(0)  # keep hyphen + space / markers

    return SOFT_HYPHEN_CANDIDATE_RE.sub(_sub, text)


# Hyphen without space: ``di-fferent`` / ``ap-proximation``.
_SOFT_HYPHEN_TIGHT_RE = regex.compile(
    r"(?<=[A-Za-z]{2})" + "[-\u2010\u2011\u00ad]" + r"([a-z]{2,})"
)

# Full words often split by PDF gaps / soft hyphens in design ebooks (OA dual).
# Single source of truth for space-join, short-stem+ff glue, and orphan tails.
_KNOWN_SPLIT_WORDS = frozenset(
    {
        "different",
        "difficult",
        "clitoral",
        "clitoris",
        "stuff",
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

# Prefixes stripped to derive orphan tails (``di``+``fferent``, lost ``e``+``ffective``).
# Longer prefixes first so ``self`` wins over ``s`` if both ever match.
_ORPHAN_STRIP_PREFIXES: tuple[str, ...] = (
    "self",
    "pro",
    "pre",
    "per",
    "dis",
    "di",
    "de",
    "su",
    "ap",
    "ef",
    "cli",
    "e",
    "a",
)

# After ligature expand: ``di fferent`` — only short stems, and only when joined
# form is a known split word (never ``like fferent`` → ``likefferent``).
_LIGATURE_SPACE_CONT_RE = regex.compile(
    r"\b([A-Za-z]{1,3})\s+((?:ff|fi|fl|ffi|ffl)[a-z]*)",
    regex.IGNORECASE,
)


def _build_orphan_tail_map() -> dict[str, str]:
    """Map lost-stem tails → full word from :data:`_KNOWN_SPLIT_WORDS`.

    E.g. ``different`` − ``di`` → ``fferent``; ``exceptionally`` − ``e`` →
    ``xceptionally``. One truth source — no parallel OA whitelist.

    On tail collisions prefer the **shorter stripped prefix** (ligature/OCR
    loss is usually 1–2 letters: ``e``+``fficient`` beats ``su``+``fficient``).
    """
    # tail -> (word, prefix_len)
    best: dict[str, tuple[str, int]] = {}
    for word in _KNOWN_SPLIT_WORDS:
        for pref in _ORPHAN_STRIP_PREFIXES:
            if not word.startswith(pref):
                continue
            tail = word[len(pref) :]
            if len(tail) < 4:
                continue
            # Refuse free English words and tails that are already full known words
            # (``self``+``understanding`` must not map orphan ``understanding``).
            if is_standalone_en_word(tail) or tail in _KNOWN_SPLIT_WORDS:
                continue
            pref_len = len(pref)
            prev = best.get(tail)
            if (
                prev is None
                or pref_len < prev[1]
                or (pref_len == prev[1] and len(word) > len(prev[0]))
            ):
                best[tail] = (word, pref_len)
    return {tail: word for tail, (word, _) in best.items()}


_ORPHAN_TAIL_TO_WORD: dict[str, str] = _build_orphan_tail_map()
_ORPHAN_TAIL_RE = (
    regex.compile(
        r"(?<![A-Za-z])("
        + "|".join(
            sorted(
                (regex.escape(t) for t in _ORPHAN_TAIL_TO_WORD),
                key=len,
                reverse=True,
            )
        )
        + r")(?![A-Za-z])",
        regex.IGNORECASE,
    )
    if _ORPHAN_TAIL_TO_WORD
    else None
)


def _match_case(template: str, word: str) -> str:
    """Apply rough casing of *template* onto *word*."""
    if template.isupper():
        return word.upper()
    if template[:1].isupper():
        return word[:1].upper() + word[1:]
    return word


def rejoin_ligature_space_splits(text: str) -> str:
    """Glue ``di fferent`` when the joined token is a known split word."""
    if not text:
        return text
    text = expand_latin_ligatures(text)

    def _sub(m: regex.Match[str]) -> str:
        joined = m.group(1) + m.group(2)
        if joined.lower() in _KNOWN_SPLIT_WORDS:
            return joined
        return m.group(0)

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
                continue
            i += 1
    return "".join(parts)


def repair_orphan_split_tails(text: str) -> str:
    """Repair ``fferent`` / ``fficult`` when the left stem was lost before MT.

    Tails are derived from :data:`_KNOWN_SPLIT_WORDS` via
    :func:`_build_orphan_tail_map` — not a second hard-coded word list.
    """
    if not text or _ORPHAN_TAIL_RE is None:
        return text
    text = expand_latin_ligatures(text)

    def _sub(m: regex.Match[str]) -> str:
        raw = m.group(1)
        full = _ORPHAN_TAIL_TO_WORD.get(raw.lower())
        if not full:
            return raw
        return _match_case(raw, full)

    return _ORPHAN_TAIL_RE.sub(_sub, text)


# Back-compat alias (older tests / call sites).
repair_orphan_ligature_stems = repair_orphan_split_tails


def has_decorative_mid_caps(text: str) -> bool:
    """True if *text* shows design-font mid-word capitals (``haS``, ``orgaSMS``).

    Shared predicate for title-case normalization. Requires mixed case so
    ALLCAPS / pure Title Case (``Women``) stay untouched.
    """
    if not text:
        return False
    if not any(c.islower() for c in text) or not any(c.isupper() for c in text):
        return False
    if regex.search(r"[a-z][A-Z]", text):
        return True
    if regex.search(r"[A-Za-z][A-Z]{2,}", text):
        return True
    return False


# OA / design PDFs: "Chapter1" after digit reorder or tight kerning.
_CHAPTER_DIGIT_RE = regex.compile(
    r"(?i)\b(chapter)(\d{1,3})(?!\d)"
)
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


_MIDCAP_TITLE_LABELS = frozenset({"title", "section_header"})


def _mostly_ascii_letters(text: str) -> bool:
    """True when *text* is short and mostly ASCII letters (title-case gate).

    Cap is 200 (not 80): OA position titles glue mid-caps name + DIRECT/THRUST
    tags into ~90–120 chars. 12pt body brands stay protected by the *label*
    gate in :func:`should_normalize_midcap_title`, not this length cap.
    """
    if not text or len(text) > 200:
        return False
    letters = [c for c in text if c.isalpha()]
    if len(letters) < 4:
        return False
    ascii_letters = [c for c in letters if ord(c) < 128]
    return len(ascii_letters) >= max(4, int(0.8 * len(letters)))


def should_normalize_midcap_title(
    paragraph: PdfParagraph,
    text: str | None = None,
) -> bool:
    """True when a mid-caps title should be lowered without tracking.

    Must AND :func:`has_decorative_mid_caps`. Must not open OR on 12pt body
    (``plain text`` / BODY labels). Qualifies when the layout label is
    ``title`` / ``section_header`` or :func:`is_display_title` (font ≥ 28pt).
    """
    src = text if text is not None else (getattr(paragraph, "unicode", None) or "")
    if not has_decorative_mid_caps(src):
        return False
    if not _mostly_ascii_letters(src):
        return False
    label = (getattr(paragraph, "layout_label", None) or "").strip().lower()
    if label in _MIDCAP_TITLE_LABELS:
        return True
    from babeldoc.format.pdf.document_il.utils.vertical_gap import is_display_title

    return is_display_title(paragraph)


def normalize_decorative_title_case(text: str) -> str:
    """Normalize design-font mixed case for MT readability.

    Microstyle / reverse-paint titles often yield ``Who haS orgaSMS?`` which
    DeepLX mangles into ``WhohaSorgaSMS``. Lowercase short Latin titles that
    show mid-word capitals so MT sees ``who has orgasms?``.

    Guards: length ≤ 200, mostly ASCII letters, :func:`has_decorative_mid_caps`.
    Call only from decorative/geometry-gated sites — not on full body prose
    (would smash ``iPhone`` / ``eBay``).

    Proper CamelCase tokens (``LearnTheTrigasmBasics``) are spaced before
    lowercasing so MT/glossary see real words. Mid-caps soup
    (``SLoWcoMfortaBLe``, consecutive caps) is lowered in place — do **not**
    run a naive ``(?<=[a-z])(?=[A-Z])`` split on that soup.
    """
    if not _mostly_ascii_letters(text or ""):
        return text
    if not has_decorative_mid_caps(text):
        return text
    text = _space_proper_camel_case(text)
    return text.lower()


# Proper CamelCase: starts with a capital, humps are Upper+lowers, no mid-caps soup.
_PROPER_CAMEL_TOKEN_RE = regex.compile(r"\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b")
_CAMEL_HUMP_RE = regex.compile(r"(?<=[a-z])(?=[A-Z])")


def _space_proper_camel_case(text: str) -> str:
    """``LearnTheTrigasmBasics`` → ``Learn The Trigasm Basics``.

    Leaves ``SLoWcoMfortaBLe`` / ``dIrect`` / ``otWart`` untouched (those are
    not proper CamelCase).
    """
    return _PROPER_CAMEL_TOKEN_RE.sub(
        lambda m: _CAMEL_HUMP_RE.sub(" ", m.group(0)),
        text,
    )


def recover_latin_word_fragments(text: str) -> str:
    """Pre-MT recovery: ligatures, soft hyphens, known splits, orphan tails.

    Call after assembling paragraph unicode and before MT.
    Drop-cap ``I f`` rejoins run in ``drop_cap.rejoin_drop_cap_in_text``
    (usually before this, from ``get_char_unicode_string``).

    Decorative mid-word caps are **not** applied here — use
    :func:`normalize_decorative_title_case` at geometry-gated call sites.
    """
    if not text:
        return text
    from babeldoc.format.pdf.document_il.utils.drop_cap import rejoin_drop_cap_in_text

    text = expand_latin_ligatures(text)
    text = rejoin_drop_cap_in_text(text)
    text = rejoin_soft_hyphens_in_text(text)
    text = rejoin_soft_hyphen_tight(text)
    text = rejoin_ligature_space_splits(text)
    text = rejoin_known_split_latin_words(text)
    text = repair_orphan_split_tails(text)
    text = space_chapter_number(text)
    return text
