"""
Indian government identifier detection, checksum validation and PII masking.

Why this matters for extraction quality: an FIR narrative is full of 12-digit strings
that are *not* Aadhaar numbers, and 10-character tokens that are *not* PAN. Extracting
them blindly creates junk entities and, worse, false identity links between unrelated
people. Every identifier here is validated against its real checksum/format before it is
allowed into the graph.

Supported:
    AADHAAR  12 digits, Verhoeff checksum, first digit 2-9
    PAN      AAAAA9999A, 4th char = holder type, 5th = surname initial
    GSTIN    15 chars, embeds a PAN, state code 01-38, mod-36 checksum
    IFSC     4 letters + '0' + 6 alphanumeric
    VOTERID  3 letters + 7 digits (EPIC)
    PASSPORT 1 letter + 7 digits
    DL       state code + RTO + year + serial
    UPI      handle@psp

PII handling: Aadhaar is the most sensitive identifier in India and must never be stored
or displayed in full. `mask()` keeps only the last 4 digits, and the graph stores the
masked form as the label while keeping a salted hash for matching. That means two records
citing the same Aadhaar still resolve to one person, without the number itself sitting in
the database.

The Verhoeff tables are the standard ones published with the algorithm (Verhoeff, 1969);
this implementation was adapted from the team's `services/verhoeff.py` and verified against
the published test vectors (236 -> 3, 12345 -> 1).
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from ..config import settings

# --------------------------------------------------------------------------- Verhoeff
# Dihedral group D5 multiplication table
_D = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
    [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
    [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
    [4, 0, 1, 2, 3, 9, 5, 6, 7, 8],
    [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2],
    [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
    [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
    [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
]
# permutation table
_P = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
    [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
    [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
    [9, 4, 5, 3, 1, 2, 6, 8, 7, 0],
    [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5],
    [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]
_INV = [0, 4, 3, 2, 1, 5, 6, 7, 8, 9]


def verhoeff_check_digit(number: str) -> str:
    """Check digit for `number` (digits only). Verified: 236 -> 3, 12345 -> 1."""
    if not number.isdigit():
        raise ValueError("number must contain only digits")
    c = 0
    for i, n in enumerate(reversed([int(x) for x in number])):
        c = _D[c][_P[(i + 1) % 8][n]]
    return str(_INV[c])


def verhoeff_valid(number: str) -> bool:
    """True if the trailing digit is a correct Verhoeff check digit."""
    digits = "".join(ch for ch in number if ch.isdigit())
    if not digits:
        return False
    c = 0
    for i, n in enumerate(reversed([int(x) for x in digits])):
        c = _D[c][_P[i % 8][n]]
    return c == 0


# --------------------------------------------------------------------------- patterns
RE_AADHAAR = re.compile(r"(?<!\d)([2-9]\d{3})[\s-]?(\d{4})[\s-]?(\d{4})(?!\d)")
RE_PAN = re.compile(r"\b([A-Z]{5}\d{4}[A-Z])\b")
RE_GSTIN = re.compile(r"\b(\d{2}[A-Z]{5}\d{4}[A-Z][A-Z\d][Zz][A-Z\d])\b")
RE_IFSC = re.compile(r"\b([A-Z]{4}0[A-Z0-9]{6})\b")
RE_VOTER = re.compile(r"\b([A-Z]{3}\d{7})\b")
RE_PASSPORT = re.compile(r"\b([A-PR-WY][0-9]{7})\b")
RE_DL = re.compile(r"\b([A-Z]{2}[\s-]?\d{2}[\s-]?(?:19|20)\d{2}[\s-]?\d{7})\b")
RE_UPI = re.compile(r"\b([a-zA-Z0-9.\-_]{3,})@(ybl|okaxis|oksbi|okhdfcbank|okicici|paytm|upi|axl|ibl|apl|hdfcbank|sbi)\b")

# GSTIN state codes 01-38 (+ 97 other territory, 99 centre)
_GST_STATES = {f"{i:02d}" for i in range(1, 39)} | {"97", "99"}
# PAN 4th character: entity type
_PAN_TYPES = {"P": "individual", "C": "company", "H": "HUF", "F": "firm/LLP", "A": "AOP", "T": "trust",
              "B": "body of individuals", "L": "local authority", "J": "artificial juridical person", "G": "government"}
_GST_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


@dataclass
class Identifier:
    kind: str          # AADHAAR | PAN | GSTIN | IFSC | VOTERID | PASSPORT | DL | UPI
    raw: str           # exact text as it appeared
    normalized: str    # canonical form (masked for Aadhaar)
    valid: bool        # passed checksum / structural validation
    start: int
    end: int
    attrs: dict
    sensitive: bool = False

    @property
    def display(self) -> str:
        return self.normalized


# --------------------------------------------------------------------------- validators
def validate_aadhaar(num: str) -> tuple[bool, dict]:
    d = "".join(ch for ch in num if ch.isdigit())
    if len(d) != 12:
        return False, {"reason": "must be 12 digits"}
    if d[0] in "01":
        return False, {"reason": "Aadhaar cannot start with 0 or 1"}
    if len(set(d)) == 1:
        return False, {"reason": "repeated-digit placeholder"}
    ok = verhoeff_valid(d)
    return ok, {"checksum": "verhoeff", "valid": ok, **({} if ok else {"reason": "Verhoeff checksum failed"})}


def validate_pan(pan: str) -> tuple[bool, dict]:
    pan = pan.upper()
    if not RE_PAN.fullmatch(pan):
        return False, {"reason": "format must be AAAAA9999A"}
    holder = _PAN_TYPES.get(pan[3])
    if holder is None:
        return False, {"reason": f"invalid holder-type character '{pan[3]}'"}
    return True, {"holder_type": holder, "surname_initial": pan[4]}


def _gst_checksum(gstin: str) -> str:
    total = 0
    for i, ch in enumerate(gstin[:14]):
        v = _GST_ALPHABET.index(ch)
        f = v * (2 if i % 2 else 1)
        total += f // 36 + f % 36
    return _GST_ALPHABET[(36 - total % 36) % 36]


def validate_gstin(g: str) -> tuple[bool, dict]:
    g = g.upper()
    if len(g) != 15 or not RE_GSTIN.fullmatch(g):
        return False, {"reason": "format must be 99AAAAA9999A9Z9"}
    if g[:2] not in _GST_STATES:
        return False, {"reason": f"invalid state code '{g[:2]}'"}
    pan_ok, pan_attrs = validate_pan(g[2:12])
    if not pan_ok:
        return False, {"reason": "embedded PAN invalid"}
    expected = _gst_checksum(g)
    if g[14] != expected:
        return False, {"reason": f"checksum failed (expected {expected})"}
    return True, {"state_code": g[:2], "pan": g[2:12], **pan_attrs}


def validate_ifsc(code: str) -> tuple[bool, dict]:
    code = code.upper()
    if not RE_IFSC.fullmatch(code):
        return False, {"reason": "format must be AAAA0XXXXXX"}
    return True, {"bank_code": code[:4], "branch_code": code[5:]}


# --------------------------------------------------------------------------- masking
def mask(kind: str, value: str) -> str:
    """Mask sensitive identifiers for storage and display."""
    if kind == "AADHAAR":
        d = "".join(ch for ch in value if ch.isdigit())
        return f"XXXX-XXXX-{d[-4:]}"
    if kind == "PAN":
        return f"{value[:3]}XX{value[5:9]}X" if len(value) == 10 else value
    if kind == "PASSPORT":
        return f"{value[0]}XXXX{value[-3:]}"
    return value


def fingerprint(kind: str, value: str) -> str:
    """Salted hash so two records citing the same identifier still resolve to one entity
    without the identifier itself being stored."""
    digits = "".join(ch for ch in value if ch.isalnum()).upper()
    return hashlib.sha256(f"{settings.jwt_secret}|{kind}|{digits}".encode()).hexdigest()[:32]


# --------------------------------------------------------------------------- extraction
def extract(text: str, include_invalid: bool = False) -> list[Identifier]:
    """Find every Indian identifier in `text`, validated. Invalid ones are dropped unless asked for.

    Aadhaar is returned masked, with a `fingerprint` attribute for matching.
    """
    out: list[Identifier] = []
    taken: list[tuple[int, int]] = []

    def free(s: int, e: int) -> bool:
        return not any(s < te and e > ts for ts, te in taken)

    def add(idf: Identifier):
        if free(idf.start, idf.end) and (idf.valid or include_invalid):
            taken.append((idf.start, idf.end))
            out.append(idf)

    # GSTIN before PAN (a GSTIN contains a PAN), both before Aadhaar (digit overlap)
    for m in RE_GSTIN.finditer(text):
        ok, attrs = validate_gstin(m.group(1))
        add(Identifier("GSTIN", m.group(1), m.group(1).upper(), ok, m.start(1), m.end(1), attrs))
    for m in RE_PAN.finditer(text):
        ok, attrs = validate_pan(m.group(1))
        add(Identifier("PAN", m.group(1), m.group(1).upper(), ok, m.start(1), m.end(1),
                       {**attrs, "fingerprint": fingerprint("PAN", m.group(1))}, sensitive=True))
    for m in RE_IFSC.finditer(text):
        ok, attrs = validate_ifsc(m.group(1))
        add(Identifier("IFSC", m.group(1), m.group(1).upper(), ok, m.start(1), m.end(1), attrs))
    for m in RE_AADHAAR.finditer(text):
        raw = m.group(0)
        ok, attrs = validate_aadhaar(raw)
        add(Identifier("AADHAAR", raw, mask("AADHAAR", raw), ok, m.start(), m.end(),
                       {**attrs, "fingerprint": fingerprint("AADHAAR", raw)}, sensitive=True))
    for m in RE_VOTER.finditer(text):
        add(Identifier("VOTERID", m.group(1), m.group(1).upper(), True, m.start(1), m.end(1), {}))
    for m in RE_PASSPORT.finditer(text):
        add(Identifier("PASSPORT", m.group(1), mask("PASSPORT", m.group(1)), True, m.start(1), m.end(1),
                       {"fingerprint": fingerprint("PASSPORT", m.group(1))}, sensitive=True))
    for m in RE_DL.finditer(text):
        add(Identifier("DL", m.group(1), re.sub(r"[\s-]", "", m.group(1).upper()), True, m.start(1), m.end(1),
                       {"state_code": m.group(1)[:2]}))
    for m in RE_UPI.finditer(text):
        add(Identifier("UPI", m.group(0), m.group(0).lower(), True, m.start(), m.end(), {"psp": m.group(2)}))
    out.sort(key=lambda i: i.start)
    return out


def summarize(text: str) -> dict:
    """Counts by kind plus any identifiers that failed validation - useful for a document quality panel."""
    found = extract(text, include_invalid=True)
    valid = [i for i in found if i.valid]
    invalid = [i for i in found if not i.valid]
    counts: dict[str, int] = {}
    for i in valid:
        counts[i.kind] = counts.get(i.kind, 0) + 1
    return {"counts": counts, "valid": len(valid), "invalid": len(invalid),
            "rejected": [{"kind": i.kind, "text": i.raw if not i.sensitive else mask(i.kind, i.raw),
                          "reason": i.attrs.get("reason", "failed validation")} for i in invalid[:10]]}
