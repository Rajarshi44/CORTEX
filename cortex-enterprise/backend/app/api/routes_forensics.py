"""Identifier validation, evidence ledger and behavioural case-linkage endpoints."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import audit, current_user, require_role
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
@router.get("/ledger/verify")
def ledger_verify(db: Annotated[Session, Depends(get_session)], _: Annotated[User, Depends(current_user)]):
    """Walk the evidence hash chain and report the exact break point if tampering occurred."""
    return ledger.verify(db)


@router.get("/ledger")
def ledger_entries(db: Annotated[Session, Depends(get_session)], _: Annotated[User, Depends(current_user)],
                   limit: int = 100, action: str | None = None, subject_id: str | None = None):
    q = db.query(ledger.LedgerEntry)
    if action:
        q = q.filter(ledger.LedgerEntry.action == action)
    if subject_id:
        q = q.filter(ledger.LedgerEntry.subject_id == subject_id)
    rows = q.order_by(ledger.LedgerEntry.index.desc()).limit(limit).all()
    return {"entries": [e.as_dict() for e in rows], **ledger.stats(db)}


@router.get("/ledger/anchor")
def ledger_anchor(db: Annotated[Session, Depends(get_session)], _: Annotated[User, Depends(current_user)]):
    return ledger.anchor(db)


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
