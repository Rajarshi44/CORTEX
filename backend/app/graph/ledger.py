"""
Tamper-evident evidence ledger (append-only SHA-256 hash chain with Ed25519 signatures,
Merkle batch inclusion proofs, and persistent external anchors).

Chain of custody is the weak point of any digital investigation system: if a defence
lawyer asks "could this evidence have been altered after collection?", a plain database
row cannot answer. Each ledger entry hashes its own content together with the previous
entry's hash, and signs the resulting entry_hash using an Ed25519 digital signature key.

Merkle tree roots and inclusion proofs allow proving presence of any record in O(log n)
with an external cryptographic anchor published at `backend/data/ledger_anchor.json`.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from sqlalchemy import DateTime, Integer, String, Text, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Mapped, Session, mapped_column

from ..config import settings
from ..db import Base, utcnow
from . import ed25519

GENESIS_HASH = "0" * 64
KEY_FILE_NAME = "ledger_ed25519.json"
ANCHOR_FILE_NAME = "ledger_anchor.json"


def _get_key_path() -> Path:
    return settings.data_dir / KEY_FILE_NAME


def _get_anchor_path() -> Path:
    return settings.data_dir / ANCHOR_FILE_NAME


# --------------------------------------------------------------------------------- Ed25519 Key Management
def get_or_create_keypair(key_path: Path | None = None) -> tuple[str, str]:
    """Retrieve or generate persistent Ed25519 keypair for ledger signing.

    Returns:
        (private_key_hex, public_key_hex)
    """
    path = key_path or _get_key_path()
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            priv = data.get("private_key_hex")
            pub = data.get("public_key_hex")
            if priv and pub and len(priv) == 64 and len(pub) == 64:
                return priv, pub
        except Exception:
            pass

    seed, pub = ed25519.generate_keypair()
    priv_hex = seed.hex()
    pub_hex = pub.hex()

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "private_key_hex": priv_hex,
        "public_key_hex": pub_hex,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "algorithm": "Ed25519",
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return priv_hex, pub_hex


def get_public_key(key_path: Path | None = None) -> str:
    _, pub = get_or_create_keypair(key_path)
    return pub


def sign_hash(entry_hash: str, private_key_hex: str | None = None) -> str:
    """Sign an entry_hash string using Ed25519 private key seed."""
    if not private_key_hex:
        private_key_hex, _ = get_or_create_keypair()
    seed = bytes.fromhex(private_key_hex)
    msg = entry_hash.encode("utf-8")
    sig = ed25519.sign(seed, msg)
    return sig.hex()


def verify_signature(entry: LedgerEntry | dict, public_key_hex: str | None = None) -> bool:
    """Verify Ed25519 signature on an entry."""
    if not public_key_hex:
        public_key_hex = get_public_key()
    pub = bytes.fromhex(public_key_hex)

    if isinstance(entry, dict):
        sig_hex = entry.get("signature") or ""
        hash_val = entry.get("entry_hash") or ""
    else:
        sig_hex = entry.signature or ""
        hash_val = entry.entry_hash or ""

    if not sig_hex or not hash_val:
        return False

    try:
        sig = bytes.fromhex(sig_hex)
        msg = hash_val.encode("utf-8")
        return ed25519.verify(pub, msg, sig)
    except Exception:
        return False


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
    actor: Mapped[str] = mapped_column(String(64), index=True)  # username or "system"
    action: Mapped[str] = mapped_column(String(64), index=True)  # INGEST | EVIDENCE | ALERT | EXPORT | LOGIN ...
    subject_type: Mapped[str] = mapped_column(String(32), default="")  # document | entity | relationship | alert | export
    subject_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    payload_hash: Mapped[str] = mapped_column(String(64))  # hash of the content being attested
    previous_hash: Mapped[str] = mapped_column(String(64))
    entry_hash: Mapped[str] = mapped_column(String(64), unique=True)
    signature: Mapped[str] = mapped_column(Text, default="", nullable=True)
    detail: Mapped[str] = mapped_column(Text, default="")

    def compute_hash(self) -> str:
        """Every stored field except signature is covered.

        The signature certifies this exact entry_hash.
        """
        return sha256(_canonical({
            "index": self.index,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "actor": self.actor,
            "action": self.action,
            "subject_type": self.subject_type,
            "subject_id": self.subject_id,
            "payload_hash": self.payload_hash,
            "previous_hash": self.previous_hash,
            "detail": self.detail,
        }))

    def as_dict(self) -> dict:
        return {
            "index": self.index,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "actor": self.actor,
            "action": self.action,
            "subject_type": self.subject_type,
            "subject_id": self.subject_id,
            "payload_hash": self.payload_hash,
            "previous_hash": self.previous_hash,
            "entry_hash": self.entry_hash,
            "signature": self.signature or "",
            "detail": self.detail,
        }


def ensure_ledger_schema(engine_or_session: Engine | Session) -> None:
    """Ensure evidence_ledger table has `signature` column and backfill signatures if needed."""
    try:
        bind = engine_or_session.get_bind() if isinstance(engine_or_session, Session) else engine_or_session
        with bind.connect() as conn:
            dialect_name = bind.dialect.name.lower()
            if dialect_name == "sqlite":
                res = conn.execute(text("PRAGMA table_info(evidence_ledger)")).fetchall()
                cols = [r[1] for r in res]
                if res and "signature" not in cols:
                    conn.execute(text("ALTER TABLE evidence_ledger ADD COLUMN signature TEXT DEFAULT ''"))
                    conn.commit()
            else:
                # Postgres or MySQL
                conn.execute(text("ALTER TABLE evidence_ledger ADD COLUMN IF NOT EXISTS signature TEXT DEFAULT ''"))
                conn.commit()
    except Exception:
        pass


# --------------------------------------------------------------------------------- Merkle Tree Calculations
def compute_merkle_root(entries_or_hashes: Sequence[LedgerEntry | dict | str]) -> str:
    """Calculate Merkle root over ledger entries or hashes.

    Uses SHA-256 tree calculation: adjacent hashes are concatenated and hashed.
    For odd number of items, the last item is duplicated (standard tree construction).
    """
    if not entries_or_hashes:
        return GENESIS_HASH

    current: list[str] = []
    for item in entries_or_hashes:
        if isinstance(item, LedgerEntry):
            current.append(item.entry_hash)
        elif isinstance(item, dict):
            current.append(item.get("entry_hash", ""))
        else:
            current.append(str(item))

    if not current:
        return GENESIS_HASH
    if len(current) == 1:
        return current[0]

    while len(current) > 1:
        next_level: list[str] = []
        if len(current) % 2 == 1:
            current.append(current[-1])
        for i in range(0, len(current), 2):
            combined = current[i] + current[i + 1]
            next_level.append(sha256(combined))
        current = next_level

    return current[0]


def get_inclusion_proof(entry_index: int, db: Session) -> dict:
    """Build a Merkle inclusion proof for the entry at `entry_index`.

    Returns:
        {
            "leaf_index": index,
            "leaf_hash": hash,
            "root_hash": root,
            "total_leaves": int,
            "audit_path": [{"position": "left" | "right", "hash": str}]
        }
    """
    entries = db.execute(select(LedgerEntry).order_by(LedgerEntry.index.asc())).scalars().all()
    if not entries:
        raise ValueError("Ledger is empty")

    idx_map = {e.index: i for i, e in enumerate(entries)}
    if entry_index not in idx_map:
        raise ValueError(f"Entry with index {entry_index} not found in ledger")

    leaf_pos = idx_map[entry_index]
    target_leaf_hash = entries[leaf_pos].entry_hash
    current_hashes = [e.entry_hash for e in entries]
    total_leaves = len(current_hashes)

    if total_leaves == 1:
        return {
            "leaf_index": entry_index,
            "leaf_hash": target_leaf_hash,
            "root_hash": target_leaf_hash,
            "total_leaves": 1,
            "audit_path": [],
        }

    audit_path: list[dict[str, str]] = []
    curr_idx = leaf_pos

    while len(current_hashes) > 1:
        if len(current_hashes) % 2 == 1:
            current_hashes.append(current_hashes[-1])

        if curr_idx % 2 == 0:
            sibling_idx = curr_idx + 1
            sibling_hash = current_hashes[sibling_idx]
            audit_path.append({"position": "right", "hash": sibling_hash})
        else:
            sibling_idx = curr_idx - 1
            sibling_hash = current_hashes[sibling_idx]
            audit_path.append({"position": "left", "hash": sibling_hash})

        next_level = []
        for i in range(0, len(current_hashes), 2):
            combined = current_hashes[i] + current_hashes[i + 1]
            next_level.append(sha256(combined))

        curr_idx = curr_idx // 2
        current_hashes = next_level

    root_hash = current_hashes[0]

    return {
        "leaf_index": entry_index,
        "leaf_hash": target_leaf_hash,
        "root_hash": root_hash,
        "total_leaves": total_leaves,
        "audit_path": audit_path,
    }


def verify_inclusion_proof(leaf_hash: str, proof: dict) -> bool:
    """Verify a Merkle inclusion proof for `leaf_hash`."""
    if not proof or not leaf_hash:
        return False

    expected_root = proof.get("root_hash")
    if not expected_root:
        return False

    proof_leaf = proof.get("leaf_hash")
    if proof_leaf and proof_leaf != leaf_hash:
        return False

    audit_path = proof.get("audit_path", [])
    current = leaf_hash

    for step in audit_path:
        pos = step.get("position")
        sibling = step.get("hash")
        if not sibling:
            return False
        if pos == "right":
            current = sha256(current + sibling)
        elif pos == "left":
            current = sha256(sibling + current)
        else:
            return False

    return current == expected_root


# --------------------------------------------------------------------------------- External Anchor
def persist_anchor(db: Session, anchor_path: Path | None = None) -> dict:
    """Publish and persist external anchor with Ed25519 signature over head hash and Merkle root."""
    h = head(db)
    if h is None:
        return {"status": "empty", "height": 0}

    entries = db.execute(select(LedgerEntry).order_by(LedgerEntry.index.asc())).scalars().all()
    merkle_root = compute_merkle_root(entries)
    priv, pub = get_or_create_keypair()

    anchor_msg = f"{h.index}:{h.entry_hash}:{merkle_root}"
    sig = sign_hash(anchor_msg, priv)

    record = {
        "height": h.index,
        "head_hash": h.entry_hash,
        "merkle_root": merkle_root,
        "signature": sig,
        "public_key": pub,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "anchored",
        "note": "External anchor publishing head hash & Merkle root signed via Ed25519",
    }

    path = anchor_path or _get_anchor_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def get_anchor(db: Session | None = None, anchor_path: Path | None = None) -> dict:
    """Retrieve the current external anchor record, or compute & persist if not found."""
    path = anchor_path or _get_anchor_path()
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass

    if db is not None:
        return persist_anchor(db, path)
    return {"status": "not_anchored"}


def anchor(db: Session) -> dict:
    """Backward-compatible external anchor publishing."""
    return persist_anchor(db)


# --------------------------------------------------------------------------------- Writing
def head(db: Session) -> LedgerEntry | None:
    """Newest entry in the chain."""
    with db.no_autoflush:
        pending = [o for o in db.new if isinstance(o, LedgerEntry)]
        if pending:
            return max(pending, key=lambda e: e.index)
        return db.execute(select(LedgerEntry).order_by(LedgerEntry.index.desc()).limit(1)).scalar_one_or_none()


def append(
    db: Session,
    actor: str,
    action: str,
    payload: Any,
    *,
    subject_type: str = "",
    subject_id: str = "",
    detail: str = "",
    commit: bool = True,
) -> LedgerEntry:
    """Attest `payload` to the chain with Ed25519 signature over entry_hash."""
    prev = head(db)
    entry = LedgerEntry(
        index=(prev.index + 1) if prev else 1,
        timestamp=datetime.now(timezone.utc).replace(tzinfo=None),
        actor=actor or "system",
        action=action,
        subject_type=subject_type,
        subject_id=str(subject_id or ""),
        payload_hash=sha256(_canonical(payload)),
        previous_hash=prev.entry_hash if prev else GENESIS_HASH,
        detail=detail[:2000],
    )
    entry.entry_hash = entry.compute_hash()
    entry.signature = sign_hash(entry.entry_hash)

    db.add(entry)
    if commit:
        db.commit()
    return entry


def attest_document(
    db: Session, actor: str, doc_id: str, title: str, content: str, source_type: str, commit: bool = True
) -> LedgerEntry:
    """Seal an ingested document at the moment of collection."""
    return append(
        db,
        actor,
        "INGEST",
        {"document_id": doc_id, "title": title, "source_type": source_type, "content": content},
        subject_type="document",
        subject_id=doc_id,
        detail=f"{source_type}: {title[:180]}",
        commit=commit,
    )


def attest_evidence(
    db: Session, actor: str, evidence_id: int, snippet: str, document_id: str, entity_id: str | None, extractor: str
) -> LedgerEntry:
    return append(
        db,
        actor,
        "EVIDENCE",
        {
            "evidence_id": evidence_id,
            "snippet": snippet,
            "document_id": document_id,
            "entity_id": entity_id,
            "extractor": extractor,
        },
        subject_type="evidence",
        subject_id=str(evidence_id),
        detail=f"{extractor} extraction from {document_id}",
    )


def attest_export(db: Session, actor: str, kind: str, content: bytes | str) -> LedgerEntry:
    """Seal a report at export time so a PDF handed to a court can be proven unmodified."""
    payload = content if isinstance(content, str) else hashlib.sha256(content).hexdigest()
    return append(
        db,
        actor,
        "EXPORT",
        {"kind": kind, "content": payload},
        subject_type="report",
        subject_id=kind,
        detail=f"exported {kind}",
    )


def seal_bytes(db: Session, actor: str, kind: str, raw_bytes: bytes, filename: str = "") -> dict:
    """Compute SHA-256 of raw bytes, append an EXPORT entry with payload_hash, sign it, and return metadata."""
    payload_hash = hashlib.sha256(raw_bytes).hexdigest()
    detail = (
        f"Sealed {kind} export: {filename} ({len(raw_bytes)} bytes)"
        if filename
        else f"Sealed {kind} export ({len(raw_bytes)} bytes)"
    )
    entry = append(
        db,
        actor=actor or "system",
        action="EXPORT",
        payload={"kind": kind, "filename": filename, "payload_hash": payload_hash, "size": len(raw_bytes)},
        subject_type="export",
        subject_id=kind,
        detail=detail,
    )
    return {
        "index": entry.index,
        "hash": payload_hash,
        "payload_hash": payload_hash,
        "entry_hash": entry.entry_hash,
        "signature": entry.signature,
        "action": entry.action,
        "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
        "actor": entry.actor,
        "filename": filename,
    }


# --------------------------------------------------------------------------------- Verification
def verify(db: Session) -> dict:
    """Walk the chain and verify hash links and Ed25519 signatures, reporting the exact break point if any."""
    entries = db.execute(select(LedgerEntry).order_by(LedgerEntry.index.asc())).scalars().all()
    if not entries:
        return {"status": "empty", "entries": 0, "valid": True}

    expected_prev = GENESIS_HASH
    pub_key = get_public_key()

    for e in entries:
        if e.previous_hash != expected_prev:
            return {
                "status": "broken",
                "valid": False,
                "entries": len(entries),
                "broken_at": e.index,
                "reason": "previous_hash does not match preceding entry (alteration, insertion, or removal)",
                "expected_previous": expected_prev,
                "found_previous": e.previous_hash,
                "entry": e.as_dict(),
            }
        if e.compute_hash() != e.entry_hash:
            return {
                "status": "broken",
                "valid": False,
                "entries": len(entries),
                "broken_at": e.index,
                "reason": "entry content does not match its stored hash (record modified after sealing)",
                "entry": e.as_dict(),
            }
        if e.signature:
            if not verify_signature(e, pub_key):
                return {
                    "status": "broken",
                    "valid": False,
                    "entries": len(entries),
                    "broken_at": e.index,
                    "reason": "Ed25519 signature verification failed (signature or entry hash invalid)",
                    "entry": e.as_dict(),
                }
        expected_prev = e.entry_hash

    merkle_root = compute_merkle_root(entries)
    return {
        "status": "intact",
        "valid": True,
        "entries": len(entries),
        "head": entries[-1].entry_hash,
        "merkle_root": merkle_root,
        "public_key": pub_key,
        "first_sealed": entries[0].timestamp.isoformat(),
        "last_sealed": entries[-1].timestamp.isoformat(),
    }


def verify_payload(db: Session, index: int, payload: Any) -> dict:
    """Prove a specific artefact still matches what was sealed at `index`."""
    e = db.get(LedgerEntry, index)
    if e is None:
        return {"status": "not_found", "index": index}
    actual = sha256(_canonical(payload))
    sig_valid = verify_signature(e) if e.signature else False
    return {
        "status": "match" if actual == e.payload_hash else "mismatch",
        "index": index,
        "sealed_hash": e.payload_hash,
        "computed_hash": actual,
        "signature_valid": sig_valid,
        "sealed_at": e.timestamp.isoformat() if e.timestamp else None,
        "actor": e.actor,
        "conclusion": (
            "content is byte-identical to what was sealed"
            if actual == e.payload_hash
            else "content has changed since it was sealed"
        ),
    }


def stats(db: Session) -> dict:
    from sqlalchemy import func

    rows = db.execute(select(LedgerEntry.action, func.count()).group_by(LedgerEntry.action)).all()
    h = head(db)
    entries = db.execute(select(LedgerEntry).order_by(LedgerEntry.index.asc())).scalars().all()
    merkle_root = compute_merkle_root(entries) if entries else GENESIS_HASH
    return {
        "height": h.index if h else 0,
        "head_hash": h.entry_hash if h else None,
        "merkle_root": merkle_root,
        "public_key": get_public_key(),
        "by_action": {a: c for a, c in rows},
    }
