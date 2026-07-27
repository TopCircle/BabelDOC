"""Recover missing word boundaries and TeX soft hyphens from PDF geometry.

PDF often omits explicit space glyphs; TeX author lines use ~3.6pt gaps that
fall just under the classic 0.5× width threshold (``S.Hazra`` / ``andM.H.``).
Line wraps also leave soft hyphens (``ap-`` + ``proximation``).

Used by ``layout_helper.get_char_unicode_string`` and dummy-space insertion.
"""

from __future__ import annotations

import regex

from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter

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


def should_soft_rejoin(continuation: str | None) -> bool:
    """Whether ``word- cont`` is a TeX soft hyphen that should glue.

    Rejoin only pure-lowercase, non-standalone tails (``proximation``,
    ``ence``).  Refuse free English words (``actually``) and decorative
    mixed/Title case (``acTuaLLy``).
    """
    if not continuation:
        return False
    # Pure lowercase only — mixed/Title/UPPER stays as intentional dash.
    if not continuation.islower():
        return False
    if is_standalone_en_word(continuation):
        return False
    return True


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
    """
    if not text or "-" not in text:
        return text

    def _sub(m: regex.Match[str]) -> str:
        cont = m.group(1)
        if should_soft_rejoin(cont):
            return cont  # drop "- " and glue
        return m.group(0)  # keep hyphen + space

    return SOFT_HYPHEN_CANDIDATE_RE.sub(_sub, text)
