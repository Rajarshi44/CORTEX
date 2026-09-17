"""Comprehensive tests for Milestone M4: Verifiable Evidence Ledger (R5).

Covers:
1. Ed25519 cryptographic key management, signing, and verification.
2. Tamper-evident ledger integrity and tampering detection.
3. Merkle batch calculation, inclusion proofs, and proof verification.
4. External anchor persistence and verification.
5. Sealing arbitrary bytes (CSV, PDF) with EXPORT ledger records.
6. PDF report generation with embedded "Verify this brief" QR code.
7. Forensics API endpoints.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import create_token
from app.db import Base, Document, User
from app.graph import ed25519, ledger
from app.main import app
from app.reports.generator import build_pdf


# ----------------------------------------------------------------------------- Fixtures
@pytest.fixture
def isolated_db(tmp_path: Path):
    """Create a completely isolated SQLite test database for ledger verification."""
    db_file = tmp_path / "test_ledger.db"
    engine = create_engine(f"sqlite:///{db_file.as_posix()}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    ledger.ensure_ledger_schema(engine)
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def auth_token(isolated_db):
    """Generate an analyst JWT token for authenticated endpoints."""
    user = User(username="test_analyst", password_hash="dummy_hash", role="analyst", full_name="Test Investigator")
    isolated_db.add(user)
    isolated_db.commit()
    return create_token(user)


@pytest.fixture
def client(isolated_db):
    """TestClient wired with get_session overridden to isolated_db."""
    from app.db import get_session

    def override_get_session():
        yield isolated_db

    app.dependency_overrides[get_session] = override_get_session
    c = TestClient(app, raise_server_exceptions=True)
    yield c
    app.dependency_overrides.clear()


# ----------------------------------------------------------------------------- 1. Ed25519 Cryptography
def test_ed25519_keypair_generation_and_signatures():
    seed, pub = ed25519.generate_keypair()
    assert len(seed) == 32
    assert len(pub) == 32

    # Public key derivation is deterministic from seed
    assert ed25519.public_key_from_seed(seed) == pub

    msg = b"attestation-payload-test-string"
    sig = ed25519.sign(seed, msg)
    assert len(sig) == 64

    # Genuine signature verifies
    assert ed25519.verify(pub, msg, sig) is True

    # Modified message fails verification
    assert ed25519.verify(pub, b"tampered-payload", sig) is False

    # Corrupted signature fails verification
    corrupted_sig = bytearray(sig)
    corrupted_sig[10] ^= 0xFF
    assert ed25519.verify(pub, msg, bytes(corrupted_sig)) is False


def test_persistent_keypair_management(tmp_path: Path):
    key_file = tmp_path / "ledger_ed25519.json"
    assert not key_file.exists()

    priv1, pub1 = ledger.get_or_create_keypair(key_file)
    assert key_file.exists()
    assert len(priv1) == 64
    assert len(pub1) == 64

    # Second call reuses existing persistent key
    priv2, pub2 = ledger.get_or_create_keypair(key_file)
    assert priv1 == priv2
    assert pub1 == pub2

    # Signature made with persistent key verifies
    data_hash = hashlib.sha256(b"sample-entry").hexdigest()
    sig_hex = ledger.sign_hash(data_hash, priv1)
    entry_dict = {"entry_hash": data_hash, "signature": sig_hex}
    assert ledger.verify_signature(entry_dict, pub1) is True


# ----------------------------------------------------------------------------- 2. Ledger & Tamper Detection
def test_ledger_append_signs_and_verifies(isolated_db):
    entry1 = ledger.append(isolated_db, "officer1", "INGEST", {"data": "file-1"}, detail="First doc")
    assert entry1.index == 1
    assert entry1.signature
    assert len(entry1.signature) == 128  # 64 bytes in hex

    entry2 = ledger.append(isolated_db, "officer1", "EVIDENCE", {"item": "phone"}, detail="Found burner")
    assert entry2.index == 2
    assert entry2.previous_hash == entry1.entry_hash

    # Verification passes for intact chain
    report = ledger.verify(isolated_db)
    assert report["valid"] is True
    assert report["status"] == "intact"
    assert report["entries"] == 2
    assert report["merkle_root"]


def test_ledger_tampering_detection(isolated_db):
    e1 = ledger.append(isolated_db, "officer", "INGEST", {"data": "record-1"})
    e2 = ledger.append(isolated_db, "officer", "INGEST", {"data": "record-2"})
    e3 = ledger.append(isolated_db, "officer", "INGEST", {"data": "record-3"})
    assert ledger.verify(isolated_db)["valid"] is True

    # Tamper 1: modify detail/content of middle entry without recomputing hash
    e2.detail = "UNAUTHORIZED TAMPERING"
    isolated_db.commit()
    report1 = ledger.verify(isolated_db)
    assert report1["valid"] is False
    assert report1["status"] == "broken"
    assert report1["broken_at"] == 2
    assert "entry content does not match" in report1["reason"]

    # Tamper 2: recompute entry_hash so content matches hash, but signature is invalid
    e2.entry_hash = e2.compute_hash()
    isolated_db.commit()
    report2 = ledger.verify(isolated_db)
    assert report2["valid"] is False
    assert report2["broken_at"] == 2
    assert "signature verification failed" in report2["reason"] or "previous_hash does not match" in report2["reason"]


# ----------------------------------------------------------------------------- 3. Merkle Batches & Inclusion Proofs
def test_merkle_tree_calculation_and_proofs(isolated_db):
    # Empty ledger
    assert ledger.compute_merkle_root([]) == ledger.GENESIS_HASH

    # 1 entry
    e1 = ledger.append(isolated_db, "sys", "ALERT", {"id": 1})
    root1 = ledger.compute_merkle_root([e1])
    assert root1 == e1.entry_hash

    proof1 = ledger.get_inclusion_proof(e1.index, isolated_db)
    assert proof1["root_hash"] == root1
    assert ledger.verify_inclusion_proof(e1.entry_hash, proof1) is True

    # Append entries to create an odd number (5 total entries)
    entries = [e1]
    for i in range(2, 6):
        entries.append(ledger.append(isolated_db, "sys", "ALERT", {"id": i}))

    overall_root = ledger.compute_merkle_root(entries)
    assert len(overall_root) == 64

    # Every entry must have a valid inclusion proof
    for e in entries:
        proof = ledger.get_inclusion_proof(e.index, isolated_db)
        assert proof["leaf_index"] == e.index
        assert proof["leaf_hash"] == e.entry_hash
        assert proof["root_hash"] == overall_root
        assert len(proof["audit_path"]) > 0

        # Verify genuine proof
        assert ledger.verify_inclusion_proof(e.entry_hash, proof) is True

        # Tampered leaf fails
        assert ledger.verify_inclusion_proof("0" * 64, proof) is False

        # Corrupted audit step fails
        corrupted_proof = json.loads(json.dumps(proof))
        corrupted_proof["audit_path"][0]["hash"] = "f" * 64
        assert ledger.verify_inclusion_proof(e.entry_hash, corrupted_proof) is False


# ----------------------------------------------------------------------------- 4. External Anchor Persistence
def test_external_anchor_persistence(isolated_db, tmp_path: Path):
    anchor_file = tmp_path / "ledger_anchor.json"
    ledger.append(isolated_db, "user", "LOGIN", {"ip": "127.0.0.1"})
    ledger.append(isolated_db, "user", "INGEST", {"doc": 101})

    anchor = ledger.persist_anchor(isolated_db, anchor_file)
    assert anchor_file.exists()
    assert anchor["status"] == "anchored"
    assert anchor["height"] == 2
    assert anchor["head_hash"]
    assert anchor["merkle_root"]
    assert anchor["signature"]
    assert anchor["public_key"]

    # Verify anchor signature
    anchor_msg = f"{anchor['height']}:{anchor['head_hash']}:{anchor['merkle_root']}"
    assert ed25519.verify(
        bytes.fromhex(anchor["public_key"]),
        anchor_msg.encode("utf-8"),
        bytes.fromhex(anchor["signature"]),
    ) is True

    # Loading anchor from disk
    loaded = ledger.get_anchor(isolated_db, anchor_file)
    assert loaded["height"] == anchor["height"]
    assert loaded["signature"] == anchor["signature"]


# ----------------------------------------------------------------------------- 5. Byte Sealing (CSV & PDF)
def test_seal_bytes_csv_and_pdf(isolated_db):
    csv_content = b"id,name,amount\n1,Alice,5000\n2,Bob,9000\n"
    csv_seal = ledger.seal_bytes(isolated_db, "finance_officer", "csv", csv_content, "transactions.csv")

    assert csv_seal["index"] == 1
    assert csv_seal["action"] == "EXPORT"
    assert csv_seal["hash"] == hashlib.sha256(csv_content).hexdigest()
    assert csv_seal["signature"]
    assert ledger.verify_signature(csv_seal) is True

    # PDF bytes
    dummy_pdf = b"%PDF-1.4 sample pdf binary stream \x00\x01\x02%%EOF"
    pdf_seal = ledger.seal_bytes(isolated_db, "analyst", "pdf", dummy_pdf, "case_brief.pdf")
    assert pdf_seal["index"] == 2
    assert pdf_seal["hash"] == hashlib.sha256(dummy_pdf).hexdigest()
    assert ledger.verify_signature(pdf_seal) is True

    # Chain remains intact
    assert ledger.verify(isolated_db)["valid"] is True


# ----------------------------------------------------------------------------- 6. Report Generation with QR Code
def test_build_pdf_with_qr_code_and_ledger_sealing(isolated_db):
    md = "# Case Brief\n\n## Summary\nCritical network analysis brief for court evidence.\n"
    pdf_bytes = build_pdf(md, title="Court Brief", db=isolated_db, actor="investigator")

    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 500
    assert pdf_bytes.startswith(b"%PDF")

    # When db is passed, build_pdf seals both brief markdown and pdf bytes
    entries = isolated_db.query(ledger.LedgerEntry).order_by(ledger.LedgerEntry.index.asc()).all()
    assert len(entries) == 2
    assert entries[0].action == "EXPORT"
    assert "Court Brief.md" in entries[0].detail
    assert entries[1].action == "EXPORT"
    assert "Court Brief.pdf" in entries[1].detail

    # Both entries have genuine Ed25519 signatures
    assert ledger.verify_signature(entries[0]) is True
    assert ledger.verify_signature(entries[1]) is True


# ----------------------------------------------------------------------------- 7. API Endpoints
def test_api_ledger_endpoints(client, isolated_db, auth_token):
    headers = {"Authorization": f"Bearer {auth_token}"}

    # Append entries
    e1 = ledger.append(isolated_db, "analyst", "INGEST", {"doc": "FIR-01"})
    e2 = ledger.append(isolated_db, "analyst", "EVIDENCE", {"ev": "SIM-01"})

    # GET /api/forensics/ledger/entries
    r = client.get("/api/forensics/ledger/entries", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert "entries" in data
    assert len(data["entries"]) == 2
    assert "public_key" in data
    assert "merkle_root" in data
    assert data["height"] == 2

    # GET /api/forensics/ledger/proof/{index}
    r_proof = client.get("/api/forensics/ledger/proof/1", headers=headers)
    assert r_proof.status_code == 200
    proof_data = r_proof.json()
    assert proof_data["leaf_index"] == 1
    assert proof_data["leaf_hash"] == e1.entry_hash
    assert "root_hash" in proof_data
    assert "audit_path" in proof_data

    # POST /api/forensics/ledger/verify-proof (valid)
    r_ver = client.post(
        "/api/forensics/ledger/verify-proof",
        json={"leaf_hash": e1.entry_hash, "proof": proof_data},
        headers=headers,
    )
    assert r_ver.status_code == 200
    assert r_ver.json()["valid"] is True

    # POST /api/forensics/ledger/verify-proof (invalid leaf)
    r_bad = client.post(
        "/api/forensics/ledger/verify-proof",
        json={"leaf_hash": "a" * 64, "proof": proof_data},
        headers=headers,
    )
    assert r_bad.status_code == 200
    assert r_bad.json()["valid"] is False

    # GET /api/forensics/ledger/anchor
    r_anchor = client.get("/api/forensics/ledger/anchor", headers=headers)
    assert r_anchor.status_code == 200
    anchor_resp = r_anchor.json()
    assert anchor_resp["status"] == "anchored"
    assert anchor_resp["height"] >= 2
    assert "signature" in anchor_resp
    assert "merkle_root" in anchor_resp
    assert "head_hash" in anchor_resp

    # GET /api/forensics/ledger/verify-brief (valid)
    r_brief = client.get(f"/api/forensics/ledger/verify-brief?hash={e1.payload_hash}&index={e1.index}")
    assert r_brief.status_code == 200
    brief_data = r_brief.json()
    assert brief_data["status"] == "verified"
    assert brief_data["valid"] is True
    assert brief_data["signature_valid"] is True

    # GET /api/forensics/ledger/verify-brief (tampered hash)
    r_tampered = client.get(f"/api/forensics/ledger/verify-brief?hash=wrong_hash&index={e1.index}")
    assert r_tampered.status_code == 200
    assert r_tampered.json()["valid"] is False
    assert r_tampered.json()["status"] == "invalid"
