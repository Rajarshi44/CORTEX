"""Standing watches: selector normalisation, firing on ingest, backfill and de-duplication.

The suite runs against its own SQLite file rather than the app engine, so a test never writes to
the working sheet and the order test modules import in cannot matter.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, Document, Entity, Evidence, Relationship, Watch, WatchHit
from app.graph import ledger  # noqa: F401  (registers evidence_ledger on Base before create_all)
from app.ingestion import identifiers
from app.ingestion.pipeline import IngestionService
from app.watch import matcher

# A phone number the rule extractor will accept (ten digits, leading 6-9).
PHONE = "9876543210"
PLATE = "MH12AB1234"


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'watch.db').as_posix()}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def ingest(db, title: str, text: str, source_type: str = "INTEL") -> IngestionService:
    """Run one document through the real pipeline, so watches see what ingestion actually stores."""
    svc = IngestionService(db, use_llm=False, use_neural=False, seal_documents=False)
    svc.ingest_text(source_type, title, text)
    return svc


def valid_aadhaar() -> str:
    """A number that passes the Verhoeff check, found rather than hard-coded so the test cannot
    drift from the validator."""
    for tail in range(1000):
        candidate = f"2234{tail:08d}"
        ok, _ = identifiers.validate_aadhaar(candidate)
        if ok:
            return candidate
    raise AssertionError("no valid Aadhaar candidate found")


# ------------------------------------------------------------------------------- normalisation
@pytest.mark.parametrize("raw", [PHONE, f"+91 {PHONE}", f"0{PHONE}", "98765-43210"])
def test_phone_variants_share_one_key(raw):
    """However the number is written, the watch keys the same way the resolver does."""
    assert matcher.normalize("PHONE", raw)[0] == PHONE


def test_short_phone_is_refused():
    with pytest.raises(matcher.WatchError, match="ten digits"):
        matcher.normalize("PHONE", "98765")


def test_plate_ignores_spacing():
    assert matcher.normalize("VEHICLE", "mh 12 ab 1234")[0] == PLATE


def test_text_watch_needs_length():
    with pytest.raises(matcher.WatchError, match="four characters"):
        matcher.normalize("TEXT", "the")


def test_unknown_kind_is_refused():
    with pytest.raises(matcher.WatchError, match="Unknown watch kind"):
        matcher.normalize("FINGERPRINT", "whatever")


def test_aadhaar_is_fingerprinted_never_stored():
    """The whole point of a GOV_ID watch: it matches without the number entering the database."""
    number = valid_aadhaar()
    norm, display = matcher.normalize("GOV_ID", number)
    assert norm.startswith(matcher.FP)
    assert number not in norm and number not in display
    assert display.endswith(number[-4:]) and display.startswith("XXXX")


def test_aadhaar_failing_checksum_is_refused():
    with pytest.raises(matcher.WatchError):
        matcher.normalize("GOV_ID", "234567890123")


# ------------------------------------------------------------------------------- firing
def test_watch_fires_on_a_record_that_arrives_later(db):
    w, backfill, created = matcher.create(db, "PHONE", PHONE, "suspect handset", created_by="analyst")
    assert created and backfill == 0

    ingest(db, "Surveillance note", f"Subject contacted on {PHONE} before the meeting.")

    hits = db.query(WatchHit).all()
    assert len(hits) == 1
    assert hits[0].watch_id == w.id
    assert PHONE in hits[0].snippet
    assert db.get(Watch, w.id).hit_count == 1
    assert db.get(Watch, w.id).last_hit_at is not None


def test_backfill_answers_for_records_already_held(db):
    ingest(db, "Seizure report", f"Vehicle {PLATE} was impounded at the checkpoint.")
    w, backfill, created = matcher.create(db, "VEHICLE", PLATE, "wanted vehicle", created_by="analyst")
    assert created and backfill == 1
    assert db.query(WatchHit).filter(WatchHit.watch_id == w.id).count() == 1


def test_text_watch_matches_the_body(db):
    matcher.create(db, "TEXT", "hawala", "typology of interest", created_by="analyst")
    ingest(db, "Intelligence note", "Funds were moved through a hawala channel in Nagpur.")
    hit = db.query(WatchHit).one()
    assert hit.entity_id == ""  # matched text, not a resolved entity
    assert "hawala" in hit.snippet.lower()


def test_inactive_watch_does_not_fire(db):
    w, _, _ = matcher.create(db, "PHONE", PHONE, created_by="analyst")
    w.active = False
    db.commit()
    ingest(db, "Later note", f"Called {PHONE} twice.")
    assert db.query(WatchHit).count() == 0


def test_a_watch_never_double_reports_the_same_record(db):
    matcher.create(db, "PHONE", PHONE, created_by="analyst")
    ingest(db, "First note", f"Number {PHONE} seen.")
    assert db.query(WatchHit).count() == 1
    matcher.scan(db)          # rescan everything
    matcher.scan(db)          # and again
    assert db.query(WatchHit).count() == 1


def test_second_analyst_joins_an_existing_watch(db):
    first, _, created_a = matcher.create(db, "PHONE", PHONE, "handset", created_by="a")
    second, _, created_b = matcher.create(db, "PHONE", f"+91 {PHONE}", "same handset", created_by="b")
    assert created_a and not created_b
    assert first.id == second.id
    assert db.query(Watch).count() == 1


def test_a_new_record_fires_once_not_once_per_mention(db):
    matcher.create(db, "PHONE", PHONE, created_by="analyst")
    ingest(db, "Repetitive note", f"{PHONE} called. Then {PHONE} called again. Later {PHONE} once more.")
    assert db.query(WatchHit).count() == 1


def test_gov_id_watch_matches_the_ingested_identifier(db):
    number = valid_aadhaar()
    w, _, _ = matcher.create(db, "GOV_ID", number, "subject of enquiry", created_by="analyst")
    ingest(db, "KYC packet", f"Sunil Pawar holding Aadhaar {number} opened the account.")

    hits = db.query(WatchHit).filter(WatchHit.watch_id == w.id).all()
    assert len(hits) == 1
    # The graph stores the identifier masked, so neither the watch nor the hit carries the number.
    assert number not in (db.get(Watch, w.id).selector + hits[0].matched_on)
    assert not db.query(Entity).filter(Entity.label.contains(number)).count()


def test_watch_fires_on_a_party_that_only_exists_as_an_edge_endpoint(db):
    """The case that a first cut missed.

    A named party in a judgment enters the graph as one end of an ACCUSED_IN edge, so the sentence
    is filed under the relationship and the entity carries no evidence row of its own. On the real
    public-record sheet 218 entities are in that position, including the most-mentioned person on
    it. Reading only entity-level evidence left a watch on any of them silently never firing.
    """
    doc = Document(id="d1", source_type="JUDGMENT", title="State vs Umraniya", content="")
    party = Entity(id="e1", type="PERSON", label="Rajendra Umraniya", canonical_key="rajendra umraniya")
    case = Entity(id="e2", type="REPORT", label="Crl. Appeal 44/2019", canonical_key="crl appeal 44/2019")
    rel = Relationship(id="r1", source_id="e1", target_id="e2", rel_type="ACCUSED_IN")
    db.add_all([doc, party, case, rel])
    db.add(Evidence(document_id="d1", entity_id=None, relationship_id="r1",
                    snippet="the appellant Rajendra Umraniya was convicted under s.302"))
    db.commit()
    assert db.query(Evidence).filter(Evidence.entity_id.isnot(None)).count() == 0  # the premise

    w, backfill, _ = matcher.create(db, "PERSON", "Rajendra Umraniya", "absconding", created_by="analyst")
    assert backfill == 1
    hit = db.query(WatchHit).filter(WatchHit.watch_id == w.id).one()
    assert hit.entity_id == "e1"
    assert "Rajendra Umraniya" in hit.snippet


def test_a_partys_own_sentence_is_preferred_over_the_edges(db):
    """Entity-level evidence carries the better snippet, so it must not be displaced by edge text."""
    doc = Document(id="d1", source_type="JUDGMENT", title="State vs Umraniya", content="")
    party = Entity(id="e1", type="PERSON", label="Rajendra Umraniya", canonical_key="rajendra umraniya")
    case = Entity(id="e2", type="REPORT", label="Crl. Appeal 44/2019", canonical_key="crl appeal 44/2019")
    db.add_all([doc, party, case, Relationship(id="r1", source_id="e1", target_id="e2", rel_type="ACCUSED_IN")])
    db.add(Evidence(document_id="d1", entity_id="e1", snippet="ENTITY SENTENCE"))
    db.add(Evidence(document_id="d1", entity_id=None, relationship_id="r1", snippet="EDGE SENTENCE"))
    db.commit()

    matcher.create(db, "PERSON", "Rajendra Umraniya", created_by="analyst")
    assert db.query(WatchHit).one().snippet == "ENTITY SENTENCE"


def test_hits_survive_a_rescan_after_being_actioned(db):
    """A detector alert is replaced on recompute; a hit is a historical fact and must not be."""
    matcher.create(db, "PHONE", PHONE, created_by="analyst")
    ingest(db, "Note", f"Number {PHONE}.")
    hit = db.query(WatchHit).one()
    hit.status = "confirmed"
    db.commit()
    matcher.scan(db)
    assert db.query(WatchHit).one().status == "confirmed"


def test_remove_takes_its_hits_with_it(db):
    w, _, _ = matcher.create(db, "PHONE", PHONE, created_by="analyst")
    ingest(db, "Note", f"Number {PHONE}.")
    assert db.query(WatchHit).count() == 1
    assert matcher.remove(db, w.id) is True
    assert db.query(WatchHit).count() == 0
    assert db.query(Watch).count() == 0


def test_ingestion_reports_what_it_fired(db):
    matcher.create(db, "PHONE", PHONE, created_by="analyst")
    svc = ingest(db, "Note", f"Number {PHONE} in the log.")
    assert svc.stats.watch_hits == 1


def test_no_watches_means_no_work_and_no_hits(db):
    svc = ingest(db, "Note", f"Number {PHONE} in the log.")
    assert svc.stats.watch_hits == 0
    assert db.query(WatchHit).count() == 0
    assert db.query(Document).count() == 1
