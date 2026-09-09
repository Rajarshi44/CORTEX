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
from .ner import LOCATION, ORGANIZATION, PERSON

# --- 1. artifacts ------------------------------------------------------------------------------

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
