"""Bilingual entity matching and headline similarity.

This is the piece that would normally be a 2 GB LaBSE model. On a CPU-only
laptop that is a bad trade, so instead we lean on the fact that a state's
news revolves around a knowable cast: about sixty people, places, parties and
recurring topics. Match those in either script and a Telugu headline and its
English twin land on the same canonical signature.

Nothing here is heuristic guesswork about *language* — it is a lookup table you
can read, correct and extend in config.LEXICON.
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

from . import config

TELUGU_RANGE = re.compile(r"[ఀ-౿]")
# Any other Indic script. Google's India-wide trends carry Hindi, Marathi,
# Tamil, Kannada and Bengali queries that mean nothing to a Telugu desk.
_OTHER_INDIC = re.compile(r"[\u0900-\u0BFF\u0C80-\u0DFF]")  # Devanagari … Tamil, Kannada … Sinhala
_WORD = re.compile(r"[\wఀ-౿]+", re.UNICODE)

# Build a surface-form -> key index once, longest form first so that
# "chandrababu naidu" wins over the bare "naidu".
_SURFACES: list[tuple[str, str, str]] = []  # (surface, key, kind)
for _key, (_kind, _forms) in config.LEXICON.items():
    for _form in _forms:
        _SURFACES.append((_form.lower(), _key, _kind))
_SURFACES.sort(key=lambda t: len(t[0]), reverse=True)

LOCAL_PLACE_KEYS = {k for k, (kind, _) in config.LEXICON.items() if kind == "place"}
TOPIC_KEYS = {k for k, (kind, _) in config.LEXICON.items() if kind == "topic"}
# Named things. "cricket" or "cinema" identify a beat; "tirumala" identifies a
# story, and only the latter can tie a search query to a headline.
SPECIFIC_KEYS = {k for k in config.LEXICON if k not in TOPIC_KEYS}
# Locality is derived from the lexicon so that adding a minister there is
# enough; only the exceptions are listed, in config.
NATIONAL_KEYS = config.NATIONAL_KEYS
NEIGHBOUR_KEYS = config.NEIGHBOUR_KEYS
_EXCEPT = NATIONAL_KEYS | NEIGHBOUR_KEYS
LOCAL_PERSON_KEYS = {k for k, (kind, _) in config.LEXICON.items()
                     if kind == "person" and k not in _EXCEPT}
LOCAL_ORG_KEYS = {k for k, (kind, _) in config.LEXICON.items()
                  if kind == "org" and k not in _EXCEPT}


def is_telugu(text: str) -> bool:
    return bool(TELUGU_RANGE.search(text or ""))


# Every headline is re-examined on each tick against every live trend, so these
# three run hundreds of thousands of times a minute on the same few thousand
# strings. Uncached, that alone took a tick past its own five-minute interval.
@lru_cache(maxsize=50_000)
def desk_script(text: str) -> bool:
    """True if the text is Telugu, Latin, or a mix — the scripts this desk reads."""
    return not _OTHER_INDIC.search(text or "")


@lru_cache(maxsize=200_000)
def normalise(text: str) -> str:
    """Lowercase, strip accents/punctuation, keep Telugu intact."""
    text = unicodedata.normalize("NFKC", text or "")
    return " ".join(_WORD.findall(text.lower()))


@lru_cache(maxsize=100_000)
def _entities_cached(text: str) -> frozenset[str]:
    return frozenset(_entities_uncached(text))


def entities(text: str) -> set[str]:
    """Lexicon keys named anywhere in the headline, in either script."""
    return set(_entities_cached(text)) if text else set()


def _entities_uncached(text: str) -> set[str]:
    if not text:
        return set()
    hay = " " + normalise(text) + " "
    found: set[str] = set()
    for surface, key, _kind in _SURFACES:
        if key in found:
            continue
        needle = normalise(surface)
        if not needle:
            continue
        # Word-boundary match for Latin; substring is correct for Telugu, which
        # agglutinates case endings straight onto the noun (విశాఖపట్నంలో).
        if is_telugu(surface):
            if needle in hay:
                found.add(key)
        elif re.search(r"(?<![\w])" + re.escape(needle) + r"(?![\w])", hay):
            found.add(key)
    return found


# Newsroom shorthand that would otherwise look like a different word.
_ABBREV = {
    "govt": "government", "cm": "chiefminister", "dy": "deputy",
    "mla": "legislator", "mlas": "legislator", "mp": "parliamentarian",
    "hc": "highcourt", "sc": "supremecourt", "cbi": "cbi", "ed": "enforcement",
    "dept": "department", "univ": "university", "assn": "association",
    "vizag": "visakhapatnam", "amaravathi": "amaravati",
}


def _stem(token: str) -> str:
    """Crude English suffix stripping so plurals and tenses agree.

    Telugu needs no equivalent here — its case endings agglutinate onto nouns,
    which is exactly why entity matching does the cross-lingual work instead.
    """
    if token in _ABBREV:
        return _ABBREV[token]
    if not token.isascii() or len(token) <= 4:
        return token
    for suffix in ("ing", "ies", "ed", "es", "s"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 4:
            base = token[: -len(suffix)]
            return base + "y" if suffix == "ies" else base
    return token


@lru_cache(maxsize=100_000)
def _tokens_cached(text: str) -> frozenset[str]:
    return frozenset(
        _stem(t) for t in normalise(text).split()
        if len(t) > 2 and t not in config.STOPWORDS and not t.isdigit()
    )


def tokens(text: str) -> set[str]:
    """Content words: stopwords dropped, English plurals and tenses folded."""
    return set(_tokens_cached(text)) if text else set()


def locality(keys: set[str]) -> tuple[float, str]:
    """How local is this? Returns (multiplier, label).

    Only a named place, politician or institution counts. Topic words like
    "cricket" or "movie" are deliberately worthless here — otherwise a
    Caribbean Premier League scorecard reads as local news because it
    contains the word wicket.
    """
    if keys & (LOCAL_PLACE_KEYS | LOCAL_PERSON_KEYS | LOCAL_ORG_KEYS):
        return config.LOCALITY_STRONG, config.LOCAL_LABEL
    if keys & NEIGHBOUR_KEYS:
        return config.LOCALITY_WEAK, config.NEIGHBOUR_LABEL
    return config.LOCALITY_NONE, "wider"


def signature(text: str) -> str:
    """Canonical, language-independent identity for a headline."""
    keys = entities(text)
    if keys:
        return "|".join(sorted(keys))
    # No known entity: fall back to the four most distinctive tokens.
    return "~" + "|".join(sorted(tokens(text))[:4])


def similarity(a_title: str, b_title: str,
               a_ents: set[str] | None = None,
               b_ents: set[str] | None = None) -> float:
    """0..1 similarity that works across English and Telugu.

    Entity overlap carries the cross-lingual weight; token overlap separates
    two different stories that happen to name the same politician.
    """
    a_ents = entities(a_title) if a_ents is None else a_ents
    b_ents = entities(b_title) if b_ents is None else b_ents

    ent_score = 0.0
    if a_ents and b_ents:
        ent_score = len(a_ents & b_ents) / len(a_ents | b_ents)

    a_tok, b_tok = tokens(a_title), tokens(b_title)
    tok_score = 0.0
    if a_tok and b_tok:
        tok_score = len(a_tok & b_tok) / len(a_tok | b_tok)

    shared_tok = len(a_tok & b_tok)
    cross_script = is_telugu(a_title) != is_telugu(b_title)
    if cross_script:
        # Telugu headlines from these outlets almost always carry a Latin
        # kicker — "Pawan Kalyan:", "Visakhapatnam Airport |" — so shared Latin
        # words are a real cross-script signal on top of the entity overlap.
        latin_shared = len({t for t in a_tok & b_tok if t.isascii()})
        shared_ents = len(a_ents & b_ents)
        if shared_ents >= 2:
            return 0.55 + 0.45 * ent_score
        if shared_ents >= 1 and latin_shared >= 1:
            return 0.44 + 0.30 * ent_score + min(0.20, 0.10 * latin_shared)
        if latin_shared >= 3:
            return 0.45
        return 0.30 * ent_score

    # Same script. Two headlines about one event share several distinctive
    # words; two headlines that merely name the same politician do not.
    if shared_tok < 2:
        return min(0.35, 0.55 * ent_score)
    return 0.45 * ent_score + 0.55 * tok_score


MERGE_THRESHOLD = 0.42


def matches_trend(trend_query: str, title: str,
                  title_ents: set[str] | None = None) -> float:
    """How strongly does a headline answer a live search query? 0..1."""
    if not trend_query or not title:
        return 0.0
    t_ents = entities(trend_query)
    h_ents = entities(title) if title_ents is None else title_ents

    q_tok = tokens(trend_query)
    h_tok = tokens(title)
    same_script = is_telugu(trend_query) == is_telugu(title)

    # The query names something specific and the headline names all of it.
    #
    # Within one script that is not sufficient on its own: "rohan naidu" and
    # "Jagan slams Naidu" share the Naidu entity while being unrelated stories,
    # so the query's own words have to show up too. Across scripts there are no
    # shared words to check, which is exactly what the lexicon is for.
    named = t_ents & SPECIFIC_KEYS
    if named and h_ents and t_ents <= h_ents:
        if not same_script:
            return 1.0
        if q_tok and len(q_tok & h_tok) / len(q_tok) >= 0.7:
            return 1.0

    q_norm = normalise(trend_query)
    h_norm = normalise(title)
    if q_norm and q_norm in h_norm:
        return 1.0

    if q_tok and h_tok:
        # Strict, because the word a query does *not* share is usually the one
        # that matters: "delhi high court" overlaps "Andhra Pradesh High Court"
        # on two words out of three while meaning a different court entirely.
        covered = len(q_tok & h_tok) / len(q_tok)
        if covered >= 0.75:
            return 0.55 + 0.45 * covered
    if named and h_ents and not same_script:
        shared = len(named & h_ents) / len(named)
        if shared >= 0.5:
            return 0.45 + 0.35 * shared
    return 0.0
