"""
Rule-based Named Entity + Relation extraction tuned for Indian law-enforcement text
(FIR narratives, intel notes, surveillance observations, social posts).

Design goals:
  * Deterministic and explainable - every mention carries the exact text span.
  * Indian context - mobile numbers, vehicle registrations (MH 04 JK 2211), IFSC, UPI,
    honorifics (Shri/Smt), 'r/o' (resident of), '@' aliases, 'u/s' legal sections.
  * Gazetteer-aware - known locations and previously resolved person names boost recall.
  * Optionally augmented by an LLM extractor (see app/ai/llm.py); the rules always run.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

# ----------------------------------------------------------------------------- types
PERSON = "PERSON"
PHONE = "PHONE"
LOCATION = "LOCATION"
VEHICLE = "VEHICLE"
ORGANIZATION = "ORGANIZATION"
BANK_ACCOUNT = "BANK_ACCOUNT"
CASE = "CASE"
REPORT = "REPORT"
SOCIAL_HANDLE = "SOCIAL_HANDLE"
GOV_ID = "GOV_ID"  # Aadhaar / PAN / GSTIN / passport / voter ID / DL - checksum validated, masked
CRYPTO_WALLET = "CRYPTO_WALLET"  # on-chain address; a value-bearing account the banking system cannot see

ENTITY_TYPES = [PERSON, PHONE, LOCATION, VEHICLE, ORGANIZATION, BANK_ACCOUNT, CRYPTO_WALLET, CASE, REPORT,
                SOCIAL_HANDLE, GOV_ID]


@dataclass
class Mention:
    type: str
    text: str
    start: int
    end: int
    confidence: float = 0.9
    attrs: dict = field(default_factory=dict)

    @property
    def key(self) -> tuple[str, str]:
        return (self.type, self.text)


@dataclass
class ExtractedRelation:
    source: Mention
    target: Mention
    rel_type: str
    confidence: float
    snippet: str
    attrs: dict = field(default_factory=dict)


@dataclass
class ExtractionResult:
    mentions: list[Mention]
    relations: list[ExtractedRelation]
    dates: list[str]
    sections: list[str]


# ----------------------------------------------------------------------------- lexicons
HONORIFICS = r"(?:Shri|Smt|Sri|Mr|Mrs|Ms|Miss|Dr|Adv|Kum|Md|Mohd|Shaikh)"
ROLE_CUES = r"(?:accused|complainant|suspect|subject|namely|one|holder|agent|proprietor|director|driver|owner|informant|witness|victim|deceased|applicant)"

ORG_SUFFIX = (
    r"(?:Pvt\.?\s+Ltd\.?|Private\s+Limited|Ltd\.?|Limited|LLP|Enterprises|Traders|Agency|Movers|Realty|Ventures|"
    r"Corporation|Corp\.?|Industries|Logistics|Exports|Imports|Group|Associates|Builders|Developers|Infra|"
    r"Bullion\s+&\s+Traders|Bank|Hospital|Foundation|Trust|Society|Co\.?|Company|Stores|Shop)"
)

NAME_STOPWORDS = {
    "police station", "anti narcotics", "narcotics cell", "crime branch", "special branch", "customs act",
    "arms act", "ndps act", "it act", "green channel", "mobile phone", "cash rs", "branch manager", "bank ghatkopar",
    "superintendent of", "directorate of", "enforcement directorate", "hotel sea", "sea breeze", "sky residency",
    "site office", "gate", "cctv", "call records", "the", "on", "at", "during", "accused", "complainant",
    "reference", "investigation", "inquiry", "efforts", "subsequent", "source reporting", "advance intelligence",
    "chor bazaar", "rahnal village", "godown no", "table", "night out", "good morning", "family time", "weekend vibes",
    "cricket tonight", "monday blues", "new bike", "new life", "best vada", "vada pav", "proud investor", "dinner at",
    "zonal office", "voter id", "mumbai zonal", "local train", "bank official", "kurla nights", "kurla station",
    "jebel ali", "mumbra bypass", "dubai", "uae", "pune", "mumbai", "india", "unit", "table 12",
}

COMMON_FIRST = set("""aarav vivaan aditya sai arjun rohan karan nikhil rahul amit vijay sanjay manoj prakash ganesh santosh
dinesh rajesh sachin mahesh suresh ramesh naresh umesh pravin nitin sunita anjali pooja neha kavita sneha priyanka
deepika shweta rekha meena asha usha lata farhan irfan zubair nadeem sameer tariq junaid shabana nazia ayesha fatima
joseph michael peter francis savio melwyn gurpreet harpreet simran rafiq salim vikram anthony imran sunil deepak ravi
anita mohd suresh priya rakesh kiran nilesh abdul abu ramesh dinesh bunty raju vinod ashok kishor kamlesh jitendra
mukesh hemant rohit ajay pankaj yogesh sandeep prashant vishal amol nilesh rupesh mangesh swapnil tushar mayur
mohammed mohammad ahmed ali hasan hussain yusuf ibrahim salman arbaaz aslam imtiaz javed shakeel wasim akram
rahim karim hamza laxmi seema geeta sunil""".split())

COMMON_LAST = set("""sharma verma patil jadhav more kadam pawar shinde deshmukh kulkarni joshi bhosale gaikwad chavan
salunkhe kamble sawant rane naik mhatre khan shaikh sheikh ansari qureshi siddiqui sayed pathan memon fernandes d'souza
dsouza pereira gomes rodrigues singh kaur gupta agarwal jain mehta shah yadav mishra tiwari dubey pandey reddy nair
menon iyer pillai kumar farhan rathod tambe mane bhoir karim hamza hussain ahmed ali sheikh""".split())

# ----------------------------------------------------------------------------- regexes
RE_PHONE = re.compile(
    r"(?<![\d/])(?:\+?91[\-\s]?|0)?([6-9]\d{4}[\-\s]?\d{5})(?!\d)"  # Indian mobiles with optional +91/0
    r"|(?<!\d)\+?(971\s?\d{2}\s?\d{3}\s?\d{4})(?!\d)"  # UAE numbers (common in intel)
)
RE_VEHICLE = re.compile(r"\b([A-Z]{2})[\s\-]?(\d{1,2})[\s\-]?([A-Z]{1,3})[\s\-]?(\d{4})\b")
RE_IFSC = re.compile(r"\b([A-Z]{4}0[A-Z0-9]{6})\b")
RE_ACCOUNT = re.compile(r"(?:A/c|Account|Acct|Acc)\.?\s*(?:No\.?|Number)?\s*:?\s*(\d{9,18})\b", re.I)
RE_UPI = re.compile(r"\b([a-z0-9.\-_]{3,}@(?:ybl|okaxis|oksbi|okhdfcbank|okicici|paytm|upi|axl|ibl|apl))\b", re.I)
RE_HANDLE = re.compile(r"(?<![\w@])@([A-Za-z0-9_.]{3,30})\b")
RE_DATE = re.compile(
    r"\b(\d{1,2}[/\-]\d{1,2}[/\-]\d{4})\b|\b(\d{4}-\d{2}-\d{2})\b|"
    r"\b(\d{1,2}(?:st|nd|rd|th)?\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?,?\s+\d{4})\b"
)
RE_SECTION = re.compile(
    r"\b(?:u/s|under section|sec\.?|section)\s+([\dA-Za-z\(\)\.,/&\s\-]+?\s*(?:IPC|NDPS Act|Arms Act|Customs Act|PMLA|IT Act|BNS|BNSS|MCOCA|UAPA|Excise Act))",
    re.I,
)
RE_ORG = re.compile(r"\b((?:[A-Z][A-Za-z&']+\s+){1,4}" + ORG_SUFFIX + r")(?![A-Za-z])")
RE_ALIAS = re.compile(r"(?<!['\w])((?:[A-Z][A-Za-z']*[a-z]\s+){1,2}[A-Z][A-Za-z']*[a-z])\s*(?:@|alias|@\s)\s*((?:[A-Z][A-Za-z']*[A-Za-z]\s?){1,3})(?=\s*(?:r/o|,|\.|\(|of|age|was|is|seen|met|were|\)|$))")
RE_ALIAS_QUOTE = re.compile(r"'([A-Z][A-Za-z ]{1,20})'")
RE_HONORIFIC_NAME = re.compile(HONORIFICS + r"\.?\s+((?:[A-Z][A-Za-z']*[a-z]\s+){0,2}[A-Z][A-Za-z']*[a-z])")
RE_ROLE_NAME = re.compile(r"\b" + ROLE_CUES + r"\s+((?:[A-Z][A-Za-z']*[a-z]\s+){1,2}[A-Z][A-Za-z']*[a-z])\b")
RE_RO_LOCATION = re.compile(r"\br/o\s+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)?)")
RE_CAP_NAME = re.compile(r"\b([A-Z][A-Za-z']*[a-z](?:\s+[A-Z][A-Za-z']*[a-z]){1,2})\b")
RE_AGE = re.compile(r"\(age\s+(\d{1,2})\)")


def _load_gazetteer() -> dict[str, dict]:
    p = Path(__file__).resolve().parent.parent.parent / "data" / "samples" / "gazetteer.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


class RuleNER:
    def __init__(self, gazetteer: dict[str, dict] | None = None):
        self.gazetteer = gazetteer if gazetteer is not None else _load_gazetteer()
        self._gaz_re = self._build_gaz_re()
        self.known_persons: dict[str, str] = {}  # lowercase mention -> canonical label
        self.known_orgs: dict[str, str] = {}
        self._known_re: re.Pattern | None = None

    # ----------------------------------------------------------------- setup
    def _build_gaz_re(self) -> re.Pattern | None:
        if not self.gazetteer:
            return None
        names = sorted(self.gazetteer, key=len, reverse=True)
        return re.compile(r"\b(" + "|".join(re.escape(n) for n in names) + r")\b", re.I)

    def add_location(self, name: str, lat: float | None = None, lon: float | None = None):
        if name not in self.gazetteer:
            self.gazetteer[name] = {"lat": lat, "lon": lon}
            self._gaz_re = self._build_gaz_re()

    def set_known(self, persons: Iterable[str], orgs: Iterable[str] = ()):
        """Dictionary matching against already-known entities (from structured sources / prior docs)."""
        self.known_persons = {p.lower(): p for p in persons if p and len(p) >= 4}
        self.known_orgs = {o.lower(): o for o in orgs if o and len(o) >= 4}
        alls = sorted(list(self.known_persons) + list(self.known_orgs), key=len, reverse=True)
        self._known_re = re.compile(r"\b(" + "|".join(re.escape(a) for a in alls) + r")\b", re.I) if alls else None

    # ----------------------------------------------------------------- helpers
    @staticmethod
    def norm_phone(raw: str) -> str:
        d = re.sub(r"\D", "", raw)
        if len(d) == 10 and d[0] in "6789":
            return d
        if len(d) == 11 and d.startswith("0"):
            return d[1:]
        if len(d) == 12 and d.startswith("91"):
            return d[2:]
        return d  # international

    @staticmethod
    def norm_vehicle(raw: str) -> str:
        return re.sub(r"[\s\-]", "", raw.upper())

    @staticmethod
    def clean_name(raw: str) -> str:
        n = re.sub(r"\s+", " ", raw.strip(" .,;:'\""))
        n = re.sub(r"^(?:Shri|Smt|Sri|Mr|Mrs|Ms|Miss|Dr|Adv|Kum)\.?\s+", "", n)
        n = re.sub(r"^(?:Accused|Complainant|Suspect|Subject|One|Namely|Holder|Agent|Director|Driver|Owner|Witness|Victim|Applicant|Informant)\s+", "", n, flags=re.I)
        return n

    def _looks_like_name(self, text: str) -> bool:
        t = text.lower()
        if t in NAME_STOPWORDS or any(t.startswith(s) or t.endswith(s) for s in NAME_STOPWORDS if " " in s):
            return False
        if t in self.known_persons:
            return True
        toks = t.split()
        if len(toks) < 2 or len(toks) > 3:
            return False
        if any(tok in self.gazetteer_lower for tok in toks) and toks[-1] in self.gazetteer_lower:
            return False
        first, last = toks[0], toks[-1]
        return first in COMMON_FIRST or last in COMMON_LAST or first.rstrip(".") in {"mohd", "md", "syed"}

    @property
    def gazetteer_lower(self) -> set[str]:
        return {g.lower() for g in self.gazetteer}

    # ----------------------------------------------------------------- main
    def extract(self, text: str) -> ExtractionResult:
        mentions: list[Mention] = []
        taken: list[tuple[int, int]] = []

        def add(m: Mention) -> Mention | None:
            for s, e in taken:
                if m.start < e and m.end > s:  # overlap -> keep earlier (higher precision) mention
                    return None
            taken.append((m.start, m.end))
            mentions.append(m)
            return m

        # 1. High-precision structured patterns first
        for m in RE_VEHICLE.finditer(text):
            add(Mention(VEHICLE, self.norm_vehicle(m.group(0)), m.start(), m.end(), 0.98, {"raw": m.group(0)}))
        for m in RE_PHONE.finditer(text):
            raw = m.group(0)
            num = self.norm_phone(raw)
            if len(num) >= 10:
                add(Mention(PHONE, num, m.start(), m.end(), 0.98, {"raw": raw, "international": len(num) > 10}))
        for m in RE_ACCOUNT.finditer(text):
            add(Mention(BANK_ACCOUNT, m.group(1), m.start(), m.end(), 0.95))
        for m in RE_UPI.finditer(text):
            add(Mention(BANK_ACCOUNT, m.group(1).lower(), m.start(), m.end(), 0.9, {"upi": True}))
        for m in RE_HANDLE.finditer(text):
            add(Mention(SOCIAL_HANDLE, "@" + m.group(1).lower(), m.start(), m.end(), 0.9))

        # 2. Organizations (before names, since org names contain capitalised words)
        for m in RE_ORG.finditer(text):
            name = m.group(1).strip()
            if name.lower().startswith(("the ", "of ", "at ", "by ", "and ")):
                name = name.split(" ", 1)[1]
            name = name.rstrip(".")
            if len(name.split()) >= 2:
                add(Mention(ORGANIZATION, name, m.start(1), m.end(1), 0.85))

        # 3. Persons: alias pattern -> honorific -> role cue -> known dictionary -> generic capitalised
        for m in RE_ALIAS.finditer(text):
            name, alias = self.clean_name(m.group(1)), m.group(2).strip()
            if self._looks_like_name(name) or name.lower() in self.known_persons:
                mm = add(Mention(PERSON, name, m.start(1), m.end(1), 0.95, {"alias": alias}))
                if mm is None:  # already captured by another pattern; still record alias
                    for x in mentions:
                        if x.type == PERSON and x.text == name:
                            x.attrs["alias"] = alias
        for m in RE_HONORIFIC_NAME.finditer(text):
            name = self.clean_name(m.group(1))
            if self._looks_like_name(name):
                add(Mention(PERSON, name, m.start(1), m.end(1), 0.9))
        for m in RE_ROLE_NAME.finditer(text):
            name = self.clean_name(m.group(1))
            role = m.group(0).split()[0].lower()
            if self._looks_like_name(name):
                mm = add(Mention(PERSON, name, m.start(1), m.end(1), 0.9, {"role": role}))
                if mm is None:
                    for x in mentions:
                        if x.type == PERSON and x.text == name and "role" not in x.attrs:
                            x.attrs["role"] = role
        if self._known_re:
            for m in self._known_re.finditer(text):
                key = m.group(1).lower()
                if key in self.known_persons:
                    add(Mention(PERSON, self.known_persons[key], m.start(), m.end(), 0.92, {"dictionary": True}))
                elif key in self.known_orgs:
                    add(Mention(ORGANIZATION, self.known_orgs[key], m.start(), m.end(), 0.92, {"dictionary": True}))
        for m in RE_CAP_NAME.finditer(text):
            name = self.clean_name(m.group(1))
            if self._looks_like_name(name):
                off = m.group(1).find(name)
                add(Mention(PERSON, name, m.start(1) + off, m.start(1) + off + len(name), 0.7))

        # 4. Locations: r/o pattern + gazetteer
        for m in RE_RO_LOCATION.finditer(text):
            add(Mention(LOCATION, self._canon_loc(m.group(1)), m.start(1), m.end(1), 0.9, {"residence": True}))
        if self._gaz_re:
            for m in self._gaz_re.finditer(text):
                add(Mention(LOCATION, self._canon_loc(m.group(1)), m.start(), m.end(), 0.9))
        for m in re.finditer(r"\b(Hotel\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?|Godown\s+No\.?\s*\d+[^,.]*|[A-Z][a-z]+\s+(?:Restaurant|Lounge|Bar|Mall|Station))\b", text):
            add(Mention(LOCATION, m.group(1).strip(), m.start(1), m.end(1), 0.8, {"venue": True}))

        # 5. Age attribute attach
        for m in RE_AGE.finditer(text):
            for x in mentions:
                if x.type == PERSON and 0 <= m.start() - x.end <= 3:
                    x.attrs["age"] = int(m.group(1))

        mentions.sort(key=lambda x: x.start)
        dates = [next(g for g in m.groups() if g) for m in RE_DATE.finditer(text)]
        sections = [re.sub(r"\s+", " ", m.group(1)).strip() for m in RE_SECTION.finditer(text)]
        relations = self._infer_relations(text, mentions)
        return ExtractionResult(mentions, relations, dates, sections)

    def _canon_loc(self, raw: str) -> str:
        low = raw.strip().lower()
        for g in self.gazetteer:
            if g.lower() == low:
                return g
        return raw.strip().title() if raw.isupper() or raw.islower() else raw.strip()

    # ----------------------------------------------------------------- relations
    def _infer_relations(self, text: str, mentions: list[Mention]) -> list[ExtractedRelation]:
        rels: list[ExtractedRelation] = []
        sentences = self._sentences(text)

        def snippet(a: Mention, b: Mention) -> str:
            s, e = min(a.start, b.start), max(a.end, b.end)
            return text[max(0, s - 40): min(len(text), e + 40)].strip()

        def between(a: Mention, b: Mention) -> str:
            return text[min(a.end, b.end): max(a.start, b.start)].lower()

        for s_start, s_end in sentences:
            in_s = [m for m in mentions if m.start >= s_start and m.end <= s_end]
            persons = [m for m in in_s if m.type == PERSON]
            for i, p in enumerate(persons):
                # Person -> residence
                for loc in (m for m in in_s if m.type == LOCATION and m.attrs.get("residence")):
                    if 0 <= loc.start - p.end <= 12 and "r/o" in text[p.end: loc.start]:
                        rels.append(ExtractedRelation(p, loc, "RESIDES_AT", 0.95, snippet(p, loc)))
                # Person -> phone (same sentence, within 120 chars, phone after person)
                for ph in (m for m in in_s if m.type == PHONE):
                    gap = ph.start - p.end
                    if 0 <= gap <= 120 and not any(o.type == PERSON and p.end < o.start < ph.start for o in in_s):
                        rels.append(ExtractedRelation(p, ph, "USES_PHONE", 0.85, snippet(p, ph)))
                # Person -> vehicle
                for v in (m for m in in_s if m.type == VEHICLE):
                    mid = between(p, v)
                    conf = 0.9 if re.search(r"(riding|driving|arrived in|owned by|his|her|bearing|wheel)", mid) else 0.6
                    if abs(v.start - p.end) <= 220:
                        rels.append(ExtractedRelation(p, v, "ASSOCIATED_VEHICLE", conf, snippet(p, v)))
                # Person -> organization
                for o in (m for m in in_s if m.type == ORGANIZATION):
                    mid = between(p, o)
                    strong = re.search(r"(proprietor|director|owner|promoted by|promoter|partner)", mid)
                    if (strong and abs(o.start - p.end) <= 90) or (re.search(r"^(?:\s*,|\s+of\s+)\s*$", mid) and abs(o.start - p.end) <= 30):
                        rt = "DIRECTOR_OF" if "director" in mid else "OWNS" if re.search(r"proprietor|owner|promot", mid) else "AFFILIATED_WITH"
                        rels.append(ExtractedRelation(p, o, rt, 0.8 if rt != "AFFILIATED_WITH" else 0.6, snippet(p, o)))
                    elif o.end <= p.start and re.search(r"\(\s*$", text[o.end: p.start]) or (0 < p.start - o.end <= 3 and text[o.end:p.start].strip() == "("):
                        rels.append(ExtractedRelation(p, o, "AFFILIATED_WITH", 0.7, snippet(p, o)))
                # Person <-> person co-occurrence, with verb-cue typing
                for j, q in enumerate(persons[i + 1:]):
                    mid = between(p, q)
                    if j > 0 or q.text == p.text:  # only adjacent, distinct persons get typed relations
                        if q.text != p.text:
                            rels.append(ExtractedRelation(p, q, "MENTIONED_WITH", 0.4, snippet(p, q)))
                        continue
                    if re.search(r"\b(met|meeting|along with|together with|with|accompanied)\b", mid) and len(mid) < 90:
                        rels.append(ExtractedRelation(p, q, "MET", 0.85, snippet(p, q)))
                    elif re.search(r"\b(instructions of|on behalf of|lieutenant|handler|controlled by|reports to|works for|lent .* to)\b", mid):
                        rels.append(ExtractedRelation(p, q, "REPORTS_TO", 0.8, snippet(p, q)))
                    elif re.search(r"\b(contact|calls?|chats? with|frequent)\b", mid) and len(mid) < 120:
                        rels.append(ExtractedRelation(p, q, "COMMUNICATED_WITH", 0.7, snippet(p, q)))
                    else:
                        rels.append(ExtractedRelation(p, q, "MENTIONED_WITH", 0.5, snippet(p, q)))
            # Vehicle -> organization ownership
            for v in (m for m in in_s if m.type == VEHICLE):
                for o in (m for m in in_s if m.type == ORGANIZATION):
                    mid = between(v, o)
                    if re.search(r"(owned by|of|labels of|belonging to)", mid) and abs(o.start - v.end) <= 60:
                        rels.append(ExtractedRelation(v, o, "OWNED_BY", 0.85, snippet(v, o)))
            # Person/vehicle seen at venue-type location (non-residence)
            for loc in (m for m in in_s if m.type == LOCATION and not m.attrs.get("residence")):
                for p in persons:
                    mid = between(p, loc)
                    if re.search(r"\b(at|near|in|entering|visited|hosted|seen)\b", mid) and abs(loc.start - p.end) <= 100:
                        rels.append(ExtractedRelation(p, loc, "SEEN_AT", 0.7, snippet(p, loc)))
            # Organization -> location
            for o in (m for m in in_s if m.type == ORGANIZATION):
                for loc in (m for m in in_s if m.type == LOCATION):
                    if 0 < loc.start - o.end <= 4 and text[o.end:loc.start].strip() == ",":
                        rels.append(ExtractedRelation(o, loc, "LOCATED_AT", 0.85, snippet(o, loc)))
        # de-duplicate (keep highest confidence per pair/type)
        best: dict[tuple, ExtractedRelation] = {}
        for r in rels:
            k = (r.source.type, r.source.text, r.target.type, r.target.text, r.rel_type)
            if k not in best or best[k].confidence < r.confidence:
                best[k] = r
        return list(best.values())

    @staticmethod
    def _sentences(text: str) -> list[tuple[int, int]]:
        abbrev = {"no", "rs", "sr", "dr", "mr", "mrs", "smt", "shri", "approx", "pvt", "ltd", "st", "jr", "vs", "etc", "u/s", "reg", "regn", "mob", "tel", "ph"}
        spans, start = [], 0
        for m in re.finditer(r"\.\s+(?=[A-Z])", text):
            prev = re.search(r"([\w/]+)\.$", text[: m.start() + 1])
            if prev and prev.group(1).lower() in abbrev:
                continue
            spans.append((start, m.end()))
            start = m.end()
        spans.append((start, len(text)))
        return spans
