"""Quality and protection rules for graph entities (e.g. victims, complainants, witnesses, police).

Protected parties must be excluded from evidentiary suspicion scoring, priority ranking,
criminal community grouping, and first-time offender proximity risk.
"""
from __future__ import annotations

PROTECTED_PARTY_ROLES = {"victim", "complainant", "witness", "police"}


def is_protected_party(node_type: str = "", label: str = "", attrs: dict | None = None) -> bool:
    """True when an entity is a protected party (victim, complainant, witness, police/law enforcement).

    Protected parties must be excluded from evidentiary suspicion scoring, priority ranking,
    criminal community grouping, and first-time offender proximity risk.
    """
    attrs = attrs or {}

    # 1. Explicit party_role attribute
    party_role = str(attrs.get("party_role") or "").lower().strip()
    if party_role in PROTECTED_PARTY_ROLES:
        return True
    for pr in PROTECTED_PARTY_ROLES:
        if pr in party_role:
            return True

    # 2. Role in network / status
    role = str(attrs.get("role_in_network") or "").lower().strip()
    for pr in PROTECTED_PARTY_ROLES:
        if pr in role:
            return True

    status = str(attrs.get("status") or "").lower().strip()
    for pr in PROTECTED_PARTY_ROLES:
        if pr in status:
            return True

    # 3. Court role / record role
    court_role = str(attrs.get("court_role") or attrs.get("record_role") or "").lower().strip()
    for pr in PROTECTED_PARTY_ROLES:
        if pr in court_role:
            return True

    # 4. Label / Name checks (e.g., "Victim", "Complainant 1", "Victim Savings Account", etc.)
    lbl = str(label or "").lower().strip()
    if "victim" in lbl or "complainant" in lbl:
        return True
    if "witness" in lbl:
        return True
    if any(w in lbl for w in ("police officer", "sub-inspector", "inspector", "constable", "investigating officer")):
        return True

    # 5. Record id checks (e.g. P001 which is the primary victim/complainant)
    rec_id = str(attrs.get("record_id") or "").upper().strip()
    if rec_id == "P001":
        return True

    return False
