"""
Statutory charges: turning "u/s 302, 34 IPC" into something the graph can reason about.

The rule extractor already finds section citations and hands them back as raw strings, which the
pipeline filed as an attribute on the case. An attribute cannot be searched, ranked or joined: you
could read the sections on one FIR but you could not ask *who else on this sheet is booked under
NDPS 21(c)*, and a murder charge counted for exactly as much as a common-intention clause.

This module parses a citation into a `Charge`, gives it a canonical key, and attaches two things the
citation itself does not carry:

  category   what kind of offence it is (homicide, narcotics, sexual offence, ...), so a corpus can
             be summarised by what people are accused of rather than by section number.
  gravity    0-1, how serious the offence is. Feeds suspicion scoring, so being named in a murder
             case outweighs being named in a hurt case instead of both counting as "accused: 1".

Three honesty constraints, because a wrong number here becomes a wrong ranking:

  1. The gravity table is curated, not exhaustive. A section that is not in it falls back to its
     act's default and says so in `gravity_basis`, so a reader can tell a researched number from a
     placeholder.
  2. Modes of liability are not offences. IPC 34 (common intention), 149 (common object) and BNS
     3(5) attach liability for someone else's act and carry near-zero gravity of their own. Scoring
     them like substantive offences would have made every co-accused in a riot look like a
     principal.
  3. The IPC-to-BNS bridge is a curated subset of the well-known correspondences, offered as a
     navigation aid so a search for murder finds cases charged under either code. It is not a
     complete or authoritative concordance and is not legal advice.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# --------------------------------------------------------------------------------- acts
# Surface forms seen in Indian police and court text -> canonical act code. Order matters: the
# longest, most specific pattern is tried first so "BNSS" is never read as "BNS".
ACT_PATTERNS: list[tuple[str, str]] = [
    (r"bharatiya\s+nagarik\s+suraksha\s+sanhita|bnss", "BNSS"),
    (r"bharatiya\s+nyaya\s+sanhita|bns", "BNS"),
    (r"bharatiya\s+sakshya\s+adhiniyam|bsa", "BSA"),
    (r"indian\s+penal\s+code|i\.?p\.?c\.?", "IPC"),
    (r"code\s+of\s+criminal\s+procedure|cr\.?p\.?c\.?", "CRPC"),
    (r"n\.?d\.?p\.?s\.?(?:\s+act)?|narcotic\s+drugs", "NDPS"),
    (r"u\.?a\.?p\.?a\.?|unlawful\s+activities", "UAPA"),
    (r"m\.?c\.?o\.?c\.?a\.?|maharashtra\s+control\s+of\s+organised\s+crime", "MCOCA"),
    (r"p\.?m\.?l\.?a\.?|prevention\s+of\s+money\s+laundering", "PMLA"),
    (r"p\.?o\.?c\.?s\.?o\.?|protection\s+of\s+children\s+from\s+sexual\s+offences", "POCSO"),
    (r"dowry\s+prohibition", "DOWRY"),
    (r"immoral\s+traffic|i\.?t\.?p\.?a\.?", "ITPA"),
    (r"protection\s+of\s+women\s+from\s+domestic\s+violence|domestic\s+violence", "DV"),
    (r"arms\s+act", "ARMS"),
    (r"explosive\s+substances?(?:\s+act)?", "EXPLOSIVES"),
    (r"information\s+technology\s+act|i\.?t\.?\s+act", "IT"),
    (r"customs\s+act", "CUSTOMS"),
    (r"excise\s+act", "EXCISE"),
    (r"prevention\s+of\s+corruption|p\.?c\.?\s+act", "PC"),
    (r"juvenile\s+justice|j\.?j\.?\s+act", "JJ"),
    (r"gambling\s+act", "GAMBLING"),
    (r"motor\s+vehicles?\s+act|m\.?v\.?\s+act", "MV"),
]
ACT_RE = [(re.compile(rf"\b(?:{pat})\b", re.I), code) for pat, code in ACT_PATTERNS]

ACT_NAMES: dict[str, str] = {
    "IPC": "Indian Penal Code", "BNS": "Bharatiya Nyaya Sanhita", "BNSS": "Bharatiya Nagarik Suraksha Sanhita",
    "BSA": "Bharatiya Sakshya Adhiniyam", "CRPC": "Code of Criminal Procedure", "NDPS": "NDPS Act",
    "UAPA": "UAPA", "MCOCA": "MCOCA", "PMLA": "PMLA", "POCSO": "POCSO Act",
    "DOWRY": "Dowry Prohibition Act", "ITPA": "Immoral Traffic (Prevention) Act",
    "DV": "Protection of Women from Domestic Violence Act", "ARMS": "Arms Act",
    "EXPLOSIVES": "Explosive Substances Act", "IT": "IT Act", "CUSTOMS": "Customs Act",
    "EXCISE": "Excise Act", "PC": "Prevention of Corruption Act", "JJ": "Juvenile Justice Act",
    "GAMBLING": "Gambling Act", "MV": "Motor Vehicles Act",
}

# Per-act fallback when a section is not in the curated table. A number here says "an offence under
# this act is typically about this serious", nothing more precise.
ACT_DEFAULT_GRAVITY: dict[str, float] = {
    "IPC": 0.45, "BNS": 0.45, "NDPS": 0.70, "UAPA": 0.95, "MCOCA": 0.90, "PMLA": 0.80,
    "POCSO": 0.95, "DOWRY": 0.60, "ITPA": 0.75, "DV": 0.50, "ARMS": 0.65, "EXPLOSIVES": 0.85,
    "IT": 0.50, "CUSTOMS": 0.60, "EXCISE": 0.35, "PC": 0.65, "JJ": 0.40, "GAMBLING": 0.25,
    "MV": 0.15, "BNSS": 0.0, "CRPC": 0.0, "BSA": 0.0,  # procedural codes charge nobody with anything
}
ACT_DEFAULT_CATEGORY: dict[str, str] = {
    "NDPS": "narcotics", "UAPA": "terror", "MCOCA": "organised crime", "PMLA": "economic",
    "POCSO": "sexual offence", "DOWRY": "offence against women", "ITPA": "trafficking",
    "DV": "offence against women", "ARMS": "arms", "EXPLOSIVES": "arms", "IT": "cyber",
    "CUSTOMS": "economic", "EXCISE": "excise", "PC": "corruption", "JJ": "juvenile",
    "GAMBLING": "public order", "MV": "traffic", "BNSS": "procedure", "CRPC": "procedure", "BSA": "procedure",
}

# --------------------------------------------------------------------------------- sections
# (offence, category, gravity). Curated: the sections that actually recur in Indian police records.
# Anything absent falls back to its act's default and is flagged as such.
SECTIONS: dict[str, tuple[str, str, float]] = {
    # --- IPC, substantive
    "IPC:302": ("Murder", "homicide", 1.00),
    "IPC:304": ("Culpable homicide not amounting to murder", "homicide", 0.85),
    "IPC:304A": ("Death by negligence", "homicide", 0.55),
    "IPC:304B": ("Dowry death", "offence against women", 0.90),
    "IPC:305": ("Abetment of suicide of a child", "homicide", 0.90),
    "IPC:306": ("Abetment of suicide", "homicide", 0.70),
    "IPC:307": ("Attempt to murder", "homicide", 0.90),
    "IPC:308": ("Attempt to commit culpable homicide", "homicide", 0.70),
    "IPC:323": ("Voluntarily causing hurt", "hurt", 0.30),
    "IPC:324": ("Hurt by dangerous weapon", "hurt", 0.50),
    "IPC:325": ("Grievous hurt", "hurt", 0.60),
    "IPC:326": ("Grievous hurt by dangerous weapon", "hurt", 0.70),
    "IPC:326A": ("Acid attack", "offence against women", 0.95),
    "IPC:354": ("Assault on a woman with intent to outrage modesty", "offence against women", 0.70),
    "IPC:354A": ("Sexual harassment", "offence against women", 0.65),
    "IPC:354D": ("Stalking", "offence against women", 0.60),
    "IPC:363": ("Kidnapping", "kidnapping", 0.70),
    "IPC:364": ("Kidnapping in order to murder", "kidnapping", 0.90),
    "IPC:365": ("Kidnapping with intent to confine", "kidnapping", 0.70),
    "IPC:366": ("Kidnapping or abducting a woman", "offence against women", 0.80),
    "IPC:370": ("Trafficking of persons", "trafficking", 0.90),
    "IPC:376": ("Rape", "sexual offence", 1.00),
    "IPC:376D": ("Gang rape", "sexual offence", 1.00),
    "IPC:379": ("Theft", "property", 0.40),
    "IPC:380": ("Theft in a dwelling", "property", 0.45),
    "IPC:384": ("Extortion", "property", 0.60),
    "IPC:392": ("Robbery", "property", 0.70),
    "IPC:395": ("Dacoity", "property", 0.85),
    "IPC:396": ("Dacoity with murder", "homicide", 1.00),
    "IPC:397": ("Robbery with attempt to cause death", "property", 0.90),
    "IPC:406": ("Criminal breach of trust", "economic", 0.50),
    "IPC:409": ("Criminal breach of trust by a public servant", "economic", 0.65),
    "IPC:411": ("Receiving stolen property", "property", 0.45),
    "IPC:420": ("Cheating", "economic", 0.50),
    "IPC:465": ("Forgery", "economic", 0.55),
    "IPC:467": ("Forgery of a valuable security", "economic", 0.65),
    "IPC:468": ("Forgery for the purpose of cheating", "economic", 0.60),
    "IPC:471": ("Using a forged document as genuine", "economic", 0.55),
    "IPC:489A": ("Counterfeiting currency notes", "economic", 0.75),
    "IPC:498A": ("Cruelty by husband or his relatives", "offence against women", 0.60),
    "IPC:504": ("Intentional insult to provoke breach of peace", "public order", 0.20),
    "IPC:506": ("Criminal intimidation", "public order", 0.45),
    "IPC:509": ("Word or gesture insulting the modesty of a woman", "offence against women", 0.45),
    "IPC:201": ("Causing disappearance of evidence", "obstruction", 0.50),
    "IPC:212": ("Harbouring an offender", "obstruction", 0.50),
    "IPC:147": ("Rioting", "public order", 0.40),
    "IPC:148": ("Rioting armed with a deadly weapon", "public order", 0.50),
    # --- IPC, modes of liability. Not offences: they attach liability for another's act.
    "IPC:34": ("Acts done in furtherance of common intention", "mode of liability", 0.05),
    "IPC:149": ("Unlawful assembly with common object", "mode of liability", 0.10),
    "IPC:120B": ("Criminal conspiracy", "mode of liability", 0.60),
    "IPC:107": ("Abetment", "mode of liability", 0.40),
    "IPC:109": ("Abetment where the act is committed", "mode of liability", 0.40),

    # --- BNS (in force 1 July 2024)
    "BNS:103": ("Murder", "homicide", 1.00),
    "BNS:105": ("Culpable homicide not amounting to murder", "homicide", 0.85),
    "BNS:106": ("Death by negligence", "homicide", 0.55),
    "BNS:108": ("Abetment of suicide", "homicide", 0.70),
    "BNS:109": ("Attempt to murder", "homicide", 0.90),
    "BNS:111": ("Organised crime", "organised crime", 0.90),
    "BNS:112": ("Petty organised crime", "organised crime", 0.60),
    "BNS:113": ("Terrorist act", "terror", 1.00),
    "BNS:115": ("Voluntarily causing hurt", "hurt", 0.30),
    "BNS:117": ("Grievous hurt", "hurt", 0.60),
    "BNS:118": ("Hurt by dangerous weapon", "hurt", 0.50),
    "BNS:64": ("Rape", "sexual offence", 1.00),
    "BNS:70": ("Gang rape", "sexual offence", 1.00),
    "BNS:74": ("Assault on a woman with intent to outrage modesty", "offence against women", 0.70),
    "BNS:75": ("Sexual harassment", "offence against women", 0.65),
    "BNS:78": ("Stalking", "offence against women", 0.60),
    "BNS:79": ("Word or gesture insulting the modesty of a woman", "offence against women", 0.45),
    "BNS:80": ("Dowry death", "offence against women", 0.90),
    "BNS:85": ("Cruelty by husband or his relatives", "offence against women", 0.60),
    "BNS:137": ("Kidnapping", "kidnapping", 0.70),
    "BNS:140": ("Kidnapping or abducting in order to murder", "kidnapping", 0.90),
    "BNS:143": ("Trafficking of persons", "trafficking", 0.90),
    "BNS:303": ("Theft", "property", 0.40),
    "BNS:308": ("Extortion", "property", 0.60),
    "BNS:309": ("Robbery", "property", 0.70),
    "BNS:310": ("Dacoity", "property", 0.85),
    "BNS:316": ("Criminal breach of trust", "economic", 0.50),
    "BNS:317": ("Receiving stolen property", "property", 0.45),
    "BNS:318": ("Cheating", "economic", 0.50),
    "BNS:336": ("Forgery", "economic", 0.60),
    "BNS:338": ("Forgery of a valuable security", "economic", 0.65),
    "BNS:340": ("Using a forged document as genuine", "economic", 0.55),
    "BNS:351": ("Criminal intimidation", "public order", 0.45),
    "BNS:238": ("Causing disappearance of evidence", "obstruction", 0.50),
    "BNS:61": ("Criminal conspiracy", "mode of liability", 0.60),
    "BNS:3(5)": ("Acts done in furtherance of common intention", "mode of liability", 0.05),
    "BNS:190": ("Unlawful assembly with common object", "mode of liability", 0.10),

    # --- NDPS. Quantity drives the sentence, so the sub-clause drives the gravity.
    "NDPS:8": ("Prohibited dealing in narcotic drugs", "narcotics", 0.60),
    "NDPS:20": ("Contravention involving cannabis", "narcotics", 0.60),
    "NDPS:21": ("Contravention involving manufactured drugs", "narcotics", 0.75),
    "NDPS:21(a)": ("Manufactured drugs, small quantity", "narcotics", 0.50),
    "NDPS:21(b)": ("Manufactured drugs, intermediate quantity", "narcotics", 0.70),
    "NDPS:21(c)": ("Manufactured drugs, commercial quantity", "narcotics", 0.95),
    "NDPS:22": ("Contravention involving psychotropic substances", "narcotics", 0.75),
    "NDPS:22(c)": ("Psychotropic substances, commercial quantity", "narcotics", 0.95),
    "NDPS:25": ("Allowing premises to be used for an offence", "narcotics", 0.60),
    "NDPS:27A": ("Financing traffic and harbouring offenders", "narcotics", 0.95),
    "NDPS:29": ("Abetment and criminal conspiracy", "narcotics", 0.70),

    # --- special acts
    "UAPA:16": ("Terrorist act", "terror", 1.00),
    "UAPA:18": ("Conspiracy to commit a terrorist act", "terror", 0.90),
    "UAPA:20": ("Membership of a terrorist gang or organisation", "terror", 0.90),
    "UAPA:38": ("Association with a terrorist organisation", "terror", 0.85),
    "UAPA:39": ("Support to a terrorist organisation", "terror", 0.85),
    "MCOCA:3": ("Organised crime", "organised crime", 0.95),
    "MCOCA:4": ("Possessing unaccountable wealth from organised crime", "organised crime", 0.85),
    "PMLA:3": ("Money laundering", "economic", 0.85),
    "PMLA:4": ("Punishment for money laundering", "economic", 0.85),
    "ARMS:3": ("Acquiring arms without a licence", "arms", 0.50),
    "ARMS:25": ("Punishment for unlicensed arms", "arms", 0.70),
    "ARMS:27": ("Using arms in an offence", "arms", 0.80),
    "IT:66": ("Computer-related offences", "cyber", 0.55),
    "IT:66C": ("Identity theft", "cyber", 0.60),
    "IT:66D": ("Cheating by personation using a computer", "cyber", 0.60),
    "IT:67": ("Publishing obscene material electronically", "cyber", 0.60),
    "IT:67B": ("Child sexual abuse material", "sexual offence", 0.95),
    "CUSTOMS:135": ("Evasion of duty and smuggling", "economic", 0.70),
    "PC:7": ("Bribery by a public servant", "corruption", 0.70),
    "PC:13": ("Criminal misconduct by a public servant", "corruption", 0.70),
}

# Curated correspondences between the repealed IPC and the BNS that replaced it, so a corpus
# spanning July 2024 can be read as one. Partial by design; a pair absent here is simply not
# bridged rather than guessed at. Not an authoritative concordance.
IPC_TO_BNS: dict[str, str] = {
    "34": "3(5)", "107": "45", "120B": "61", "147": "191", "148": "191", "149": "190",
    "201": "238", "302": "103", "304": "105", "304A": "106", "304B": "80", "306": "108",
    "307": "109", "323": "115", "324": "118", "325": "117", "326": "118",
    "354": "74", "354A": "75", "354D": "78", "363": "137", "364": "140", "366": "87",
    "370": "143", "376": "64", "376D": "70", "379": "303", "380": "305", "384": "308",
    "392": "309", "395": "310", "406": "316", "409": "316", "411": "317", "420": "318",
    "465": "336", "467": "338", "468": "336", "471": "340", "498A": "85", "506": "351", "509": "79",
}
BNS_TO_IPC: dict[str, str] = {}
for _ipc, _bns in IPC_TO_BNS.items():  # first IPC section wins where several map onto one BNS section
    BNS_TO_IPC.setdefault(_bns, _ipc)

# "302", "304B", "21(c)", "3(5)". A trailing letter belongs to the section number (304B); a
# parenthesised part is the sub-clause (21(c)) and changes the offence, so it is kept separate.
TOKEN_RE = re.compile(r"^(\d{1,4})\s*([A-Z]{1,2})?\s*(?:\(\s*([0-9A-Za-z]{1,3})\s*\))?$")
# The words that introduce a citation. Stripped everywhere rather than only at the front, because
# "u/s 302 and sec 34 IPC" repeats them, and because "u/s" would otherwise be split on its own
# slash into tokens that parse as nothing - which silently dropped the first and gravest section
# of every citation written the way a police record actually writes it.
PREFIX_RE = re.compile(r"\b(?:u\s*/\s*s|under\s+sections?|sections?|secs?\.?|s\.)\s*", re.I)
# Separators between citations in one string: "302, 34", "302 & 34", "302 r/w 34", "302 and 34".
SPLIT_RE = re.compile(r"\s*(?:,|&|/|\band\b|\br/?w\b|\bread\s+with\b)\s*", re.I)

MODE_OF_LIABILITY = "mode of liability"


@dataclass(frozen=True)
class Charge:
    """One statutory citation, parsed and scored."""

    act: str            # canonical act code, e.g. "IPC"
    section: str        # "302", "304B", "3"
    subsection: str     # "c" in 21(c); "" when there is none
    key: str            # canonical identity: "IPC:302", "NDPS:21(c)"
    label: str          # how an analyst writes it: "s.302 IPC"
    offence: str        # "Murder"; "" when the section is not in the curated table
    category: str       # "homicide", "narcotics", ...
    gravity: float      # 0-1
    gravity_basis: str  # "section" when researched, "act" when it fell back to the act default
    equivalent: str | None  # the same offence's key in the other code, where one is known

    @property
    def is_mode_of_liability(self) -> bool:
        """IPC 34 and its kin attach liability for someone else's act; they charge no offence."""
        return self.category == MODE_OF_LIABILITY

    def as_dict(self) -> dict:
        return {"act": self.act, "act_name": ACT_NAMES.get(self.act, self.act), "section": self.section,
                "subsection": self.subsection, "key": self.key, "label": self.label, "offence": self.offence,
                "category": self.category, "gravity": self.gravity, "gravity_basis": self.gravity_basis,
                "equivalent": self.equivalent}


def _act_of(text: str) -> tuple[str, str] | None:
    """Find the act named in a citation, returning (code, the text with the act name removed)."""
    for rx, code in ACT_RE:
        m = rx.search(text)
        if m:
            return code, (text[:m.start()] + " " + text[m.end():])
    return None


def _equivalent(act: str, section: str, subsection: str) -> str | None:
    if act == "IPC" and section in IPC_TO_BNS:
        return f"BNS:{IPC_TO_BNS[section]}"
    if act == "BNS":
        probe = f"{section}({subsection})" if subsection else section
        if probe in BNS_TO_IPC:
            return f"IPC:{BNS_TO_IPC[probe]}"
        if section in BNS_TO_IPC:
            return f"IPC:{BNS_TO_IPC[section]}"
    return None


def _charge(act: str, section: str, subsection: str) -> Charge:
    key = f"{act}:{section}" + (f"({subsection})" if subsection else "")
    entry = SECTIONS.get(key)
    if entry is None and subsection:
        entry = SECTIONS.get(f"{act}:{section}")  # 21(f) is unlisted; 21 is not
    if entry is not None:
        offence, category, gravity, basis = (*entry, "section")
    else:
        offence, basis = "", "act"
        category = ACT_DEFAULT_CATEGORY.get(act, "other")
        gravity = ACT_DEFAULT_GRAVITY.get(act, 0.35)
    label = f"s.{section}" + (f"({subsection})" if subsection else "") + f" {ACT_NAMES.get(act, act)}"
    return Charge(act=act, section=section, subsection=subsection, key=key, label=label, offence=offence,
                  category=category, gravity=round(float(gravity), 2), gravity_basis=basis,
                  equivalent=_equivalent(act, section, subsection))


def parse(citation: str) -> list[Charge]:
    """Parse one citation string into its charges.

    "302, 34 IPC" is two charges under one act; the act is stated once at the end and applies to
    every section before it, which is how the citation is written and read.
    """
    if not citation or not citation.strip():
        return []
    found = _act_of(citation)
    if found is None:
        return []  # a bare number with no act names no offence we can identify
    act, rest = found
    rest = PREFIX_RE.sub(" ", rest)
    out: list[Charge] = []
    seen: set[str] = set()
    for token in SPLIT_RE.split(rest):
        token = token.strip(" .;:-")
        if not token:
            continue
        m = TOKEN_RE.match(token)
        if not m:
            continue
        number, suffix, sub = m.group(1), (m.group(2) or "").upper(), (m.group(3) or "").lower()
        c = _charge(act, f"{number}{suffix}", sub)
        if c.key not in seen:
            seen.add(c.key)
            out.append(c)
    return out


def parse_all(citations: list[str] | str | None) -> list[Charge]:
    """Parse every citation on a record, de-duplicated, gravest first."""
    if not citations:
        return []
    items = [citations] if isinstance(citations, str) else list(citations)
    by_key: dict[str, Charge] = {}
    for raw in items:
        for c in parse(str(raw)):
            by_key.setdefault(c.key, c)
    return sorted(by_key.values(), key=lambda c: (-c.gravity, c.key))


def gravest(charges: list[Charge]) -> Charge | None:
    """The charge that sets the seriousness of a case.

    Modes of liability are skipped where anything substantive is present: a case under 302 r/w 34 is
    a murder case, not a common-intention case. Where nothing else is charged the mode is returned,
    because something is better than nothing to show the reader.
    """
    substantive = [c for c in charges if not c.is_mode_of_liability]
    pool = substantive or charges
    return max(pool, key=lambda c: c.gravity) if pool else None


def summarise(charges: list[Charge]) -> dict:
    """A record's charge profile: what it is about and how serious, in one dict."""
    top = gravest(charges)
    return {"charges": [c.as_dict() for c in charges],
            "keys": [c.key for c in charges],
            "categories": sorted({c.category for c in charges if not c.is_mode_of_liability}),
            "gravity": top.gravity if top else 0.0,
            "gravest": top.key if top else None,
            "offence": (top.offence or top.label) if top else ""}
