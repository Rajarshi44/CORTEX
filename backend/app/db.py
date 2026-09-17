"""SQLAlchemy models + session management (SQLite by default, Postgres-ready)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Iterator

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    create_engine,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

from .config import settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32), default="analyst")  # admin | analyst | viewer
    full_name: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Case(Base):
    __tablename__ = "cases"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Document(Base):
    """Any ingested artifact: an FIR, a CDR batch, a bank statement, a surveillance log, a post."""

    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("cases.id"), nullable=True)
    source_type: Mapped[str] = mapped_column(String(32), index=True)  # FIR|CDR|TRANSACTION|SURVEILLANCE|SOCIAL|INTEL|KYC
    title: Mapped[str] = mapped_column(String(300))
    content: Mapped[str] = mapped_column(Text, default="")
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    record_count: Mapped[int] = mapped_column(Integer, default=1)


class Entity(Base):
    __tablename__ = "entities"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    type: Mapped[str] = mapped_column(String(32), index=True)
    label: Mapped[str] = mapped_column(String(300), index=True)
    canonical_key: Mapped[str] = mapped_column(String(300), index=True)  # normalized key used for resolution
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    mention_count: Mapped[int] = mapped_column(Integer, default=0)
    first_seen: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    __table_args__ = (Index("ix_entities_type_key", "type", "canonical_key", unique=True),)


class Relationship(Base):
    __tablename__ = "relationships"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(36), ForeignKey("entities.id"), index=True)
    target_id: Mapped[str] = mapped_column(String(36), ForeignKey("entities.id"), index=True)
    rel_type: Mapped[str] = mapped_column(String(48), index=True)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    count: Mapped[int] = mapped_column(Integer, default=1)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    first_seen: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)

    __table_args__ = (Index("ix_rel_unique", "source_id", "target_id", "rel_type", unique=True),)


class Evidence(Base):
    """Provenance: which document/snippet supports an entity or a relationship."""

    __tablename__ = "evidence"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(String(36), ForeignKey("documents.id"), index=True)
    entity_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("entities.id"), nullable=True, index=True)
    relationship_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("relationships.id"), nullable=True, index=True
    )
    snippet: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    extractor: Mapped[str] = mapped_column(String(32), default="rules")  # rules | llm | structured

    document: Mapped[Document] = relationship()


class TimelineEvent(Base):
    """Normalized, entity-attributed events (calls, transfers, sightings, posts, FIR filings)."""

    __tablename__ = "timeline_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(String(36), ForeignKey("documents.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)  # CALL|TRANSFER|SIGHTING|POST|FIR|INTEL
    occurred_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    entity_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    summary: Mapped[str] = mapped_column(String(500), default="")
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kind: Mapped[str] = mapped_column(String(48), index=True)
    severity: Mapped[str] = mapped_column(String(16), index=True)  # low|medium|high|critical
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    score: Mapped[float] = mapped_column(Float, default=0.0)
    entity_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="open")  # open|reviewing|dismissed|confirmed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class EntityNote(Base):
    __tablename__ = "entity_notes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_id: Mapped[str] = mapped_column(String(36), ForeignKey("entities.id"), index=True)
    username: Mapped[str] = mapped_column(String(64))
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    detail: Mapped[str] = mapped_column(Text, default="")
    ip: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class Watch(Base):
    """A standing request: say something when a record touches this selector.

    The detectors in `graph/anomalies.py` reason over the whole corpus and are replaced on every
    recompute. That is the right shape for "this cluster looks like structuring" and the wrong shape
    for "tell me the moment anything mentions this number". CCTNS runs the second kind nationally -
    the auto-match services for missing/found persons and missing/found vehicles - and a Watch is
    that, generalised: one selector, checked against every arriving record, kept with the document
    that triggered it.

    `norm` is the matching key, never the thing the analyst typed. For a sensitive government
    identifier it is a salted fingerprint, so a watch on an Aadhaar number can fire without the
    number ever being stored - the same guarantee `ingestion/identifiers.py` gives the graph.
    """

    __tablename__ = "watches"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kind: Mapped[str] = mapped_column(String(24), index=True)  # PERSON|ORGANIZATION|PHONE|VEHICLE|BANK_ACCOUNT|GOV_ID|TEXT
    selector: Mapped[str] = mapped_column(String(300))  # display form; masked for a sensitive identifier
    norm: Mapped[str] = mapped_column(String(300), index=True)  # matching key
    reason: Mapped[str] = mapped_column(Text, default="")  # why it is watched; copied onto every hit
    severity: Mapped[str] = mapped_column(String(16), default="high")  # stamped on hits
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_by: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_hit_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    hit_count: Mapped[int] = mapped_column(Integer, default=0)

    # One selector is watched once. A second analyst asking for the same number joins the existing
    # watch rather than doubling every alert it raises.
    __table_args__ = (Index("ix_watch_kind_norm", "kind", "norm", unique=True),)


class WatchHit(Base):
    """One arriving record matched one watch.

    Durable by design: unlike a detector alert, a hit is a historical fact about a document that
    arrived, so a recompute must never delete it. `entity_id` is "" when the match was on document
    text rather than on a resolved entity, which keeps the uniqueness index usable on SQLite (where
    NULLs do not compare equal and would let the same hit insert twice).
    """

    __tablename__ = "watch_hits"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    watch_id: Mapped[str] = mapped_column(String(36), ForeignKey("watches.id"), index=True)
    document_id: Mapped[str] = mapped_column(String(36), ForeignKey("documents.id"), index=True)
    entity_id: Mapped[str] = mapped_column(String(36), default="", index=True)
    matched_on: Mapped[str] = mapped_column(String(200), default="")  # what matched, in words
    snippet: Mapped[str] = mapped_column(Text, default="")
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    status: Mapped[str] = mapped_column(String(16), default="new", index=True)  # new|reviewing|dismissed|confirmed

    watch: Mapped[Watch] = relationship()
    document: Mapped[Document] = relationship()

    __table_args__ = (Index("ix_watch_hit_unique", "watch_id", "document_id", "entity_id", unique=True),)


class AnalysisSnapshot(Base):
    """Cached results of the last analytics run so the UI loads instantly."""

    __tablename__ = "analysis_snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(48), unique=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    stale: Mapped[bool] = mapped_column(Boolean, default=False)


# --------------------------------------------------------------------------------------
# Engine / session
# --------------------------------------------------------------------------------------
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args, json_serializer=json.dumps)

if settings.database_url.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _):  # pragma: no cover - trivial
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    from .graph import ledger  # noqa: F401  (registers the evidence_ledger table on Base)

    Base.metadata.create_all(engine)
    ledger.ensure_ledger_schema(engine)


def get_session() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
