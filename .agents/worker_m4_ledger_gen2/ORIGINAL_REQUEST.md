## 2026-09-17T20:33:34Z

You are worker_m4_ledger_gen2, a specialized implementation worker replacing worker_m4_ledger which was interrupted by a network failure.

Working directory: `c:\Users\NIRJHAR BARMA\Desktop\batcave\.agents\worker_m4_ledger_gen2`
Project root: `c:\Users\NIRJHAR BARMA\Desktop\batcave`
Python environment: `c:\Users\NIRJHAR BARMA\Desktop\batcave\backend\venv\Scripts\python.exe`
Pytest: `c:\Users\NIRJHAR BARMA\Desktop\batcave\backend\venv\Scripts\pytest.exe`

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A Forensic Auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Your assigned task: Milestone M4 — Verifiable Evidence Ledger (R5)
"Implement 'blockchain' claims using real cryptography: Sign entries (Ed25519) and create Merkle batches with inclusion proofs using a standard Python crypto library. Persist an external anchor, seal CSV bytes and PDF exports, and add a 'verify this brief' QR code."

Requirements & Steps:
1. Cryptographic Signing (Ed25519):
   - Implement real Ed25519 key management and signing/verification in `backend/app/graph/ledger.py`.
   - You can use pure-Python RFC 8032 Ed25519 or python cryptography library/stdlib. Ensure it is completely self-contained and requires NO broken external dependencies.
   - Maintain a persistent keypair (e.g. in `backend/data/ledger_ed25519.json`).
   - In `LedgerEntry` model and database schema, add field `signature` (Text or String, storing hex/base64 signature).
   - When an entry is appended, sign `entry_hash` with the Ed25519 private key.
   - Provide `verify_signature(entry)` function to verify the signature against the public key.

2. Merkle Batches & Inclusion Proofs:
   - Implement Merkle tree calculation over ledger entries in `backend/app/graph/ledger.py`.
   - Group entries into Merkle trees (or compute over chain of entries).
   - Implement `get_inclusion_proof(entry_index: int)` returning:
     `{"leaf_index": index, "leaf_hash": hash, "root_hash": root, "audit_path": [{"position": "left"|"right", "hash": ...}]}`
   - Implement `verify_inclusion_proof(leaf_hash: str, proof: dict) -> bool`.

3. External Anchor Persistence:
   - Implement external anchor publishing and persistence in `backend/app/graph/ledger.py`:
     Save anchor records to persistent storage (`backend/data/ledger_anchor.json`).
     The anchor stores: `{height: int, head_hash: str, merkle_root: str, signature: str, timestamp: str, status: "anchored"}`.
     Provide `get_anchor()` and `persist_anchor()` functions.

4. Sealing CSV Bytes & PDF Exports:
   - Implement `seal_bytes(db: Session, actor: str, kind: str, raw_bytes: bytes, filename: str) -> dict`:
     Computes SHA-256 of raw bytes, appends an `EXPORT` entry in the ledger with `payload_hash`, signs it, returns signature, hash, and ledger index.
   - In `backend/app/reports/generator.py`:
     - When `build_pdf` is called, seal the report bytes in the ledger.
     - Add a "Verify this brief" QR code section on the PDF:
       Use ReportLab's built-in `reportlab.graphics.barcode.qr.QrCodeWidget` (or render a QR code into the PDF drawing).
       The QR code encodes the verification URL (e.g. `http://localhost:8001/api/forensics/ledger/verify-brief?hash=...&index=...`) and seal info.

5. API Endpoints:
   - In `backend/app/api/routes_forensics.py`:
     - `GET /api/forensics/ledger/entries` (includes signatures, public key, merkle root)
     - `GET /api/forensics/ledger/proof/{index}` (returns Merkle inclusion proof)
     - `POST /api/forensics/ledger/verify-proof` (verifies inclusion proof)
     - `GET /api/forensics/ledger/anchor` (returns external anchor)
     - `GET /api/forensics/ledger/verify-brief` (verifies brief hash and signature)

6. Frontend Display:
   - In `frontend-next/src/app/(sheet)/ledger/page.tsx`:
     - Ensure the UI displays the cryptographic verification status, Ed25519 signature badge, Merkle root, and external anchor status.

7. Verification:
   - Write comprehensive automated tests in `backend/tests/test_m4_ledger.py`:
     - Test Ed25519 key generation, entry signing, and signature verification.
     - Test tampering detection (modifying entry invalidates signature).
     - Test Merkle tree generation, inclusion proof creation, and proof verification.
     - Test external anchor persistence.
     - Test byte sealing for CSV and PDF.
     - Test QR code presence in generated PDF.
     - Test API endpoints.
   - Run tests using:
     `& "c:\Users\NIRJHAR BARMA\Desktop\batcave\backend\venv\Scripts\pytest.exe" backend/tests/test_m4_ledger.py -v`
   - Ensure all tests pass with 100% success.

8. Handoff:
   - Write `handoff.md` and `progress.md` in `c:\Users\NIRJHAR BARMA\Desktop\batcave\.agents\worker_m4_ledger_gen2\`.
   - Send completion message to orchestrator.
