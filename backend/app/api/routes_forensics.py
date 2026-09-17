"""Identifier validation, evidence ledger and behavioural case-linkage endpoints."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import audit, current_user, optional_user, require_role
from ..db import Document, User, get_session
from ..graph import ledger
from ..graph.case_linkage import CaseLinkageEngine, extract_features
from ..ingestion import identifiers

router = APIRouter(prefix="/api/forensics", tags=["forensics"])


# ----------------------------------------------------------------------------- identifiers
class IdText(BaseModel):
    text: str
    include_invalid: bool = True


@router.post("/identifiers")
def find_identifiers(body: IdText, _: Annotated[User, Depends(current_user)]):
    """Detect and checksum-validate Indian government identifiers. Aadhaar is returned masked."""
    found = identifiers.extract(body.text, include_invalid=body.include_invalid)
    return {"identifiers": [{"kind": i.kind, "value": i.display, "valid": i.valid, "sensitive": i.sensitive,
                             "start": i.start, "end": i.end,
                             "attrs": {k: v for k, v in i.attrs.items() if k != "fingerprint"}} for i in found],
            "summary": identifiers.summarize(body.text),
            "note": "Aadhaar/PAN/passport values are masked; a salted fingerprint is used for matching so the "
                    "raw number is never stored."}


class AadhaarIn(BaseModel):
    number: str


@router.post("/identifiers/validate-aadhaar")
def check_aadhaar(body: AadhaarIn, _: Annotated[User, Depends(current_user)]):
    ok, attrs = identifiers.validate_aadhaar(body.number)
    return {"valid": ok, "masked": identifiers.mask("AADHAAR", body.number), **attrs}


@router.get("/documents/{doc_id}/identifiers")
def document_identifiers(doc_id: str, db: Annotated[Session, Depends(get_session)], _: Annotated[User, Depends(current_user)]):
    d = db.get(Document, doc_id)
    if not d:
        raise HTTPException(404, "document not found")
    return identifiers.summarize(f"{d.title}. {d.content or ''}")


# ----------------------------------------------------------------------------- ledger
class VerifyProofIn(BaseModel):
    leaf_hash: str
    proof: dict


@router.get("/ledger/verify")
def ledger_verify(db: Annotated[Session, Depends(get_session)], _: Annotated[User, Depends(current_user)]):
    """Walk the evidence hash chain and report the exact break point if tampering occurred."""
    return ledger.verify(db)


@router.get("/ledger")
@router.get("/ledger/entries")
def ledger_entries(
    db: Annotated[Session, Depends(get_session)],
    _: Annotated[User, Depends(current_user)],
    limit: int = 100,
    action: str | None = None,
    subject_id: str | None = None,
):
    """List ledger entries along with Merkle root, public key, and chain height."""
    q = db.query(ledger.LedgerEntry)
    if action:
        q = q.filter(ledger.LedgerEntry.action == action)
    if subject_id:
        q = q.filter(ledger.LedgerEntry.subject_id == subject_id)
    rows = q.order_by(ledger.LedgerEntry.index.desc()).limit(limit).all()
    return {"entries": [e.as_dict() for e in rows], **ledger.stats(db)}


@router.get("/ledger/proof/{index}")
def ledger_proof(
    index: int,
    db: Annotated[Session, Depends(get_session)],
    _: Annotated[User | None, Depends(optional_user)] = None,
):
    """Return cryptographic Merkle inclusion proof for a ledger entry."""
    try:
        return ledger.get_inclusion_proof(index, db)
    except ValueError as err:
        raise HTTPException(404, str(err))


@router.post("/ledger/verify-proof")
def ledger_verify_proof(
    body: VerifyProofIn,
    _: Annotated[User | None, Depends(optional_user)] = None,
):
    """Verify a Merkle tree inclusion proof against the calculated root."""
    valid = ledger.verify_inclusion_proof(body.leaf_hash, body.proof)
    return {
        "valid": valid,
        "leaf_hash": body.leaf_hash,
        "root_hash": body.proof.get("root_hash"),
    }


@router.get("/ledger/anchor")
def ledger_anchor(
    db: Annotated[Session, Depends(get_session)],
    _: Annotated[User | None, Depends(optional_user)] = None,
):
    """Return persisted external anchor record with Ed25519 signature."""
    return ledger.get_anchor(db)


@router.get("/ledger/verify-brief")
def verify_brief(
    db: Annotated[Session, Depends(get_session)],
    hash: str | None = None,
    index: int | None = None,
    _: Annotated[User | None, Depends(optional_user)] = None,
):
    """Verify brief hash and Ed25519 signature against evidence ledger."""
    if not hash and index is None:
        raise HTTPException(400, "Must provide 'hash' or 'index' query parameter")

    entry: ledger.LedgerEntry | None = None
    if index is not None:
        entry = db.get(ledger.LedgerEntry, index)

    if entry is None and hash:
        entry = (
            db.query(ledger.LedgerEntry)
            .filter(
                (ledger.LedgerEntry.payload_hash == hash)
                | (ledger.LedgerEntry.entry_hash == hash)
                | (ledger.LedgerEntry.detail.contains(hash))
            )
            .order_by(ledger.LedgerEntry.index.desc())
            .first()
        )

    if entry is None:
        return {
            "status": "not_found",
            "valid": False,
            "hash": hash,
            "index": index,
            "reason": "No matching ledger entry found for this brief",
        }

    sig_valid = ledger.verify_signature(entry)
    hash_match = True
    if hash:
        hash_match = (hash == entry.payload_hash) or (hash == entry.entry_hash) or (hash in entry.detail)

    chain_status = ledger.verify(db)
    is_valid = sig_valid and hash_match and chain_status.get("valid", True)

    return {
        "status": "verified" if is_valid else "invalid",
        "valid": is_valid,
        "index": entry.index,
        "action": entry.action,
        "subject_type": entry.subject_type,
        "subject_id": entry.subject_id,
        "payload_hash": entry.payload_hash,
        "entry_hash": entry.entry_hash,
        "signature": entry.signature or "",
        "signature_valid": sig_valid,
        "hash_match": hash_match,
        "chain_intact": chain_status.get("valid", True),
        "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
        "actor": entry.actor,
        "detail": entry.detail,
    }


@router.get("/ledger/verify-document/{doc_id}")
def verify_document(doc_id: str, db: Annotated[Session, Depends(get_session)], _: Annotated[User, Depends(current_user)]):
    """Prove an ingested document is byte-identical to what was sealed at collection."""
    d = db.get(Document, doc_id)
    if not d:
        raise HTTPException(404, "document not found")
    entry = (db.query(ledger.LedgerEntry)
             .filter(ledger.LedgerEntry.subject_type == "document", ledger.LedgerEntry.subject_id == doc_id)
             .order_by(ledger.LedgerEntry.index.asc()).first())
    if entry is None:
        return {"status": "not_sealed", "document_id": doc_id,
                "reason": "this document predates the ledger or was ingested with sealing disabled"}
    return ledger.verify_payload(db, entry.index, {"document_id": d.id, "title": d.title,
                                                   "source_type": d.source_type, "content": d.content})


# ----------------------------------------------------------------------------- case linkage
@router.get("/linkage")
def linkage(db: Annotated[Session, Depends(get_session)], user: Annotated[User, Depends(current_user)],
            threshold: float = 0.55, limit: int = 300, crime_head: str | None = None):
    """Behavioural case linkage: which unsolved offences may share an offender."""
    eng = CaseLinkageEngine(db)
    n = eng.load(limit=limit, crime_head=crime_head)
    if n < 2:
        return {"status": "insufficient_data", "cases_analysed": n,
                "reason": "need at least two narrative case documents (FIR / judgment / news)"}
    audit(db, user, "case_linkage", f"{n} cases, threshold {threshold}")
    return eng.report(threshold)


@router.get("/linkage/series")
def linkage_series(db: Annotated[Session, Depends(get_session)], _: Annotated[User, Depends(current_user)],
                   threshold: float = 0.55, limit: int = 300, min_size: int = 2):
    eng = CaseLinkageEngine(db)
    eng.load(limit=limit)
    return {"series": eng.series(threshold, min_size),
            "disclaimer": "CANDIDATE LEADS ONLY - behavioural similarity, not identification."}


@router.get("/linkage/case/{doc_id}")
def linkage_for_case(doc_id: str, db: Annotated[Session, Depends(get_session)], _: Annotated[User, Depends(current_user)],
                     threshold: float = 0.45, limit: int = 300):
    """Everything behaviourally similar to one case, ranked, with per-signal explanation."""
    d = db.get(Document, doc_id)
    if not d:
        raise HTTPException(404, "document not found")
    eng = CaseLinkageEngine(db)
    eng.load(limit=limit)
    ids = [c.document_id for c in eng.cases]
    if doc_id not in ids:
        eng.cases.insert(0, extract_features(d))
        eng._narrative = None
        i = 0
    else:
        i = ids.index(doc_id)
    eng._narrative_matrix()
    pairs = [eng.pair_score(min(i, j), max(i, j)) for j in range(len(eng.cases)) if j != i]
    pairs = sorted([p for p in pairs if p["score"] >= threshold], key=lambda p: -p["score"])[:25]
    return {"case": eng.cases[i].as_dict(), "similar": pairs, "count": len(pairs),
            "disclaimer": "CANDIDATE LEADS ONLY - behavioural similarity, not identification."}


@router.get("/linkage/features/{doc_id}")
def case_features(doc_id: str, db: Annotated[Session, Depends(get_session)], _: Annotated[User, Depends(current_user)]):
    d = db.get(Document, doc_id)
    if not d:
        raise HTTPException(404, "document not found")
    return extract_features(d).as_dict()
