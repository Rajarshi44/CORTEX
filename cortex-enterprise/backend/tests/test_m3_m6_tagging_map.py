"""Automated tests for Milestone M3 & M6: Synthetic Data Tagging & Map/UI Polish (R4, R6).

Verifies:
1. `sheet_identity` treats all ingested case corpus data as "real" system data by default:
   kind: "real", title: "Operation CyberHawk 2.0", code: "OPS-CH2",
   subtitle: "Delhi Crime Branch / IFSO Investigation Corpus (Verified Evidence)."
2. `describe()` in provenance module defaults to verified investigation provenance ("Real / Official Records").
3. Explicit unverified or synthetic tags override sheet_identity appropriately.
4. Manual provenance tagging endpoint `POST /api/sources/tag` updates and persists a document's provenance.
5. Manual provenance tagging endpoint `PUT /api/documents/{id}/provenance` updates and persists provenance.
6. Map endpoints `/api/geo` and `/api/geo/config` return Delhi coordinates [77.2090, 28.6139].
7. Document summary and detail API endpoints include provenance fields.
"""
from __future__ import annotations

from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import create_token
from app.db import Base, Document, User, get_session
from app.api.routes_graph import sheet_identity
from app.ingestion import provenance
from app.main import app


@pytest.fixture
def isolated_db(tmp_path: Path):
    """Create an isolated SQLite test database."""
    db_file = tmp_path / "test_m3_m6.db"
    engine = create_engine(f"sqlite:///{db_file.as_posix()}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def auth_token(isolated_db):
    """Generate an analyst JWT token."""
    user = User(username="analyst_test", password_hash="dummy", role="analyst", full_name="Analyst User")
    isolated_db.add(user)
    isolated_db.commit()
    return create_token(user)


@pytest.fixture
def client(isolated_db):
    """TestClient with overridden get_session."""
    def override_get_session():
        yield isolated_db

    app.dependency_overrides[get_session] = override_get_session
    c = TestClient(app, raise_server_exceptions=True)
    yield c
    app.dependency_overrides.clear()


# -----------------------------------------------------------------------------
# 1. Default to Real System Data (R4)
# -----------------------------------------------------------------------------

def test_sheet_identity_defaults_to_real_system_data(isolated_db):
    """Ingested case corpus data must default to real system data: kind='real', Operation CyberHawk 2.0."""
    # Seed an FIR document without explicit overrides
    doc = Document(
        id="doc-fir-001",
        source_type="FIR",
        title="FIR No. 42/2026 PS Special Cell",
        content="Investigation into cyber fraud syndicate.",
        meta={"fir_num": "42/2026"},
    )
    isolated_db.add(doc)
    isolated_db.commit()

    ident = sheet_identity(isolated_db)
    assert ident["kind"] == "real", f"Expected 'real', got {ident['kind']}"
    assert ident["title"] == "Operation CyberHawk 2.0"
    assert ident["code"] == "OPS-CH2"
    assert "Delhi Crime Branch / IFSO Investigation Corpus (Verified Evidence)" in ident["subtitle"]


def test_sheet_identity_empty_and_public(isolated_db):
    """Empty DB returns kind='empty'; public-only DB returns kind='real' with PRS-IN."""
    # Empty
    assert sheet_identity(isolated_db)["kind"] == "empty"

    # Only public record
    doc_pub = Document(
        id="doc-watchlist-001",
        source_type="WATCHLIST",
        title="OpenSanctions Watchlist Entry",
        meta={},
    )
    isolated_db.add(doc_pub)
    isolated_db.commit()

    ident = sheet_identity(isolated_db)
    assert ident["kind"] == "real"
    assert ident["code"] == "PRS-IN"


def test_sheet_identity_respects_explicit_overrides(isolated_db):
    """Explicitly tagged synthetic or unverified documents must override sheet_identity kind."""
    doc_real = Document(
        id="doc-real-001",
        source_type="FIR",
        title="FIR 1",
        meta={},
    )
    isolated_db.add(doc_real)
    isolated_db.commit()

    # Still real by default
    assert sheet_identity(isolated_db)["kind"] == "real"

    # Add an explicitly synthetic document
    doc_synth = Document(
        id="doc-synth-001",
        source_type="CDR",
        title="Synthetic CDR Dump",
        meta={"provenance": "Synthetic Override"},
    )
    isolated_db.add(doc_synth)
    isolated_db.commit()

    ident_synth = sheet_identity(isolated_db)
    assert ident_synth["kind"] == "demo"
    assert "Synthetic Data" in ident_synth["subtitle"]

    # Remove synthetic, test unverified
    isolated_db.delete(doc_synth)
    doc_unver = Document(
        id="doc-unver-001",
        source_type="CDR",
        title="Unverified Lead",
        meta={"provenance": "Unverified"},
    )
    isolated_db.add(doc_unver)
    isolated_db.commit()

    ident_unver = sheet_identity(isolated_db)
    assert ident_unver["kind"] == "unverified"


def test_provenance_describe_defaults_to_verified(isolated_db):
    """describe() in provenance module defaults to 'Real / Official Records'."""
    doc = Document(
        id="doc-123",
        source_type="FIR",
        title="FIR 100",
        meta={},
    )
    info = provenance.describe(doc)
    assert info["provenance"] == "Real / Official Records"
    assert info["is_verified"] is True
    assert info["source_name"] == "First Information Report"

    # Explicit override
    doc.meta = {"provenance": "Unverified"}
    info2 = provenance.describe(doc)
    assert info2["provenance"] == "Unverified"
    assert info2["is_verified"] is False


# -----------------------------------------------------------------------------
# 2. Manual Provenance Tagging Capabilities (R4)
# -----------------------------------------------------------------------------

def test_manual_tagging_endpoint_post_tag(client, isolated_db, auth_token):
    """POST /api/sources/tag allows analysts to manually tag document provenance with notes."""
    doc = Document(
        id="doc-tag-001",
        source_type="FIR",
        title="FIR 12/2026",
        content="FIR narrative text",
        meta={},
    )
    isolated_db.add(doc)
    isolated_db.commit()

    headers = {"Authorization": f"Bearer {auth_token}"}
    payload = {
        "document_id": "doc-tag-001",
        "provenance": "Real / Official Records",
        "notes": "Verified against state police portal registry.",
    }

    resp = client.post("/api/sources/tag", json=payload, headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["id"] == "doc-tag-001"
    assert data["provenance"] == "Real / Official Records"
    assert data["notes"] == "Verified against state police portal registry."
    assert data["tagged_by"] == "analyst_test"

    # Verify persistence in database
    isolated_db.expire_all()
    reloaded = isolated_db.get(Document, "doc-tag-001")
    assert reloaded.meta["provenance"] == "Real / Official Records"
    assert reloaded.meta["provenance_notes"] == "Verified against state police portal registry."

    # Now override to Unverified
    payload2 = {
        "document_id": "doc-tag-001",
        "provenance": "Unverified",
        "notes": "Awaiting official certified copy.",
    }
    resp2 = client.post("/api/sources/tag", json=payload2, headers=headers)
    assert resp2.status_code == 200
    assert resp2.json()["provenance"] == "Unverified"

    isolated_db.expire_all()
    reloaded2 = isolated_db.get(Document, "doc-tag-001")
    assert reloaded2.meta["provenance"] == "Unverified"
    assert reloaded2.meta.get("unverified") is True


def test_manual_tagging_endpoint_put_document_provenance(client, isolated_db, auth_token):
    """PUT /api/documents/{id}/provenance updates document provenance."""
    doc = Document(
        id="doc-put-002",
        source_type="CDR",
        title="CDR Tower Dump",
        content="CDR records",
        meta={},
    )
    isolated_db.add(doc)
    isolated_db.commit()

    headers = {"Authorization": f"Bearer {auth_token}"}
    payload = {
        "provenance": "Synthetic Override",
        "notes": "Analyst flagged as test synthetic data.",
    }

    resp = client.put(f"/api/documents/{doc.id}/provenance", json=payload, headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["ok"] is True
    assert resp.json()["provenance"] == "Synthetic Override"

    # Verify persistence
    isolated_db.expire_all()
    reloaded = isolated_db.get(Document, doc.id)
    assert reloaded.meta["provenance"] == "Synthetic Override"
    assert reloaded.meta.get("synthetic") is True


# -----------------------------------------------------------------------------
# 3. Fix Map Rendering & Center on Delhi (R6)
# -----------------------------------------------------------------------------

def test_geo_endpoints_return_delhi_coordinates(client, auth_token):
    """Geo API endpoints must configure and return Delhi coordinates [77.2090, 28.6139]."""
    headers = {"Authorization": f"Bearer {auth_token}"}

    # /api/geo
    resp_geo = client.get("/api/geo", headers=headers)
    assert resp_geo.status_code == 200, resp_geo.text
    geo_data = resp_geo.json()
    assert geo_data["center"] == [77.2090, 28.6139]
    assert geo_data["default_center"] == [77.2090, 28.6139]
    assert geo_data["zoom"] == 10.5
    assert geo_data["meta"]["default_center"] == [77.2090, 28.6139]

    # /api/geo/config
    resp_conf = client.get("/api/geo/config", headers=headers)
    assert resp_conf.status_code == 200, resp_conf.text
    conf_data = resp_conf.json()
    assert conf_data["center"] == [77.2090, 28.6139]
    assert conf_data["default_center"] == [77.2090, 28.6139]
    assert conf_data["city"] == "Delhi"
    assert conf_data["coordinates"]["lng"] == 77.2090
    assert conf_data["coordinates"]["lat"] == 28.6139


def test_documents_endpoint_includes_provenance(client, isolated_db, auth_token):
    """GET /api/ingest/documents and /api/ingest/documents/{id} include provenance field."""
    doc = Document(
        id="doc-list-001",
        source_type="JUDGMENT",
        title="Supreme Court Criminal Appeal 2024",
        content="Judgment text...",
        meta={"provenance": "Real / Official Records"},
    )
    isolated_db.add(doc)
    isolated_db.commit()

    headers = {"Authorization": f"Bearer {auth_token}"}
    resp = client.get("/api/ingest/documents", headers=headers)
    assert resp.status_code == 200
    docs = resp.json()
    assert len(docs) >= 1
    d_item = next(d for d in docs if d["id"] == "doc-list-001")
    assert d_item["provenance"] == "Real / Official Records"

    # Detail
    resp_det = client.get("/api/ingest/documents/doc-list-001", headers=headers)
    assert resp_det.status_code == 200
    assert resp_det.json()["provenance"] == "Real / Official Records"
