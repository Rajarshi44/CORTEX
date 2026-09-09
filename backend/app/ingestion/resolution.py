"""
Entity resolution: maps raw mentions from any source onto canonical graph entities.

Strategies (in order):
  1. Deterministic normalisation (phones -> 10 digit, plates -> compact uppercase, ...)
  2. Alias index ("Salim Bhai" -> Salim Qureshi, "Bhai" -> Rafiq Sheikh when unambiguous)
  3. Fuzzy name matching (RapidFuzz token_set_ratio) with blocking on first letter
  4. Otherwise create a new entity
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime

from rapidfuzz import fuzz, process
from sqlalchemy.orm import Session

from ..config import settings
from ..db import Entity
from .ner import (BANK_ACCOUNT, CASE, GOV_ID, LOCATION, ORGANIZATION, PERSON, PHONE, REPORT, SOCIAL_HANDLE,
                  VEHICLE, RuleNER)
from .quality import is_junk, role_of


class JunkMention(ValueError):
    """A mention that must not become an entity (stopword, bare number, ISO code as a place)."""

    def __init__(self, etype: str, text: str, reason: str):
        super().__init__(f"{etype}:{text!r} rejected - {reason}")
        self.etype, self.text, self.reason = etype, text, reason

HONORIFIC_RE = re.compile(r"^(?:shri|smt|sri|mr|mrs|ms|miss|dr|adv|kum)\.?\s+", re.I)
ORG_SUFFIX_RE = re.compile(r"\b(pvt\.?\s*ltd\.?|private\s+limited|ltd\.?|limited|llp|co\.?|company)\b\.?", re.I)


def canonical_key(etype: str, text: str) -> str:
    t = text.strip()
    if etype == PHONE:
        return RuleNER.norm_phone(t)
    if etype == VEHICLE:
        return RuleNER.norm_vehicle(t)
    if etype == BANK_ACCOUNT:
        return re.sub(r"\s", "", t.lower()) if "@" in t else re.sub(r"\D", "", t)
    if etype == PERSON:
        t = HONORIFIC_RE.sub("", t)
        t = re.sub(r"[.\-']", "", t)
        t = re.sub(r"\s+", " ", t).strip().lower()
        t = re.sub(r"^(mohd|md|mohammad|mohammed)\b", "mohd", t)
        return t
    if etype == ORGANIZATION:
        t = ORG_SUFFIX_RE.sub("", t)
        t = re.sub(r"[^\w& ]", "", t)
        return re.sub(r"\s+", " ", t).strip().lower()
    if etype == SOCIAL_HANDLE:
        return t.lower().lstrip("@")
    if etype == GOV_ID:
        return re.sub(r"[\s-]", "", t).upper()
    return re.sub(r"\s+", " ", t).strip().lower()


# Two people share a name and the sheet must show both. The suffix has to tell a reader which
# record each one came from, so it is phrased the way an analyst would say it out loud.
SOURCE_QUALIFIER = {
    "text": "named in reports",
    "OpenSanctions": "watchlist",
    "ICIJ": "offshore leaks",
    "eCourts": "court record",
    "GLEIF": "company registry",
    "wanted-list": "wanted notice",
    "address-fold": "address",
}


def _qualifier(source: str | None) -> str | None:
    if not source:
        return None
    return SOURCE_QUALIFIER.get(source, str(source))


class EntityResolver:
    def __init__(self, db: Session):
        self.db = db
        self.by_key: dict[tuple[str, str], Entity] = {}
        self.alias_index: dict[str, list[Entity]] = {}  # lowercase alias -> entities
        self.person_labels: dict[str, Entity] = {}  # label -> entity (for fuzzy)
        self.new_entities = 0
        self.rejected = 0  # mentions refused by quality.is_junk
        self.merges = 0
        self._load()

    def _load(self):
        for e in self.db.query(Entity).all():
            self._index(e)

    def _index(self, e: Entity):
        self.by_key[(e.type, e.canonical_key)] = e
        if e.type == PERSON:
            self.person_labels[e.label] = e
            for a in e.aliases or []:
                self.alias_index.setdefault(a.lower(), []).append(e)

    # ------------------------------------------------------------------ public
    def known_person_names(self) -> list[str]:
        # single-token labels/aliases ("Kumar", "Bhai") are too ambiguous for dictionary matching
        names = [n for n in self.person_labels if " " in n.strip()]
        for a, ents in self.alias_index.items():
            if len(ents) == 1 and (" " in a.strip() or len(a) >= 9):
                names.append(ents[0].aliases[[x.lower() for x in ents[0].aliases].index(a)])
        return names

    def known_org_names(self) -> list[str]:
        return [e.label for (t, _), e in self.by_key.items() if t == ORGANIZATION]

    def resolve(self, etype: str, text: str, attrs: dict | None = None, seen: datetime | None = None,
                aliases: list[str] | None = None, discriminator: str | None = None) -> Entity:
        """Resolve a mention to an entity.

        `discriminator` (e.g. "address") names an attribute that must agree for a same-name match:
        two KYC records "Meena D'Souza / Vasco" and "Meena D'Souza / Chembur" become distinct persons.
        """
        attrs = dict(attrs or {})
        rejected, why = is_junk(etype, text)
        if rejected:
            raise JunkMention(etype, text, why)
        key = canonical_key(etype, text)
        if not key:
            raise ValueError(f"empty key for {etype}:{text!r}")
        ent = self.by_key.get((etype, key))
        # "Rajiv Singh" in the ICIJ leaks and "Rajiv Singh" on an INTERPOL notice are not the same man
        # by name alone: two-token names from different structured sources split into namesakes, and
        # only screening (with score and strength recorded) may relate them.
        if (ent is not None and etype == PERSON and not discriminator and attrs.get("source") and ent.attributes.get("source")
                and ent.attributes["source"] != attrs["source"] and len([t for t in text.split() if len(t) > 1]) <= 2):
            discriminator = "source"
            mine = str(attrs[discriminator]).strip().lower()
            theirs = str(ent.attributes.get(discriminator) or "").strip().lower()
            if theirs and theirs != mine:
                # look for an already-split namesake with the same discriminator, else split
                n = 2
                while True:
                    alt = self.by_key.get((etype, f"{key}#{n}"))
                    if alt is None:
                        key = f"{key}#{n}"
                        ent = None
                        break
                    if str(alt.attributes.get(discriminator) or "").strip().lower() == mine:
                        ent = alt
                        break
                    n += 1
        if ent is None and etype == PERSON:
            ent = self._resolve_person(text, key)
            # a fuzzy match never joins records across structured sources: "Rajiv Ranjan Singh" on a SEBI
            # order is not "Rajiv Singh" in the leaks. Cross-source identity is screening's job, with a score.
            if ent is not None and attrs.get("source") and ent.attributes.get("source") and ent.attributes["source"] != attrs["source"]:
                ent = None
        if ent is None and etype == LOCATION:
            ent = self._resolve_location(text, key)
        if ent is None:
            label = self._display_label(etype, text)
            if "#" in key:
                label = f"{label} ({_qualifier(attrs.get('source')) or key.rsplit('#', 1)[1]})"
            ent = Entity(id=str(uuid.uuid4()), type=etype, label=label, canonical_key=key,
                         aliases=[], attributes={}, mention_count=0, first_seen=None, last_seen=None)
            self.db.add(ent)
            self.new_entities += 1
            self._index(ent)
        # merge attrs / aliases / temporal bounds
        changed = False
        for k, v in attrs.items():
            if v is None or v == "":
                continue
            if k not in ent.attributes or (ent.attributes.get(k) in (None, "", "Unverified") and v):
                ent.attributes = {**ent.attributes, k: v}
                changed = True
        for a in aliases or []:
            a = a.strip()
            if a and a.lower() != ent.label.lower() and a.lower() not in [x.lower() for x in ent.aliases]:
                ent.aliases = [*ent.aliases, a]
                self.alias_index.setdefault(a.lower(), []).append(ent)
                changed = True
        ent.mention_count = (ent.mention_count or 0) + 1
        if seen:
            if ent.first_seen is None or seen < ent.first_seen:
                ent.first_seen = seen
            if ent.last_seen is None or seen > ent.last_seen:
                ent.last_seen = seen
        # Standing in the record (judge / institution / authority / party). Ranking and suspicion
        # read this to keep the machinery of a case out of its list of subjects.
        role = role_of(etype, ent.label, ent.attributes)
        if role and ent.attributes.get("record_role") != role:
            ent.attributes = {**ent.attributes, "record_role": role}
            changed = True
        if changed:
            self.db.add(ent)
        return ent

    def resolve_opt(self, etype: str, text: str, attrs: dict | None = None, seen: datetime | None = None,
                    aliases: list[str] | None = None, discriminator: str | None = None) -> Entity | None:
        """`resolve` for free text that may be noise: returns None instead of raising on a junk mention."""
        try:
            return self.resolve(etype, text, attrs, seen, aliases, discriminator)
        except JunkMention:
            self.rejected += 1
            return None
        except ValueError:
            return None

    # ------------------------------------------------------------------ internals
    @staticmethod
    def _display_label(etype: str, text: str) -> str:
        if etype == PHONE:
            k = RuleNER.norm_phone(text)
            return f"+{k}" if len(k) > 10 else k
        if etype == VEHICLE:
            k = RuleNER.norm_vehicle(text)
            m = re.match(r"([A-Z]{2})(\d{1,2})([A-Z]{1,3})(\d{4})", k)
            return " ".join(m.groups()) if m else k
        if etype == PERSON:
            return re.sub(r"\s+", " ", HONORIFIC_RE.sub("", text.strip()))
        if etype == SOCIAL_HANDLE:
            return "@" + text.lower().lstrip("@")
        return re.sub(r"\s+", " ", text.strip())

    def _resolve_person(self, text: str, key: str) -> Entity | None:
        low = HONORIFIC_RE.sub("", text.strip()).lower()
        # alias lookup ("Salim Bhai", "Bhai", "DK", "Seth")
        cands = self.alias_index.get(low)
        if cands and len(cands) == 1:
            self.merges += 1
            return cands[0]
        # "X Bhai" / "X Seth" -> first-name prefix match when unambiguous
        m = re.match(r"^([a-z]+)\s+(bhai|seth|sir|saheb|sahab|anna|dada)$", low)
        if m:
            first = m.group(1)
            matches = [e for lbl, e in self.person_labels.items() if lbl.lower().split()[0] == first]
            if len(matches) == 1:
                self.merges += 1
                return matches[0]
        # fuzzy match with blocking on first letter (only multi-token names)
        if len(key.split()) >= 2 and self.person_labels:
            block = [lbl for lbl in self.person_labels if lbl and lbl[0].lower() == key[0]]
            if block:
                best = process.extractOne(key, block, scorer=fuzz.token_set_ratio, processor=lambda s: canonical_key(PERSON, s))
                if best and best[1] >= settings.fuzzy_name_threshold:
                    # guard: last names must agree to avoid merging different people with same first name
                    if key.split()[-1] == canonical_key(PERSON, best[0]).split()[-1]:
                        self.merges += 1
                        return self.person_labels[best[0]]
        return None

    def _resolve_location(self, text: str, key: str) -> Entity | None:
        # "Bandra" ~ "Bandra West" style containment for short gazetteer names
        for (t, k), e in self.by_key.items():
            if t == LOCATION and (k == key or (len(key) >= 5 and (k.startswith(key + " ") or key.startswith(k + " ")))):
                return e
        return None


ENTITY_ICON = {
    PERSON: "user", PHONE: "phone", LOCATION: "map-pin", VEHICLE: "car", ORGANIZATION: "building",
    BANK_ACCOUNT: "landmark", CASE: "file-text", REPORT: "shield", SOCIAL_HANDLE: "at-sign",
}
