"""
Entity hygiene for the real public-record corpus.

Two failure modes cost the sheet its credibility, and both are decided here rather than in each
connector, so a fix lands everywhere at once:

1. Artifact entities. A watchlist row's ISO country code ("IN") became a LOCATION that 305 people
   "resided at" - a hub with no evidence behind it that distorted every centrality score. Anything
   `is_junk` rejects must never reach the graph.

2. Role confusion. 93% of the corpus is court judgments, so the loudest names in it are judges,
   state parties and the Union of India - the machinery of a case, not its subjects. `role_of`
   labels them so ranking, alerts and suspicion can hold them apart from the people a case is
   actually about. The sheet promises that nothing on it asserts guilt; a judge ranked as a key
   player breaks that promise.
"""
from __future__ import annotations

import re

from .geo import COUNTRIES
from .ner import BANK_ACCOUNT, GOV_ID, LOCATION, ORGANIZATION, PERSON, PHONE

# --- 1. artifacts ------------------------------------------------------------------------------

# Identifiers are legitimately all digits and carry no letters. A bare number is an artifact only
# where a *name* was expected; rejecting it everywhere silently deleted every phone number, which
# took call records, USES_PHONE links and the burner-phone detector with it.
NUMERIC_TYPES = {PHONE, BANK_ACCOUNT, GOV_ID}

# Bare ISO codes reaching entity resolution are always a connector leaking a field, never a place.
ISO2 = set(COUNTRIES) | {"AF", "AL", "DZ", "AR", "AT", "AZ", "BH", "BY", "BG", "KH", "CL", "CO", "HR",
                         "CZ", "DK", "EG", "EE", "FI", "GE", "GH", "GR", "HU", "IS", "IE", "IL", "JO",
                         "KZ", "LV", "LB", "LT", "MA", "NZ", "NO", "PE", "PL", "PT", "RO", "RS", "SK",
                         "SI", "SE", "TW", "TZ", "UA", "UY", "UZ", "VE", "ZW"}

# Tokens that are grammar, not names - seen as LOCATION/ORGANIZATION from loose extraction.
JUNK_LABELS = {
    "in", "on", "at", "of", "the", "and", "or", "to", "by", "for", "with", "from", "as", "is",
    "n/a", "na", "null", "none", "nil", "unknown", "not available", "not known", "-", "--", "...",
    "india", "other", "others", "misc", "miscellaneous", "same", "ditto", "do", "etc",
}

# A person mention must name somebody. Free-text extractors (and language models especially)
# return descriptor phrases - "his cousin", "the accused", "one of them" - which are grammar
# pointing at a person, not an identity. In these documents a real name is capitalised, so a
# PERSON label with no capitalised token is a descriptor. Non-Latin scripts have no case, so
# the rule only applies where ASCII letters are present.
_LEADING_CUE_RE = re.compile(
    r"^(?:the|a|an|one|his|her|their|its|my|our|your|another|other|said|above|same|this|that|"
    r"co-?accused|accused|complainant|suspect|victim|deceased|witness|informant|applicant)\b\s*", re.I)
_ASCII_LETTER_RE = re.compile(r"[A-Za-z]")
_CAP_TOKEN_RE = re.compile(r"\b[A-Z][a-z'\u2019]+|\b[A-Z]{2,}\b")


# Headline prose capitalises ordinary words, so a capitalised run is not yet a name. "Ban Ajit
# Pawar", "Over Gulzar Singh" and "Vikram Mumbai Demolition" all arrived this way from news pages.
# A token that is an ordinary English word, or a place, cannot be part of somebody's name here.
NON_NAME_TOKENS = {
    # sentence glue that leads a capitalised run
    "a", "an", "the", "and", "or", "but", "as", "at", "by", "for", "from", "in", "into", "of", "on",
    "over", "to", "with", "after", "amid", "before", "during", "under", "against", "between",
    # headline verbs and nouns
    "ban", "bans", "banned", "held", "hold", "says", "said", "seeks", "seek", "gets", "get", "row",
    "case", "cases", "court", "police", "arrest", "arrested", "murder", "murdered", "death", "dead",
    "killed", "attack", "probe", "raid", "bail", "fir", "chargesheet", "verdict", "hearing", "plea",
    "demolition", "airbase", "airport", "station", "hospital", "school", "college", "university",
    "minister", "chief", "president", "governor", "mayor", "commissioner", "officer", "inspector",
    "report", "reports", "news", "video", "photos", "live", "updates", "exclusive", "opinion",
    "today", "yesterday", "week", "month", "year", "day", "night", "morning", "evening",
}


def is_person_name(label: str) -> bool:
    """True when a PERSON label plausibly names an individual rather than describing one.

    Two independent failures are caught here. A descriptor ("his cousin") has no capitalised token
    at all. A headline fragment ("Ban Ajit Pawar") is capitalised throughout but contains a word
    that is not part of anybody's name. Both reached the graph from real corpora.
    """
    t = (label or "").strip()
    if not t:
        return False
    if not _ASCII_LETTER_RE.search(t):
        return True  # Devanagari and other caseless scripts: cannot judge by capitalisation
    core = _LEADING_CUE_RE.sub("", t).strip()
    if not core or not _CAP_TOKEN_RE.search(core):
        return False
    tokens = [tok.strip(".,'’").lower() for tok in core.split()]
    tokens = [tok for tok in tokens if tok]
    if not tokens:
        return False
    if any(tok in NON_NAME_TOKENS for tok in tokens):
        return False
    # a place inside a person's name means a headline ran two facts together
    from .geo import CITIES, STATES

    places = {p.lower() for p in CITIES} | {p.lower() for p in STATES}
    return not any(tok in places for tok in tokens)


_ONLY_PUNCT_RE = re.compile(r"^[\W_]+$")
_ONLY_DIGITS_RE = re.compile(r"^\d+$")
_HAS_LETTER_RE = re.compile(r"[A-Za-z]")


def is_junk(etype: str, label: str) -> tuple[bool, str]:
    """
    Should this mention become a graph entity at all?

    Returns (rejected, reason). The reason is recorded on the audit trail so a purge is explainable
    rather than a silent deletion of someone's data.
    """
    t = (label or "").strip()
    if not t:
        return True, "empty label"
    low = t.lower()
    if low in JUNK_LABELS:
        return True, f"stopword token '{t}'"
    if _ONLY_PUNCT_RE.match(t):
        return True, "punctuation only"
    if etype not in NUMERIC_TYPES:
        if _ONLY_DIGITS_RE.match(t):
            return True, f"bare number '{t}'"
        if not _HAS_LETTER_RE.search(t):
            return True, "no letters"
    # "IN" / "AE" as a place is a country code a connector forgot to expand.
    if etype == LOCATION and t.upper() in ISO2 and len(t) == 2:
        return True, f"ISO country code '{t.upper()}' used as a location"
    # A one or two character person/org name carries no identity.
    if etype in (PERSON, ORGANIZATION) and len(re.sub(r"\W", "", t)) < 3:
        return True, f"name too short '{t}'"
    if etype == PERSON and not is_person_name(t):
        return True, f"descriptor, not a name '{t}'"
    return False, ""


# --- 2. roles ----------------------------------------------------------------------------------

# A case is *against* the state, so the state is not a suspect in it.
INSTITUTION_RE = re.compile(
    r"^\s*(?:the\s+)?(?:state\s+of\b|union\s+of\s+india\b|govt\.?\s+of\b|government\s+of\b|"
    r"republic\s+of\s+india\b|state\b\s*$)", re.I)
AUTHORITY_RE = re.compile(
    r"\b(?:high\s+court|supreme\s+court|district\s+court|sessions\s+court|tribunal|commissioner\s+of\s+police|"
    r"police\s+station|superintendent\s+of\s+police|directorate\s+of\s+enforcement|enforcement\s+directorate|"
    r"central\s+bureau\s+of\s+investigation|c\.?b\.?i\.?|narcotics\s+control\s+bureau|income\s+tax\s+department|"
    r"customs|registrar|municipal\s+corporation|ministry\s+of)\b", re.I)

# Court personnel and institutional parties: present in the record, never its subject.
NON_SUBJECT_ROLES = {"judge", "institution", "authority"}


def role_of(etype: str, label: str, attrs: dict | None = None) -> str | None:
    """
    Classify an entity's standing in the record.

      judge        - decided the matter
      institution  - the State / Union as a party
      authority    - a court, police unit or regulator named in the text
      petitioner / respondent - a real party, carried through from the source

    None means an ordinary entity. Everything in NON_SUBJECT_ROLES is excluded from suspicion
    scoring and key-player ranking.
    """
    a = attrs or {}
    court_role = (a.get("court_role") or "").lower().strip()
    if court_role == "judge":
        return "judge"
    text = (label or "").strip()
    if etype == ORGANIZATION and INSTITUTION_RE.match(text):
        return "institution"
    if etype == ORGANIZATION and AUTHORITY_RE.search(text):
        return "authority"
    if court_role in ("petitioner", "respondent", "complainant", "accused"):
        return court_role
    return None


def is_non_subject(etype: str, label: str, attrs: dict | None = None) -> bool:
    """True when an entity is part of the machinery of a case rather than a subject of it."""
    return role_of(etype, label, attrs) in NON_SUBJECT_ROLES
