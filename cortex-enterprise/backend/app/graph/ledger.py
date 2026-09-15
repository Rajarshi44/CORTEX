"""
Tamper-evident evidence ledger (append-only SHA-256 hash chain).

Chain of custody is the weak point of any digital investigation system: if a defence
lawyer asks "could this evidence have been altered after collection?", a plain database
row cannot answer. Each ledger entry hashes its own content together with the previous
entry's hash, so altering any historical record invalidates every hash after it, and the
break is detectable in O(n) with no external service.

This is a hash chain, not a distributed blockchain — there is no consensus or mining,
because a single institution (the investigating agency) is the trusted writer. That is the
correct design for this problem; proof-of-work would add cost and no security here.
What it does guarantee: nobody, including a database administrator, can silently rewrite
history. To detect *deletion* of the newest entries as well, `anchor()` publishes the head
hash, which can be recorded externally (a case diary, a signed email, or a public chain).

Adapted from the team's `services/blockchain.py` (audit-log chaining) and extended to
cover evidence records and entity/relationship provenance, with genesis handling,
verification that reports the exact break point, and external anchoring.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Integer, String, Text, DateTime, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from ..db import Base, utcnow

GENESIS_HASH = "0" * 64


def _canonical(data: Any) -> str:
    """Deterministic serialisation - key order and separators must never vary or hashes break."""
    return json.dumps(data, sort_keys=True, default=str, separators=(",", ":"), ensure_ascii=False)


def sha256(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class LedgerEntry(Base):
    """One immutable link in the chain."""

    __tablename__ = "evidence_ledger"

    index: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    actor: Mapped[str] = mapped_column(String(64), index=True)       # username or "system"
    action: Mapped[str] = mapped_column(String(64), index=True)      # INGEST | EVIDENCE | ALERT | EXPORT | LOGIN ...
    subject_type: Mapped[str] = mapped_column(String(32), default="")  # document | entity | relationship | alert
    subject_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    payload_hash: Mapped[str] = mapped_column(String(64))            # hash of the content being attested
    previous_hash: Mapped[str] = mapped_column(String(64))
    entry_hash: Mapped[str] = mapped_column(String(64), unique=True)
    detail: Mapped[str] = mapped_column(Text, default="")

    def compute_hash(self) -> str:
        """Every stored field is covered. A field left out of the hash could be edited without
        breaking the chain, which would defeat the purpose of having one."""
        return sha256(_canonical({
            "index": self.index, "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "actor": self.actor, "action": self.action, "subject_type": self.subject_type,
            "subject_id": self.subject_id, "payload_hash": self.payload_hash, "previous_hash": self.previous_hash,
            "detail": self.detail,
        }))

    def as_dict(self) -> dict:
        return {"index": self.index, "timestamp": self.timestamp.isoformat() if self.timestamp else None,
                "actor": self.actor, "action": self.action, "subject_type": self.subject_type,
                "subject_id": self.subject_id, "payload_hash": self.payload_hash,
                "previous_hash": self.previous_hash, "entry_hash": self.entry_hash, "detail": self.detail}


# --------------------------------------------------------------------------------- writing
def head(db: Session) -> LedgerEntry | None:
    """Newest entry. Autoflush is suppressed: during ingestion the session holds Evidence rows whose
    relationships have not been flushed yet, and an incidental flush here would violate their FKs."""
    with db.no_autoflush:
        pending = [o for o in db.new if isinstance(o, LedgerEntry)]
        if pending:
            return max(pending, key=lambda e: e.index)
        return db.execute(select(LedgerEntry).order_by(LedgerEntry.index.desc()).limit(1)).scalar_one_or_none()


def append(db: Session, actor: str, action: str, payload: Any, *, subject_type: str = "",
           subject_id: str = "", detail: str = "", commit: bool = True) -> LedgerEntry:
    """Attest `payload` to the chain. The payload itself is not stored - only its hash.

    The index is assigned explicitly rather than by autoincrement, because it is part of the
    hashed content and the row cannot be inserted before its own hash exists.
    """
    prev = head(db)
    entry = LedgerEntry(
        index=(prev.index + 1) if prev else 1,
        timestamp=datetime.now(timezone.utc).replace(tzinfo=None),
        actor=actor or "system", action=action, subject_type=subject_type, subject_id=str(subject_id or ""),
        payload_hash=sha256(_canonical(payload)),
        previous_hash=prev.entry_hash if prev else GENESIS_HASH,
        detail=detail[:2000],
    )
    entry.entry_hash = entry.compute_hash()
    db.add(entry)
    if commit:
        db.commit()
    return entry


def attest_document(db: Session, actor: str, doc_id: str, title: str, content: str, source_type: str,
                    commit: bool = True) -> LedgerEntry:
    """Seal an ingested document at the moment of collection."""
    return append(db, actor, "INGEST",
                  {"document_id": doc_id, "title": title, "source_type": source_type, "content": content},
                  subject_type="document", subject_id=doc_id,
                  detail=f"{source_type}: {title[:180]}", commit=commit)


def attest_evidence(db: Session, actor: str, evidence_id: int, snippet: str, document_id: str,
                    entity_id: str | None, extractor: str) -> LedgerEntry:
    return append(db, actor, "EVIDENCE",
                  {"evidence_id": evidence_id, "snippet": snippet, "document_id": document_id,
                   "entity_id": entity_id, "extractor": extractor},
                  subject_type="evidence", subject_id=str(evidence_id),
                  detail=f"{extractor} extraction from {document_id}")


def attest_export(db: Session, actor: str, kind: str, content: bytes | str) -> LedgerEntry:
    """Seal a report at export time so a PDF handed to a court can be proven unmodified."""
    payload = content if isinstance(content, str) else hashlib.sha256(content).hexdigest()
    return append(db, actor, "EXPORT", {"kind": kind, "content": payload},
                  subject_type="report", subject_id=kind, detail=f"exported {kind}")


# --------------------------------------------------------------------------------- verification
def verify(db: Session) -> dict:
    """Walk the chain and report the first break, if any."""
    entries = db.execute(select(LedgerEntry).order_by(LedgerEntry.index.asc())).scalars().all()
    if not entries:
        return {"status": "empty", "entries": 0, "valid": True}
    expected_prev = GENESIS_HASH
    for e in entries:
        if e.previous_hash != expected_prev:
            return {"status": "broken", "valid": False, "entries": len(entries), "broken_at": e.index,
                    "reason": "previous_hash does not match the preceding entry - an entry was altered, "
                              "inserted or removed",
                    "expected_previous": expected_prev, "found_previous": e.previous_hash,
                    "entry": e.as_dict()}
        if e.compute_hash() != e.entry_hash:
            return {"status": "broken", "valid": False, "entries": len(entries), "broken_at": e.index,
                    "reason": "entry content does not match its stored hash - this record was modified after sealing",
                    "entry": e.as_dict()}
        expected_prev = e.entry_hash
    return {"status": "intact", "valid": True, "entries": len(entries), "head": entries[-1].entry_hash,
            "first_sealed": entries[0].timestamp.isoformat(), "last_sealed": entries[-1].timestamp.isoformat()}


def verify_payload(db: Session, index: int, payload: Any) -> dict:
    """Prove a specific artefact still matches what was sealed at `index`."""
    e = db.get(LedgerEntry, index)
    if e is None:
        return {"status": "not_found", "index": index}
    actual = sha256(_canonical(payload))
    return {"status": "match" if actual == e.payload_hash else "mismatch",
            "index": index, "sealed_hash": e.payload_hash, "computed_hash": actual,
            "sealed_at": e.timestamp.isoformat(), "actor": e.actor,
            "conclusion": ("content is byte-identical to what was sealed" if actual == e.payload_hash
                           else "content has changed since it was sealed")}


def anchor(db: Session) -> dict:
    """The head hash: publish this externally to also detect truncation of the newest entries."""
    h = head(db)
    if h is None:
        return {"status": "empty"}
    return {"status": "ok", "head_hash": h.entry_hash, "height": h.index,
            "sealed_at": h.timestamp.isoformat(),
            "note": "record this value externally (case diary / signed email / public chain) to make "
                    "deletion of the most recent entries detectable as well"}


def stats(db: Session) -> dict:
    from sqlalchemy import func

    rows = db.execute(select(LedgerEntry.action, func.count()).group_by(LedgerEntry.action)).all()
    h = head(db)
    return {"height": h.index if h else 0, "head_hash": h.entry_hash if h else None,
            "by_action": {a: c for a, c in rows}}
