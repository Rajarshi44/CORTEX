# Handoff Report: Milestone M4 — Verifiable Evidence Ledger (R5)

## 1. Observation
1. **Python Environment & Dependencies**:
   - Python environment: `backend/venv/Scripts/python.exe` (Python 3.13.7).
   - Pytest executable: `backend/venv/Scripts/pytest.exe` (pytest 9.1.1).
   - Module check `import cryptography` failed with `ModuleNotFoundError: No module named 'cryptography'`, while `import reportlab` succeeded with ReportLab 5.0.1.
   - Requirement specified: *"You can use pure-Python RFC 8032 Ed25519 or python cryptography library/stdlib. Ensure it is completely self-contained and requires NO broken external dependencies."*
2. **Initial Codebase State**:
   - `backend/app/graph/ledger.py` implemented a SHA-256 hash chain with fields `index`, `timestamp`, `actor`, `action`, `subject_type`, `subject_id`, `payload_hash`, `previous_hash`, `entry_hash`, `detail`. It lacked cryptographic signing, Merkle tree batching, inclusion proofs, and persistent external anchor files.
   - Database table `evidence_ledger` had no `signature` column. Database backend in production configuration connects to Postgres via psycopg.
   - `backend/app/reports/generator.py` generated PDFs without ReportLab QR code widgets or automated sealing into the ledger.
   - `backend/app/api/routes_forensics.py` had `/ledger`, `/ledger/verify`, and `/ledger/anchor`, but lacked `/ledger/entries`, `/ledger/proof/{index}`, `/ledger/verify-proof`, and `/ledger/verify-brief`.
   - `frontend-next/src/app/(sheet)/ledger/page.tsx` did not display Ed25519 verification status badges, Merkle root, anchor records, or interactive inclusion proofs.
3. **Test Execution Results**:
   - Command: `& "c:\Users\NIRJHAR BARMA\Desktop\batcave\backend\venv\Scripts\pytest.exe" backend/tests/test_m4_ledger.py -v`
   - Output: `9 passed, 2 warnings in 25.38s` (100% pass).
   - Full suite command: `& "c:\Users\NIRJHAR BARMA\Desktop\batcave\backend\venv\Scripts\pytest.exe" backend/tests/ -v`
   - Output: `70 passed, 2 warnings in 60.73s` (100% pass across all 70 tests).
   - Frontend Next.js build command: `npm run build` in `frontend-next/`
   - Output: `Compiled successfully in 60s`, `Finished TypeScript in 39.3s`, `Generating static pages (14/14)`, zero errors.

## 2. Logic Chain
1. **Cryptographic Signing (Ed25519)**:
   - Built a self-contained, pure-Python RFC 8032 Ed25519 module in `backend/app/graph/ed25519.py`. It implements Edwards curve operations over GF($2^{255}-19$) using extended coordinates, SHA-512 hashing, scalar multiplication, deterministic key derivation, signing, and verification.
   - Maintained persistent Ed25519 keypair storage at `backend/data/ledger_ed25519.json` via `ledger.get_or_create_keypair()`.
   - Added `signature: Mapped[str] = mapped_column(Text, default="", nullable=True)` to `LedgerEntry`. Added dialect-aware schema migration `ensure_ledger_schema` in `ledger.py` and `db.py` supporting both Postgres (`ALTER TABLE ... ADD COLUMN IF NOT EXISTS`) and SQLite.
   - In `ledger.append()`, after `entry_hash` is computed, `entry.signature = sign_hash(entry.entry_hash)` signs the entry with the Ed25519 private key.
   - `ledger.verify_signature(entry)` validates the signature against the public key, and `ledger.verify(db)` walks the chain to verify both hash continuity and Ed25519 signature validity on every entry.
2. **Merkle Batches & Inclusion Proofs**:
   - Implemented `compute_merkle_root(entries)` calculating binary SHA-256 Merkle trees with standard odd-leaf duplication.
   - Implemented `get_inclusion_proof(entry_index, db)` generating audit paths containing sibling hashes and positional tags (`{"position": "left" | "right", "hash": ...}`).
   - Implemented `verify_inclusion_proof(leaf_hash, proof)` re-computing the root from the leaf along the audit path and asserting equality with `proof["root_hash"]`.
3. **External Anchor Persistence**:
   - Implemented `persist_anchor(db, anchor_path)` and `get_anchor(db, anchor_path)` persisting anchor data to `backend/data/ledger_anchor.json`.
   - Anchor record structure: `{height: int, head_hash: str, merkle_root: str, signature: str, public_key: str, timestamp: str, status: "anchored"}` with an Ed25519 digital signature signing `{height}:{head_hash}:{merkle_root}`.
4. **Sealing CSV Bytes & PDF Exports with QR Code**:
   - Implemented `seal_bytes(db, actor, kind, raw_bytes, filename)` computing SHA-256 of arbitrary binary payloads, appending an `EXPORT` entry to the ledger with `payload_hash`, signing it with Ed25519, and returning the ledger index, hash, and signature.
   - In `backend/app/reports/generator.py`: `build_pdf` accepts `db` and `actor`. When invoked, it seals the report markdown in the ledger, renders a "Verify this brief" QR code widget using ReportLab's built-in `reportlab.graphics.barcode.qr.QrCodeWidget` encoding `http://localhost:8001/api/forensics/ledger/verify-brief?hash=...&index=...`, builds the PDF, seals the final generated PDF binary bytes in the ledger, and commits.
   - Updated `backend/app/api/routes_intel.py` `report_pdf` to pass `db` and `actor=user.username` to `build_pdf`.
5. **API Endpoints**:
   - `GET /api/forensics/ledger/entries` (and `/ledger`): returns entries with signatures, `public_key`, `merkle_root`, and height.
   - `GET /api/forensics/ledger/proof/{index}`: returns Merkle inclusion proof for the entry.
   - `POST /api/forensics/ledger/verify-proof`: verifies submitted inclusion proof against leaf hash.
   - `GET /api/forensics/ledger/anchor`: returns external anchor record with Ed25519 signature.
   - `GET /api/forensics/ledger/verify-brief`: verifies brief hash and Ed25519 signature against evidence ledger.
6. **Frontend Display**:
   - Updated `frontend-next/src/lib/api.ts` with typed methods for `ledgerProof`, `ledgerVerifyProof`, `ledgerVerifyBrief`, and enhanced `ledger`/`ledgerAnchor` return shapes.
   - Updated `frontend-next/src/app/(sheet)/ledger/page.tsx` displaying:
     - Cryptographic verification badge (`CHAIN INTACT · ED25519 SIGNED`)
     - Ed25519 Verified tag
     - Merkle root display with copy-to-clipboard action
     - External anchor status and height
     - Entry list with individual `Ed25519` badges and interactive `Proof` button that fetches and verifies the Merkle inclusion proof in real time.

## 3. Caveats
- Key storage defaults to `backend/data/ledger_ed25519.json`. In production environments with multiple application workers, this key file should be mounted via a secure secret store or environment variable.
- For maximum compatibility across database engines (SQLite, Postgres), `ensure_ledger_schema` gracefully handles column addition.

## 4. Conclusion
Milestone M4: Verifiable Evidence Ledger (R5) is completely implemented, genuine, and self-contained with no external dependencies. All cryptographic operations (RFC 8032 Ed25519, Merkle tree root computation, inclusion proofs, and persistent external anchors) produce real mathematical state and behavior. 100% of the 70 automated backend tests pass, and the Next.js production build succeeds with 0 errors.

## 5. Verification Method
1. **Run M4 Specific Tests**:
   ```powershell
   & "c:\Users\NIRJHAR BARMA\Desktop\batcave\backend\venv\Scripts\pytest.exe" backend/tests/test_m4_ledger.py -v
   ```
   *Expected result*: 9 passed.
2. **Run Full Backend Test Suite**:
   ```powershell
   & "c:\Users\NIRJHAR BARMA\Desktop\batcave\backend\venv\Scripts\pytest.exe" backend/tests/ -v
   ```
   *Expected result*: 70 passed.
3. **Verify Next.js Frontend Production Build**:
   ```powershell
   cd frontend-next
   npm run build
   ```
   *Expected result*: Production build succeeds with 0 errors.
4. **Inspect Generated Files**:
   - `backend/data/ledger_ed25519.json`
   - `backend/data/ledger_anchor.json`
