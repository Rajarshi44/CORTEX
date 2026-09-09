"""
Behavioural case linkage - "were these crimes committed by the same offender?"

Our network analytics answer "who is connected to whom". This answers a different and
equally important question for NCRB and the Women Safety Division: a series of unsolved
offences across different police stations may share one offender, and nobody notices
because the cases sit in different jurisdictions with no named suspect in common.

Method (standard behavioural crime-linkage practice):

    signature   0.40  the ritual detail an offender repeats because they need to, not
                      because the crime requires it - the strongest discriminator
    narrative   0.25  TF-IDF cosine similarity over the FIR text itself
    victimology 0.20  who is targeted: age band, gender, occupation, risk level
    modus       0.15  how it is done: approach, control method, weapon, scene organisation

Geography and time are reported as *context*, never as score suppressors: a travelling
offender is precisely the case that gets missed when distance is penalised.

Adapted from the team's `services/case_linkage/` (weights, victimology/MO decomposition and
the leads-not-matches framing retained); reimplemented against our Document/Entity schema,
with agglomerative series clustering and per-pair evidence explanation.

Every output is a CANDIDATE LEAD requiring corroboration. This never asserts a match, and
never names a suspect - it groups offences for a human investigator to examine.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sqlalchemy.orm import Session

from ..db import Document

# composite weights (must sum to 1.0)
W_SIGNATURE, W_NARRATIVE, W_VICTIMOLOGY, W_MO = 0.40, 0.25, 0.20, 0.15
LINK_THRESHOLD = 0.55   # below this a pair is not worth an investigator's time
STRONG_THRESHOLD = 0.72

# ------------------------------------------------------------------ behavioural vocabulary
APPROACH = {
    "con": r"\b(posing as|impersonat\w+|pretext|posed as|introduced himself|fake (?:id|identity)|befriend\w*)\b",
    "blitz": r"\b(sudden(?:ly)? attack\w*|ambush\w*|struck from behind|surprise attack)\b",
    "surprise": r"\b(lying in wait|waited for|followed her|stalk\w+|hiding)\b",
    "lure": r"\b(offered (?:a )?lift|offered (?:job|money|marriage)|enticed|lured)\b",
}
CONTROL = {
    "weapon": r"\b(knife|chaku|pistol|revolver|firearm|katta|blade|sickle|acid|iron rod)\b",
    "restraint": r"\b(tied|bound|gagged|handcuff\w*|rope|duct tape|dupatta.{0,20}(?:tied|neck))\b",
    "threat": r"\b(threat\w+|intimidat\w+|blackmail\w+|warned (?:her|him)|abusive)\b",
    "drugging": r"\b(sedat\w+|drugged|spiked|intoxicant|unconscious)\b",
}
SCENE = {
    "organised": r"\b(pre-?planned|premeditat\w+|cleaned|wiped|removed (?:cctv|sim)|no fingerprints|disposed|gloves)\b",
    "disorganised": r"\b(scattered|left behind|panick\w+|fled leaving|in haste|struggle)\b",
}
SIGNATURE = {
    "property_taken": r"\b(mobile|gold chain|mangalsutra|cash|purse|bike|jewell?ery|laptop)\b",
    "vehicle_used": r"\b(motorcycle|bike|scooter|auto[- ]?rickshaw|car|tempo|truck)\b",
    "time_night": r"\b(night|midnight|\b(?:2[0-3]|0?[0-4])[.:]\d{2}\s*(?:hrs|hours)?)\b",
    "isolated_place": r"\b(deserted|isolated|secluded|lonely (?:road|place)|vacant plot|under (?:the )?bridge|farm)\b",
    "public_transport": r"\b(local train|bus stop|railway station|platform|metro)\b",
    "victim_alone": r"\b(alone|unaccompanied|by herself|single female)\b",
    "face_covered": r"\b(mask\w*|helmet|face covered|muffler|monkey cap)\b",
    "multiple_offenders": r"\b(two|three|four|2|3|4)\s+(?:unknown\s+)?(?:persons|men|accused|youths|assailants)\b",
}
VICTIM_GENDER = {"female": r"\b(she|her|woman|lady|girl|smt\.?|mrs\.?|ms\.?|kum\.?)\b",
                 "male": r"\b(he|him|man|boy|shri|mr\.?)\b"}
RE_AGE = re.compile(r"\b(?:aged?|age)\s*(?:about\s*)?(\d{1,2})\b|\((\d{1,2})\s*(?:yrs?|years?)\)", re.I)
OCCUPATION = r"\b(student|labour\w*|worker|driver|shopkeeper|business\w*|teacher|nurse|doctor|engineer|housewife|farmer|vendor|guard|clerk)\b"

CRIME_KEYWORDS = r"\b(theft|robbery|snatch\w+|chain\s*snatch\w*|burglar\w+|dacoity|assault|molest\w+|rape|murder|" \
                 r"kidnap\w+|abduct\w+|extort\w+|cheat\w+|fraud|ndps|narcotic)\w*"


@dataclass
class CaseFeatures:
    document_id: str
    title: str
    text: str
    occurred_at: datetime | None
    station: str = ""
    crime_head: str = ""
    sections: str = ""
    lat: float | None = None
    lon: float | None = None
    approach: set[str] = field(default_factory=set)
    control: set[str] = field(default_factory=set)
    scene: set[str] = field(default_factory=set)
    signature: set[str] = field(default_factory=set)
    victim_gender: str = ""
    victim_age: int | None = None
    victim_occupation: str = ""
    crime_types: set[str] = field(default_factory=set)

    def as_dict(self) -> dict:
        return {"document_id": self.document_id, "title": self.title, "station": self.station,
                "crime_head": self.crime_head, "occurred_at": self.occurred_at.isoformat() if self.occurred_at else None,
                "approach": sorted(self.approach), "control": sorted(self.control), "scene": sorted(self.scene),
                "signature": sorted(self.signature), "victim_gender": self.victim_gender,
                "victim_age": self.victim_age, "victim_occupation": self.victim_occupation,
                "crime_types": sorted(self.crime_types)}


def _match_set(text: str, patterns: dict[str, str]) -> set[str]:
    return {k for k, p in patterns.items() if re.search(p, text, re.I)}


def extract_features(doc: Document) -> CaseFeatures:
    text = f"{doc.title}. {doc.content or ''}"
    meta = doc.meta or {}
    f = CaseFeatures(
        document_id=doc.id, title=doc.title, text=text, occurred_at=doc.occurred_at,
        station=str(meta.get("police_station") or meta.get("court") or ""),
        crime_head=str(meta.get("crime_head") or ""), sections=str(meta.get("sections") or ""),
        lat=meta.get("lat"), lon=meta.get("lon"),
    )
    f.approach = _match_set(text, APPROACH)
    f.control = _match_set(text, CONTROL)
    f.scene = _match_set(text, SCENE)
    f.signature = _match_set(text, SIGNATURE)
    f.crime_types = {m.group(0).lower() for m in re.finditer(CRIME_KEYWORDS, text, re.I)}
    counts = Counter(g for g, p in VICTIM_GENDER.items() for _ in re.finditer(p, text, re.I))
    if counts:
        f.victim_gender = counts.most_common(1)[0][0]
    am = RE_AGE.search(text)
    if am:
        f.victim_age = int(am.group(1) or am.group(2))
    om = re.search(OCCUPATION, text, re.I)
    if om:
        f.victim_occupation = om.group(1).lower()
    return f


# ------------------------------------------------------------------ similarity
def _jaccard(a: set, b: set) -> float | None:
    if not a and not b:
        return None            # no evidence either way - excluded from the average, not scored 0
    return len(a & b) / len(a | b) if (a | b) else None


def _victimology(a: CaseFeatures, b: CaseFeatures) -> tuple[float, list[str]]:
    parts, why = [], []
    if a.victim_gender and b.victim_gender:
        same = a.victim_gender == b.victim_gender
        parts.append(1.0 if same else 0.0)
        if same:
            why.append(f"both victims {a.victim_gender}")
    if a.victim_age and b.victim_age:
        gap = abs(a.victim_age - b.victim_age)
        parts.append(max(0.0, 1.0 - gap / 25.0))
        if gap <= 5:
            why.append(f"similar victim age ({a.victim_age} vs {b.victim_age})")
    if a.victim_occupation and b.victim_occupation:
        same = a.victim_occupation == b.victim_occupation
        parts.append(1.0 if same else 0.0)
        if same:
            why.append(f"both victims {a.victim_occupation}s")
    return (sum(parts) / len(parts) if parts else 0.0), why


def _modus(a: CaseFeatures, b: CaseFeatures) -> tuple[float, list[str]]:
    parts, why = [], []
    for name, sa, sb in (("approach", a.approach, b.approach), ("control", a.control, b.control),
                         ("scene organisation", a.scene, b.scene)):
        j = _jaccard(sa, sb)
        if j is not None:
            parts.append(j)
            shared = sa & sb
            if shared:
                why.append(f"shared {name}: {', '.join(sorted(shared))}")
    return (sum(parts) / len(parts) if parts else 0.0), why


def _signature(a: CaseFeatures, b: CaseFeatures) -> tuple[float, list[str]]:
    j = _jaccard(a.signature, b.signature)
    shared = a.signature & b.signature
    why = [f"repeated signature element: {s.replace('_', ' ')}" for s in sorted(shared)]
    return (j if j is not None else 0.0), why


def _haversine_km(a: CaseFeatures, b: CaseFeatures) -> float | None:
    if None in (a.lat, a.lon, b.lat, b.lon):
        return None
    R = 6371.0
    p1, p2 = math.radians(a.lat), math.radians(b.lat)
    dp, dl = math.radians(b.lat - a.lat), math.radians(b.lon - a.lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(h), math.sqrt(1 - h))


# ------------------------------------------------------------------ engine
class CaseLinkageEngine:
    """Pairwise behavioural linkage plus agglomerative grouping into candidate series."""

    def __init__(self, db: Session, source_types: tuple[str, ...] = ("FIR", "JUDGMENT", "NEWS")):
        self.db = db
        self.source_types = source_types
        self.cases: list[CaseFeatures] = []
        self._narrative: np.ndarray | None = None

    def load(self, limit: int = 400, crime_head: str | None = None) -> int:
        q = self.db.query(Document).filter(Document.source_type.in_(self.source_types))
        docs = [d for d in q.limit(limit * 3).all() if (d.content or "").strip()]
        feats = [extract_features(d) for d in docs]
        if crime_head:
            k = crime_head.lower()
            feats = [f for f in feats if k in f.crime_head.lower() or any(k in c for c in f.crime_types)]
        self.cases = feats[:limit]
        self._narrative = None
        return len(self.cases)

    def _narrative_matrix(self) -> np.ndarray:
        if self._narrative is None:
            texts = [c.text for c in self.cases] or [""]
            try:
                tfidf = TfidfVectorizer(stop_words="english", max_features=6000, ngram_range=(1, 2), min_df=1)
                m = tfidf.fit_transform(texts)
                self._narrative = (m @ m.T).toarray()
            except ValueError:  # empty vocabulary
                self._narrative = np.zeros((len(texts), len(texts)))
        return self._narrative

    def pair_score(self, i: int, j: int) -> dict:
        a, b = self.cases[i], self.cases[j]
        sig, why_sig = _signature(a, b)
        vic, why_vic = _victimology(a, b)
        mo, why_mo = _modus(a, b)
        nar = float(self._narrative_matrix()[i][j])
        score = W_SIGNATURE * sig + W_NARRATIVE * nar + W_VICTIMOLOGY * vic + W_MO * mo

        reasons = why_sig + why_mo + why_vic
        if nar >= 0.35:
            reasons.append(f"narrative wording overlaps strongly (cosine {nar:.2f})")
        shared_crime = a.crime_types & b.crime_types
        if shared_crime:
            reasons.append(f"same offence type: {', '.join(sorted(shared_crime)[:3])}")

        km = _haversine_km(a, b)
        days = abs((a.occurred_at - b.occurred_at).days) if (a.occurred_at and b.occurred_at) else None
        context = {"distance_km": round(km, 1) if km is not None else None, "days_apart": days,
                   "same_station": bool(a.station and a.station == b.station),
                   "cross_jurisdiction": bool(a.station and b.station and a.station != b.station)}
        if context["cross_jurisdiction"]:
            reasons.append(f"different police stations ({a.station} vs {b.station}) - would not surface in either file alone")

        return {"a": a.document_id, "b": b.document_id, "a_title": a.title, "b_title": b.title,
                "score": round(score, 4), "strength": "strong" if score >= STRONG_THRESHOLD else "moderate",
                "components": {"signature": round(sig, 3), "narrative": round(nar, 3),
                               "victimology": round(vic, 3), "modus_operandi": round(mo, 3)},
                "weights": {"signature": W_SIGNATURE, "narrative": W_NARRATIVE,
                            "victimology": W_VICTIMOLOGY, "modus_operandi": W_MO},
                "reasons": reasons, "context": context}

    def candidate_links(self, threshold: float = LINK_THRESHOLD, top: int = 60) -> list[dict]:
        n = len(self.cases)
        if n < 2:
            return []
        self._narrative_matrix()
        out = [p for i in range(n) for j in range(i + 1, n)
               if (p := self.pair_score(i, j))["score"] >= threshold]
        out.sort(key=lambda p: -p["score"])
        return out[:top]

    def series(self, threshold: float = LINK_THRESHOLD, min_size: int = 2) -> list[dict]:
        """Group linked pairs into candidate series (connected components over the link graph)."""
        import networkx as nx

        links = self.candidate_links(threshold, top=10_000)
        G = nx.Graph()
        G.add_nodes_from(range(len(self.cases)))
        idx = {c.document_id: i for i, c in enumerate(self.cases)}
        for p in links:
            G.add_edge(idx[p["a"]], idx[p["b"]], weight=p["score"])
        out = []
        for comp in nx.connected_components(G):
            if len(comp) < min_size:
                continue
            members = [self.cases[i] for i in sorted(comp)]
            sub = G.subgraph(comp)
            cohesion = float(np.mean([d["weight"] for _, _, d in sub.edges(data=True)])) if sub.number_of_edges() else 0.0
            sig = Counter(s for m in members for s in m.signature)
            common_sig = [s for s, c in sig.items() if c == len(members)]
            dates = sorted([m.occurred_at for m in members if m.occurred_at])
            stations = sorted({m.station for m in members if m.station})
            out.append({
                "size": len(members), "cohesion": round(cohesion, 4),
                "members": [{"document_id": m.document_id, "title": m.title, "station": m.station,
                             "occurred_at": m.occurred_at.isoformat() if m.occurred_at else None} for m in members],
                "common_signature": sorted(common_sig),
                "recurring_signature": [s for s, c in sig.most_common(6)],
                "stations": stations, "cross_jurisdiction": len(stations) > 1,
                "first_offence": dates[0].isoformat() if dates else None,
                "last_offence": dates[-1].isoformat() if dates else None,
                "span_days": (dates[-1] - dates[0]).days if len(dates) > 1 else None,
                "crime_types": sorted({c for m in members for c in m.crime_types}),
                "assessment": ("candidate series - consistent behavioural signature across cases"
                               if cohesion >= STRONG_THRESHOLD else
                               "possible series - review recommended, evidence is suggestive rather than conclusive"),
            })
        out.sort(key=lambda s: (-s["size"], -s["cohesion"]))
        return out

    def report(self, threshold: float = LINK_THRESHOLD) -> dict:
        links = self.candidate_links(threshold)
        series = self.series(threshold)
        return {
            "cases_analysed": len(self.cases),
            "candidate_links": len(links),
            "candidate_series": len(series),
            "cross_jurisdiction_series": sum(1 for s in series if s["cross_jurisdiction"]),
            "threshold": threshold,
            "method": {"weights": {"signature": W_SIGNATURE, "narrative": W_NARRATIVE,
                                   "victimology": W_VICTIMOLOGY, "modus_operandi": W_MO},
                       "note": "geography and time are reported as context only and never reduce a score - "
                               "a travelling offender is exactly the case that distance penalties hide"},
            "disclaimer": "CANDIDATE LEADS ONLY. These are behavioural similarities for an investigator to "
                          "examine, not identifications. No suspect is named or implied by this analysis.",
            "series": series[:20], "links": links[:40],
        }
